"""HTTP route registration for Probation surfaces (thin wrappers over frozen authority)."""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


class ProbationCreateBody(BaseModel):
    employee_key: str
    probation_start: str | None = None
    probation_days: int | None = None
    manager_user_id: str | None = None
    idempotency_key: str | None = None


class ProbationTransitionBody(BaseModel):
    to_status: str
    decision_reason: str | None = None
    expected_row_version: int | None = None


class ProbationExtendBody(BaseModel):
    extend_days: int = Field(gt=0, le=365)
    decision_reason: str | None = None
    expected_row_version: int | None = None


class ProbationMilestoneBody(BaseModel):
    to_status: str
    notes: str | None = None
    expected_row_version: int | None = None


class ProbationRecommendBody(BaseModel):
    recommendation: str  # confirm | extend | fail
    notes: str | None = None
    extend_days: int | None = None


class ProbationRemindBody(BaseModel):
    milestone_key: str | None = None
    locale: str = "en"


class ProbationSettingsBody(BaseModel):
    enabled: bool | None = None
    auto_plan_on_hire: bool | None = None
    start_mode: str | None = None
    default_probation_days: int | None = None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "probation_denied")
    if err in {"probation_disabled", "probation_company_not_allowlisted", "probation_company_disabled"}:
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "Probation is not enabled for this company.",
                "gate": result.get("gate"),
            },
        )
    if err in {"case_not_found", "milestone_not_found", "employee_not_found"}:
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in {"manager_scope_denied", "permission_denied", "scope_denied"}:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted."})
    if err == "concurrency_conflict":
        raise HTTPException(status_code=409, detail={"error": err, "message": "Stale row — refresh and retry."})
    if err == "decision_reason_required":
        raise HTTPException(status_code=422, detail={"error": err, "message": "Decision reason is required."})
    raise HTTPException(
        status_code=422,
        detail={
            "error": err,
            "message": result.get("message") or err,
            **{k: result.get(k) for k in ("from", "to", "status") if k in result},
        },
    )


