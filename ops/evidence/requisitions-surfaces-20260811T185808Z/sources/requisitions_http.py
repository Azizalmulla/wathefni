"""HTTP routes for Requisitions surfaces (thin wrappers over frozen authority)."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


class ReqCreateBody(BaseModel):
    title_en: str
    title_ar: str | None = None
    department: str | None = None
    headcount: int = Field(default=1, ge=1, le=500)
    target_hire_date: str | None = None
    budget_ref: str | None = None
    position_id: str | None = None
    submit: bool = False
    idempotency_key: str | None = None


class ReqTransitionBody(BaseModel):
    to_status: str
    expected_row_version: int | None = None


class ReqLinkJobBody(BaseModel):
    job_id: str | None = None
    position_code: str | None = None


class ReqSettingsBody(BaseModel):
    enabled: bool | None = None
    jobs_require_approved_requisition: bool | None = None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "requisitions_denied")
    if err in {
        "requisitions_disabled",
        "requisitions_company_not_allowlisted",
        "requisitions_company_disabled",
    }:
        raise HTTPException(
            status_code=403,
            detail={"error": err, "message": "Requisitions is not enabled for this company.", "gate": result.get("gate")},
        )
    if err in {"requisition_not_found"}:
        raise HTTPException(status_code=404, detail={"error": err})
    if err in {"self_approval_forbidden", "permission_denied"}:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted (SoD)."})
    if err == "concurrency_conflict":
        raise HTTPException(status_code=409, detail={"error": err, "message": "Stale row — refresh and retry."})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_requisitions_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    _posthire_read_context = app_mod._posthire_read_context
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key

    import requisitions as rq
    import requisitions_surfaces as surfaces

    def _actor_role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or "").strip().lower()
        if role in {"manager", "hr", "admin", "owner"}:
            return role
        perms = context_permissions(context, dashboard_context_role_key(context))
        if "requisitions.approve" in perms or "requisitions.manage" in perms:
            return "hr"
        if str(context.get("scope") or "").lower() == "manager":
            return "manager"
        return role or "hr"

    def _perms(context: dict[str, Any], role: str) -> dict[str, bool]:
        perms = context_permissions(context, dashboard_context_role_key(context))
        return {
            "manage": "requisitions.manage" in perms or role in {"hr", "admin", "owner"},
            "approve": "requisitions.approve" in perms or role in {"hr", "admin", "owner"},
            "configure": role in {"hr", "admin", "owner"},
        }

    @app.get("/dashboard/prehire/requisitions")
    def dashboard_prehire_requisitions(
        offset: int = 0,
        limit: int = 100,
        search: str = "",
        status: str = "",
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        role = _actor_role(context)
        perms = _perms(context, role)
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                # Managers without approve see own requests; approvers see full queue.
                mgr_only = role == "manager" and not perms.get("approve")
                payload = surfaces.queue_payload(
                    cur,
                    company_code=company,
                    status=status or None,
                    search=search or None,
                    manager_scope_only=mgr_only,
                    actor_user_id=context.get("actor_user_id"),
                    limit=limit,
                    offset=offset,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        payload["permissions"] = perms
        return json_safe(payload)

    @app.get("/dashboard/prehire/requisitions/{requisition_id}")
    def dashboard_prehire_requisition_detail(
        requisition_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        role = _actor_role(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                payload = surfaces.detail_payload(
                    cur,
                    company_code=company,
                    requisition_id=requisition_id,
                    actor_user_id=context.get("actor_user_id"),
                    actor_role=role,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        payload["permissions"] = {**(payload.get("permissions") or {}), **_perms(context, role)}
        return json_safe(payload)

    @app.post("/dashboard/prehire/requisitions")
    def dashboard_prehire_requisition_create(
        body: ReqCreateBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        role = _actor_role(context)
        if not _perms(context, role).get("manage") and role == "viewer":
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                result = rq.create_requisition(
                    cur,
                    company_code=company,
                    title_en=body.title_en,
                    title_ar=body.title_ar,
                    department=body.department,
                    headcount=body.headcount,
                    target_hire_date=_parse_date(body.target_hire_date),
                    budget_ref=body.budget_ref,
                    position_id=body.position_id,
                    created_by_user_id=context.get("actor_user_id"),
                    created_by_phone=context.get("actor_phone"),
                    idempotency_key=body.idempotency_key,
                    submit=body.submit,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/prehire/requisitions/{requisition_id}/transition")
    def dashboard_prehire_requisition_transition(
        requisition_id: str,
        body: ReqTransitionBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        role = _actor_role(context)
        perms = _perms(context, role)
        dst = str(body.to_status or "").strip().lower()
        if dst in {"approved", "rejected"} and not perms.get("approve"):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "requisitions.approve required"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                result = rq.transition_requisition(
                    cur,
                    company_code=company,
                    requisition_id=requisition_id,
                    to_status=dst,
                    actor_user_id=context.get("actor_user_id"),
                    actor_phone=context.get("actor_phone"),
                    expected_row_version=body.expected_row_version,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/prehire/requisitions/{requisition_id}/link-job")
    def dashboard_prehire_requisition_link_job(
        requisition_id: str,
        body: ReqLinkJobBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        if not _perms(context, _actor_role(context)).get("manage"):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                result = rq.link_job_to_requisition(
                    cur,
                    company_code=company,
                    requisition_id=requisition_id,
                    position_code=(body.position_code or body.job_id or ""),
                    actor_user_id=context.get("actor_user_id"),
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.patch("/dashboard/prehire/requisition-settings")
    def dashboard_requisition_settings(
        body: ReqSettingsBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        if _actor_role(context) not in {"hr", "admin", "owner"}:
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                settings = rq.set_settings(
                    cur,
                    company,
                    enabled=body.enabled,
                    jobs_require_approved_requisition=body.jobs_require_approved_requisition,
                )
            conn.commit()
        return json_safe({"ok": True, "settings": settings})

    @app.get("/dashboard/mobile/requisitions")
    def mobile_requisitions(
        view: str = "attention",
        limit: int = 50,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        role = _actor_role(context)
        perms = _perms(context, role)
        status_map = {
            "attention": "attention",
            "pending_approval": "pending_approval",
            "approved": "approved",
            "open": "open",
            "draft": "draft",
        }
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                payload = surfaces.queue_payload(
                    cur,
                    company_code=company,
                    status=status_map.get(view, "attention"),
                    manager_scope_only=role == "manager" and not perms.get("approve"),
                    actor_user_id=context.get("actor_user_id"),
                    limit=limit,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        payload["view"] = view
        payload["permissions"] = perms
        return json_safe(payload)

    @app.get("/dashboard/mobile/requisitions/{requisition_id}")
    def mobile_requisition_detail(requisition_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        return dashboard_prehire_requisition_detail(requisition_id, context)

    @app.post("/dashboard/mobile/requisitions/{requisition_id}/transition")
    def mobile_requisition_transition(
        requisition_id: str,
        body: ReqTransitionBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_prehire_requisition_transition(requisition_id, body, context)

    @app.get("/dashboard/assistant/requisitions/{requisition_id}")
    def assistant_requisition_explain(
        requisition_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "requisitions")
        with db_connect() as conn:
            with conn.cursor() as cur:
                rq.ensure_requisitions_schema(cur)
                req = rq.get_requisition(cur, company_code=company, requisition_id=requisition_id)
                if not req:
                    raise HTTPException(status_code=404, detail={"error": "requisition_not_found"})
                explained = surfaces.explain_status(req)
            conn.commit()
        return json_safe({"ok": True, "requisition_id": requisition_id, **explained})
