#!/usr/bin/env python3
"""HTTP adapters for Performance (R5B) — thin wrappers over frozen C1–C4.

Namespaces:
  /dashboard/performance/...
  /dashboard/mobile/performance/...
  /app/performance/...

Company and actor identity come from authenticated context only.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import okr_operating_pt1 as pt1
import performance_calibration_c4 as c4
import performance_feedback_c3 as c3
import performance_goals_c1 as c1
import performance_reviews_c2 as c2
import performance_surfaces as surfaces


class MeasureBody(BaseModel):
    name_en: str
    unit: str
    direction: str
    name_ar: str | None = None
    source: str = "manual"
    baseline: Any = None
    target: Any = None
    range_low: Any = None
    range_high: Any = None
    period_start: str | None = None
    period_end: str | None = None
    owner_employee_key: str | None = None
    reason: str = "create measure"


class ObjectiveBody(BaseModel):
    title_en: str
    scope: str = "individual"
    title_ar: str | None = None
    owner_employee_key: str | None = None
    org_unit_id: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    weight: Any = None
    cycle_id: str | None = None
    visibility: str | None = None
    reason: str = "create objective"


class OkrCycleBody(BaseModel):
    name_en: str
    period_start: str
    period_end: str
    name_ar: str | None = None
    scope: str = "company"
    org_unit_id: str | None = None
    visibility_policy: str | None = None
    reason: str = "create okr cycle"


class OkrAlignBody(BaseModel):
    child_objective_id: str
    parent_objective_id: str
    link_kind: str = "contributes_to"
    reason: str = "align"


class OkrUpdateBody(BaseModel):
    subject_type: str = "objective"
    subject_id: str | None = None
    update_text: str
    observed_value: Any = None
    confidence: str | None = None
    cycle_id: str | None = None
    reason: str = "okr update"


class KeyResultBody(BaseModel):
    title_en: str
    measure_id: str
    title_ar: str | None = None
    weight: Any = 1
    reason: str = "add key result"


class ProgressBody(BaseModel):
    subject_type: str
    subject_id: str
    current_value: Any
    source: str = "manual"
    note: str | None = None
    progress_pct: Any = None


class CycleBody(BaseModel):
    name_en: str
    period_start: str
    period_end: str
    template_id: str
    scale_id: str
    name_ar: str | None = None
    framework_id: str | None = None
    goals_integration: bool | None = None
    competencies_enabled: bool | None = None
    review_360_enabled: bool | None = None
    anonymity_enabled: bool | None = None
    min_respondent_threshold: int | None = None
    due_self: str | None = None
    due_manager: str | None = None
    due_360: str | None = None
    reason: str = "create cycle"


class ConfigureCycleBody(BaseModel):
    participants: list[dict[str, Any]]
    peer_assignments: list[dict[str, Any]] | None = None
    reason: str = "configure cycle"


class ReasonBody(BaseModel):
    reason: str = "performance action"
    expected_row_version: int | None = None


class ReviewSubmitBody(BaseModel):
    overall_rating_value: Any
    rationale: str
    components: list[dict[str, Any]] | None = None
    competency_ratings: list[dict[str, Any]] | None = None
    confidential_comment: str | None = None
    overall_rating_label: str | None = None
    expected_version: int | None = None
    cycle_id: str | None = None
    assignment_id: str | None = None


class ScaleBody(BaseModel):
    name_en: str
    points: list[dict[str, Any]]
    scale_type: str = "numeric"
    name_ar: str | None = None
    reason: str = "create scale"


class TemplateBody(BaseModel):
    name_en: str
    name_ar: str | None = None
    sections: list[dict[str, Any]] | None = None
    include_goals: bool = True
    include_competencies: bool = False
    reason: str = "create template"


class CheckInBody(BaseModel):
    employee_key: str
    kind: str = "ad_hoc"
    manager_employee_key: str | None = None
    scheduled_for: str | None = None
    notes_shared: str | None = None
    talking_points: list[Any] | None = None
    reason: str = "create check-in"


class DevelopmentPlanBody(BaseModel):
    employee_key: str
    title_en: str
    title_ar: str | None = None
    reason: str = "create development plan"


class DevelopmentActionBody(BaseModel):
    plan_id: str
    title_en: str
    title_ar: str | None = None
    description_en: str | None = None
    due_date: str | None = None
    owner_employee_key: str | None = None
    reason: str = "create development action"


class AdvanceActionBody(BaseModel):
    to_status: str
    expected_row_version: int = 1
    reason: str = "advance development action"


class CalibrationBody(BaseModel):
    cycle_id: str
    name_en: str
    name_ar: str | None = None
    reason: str = "create calibration session"


class CalibrationAdjustBody(BaseModel):
    subject_employee_key: str
    new_value: Any
    expected_row_version: int = 1
    new_label: str | None = None
    reason: str = "apply calibration adjustment"


_GATE_ERRORS = {
    "performance_kill_switch",
    "performance_goals_c1_off",
    "performance_reviews_c2_off",
    "performance_feedback_c3_off",
    "performance_calibration_c4_off",
    "performance_goals_company_not_allowlisted",
    "performance_reviews_company_not_allowlisted",
    "performance_feedback_company_not_allowlisted",
    "performance_calibration_company_not_allowlisted",
    "performance_goals_entitlement_off",
    "performance_reviews_entitlement_off",
    "performance_feedback_entitlement_off",
    "company_disabled",
    "entitlement_off",
}

_NOT_FOUND = {
    "objective_not_found",
    "key_result_not_found",
    "goal_not_found",
    "measure_not_found",
    "cycle_not_found",
    "review_not_found",
    "assignment_not_found",
    "check_in_not_found",
    "development_plan_not_found",
    "calibration_session_not_found",
}

_FORBIDDEN = {
    "permission_denied",
    "manager_scope_denied",
    "scope_denied",
    "calibration_forbidden",
    "sensitive_360_permission_required",
    "reviewer_assignment_mismatch",
    "self_review_forbidden",
    "progress_not_owned",
    "cycle_admin_required",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "performance_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "Performance is not enabled for this company.",
                "gate": result.get("gate"),
            },
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted."})
    if err in {"concurrency_conflict", "stale_row_version"}:
        raise HTTPException(status_code=409, detail={"error": err, "message": "Stale row — refresh and retry."})
    raise HTTPException(
        status_code=422,
        detail={"error": err, "message": result.get("message") or err},
    )


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def register_performance_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    employee_app_context = app_mod.employee_app_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    posthire_context = app_mod._posthire_read_context
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key
    context_manager_employee_keys = getattr(app_mod, "context_manager_employee_keys", None)
    require_employee_app_feature = app_mod.require_employee_app_feature
    deliver_employee_notification = getattr(app_mod, "deliver_employee_notification", None)
    find_employee_by_key = getattr(app_mod, "find_employee_by_key", None)
    require_entitlement = getattr(app_mod, "require_entitlement", None)

    def _perms(context: dict[str, Any]) -> set[str]:
        return set(context_permissions(context, dashboard_context_role_key(context)) or [])

    def _role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or dashboard_context_role_key(context) or "").strip().lower()
        if role in {"owner", "hr_admin", "hr_manager", "admin"}:
            return "hr"
        if role in {"manager"}:
            return "manager"
        perms = _perms(context)
        if "performance.calibrate" in perms or "performance.manage" in perms:
            return "hr"
        if str(context.get("scope") or "").lower() == "manager" or "performance.read" in perms:
            if "performance.manage" not in perms and role == "manager":
                return "manager"
        return role or "hr"

    def _actor_phone(context: dict[str, Any]) -> str:
        return str(context.get("actor_phone") or context.get("hr_phone") or context.get("phone") or "")

    def _manager_keys(context: dict[str, Any], company: str) -> list[str] | None:
        if _role(context) != "manager":
            return None
        if not context_manager_employee_keys:
            return []
        keys = context_manager_employee_keys(context, company) or set()
        return sorted(str(item) for item in keys)

    def _company(context: dict[str, Any], *, write: bool = False) -> str:
        company = posthire_context(context, "performance")
        perms = _perms(context)
        if write and "performance.manage" not in perms and _role(context) not in {"hr", "admin", "owner"}:
            if "performance.manage" not in perms:
                raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})
        gate = c1.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _require_cycle_admin(context: dict[str, Any]) -> str:
        if _role(context) != "hr":
            raise HTTPException(status_code=403, detail={"error": "cycle_admin_required", "message": "Not permitted."})
        return _company(context, write=True)

    def _assert_manager_scope(context: dict[str, Any], company: str, employee_key: str | None) -> None:
        keys = _manager_keys(context, company)
        if keys is None:
            return
        if not employee_key or employee_key not in keys:
            raise HTTPException(status_code=403, detail={"error": "scope_denied", "message": "Not permitted."})

    def _notify(company: str, employee_key: str, *, template_key: str, text: str, subject: str) -> None:
        if not deliver_employee_notification or not find_employee_by_key:
            return
        employee = find_employee_by_key(employee_key, company_code=company)
        if not employee:
            return
        try:
            deliver_employee_notification(
                employee,
                flow="performance",
                template_key=template_key,
                text=text,
                email_subject=subject,
                company_code=company,
                dedupe_key=f"performance:{template_key}:{company}:{employee_key}",
            )
        except Exception:
            return

    def _run(callback: Any) -> Any:
        with db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.ensure_all_schemas(cur)
                result = callback(cur)
            conn.commit()
        if isinstance(result, dict) and result.get("ok") is False:
            _raise_gate(result)
        return json_safe(surfaces.strip_talent(result))

    # --- HR / Manager workspace -------------------------------------------------
    @app.get("/dashboard/performance/workspace")
    def dashboard_performance_workspace(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        role = _role(context)
        return _run(
            lambda cur: surfaces.workspace_summary(
                cur,
                company_code=company,
                actor_role=role,
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    @app.get("/dashboard/performance/objectives")
    def dashboard_performance_objectives(
        owner_employee_key: str = "",
        status: str = "",
        offset: int = 0,
        limit: int = 100,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_objectives(
                cur,
                company_code=company,
                owner_employee_key=owner_employee_key or None,
                manager_scope_keys=_manager_keys(context, company),
                status=status or None,
                offset=offset,
                limit=limit,
            )
        )

    @app.get("/dashboard/performance/measures")
    def dashboard_performance_measures(
        offset: int = 0,
        limit: int = 100,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_measures(cur, company_code=company, offset=offset, limit=limit)
        )

    @app.post("/dashboard/performance/measures")
    def dashboard_performance_create_measure(
        body: MeasureBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: c1.create_measure_definition(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                name_en=body.name_en,
                unit=body.unit,
                direction=body.direction,
                name_ar=body.name_ar,
                source=body.source,
                baseline=body.baseline,
                target=body.target,
                range_low=body.range_low,
                range_high=body.range_high,
                period_start=body.period_start,
                period_end=body.period_end,
                owner_employee_key=body.owner_employee_key,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/objectives")
    def dashboard_performance_create_objective(
        body: ObjectiveBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.owner_employee_key)

        def _create(cur: Any) -> dict[str, Any]:
            if body.cycle_id:
                return pt1.create_objective_in_cycle(
                    cur,
                    company_code=company,
                    actor_phone=_actor_phone(context),
                    cycle_id=body.cycle_id,
                    title_en=body.title_en,
                    scope=body.scope,
                    owner_employee_key=body.owner_employee_key,
                    org_unit_id=body.org_unit_id,
                    title_ar=body.title_ar,
                    visibility=body.visibility,
                    reason=body.reason,
                )
            return c1.create_objective(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                title_en=body.title_en,
                scope=body.scope,
                owner_employee_key=body.owner_employee_key,
                org_unit_id=body.org_unit_id,
                title_ar=body.title_ar,
                period_start=body.period_start,
                period_end=body.period_end,
                weight=body.weight,
                reason=body.reason,
            )

        return _run(_create)

    @app.get("/dashboard/performance/objectives/{objective_id}")
    def dashboard_performance_objective_detail(
        objective_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.get_objective_detail(
                cur,
                company_code=company,
                objective_id=objective_id,
                manager_scope_keys=_manager_keys(context, company),
                actor_role=_role(context),
            )
        )

    @app.post("/dashboard/performance/objectives/{objective_id}/key-results")
    def dashboard_performance_add_kr(
        objective_id: str, body: KeyResultBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: c1.add_key_result(
                cur,
                company_code=company,
                objective_id=objective_id,
                actor_phone=_actor_phone(context),
                title_en=body.title_en,
                measure_id=body.measure_id,
                weight=body.weight,
                title_ar=body.title_ar,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/objectives/{objective_id}/activate")
    def dashboard_performance_activate_objective(
        objective_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: c1.activate_objective(
                cur,
                company_code=company,
                objective_id=objective_id,
                actor_phone=_actor_phone(context),
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/progress")
    def dashboard_performance_progress(
        body: ProgressBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: c1.record_progress(
                cur,
                company_code=company,
                subject_type=body.subject_type,
                subject_id=body.subject_id,
                actor_phone=_actor_phone(context),
                current_value=body.current_value,
                source=body.source,
                note=body.note,
                progress_pct=body.progress_pct,
            )
        )

    @app.get("/dashboard/performance/objectives/{objective_id}/history")
    def dashboard_performance_objective_history(
        objective_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        return _run(
            lambda cur: pt1.objective_operating_history(
                cur, company_code=company, objective_id=objective_id
            )
        )

    @app.get("/dashboard/performance/okr-cycles")
    def dashboard_performance_okr_cycles(
        status: str = "", context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        return _run(
            lambda cur: pt1.list_okr_cycles(cur, company_code=company, status=status or None)
        )

    @app.post("/dashboard/performance/okr-cycles")
    def dashboard_performance_create_okr_cycle(
        body: OkrCycleBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: pt1.create_okr_cycle(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                name_en=body.name_en,
                period_start=body.period_start,
                period_end=body.period_end,
                name_ar=body.name_ar,
                scope=body.scope,
                org_unit_id=body.org_unit_id,
                visibility_policy=body.visibility_policy,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/okr-cycles/{cycle_id}/activate")
    def dashboard_performance_activate_okr_cycle(
        cycle_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: pt1.set_okr_cycle_status(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                actor_phone=_actor_phone(context),
                status="active",
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/okr-cycles/{cycle_id}/close")
    def dashboard_performance_close_okr_cycle(
        cycle_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: pt1.set_okr_cycle_status(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                actor_phone=_actor_phone(context),
                status="closed",
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/okr-cycles/{cycle_id}/alignment")
    def dashboard_performance_okr_alignment(
        cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        return _run(
            lambda cur: pt1.alignment_tree(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    @app.get("/dashboard/performance/okr-cycles/{cycle_id}/objectives")
    def dashboard_performance_okr_cycle_objectives(
        cycle_id: str,
        owner_employee_key: str = "",
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: pt1.list_cycle_objectives(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                owner_employee_key=owner_employee_key or None,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    @app.post("/dashboard/performance/alignment")
    def dashboard_performance_align(
        body: OkrAlignBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: pt1.create_alignment(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                child_objective_id=body.child_objective_id,
                parent_objective_id=body.parent_objective_id,
                link_kind=body.link_kind,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/objectives/{objective_id}/updates")
    def dashboard_performance_okr_update(
        objective_id: str, body: OkrUpdateBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: pt1.record_update(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                subject_type=body.subject_type,
                subject_id=body.subject_id or objective_id,
                update_text=body.update_text,
                observed_value=body.observed_value,
                confidence=body.confidence,
                cycle_id=body.cycle_id,
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/objectives/{objective_id}/updates")
    def dashboard_performance_okr_updates(
        objective_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        return _run(
            lambda cur: pt1.list_updates(
                cur, company_code=company, subject_type="objective", subject_id=objective_id
            )
        )

    @app.get("/dashboard/performance/cycles")
    def dashboard_performance_cycles(
        status: str = "",
        offset: int = 0,
        limit: int = 50,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_cycles(
                cur, company_code=company, status=status or None, offset=offset, limit=limit
            )
        )

    @app.get("/dashboard/performance/scales")
    def dashboard_performance_scales(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_scales(cur, company_code=company))

    @app.post("/dashboard/performance/scales")
    def dashboard_performance_create_scale(
        body: ScaleBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: c2.create_rating_scale(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                name_en=body.name_en,
                points=body.points,
                scale_type=body.scale_type,
                name_ar=body.name_ar,
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/templates")
    def dashboard_performance_templates(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_templates(cur, company_code=company))

    @app.post("/dashboard/performance/templates")
    def dashboard_performance_create_template(
        body: TemplateBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: c2.create_review_template(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                name_en=body.name_en,
                name_ar=body.name_ar,
                sections=body.sections or [],
                include_goals=body.include_goals,
                include_competencies=body.include_competencies,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/cycles")
    def dashboard_performance_create_cycle(
        body: CycleBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: c2.create_cycle(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                name_en=body.name_en,
                period_start=body.period_start,
                period_end=body.period_end,
                template_id=body.template_id,
                scale_id=body.scale_id,
                name_ar=body.name_ar,
                framework_id=body.framework_id,
                goals_integration=body.goals_integration,
                competencies_enabled=body.competencies_enabled,
                review_360_enabled=body.review_360_enabled,
                anonymity_enabled=body.anonymity_enabled,
                min_respondent_threshold=body.min_respondent_threshold,
                due_self=body.due_self,
                due_manager=body.due_manager,
                due_360=body.due_360,
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/cycles/{cycle_id}")
    def dashboard_performance_cycle_detail(
        cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.get_cycle_detail(
                cur, company_code=company, cycle_id=cycle_id, actor_role=_role(context)
            )
        )

    @app.get("/dashboard/performance/cycles/{cycle_id}/snapshot")
    def dashboard_performance_cycle_snapshot(
        cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        if _role(context) != "hr":
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})
        return _run(
            lambda cur: surfaces.get_cycle_detail(
                cur, company_code=company, cycle_id=cycle_id, actor_role="hr", include_snapshot=True
            )
        )

    @app.post("/dashboard/performance/cycles/{cycle_id}/configure")
    def dashboard_performance_configure_cycle(
        cycle_id: str, body: ConfigureCycleBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: c2.configure_cycle(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                actor_phone=_actor_phone(context),
                participants=body.participants,
                peer_assignments=body.peer_assignments,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/cycles/{cycle_id}/launch")
    def dashboard_performance_launch_cycle(
        cycle_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)

        def _do(cur: Any) -> dict[str, Any]:
            result = c2.launch_cycle(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                actor_phone=_actor_phone(context),
                reason=body.reason,
            )
            if result.get("ok"):
                snapshot = (result.get("cycle") or {}).get("snapshot") or {}
                if isinstance(snapshot, str):
                    try:
                        snapshot = json.loads(snapshot)
                    except Exception:
                        snapshot = {}
                for p in snapshot.get("population") or []:
                    emp = str(p.get("employee_key") or "")
                    if emp:
                        _notify(
                            company,
                            emp,
                            template_key="performance_self_review_due",
                            text="Your performance self-review is ready.",
                            subject="Self-review due",
                        )
                for assignment in snapshot.get("reviewer_assignments") or []:
                    role = str(assignment.get("reviewer_role") or "")
                    reviewer = str(assignment.get("reviewer_employee_key") or "")
                    if not reviewer:
                        continue
                    if role == "manager":
                        _notify(
                            company,
                            reviewer,
                            template_key="performance_manager_review_due",
                            text="A manager review is waiting for you.",
                            subject="Manager review due",
                        )
                    elif role in {"peer", "subordinate", "stakeholder"}:
                        _notify(
                            company,
                            reviewer,
                            template_key="performance_feedback_requested",
                            text="You have been asked for performance feedback.",
                            subject="Feedback requested",
                        )
            return result

        return _run(_do)

    @app.post("/dashboard/performance/cycles/{cycle_id}/close")
    def dashboard_performance_close_cycle(
        cycle_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        return _run(
            lambda cur: c2.close_cycle(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                actor_phone=_actor_phone(context),
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/reviews")
    def dashboard_performance_reviews(
        cycle_id: str = "",
        subject_employee_key: str = "",
        reviewer_role: str = "",
        pending_only: bool = False,
        offset: int = 0,
        limit: int = 100,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_reviews(
                cur,
                company_code=company,
                cycle_id=cycle_id or None,
                subject_employee_key=subject_employee_key or None,
                reviewer_role=reviewer_role or None,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
                pending_only=pending_only,
                offset=offset,
                limit=limit,
            )
        )

    @app.get("/dashboard/performance/reviews/{review_id}")
    def dashboard_performance_review_detail(
        review_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        perms = _perms(context)
        return _run(
            lambda cur: surfaces.get_review_detail(
                cur,
                company_code=company,
                review_id=review_id,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
                can_see_sensitive="performance.sensitive" in perms,
            )
        )

    @app.post("/dashboard/performance/reviews/{review_id}/submit")
    def dashboard_performance_submit_review(
        review_id: str, body: ReviewSubmitBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)

        def _do(cur: Any) -> dict[str, Any]:
            cur.execute(
                "SELECT * FROM perf_reviews WHERE company_code=%s AND review_id=%s",
                (company, review_id),
            )
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "review_not_found"}
            review = dict(row)
            return c2.submit_review(
                cur,
                company_code=company,
                cycle_id=str(body.cycle_id or review["cycle_id"]),
                assignment_id=str(body.assignment_id or review["assignment_id"]),
                actor_phone=_actor_phone(context),
                overall_rating_value=body.overall_rating_value,
                rationale=body.rationale,
                components=body.components,
                competency_ratings=body.competency_ratings,
                confidential_comment=body.confidential_comment,
                overall_rating_label=body.overall_rating_label,
                expected_version=body.expected_version,
            )

        return _run(_do)

    @app.get("/dashboard/performance/360")
    def dashboard_performance_360(
        cycle_id: str,
        subject_employee_key: str,
        raw: bool = False,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        perms = _perms(context)

        def _do(cur: Any) -> dict[str, Any]:
            if raw:
                return c2.get_raw_360_responses(
                    cur,
                    company_code=company,
                    cycle_id=cycle_id,
                    subject_employee_key=subject_employee_key,
                    actor_phone=_actor_phone(context),
                    has_sensitive_hr_permission="performance.sensitive" in perms,
                )
            return c2.get_360_aggregate(
                cur,
                company_code=company,
                cycle_id=cycle_id,
                subject_employee_key=subject_employee_key,
                actor_role=_role(context),
            )

        return _run(_do)

    @app.get("/dashboard/performance/competencies")
    def dashboard_performance_competencies(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_competencies(cur, company_code=company))

    @app.get("/dashboard/performance/feedback")
    def dashboard_performance_feedback(
        employee_key: str = "",
        offset: int = 0,
        limit: int = 100,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        return dashboard_performance_check_ins(employee_key, offset, limit, context)

    @app.get("/dashboard/performance/check-ins")
    def dashboard_performance_check_ins(
        employee_key: str = "",
        offset: int = 0,
        limit: int = 100,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_check_ins(
                cur,
                company_code=company,
                employee_key=employee_key or None,
                manager_scope_keys=_manager_keys(context, company),
                actor_role=_role(context),
                offset=offset,
                limit=limit,
            )
        )

    @app.post("/dashboard/performance/check-ins")
    def dashboard_performance_create_check_in(
        body: CheckInBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        return _run(
            lambda cur: c3.create_check_in(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                employee_key=body.employee_key,
                kind=body.kind,
                manager_employee_key=body.manager_employee_key,
                scheduled_for=_as_date(body.scheduled_for),
                notes_shared=body.notes_shared,
                talking_points=body.talking_points,
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/check-ins/{check_in_id}")
    def dashboard_performance_check_in_detail(
        check_in_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        def _do(cur: Any) -> dict[str, Any]:
            row = c3.get_check_in(cur, company_code=company, check_in_id=check_in_id)
            if not row:
                return {"ok": False, "error": "check_in_not_found"}
            if _role(context) == "employee":
                row = dict(row)
                row.pop("notes_sensitive", None)
            return {"ok": True, "check_in": row}

        return _run(_do)

    @app.post("/dashboard/performance/check-ins/{check_in_id}/complete")
    def dashboard_performance_complete_check_in(
        check_in_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: c3.complete_check_in(
                cur,
                company_code=company,
                check_in_id=check_in_id,
                actor_phone=_actor_phone(context),
                expected_row_version=int(body.expected_row_version or 1),
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/development")
    def dashboard_performance_development(
        employee_key: str = "",
        offset: int = 0,
        limit: int = 100,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_development(
                cur,
                company_code=company,
                employee_key=employee_key or None,
                manager_scope_keys=_manager_keys(context, company),
                actor_role=_role(context),
                offset=offset,
                limit=limit,
            )
        )

    @app.post("/dashboard/performance/development/plans")
    def dashboard_performance_create_plan(
        body: DevelopmentPlanBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        return _run(
            lambda cur: c3.create_development_plan(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                employee_key=body.employee_key,
                title_en=body.title_en,
                title_ar=body.title_ar,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/development/actions")
    def dashboard_performance_create_action(
        body: DevelopmentActionBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: c3.create_development_action(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                plan_id=body.plan_id,
                title_en=body.title_en,
                title_ar=body.title_ar,
                description_en=body.description_en,
                due_date=_as_date(body.due_date),
                owner_employee_key=body.owner_employee_key,
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/development/actions/{action_id}/advance")
    def dashboard_performance_advance_action(
        action_id: str, body: AdvanceActionBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        return _run(
            lambda cur: c3.advance_development_action(
                cur,
                company_code=company,
                action_id=action_id,
                actor_phone=_actor_phone(context),
                to_status=body.to_status,
                expected_row_version=int(body.expected_row_version or 1),
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/calibration")
    def dashboard_performance_calibration(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        perms = _perms(context)
        if "performance.calibrate" not in perms and _role(context) != "hr":
            raise HTTPException(status_code=403, detail={"error": "calibration_forbidden"})
        return _run(
            lambda cur: surfaces.list_calibration_sessions(
                cur, company_code=company, actor_phone=_actor_phone(context)
            )
        )

    @app.post("/dashboard/performance/calibration")
    def dashboard_performance_create_calibration(
        body: CalibrationBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _require_cycle_admin(context)
        perms = _perms(context)
        if "performance.calibrate" not in perms:
            raise HTTPException(status_code=403, detail={"error": "calibration_forbidden"})
        return _run(
            lambda cur: c4.create_calibration_session(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                cycle_id=body.cycle_id,
                name_en=body.name_en,
                name_ar=body.name_ar,
                reason=body.reason,
            )
        )

    @app.get("/dashboard/performance/calibration/{session_id}")
    def dashboard_performance_calibration_detail(
        session_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        perms = _perms(context)
        return _run(
            lambda cur: surfaces.get_calibration_detail(
                cur,
                company_code=company,
                session_id=session_id,
                actor_phone=_actor_phone(context),
                can_calibrate="performance.calibrate" in perms,
            )
        )

    @app.post("/dashboard/performance/calibration/{session_id}/adjust")
    def dashboard_performance_calibrate_adjust(
        session_id: str, body: CalibrationAdjustBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        if "performance.calibrate" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "calibration_forbidden"})
        return _run(
            lambda cur: c4.apply_calibration_adjustment(
                cur,
                company_code=company,
                session_id=session_id,
                actor_phone=_actor_phone(context),
                subject_employee_key=body.subject_employee_key,
                new_value=body.new_value,
                expected_row_version=int(body.expected_row_version or 1),
                new_label=body.new_label,
                has_sensitive_permission="performance.sensitive" in _perms(context),
                reason=body.reason,
            )
        )

    @app.post("/dashboard/performance/calibration/{session_id}/lock")
    def dashboard_performance_calibrate_lock(
        session_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context, write=True)
        if "performance.calibrate" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "calibration_forbidden"})
        return _run(
            lambda cur: c4.lock_and_publish_calibration(
                cur,
                company_code=company,
                session_id=session_id,
                actor_phone=_actor_phone(context),
                reason=body.reason,
                has_sensitive_permission="performance.sensitive" in _perms(context),
            )
        )

    @app.get("/dashboard/performance/manager/queue")
    def dashboard_performance_manager_queue(
        limit: int = 50, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        keys = _manager_keys(context, company)
        if keys is None:
            keys = []
        return _run(
            lambda cur: surfaces.manager_queue(
                cur, company_code=company, manager_scope_keys=keys, limit=limit
            )
        )

    # --- HR Mobile thin queue ---------------------------------------------------
    @app.get("/dashboard/mobile/performance")
    def dashboard_mobile_performance_queue(
        offset: int = 0,
        limit: int = 30,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        payload = _run(
            lambda cur: surfaces.list_reviews(
                cur,
                company_code=company,
                reviewer_role="manager",
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
                pending_only=True,
                offset=offset,
                limit=limit,
            )
        )
        items = []
        for review in payload.get("reviews") or []:
            items.append(
                {
                    "review_id": review.get("review_id"),
                    "subject_employee_key": review.get("subject_employee_key"),
                    "cycle_name_en": review.get("cycle_name_en"),
                    "cycle_name_ar": review.get("cycle_name_ar"),
                    "status": review.get("status"),
                    "reviewer_role": review.get("reviewer_role"),
                    "destination": f"/performance/{review.get('review_id')}",
                    "allowed_actions": ["read", "submit"] if review.get("status") in {"not_started", "draft"} else ["read"],
                }
            )
        return json_safe(
            {
                "ok": True,
                "items": items,
                "total": payload.get("total") or 0,
                "has_more": (offset + len(items)) < int(payload.get("total") or 0),
                "offset": offset,
                "limit": limit,
            }
        )

    @app.get("/dashboard/mobile/performance/reviews/{review_id}")
    def dashboard_mobile_performance_review(
        review_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.get_review_detail(
                cur,
                company_code=company,
                review_id=review_id,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
                can_see_sensitive="performance.sensitive" in _perms(context),
            )
        )

    @app.post("/dashboard/mobile/performance/reviews/{review_id}/submit")
    def dashboard_mobile_performance_submit(
        review_id: str, body: ReviewSubmitBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return dashboard_performance_submit_review(review_id, body, context)

    # --- Employee App -----------------------------------------------------------
    def _app_company(context: dict[str, Any]) -> tuple[str, str]:
        require_employee_app_feature(context, "performance", action="view")
        company = str(context["company_code"]).upper()
        employee_key = str(context["employee_key"])
        gate = c1.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company, employee_key

    @app.get("/app/performance")
    def app_performance(context: dict[str, Any] = Depends(employee_app_context)):
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: surfaces.employee_workspace(
                cur, company_code=company, employee_key=employee_key
            )
        )

    @app.get("/app/performance/okr-cycles/current")
    def app_performance_current_okr_cycle(context: dict[str, Any] = Depends(employee_app_context)):
        company, _employee_key = _app_company(context)
        return _run(lambda cur: pt1.current_okr_cycle(cur, company_code=company))

    @app.get("/app/performance/objectives")
    def app_performance_objectives(context: dict[str, Any] = Depends(employee_app_context)):
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: pt1.list_cycle_objectives(
                cur,
                company_code=company,
                owner_employee_key=employee_key,
                actor_role="employee",
                actor_employee_key=employee_key,
            )
        )

    @app.post("/app/performance/objectives/{objective_id}/updates")
    def app_performance_okr_update(
        objective_id: str, body: OkrUpdateBody, context: dict[str, Any] = Depends(employee_app_context)
    ):
        require_employee_app_feature(context, "performance", action="update")
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: pt1.record_update(
                cur,
                company_code=company,
                actor_phone=_actor_phone(context),
                subject_type=body.subject_type,
                subject_id=body.subject_id or objective_id,
                update_text=body.update_text,
                actor_employee_key=employee_key,
                observed_value=body.observed_value,
                confidence=body.confidence,
                cycle_id=body.cycle_id,
                reason=body.reason,
            )
        )

    @app.get("/app/performance/objectives/{objective_id}")
    def app_performance_objective_detail(
        objective_id: str, context: dict[str, Any] = Depends(employee_app_context)
    ):
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: surfaces.get_objective_detail(
                cur,
                company_code=company,
                objective_id=objective_id,
                actor_employee_key=employee_key,
                actor_role="employee",
            )
        )

    @app.post("/app/performance/progress")
    def app_performance_progress(
        body: ProgressBody, context: dict[str, Any] = Depends(employee_app_context)
    ):
        require_employee_app_feature(context, "performance", action="update")
        company, employee_key = _app_company(context)

        def _do(cur: Any) -> dict[str, Any]:
            if not surfaces.employee_owns_progress_subject(
                cur,
                company_code=company,
                employee_key=employee_key,
                subject_type=body.subject_type,
                subject_id=body.subject_id,
            ):
                return {"ok": False, "error": "progress_not_owned"}
            return c1.record_progress(
                cur,
                company_code=company,
                subject_type=body.subject_type,
                subject_id=body.subject_id,
                actor_phone=_actor_phone(context),
                current_value=body.current_value,
                source=body.source,
                note=body.note,
                progress_pct=body.progress_pct,
            )

        return _run(_do)

    @app.get("/app/performance/reviews")
    def app_performance_reviews(context: dict[str, Any] = Depends(employee_app_context)):
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: surfaces.list_reviews(
                cur,
                company_code=company,
                actor_role="employee",
                actor_employee_key=employee_key,
            )
        )

    @app.get("/app/performance/reviews/{review_id}")
    def app_performance_review_detail(
        review_id: str, context: dict[str, Any] = Depends(employee_app_context)
    ):
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: surfaces.get_review_detail(
                cur,
                company_code=company,
                review_id=review_id,
                actor_role="employee",
                actor_employee_key=employee_key,
                can_see_sensitive=False,
            )
        )

    @app.post("/app/performance/reviews/{review_id}/submit")
    def app_performance_submit_review(
        review_id: str, body: ReviewSubmitBody, context: dict[str, Any] = Depends(employee_app_context)
    ):
        require_employee_app_feature(context, "performance", action="submit")
        company, employee_key = _app_company(context)

        def _do(cur: Any) -> dict[str, Any]:
            cur.execute(
                "SELECT * FROM perf_reviews WHERE company_code=%s AND review_id=%s",
                (company, review_id),
            )
            row = cur.fetchone()
            if not row:
                return {"ok": False, "error": "review_not_found"}
            review = dict(row)
            if str(review.get("reviewer_employee_key") or "") not in {"", employee_key} and str(
                review.get("subject_employee_key") or ""
            ) != employee_key:
                return {"ok": False, "error": "review_not_found"}
            if str(review.get("reviewer_role") or "") == "manager" and str(
                review.get("reviewer_employee_key") or ""
            ) != employee_key:
                return {"ok": False, "error": "permission_denied"}
            return c2.submit_review(
                cur,
                company_code=company,
                cycle_id=str(review["cycle_id"]),
                assignment_id=str(review["assignment_id"]),
                actor_phone=_actor_phone(context),
                actor_employee_key=employee_key,
                overall_rating_value=body.overall_rating_value,
                rationale=body.rationale,
                components=body.components,
                competency_ratings=body.competency_ratings,
                confidential_comment=None,
                overall_rating_label=body.overall_rating_label,
                expected_version=body.expected_version,
            )

        return _run(_do)

    @app.get("/app/performance/feedback")
    def app_performance_feedback(context: dict[str, Any] = Depends(employee_app_context)):
        return app_performance_check_ins(context)

    @app.get("/app/performance/check-ins")
    def app_performance_check_ins(context: dict[str, Any] = Depends(employee_app_context)):
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: surfaces.list_check_ins(
                cur, company_code=company, employee_key=employee_key, actor_role="employee"
            )
        )

    @app.get("/app/performance/development")
    def app_performance_development(context: dict[str, Any] = Depends(employee_app_context)):
        company, employee_key = _app_company(context)
        return _run(
            lambda cur: surfaces.list_development(
                cur, company_code=company, employee_key=employee_key, actor_role="employee"
            )
        )

    _ = require_entitlement