def register_probation_http(app_mod: Any) -> None:
    """Attach dashboard / mobile / employee / assistant probation routes."""
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

    import probation as pr
    import probation_surfaces as surfaces

    def _actor_role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or "").strip().lower()
        if role in {"manager", "hr", "admin", "owner", "employee"}:
            return role
        perms = context_permissions(context, dashboard_context_role_key(context))
        if "probation.decide" in perms or "probation.manage" in perms:
            return "hr"
        if str(context.get("scope") or "").lower() == "manager":
            return "manager"
        return role or "hr"

    def _hub(employee_key: str, company: str) -> dict[str, Any] | None:
        return find_employee_by_key(employee_key, company_code=company)

    def _perms(context: dict[str, Any], role: str) -> dict[str, bool]:
        perms = context_permissions(context, dashboard_context_role_key(context))
        return {
            "manage": "probation.manage" in perms or role in {"hr", "admin", "owner", "manager"},
            "decide": "probation.decide" in perms or role in {"hr", "admin", "owner"},
            "recommend": "probation.manage" in perms or role in {"hr", "admin", "owner", "manager"},
            "configure": role in {"hr", "admin", "owner"},
        }

    # --- HR Web -----------------------------------------------------------------
    @app.get("/dashboard/posthire/probation")
    def dashboard_posthire_probation(
        offset: int = 0,
        limit: int = 100,
        search: str = "",
        status: str = "",
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        role = _actor_role(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
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
        payload["permissions"] = _perms(context, role)
        return json_safe(payload)

    @app.get("/dashboard/posthire/probation/{case_id}")
    def dashboard_posthire_probation_detail(
        case_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        role = _actor_role(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                case = pr.get_case(cur, company_code=company, case_id=case_id)
                if not case:
                    raise HTTPException(status_code=404, detail={"error": "case_not_found"})
                emp = _hub(case["employee_key"], company)
                if emp and not context_manager_allows_employee(context, emp, company_code=company):
                    raise HTTPException(status_code=404, detail={"error": "case_not_found"})
                payload = surfaces.detail_payload(
                    cur,
                    company_code=company,
                    case_id=case_id,
                    actor_user_id=context.get("actor_user_id"),
                    actor_role=role,
                    hub_employee=emp,
                    include_confidential=role != "employee",
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        payload["permissions"] = {**(payload.get("permissions") or {}), **_perms(context, role)}
        return json_safe(payload)

    @app.post("/dashboard/posthire/probation")
    def dashboard_posthire_probation_create(
        body: ProbationCreateBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        if _actor_role(context) == "manager":
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        emp = _hub(body.employee_key, company)
        if not emp:
            raise HTTPException(status_code=404, detail={"error": "employee_not_found"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                result = pr.create_case(
                    cur,
                    company_code=company,
                    employee_key=body.employee_key,
                    probation_start=_parse_date(body.probation_start),
                    probation_days=body.probation_days,
                    manager_user_id=body.manager_user_id,
                    actor_user_id=context.get("actor_user_id"),
                    idempotency_key=body.idempotency_key,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/probation/{case_id}/transition")
    def dashboard_posthire_probation_transition(
        case_id: str,
        body: ProbationTransitionBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        role = _actor_role(context)
        perms = _perms(context, role)
        dst = str(body.to_status or "").strip().lower()
        if dst in {"confirmed", "failed"} and not perms.get("decide"):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "probation.decide required"})
        if role == "manager" and dst in {"confirmed", "failed", "extended"}:
            # Managers recommend; they do not finalize unless decide permission granted.
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "manager_cannot_finalize",
                    "message": "Managers submit recommendations; HR decides.",
                },
            )
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                result = pr.transition_case(
                    cur,
                    company_code=company,
                    case_id=case_id,
                    to_status=dst,
                    actor_user_id=context.get("actor_user_id"),
                    decision_reason=body.decision_reason,
                    expected_row_version=body.expected_row_version,
                )
                if result.get("ok") and dst == "under_review":
                    try:
                        import wave1_task_sync as _w1t

                        _w1t.on_probation_decision_required(
                            cur,
                            company_code=company,
                            case=result.get("case") or {},
                            actor_user_id=context.get("actor_user_id"),
                        )
                    except Exception:
                        pass
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/probation/{case_id}/extend")
    def dashboard_posthire_probation_extend(
        case_id: str,
        body: ProbationExtendBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        role = _actor_role(context)
        if not _perms(context, role).get("decide"):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        if role == "manager":
            raise HTTPException(status_code=403, detail={"error": "manager_cannot_finalize"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                result = pr.extend_case(
                    cur,
                    company_code=company,
                    case_id=case_id,
                    extend_days=body.extend_days,
                    actor_user_id=context.get("actor_user_id"),
                    decision_reason=body.decision_reason,
                    expected_row_version=body.expected_row_version,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/probation/{case_id}/milestones/{milestone_key}")
    def dashboard_posthire_probation_milestone(
        case_id: str,
        milestone_key: str,
        body: ProbationMilestoneBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        role = _actor_role(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                case = pr.get_case(cur, company_code=company, case_id=case_id)
                if not case:
                    raise HTTPException(status_code=404, detail={"error": "case_not_found"})
                scope = surfaces.assert_manager_scope(
                    case=case, actor_user_id=context.get("actor_user_id"), actor_role=role
                )
                if not scope.get("ok"):
                    _raise_gate(scope)
                result = pr.update_milestone(
                    cur,
                    company_code=company,
                    case_id=case_id,
                    milestone_key=milestone_key,
                    to_status=body.to_status,
                    actor_user_id=context.get("actor_user_id"),
                    notes=body.notes,
                    expected_row_version=body.expected_row_version,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    @app.post("/dashboard/posthire/probation/{case_id}/recommend")
    def dashboard_posthire_probation_recommend(
        case_id: str,
        body: ProbationRecommendBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        """Manager/HR recommendation — recorded in audit; not final unless decide path used."""
        company = _posthire_read_context(context, "probation")
        role = _actor_role(context)
        if not _perms(context, role).get("recommend"):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        rec = str(body.recommendation or "").strip().lower()
        if rec not in {"confirm", "extend", "fail"}:
            raise HTTPException(status_code=422, detail={"error": "recommendation_invalid"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                case = pr.get_case(cur, company_code=company, case_id=case_id)
                if not case:
                    raise HTTPException(status_code=404, detail={"error": "case_not_found"})
                scope = surfaces.assert_manager_scope(
                    case=case, actor_user_id=context.get("actor_user_id"), actor_role=role
                )
                if not scope.get("ok"):
                    _raise_gate(scope)
                # Move to under_review if still active so HR sees the decision queue.
                if case.get("status") == "active":
                    pr.transition_case(
                        cur,
                        company_code=company,
                        case_id=case_id,
                        to_status="under_review",
                        actor_user_id=context.get("actor_user_id"),
                        decision_reason=f"manager_recommendation:{rec}",
                    )
                pr._insert_event(
                    cur,
                    company_code=company,
                    event_type="manager_recommendation",
                    case_id=case_id,
                    actor_user_id=context.get("actor_user_id"),
                    payload={
                        "recommendation": rec,
                        "notes": body.notes,
                        "extend_days": body.extend_days,
                        "is_final": False,
                        "actor_role": role,
                    },
                )
                updated = pr.get_case(cur, company_code=company, case_id=case_id)
            conn.commit()
        return json_safe(
            {
                "ok": True,
                "recommendation": rec,
                "is_final": False,
                "case": updated,
                "message": "Recommendation recorded; HR decision still required.",
            }
        )

    @app.post("/dashboard/posthire/probation/{case_id}/remind")
    def dashboard_posthire_probation_remind(
        case_id: str,
        body: ProbationRemindBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                case = pr.get_case(cur, company_code=company, case_id=case_id)
                if not case:
                    raise HTTPException(status_code=404, detail={"error": "case_not_found"})
                ms = None
                if body.milestone_key:
                    items = pr.list_milestones(cur, company_code=company, case_id=case_id)
                    ms = next((m for m in items if m["milestone_key"] == body.milestone_key), None)
                payload = surfaces.remind_payload(case=case, milestone=ms, locale=body.locale)
                pr._insert_event(
                    cur,
                    company_code=company,
                    event_type="remind_sent",
                    case_id=case_id,
                    actor_user_id=context.get("actor_user_id"),
                    payload={"milestone_key": body.milestone_key},
                )
                try:
                    import wave1_task_sync as _w1t

                    if ms:
                        task = _w1t.on_probation_milestone_due(
                            cur,
                            company_code=company,
                            case=case,
                            milestone=ms,
                            actor_user_id=context.get("actor_user_id"),
                        )
                    else:
                        task = _w1t.on_probation_decision_required(
                            cur,
                            company_code=company,
                            case=case,
                            actor_user_id=context.get("actor_user_id"),
                        )
                    payload["canonical_task"] = task
                except Exception:
                    pass
            conn.commit()
        return json_safe(payload)

    @app.patch("/dashboard/posthire/probation-settings")
    def dashboard_probation_settings(
        body: ProbationSettingsBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        if _actor_role(context) not in {"hr", "admin", "owner"}:
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                settings = pr.set_settings(
                    cur,
                    company,
                    enabled=body.enabled,
                    auto_plan_on_hire=body.auto_plan_on_hire,
                    start_mode=body.start_mode,
                    default_probation_days=body.default_probation_days,
                )
            conn.commit()
        return json_safe({"ok": True, "settings": settings})

    # --- HR Mobile --------------------------------------------------------------
    @app.get("/dashboard/mobile/probation")
    def mobile_probation(
        view: str = "attention",
        limit: int = 50,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        role = _actor_role(context)
        status_map = {
            "attention": "attention",
            "reviews_due": "under_review",
            "active": "active",
            "extended": "extended",
            "upcoming": "active",
        }
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                payload = surfaces.queue_payload(
                    cur,
                    company_code=company,
                    status=status_map.get(view, "attention"),
                    manager_scope_only=role == "manager",
                    actor_user_id=context.get("actor_user_id"),
                    limit=limit,
                    hub_lookup=_hub,
                )
            conn.commit()
        if not payload.get("ok"):
            _raise_gate(payload)
        cases = payload.get("cases") or []
        if view == "upcoming":
            cases = sorted(
                [c for c in cases if c.get("next_milestone")],
                key=lambda c: str((c.get("next_milestone") or {}).get("due_on") or "9999"),
            )
        elif view == "attention":
            cases = [c for c in cases if c.get("needs_attention")]
        payload["cases"] = cases
        payload["view"] = view
        payload["permissions"] = _perms(context, role)
        return json_safe(payload)

    @app.get("/dashboard/mobile/probation/{case_id}")
    def mobile_probation_detail(case_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        return dashboard_posthire_probation_detail(case_id, context)

    @app.post("/dashboard/mobile/probation/{case_id}/milestones/{milestone_key}")
    def mobile_probation_milestone(
        case_id: str,
        milestone_key: str,
        body: ProbationMilestoneBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_posthire_probation_milestone(case_id, milestone_key, body, context)

    @app.post("/dashboard/mobile/probation/{case_id}/recommend")
    def mobile_probation_recommend(
        case_id: str,
        body: ProbationRecommendBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_posthire_probation_recommend(case_id, body, context)

    @app.post("/dashboard/mobile/probation/{case_id}/transition")
    def mobile_probation_transition(
        case_id: str,
        body: ProbationTransitionBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        # Governed mobile finalize only when decide permission present
        return dashboard_posthire_probation_transition(case_id, body, context)

    @app.post("/dashboard/mobile/probation/{case_id}/extend")
    def mobile_probation_extend(
        case_id: str,
        body: ProbationExtendBody,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_posthire_probation_extend(case_id, body, context)

    # --- Employee App -----------------------------------------------------------
    @app.get("/app/probation")
    def app_probation(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "probation", "view")
        company = str(context.get("company_code") or "").upper()
        employee_key = str(context.get("employee_key") or "")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                emp = _hub(employee_key, company)
                payload = surfaces.employee_self_payload(
                    cur,
                    company_code=company,
                    employee_key=employee_key,
                    hub_employee=emp,
                )
            conn.commit()
        if not payload.get("ok") and payload.get("error"):
            _raise_gate(payload)
        return json_safe(payload)

    @app.post("/app/probation/milestones/{milestone_key}")
    def app_probation_milestone(
        milestone_key: str,
        body: ProbationMilestoneBody,
        context: dict[str, Any] = Depends(employee_app_context),
    ):
        require_employee_app_feature(context, "probation", "complete_item")
        company = str(context.get("company_code") or "").upper()
        employee_key = str(context.get("employee_key") or "")
        # Employees may only complete/skip their own reflection-style milestones
        if body.to_status not in {"completed", "skipped"}:
            raise HTTPException(status_code=422, detail={"error": "employee_status_invalid"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                case = surfaces.get_open_case_for_employee(
                    cur, company_code=company, employee_key=employee_key
                )
                if not case or case.get("status") in pr.TERMINAL_CASE:
                    raise HTTPException(status_code=404, detail={"error": "case_not_found"})
                result = pr.update_milestone(
                    cur,
                    company_code=company,
                    case_id=case["case_id"],
                    milestone_key=milestone_key,
                    to_status=body.to_status,
                    actor_user_id=context.get("actor_user_id") or employee_key,
                    notes=body.notes,
                    expected_row_version=body.expected_row_version,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_gate(result)
        return json_safe(result)

    # --- Assistant --------------------------------------------------------------
    @app.get("/dashboard/assistant/probation/{case_id}")
    def assistant_probation_explain(
        case_id: str,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _posthire_read_context(context, "probation")
        with db_connect() as conn:
            with conn.cursor() as cur:
                pr.ensure_probation_schema(cur)
                case = pr.get_case(cur, company_code=company, case_id=case_id)
                if not case:
                    raise HTTPException(status_code=404, detail={"error": "case_not_found"})
                ms = pr.list_milestones(cur, company_code=company, case_id=case_id)
                explained = surfaces.explain_status(case, ms)
            conn.commit()
        return json_safe({"ok": True, "case_id": case_id, **explained})
