#!/usr/bin/env python3
"""HTTP adapters for Compensation Planning (R5I) — thin wrappers over frozen C6.

Namespaces:
  /dashboard/compensation-planning/...
  /dashboard/posthire/compensation-planning/...  (alias)

No Employee App namespace. No HR Mobile namespace.
Company and actor identity come from authenticated context only.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import compensation_planning_c6 as c6
import compensation_surfaces as surfaces

DASH_PREFIXES = ("/dashboard/compensation-planning", "/dashboard/posthire/compensation-planning")


class CycleBody(BaseModel):
    code: str
    title_en: str
    title_ar: str
    eligibility_rule: dict[str, Any] | None = None
    currency: str = "KWD"


class LaunchBody(BaseModel):
    population: list[dict[str, Any]]


class BudgetBody(BaseModel):
    cycle_id: str
    scope_type: str = "company"
    scope_key: str = "ALL"
    allocated: float
    currency: str = "KWD"


class BandBody(BaseModel):
    code: str
    ja_grade_id: str
    minimum: float
    midpoint: float
    maximum: float
    currency: str = "KWD"
    ja_level_id: str | None = None
    band_version: int = 1
    effective_start: str | None = None


class RecommendBody(BaseModel):
    cycle_id: str
    employee_key: str
    recommendation_type: str
    amount: float | None = None
    percent: float | None = None
    rationale: str = ""
    performance_guided: bool = False
    talent_guided: bool = False
    proposed_ja_grade_id: str | None = None
    hipo_auto_convert: bool = False


class CalibrateBody(BaseModel):
    cycle_id: str
    original_recommendation_id: str
    amount: float
    rationale: str = ""


class ApproveBody(BaseModel):
    cycle_id: str
    recommendation_id: str
    decision: str = "approved"


class HandoffBody(BaseModel):
    cycle_id: str
    decision_id: str
    target_authority: str
    employment_ref: str = ""


class AssistantBody(BaseModel):
    question_kind: str
    cycle_id: str | None = None


_GATE_ERRORS = {
    "comp_planning_c6_off",
    "comp_planning_company_not_allowlisted",
    "comp_planning_disabled_for_company",
    "ja_hard_dependency_unmet",
    "ja_must_be_enabled",
    "company_disabled",
    "entitlement_off",
}

_NOT_FOUND = {"cycle_not_found", "decision_not_found", "recommendation_not_found", "snapshot_not_found"}

_FORBIDDEN = {
    "permission_denied",
    "scope_denied",
    "manager_scope_denied",
    "sod_violation_recommend_approve_same_actor",
    "mutation_forbidden",
    "employee_draft_visibility_forbidden",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "comp_planning_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "Compensation Planning is not available for this company.",
                "gate": result.get("gate"),
                "resource_state": "unavailable",
                "ja_hard_unmet": err in {"ja_hard_dependency_unmet", "ja_must_be_enabled"},
            },
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted.", "resource_state": "forbidden"})
    if err in {
        "budget_overrun_hard_block",
        "budget_overrun_requires_exception_approval",
        "currency_unsupported_no_fx",
        "invalid_band_order",
        "ja_grade_required",
        "employee_not_eligible",
        "cycle_not_draft",
        "cycle_not_open_for_recommendations",
        "original_recommendation_required",
        "performance_input_disabled",
        "talent_input_disabled",
        "hipo_not_automatic_pay",
        "payroll_handoff_disabled",
        "invalid_handoff_target",
        "invalid_recommendation_type",
        "invalid_budget_scope",
        "invalid_budget_overrun_mode",
    }:
        raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_compensation_planning_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    posthire_context = app_mod._posthire_read_context
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key
    require_entitlement = app_mod.require_entitlement
    deliver_employee_notification = getattr(app_mod, "deliver_employee_notification", None)
    find_employee_by_key = getattr(app_mod, "find_employee_by_key", None)
    context_manager_employee_keys = getattr(app_mod, "context_manager_employee_keys", None)

    def _perms(context: dict[str, Any]) -> set[str]:
        return set(context_permissions(context, dashboard_context_role_key(context)) or [])

    def _role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or dashboard_context_role_key(context) or "").strip().lower()
        if role in {"owner", "hr_admin", "hr_manager", "admin"}:
            return "hr"
        if role in {"manager"}:
            return "manager"
        return role or "hr"

    def _phone(context: dict[str, Any]) -> str:
        return str(context.get("actor_phone") or context.get("phone") or "")

    def _actor_key(context: dict[str, Any], *, manager: bool = False) -> str:
        if manager:
            return str(context.get("employee_key") or context.get("actor_employee_key") or context.get("actor_user_id") or "manager")
        return f"hr-{context.get('actor_user_id') or _phone(context) or 'ops'}"

    def _company(context: dict[str, Any], *, write: bool = False, need: set[str] | None = None) -> str:
        if _role(context) == "manager":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "permission_denied",
                    "message": "Managers do not have a Compensation Planning administration workspace.",
                    "resource_state": "forbidden",
                },
            )
        company = posthire_context(context, "comp_planning")
        perms = _perms(context)
        required = need or ({"comp_planning.manage"} if write else set())
        if write and required and not (required & perms) and "comp_planning.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        gate = c6.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _require(context: dict[str, Any], perm: str) -> None:
        if perm not in _perms(context) and "comp_planning.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})

    def _manager_keys(context: dict[str, Any], company: str) -> list[str]:
        if not context_manager_employee_keys:
            return []
        keys = context_manager_employee_keys(context, company) or set()
        return sorted(str(item) for item in keys)

    def _notify(company: str, employee_key: str, *, template_key: str) -> None:
        if not deliver_employee_notification or not find_employee_by_key:
            return
        employee = find_employee_by_key(employee_key, company_code=company)
        if not employee:
            return
        try:
            deliver_employee_notification(
                employee,
                flow="compensation_planning",
                template_key=template_key,
                text="A Compensation Planning action requires your attention.",
                email_subject="Compensation Planning",
                company_code=company,
                dedupe_key=f"comp_planning:{template_key}:{company}:{employee_key}",
            )
        except Exception:
            return

    def _run(callback: Any) -> Any:
        with db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.ensure_schema(cur)
                result = callback(cur)
            conn.commit()
        if isinstance(result, dict) and result.get("ok") is False:
            _raise_gate(result)
        return json_safe(result)

    def _bind(path: str, handler: Any, methods: tuple[str, ...] = ("GET",)) -> None:
        for prefix in DASH_PREFIXES:
            app.add_api_route(prefix + path, handler, methods=list(methods))

    def dashboard_workspace(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.workspace_summary(cur, company_code=company))

    def dashboard_cycles(status: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_cycles(cur, company_code=company, status=status))

    def dashboard_create_cycle(body: CycleBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.manage"})
        return _run(
            lambda cur: surfaces.create_cycle(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                code=body.code,
                title_en=body.title_en,
                title_ar=body.title_ar,
                eligibility_rule=body.eligibility_rule,
                currency=body.currency,
            )
        )

    def dashboard_cycle(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.cycle_detail(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_launch(cycle_id: str, body: LaunchBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.manage"})
        result = _run(
            lambda cur: surfaces.launch_cycle(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                cycle_id=cycle_id,
                population=body.population,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            for emp in body.population:
                if emp.get("eligible", True) and emp.get("manager_key"):
                    _notify(company, str(emp["manager_key"]), template_key="comp_recommendation_required")
        return result

    def dashboard_eligibility(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.eligibility_snapshot(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_budgets(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_budgets(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_create_budget(body: BudgetBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.manage"})
        return _run(
            lambda cur: surfaces.create_budget(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                cycle_id=body.cycle_id,
                scope_type=body.scope_type,
                scope_key=body.scope_key,
                allocated=body.allocated,
                currency=body.currency,
            )
        )

    def dashboard_bands(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_bands(cur, company_code=company))

    def dashboard_create_band(body: BandBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.manage"})
        return _run(
            lambda cur: surfaces.upsert_salary_band(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                code=body.code,
                ja_grade_id=body.ja_grade_id,
                minimum=body.minimum,
                midpoint=body.midpoint,
                maximum=body.maximum,
                currency=body.currency,
                ja_level_id=body.ja_level_id,
                band_version=body.band_version,
                effective_start=body.effective_start,
            )
        )

    def dashboard_worksheet(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.worksheet(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_recommend(body: RecommendBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.recommend", "comp_planning.manage"})
        return _run(
            lambda cur: surfaces.create_recommendation(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                cycle_id=body.cycle_id,
                employee_key=body.employee_key,
                actor_key=_actor_key(context),
                recommendation_type=body.recommendation_type,
                amount=body.amount,
                percent=body.percent,
                rationale=body.rationale,
                performance_guided=body.performance_guided,
                talent_guided=body.talent_guided,
                proposed_ja_grade_id=body.proposed_ja_grade_id,
                hipo_auto_convert=body.hipo_auto_convert,
            )
        )

    def dashboard_recommendations(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_recommendations(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_calibrate(body: CalibrateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.calibrate", "comp_planning.manage"})
        _require(context, "comp_planning.calibrate")
        return _run(
            lambda cur: surfaces.calibrate_recommendation(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                cycle_id=body.cycle_id,
                original_recommendation_id=body.original_recommendation_id,
                actor_key=_actor_key(context),
                amount=body.amount,
                rationale=body.rationale,
            )
        )

    def dashboard_approve(body: ApproveBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.approve", "comp_planning.manage"})
        _require(context, "comp_planning.approve")
        return _run(
            lambda cur: surfaces.approve_recommendation(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                cycle_id=body.cycle_id,
                recommendation_id=body.recommendation_id,
                approver_key=_actor_key(context),
                decision=body.decision,
            )
        )

    def dashboard_approvals(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_approvals(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_finalize(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.finalize", "comp_planning.manage"})
        _require(context, "comp_planning.finalize")
        return _run(
            lambda cur: surfaces.finalize_cycle(
                cur, company_code=company, actor_phone=_phone(context), cycle_id=cycle_id
            )
        )

    def dashboard_finalized(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_final_decisions(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_handoff(body: HandoffBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"comp_planning.manage"})
        return _run(
            lambda cur: surfaces.create_handoff(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                cycle_id=body.cycle_id,
                decision_id=body.decision_id,
                target_authority=body.target_authority,
                employment_ref=body.employment_ref,
            )
        )

    def dashboard_handoffs(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_handoffs(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_execution(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.execution_status(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_history(cycle_id: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_history(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_export(cycle_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "comp_planning.export")
        return _run(lambda cur: surfaces.export_worksheet(cur, company_code=company, cycle_id=cycle_id))

    def dashboard_assistant(body: AssistantBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.assistant_query(
                cur,
                company_code=company,
                actor=_phone(context),
                question_kind=body.question_kind,
                cycle_id=body.cycle_id,
            )
        )

    def dashboard_manager(cycle_id: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        if _role(context) != "manager" and "comp_planning.manager" not in _perms(context) and "comp_planning.read" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        require_entitlement(context, "comp_planning")
        company = str(context.get("company_code") or "").upper()
        if _role(context) == "manager" and "comp_planning.manager" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        gate = c6.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        keys = _manager_keys(context, company) if _role(context) == "manager" else []
        if _role(context) == "manager":
            return _run(
                lambda cur: surfaces.manager_worksheet(
                    cur,
                    company_code=company,
                    manager_scope_employee_keys=keys,
                    cycle_id=cycle_id,
                )
            )
        return _run(
            lambda cur: surfaces.manager_worksheet(
                cur,
                company_code=company,
                manager_scope_employee_keys=keys,
                cycle_id=cycle_id,
            )
        )

    def dashboard_manager_recommend(body: RecommendBody, context: dict[str, Any] = Depends(dashboard_context)):
        if _role(context) != "manager" or "comp_planning.manager" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        require_entitlement(context, "comp_planning")
        company = str(context.get("company_code") or "").upper()
        keys = set(_manager_keys(context, company))
        if body.employee_key not in keys:
            raise HTTPException(status_code=403, detail={"error": "manager_scope_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        return _run(
            lambda cur: surfaces.create_recommendation(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                cycle_id=body.cycle_id,
                employee_key=body.employee_key,
                actor_key=_actor_key(context, manager=True),
                recommendation_type=body.recommendation_type,
                amount=body.amount,
                percent=body.percent,
                rationale=body.rationale,
            )
        )

    _bind("", dashboard_workspace)
    _bind("/workspace", dashboard_workspace)
    _bind("/cycles", dashboard_cycles)
    _bind("/cycles", dashboard_create_cycle, ("POST",))
    _bind("/cycles/{cycle_id}", dashboard_cycle)
    _bind("/cycles/{cycle_id}/launch", dashboard_launch, ("POST",))
    _bind("/cycles/{cycle_id}/eligibility", dashboard_eligibility)
    _bind("/cycles/{cycle_id}/budgets", dashboard_budgets)
    _bind("/budgets", dashboard_create_budget, ("POST",))
    _bind("/bands", dashboard_bands)
    _bind("/bands", dashboard_create_band, ("POST",))
    _bind("/cycles/{cycle_id}/worksheet", dashboard_worksheet)
    _bind("/recommendations", dashboard_recommend, ("POST",))
    _bind("/cycles/{cycle_id}/recommendations", dashboard_recommendations)
    _bind("/calibrate", dashboard_calibrate, ("POST",))
    _bind("/approve", dashboard_approve, ("POST",))
    _bind("/cycles/{cycle_id}/approvals", dashboard_approvals)
    _bind("/cycles/{cycle_id}/finalize", dashboard_finalize, ("POST",))
    _bind("/cycles/{cycle_id}/finalized", dashboard_finalized)
    _bind("/handoffs", dashboard_handoff, ("POST",))
    _bind("/cycles/{cycle_id}/handoffs", dashboard_handoffs)
    _bind("/cycles/{cycle_id}/execution", dashboard_execution)
    _bind("/history", dashboard_history)
    _bind("/cycles/{cycle_id}/export", dashboard_export)
    _bind("/assistant", dashboard_assistant, ("POST",))
    _bind("/manager", dashboard_manager)
    _bind("/manager/recommend", dashboard_manager_recommend, ("POST",))
