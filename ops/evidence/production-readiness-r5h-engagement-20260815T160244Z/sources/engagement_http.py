#!/usr/bin/env python3
"""HTTP adapters for Engagement (R5H) — thin wrappers over frozen Wave 6 C5.

Namespaces:
  /dashboard/engagement/...
  /dashboard/posthire/engagement/...  (alias)
  /app/engagement/...

Company and actor identity come from authenticated context only.
Managers receive threshold-safe aggregates only — not survey administration.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import engagement_c5 as c5
import engagement_surfaces as surfaces

DASH_PREFIXES = ("/dashboard/engagement", "/dashboard/posthire/engagement")


class SurveyBody(BaseModel):
    code: str
    title_en: str
    title_ar: str


class VersionBody(BaseModel):
    survey_id: str
    version_no: int = 1
    privacy_mode: str = "anonymous"
    questions: list[dict[str, Any]]
    min_responses: int | None = None
    visibility: str = "hr_and_managers_threshold"


class CampaignBody(BaseModel):
    survey_id: str
    survey_version_id: str
    title_en: str
    title_ar: str
    audience_employee_keys: list[str]
    audience_rule: dict[str, Any] | None = None
    opens_at: str | None = None
    closes_at: str | None = None


class ActionPlanBody(BaseModel):
    campaign_id: str
    title_en: str
    title_ar: str
    source_result_ref: str
    owner_key: str
    actions: list[dict[str, Any]] | None = None


class SubmitBody(BaseModel):
    answers: list[dict[str, Any]]


class AssistantBody(BaseModel):
    question_kind: str
    campaign_id: str | None = None
    employee_key: str | None = None


class ResolveBody(BaseModel):
    employee_key: str


_GATE_ERRORS = {
    "engagement_c5_off",
    "engagement_company_not_allowlisted",
    "engagement_disabled_for_company",
    "employee_survey_disabled",
    "action_plans_disabled",
    "manager_results_disabled",
    "company_disabled",
    "entitlement_off",
}

_NOT_FOUND = {
    "campaign_not_found",
    "survey_version_not_found",
    "not_in_audience",
}

_FORBIDDEN = {
    "permission_denied",
    "scope_denied",
    "anonymous_respondent_answer_map_unavailable",
    "manager_cannot_see_raw_anonymous_answers",
    "free_text_access_denied",
    "hr_cannot_edit_employee_response",
    "mutation_or_privacy_forbidden",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "engagement_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "Engagement is not enabled for this company.",
                "gate": result.get("gate"),
                "resource_state": "unavailable",
            },
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted.", "resource_state": "forbidden"})
    if err in {"already_submitted_immutable", "campaign_not_open", "campaign_not_draft", "threshold_upward_only", "enps_requires_0_to_10_scale", "not_enps_question", "invalid_privacy_mode", "invalid_question_type", "audience_required", "questions_required", "ungoverned_segment_dimension"}:
        raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_engagement_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    employee_app_context = app_mod.employee_app_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    posthire_context = app_mod._posthire_read_context
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key
    require_employee_app_feature = app_mod.require_employee_app_feature
    require_entitlement = app_mod.require_entitlement
    deliver_employee_notification = getattr(app_mod, "deliver_employee_notification", None)
    find_employee_by_key = getattr(app_mod, "find_employee_by_key", None)
    find_employee_by_phone = getattr(app_mod, "find_employee_by_phone", None)
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

    def _company(context: dict[str, Any], *, write: bool = False, need: set[str] | None = None) -> str:
        if _role(context) == "manager":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "permission_denied",
                    "message": "Managers do not have an Engagement administration workspace.",
                    "resource_state": "forbidden",
                },
            )
        company = posthire_context(context, "engagement")
        perms = _perms(context)
        required = need or ({"engagement.manage", "engagement.launch"} if write else set())
        if write and required and not (required & perms) and "engagement.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        gate = c5.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _require(context: dict[str, Any], perm: str) -> None:
        if perm not in _perms(context) and "engagement.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})

    def _manager_keys(context: dict[str, Any], company: str) -> list[str]:
        if not context_manager_employee_keys:
            return []
        keys = context_manager_employee_keys(context, company) or set()
        return sorted(str(item) for item in keys)

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
                flow="engagement",
                template_key=template_key,
                text=text,
                email_subject=subject,
                company_code=company,
                dedupe_key=f"engagement:{template_key}:{company}:{key}",
            )
        except Exception:
            return

    def _run(callback: Any, *, employee_view: bool = False) -> Any:
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
        return payload

    def _bind(path: str, handler: Any, methods: tuple[str, ...] = ("GET",)) -> None:
        for prefix in DASH_PREFIXES:
            app.add_api_route(prefix + path, handler, methods=list(methods))

    def dashboard_workspace(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.workspace_summary(cur, company_code=company))

    def dashboard_surveys(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_surveys(cur, company_code=company))

    def dashboard_create_survey(body: SurveyBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"engagement.manage"})
        _require(context, "engagement.manage")
        return _run(
            lambda cur: c5.create_survey_template(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                code=body.code,
                title_en=body.title_en,
                title_ar=body.title_ar,
            )
        )

    def dashboard_versions(survey_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_versions(cur, company_code=company, survey_id=survey_id))

    def dashboard_create_version(body: VersionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"engagement.manage"})
        _require(context, "engagement.manage")
        return _run(
            lambda cur: c5.create_survey_version(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                survey_id=body.survey_id,
                version_no=body.version_no,
                privacy_mode=body.privacy_mode,
                questions=body.questions,
                min_responses=body.min_responses,
                visibility=body.visibility,
            )
        )

    def dashboard_campaigns(status: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_campaigns(cur, company_code=company, status=status))

    def dashboard_create_campaign(body: CampaignBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"engagement.manage"})
        _require(context, "engagement.manage")
        return _run(
            lambda cur: c5.create_campaign(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                survey_id=body.survey_id,
                survey_version_id=body.survey_version_id,
                title_en=body.title_en,
                title_ar=body.title_ar,
                audience_rule=body.audience_rule or {},
                audience_employee_keys=body.audience_employee_keys,
                opens_at=body.opens_at,
                closes_at=body.closes_at,
            )
        )

    def dashboard_campaign(campaign_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.campaign_detail(cur, company_code=company, campaign_id=campaign_id))

    def dashboard_launch(campaign_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"engagement.launch", "engagement.manage"})
        result = _run(
            lambda cur: c5.launch_campaign(
                cur, company_code=company, actor_phone=_phone(context), campaign_id=campaign_id
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            pop = _run(lambda cur: c5.campaign_population(cur, company_code=company, campaign_id=campaign_id))
            for key in (pop.get("employee_keys") or []) if isinstance(pop, dict) else []:
                _notify(
                    company,
                    str(key),
                    template_key="engagement_survey_opened",
                    text="An Engagement survey is open.",
                    subject="Engagement survey",
                )
        return result

    def dashboard_close(campaign_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"engagement.launch", "engagement.manage"})
        return _run(
            lambda cur: c5.close_campaign(
                cur, company_code=company, actor_phone=_phone(context), campaign_id=campaign_id
            )
        )

    def dashboard_audience(campaign_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: c5.campaign_population(cur, company_code=company, campaign_id=campaign_id))

    def dashboard_participation(campaign_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.participation_status(cur, company_code=company, campaign_id=campaign_id))

    def dashboard_results(
        campaign_id: str,
        department: str | None = None,
        location: str | None = None,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        segment = {}
        if department:
            segment["department"] = department
        if location:
            segment["location"] = location
        return _run(
            lambda cur: surfaces.campaign_results(
                cur,
                company_code=company,
                campaign_id=campaign_id,
                segment=segment or None,
                actor_role="engagement_admin",
            )
        )

    def dashboard_segments(campaign_id: str, dimension: str = "department", context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.segment_breakdown(
                cur, company_code=company, campaign_id=campaign_id, dimension=dimension
            )
        )

    def dashboard_enps(campaign_id: str, question_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: c5.compute_enps(
                cur, company_code=company, campaign_id=campaign_id, question_id=question_id
            )
        )

    def dashboard_free_text(campaign_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "engagement.manage")
        return _run(
            lambda cur: c5.free_text_access(
                cur, company_code=company, campaign_id=campaign_id, actor_role="engagement_admin"
            )
        )

    def dashboard_resolve(campaign_id: str, body: ResolveBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.refuse_admin_answer_map(
                cur, company_code=company, campaign_id=campaign_id, employee_key=body.employee_key
            )
        )

    def dashboard_action_plans(campaign_id: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_action_plans(cur, company_code=company, campaign_id=campaign_id))

    def dashboard_create_action_plan(body: ActionPlanBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"engagement.actions", "engagement.manage"})
        result = _run(
            lambda cur: c5.create_action_plan(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                campaign_id=body.campaign_id,
                title_en=body.title_en,
                title_ar=body.title_ar,
                source_result_ref=body.source_result_ref,
                owner_key=body.owner_key,
                actions=body.actions,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(
                company,
                body.owner_key,
                template_key="engagement_action_plan",
                text="An Engagement action plan requires your attention.",
                subject="Engagement action plan",
            )
        return result

    def dashboard_history(campaign_id: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_history(cur, company_code=company, campaign_id=campaign_id))

    def dashboard_export(campaign_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "engagement.export")
        return _run(lambda cur: surfaces.export_results(cur, company_code=company, campaign_id=campaign_id))

    def dashboard_assistant(body: AssistantBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.assistant_query(
                cur,
                company_code=company,
                actor=_phone(context),
                question_kind=body.question_kind,
                campaign_id=body.campaign_id,
                employee_key=body.employee_key,
            )
        )

    def dashboard_manager(campaign_id: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        if _role(context) != "manager" and "engagement.manager" not in _perms(context) and "engagement.read" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        require_entitlement(context, "engagement")
        company = str(context.get("company_code") or "").upper()
        if "engagement.manager" not in _perms(context) and _role(context) != "manager" and "engagement.read" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        if _role(context) == "manager" and "engagement.manager" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted.", "resource_state": "forbidden"})
        gate = c5.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        keys = _manager_keys(context, company) if _role(context) == "manager" else None
        if _role(context) == "manager":
            return _run(
                lambda cur: surfaces.manager_aggregates(
                    cur,
                    company_code=company,
                    manager_scope_employee_keys=keys,
                    campaign_id=campaign_id,
                )
            )
        return _run(
            lambda cur: surfaces.manager_aggregates(
                cur,
                company_code=company,
                manager_scope_employee_keys=keys or [],
                campaign_id=campaign_id,
            )
        )

    _bind("", dashboard_workspace)
    _bind("/workspace", dashboard_workspace)
    _bind("/surveys", dashboard_surveys)
    _bind("/surveys", dashboard_create_survey, ("POST",))
    _bind("/surveys/{survey_id}/versions", dashboard_versions)
    _bind("/versions", dashboard_create_version, ("POST",))
    _bind("/campaigns", dashboard_campaigns)
    _bind("/campaigns", dashboard_create_campaign, ("POST",))
    _bind("/campaigns/{campaign_id}", dashboard_campaign)
    _bind("/campaigns/{campaign_id}/launch", dashboard_launch, ("POST",))
    _bind("/campaigns/{campaign_id}/close", dashboard_close, ("POST",))
    _bind("/campaigns/{campaign_id}/audience", dashboard_audience)
    _bind("/campaigns/{campaign_id}/participation", dashboard_participation)
    _bind("/campaigns/{campaign_id}/results", dashboard_results)
    _bind("/campaigns/{campaign_id}/segments", dashboard_segments)
    _bind("/campaigns/{campaign_id}/enps/{question_id}", dashboard_enps)
    _bind("/campaigns/{campaign_id}/free-text", dashboard_free_text)
    _bind("/campaigns/{campaign_id}/resolve", dashboard_resolve, ("POST",))
    _bind("/action-plans", dashboard_action_plans)
    _bind("/action-plans", dashboard_create_action_plan, ("POST",))
    _bind("/history", dashboard_history)
    _bind("/campaigns/{campaign_id}/export", dashboard_export)
    _bind("/assistant", dashboard_assistant, ("POST",))
    _bind("/manager", dashboard_manager)

    def _employee_key(context: dict[str, Any]) -> str:
        return str(context.get("employee_key") or context.get("actor_employee_key") or "")

    @app.get("/app/engagement")
    def app_engagement_workspace(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "engagement", action="view")
        company = str(context.get("company_code") or "")
        gate = c5.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return _run(
            lambda cur: surfaces.employee_workspace(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.get("/app/engagement/surveys/{campaign_id}")
    def app_engagement_detail(campaign_id: str, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "engagement", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.employee_survey_detail(
                cur,
                company_code=company,
                employee_key=_employee_key(context),
                campaign_id=campaign_id,
            ),
            employee_view=True,
        )

    @app.post("/app/engagement/surveys/{campaign_id}/start")
    def app_engagement_start(campaign_id: str, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "engagement", action="submit")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.employee_start(
                cur,
                company_code=company,
                employee_key=_employee_key(context),
                campaign_id=campaign_id,
            ),
            employee_view=True,
        )

    @app.post("/app/engagement/surveys/{campaign_id}/submit")
    def app_engagement_submit(campaign_id: str, body: SubmitBody, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "engagement", action="submit")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.employee_submit(
                cur,
                company_code=company,
                employee_key=_employee_key(context),
                campaign_id=campaign_id,
                answers=body.answers,
            ),
            employee_view=True,
        )
