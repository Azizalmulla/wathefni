#!/usr/bin/env python3
"""HTTP adapters for Workforce Planning (R5J) — thin wrappers over frozen C7.

Namespaces:
  /dashboard/workforce-planning/...
  /dashboard/posthire/workforce-planning/...  (alias)

No Employee App namespace. No HR Mobile namespace.
Company and actor identity come from authenticated context only.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import workforce_planning_c7 as c7
import workforce_planning_surfaces as surfaces

DASH_PREFIXES = ("/dashboard/workforce-planning", "/dashboard/posthire/workforce-planning")


class PlanBody(BaseModel):
    code: str
    title_en: str
    title_ar: str
    horizon: str | None = None
    currency: str = "KWD"
    period_start: str | None = None
    period_end: str | None = None
    fiscal_year: int | None = None


class BaselineBody(BaseModel):
    as_of_date: str
    population: list[dict[str, Any]] | None = None


class ScenarioBody(BaseModel):
    code: str
    scenario_type: str
    title_en: str
    title_ar: str
    parent_scenario_id: str | None = None


class ReviseBody(BaseModel):
    approved_scenario_id: str
    code: str
    title_en: str
    title_ar: str


class AssumptionBody(BaseModel):
    scenario_id: str
    assumption_key: str
    value: dict[str, Any]
    source: str = "explicit_planner"
    notes_en: str = ""
    notes_ar: str = ""
    assumption_version: int = 1


class DemandBody(BaseModel):
    plan_id: str
    scenario_id: str
    demand_type: str
    quantity: int
    ja_profile_id: str
    ja_grade_id: str | None = None
    ja_level_id: str | None = None
    org_unit: str = ""
    location: str = ""
    target_period: str | None = None
    reason_en: str = ""
    reason_ar: str = ""
    owner_key: str = ""
    planned_unit_cost: float | None = None
    capability_demand: dict[str, Any] | None = None


class GapBody(BaseModel):
    scenario_id: str
    definition: str = "planned_demand_vs_baseline"
    ja_profile_id: str | None = None


class CompareBody(BaseModel):
    scenario_a: str
    scenario_b: str


class ApproveBody(BaseModel):
    plan_id: str
    scenario_id: str
    decision: str = "approved"


class HandoffBody(BaseModel):
    plan_id: str
    scenario_id: str
    demand_id: str
    target_authority: str | None = None


class AssistantBody(BaseModel):
    question_kind: str
    scenario_id: str | None = None


_GATE_ERRORS = {
    "workforce_planning_c7_off",
    "workforce_planning_company_not_allowlisted",
    "workforce_planning_disabled_for_company",
    "ja_hard_dependency_unmet",
    "ja_must_be_enabled",
    "company_disabled",
    "entitlement_off",
}

_NOT_FOUND = {
    "plan_not_found",
    "scenario_not_found",
    "demand_not_found",
    "baseline_not_found",
    "handoff_not_found",
}

_FORBIDDEN = {
    "permission_denied",
    "scope_denied",
    "manager_scope_denied",
    "mutation_forbidden",
    "employee_plan_visibility_forbidden",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "workforce_planning_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "Workforce Planning is not available for this company.",
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
        "currency_unsupported_no_fx",
        "currency_mismatch_fail_closed",
        "invalid_horizon",
        "invalid_scenario_type",
        "invalid_demand_type",
        "invalid_decision",
        "invalid_gap_definition",
        "invalid_handoff_target",
        "ja_profile_required",
        "ja_grade_required",
        "replacement_reason_required_explicit",
        "wave5_turnover_must_be_explicitly_selected",
        "comp_assumptions_disabled",
        "talent_skills_disabled",
        "baseline_already_frozen",
        "plan_not_draft",
        "scenario_not_open_for_demand",
        "scenario_not_approved",
        "approved_scenario_immutable_create_revision",
        "approved_scenario_required_for_revision",
        "reduction_not_requisition_handoff",
        "recruiting_handoff_disabled",
        "handoff_not_cancellable",
        "handoff_must_be_draft_only",
        "incompatible_baselines_fail_closed",
        "scenarios_not_found",
    }:
        raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_workforce_planning_http(app_mod: Any) -> None:
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
                    "message": "Managers do not have a Workforce Planning administration workspace.",
                    "resource_state": "forbidden",
                },
            )
        company = posthire_context(context, "workforce_planning")
        perms = _perms(context)
        required = need or ({"workforce_planning.manage"} if write else set())
        if write and required and not (required & perms) and "workforce_planning.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        gate = c7.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _require(context: dict[str, Any], perm: str) -> None:
        if perm not in _perms(context) and "workforce_planning.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})

    def _can_cost(context: dict[str, Any]) -> bool:
        perms = _perms(context)
        return "workforce_planning.cost" in perms or "workforce_planning.manage" in perms

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
                flow="workforce_planning",
                template_key=template_key,
                text="A Workforce Planning action requires your attention.",
                email_subject="Workforce Planning",
                company_code=company,
                dedupe_key=f"workforce_planning:{template_key}:{company}:{employee_key}",
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

    def dashboard_plans(status: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_plans(cur, company_code=company, status=status))

    def dashboard_create_plan(body: PlanBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        return _run(
            lambda cur: surfaces.create_plan(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                code=body.code,
                title_en=body.title_en,
                title_ar=body.title_ar,
                horizon=body.horizon,
                currency=body.currency,
                period_start=body.period_start,
                period_end=body.period_end,
                fiscal_year=body.fiscal_year,
            )
        )

    def dashboard_plan(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.plan_detail(cur, company_code=company, plan_id=plan_id))

    def dashboard_freeze_baseline(plan_id: str, body: BaselineBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        return _run(
            lambda cur: surfaces.freeze_baseline(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                plan_id=plan_id,
                as_of_date=body.as_of_date,
                population=body.population,
            )
        )

    def dashboard_baseline(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.get_baseline(cur, company_code=company, plan_id=plan_id))

    def dashboard_scenarios(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_scenarios(cur, company_code=company, plan_id=plan_id))

    def dashboard_create_scenario(plan_id: str, body: ScenarioBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        return _run(
            lambda cur: surfaces.create_scenario(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                plan_id=plan_id,
                code=body.code,
                scenario_type=body.scenario_type,
                title_en=body.title_en,
                title_ar=body.title_ar,
                parent_scenario_id=body.parent_scenario_id,
            )
        )

    def dashboard_revise(plan_id: str, body: ReviseBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        return _run(
            lambda cur: surfaces.revise_scenario(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                plan_id=plan_id,
                approved_scenario_id=body.approved_scenario_id,
                code=body.code,
                title_en=body.title_en,
                title_ar=body.title_ar,
            )
        )

    def dashboard_assumptions(scenario_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_assumptions(cur, company_code=company, scenario_id=scenario_id))

    def dashboard_upsert_assumption(body: AssumptionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        return _run(
            lambda cur: surfaces.upsert_assumption(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                scenario_id=body.scenario_id,
                assumption_key=body.assumption_key,
                value=body.value,
                source=body.source,
                notes_en=body.notes_en,
                notes_ar=body.notes_ar,
                assumption_version=body.assumption_version,
            )
        )

    def dashboard_demand(
        plan_id: str | None = None,
        scenario_id: str | None = None,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_demand(
                cur,
                company_code=company,
                plan_id=plan_id,
                scenario_id=scenario_id,
                include_cost=_can_cost(context),
            )
        )

    def dashboard_add_demand(body: DemandBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        return _run(
            lambda cur: surfaces.add_demand(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                plan_id=body.plan_id,
                scenario_id=body.scenario_id,
                demand_type=body.demand_type,
                quantity=body.quantity,
                ja_profile_id=body.ja_profile_id,
                ja_grade_id=body.ja_grade_id,
                ja_level_id=body.ja_level_id,
                org_unit=body.org_unit,
                location=body.location,
                target_period=body.target_period,
                reason_en=body.reason_en,
                reason_ar=body.reason_ar,
                owner_key=body.owner_key,
                planned_unit_cost=body.planned_unit_cost,
                capability_demand=body.capability_demand,
            )
        )

    def dashboard_planned_positions(scenario_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_planned_positions(
                cur, company_code=company, scenario_id=scenario_id, include_cost=_can_cost(context)
            )
        )

    def dashboard_projection(scenario_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.project_headcount(cur, company_code=company, scenario_id=scenario_id))

    def dashboard_cost(scenario_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "workforce_planning.cost")
        return _run(lambda cur: surfaces.project_planned_cost(cur, company_code=company, scenario_id=scenario_id))

    def dashboard_compute_gap(body: GapBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        return _run(
            lambda cur: surfaces.compute_gap(
                cur,
                company_code=company,
                scenario_id=body.scenario_id,
                definition=body.definition,
                ja_profile_id=body.ja_profile_id,
            )
        )

    def dashboard_gaps(scenario_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_gaps(cur, company_code=company, scenario_id=scenario_id))

    def dashboard_compare(body: CompareBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.compare_scenarios(
                cur, company_code=company, scenario_a=body.scenario_a, scenario_b=body.scenario_b
            )
        )

    def dashboard_submit(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.manage", "workforce_planning.plan"})
        result = _run(
            lambda cur: surfaces.submit_plan(
                cur, company_code=company, actor_phone=_phone(context), plan_id=plan_id
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(company, _actor_key(context), template_key="wfp_approval_required")
        return result

    def dashboard_approve(body: ApproveBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.approve", "workforce_planning.manage"})
        _require(context, "workforce_planning.approve")
        return _run(
            lambda cur: surfaces.approve_scenario(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                plan_id=body.plan_id,
                scenario_id=body.scenario_id,
                approver_key=_actor_key(context),
                decision=body.decision,
            )
        )

    def dashboard_approvals(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_approvals(cur, company_code=company, plan_id=plan_id))

    def dashboard_handoff(body: HandoffBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.execute", "workforce_planning.manage"})
        _require(context, "workforce_planning.execute")
        return _run(
            lambda cur: surfaces.create_execution_handoff(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                plan_id=body.plan_id,
                scenario_id=body.scenario_id,
                demand_id=body.demand_id,
                target_authority=body.target_authority,
            )
        )

    def dashboard_handoffs(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_handoffs(cur, company_code=company, plan_id=plan_id))

    def dashboard_execution(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.execution_status(cur, company_code=company, plan_id=plan_id))

    def dashboard_cancel_handoff(handoff_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"workforce_planning.execute", "workforce_planning.manage"})
        _require(context, "workforce_planning.execute")
        return _run(
            lambda cur: surfaces.cancel_execution_handoff(
                cur, company_code=company, actor_phone=_phone(context), handoff_id=handoff_id
            )
        )

    def dashboard_actual_vs_plan(scenario_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.actual_vs_plan(cur, company_code=company, scenario_id=scenario_id))

    def dashboard_history(plan_id: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_history(cur, company_code=company, plan_id=plan_id))

    def dashboard_export(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "workforce_planning.export")
        return _run(
            lambda cur: surfaces.export_plan(
                cur, company_code=company, plan_id=plan_id, include_cost=_can_cost(context)
            )
        )

    def dashboard_assistant(body: AssistantBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.assistant_query(
                cur,
                company_code=company,
                actor=_phone(context),
                question_kind=body.question_kind,
                scenario_id=body.scenario_id,
            )
        )

    def dashboard_manager(plan_id: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        if _role(context) != "manager" and "workforce_planning.manager" not in _perms(context) and "workforce_planning.read" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        require_entitlement(context, "workforce_planning")
        company = str(context.get("company_code") or "").upper()
        if _role(context) == "manager" and "workforce_planning.manager" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        gate = c7.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        keys = _manager_keys(context, company) if _role(context) == "manager" else []
        return _run(
            lambda cur: surfaces.manager_workspace(
                cur,
                company_code=company,
                manager_scope_employee_keys=keys,
                plan_id=plan_id,
            )
        )

    def dashboard_manager_demand(body: DemandBody, context: dict[str, Any] = Depends(dashboard_context)):
        if _role(context) != "manager" or "workforce_planning.manager" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        require_entitlement(context, "workforce_planning")
        company = str(context.get("company_code") or "").upper()
        keys = set(_manager_keys(context, company))
        owner = body.owner_key or _actor_key(context, manager=True)
        if owner not in keys and _actor_key(context, manager=True) not in keys:
            raise HTTPException(status_code=403, detail={"error": "manager_scope_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        return _run(
            lambda cur: surfaces.add_demand(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                plan_id=body.plan_id,
                scenario_id=body.scenario_id,
                demand_type=body.demand_type,
                quantity=body.quantity,
                ja_profile_id=body.ja_profile_id,
                ja_grade_id=body.ja_grade_id,
                ja_level_id=body.ja_level_id,
                org_unit=body.org_unit,
                location=body.location,
                target_period=body.target_period,
                reason_en=body.reason_en,
                reason_ar=body.reason_ar,
                owner_key=owner,
                planned_unit_cost=None,
                capability_demand=None,
            )
        )

    _bind("", dashboard_workspace)
    _bind("/workspace", dashboard_workspace)
    _bind("/plans", dashboard_plans)
    _bind("/cycles", dashboard_plans)
    _bind("/plans", dashboard_create_plan, ("POST",))
    _bind("/plans/{plan_id}", dashboard_plan)
    _bind("/plans/{plan_id}/baseline", dashboard_baseline)
    _bind("/plans/{plan_id}/baseline", dashboard_freeze_baseline, ("POST",))
    _bind("/plans/{plan_id}/scenarios", dashboard_scenarios)
    _bind("/plans/{plan_id}/scenarios", dashboard_create_scenario, ("POST",))
    _bind("/plans/{plan_id}/revise", dashboard_revise, ("POST",))
    _bind("/scenarios/{scenario_id}/assumptions", dashboard_assumptions)
    _bind("/assumptions", dashboard_upsert_assumption, ("POST",))
    _bind("/demand", dashboard_demand)
    _bind("/demand", dashboard_add_demand, ("POST",))
    _bind("/scenarios/{scenario_id}/planned-positions", dashboard_planned_positions)
    _bind("/scenarios/{scenario_id}/projection", dashboard_projection)
    _bind("/scenarios/{scenario_id}/headcount", dashboard_projection)
    _bind("/scenarios/{scenario_id}/cost", dashboard_cost)
    _bind("/gaps", dashboard_compute_gap, ("POST",))
    _bind("/scenarios/{scenario_id}/gaps", dashboard_gaps)
    _bind("/compare", dashboard_compare, ("POST",))
    _bind("/plans/{plan_id}/submit", dashboard_submit, ("POST",))
    _bind("/approve", dashboard_approve, ("POST",))
    _bind("/plans/{plan_id}/approvals", dashboard_approvals)
    _bind("/handoffs", dashboard_handoff, ("POST",))
    _bind("/plans/{plan_id}/handoffs", dashboard_handoffs)
    _bind("/plans/{plan_id}/execution", dashboard_execution)
    _bind("/handoffs/{handoff_id}/cancel", dashboard_cancel_handoff, ("POST",))
    _bind("/actual-vs-plan", dashboard_actual_vs_plan)
    _bind("/history", dashboard_history)
    _bind("/plans/{plan_id}/export", dashboard_export)
    _bind("/assistant", dashboard_assistant, ("POST",))
    _bind("/manager", dashboard_manager)
    _bind("/manager/demand", dashboard_manager_demand, ("POST",))
