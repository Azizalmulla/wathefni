#!/usr/bin/env python3
"""Attendance Wave 3 — FastAPI routes for HR/manager exception operations (dark)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from fastapi import Body, HTTPException, Query
from pydantic import BaseModel, Field

import attendance_ops_wave3 as ops


class ExceptionOpen(BaseModel):
    employee_key: str
    work_date: date
    kind: str
    shift_key: str = ""
    priority: str | None = None
    owner_phone: str | None = None
    source: str = "manual"
    source_ref: str | None = None


class ExceptionAssign(BaseModel):
    owner_phone: str
    expected_row_version: int
    priority: str | None = None
    due_at: datetime | None = None


class CorrectionRequest(BaseModel):
    employee_key: str
    work_date: date
    changes: dict[str, Any]
    shift_id: str | None = None
    exception_id: str | None = None
    kind: str | None = None


class CaseReview(BaseModel):
    decision: str
    expected_row_version: int
    decision_note: str | None = None


class CaseApply(BaseModel):
    expected_row_version: int
    idempotency_key: str
    shift_id: str | None = None


class DisputeRaise(BaseModel):
    employee_key: str
    work_date: date
    reason: str
    exception_id: str | None = None
    case_id: str | None = None
    shift_key: str = ""


class DisputeResolve(BaseModel):
    resolution: str
    expected_row_version: int
    resolution_note: str | None = None


class ExceptionReopen(BaseModel):
    expected_row_version: int
    evidence_note: str


class CommentCreate(BaseModel):
    entity_type: str
    entity_id: str
    body: str


class AttachmentCreate(BaseModel):
    entity_type: str
    entity_id: str
    filename: str
    storage_ref: str
    content_type: str = "application/octet-stream"


def register_attendance_ops_routes(
    app: Any,
    *,
    Depends: Any,
    dashboard_context: Callable,
    require_entitlement: Callable,
    manager_scope_allows_employee: Callable,
    context_manager_allows_employee: Callable | None = None,
    record_admin_audit: Callable,
    digits: Callable,
    json_safe: Callable,
    get_employee: Callable | None = None,
    payroll_date_locked: Callable | None = None,
    manager_is_configured: Callable | None = None,
    manager_scope_employee_keys: Callable | None = None,
) -> None:
    def _company(context: dict[str, Any]) -> str:
        return str(context.get("company_code") or "WATHEFNI").upper()

    def _actor(context: dict[str, Any]) -> str:
        return digits(context.get("hr_phone") or context.get("phone") or "")

    def _role(context: dict[str, Any]) -> str:
        role = str(context.get("actor_role") or context.get("role") or "").lower()
        if role in {"owner", "hr", "admin"}:
            return "hr"
        if context.get("is_owner") or context.get("is_hr"):
            return "hr"
        return "manager"

    def _scope_allows(company: str, actor: str, employee_key: str) -> bool:
        emp = {"employee_key": employee_key, "company_code": company}
        if get_employee:
            found = get_employee(company, employee_key)
            if found:
                emp = found
        return bool(manager_scope_allows_employee(emp, company_code=company, viewer_phone=actor))

    def _payroll_locked(company: str, employee_key: str, work_date: date) -> bool:
        if payroll_date_locked is None:
            return False
        return bool(payroll_date_locked(company, employee_key, work_date))

    def _mgr_configured(company: str, actor: str) -> bool:
        if manager_is_configured is None:
            return True
        return bool(manager_is_configured(company, actor))

    def _svc() -> ops.AttendanceOpsService:
        return ops.get_ops_service(
            scope_allows=_scope_allows,
            payroll_locked=_payroll_locked,
            manager_configured=_mgr_configured,
        )

    def _require_ops(company: str) -> None:
        if not ops.ops_enabled_for_company(company):
            raise HTTPException(status_code=404, detail="attendance_ops_disabled")

    def _emp(company: str, employee_key: str) -> dict[str, Any]:
        if get_employee:
            found = get_employee(company, employee_key)
            if found:
                return found
        return {"employee_key": employee_key, "company_code": company}

    @app.get("/dashboard/attendance/ops/state-model")
    def attendance_ops_state_model(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        return json_safe(ops.state_model_doc())

    @app.get("/dashboard/attendance/ops/exceptions")
    def attendance_ops_list_exceptions(
        status: str | None = Query(None),
        kind: str | None = Query(None),
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        role = _role(context)
        actor = _actor(context)
        keys = None
        if role == "manager":
            if manager_scope_employee_keys is not None:
                keys = manager_scope_employee_keys(company, actor)
            if keys is not None and len(keys) == 0 and not _mgr_configured(company, actor):
                return json_safe({"ok": False, "error": "manager_unconfigured", "exceptions": [], "count": 0})
            if keys is None:
                # Unrestricted (HR-like) — treat as hr for listing
                role = "hr"
        result = _svc().list_queue(
            company_code=company,
            actor_phone=actor,
            actor_role=role,
            status=status,
            kind=kind,
            employee_keys=keys,
        )
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/exceptions")
    def attendance_ops_open_exception(
        body: ExceptionOpen,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        emp = _emp(company, body.employee_key)
        result = _svc().open_exception(
            company_code=company,
            employee=emp,
            work_date=body.work_date,
            kind=body.kind,
            actor_phone=_actor(context),
            shift_key=body.shift_key,
            source=body.source,
            source_ref=body.source_ref,
            priority=body.priority,
            owner_phone=body.owner_phone,
            actor_role=_role(context),
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        record_admin_audit(
            context,
            "attendance_ops_exception_opened",
            summary=f"Opened {body.kind} exception for {body.employee_key}",
            target_type="employee",
            target=body.employee_key,
            details=result,
        )
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/exceptions/{exception_id}/assign")
    def attendance_ops_assign(
        exception_id: str,
        body: ExceptionAssign,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        result = _svc().assign_exception(
            company_code=company,
            exception_id=exception_id,
            owner_phone=body.owner_phone,
            actor_phone=_actor(context),
            expected_row_version=body.expected_row_version,
            priority=body.priority,
            due_at=body.due_at,
            actor_role=_role(context),
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 400
            raise HTTPException(status_code=code, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/exceptions/{exception_id}/reopen")
    def attendance_ops_reopen(
        exception_id: str,
        body: ExceptionReopen,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        result = _svc().reopen_exception(
            company_code=company,
            exception_id=exception_id,
            actor_phone=_actor(context),
            expected_row_version=body.expected_row_version,
            evidence_note=body.evidence_note,
            actor_role=_role(context),
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 400
            raise HTTPException(status_code=code, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/corrections")
    def attendance_ops_request_correction(
        body: CorrectionRequest,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        emp = _emp(company, body.employee_key)
        shift = {"shift_id": body.shift_id} if body.shift_id else None
        result = _svc().request_correction(
            company_code=company,
            employee=emp,
            work_date=body.work_date,
            requested_by_phone=_actor(context),
            changes=body.changes,
            shift=shift,
            exception_id=body.exception_id,
            actor_is_manager=_role(context) == "manager",
            actor_role=_role(context),
            kind=body.kind,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/cases/{case_id}/review")
    def attendance_ops_review_case(
        case_id: str,
        body: CaseReview,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        case = _svc().store.get_case(case_id, company)
        emp = _emp(company, str((case or {}).get("employee_key") or ""))
        result = _svc().review_case(
            company_code=company,
            case_id=case_id,
            decision=body.decision,
            decided_by_phone=_actor(context),
            expected_row_version=body.expected_row_version,
            decision_note=body.decision_note,
            actor_role=_role(context),
            employee=emp,
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 400
            raise HTTPException(status_code=code, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/cases/{case_id}/apply")
    def attendance_ops_apply_case(
        case_id: str,
        body: CaseApply,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        case = _svc().store.get_case(case_id, company)
        emp = _emp(company, str((case or {}).get("employee_key") or ""))
        shift = {"shift_id": body.shift_id} if body.shift_id else None
        result = _svc().apply_case(
            company_code=company,
            case_id=case_id,
            applied_by_phone=_actor(context),
            expected_row_version=body.expected_row_version,
            idempotency_key=body.idempotency_key,
            employee=emp,
            shift=shift,
            actor_role=_role(context),
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 400
            raise HTTPException(status_code=code, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/disputes")
    def attendance_ops_raise_dispute(
        body: DisputeRaise,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        emp = _emp(company, body.employee_key)
        result = _svc().raise_dispute(
            company_code=company,
            employee=emp,
            work_date=body.work_date,
            raised_by_phone=_actor(context),
            reason=body.reason,
            exception_id=body.exception_id,
            case_id=body.case_id,
            shift_key=body.shift_key,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/disputes/{dispute_id}/resolve")
    def attendance_ops_resolve_dispute(
        dispute_id: str,
        body: DisputeResolve,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        dispute = _svc().store.get_dispute(dispute_id, company)
        emp = _emp(company, str((dispute or {}).get("employee_key") or ""))
        result = _svc().resolve_dispute(
            company_code=company,
            dispute_id=dispute_id,
            resolution=body.resolution,
            resolved_by_phone=_actor(context),
            expected_row_version=body.expected_row_version,
            resolution_note=body.resolution_note,
            actor_role=_role(context),
            employee=emp,
        )
        if not result.get("ok"):
            code = 409 if result.get("error") == "stale_row_version" else 400
            raise HTTPException(status_code=code, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/comments")
    def attendance_ops_comment(
        body: CommentCreate,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        result = _svc().add_comment(
            company_code=company,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            author_phone=_actor(context),
            body=body.body,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        return json_safe(result)

    @app.post("/dashboard/attendance/ops/attachments")
    def attendance_ops_attachment(
        body: AttachmentCreate,
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = _company(context)
        _require_ops(company)
        require_entitlement(context, "attendance")
        result = _svc().add_attachment(
            company_code=company,
            entity_type=body.entity_type,
            entity_id=body.entity_id,
            uploaded_by_phone=_actor(context),
            filename=body.filename,
            storage_ref=body.storage_ref,
            content_type=body.content_type,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        return json_safe(result)
