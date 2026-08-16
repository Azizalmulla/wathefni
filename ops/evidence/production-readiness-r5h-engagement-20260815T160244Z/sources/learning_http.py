#!/usr/bin/env python3
"""HTTP adapters for Learning (R5E) — thin wrappers over frozen Wave 6 C2.

Namespaces:
  /dashboard/learning/...
  /dashboard/posthire/learning/...  (alias)
  /app/learning/...

Company and actor identity come from authenticated context only.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import learning_development_c2 as c2
import learning_surfaces as surfaces

DASH_PREFIXES = ("/dashboard/learning", "/dashboard/posthire/learning")


class CatalogItemBody(BaseModel):
    code: str
    item_type: str
    title_en: str
    title_ar: str
    status: str = "draft"
    category: str = ""
    provider_id: str | None = None
    delivery_mode: str = "self_paced"
    duration_minutes: int | None = None
    description_en: str = ""
    description_ar: str = ""
    completion_requirements: dict[str, Any] | None = None
    optional_refs: dict[str, Any] | None = None
    reason: str = "upsert learning item"


class ProgramChildBody(BaseModel):
    program_item_id: str
    child_item_id: str
    program_version: int = 1
    sequence_no: int | None = None
    required: bool = True


class AssignmentBody(BaseModel):
    employee_key: str
    item_id: str
    source: str = "hr_assigned"
    required: bool = True
    due_date: str | None = None
    offering_id: str | None = None
    program_item_id: str | None = None
    program_version: int | None = None
    reason: str = "assign learning"


class AdvanceBody(BaseModel):
    to_status: str
    reason: str = ""


class RequestBody(BaseModel):
    item_id: str
    employee_key: str | None = None
    reason: str = ""


class DecideBody(BaseModel):
    approve: bool
    reason: str = ""


class SessionBody(BaseModel):
    item_id: str
    starts_at: str | None = None
    ends_at: str | None = None
    location_or_virtual: str = ""
    instructor: str = ""
    capacity: int | None = None


class EnrollBody(BaseModel):
    employee_key: str
    source: str = "hr_assigned"
    reason: str = "enroll in session"


class AttendanceBody(BaseModel):
    assignment_id: str
    evidence_ref: str = ""
    evidence_payload: dict[str, Any] | None = None


class CompletionBody(BaseModel):
    assignment_id: str
    evidence_source: str
    evidence_ref: str = ""
    evidence_payload: dict[str, Any] | None = None
    provider_id: str | None = None


class CertificateBody(BaseModel):
    employee_key: str
    cert_type: str
    title_en: str
    title_ar: str
    issued_on: str
    expires_on: str | None = None
    issuer: str = ""
    evidence_ref: str = ""
    linked_completion_id: str | None = None
    renewal_of: str | None = None


class MandatoryBody(BaseModel):
    code: str
    title_en: str
    title_ar: str
    item_id: str
    population_rule: dict[str, Any]
    due_offset_days: int = 30
    policy_version: int = 1


class GenerateBody(BaseModel):
    employee_keys: list[str]
    reason: str = "generate mandatory assignments"


class DevelopmentLinkBody(BaseModel):
    development_action_id: str
    assignment_id: str | None = None
    completion_id: str | None = None
    item_id: str | None = None


_GATE_ERRORS = {
    "learning_c2_off",
    "learning_company_not_allowlisted",
    "learning_disabled_for_company",
    "company_disabled",
    "entitlement_off",
    "employee_requests_disabled",
    "development_fulfillment_disabled",
}

_NOT_FOUND = {
    "learning_item_not_found",
    "assignment_not_found",
    "request_not_found",
    "session_not_found",
    "policy_not_found",
}

_FORBIDDEN = {
    "permission_denied",
    "scope_denied",
    "employee_self_completion_forbidden",
    "manager_out_of_scope",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "learning_denied")
    if err in _GATE_ERRORS or err.endswith("_entitlement_off") or err.endswith("_not_allowlisted"):
        raise HTTPException(
            status_code=403,
            detail={"error": err, "message": "Learning is not enabled for this company.", "gate": result.get("gate")},
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted."})
    if err == "session_capacity_exceeded":
        raise HTTPException(status_code=409, detail={"error": err, "message": "Session is at capacity."})
    if err in {"rejection_reason_required", "evidence_required", "request_not_pending"}:
        raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_learning_http(app_mod: Any) -> None:
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

    def _manager_keys(context: dict[str, Any], company: str) -> list[str] | None:
        if _role(context) != "manager":
            return None
        if not context_manager_employee_keys:
            return []
        keys = context_manager_employee_keys(context, company) or set()
        return sorted(str(item) for item in keys)

    def _company(context: dict[str, Any], *, write: bool = False, need: set[str] | None = None) -> str:
        company = posthire_context(context, "learning")
        perms = _perms(context)
        required = need or ({"learning.manage", "learning.assign", "learning.approve"} if write else set())
        if write and required and not (required & perms) and "learning.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})
        gate = c2.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _assert_manager_scope(context: dict[str, Any], company: str, employee_key: str | None) -> None:
        keys = _manager_keys(context, company)
        if keys is None:
            return
        if not employee_key or employee_key not in keys:
            raise HTTPException(status_code=403, detail={"error": "scope_denied", "message": "Not permitted."})

    def _require_manage(context: dict[str, Any]) -> None:
        if "learning.manage" not in _perms(context):
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})

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
                flow="learning",
                template_key=template_key,
                text=text,
                email_subject=subject,
                company_code=company,
                dedupe_key=f"learning:{template_key}:{company}:{key}",
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
        return _run(
            lambda cur: surfaces.workspace_summary(
                cur,
                company_code=company,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    def dashboard_catalog(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_catalog(cur, company_code=company))

    def dashboard_upsert_item(body: CatalogItemBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        return _run(
            lambda cur: c2.upsert_learning_item(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                code=body.code,
                item_type=body.item_type,
                title_en=body.title_en,
                title_ar=body.title_ar,
                status=body.status,
                category=body.category,
                provider_id=body.provider_id,
                delivery_mode=body.delivery_mode,
                duration_minutes=body.duration_minutes,
                description_en=body.description_en,
                description_ar=body.description_ar,
                completion_requirements=body.completion_requirements,
                optional_refs=body.optional_refs,
                reason=body.reason,
            )
        )

    def dashboard_program_child(body: ProgramChildBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        return _run(
            lambda cur: c2.add_program_child(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                program_item_id=body.program_item_id,
                child_item_id=body.child_item_id,
                program_version=body.program_version,
                sequence_no=body.sequence_no,
                required=body.required,
            )
        )

    def dashboard_assignments(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_assignments(
                cur,
                company_code=company,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    def dashboard_assign(body: AssignmentBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.assign", "learning.manage"})
        _assert_manager_scope(context, company, body.employee_key)
        source = body.source
        if _role(context) == "manager":
            source = "manager_assigned"
        result = _run(
            lambda cur: c2.create_assignment(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                item_id=body.item_id,
                source=source,
                required=body.required,
                due_date=body.due_date,
                offering_id=body.offering_id,
                program_item_id=body.program_item_id,
                program_version=body.program_version,
                reason=body.reason,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(
                company,
                body.employee_key,
                template_key="learning_assignment_created",
                text="You have a new learning assignment.",
                subject="New learning assignment",
            )
        return result

    def dashboard_advance(assignment_id: str, body: AdvanceBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.assign", "learning.manage"})
        return _run(
            lambda cur: c2.advance_assignment(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                assignment_id=assignment_id,
                to_status=body.to_status,
                reason=body.reason,
            )
        )

    def dashboard_requests(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_requests(
                cur,
                company_code=company,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    def dashboard_create_request(body: RequestBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.assign", "learning.manage", "learning.approve"})
        key = body.employee_key or ""
        _assert_manager_scope(context, company, key)
        return _run(
            lambda cur: c2.create_learning_request(
                cur, company_code=company, employee_key=key, item_id=body.item_id, reason=body.reason
            )
        )

    def dashboard_decide(request_id: str, body: DecideBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.approve", "learning.manage"})
        result = _run(
            lambda cur: surfaces.decide_request(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                request_id=request_id,
                approve=body.approve,
                reason=body.reason,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            req = result.get("request") or {}
            employee_key = str(req.get("employee_key") or "")
            if body.approve:
                _notify(
                    company,
                    employee_key,
                    template_key="learning_request_approved",
                    text="Your learning request was approved.",
                    subject="Learning request approved",
                )
            else:
                _notify(
                    company,
                    employee_key,
                    template_key="learning_request_rejected",
                    text="Your learning request was not approved.",
                    subject="Learning request update",
                )
        return result

    def dashboard_sessions(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_sessions(cur, company_code=company))

    def dashboard_create_session(body: SessionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        return _run(
            lambda cur: c2.create_offering(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                item_id=body.item_id,
                starts_at=body.starts_at,
                ends_at=body.ends_at,
                location_or_virtual=body.location_or_virtual,
                instructor=body.instructor,
                capacity=body.capacity,
            )
        )

    def dashboard_enroll(offering_id: str, body: EnrollBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.assign", "learning.manage"})
        _assert_manager_scope(context, company, body.employee_key)
        source = "manager_assigned" if _role(context) == "manager" else body.source
        return _run(
            lambda cur: surfaces.enroll_in_session(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                offering_id=offering_id,
                employee_key=body.employee_key,
                source=source,
                reason=body.reason,
            )
        )

    def dashboard_attendance(offering_id: str, body: AttendanceBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        return _run(
            lambda cur: surfaces.record_session_attendance(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                offering_id=offering_id,
                assignment_id=body.assignment_id,
                evidence_ref=body.evidence_ref,
                evidence_payload=body.evidence_payload,
            )
        )

    def dashboard_completions(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_completions(
                cur,
                company_code=company,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    def dashboard_complete(body: CompletionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        return _run(
            lambda cur: surfaces.record_completion_guarded(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                assignment_id=body.assignment_id,
                evidence_source=body.evidence_source,
                evidence_ref=body.evidence_ref,
                evidence_payload=body.evidence_payload,
                provider_id=body.provider_id,
                actor_role=_role(context),
            )
        )

    def dashboard_certificates(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_certificates(
                cur,
                company_code=company,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    def dashboard_issue_cert(body: CertificateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        result = _run(
            lambda cur: c2.issue_certification(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                cert_type=body.cert_type,
                title_en=body.title_en,
                title_ar=body.title_ar,
                issued_on=body.issued_on,
                expires_on=body.expires_on,
                issuer=body.issuer,
                evidence_ref=body.evidence_ref,
                linked_completion_id=body.linked_completion_id,
                renewal_of=body.renewal_of,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            _notify(
                company,
                body.employee_key,
                template_key="learning_certification_issued" if not body.renewal_of else "learning_renewal_needed",
                text="A learning certification was issued." if not body.renewal_of else "A certification renewal was recorded.",
                subject="Learning certification",
            )
        return result

    def dashboard_mandatory(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_mandatory(cur, company_code=company))

    def dashboard_create_mandatory(body: MandatoryBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        return _run(
            lambda cur: c2.create_mandatory_policy(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                code=body.code,
                title_en=body.title_en,
                title_ar=body.title_ar,
                item_id=body.item_id,
                population_rule=body.population_rule,
                due_offset_days=body.due_offset_days,
                policy_version=body.policy_version,
            )
        )

    def dashboard_generate(policy_id: str, body: GenerateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        result = _run(
            lambda cur: c2.generate_mandatory_assignments(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                policy_id=policy_id,
                employee_keys=body.employee_keys,
            )
        )
        if isinstance(result, dict) and result.get("ok"):
            for key in result.get("created") or []:
                _notify(
                    company,
                    str(key),
                    template_key="learning_mandatory_due",
                    text="Mandatory learning has been assigned to you.",
                    subject="Mandatory learning",
                )
        return result

    def dashboard_dev_links(body: DevelopmentLinkBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, need={"learning.manage"})
        _require_manage(context)
        return _run(
            lambda cur: c2.link_development_fulfillment(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                development_action_id=body.development_action_id,
                assignment_id=body.assignment_id,
                completion_id=body.completion_id,
                item_id=body.item_id,
            )
        )

    def dashboard_history(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.list_history(
                cur,
                company_code=company,
                actor_role=_role(context),
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    def dashboard_programs(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_catalog(cur, company_code=company, programs_only=True))

    def dashboard_list_dev_links(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_development_links(cur, company_code=company))

    def dashboard_team(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(
            lambda cur: surfaces.manager_team_status(
                cur,
                company_code=company,
                manager_scope_keys=_manager_keys(context, company),
            )
        )

    _bind("/workspace", dashboard_workspace)
    _bind("/catalog", dashboard_catalog)
    _bind("/catalog", dashboard_upsert_item, ("POST",))
    _bind("/programs/children", dashboard_program_child, ("POST",))
    _bind("/assignments", dashboard_assignments)
    _bind("/assignments", dashboard_assign, ("POST",))
    _bind("/assignments/{assignment_id}/advance", dashboard_advance, ("POST",))
    _bind("/requests", dashboard_requests)
    _bind("/requests", dashboard_create_request, ("POST",))
    _bind("/requests/{request_id}/decide", dashboard_decide, ("POST",))
    _bind("/sessions", dashboard_sessions)
    _bind("/sessions", dashboard_create_session, ("POST",))
    _bind("/sessions/{offering_id}/enroll", dashboard_enroll, ("POST",))
    _bind("/sessions/{offering_id}/attendance", dashboard_attendance, ("POST",))
    _bind("/completions", dashboard_completions)
    _bind("/completions", dashboard_complete, ("POST",))
    _bind("/certificates", dashboard_certificates)
    _bind("/certificates", dashboard_issue_cert, ("POST",))
    _bind("/mandatory", dashboard_mandatory)
    _bind("/mandatory", dashboard_create_mandatory, ("POST",))
    _bind("/mandatory/{policy_id}/generate", dashboard_generate, ("POST",))
    _bind("/programs", dashboard_programs)
    _bind("/development-links", dashboard_list_dev_links)
    _bind("/development-links", dashboard_dev_links, ("POST",))
    _bind("/history", dashboard_history)
    _bind("/team", dashboard_team)

    def _employee_key(context: dict[str, Any]) -> str:
        return str(context.get("employee_key") or context.get("actor_employee_key") or "")

    @app.get("/app/learning")
    def app_learning_workspace(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "learning", action="view")
        company = str(context.get("company_code") or "")
        gate = c2.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return _run(
            lambda cur: surfaces.employee_workspace(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.get("/app/learning/catalog")
    def app_learning_catalog(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "learning", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.list_catalog(cur, company_code=company, published_only=True),
            employee_view=True,
        )

    @app.get("/app/learning/assignments")
    def app_learning_assignments(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "learning", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.list_assignments(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.get("/app/learning/sessions/{offering_id}")
    def app_learning_session(offering_id: str, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "learning", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.session_detail(
                cur,
                company_code=company,
                offering_id=offering_id,
                employee_key=_employee_key(context),
            ),
            employee_view=True,
        )

    @app.post("/app/learning/requests")
    def app_learning_request(body: RequestBody, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "learning", action="request")
        company = str(context.get("company_code") or "")
        employee_key = _employee_key(context)
        return _run(
            lambda cur: c2.create_learning_request(
                cur,
                company_code=company,
                employee_key=employee_key,
                item_id=body.item_id,
                reason=body.reason,
            ),
            employee_view=True,
        )

    @app.get("/app/learning/certificates")
    def app_learning_certificates(context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "learning", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.list_certificates(
                cur, company_code=company, employee_key=_employee_key(context)
            ),
            employee_view=True,
        )

    @app.post("/app/learning/completions")
    def app_learning_complete(body: CompletionBody, context: dict[str, Any] = Depends(employee_app_context)):
        require_employee_app_feature(context, "learning", action="view")
        company = str(context.get("company_code") or "")
        return _run(
            lambda cur: surfaces.record_completion_guarded(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or context.get("phone") or ""),
                assignment_id=body.assignment_id,
                evidence_source=body.evidence_source,
                evidence_ref=body.evidence_ref,
                evidence_payload=body.evidence_payload,
                provider_id=body.provider_id,
                actor_role="employee",
            ),
            employee_view=True,
        )
