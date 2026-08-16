#!/usr/bin/env python3
"""HTTP adapters for Employee Relations (R5G) — thin wrappers over frozen Wave 6 C4.

Namespaces:
  /dashboard/employee-relations/...
  /dashboard/posthire/employee-relations/...  (alias)
  /dashboard/mobile/employee-relations/...

No Employee App case-management workspace.
Company and actor identity come from authenticated context only.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import employee_relations_c4 as c4
import employee_relations_surfaces as surfaces

DASH_PREFIXES = ("/dashboard/employee-relations", "/dashboard/posthire/employee-relations")
MOBILE_PREFIX = "/dashboard/mobile/employee-relations"

_GATE_ERRORS = {
    "employee_relations_c4_off",
    "employee_relations_company_not_allowlisted",
    "employee_relations_disabled_for_company",
    "company_disabled",
    "entitlement_off",
    "module_disabled",
}

_NOT_FOUND = {
    "case_not_found",
    "case_type_not_found",
    "evidence_not_found",
    "case_not_found_or_forbidden",
}

_FORBIDDEN = {
    "er_access_denied",
    "permission_denied",
    "sensitive_evidence_denied",
    "employee_denied_internal",
    "role_cannot_hold_sensitive_evidence",
    "reopen_requires_governed_authority",
}


class IntakeBody(BaseModel):
    case_type_id: str
    subject_employee_key: str
    intake_source: str = "hr_created"
    reporter_employee_key: str | None = None
    summary_en: str = ""
    summary_ar: str = ""
    severity: str = "medium"
    due_date: str | None = None
    allegation_en: str = ""
    allegation_ar: str = ""


class TriageBody(BaseModel):
    reason: str = "triage"


class AssignBody(BaseModel):
    investigator_key: str


class GrantBody(BaseModel):
    actor_key: str
    actor_role: str
    permissions: list[str]


class NoteBody(BaseModel):
    body_en: str
    body_ar: str = ""


class EvidenceBody(BaseModel):
    shared_document_ref: str
    label_en: str = ""
    label_ar: str = ""
    sensitive: bool = True


class FindingBody(BaseModel):
    findings_en: str
    findings_ar: str = ""
    lock: bool = True


class OutcomeBody(BaseModel):
    outcome_code: str
    summary_en: str = ""
    summary_ar: str = ""


class ClosureBody(BaseModel):
    reason: str = "closure"


class HandoffBody(BaseModel):
    outcome_id: str
    handoff_payload: dict[str, Any] | None = None


class ContributionBody(BaseModel):
    body_en: str = ""
    body_ar: str = ""


class CaseTypeBody(BaseModel):
    code: str
    title_en: str
    title_ar: str
    type_version: int = 1
    confidentiality_default: str = "standard_er"
    allowed_outcomes: list[str] | None = None


class AssistantBody(BaseModel):
    question_kind: str
    case_id: str | None = None


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "employee_relations_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "Employee Relations is not enabled for this company.",
                "gate": result.get("gate"),
                "resource_state": "unavailable",
            },
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(
            status_code=403,
            detail={
                "error": err,
                "message": "You do not have access to this Employee Relations record.",
                "case_level_need_to_know": True,
                "resource_state": "forbidden",
            },
        )
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_employee_relations_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key
    require_entitlement = app_mod.require_entitlement
    deliver_employee_notification = getattr(app_mod, "deliver_employee_notification", None)
    find_employee_by_key = getattr(app_mod, "find_employee_by_key", None)
    find_employee_by_phone = getattr(app_mod, "find_employee_by_phone", None)

    def _perms(context: dict[str, Any]) -> set[str]:
        return set(context_permissions(context, dashboard_context_role_key(context)) or [])

    def _role(context: dict[str, Any]) -> str:
        return str(context.get("actor_role") or dashboard_context_role_key(context) or "").strip().lower()

    def _actor_key(context: dict[str, Any]) -> str:
        return surfaces.actor_key_from_context(context)

    def _actor_role(context: dict[str, Any]) -> str:
        return surfaces.map_actor_role(dashboard_role=_role(context), permissions=_perms(context))

    def _phone(context: dict[str, Any]) -> str:
        return str(context.get("actor_phone") or context.get("phone") or context.get("hr_phone") or "")

    def _forbid_manager_workspace() -> None:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "permission_denied",
                "message": "Managers do not have an Employee Relations workspace.",
                "manager_not_er": True,
                "resource_state": "forbidden",
            },
        )

    def _company(context: dict[str, Any], *, need: set[str] | None = None, allow_manager: bool = False) -> str:
        if _role(context) == "manager" and not allow_manager:
            _forbid_manager_workspace()
        require_entitlement(context, "employee_relations")
        perms = _perms(context)
        if not surfaces.has_workspace_authority(perms):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "permission_denied",
                    "message": "You do not have Employee Relations authority.",
                    "ordinary_hr_not_er": True,
                    "resource_state": "forbidden",
                },
            )
        required = need or set()
        if required and not (required & perms) and "er.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})
        company = str(context.get("company_code") or "").strip().upper()
        gate = c4.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _require(context: dict[str, Any], perm: str) -> None:
        if perm not in _perms(context) and "er.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})

    def _notify(company: str, employee_key: str = "", *, template_key: str, phone: str | None = None) -> None:
        if not deliver_employee_notification:
            return
        copy = surfaces.privacy_safe_notification(template_key=template_key)
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
                flow="employee_relations",
                template_key=template_key,
                text=copy["text"],
                email_subject=copy["subject"],
                company_code=company,
                dedupe_key=f"er:{template_key}:{company}:{key}",
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
        return json_safe(surfaces.strip_raw_urls(result))

    def _bind(path: str, handler: Any, methods: tuple[str, ...] = ("GET",)) -> None:
        for prefix in DASH_PREFIXES:
            app.add_api_route(prefix + path, handler, methods=list(methods))

    def dashboard_workspace(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.workspace_summary(
                cur, company_code=company, actor_key=_actor_key(context), actor_role=_actor_role(context)
            )
        )

    def dashboard_cases(status: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_cases(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                status=status,
            )
        )

    def dashboard_my_work(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_cases(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
            )
        )

    def dashboard_case_types(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_case_types(cur, company_code=company))

    def dashboard_upsert_case_type(body: CaseTypeBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.manage"})
        return _run(
            lambda cur: c4.upsert_case_type(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                code=body.code,
                title_en=body.title_en,
                title_ar=body.title_ar,
                type_version=body.type_version,
                confidentiality_default=body.confidentiality_default,
                allowed_outcomes=body.allowed_outcomes,
            )
        )

    def dashboard_case_detail(case_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.case_detail(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
            )
        )

    def dashboard_intake(body: IntakeBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.manage", "er.investigate"})
        result = _run(
            lambda cur: surfaces.intake_case(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_type_id=body.case_type_id,
                subject_employee_key=body.subject_employee_key,
                intake_source=body.intake_source,
                reporter_employee_key=body.reporter_employee_key,
                summary_en=body.summary_en,
                summary_ar=body.summary_ar,
                severity=body.severity,
                due_date=body.due_date,
                allegation_en=body.allegation_en,
                allegation_ar=body.allegation_ar,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(company, body.subject_employee_key, template_key="er_case_opened")
        return result

    def dashboard_triage(case_id: str, body: TriageBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.manage"})
        return _run(
            lambda cur: surfaces.triage_case(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                reason=body.reason,
            )
        )

    def dashboard_assign(case_id: str, body: AssignBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.manage"})
        result = _run(
            lambda cur: surfaces.assign_investigator(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                investigator_key=body.investigator_key,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(company, body.investigator_key, template_key="er_case_assigned", phone=body.investigator_key)
        return result

    def dashboard_grant(case_id: str, body: GrantBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.manage"})
        return _run(
            lambda cur: surfaces.grant_access(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                case_id=case_id,
                target_actor_key=body.actor_key,
                target_actor_role=body.actor_role,
                permissions=body.permissions,
            )
        )

    def dashboard_notes(case_id: str, body: NoteBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.investigate", "er.manage"})
        return _run(
            lambda cur: surfaces.add_note(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                body_en=body.body_en,
                body_ar=body.body_ar,
            )
        )

    def dashboard_evidence(case_id: str, body: EvidenceBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.investigate", "er.manage"})
        return _run(
            lambda cur: surfaces.attach_evidence(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                shared_document_ref=body.shared_document_ref,
                label_en=body.label_en,
                label_ar=body.label_ar,
                sensitive=body.sensitive,
            )
        )

    def dashboard_evidence_content(evidence_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.retrieve_evidence(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                evidence_id=evidence_id,
                access_channel="download",
            )
        )

    def dashboard_finding(case_id: str, body: FindingBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.investigate", "er.manage"})
        return _run(
            lambda cur: surfaces.submit_finding(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                findings_en=body.findings_en,
                findings_ar=body.findings_ar,
                lock=body.lock,
            )
        )

    def dashboard_outcome(case_id: str, body: OutcomeBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.decide", "er.manage"})
        return _run(
            lambda cur: surfaces.record_outcome(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                outcome_code=body.outcome_code,
                summary_en=body.summary_en,
                summary_ar=body.summary_ar,
            )
        )

    def dashboard_close(case_id: str, body: ClosureBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.manage"})
        return _run(
            lambda cur: surfaces.close_case(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                reason=body.reason,
            )
        )

    def dashboard_handoff(case_id: str, body: HandoffBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, need={"er.decide", "er.manage"})
        return _run(
            lambda cur: surfaces.create_handoff_idempotent(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                outcome_id=body.outcome_id,
                handoff_payload=body.handoff_payload,
            )
        )

    def dashboard_history(case_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.case_history(
                cur, company_code=company, actor_key=_actor_key(context), case_id=case_id
            )
        )

    def dashboard_export(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require(context, "er.export")
        return _run(
            lambda cur: surfaces.export_cases(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
            )
        )

    def dashboard_contribution(
        case_id: str, body: ContributionBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        if _role(context) == "manager":
            require_entitlement(context, "employee_relations")
            company = str(context.get("company_code") or "").strip().upper()
            gate = c4.runtime_gate_for_company(company)
            if not gate.get("ok"):
                _raise_gate(gate)
        else:
            company = _company(context, allow_manager=True)
        return _run(
            lambda cur: surfaces.scoped_contribution(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
                body_en=body.body_en,
                body_ar=body.body_ar,
            )
        )

    def dashboard_assistant(body: AssistantBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.assistant_query(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                question_kind=body.question_kind,
                case_id=body.case_id,
            )
        )

    def mobile_queue(limit: int = 50, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.mobile_queue(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                limit=limit,
            )
        )

    def mobile_case(case_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.mobile_case_summary(
                cur,
                company_code=company,
                actor_key=_actor_key(context),
                actor_role=_actor_role(context),
                case_id=case_id,
            )
        )

    def mobile_acknowledge(case_id: str, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.acknowledge_action(
                cur,
                company_code=company,
                actor_phone=_phone(context),
                actor_key=_actor_key(context),
                case_id=case_id,
            )
        )

    _bind("", dashboard_workspace)
    _bind("/workspace", dashboard_workspace)
    _bind("/cases", dashboard_cases)
    _bind("/my-work", dashboard_my_work)
    _bind("/case-types", dashboard_case_types)
    _bind("/case-types", dashboard_upsert_case_type, ("POST",))
    _bind("/cases", dashboard_intake, ("POST",))
    _bind("/cases/{case_id}", dashboard_case_detail)
    _bind("/cases/{case_id}/triage", dashboard_triage, ("POST",))
    _bind("/cases/{case_id}/assign", dashboard_assign, ("POST",))
    _bind("/cases/{case_id}/grants", dashboard_grant, ("POST",))
    _bind("/cases/{case_id}/notes", dashboard_notes, ("POST",))
    _bind("/cases/{case_id}/evidence", dashboard_evidence, ("POST",))
    _bind("/evidence/{evidence_id}/content", dashboard_evidence_content)
    _bind("/cases/{case_id}/findings", dashboard_finding, ("POST",))
    _bind("/cases/{case_id}/outcomes", dashboard_outcome, ("POST",))
    _bind("/cases/{case_id}/closure", dashboard_close, ("POST",))
    _bind("/cases/{case_id}/handoffs", dashboard_handoff, ("POST",))
    _bind("/cases/{case_id}/history", dashboard_history)
    _bind("/cases/{case_id}/contribution", dashboard_contribution, ("POST",))
    _bind("/export", dashboard_export)
    _bind("/assistant", dashboard_assistant, ("POST",))

    app.add_api_route(MOBILE_PREFIX, mobile_queue, methods=["GET"])
    app.add_api_route(MOBILE_PREFIX + "/cases/{case_id}", mobile_case, methods=["GET"])
    app.add_api_route(MOBILE_PREFIX + "/cases/{case_id}/acknowledge", mobile_acknowledge, methods=["POST"])
