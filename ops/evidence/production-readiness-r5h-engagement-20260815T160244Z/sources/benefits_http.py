#!/usr/bin/env python3
"""HTTP adapters for Benefits (R5F) — thin wrappers over frozen Wave 6 C3.

Namespaces:
  /dashboard/benefits/...
  /dashboard/posthire/benefits/...  (alias)
  /app/benefits/...

Company and actor identity come from authenticated context only.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import benefits_administration_c3 as c3
import benefits_surfaces as surfaces

DASH_PREFIXES = ("/dashboard/benefits", "/dashboard/posthire/benefits")


class PlanBody(BaseModel):
    code: str
    category: str
    title_en: str
    title_ar: str
    status: str = "draft"
    provider_id: str | None = None
    policy_group_ref: str = ""
    tier_options: list[str] | None = None
    dependent_eligibility: dict[str, Any] | None = None
    contribution_policy: dict[str, Any] | None = None
    required_documents: list[str] | None = None
    description_en: str = ""
    description_ar: str = ""
    effective_start: str | None = None
    reason: str = "upsert plan"


class EligibilityRuleBody(BaseModel):
    plan_id: str
    code: str
    title_en: str
    title_ar: str
    criteria: dict[str, Any]
    rule_version: int = 1


class EvaluateBody(BaseModel):
    employee_key: str
    plan_id: str
    rule_id: str
    attributes: dict[str, Any] | None = None


class WindowBody(BaseModel):
    plan_id: str
    window_type: str
    starts_on: str
    ends_on: str
    window_version: int = 1


class StartEnrollmentBody(BaseModel):
    employee_key: str
    plan_id: str
    evaluation_id: str
    window_id: str | None = None
    source: str = "hr_admin"


class PrepareEnrollmentBody(BaseModel):
    employee_key: str
    plan_id: str
    attributes: dict[str, Any] | None = None
    window_id: str | None = None


class ElectBody(BaseModel):
    waive: bool = False
    tier: str | None = None
    reason: str = ""
    plan_id: str | None = None
    evaluation_id: str | None = None
    window_id: str | None = None
    attributes: dict[str, Any] | None = None
    enrollment_id: str | None = None


class ConfirmBody(BaseModel):
    coverage_start: str
    coverage_end: str | None = None
    provider_confirmed: bool = False


class DependentLinkBody(BaseModel):
    coverage_id: str
    dependent_id: str
    evidence_ref: str = ""


class ContributionBody(BaseModel):
    plan_id: str
    plan_version: int
    kind: str
    mode: str
    amount: float | None = None
    percent: float | None = None
    currency: str = "KWD"
    effective_start: str
    enrollment_id: str | None = None
    coverage_id: str | None = None


class HandoffBody(BaseModel):
    enrollment_id: str
    coverage_id: str | None = None
    employee_amount: float
    employer_amount: float
    period_start: str
    period_end: str | None = None
    component_mapping: dict[str, Any] | None = None


class MemberRefBody(BaseModel):
    enrollment_id: str | None = None
    coverage_id: str | None = None
    employee_key: str | None = None
    dependent_id: str | None = None
    policy_group_number: str = ""
    member_id: str = ""
    provider_status_confirmed: bool = False


class EvidenceBody(BaseModel):
    document_type: str
    shared_intake_ref: str


_GATE_ERRORS = {
    "benefits_c3_off",
    "benefits_company_not_allowlisted",
    "benefits_disabled_for_company",
    "employee_self_service_disabled",
    "payroll_handoff_disabled",
    "company_disabled",
    "entitlement_off",
}

_NOT_FOUND = {
    "plan_not_found",
    "enrollment_not_found",
    "coverage_not_found",
    "eligibility_rule_not_found",
    "window_not_found",
    "canonical_dependent_not_found",
    "evidence_request_not_found",
}

_FORBIDDEN = {
    "permission_denied",
    "scope_denied",
    "manager_private_detail_requires_explicit_ops_surface",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "benefits_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={"error": err, "message": "Benefits is not enabled for this company.", "gate": result.get("gate")},
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted."})
    if err in {"not_eligible", "enrollment_not_open", "enrollment_not_ready_to_confirm", "tier_required"}:
        raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_benefits_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    employee_app_context = app_mod.employee_app_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    posthire_context = app_mod._posthire_read_context
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key
    require_employee_app_feature = app_mod.require_employee_app_feature
    deliver_employee_notification = getattr(app_mod, "deliver_employee_notification", None)
    find_employee_by_key = getattr(app_mod, "find_employee_by_key", None)
    find_employee_by_phone = getattr(app_mod, "find_employee_by_phone", None)

    def _perms(context: dict[str, Any]) -> set[str]:
        return set(context_permissions(context, dashboard_context_role_key(context)) or [])

    def _role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or dashboard_context_role_key(context) or "").strip().lower()
        if role in {"owner", "hr_admin", "hr_manager", "admin"}:
            return "hr"
        if role in {"manager"}:
            return "manager"
        return role or "hr"

    def _company(context: dict[str, Any], *, write: bool = False, need: set[str] | None = None) -> str:
        if _role(context) == "manager":
            raise HTTPException(
                status_code=403,
                detail={"error": "permission_denied", "message": "Managers do not have a Benefits workspace."},
            )
        company = posthire_context(context, "benefits")
        perms = _perms(context)
        required = need or ({"benefits.manage", "benefits.enroll", "benefits.eligibility"} if write else set())
        if write and required and not (required & perms) and "benefits.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})
        gate = c3.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _require(context: dict[str, Any], perm: str) -> None:
        if perm not in _perms(context) and "benefits.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})

    def _maybe_strip(context: dict[str, Any], payload: Any) -> Any:
        if "benefits.sensitive" in _perms(context) or "benefits.manage" in _perms(context):
            return payload
        return json_safe(surfaces.strip_sensitive(payload))

    def _notify(
        company: str,
        employee_key: str = "",
        *,
        template_key: str,
        text: str,
        subject: str,
        phone: str | None = None,
    ) -> None:
        if not deliver_employee_notification:
            return
        employee = None
        if employee_key and find_employee_by_key:
            employee = find_employee_by_key(employee_key, company_code=company)
        if not employee and phone and find_employee_by_phone:
            employee = find_employee_by_phone(phone, company_code=company)
        if not employee:
            return
        key = str(employee.get("employee_key") or employee_key or phone or "unknown")
        try:
            deliver_employee_notification(
                employee,
                flow="benefits",
                template_key=template_key,
                text=text,
                email_subject=subject,
                company_code=company,
                dedupe_key=f"benefits:{template_key}:{company}:{key}",
            )
        except Exception:
            return

    def _run(callback: Any, *, employee_view: bool = False, context: dict[str, Any] | None = None) -> Any:
        with db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.ensure_schema(cur)
                result = callback(cur)
            conn.commit()
        if isinstance(result, dict) and result.get("ok") is False:
            _raise_gate(result)
        payload = json_safe(result)
        if employee_view:
            return json_safe(surfaces.strip_employee_admin(payload))
        if context is not None:
            return _maybe_strip(context, payload)
        return payload

    def _bind(path: str, handler: Any, methods: tuple[str, ...] = ("GET",)) -> None:
        for prefix in DASH_PREFIXES:
            app.add_api_route(prefix + path, handler, methods=list(methods))

    def dashboard_workspace(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.workspace_summary(cur, company_code=company), context=context)

    def dashboard_plans(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_plans(cur, company_code=company), context=context)

    def dashboard_upsert_plan(body: PlanBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.manage"})
        _require(context, "benefits.manage")
        return _run(
            lambda cur: c3.upsert_plan(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                code=body.code,
                category=body.category,
                title_en=body.title_en,
                title_ar=body.title_ar,
                status=body.status,
                provider_id=body.provider_id,
                policy_group_ref=body.policy_group_ref,
                tier_options=body.tier_options,
                dependent_eligibility=body.dependent_eligibility,
                contribution_policy=body.contribution_policy,
                required_documents=body.required_documents,
                description_en=body.description_en,
                description_ar=body.description_ar,
                effective_start=body.effective_start,
                reason=body.reason,
            ),
            context=context,
        )

    def dashboard_plan_versions(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_plan_versions(cur, company_code=company, plan_id=plan_id), context=context)

    def dashboard_eligibility(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_eligibility(cur, company_code=company), context=context)

    def dashboard_create_rule(body: EligibilityRuleBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.eligibility", "benefits.manage"})
        return _run(
            lambda cur: c3.create_eligibility_rule(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                plan_id=body.plan_id,
                code=body.code,
                title_en=body.title_en,
                title_ar=body.title_ar,
                criteria=body.criteria,
                rule_version=body.rule_version,
            ),
            context=context,
        )

    def dashboard_evaluate(body: EvaluateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.eligibility", "benefits.manage"})
        return _run(
            lambda cur: c3.evaluate_eligibility(
                cur,
                company_code=company,
                employee_key=body.employee_key,
                plan_id=body.plan_id,
                rule_id=body.rule_id,
                attributes=body.attributes,
            ),
            context=context,
        )

    def dashboard_windows(body: WindowBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.enroll", "benefits.manage"})
        result = _run(
            lambda cur: c3.open_enrollment_window(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                plan_id=body.plan_id,
                window_type=body.window_type,
                starts_on=body.starts_on,
                ends_on=body.ends_on,
                window_version=body.window_version,
            ),
            context=context,
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(
                company,
                template_key="benefits_window_opened",
                text="A benefits enrollment window is open.",
                subject="Benefits enrollment window",
            )
        return result

    def dashboard_enrollments(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_enrollments(cur, company_code=company), context=context)

    def dashboard_start(body: StartEnrollmentBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.enroll", "benefits.manage"})
        return _run(
            lambda cur: c3.start_enrollment(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                plan_id=body.plan_id,
                evaluation_id=body.evaluation_id,
                window_id=body.window_id,
                source=body.source,
            ),
            context=context,
        )

    def dashboard_prepare(body: PrepareEnrollmentBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.enroll", "benefits.eligibility", "benefits.manage"})
        result = _run(
            lambda cur: surfaces.prepare_enrollment(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                plan_id=body.plan_id,
                attributes=body.attributes,
                window_id=body.window_id,
            ),
            context=context,
        )
        if isinstance(result, dict) and result.get("ok") and result.get("enrollment"):
            _notify(
                company,
                body.employee_key,
                template_key="benefits_action_required",
                text="Action is required on your benefits enrollment.",
                subject="Benefits action required",
            )
        return result

    def dashboard_elect(enrollment_id: str, body: ElectBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.enroll", "benefits.manage"})
        result = _run(
            lambda cur: c3.elect_or_waive(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                enrollment_id=enrollment_id,
                waive=body.waive,
                tier=body.tier,
                reason=body.reason,
            ),
            context=context,
        )
        if isinstance(result, dict) and result.get("ok"):
            enr = result.get("enrollment") or {}
            _notify(
                company,
                str(enr.get("employee_key") or ""),
                template_key="benefits_election_processed" if not body.waive else "benefits_waiver_recorded",
                text="Your benefits election was recorded." if not body.waive else "Your benefits waiver was recorded.",
                subject="Benefits update",
            )
        return result

    def dashboard_confirm(enrollment_id: str, body: ConfirmBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.enroll", "benefits.manage"})
        result = _run(
            lambda cur: c3.confirm_enrollment(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                enrollment_id=enrollment_id,
                coverage_start=body.coverage_start,
                coverage_end=body.coverage_end,
                provider_confirmed=body.provider_confirmed,
            ),
            context=context,
        )
        if isinstance(result, dict) and result.get("ok"):
            enr = result.get("enrollment") or {}
            _notify(
                company,
                str(enr.get("employee_key") or ""),
                template_key="benefits_coverage_effective",
                text="Your benefits coverage is now effective.",
                subject="Benefits coverage",
            )
        return result

    def dashboard_waivers(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_waivers(cur, company_code=company), context=context)

    def dashboard_coverage(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_coverage(cur, company_code=company), context=context)

    def dashboard_dependents(employee_key: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_dependents_for_coverage(cur, company_code=company, employee_key=employee_key),
            context=context,
        )

    def dashboard_link_dependent(body: DependentLinkBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.enroll", "benefits.manage"})
        return _run(
            lambda cur: c3.link_dependent_coverage(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                coverage_id=body.coverage_id,
                dependent_id=body.dependent_id,
                evidence_ref=body.evidence_ref,
            ),
            context=context,
        )

    def dashboard_contributions(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "benefits.sensitive")
        return _run(lambda cur: surfaces.list_contributions(cur, company_code=company), context=context)

    def dashboard_define_contrib(body: ContributionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.sensitive", "benefits.manage"})
        return _run(
            lambda cur: c3.define_contribution(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                plan_id=body.plan_id,
                plan_version=body.plan_version,
                kind=body.kind,
                mode=body.mode,
                amount=body.amount,
                percent=body.percent,
                currency=body.currency,
                effective_start=body.effective_start,
                enrollment_id=body.enrollment_id,
                coverage_id=body.coverage_id,
            ),
            context=context,
        )

    def dashboard_handoffs(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "benefits.sensitive")
        return _run(lambda cur: surfaces.list_handoffs(cur, company_code=company), context=context)

    def dashboard_create_handoff(body: HandoffBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.sensitive", "benefits.manage"})
        return _run(
            lambda cur: c3.create_payroll_handoff(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                enrollment_id=body.enrollment_id,
                coverage_id=body.coverage_id,
                employee_amount=body.employee_amount,
                employer_amount=body.employer_amount,
                period_start=body.period_start,
                period_end=body.period_end,
                component_mapping=body.component_mapping,
            ),
            context=context,
        )

    def dashboard_members(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "benefits.sensitive")
        return _run(lambda cur: surfaces.list_member_refs(cur, company_code=company), context=context)

    def dashboard_set_member(body: MemberRefBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.sensitive", "benefits.manage"})
        return _run(
            lambda cur: c3.set_provider_member_ref(
                cur,
                company_code=company,
                enrollment_id=body.enrollment_id,
                coverage_id=body.coverage_id,
                employee_key=body.employee_key,
                dependent_id=body.dependent_id,
                policy_group_number=body.policy_group_number,
                member_id=body.member_id,
                provider_status_confirmed=body.provider_status_confirmed,
            ),
            context=context,
        )

    def dashboard_history(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_history(cur, company_code=company), context=context)

    def dashboard_evidence(enrollment_id: str, body: EvidenceBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"benefits.enroll", "benefits.manage"})
        return _run(
            lambda cur: c3.submit_evidence(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                enrollment_id=enrollment_id,
                document_type=body.document_type,
                shared_intake_ref=body.shared_intake_ref,
            ),
            context=context,
        )

    _bind("/workspace", dashboard_workspace)
    _bind("/plans", dashboard_plans)
    _bind("/plans", dashboard_upsert_plan, ("POST",))
    _bind("/plans/{plan_id}/versions", dashboard_plan_versions)
    _bind("/eligibility", dashboard_eligibility)
    _bind("/eligibility/rules", dashboard_create_rule, ("POST",))
    _bind("/eligibility/evaluate", dashboard_evaluate, ("POST",))
    _bind("/windows", dashboard_windows, ("POST",))
    _bind("/enrollments", dashboard_enrollments)
    _bind("/enrollments", dashboard_start, ("POST",))
    _bind("/enrollments/prepare", dashboard_prepare, ("POST",))
    _bind("/enrollments/{enrollment_id}/elect", dashboard_elect, ("POST",))
    _bind("/enrollments/{enrollment_id}/confirm", dashboard_confirm, ("POST",))
    _bind("/enrollments/{enrollment_id}/evidence", dashboard_evidence, ("POST",))
    _bind("/waivers", dashboard_waivers)
    _bind("/coverage", dashboard_coverage)
    _bind("/dependents/{employee_key}", dashboard_dependents)
    _bind("/dependents/link", dashboard_link_dependent, ("POST",))
    _bind("/contributions", dashboard_contributions)
    _bind("/contributions", dashboard_define_contrib, ("POST",))
    _bind("/handoffs", dashboard_handoffs)
    _bind("/handoffs", dashboard_create_handoff, ("POST",))
    _bind("/members", dashboard_members)
    _bind("/members", dashboard_set_member, ("POST",))
    _bind("/history", dashboard_history)

    def _employee_key(context: dict[str, Any]) -> str:
        return str(context.get("employee_key") or context.get("actor_employee_key") or "")

    @app.get("/app/benefits")
    def app_benefits_workspace(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "benefits", action="view")
        company = str(context.get("company_code") or "")
        gate = c3.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return _run(
            lambda cur: surfaces.employee_workspace(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.get("/app/benefits/plans")
    def app_benefits_plans(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "benefits", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.list_plans(cur, company_code=company, published_only=True),
            employee_view=True,
        )

    @app.get("/app/benefits/plans/{plan_id}")
    def app_benefits_plan_detail(plan_id: str, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "benefits", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.employee_plan_detail(
                cur,
                company_code=company,
                employee_key=_employee_key(context),
                plan_id=plan_id,
            ),
            employee_view=True,
        )

    @app.get("/app/benefits/dependents")
    def app_benefits_dependents(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "benefits", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.list_dependents_for_coverage(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.get("/app/benefits/coverage")
    def app_benefits_coverage(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "benefits", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.list_coverage(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.get("/app/benefits/history")
    def app_benefits_history(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "benefits", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.list_history(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.post("/app/benefits/elections")
    def app_benefits_elect(body: ElectBody, context: dict[str, Any] = Depends(employee_app_context)):
        action = "waive" if body.waive else "enroll"
        require_employee_app_feature(context, "benefits", action=action)
        company = str(context.get("company_code") or "")
        employee_key = _employee_key(context)
        if not body.plan_id and not body.enrollment_id:
            raise HTTPException(status_code=422, detail={"error": "plan_or_enrollment_required"})
        result = _run(
            lambda cur: surfaces.employee_elect_or_waive(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or context.get("phone") or ""),
                employee_key=employee_key,
                plan_id=str(body.plan_id or ""),
                waive=body.waive,
                tier=body.tier,
                reason=body.reason,
                evaluation_id=body.evaluation_id,
                window_id=body.window_id,
                attributes=body.attributes,
                enrollment_id=body.enrollment_id,
            ),
            employee_view=True,
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(
                company,
                employee_key,
                template_key="benefits_waiver_recorded" if body.waive else "benefits_election_processed",
                text="Your benefits waiver was recorded." if body.waive else "Your benefits election was recorded.",
                subject="Benefits update",
                phone=str(context.get("actor_phone") or context.get("phone") or ""),
            )
        return result
