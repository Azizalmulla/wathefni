#!/usr/bin/env python3
"""HTTP adapters for Talent (R5C) — thin wrappers over frozen C5–C6.

Namespaces:
  /dashboard/posthire/talent/...
  /dashboard/talent/...          (alias)
  /app/talent/...

Company and actor identity come from authenticated context only.
Never collide with recruiting talent_pool.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import talent_evidence_index_pt1 as idx
import talent_models_pt2 as pt2
import talent_role_fit_pt3 as pt3
import talent_profile_c5 as c5
import talent_succession_c6 as c6
import talent_surfaces as surfaces

DASH_PREFIXES = ("/dashboard/posthire/talent", "/dashboard/talent")


class ReasonBody(BaseModel):
    reason: str = "talent action"
    expected_row_version: int | None = None


class ProfileBody(BaseModel):
    employee_key: str
    reason: str = "ensure talent profile"


class DimensionBody(BaseModel):
    employee_key: str
    dimension_kind: str
    title_en: str
    source: str = "hr_assessed"
    title_ar: str | None = None
    detail_en: str | None = None
    detail_ar: str | None = None
    visibility: str = "manager_visible"
    reason: str = "add talent evidence"


class AspirationBody(BaseModel):
    title_en: str
    title_ar: str | None = None
    detail_en: str | None = None
    reason: str = "employee career aspiration update"


class SkillBody(BaseModel):
    employee_key: str | None = None
    skill_code: str
    name_en: str
    name_ar: str | None = None
    proficiency_level: str | None = None
    reason: str = "claim skill"


class PotentialFrameworkBody(BaseModel):
    name_en: str
    dimensions: list[dict[str, Any]]
    scale_points: list[dict[str, Any]]
    name_ar: str | None = None
    reason: str = "create potential framework"


class PotentialSubmitBody(BaseModel):
    employee_key: str
    framework_id: str
    rationale: str
    dimension_scores: dict[str, Any]
    resulting_level: str | None = None
    assessor_role: str = "hr"
    performance_evidence_optional: dict[str, Any] | None = None
    reason: str = "submit potential assessment"


class PerformanceEvidenceBody(BaseModel):
    employee_key: str
    performance_subject_type: str
    performance_subject_id: str
    reason: str = "link performance evidence"


class OkrEvidenceIndexBody(BaseModel):
    objective_id: str | None = None
    key_result_id: str | None = None
    reason: str = "index okr evidence"


class TalentModelBody(BaseModel):
    name_en: str
    name_ar: str | None = None
    reason: str = "create talent model"


class TalentModelVersionBody(BaseModel):
    model_id: str
    derivation: str = "rules_v1"
    output_classifications: list[dict[str, Any]] | list[str] | None = None
    dimensions: list[dict[str, Any]] | None = None
    evidence_bindings: list[dict[str, Any]] | None = None
    thresholds: list[dict[str, Any]] | None = None
    eligibility: list[dict[str, Any]] | None = None
    rules: list[dict[str, Any]] | None = None
    weights: dict[str, Any] | None = None
    missing_data_policy: str = "insufficient"
    ai_narration: str = "forbidden"
    use_default_high_potential_signal: bool = False
    reason: str = "save draft model version"


class TalentModelEvaluateBody(BaseModel):
    employee_key: str
    model_id: str | None = None
    version_id: str | None = None
    reason: str = "evaluate talent model"


class RoleFitSetBody(BaseModel):
    name_en: str
    name_ar: str | None = None
    job_profile_id: str | None = None
    critical_role_id: str | None = None
    reason: str = "create role requirement set"


class RoleFitVersionBody(BaseModel):
    set_id: str
    requirements: list[dict[str, Any]]
    derivation: str = "rules_v1"
    readiness_rules: list[dict[str, Any]] | None = None
    weights: dict[str, Any] | None = None
    missing_data_policy: str = "insufficient"
    reason: str = "save draft requirement set"


class RoleFitEvaluateBody(BaseModel):
    employee_key: str
    set_id: str | None = None
    version_id: str | None = None
    reason: str = "evaluate role fit"


class RoleFitImportJaBody(BaseModel):
    job_profile_id: str
    name_en: str | None = None
    name_ar: str | None = None
    reason: str = "import JA requirements as draft"


class ReadinessBody(BaseModel):
    employee_key: str
    title_en: str
    source: str
    scope: str = "general"
    role_key: str | None = None
    reason: str = "add readiness observation"


class ReviewBody(BaseModel):
    name_en: str
    name_ar: str | None = None
    facilitator_phone: str | None = None
    reason: str = "create talent review"


class PrepareReviewBody(BaseModel):
    population: list[dict[str, Any]]
    potential_framework_id: str | None = None
    nine_box_config_id: str | None = None
    reason: str = "prepare talent review"


class HipoBody(BaseModel):
    employee_key: str
    status: str
    rationale: str
    talent_review_id: str | None = None
    nine_box_cell: str | None = None
    expected_row_version: int | None = None
    reason: str = "explicit HiPo decision"


class CriticalRoleBody(BaseModel):
    canonical_role_key: str
    title_en: str
    title_ar: str | None = None
    canonical_position_id: str | None = None
    org_unit_key: str | None = None
    reason: str = "designate critical role"


class PlanBody(BaseModel):
    critical_role_id: str
    reason: str = "create succession plan"


class NominateBody(BaseModel):
    employee_key: str
    rationale: str
    readiness: str = "unassessed"
    readiness_rationale: str | None = None
    expected_row_version: int | None = None
    create_development_for_gaps: bool = False
    development_plan_id: str | None = None
    reason: str = "nominate successor"


class NineBoxConfigBody(BaseModel):
    name_en: str
    performance_axis: dict[str, Any]
    potential_axis: dict[str, Any]
    thresholds: dict[str, Any]
    labels: dict[str, Any]
    name_ar: str | None = None
    reason: str = "create nine-box config"


class NineBoxProjectBody(BaseModel):
    config_id: str
    performance_value: Any = None
    potential_level: str | None = None


class MobilityPreferenceBody(BaseModel):
    title_en: str
    title_ar: str | None = None
    detail_en: str | None = None
    reason: str = "employee mobility preference"


_GATE_ERRORS = {
    "talent_kill_switch",
    "talent_profile_c5_off",
    "talent_succession_c6_off",
    "talent_profile_company_not_allowlisted",
    "talent_succession_company_not_allowlisted",
    "talent_profile_company_not_enabled",
    "talent_succession_company_not_enabled",
    "company_disabled",
    "entitlement_off",
    "talent_review_disabled",
    "hipo_disabled",
    "succession_disabled",
    "nine_box_disabled",
    "potential_disabled",
    "skills_disabled",
    "employee_career_self_service_disabled",
    "performance_evidence_consume_disabled",
}

_NOT_FOUND = {
    "profile_not_found",
    "talent_review_not_found",
    "succession_plan_not_found",
    "critical_role_not_found",
    "nine_box_config_not_found",
    "framework_not_found",
    "assessment_not_submittable",
    "skill_not_found",
}

_FORBIDDEN = {
    "permission_denied",
    "scope_denied",
    "sensitive_permission_required",
    "potential_hidden_from_employee",
    "hipo_hidden_from_employee",
    "succession_hidden_from_employee",
    "manager_out_of_scope",
    "manager_cannot_write_as_employee_declared",
    "facilitator_required",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "talent_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={"error": err, "message": "Talent is not enabled for this company.", "gate": result.get("gate")},
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted."})
    if err in {"concurrency_conflict", "stale_row_version"}:
        raise HTTPException(status_code=409, detail={"error": err, "message": "Stale row — refresh and retry."})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_talent_http(app_mod: Any) -> None:
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

    def _perms(context: dict[str, Any]) -> set[str]:
        return set(context_permissions(context, dashboard_context_role_key(context)) or [])

    def _role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or dashboard_context_role_key(context) or "").strip().lower()
        if role in {"owner", "hr_admin", "hr_manager", "admin"}:
            return "hr"
        if role in {"manager"}:
            return "manager"
        perms = _perms(context)
        if "talent.succession" in perms or "talent.review" in perms:
            if role != "manager":
                return "hr"
        return role or "hr"

    def _manager_keys(context: dict[str, Any], company: str) -> list[str] | None:
        if _role(context) != "manager":
            return None
        if not context_manager_employee_keys:
            return []
        keys = context_manager_employee_keys(context, company) or set()
        return sorted(str(item) for item in keys)

    def _sensitive(context: dict[str, Any]) -> bool:
        return "talent.sensitive" in _perms(context) or _role(context) == "hr" and "talent.sensitive" in _perms(context)

    def _can_succession(context: dict[str, Any]) -> bool:
        perms = _perms(context)
        return "talent.succession" in perms or (_role(context) == "hr" and "talent.manage" in perms and "talent.sensitive" in perms)

    def _can_review(context: dict[str, Any]) -> bool:
        perms = _perms(context)
        return "talent.review" in perms or (_role(context) == "hr" and "talent.manage" in perms)

    def _company(context: dict[str, Any], *, write: bool = False) -> str:
        company = posthire_context(context, "talent")
        perms = _perms(context)
        if write and not (
            {"talent.manage", "talent.review", "talent.succession", "talent.sensitive"} & perms
        ):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})
        gate = c5.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _assert_manager_scope(context: dict[str, Any], company: str, employee_key: str | None) -> None:
        keys = _manager_keys(context, company)
        if keys is None:
            return
        if not employee_key or employee_key not in keys:
            raise HTTPException(status_code=403, detail={"error": "scope_denied", "message": "Not permitted."})

    find_employee_by_phone = getattr(app_mod, "find_employee_by_phone", None)

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
                flow="talent",
                template_key=template_key,
                text=text,
                email_subject=subject,
                company_code=company,
                dedupe_key=f"talent:{template_key}:{company}:{key}",
            )
        except Exception:
            return

    def _run(callback: Any, *, employee_view: bool = False) -> Any:
        with db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.ensure_all_schemas(cur)
                result = callback(cur)
            conn.commit()
        if isinstance(result, dict) and result.get("ok") is False:
            _raise_gate(result)
        payload = json_safe(result)
        if employee_view:
            return json_safe(surfaces.strip_employee_judgments(payload))
        return payload

    def _bind(path: str, handler: Any, methods: tuple[str, ...] = ("GET",)) -> None:
        for prefix in DASH_PREFIXES:
            app.add_api_route(prefix + path, handler, methods=list(methods))

    def dashboard_workspace(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        role = _role(context)
        return _run(
            lambda cur: surfaces.workspace_summary(
                cur,
                company_code=company,
                actor_role=role,
                manager_scope_keys=_manager_keys(context, company),
                can_see_sensitive=_sensitive(context),
                can_see_succession=_can_succession(context),
            )
        )

    def dashboard_profiles(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_profiles(
                cur,
                company_code=company,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    def dashboard_ensure_profile(body: ProfileBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        return _run(
            lambda cur: c5.ensure_talent_profile(
                cur, company_code=company, employee_key=body.employee_key, actor_phone=str(context.get("actor_phone") or "")
            )
        )

    def dashboard_profile_detail(employee_key: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.get_profile_detail(
                cur,
                company_code=company,
                employee_key=employee_key,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
                can_see_sensitive=_sensitive(context),
                can_see_succession=_can_succession(context),
                include_history=True,
            )
        )

    def dashboard_add_fact(body: DimensionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        if body.source == "employee_declared" and _role(context) != "employee":
            raise HTTPException(status_code=403, detail={"error": "manager_cannot_write_as_employee_declared"})
        return _run(
            lambda cur: c5.add_dimension_fact(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                dimension_kind=body.dimension_kind,
                title_en=body.title_en,
                source=body.source,
                title_ar=body.title_ar,
                detail_en=body.detail_en,
                detail_ar=body.detail_ar,
                visibility=body.visibility,
                reason=body.reason,
            )
        )

    def dashboard_claim_skill(body: SkillBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        key = body.employee_key or ""
        _assert_manager_scope(context, company, key)
        return _run(
            lambda cur: c5.claim_skill(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=key,
                skill_code=body.skill_code,
                name_en=body.name_en,
                name_ar=body.name_ar,
                proficiency_level=body.proficiency_level,
                reason=body.reason,
            )
        )

    def dashboard_potential_frameworks(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        if not _sensitive(context):
            raise HTTPException(status_code=403, detail={"error": "sensitive_permission_required"})
        return _run(lambda cur: surfaces.list_potential_frameworks(cur, company_code=company))

    def dashboard_create_framework(body: PotentialFrameworkBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _sensitive(context):
            raise HTTPException(status_code=403, detail={"error": "sensitive_permission_required"})
        return _run(
            lambda cur: c5.create_potential_framework(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                name_en=body.name_en,
                dimensions=body.dimensions,
                scale_points=body.scale_points,
                name_ar=body.name_ar,
                reason=body.reason,
            )
        )

    def dashboard_submit_potential(body: PotentialSubmitBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        if not _sensitive(context):
            raise HTTPException(status_code=403, detail={"error": "sensitive_permission_required"})
        return _run(
            lambda cur: c5.submit_potential_assessment(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                framework_id=body.framework_id,
                rationale=body.rationale,
                dimension_scores=body.dimension_scores,
                resulting_level=body.resulting_level,
                assessor_role=body.assessor_role if _role(context) == "manager" else "hr",
                performance_evidence_optional=body.performance_evidence_optional,
                has_sensitive_permission=True,
                reason=body.reason,
            )
        )

    def dashboard_accept_potential(assessment_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _sensitive(context):
            raise HTTPException(status_code=403, detail={"error": "sensitive_permission_required"})
        return _run(
            lambda cur: c5.accept_potential_assessment(
                cur,
                company_code=company,
                assessment_id=assessment_id,
                actor_phone=str(context.get("actor_phone") or ""),
                reason=body.reason,
                has_sensitive_permission=True,
            )
        )

    def dashboard_link_perf(body: PerformanceEvidenceBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        return _run(
            lambda cur: c5.link_performance_evidence(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                performance_subject_type=body.performance_subject_type,
                performance_subject_id=body.performance_subject_id,
                reason=body.reason,
            )
        )

    def dashboard_readiness(body: ReadinessBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        return _run(
            lambda cur: c5.add_readiness_observation(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                title_en=body.title_en,
                source=body.source,
                scope=body.scope,
                role_key=body.role_key,
                reason=body.reason,
            )
        )

    def dashboard_reviews(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        if not _can_review(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(lambda cur: surfaces.list_reviews(cur, company_code=company))

    def dashboard_create_review(body: ReviewBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _can_review(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        result = _run(
            lambda cur: c6.create_talent_review(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                name_en=body.name_en,
                name_ar=body.name_ar,
                facilitator_phone=body.facilitator_phone,
                reason=body.reason,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            review = result.get("review") or {}
            _notify(
                company,
                template_key="talent_review_requested",
                text="A talent review is waiting for your participation.",
                subject="Talent review requested",
                phone=str(review.get("facilitator_phone") or body.facilitator_phone or ""),
            )
        return result

    def dashboard_review_detail(review_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        if not _can_review(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(lambda cur: surfaces.get_review_detail(cur, company_code=company, review_id=review_id))

    def dashboard_prepare_review(review_id: str, body: PrepareReviewBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _can_review(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: c6.prepare_talent_review(
                cur,
                company_code=company,
                review_id=review_id,
                actor_phone=str(context.get("actor_phone") or ""),
                population=body.population,
                potential_framework_id=body.potential_framework_id,
                nine_box_config_id=body.nine_box_config_id,
                reason=body.reason,
            )
        )

    def dashboard_start_review(review_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _can_review(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        result = _run(
            lambda cur: c6.start_talent_review(
                cur,
                company_code=company,
                review_id=review_id,
                actor_phone=str(context.get("actor_phone") or ""),
                reason=body.reason,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            review = result.get("review") or {}
            _notify(
                company,
                template_key="talent_review_requested",
                text="A talent review has started.",
                subject="Talent review requested",
                phone=str(review.get("facilitator_phone") or ""),
            )
        return result

    def dashboard_lock_review(review_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _can_review(context) or not _sensitive(context):
            raise HTTPException(status_code=403, detail={"error": "sensitive_permission_required"})
        return _run(
            lambda cur: c6.complete_and_lock_talent_review(
                cur,
                company_code=company,
                review_id=review_id,
                actor_phone=str(context.get("actor_phone") or ""),
                reason=body.reason,
                has_sensitive_permission=True,
            )
        )

    def dashboard_hipo(body: HipoBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        _assert_manager_scope(context, company, body.employee_key)
        if not _sensitive(context):
            raise HTTPException(status_code=403, detail={"error": "sensitive_permission_required"})
        return _run(
            lambda cur: c6.decide_hipo(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                status=body.status,
                rationale=body.rationale,
                talent_review_id=body.talent_review_id,
                nine_box_cell=body.nine_box_cell,
                expected_row_version=body.expected_row_version,
                has_sensitive_permission=True,
                reason=body.reason,
            )
        )

    def dashboard_succession(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        if not _can_succession(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(lambda cur: surfaces.list_succession(cur, company_code=company))

    def dashboard_critical_role(body: CriticalRoleBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _can_succession(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: c6.designate_critical_role(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                canonical_role_key=body.canonical_role_key,
                title_en=body.title_en,
                title_ar=body.title_ar,
                canonical_position_id=body.canonical_position_id,
                org_unit_key=body.org_unit_key,
                reason=body.reason,
            )
        )

    def dashboard_create_plan(body: PlanBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _can_succession(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        result = _run(
            lambda cur: c6.create_succession_plan(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                critical_role_id=body.critical_role_id,
                reason=body.reason,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            plan = result.get("plan") or {}
            _notify(
                company,
                template_key="talent_succession_review_required",
                text="A succession plan needs review.",
                subject="Succession review required",
                phone=str(plan.get("owner_phone") or context.get("actor_phone") or ""),
            )
        return result

    def dashboard_slate(plan_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        if not _can_succession(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(lambda cur: surfaces.get_slate(cur, company_code=company, plan_id=plan_id))

    def dashboard_nominate(plan_id: str, body: NominateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if not _can_succession(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        _assert_manager_scope(context, company, body.employee_key)
        result = _run(
            lambda cur: c6.nominate_successor(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                plan_id=plan_id,
                employee_key=body.employee_key,
                rationale=body.rationale,
                readiness=body.readiness,
                readiness_rationale=body.readiness_rationale,
                expected_row_version=body.expected_row_version,
                has_sensitive_permission=_sensitive(context) or _can_succession(context),
                create_development_for_gaps=body.create_development_for_gaps,
                development_plan_id=body.development_plan_id,
                reason=body.reason,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            # Ask the authorized manager/HR actor to continue — never tell the
            # nominee they are on a succession slate.
            _notify(
                company,
                template_key="talent_manager_nomination_requested",
                text="A succession nomination needs your review.",
                subject="Manager nomination requested",
                phone=str(context.get("actor_phone") or ""),
            )
        return result

    def dashboard_nine_box(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_nine_box_configs(cur, company_code=company))

    def dashboard_create_nine_box(body: NineBoxConfigBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr":
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: c6.create_nine_box_config(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                name_en=body.name_en,
                performance_axis=body.performance_axis,
                potential_axis=body.potential_axis,
                thresholds=body.thresholds,
                labels=body.labels,
                name_ar=body.name_ar,
                reason=body.reason,
            )
        )

    def dashboard_project_nine_box(body: NineBoxProjectBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.derive_nine_box(
                cur,
                company_code=company,
                config_id=body.config_id,
                performance_value=body.performance_value,
                potential_level=body.potential_level,
            )
        )

    def dashboard_mobility(employee_key: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _assert_manager_scope(context, company, employee_key)
        return _run(
            lambda cur: surfaces.mobility_surface(
                cur,
                company_code=company,
                employee_key=employee_key,
                actor_role=_role(context),
                can_see_sensitive=_sensitive(context),
            )
        )

    def dashboard_development(employee_key: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _assert_manager_scope(context, company, employee_key)
        return _run(lambda cur: surfaces.development_context(cur, company_code=company, employee_key=employee_key))

    def dashboard_evidence_index(employee_key: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _assert_manager_scope(context, company, employee_key)
        perms = _perms(context)
        return _run(
            lambda cur: idx.list_evidence(
                cur,
                company_code=company,
                employee_key=employee_key,
                actor_role=_role(context),
                has_talent_read="talent.read" in perms or "talent.manage" in perms or _role(context) == "hr",
                can_see_sensitive=_sensitive(context),
                can_see_performance="performance.read" in perms or "performance.manage" in perms,
            )
        )

    def dashboard_index_okr(body: OkrEvidenceIndexBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: idx.index_okr_evidence(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                objective_id=body.objective_id,
                key_result_id=body.key_result_id,
                reason=body.reason,
            )
        )

    def dashboard_history(employee_key: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.get_profile_detail(
                cur,
                company_code=company,
                employee_key=employee_key,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
                can_see_sensitive=_sensitive(context),
                can_see_succession=_can_succession(context),
                include_history=True,
            )
        )

    _bind("/workspace", dashboard_workspace)
    _bind("/profiles", dashboard_profiles)
    _bind("/profiles", dashboard_ensure_profile, ("POST",))
    _bind("/profiles/{employee_key}", dashboard_profile_detail)
    _bind("/profiles/{employee_key}/history", dashboard_history)
    _bind("/evidence", dashboard_add_fact, ("POST",))
    _bind("/skills", dashboard_claim_skill, ("POST",))
    _bind("/potential/frameworks", dashboard_potential_frameworks)
    _bind("/potential/frameworks", dashboard_create_framework, ("POST",))
    _bind("/potential/assessments", dashboard_submit_potential, ("POST",))
    _bind("/potential/assessments/{assessment_id}/accept", dashboard_accept_potential, ("POST",))
    _bind("/performance-evidence", dashboard_link_perf, ("POST",))
    _bind("/readiness", dashboard_readiness, ("POST",))
    _bind("/reviews", dashboard_reviews)
    _bind("/reviews", dashboard_create_review, ("POST",))
    _bind("/reviews/{review_id}", dashboard_review_detail)
    _bind("/reviews/{review_id}/prepare", dashboard_prepare_review, ("POST",))
    _bind("/reviews/{review_id}/start", dashboard_start_review, ("POST",))
    _bind("/reviews/{review_id}/lock", dashboard_lock_review, ("POST",))
    _bind("/hipo", dashboard_hipo, ("POST",))
    _bind("/succession", dashboard_succession)
    _bind("/critical-roles", dashboard_critical_role, ("POST",))
    _bind("/plans", dashboard_create_plan, ("POST",))
    _bind("/plans/{plan_id}", dashboard_slate)
    _bind("/plans/{plan_id}/nominations", dashboard_nominate, ("POST",))
    _bind("/nine-box", dashboard_nine_box)
    _bind("/nine-box", dashboard_create_nine_box, ("POST",))
    _bind("/nine-box/project", dashboard_project_nine_box, ("POST",))
    _bind("/mobility/{employee_key}", dashboard_mobility)
    _bind("/development/{employee_key}", dashboard_development)
    _bind("/evidence-index/{employee_key}", dashboard_evidence_index)
    _bind("/evidence-index/okr", dashboard_index_okr, ("POST",))

    def dashboard_models(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: pt2.list_models(cur, company_code=company))

    def dashboard_create_model(body: TalentModelBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: pt2.create_model(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                name_en=body.name_en,
                name_ar=body.name_ar,
                reason=body.reason,
            )
        )

    def dashboard_save_model_version(body: TalentModelVersionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        cfg = pt2.default_high_potential_signal_config() if body.use_default_high_potential_signal else {}
        return _run(
            lambda cur: pt2.save_draft_version(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                model_id=body.model_id,
                derivation=body.derivation or cfg.get("derivation") or "rules_v1",
                output_classifications=body.output_classifications or cfg.get("output_classifications"),
                dimensions=body.dimensions or cfg.get("dimensions"),
                evidence_bindings=body.evidence_bindings or cfg.get("evidence_bindings"),
                thresholds=body.thresholds or cfg.get("thresholds"),
                eligibility=body.eligibility or cfg.get("eligibility"),
                rules=body.rules or cfg.get("rules"),
                weights=body.weights if body.weights is not None else cfg.get("weights"),
                missing_data_policy=body.missing_data_policy or cfg.get("missing_data_policy") or "insufficient",
                ai_narration=body.ai_narration or cfg.get("ai_narration") or "forbidden",
                reason=body.reason,
            )
        )

    def dashboard_publish_model(version_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: pt2.publish_version(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                version_id=version_id,
                reason=body.reason,
            )
        )

    def dashboard_evaluate_model(body: TalentModelEvaluateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        return _run(
            lambda cur: pt2.evaluate_employee(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                model_id=body.model_id,
                version_id=body.version_id,
                can_see_performance="performance.read" in _perms(context) or "performance.manage" in _perms(context),
                can_see_sensitive=_sensitive(context),
                reason=body.reason,
            )
        )

    def dashboard_why(why_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: pt2.get_why(cur, company_code=company, why_id=why_id))

    def dashboard_classifications(model_id: str = "", classification: str = "", context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: pt2.list_classifications(
                cur,
                company_code=company,
                model_id=model_id or None,
                classification=classification or None,
            )
        )

    _bind("/models", dashboard_models)
    _bind("/models", dashboard_create_model, ("POST",))
    _bind("/models/versions", dashboard_save_model_version, ("POST",))
    _bind("/models/versions/{version_id}/publish", dashboard_publish_model, ("POST",))
    _bind("/models/evaluate", dashboard_evaluate_model, ("POST",))
    _bind("/models/why/{why_id}", dashboard_why)
    _bind("/models/classifications", dashboard_classifications)

    def dashboard_role_fit_sets(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: pt3.list_sets(cur, company_code=company))

    def dashboard_create_role_fit_set(body: RoleFitSetBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: pt3.create_requirement_set(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                name_en=body.name_en,
                name_ar=body.name_ar,
                job_profile_id=body.job_profile_id,
                critical_role_id=body.critical_role_id,
                reason=body.reason,
            )
        )

    def dashboard_save_role_fit_version(body: RoleFitVersionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: pt3.save_draft_version(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                set_id=body.set_id,
                requirements=body.requirements,
                derivation=body.derivation,
                readiness_rules=body.readiness_rules,
                weights=body.weights,
                missing_data_policy=body.missing_data_policy,
                reason=body.reason,
            )
        )

    def dashboard_publish_role_fit(version_id: str, body: ReasonBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: pt3.publish_version(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                version_id=version_id,
                reason=body.reason,
            )
        )

    def dashboard_evaluate_role_fit(body: RoleFitEvaluateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        return _run(
            lambda cur: pt3.evaluate_role_fit(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                set_id=body.set_id,
                version_id=body.version_id,
                can_see_sensitive=_sensitive(context),
                reason=body.reason,
            )
        )

    def dashboard_role_fit_evaluations(set_id: str = "", context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: pt3.list_evaluations(cur, company_code=company, set_id=set_id or None))

    def dashboard_import_ja_requirements(body: RoleFitImportJaBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        if _role(context) != "hr" and "talent.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied"})
        return _run(
            lambda cur: pt3.import_draft_from_ja(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                job_profile_id=body.job_profile_id,
                name_en=body.name_en,
                name_ar=body.name_ar,
                reason=body.reason,
            )
        )

    _bind("/role-fit/sets", dashboard_role_fit_sets)
    _bind("/role-fit/sets", dashboard_create_role_fit_set, ("POST",))
    _bind("/role-fit/sets/versions", dashboard_save_role_fit_version, ("POST",))
    _bind("/role-fit/sets/versions/{version_id}/publish", dashboard_publish_role_fit, ("POST",))
    _bind("/role-fit/evaluate", dashboard_evaluate_role_fit, ("POST",))
    _bind("/role-fit/evaluations", dashboard_role_fit_evaluations)
    _bind("/role-fit/import-ja", dashboard_import_ja_requirements, ("POST",))

    @app.get("/app/talent")
    def app_talent_workspace(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "talent", action="view")
        company = str(context.get("company_code") or "")
        employee_key = str(context.get("employee_key") or context.get("actor_employee_key") or "")
        gate = c5.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return _run(
            lambda cur: surfaces.employee_workspace(cur, company_code=company, employee_key=employee_key),
            employee_view=True,
        )

    @app.get("/app/talent/profile")
    def app_talent_profile(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "talent", action="view")
        company = str(context.get("company_code") or "")
        employee_key = str(context.get("employee_key") or context.get("actor_employee_key") or "")
        return _run(
            lambda cur: surfaces.get_profile_detail(
                cur,
                company_code=company,
                employee_key=employee_key,
                actor_role="employee",
                actor_employee_key=employee_key,
            ),
            employee_view=True,
        )

    @app.post("/app/talent/aspirations")
    def app_talent_aspiration(body: AspirationBody, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "talent", action="update")
        company = str(context.get("company_code") or "")
        employee_key = str(context.get("employee_key") or context.get("actor_employee_key") or "")
        return _run(
            lambda cur: c5.update_employee_aspiration(
                cur,
                company_code=company,
                employee_phone=str(context.get("actor_phone") or context.get("phone") or ""),
                employee_key=employee_key,
                title_en=body.title_en,
                title_ar=body.title_ar,
                detail_en=body.detail_en,
                reason=body.reason,
            ),
            employee_view=True,
        )

    @app.post("/app/talent/skills")
    def app_talent_skill(body: SkillBody, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "talent", action="update")
        company = str(context.get("company_code") or "")
        employee_key = str(context.get("employee_key") or context.get("actor_employee_key") or "")
        return _run(
            lambda cur: c5.claim_skill(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or context.get("phone") or ""),
                employee_key=employee_key,
                skill_code=body.skill_code,
                name_en=body.name_en,
                name_ar=body.name_ar,
                proficiency_level=body.proficiency_level,
                reason=body.reason,
            ),
            employee_view=True,
        )

    @app.post("/app/talent/mobility")
    def app_talent_mobility(body: MobilityPreferenceBody, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "talent", action="update")
        company = str(context.get("company_code") or "")
        employee_key = str(context.get("employee_key") or context.get("actor_employee_key") or "")
        result = _run(
            lambda cur: c5.add_dimension_fact(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or context.get("phone") or ""),
                employee_key=employee_key,
                dimension_kind="mobility_preference",
                title_en=body.title_en,
                title_ar=body.title_ar,
                detail_en=body.detail_en,
                source="employee_declared",
                visibility="employee_visible",
                reason=body.reason,
            ),
            employee_view=True,
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(
                company,
                employee_key,
                template_key="talent_mobility_action",
                text="Your mobility preference was saved.",
                subject="Mobility preference updated",
            )
        return result

    @app.get("/app/talent/mobility")
    def app_talent_mobility_get(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "talent", action="view")
        company = str(context.get("company_code") or "")
        employee_key = str(context.get("employee_key") or context.get("actor_employee_key") or "")
        return _run(
            lambda cur: surfaces.mobility_surface(
                cur, company_code=company, employee_key=employee_key, actor_role="employee"
            ),
            employee_view=True,
        )
