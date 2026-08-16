"""HTTP route registration for Preboarding surfaces (thin wrappers)."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


class PreboardItemUpdateBody(BaseModel):
    to_status: str
    blocker_reason: str | None = None
    evidence_document_id: str | None = None
    expected_row_version: int | None = None


class PreboardWaiveBody(BaseModel):
    waive_reason: str = Field(min_length=2, max_length=500)
    expected_row_version: int | None = None


class PreboardJoiningDateBody(BaseModel):
    joining_date: str


class PreboardCancelBody(BaseModel):
    cancel_reason: str = "cancelled"


class PreboardCreateBody(BaseModel):
    employee_key: str
    joining_date: str | None = None
    manager_user_id: str | None = None
    application_id: str | None = None
    offer_id: str | None = None
    idempotency_key: str | None = None


class PreboardSettingsBody(BaseModel):
    enabled: bool | None = None
    auto_create_on_offer_accept: bool | None = None
    required_for_ready_mark: bool | None = None
    handoff_onboarding_enabled: bool | None = None


class PreboardRemindBody(BaseModel):
    item_key: str | None = None
    locale: str = "en"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "preboarding_denied")
    if err in {"preboarding_disabled", "preboarding_company_not_allowlisted", "preboarding_company_disabled"}:
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "Preboarding is not enabled for this company.",
                "gate": result.get("gate"),
            },
        )
    if err in {"assignment_not_found", "item_not_found", "employee_not_found"}:
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in {"manager_scope_denied", "waive_forbidden", "scope_denied"}:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted."})
    if err == "readiness_not_met":
        raise HTTPException(
            status_code=422,
            detail={"error": err, "message": "Required preboarding items are incomplete.", "readiness": result.get("readiness")},
        )
    if err == "cosmetic_ready_forbidden":
        raise HTTPException(status_code=422, detail={"error": err, "message": "Ready status is derived, not cosmetic."})
    raise HTTPException(
        status_code=422,
        detail={"error": err, "message": result.get("message") or err, **{k: result.get(k) for k in ("readiness", "from", "to") if k in result}},
    )


def register_preboarding_http(app_mod: Any) -> None:
    """Attach dashboard / mobile / employee / assistant preboarding routes."""
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    employee_app_context = app_mod.employee_app_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    _posthire_read_context = app_mod._posthire_read_context
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key
    find_employee_by_key = app_mod.find_employee_by_key
    context_manager_allows_employee = app_mod.context_manager_allows_employee
    require_employee_app_feature = app_mod.require_employee_app_feature

    import preboarding as pb
    import preboarding_surfaces as surfaces

    def _actor_role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or "").strip().lower()
        if role in {"manager", "hr", "admin", "owner", "employee"}:
            return role
        perms = context_permissions(context, dashboard_context_role_key(context))
        if "preboarding.manage" in perms or "preboarding.waive_item" in perms:
            return "hr"
        if str(context.get("scope") or "").lower() == "manager":
            return "manager"
        return role or "hr"

    def _hub(employee_key: str, company: str) -> dict[str, Any] | None:
        return find_employee_by_key(employee_key, company_code=company)

    @app.get("/dashboard/posthire/preboarding")
    def dashboard_posthire_preboarding(
        offset: int = 0,
        limit: int = 100,
        search: str = "",
        status: str = "",
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        role = _actor_role(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                payload = surfaces.queue_payload(
                    cur,
                    company_code=company,
                    status=status or None,
                    search=search or None,
                    manager_scope_only=role == "manager",
                    actor_user_id=context.get("actor_user_id"),
                    limit=limit,
                    offset=offset,
                    hub_lookup=_hub,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        payload["permissions"] = {
            "manage": "preboarding.manage" in context_permissions(context, dashboard_context_role_key(context))
            or role in {"hr", "admin", "owner"},
            "waive_item": "preboarding.waive_item" in context_permissions(context, dashboard_context_role_key(context))
            or role in {"hr", "admin", "owner"},
            "configure": role in {"hr", "admin", "owner"},
        }
        return json_safe(payload)

    @app.get("/dashboard/posthire/preboarding/{assignment_id}")
    def dashboard_posthire_preboarding_detail(
        assignment_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        role = _actor_role(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                asn = pb.get_assignment(cur, company_code=company, assignment_id=assignment_id)
                if not asn:
                    raise HTTPException(status_code=404, detail={"error": "assignment_not_found"})
                emp = _hub(asn["employee_key"], company)
                if emp and not context_manager_allows_employee(context, emp, company_code=company):
                    raise HTTPException(status_code=404, detail={"error": "assignment_not_found"})
                payload = surfaces.detail_payload(
                    cur,
                    company_code=company,
                    assignment_id=assignment_id,
                    actor_user_id=context.get("actor_user_id"),
                    actor_role=role,
                    hub_employee=emp,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        return json_safe(payload)

    @app.get("/dashboard/posthire/preboarding-config")
    def dashboard_posthire_preboarding_config(context: dict[str, Any] = Depends(dashboard_context)):
        company = _posthire_read_context(context, "preboarding")
        role = _actor_role(context)
        if role not in {"hr", "admin", "owner"}:
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                payload = surfaces.template_config_payload(cur, company_code=company)
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        return json_safe(payload)

    @app.post("/dashboard/posthire/preboarding")
    def dashboard_posthire_preboarding_create(
        body: PreboardCreateBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        if _actor_role(context) == "manager":
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        emp = _hub(body.employee_key, company)
        if not emp:
            raise HTTPException(status_code=404, detail={"error": "employee_not_found"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                result = pb.create_assignment(
                    cur,
                    company_code=company,
                    employee_key=body.employee_key,
                    joining_date=_parse_date(body.joining_date),
                    manager_user_id=body.manager_user_id,
                    application_id=body.application_id,
                    offer_id=body.offer_id,
                    created_by_user_id=context.get("actor_user_id"),
                    created_by_phone=context.get("hr_phone") or context.get("actor_phone"),
                    idempotency_key=body.idempotency_key,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/preboarding/{assignment_id}/items/{item_key}")
    def dashboard_preboarding_update_item(
        assignment_id: str,
        item_key: str,
        body: PreboardItemUpdateBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                result = pb.update_item_status(
                    cur,
                    company_code=company,
                    assignment_id=assignment_id,
                    item_key=item_key,
                    to_status=body.to_status,
                    actor_user_id=context.get("actor_user_id"),
                    actor_role=_actor_role(context),
                    blocker_reason=body.blocker_reason,
                    evidence_document_id=body.evidence_document_id,
                    expected_row_version=body.expected_row_version,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/preboarding/{assignment_id}/items/{item_key}/waive")
    def dashboard_preboarding_waive_item(
        assignment_id: str,
        item_key: str,
        body: PreboardWaiveBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                result = pb.waive_item(
                    cur,
                    company_code=company,
                    assignment_id=assignment_id,
                    item_key=item_key,
                    actor_user_id=str(context.get("actor_user_id") or ""),
                    actor_role=_actor_role(context),
                    waive_reason=body.waive_reason,
                    expected_row_version=body.expected_row_version,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/preboarding/{assignment_id}/joining-date")
    def dashboard_preboarding_joining_date(
        assignment_id: str,
        body: PreboardJoiningDateBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        if _actor_role(context) == "manager":
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                result = pb.set_joining_date(
                    cur,
                    company_code=company,
                    assignment_id=assignment_id,
                    joining_date=_parse_date(body.joining_date),  # type: ignore[arg-type]
                    actor_user_id=context.get("actor_user_id"),
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/preboarding/{assignment_id}/start")
    def dashboard_preboarding_start(
        assignment_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                result = pb.transition_assignment(
                    cur,
                    company_code=company,
                    assignment_id=assignment_id,
                    to_status="in_progress",
                    actor_user_id=context.get("actor_user_id"),
                    actor_role=_actor_role(context),
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/preboarding/{assignment_id}/cancel")
    def dashboard_preboarding_cancel(
        assignment_id: str,
        body: PreboardCancelBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        if _actor_role(context) == "manager":
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                result = pb.transition_assignment(
                    cur,
                    company_code=company,
                    assignment_id=assignment_id,
                    to_status="cancelled",
                    actor_user_id=context.get("actor_user_id"),
                    actor_role=_actor_role(context),
                    cancel_reason=body.cancel_reason,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/preboarding/{assignment_id}/remind")
    def dashboard_preboarding_remind(
        assignment_id: str,
        body: PreboardRemindBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                asn = pb.get_assignment(cur, company_code=company, assignment_id=assignment_id)
                if not asn:
                    raise HTTPException(status_code=404, detail={"error": "assignment_not_found"})
                item = None
                if body.item_key:
                    items = pb.list_items(cur, company_code=company, assignment_id=assignment_id)
                    item = next((i for i in items if i["item_key"] == body.item_key), None)
                payload = surfaces.remind_payload(assignment=asn, item=item, locale=body.locale)
                pb._insert_event(
                    cur,
                    company_code=company,
                    event_type="task_synced",
                    assignment_id=assignment_id,
                    actor_user_id=context.get("actor_user_id"),
                    payload={"remind": True, "item_key": body.item_key},
                )
            conn.commit()
        return json_safe(payload)

    @app.patch("/dashboard/posthire/preboarding-settings")
    def dashboard_preboarding_settings(
        body: PreboardSettingsBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        if _actor_role(context) not in {"hr", "admin", "owner"}:
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                settings = pb.set_settings(
                    cur,
                    company,
                    enabled=body.enabled,
                    auto_create_on_offer_accept=body.auto_create_on_offer_accept,
                    required_for_ready_mark=body.required_for_ready_mark,
                    handoff_onboarding_enabled=body.handoff_onboarding_enabled,
                )
            conn.commit()
        return json_safe({"ok": True, "settings": settings})

    # --- HR Mobile --------------------------------------------------------------
    @app.get("/dashboard/mobile/preboarding")
    def mobile_preboarding(
        offset: int = 0,
        limit: int = 50,
        view: str = "attention",
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        role = _actor_role(context)
        status = None
        if view == "ready":
            status = "ready"
        elif view == "blocked":
            status = "blocked"
        elif view == "joining_soon":
            status = None
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                payload = surfaces.queue_payload(
                    cur,
                    company_code=company,
                    status=status,
                    manager_scope_only=role == "manager",
                    actor_user_id=context.get("actor_user_id"),
                    limit=limit,
                    offset=offset,
                    hub_lookup=_hub,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        # Needs Attention = blocked + overdue required
        if view == "attention":
            payload["assignments"] = [
                a
                for a in payload.get("assignments") or []
                if a.get("status") == "blocked"
                or (a.get("items_summary") or {}).get("overdue", 0) > 0
                or (a.get("items_summary") or {}).get("required_open", 0) > 0
            ]
        elif view == "joining_soon":
            payload["assignments"] = sorted(
                payload.get("assignments") or [],
                key=lambda a: str(a.get("joining_date") or "9999"),
            )
        payload["view"] = view
        return json_safe(payload)

    @app.get("/dashboard/mobile/preboarding/{assignment_id}")
    def mobile_preboarding_detail(
        assignment_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_posthire_preboarding_detail(assignment_id, context)

    @app.post("/dashboard/mobile/preboarding/{assignment_id}/items/{item_key}/waive")
    def mobile_preboarding_waive(
        assignment_id: str,
        item_key: str,
        body: PreboardWaiveBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_preboarding_waive_item(assignment_id, item_key, body, context)

    @app.post("/dashboard/mobile/preboarding/{assignment_id}/items/{item_key}")
    def mobile_preboarding_update_item(
        assignment_id: str,
        item_key: str,
        body: PreboardItemUpdateBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_preboarding_update_item(assignment_id, item_key, body, context)

    # --- Employee App -----------------------------------------------------------
    @app.get("/app/preboarding")
    def app_preboarding(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "preboarding")
        company = context["company_code"]
        key = context["employee_key"]
        employee = context["employee"]
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                payload = surfaces.employee_self_payload(
                    cur,
                    company_code=company,
                    employee_key=key,
                    hub_employee=employee,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        return json_safe(payload)

    @app.post("/app/preboarding/items/{item_key}")
    def app_preboarding_update_item(
        item_key: str,
        body: PreboardItemUpdateBody,
        context: dict[str, Any] = Depends(employee_app_context),
    ):
        require_employee_app_feature(context, "preboarding", action="complete_item")
        company = context["company_code"]
        key = context["employee_key"]
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                asn = pb.get_open_assignment_for_employee(
                    cur, company_code=company, employee_key=key
                )
                if not asn:
                    raise HTTPException(status_code=404, detail={"error": "assignment_not_found"})
                items = pb.list_items(cur, company_code=company, assignment_id=asn["assignment_id"])
                target = next((i for i in items if i["item_key"] == item_key), None)
                if not target or target.get("owner_role") != "employee":
                    raise HTTPException(status_code=403, detail={"error": "not_employee_owned"})
                if body.to_status not in {"in_progress", "done"}:
                    raise HTTPException(status_code=422, detail={"error": "status_invalid"})
                result = pb.update_item_status(
                    cur,
                    company_code=company,
                    assignment_id=asn["assignment_id"],
                    item_key=item_key,
                    to_status=body.to_status,
                    actor_user_id=context.get("actor_user_id"),
                    actor_role="employee",
                    evidence_document_id=body.evidence_document_id,
                    expected_row_version=body.expected_row_version,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    # --- Assistant read ---------------------------------------------------------
    @app.get("/dashboard/assistant/preboarding/{assignment_id}")
    def assistant_preboarding_explain(
        assignment_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "preboarding")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pb.ensure_preboarding_schema(cur)
                asn = pb.get_assignment(cur, company_code=company, assignment_id=assignment_id)
                if not asn:
                    raise HTTPException(status_code=404, detail={"error": "assignment_not_found"})
                items = pb.list_items(cur, company_code=company, assignment_id=assignment_id)
                explained = surfaces.explain_blockers(asn, items)
            conn.commit()
        return json_safe({"ok": True, "assignment_id": assignment_id, **explained})
