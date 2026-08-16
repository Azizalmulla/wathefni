#!/usr/bin/env python3
"""Attendance Wave 3 — HR/manager exception queue and correction operations.

Built on Wave 1 attendance authority. Does not enable real clocking, device
ingest, QR/GPS/kiosk, or production deploy.

Store mode:
  WATHEFNI_ATTENDANCE_OPS_STORE=memory   (default; process-local / unit tests)
  WATHEFNI_ATTENDANCE_OPS_STORE=postgres (durable; staging)

Flags:
  WATHEFNI_ATTENDANCE_OPS=on
  WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI
  WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
"""

from __future__ import annotations

import os
import threading
import uuid
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import attendance_authority_wave1 as authority

KUWAIT_TZ = ZoneInfo("Asia/Kuwait")
_ON = {"1", "true", "yes", "on"}

EXCEPTION_KINDS = frozenset({
    "missing_check_in",
    "missing_check_out",
    "ambiguous_punches",
    "incomplete_session",
    "absence",
    "lateness",
    "early_leave",
    "connector_issue",
})
EXCEPTION_STATUSES = frozenset({
    "open",
    "assigned",
    "in_review",
    "pending_dual_approval",
    "resolved",
    "rejected",
    "reopened",
    "closed",
})
CASE_STATUSES = frozenset({
    "requested",
    "under_review",
    "approved",
    "rejected",
    "pending_dual_approval",
    "applied",
    "disputed",
    "reopened",
    "cancelled",
})
DISPUTE_STATUSES = frozenset({
    "open",
    "under_review",
    "upheld",
    "overturned",
    "closed",
})
PRIORITIES = frozenset({"low", "normal", "high", "critical"})
HIGH_RISK_DEFAULT_KINDS = frozenset({"absence", "early_leave"})

ScopeFn = Callable[[str, str, str], bool]  # company, actor_phone, employee_key
PayrollLockFn = Callable[[str, str, date], bool]  # company, employee_key, work_date
AuthorityFn = Callable[[str | None], Any]


def ops_enabled() -> bool:
    return (os.environ.get("WATHEFNI_ATTENDANCE_OPS") or "").strip().lower() in _ON


def ops_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_ATTENDANCE_OPS_COMPANIES") or "WATHEFNI").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def ops_enabled_for_company(company_code: str | None) -> bool:
    if not ops_enabled():
        return False
    allowed = ops_companies()
    if not allowed:
        return True
    return str(company_code or "").strip().upper() in allowed


def ops_store_mode() -> str:
    raw = (os.environ.get("WATHEFNI_ATTENDANCE_OPS_STORE") or "memory").strip().lower()
    return "postgres" if raw in {"postgres", "pg", "postgresql"} else "memory"


def ops_synthetic_only() -> bool:
    """Production fail-closed: ops mutate synthetic employees only unless explicitly off."""
    raw = (os.environ.get("WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY") or "").strip().lower()
    if raw in _ON:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    return env == "production"


def ops_allowed_for(
    company_code: str | None,
    employee: dict[str, Any] | None = None,
    *,
    employee_key: str | None = None,
    phone: str | None = None,
) -> bool:
    if not ops_enabled_for_company(company_code):
        return False
    if not ops_synthetic_only():
        return True
    return authority.is_attendance_synthetic_employee(employee, employee_key=employee_key, phone=phone)


def dual_approval_kinds() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS") or "").strip()
    if not raw:
        return set(HIGH_RISK_DEFAULT_KINDS)
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


def digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _now() -> datetime:
    return datetime.now(KUWAIT_TZ)


def _uid() -> str:
    return str(uuid.uuid4())


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def projection_snapshot(proj: dict[str, Any] | None) -> dict[str, Any]:
    if not proj:
        return {}
    keys = (
        "projection_id",
        "version",
        "status",
        "exception_state",
        "approval_status",
        "payroll_eligible",
        "check_in_at",
        "check_out_at",
        "late_minutes",
        "early_leave_minutes",
        "worked_minutes",
        "manual_correction",
        "leave_id",
    )
    return _json_safe({k: proj.get(k) for k in keys})


def classify_projection_exceptions(proj: dict[str, Any]) -> list[str]:
    kinds: list[str] = []
    exc = str(proj.get("exception_state") or "none")
    if exc in EXCEPTION_KINDS and exc != "none":
        kinds.append(exc)
    status = str(proj.get("status") or "")
    if status == "absent":
        kinds.append("absence")
    if int(proj.get("late_minutes") or 0) > 0:
        kinds.append("lateness")
    if int(proj.get("early_leave_minutes") or 0) > 0:
        kinds.append("early_leave")
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for k in kinds:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def default_priority(kind: str) -> str:
    if kind in {"absence", "ambiguous_punches", "connector_issue"}:
        return "high"
    if kind in {"missing_check_in", "missing_check_out", "incomplete_session"}:
        return "normal"
    return "normal"


def default_due_at(priority: str, *, now: datetime | None = None) -> datetime:
    base = now or _now()
    days = {"critical": 1, "high": 2, "normal": 5, "low": 10}.get(priority, 5)
    return base + timedelta(days=days)


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------

class InMemoryOpsStore:
    def __init__(self) -> None:
        self.exceptions: list[dict[str, Any]] = []
        self.cases: list[dict[str, Any]] = []
        self.disputes: list[dict[str, Any]] = []
        self.comments: list[dict[str, Any]] = []
        self.attachments: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.idempotency: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def _audit(self, row: dict[str, Any]) -> None:
        event = {
            "event_id": _uid(),
            "created_at": _now(),
            **row,
        }
        self.audit.append(event)

    def insert_exception(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            saved = {
                "exception_id": row.get("exception_id") or _uid(),
                "company_code": str(row["company_code"]).upper(),
                "employee_key": row["employee_key"],
                "employee_phone": digits(row.get("employee_phone")),
                "employee_name": row.get("employee_name"),
                "work_date": row["work_date"],
                "shift_key": authority.shift_key_of(row.get("shift_key")),
                "projection_id": row.get("projection_id"),
                "kind": row["kind"],
                "status": row.get("status") or "open",
                "priority": row.get("priority") or default_priority(row["kind"]),
                "owner_phone": digits(row.get("owner_phone")),
                "due_at": row.get("due_at") or default_due_at(row.get("priority") or default_priority(row["kind"])),
                "source": row.get("source") or "projection",
                "source_ref": row.get("source_ref"),
                "before_values": deepcopy(row.get("before_values") or {}),
                "after_values": deepcopy(row.get("after_values") or {}),
                "payroll_excluded": bool(row.get("payroll_excluded", True)),
                "row_version": 1,
                "metadata": deepcopy(row.get("metadata") or {}),
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.exceptions.append(saved)
            self._audit({
                "company_code": saved["company_code"],
                "entity_type": "exception",
                "entity_id": saved["exception_id"],
                "event_type": "exception_opened",
                "payload": {"kind": saved["kind"], "status": saved["status"]},
                "created_by_phone": digits((row.get("metadata") or {}).get("opened_by")),
            })
            return deepcopy(saved)

    def get_exception(self, exception_id: str, company_code: str) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._lock:
            for row in self.exceptions:
                if row["exception_id"] == exception_id and row["company_code"] == company:
                    return deepcopy(row)
        return None

    def update_exception(
        self,
        exception_id: str,
        company_code: str,
        *,
        expected_row_version: int | None = None,
        **fields: Any,
    ) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._lock:
            for row in self.exceptions:
                if row["exception_id"] != exception_id or row["company_code"] != company:
                    continue
                if expected_row_version is not None and int(row["row_version"]) != int(expected_row_version):
                    return {"__conflict__": True, "current": deepcopy(row)}
                for key, value in fields.items():
                    if key in {"before_values", "after_values", "metadata"} and isinstance(value, dict):
                        row[key] = {**(row.get(key) or {}), **value} if key == "metadata" else deepcopy(value)
                    elif key in {
                        "status", "priority", "owner_phone", "due_at", "source_ref",
                        "payroll_excluded", "projection_id", "after_values", "before_values", "metadata",
                    }:
                        if key == "owner_phone":
                            row[key] = digits(value)
                        else:
                            row[key] = value
                row["row_version"] = int(row["row_version"]) + 1
                row["updated_at"] = _now()
                return deepcopy(row)
        return None

    def list_exceptions(
        self,
        *,
        company_code: str,
        status: str | None = None,
        kind: str | None = None,
        owner_phone: str | None = None,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._lock:
            rows = [r for r in self.exceptions if r["company_code"] == company]
            if status:
                rows = [r for r in rows if r.get("status") == status]
            if kind:
                rows = [r for r in rows if r.get("kind") == kind]
            if owner_phone:
                op = digits(owner_phone)
                rows = [r for r in rows if digits(r.get("owner_phone")) == op]
            if employee_key:
                rows = [r for r in rows if r.get("employee_key") == employee_key]
            if employee_keys is not None:
                rows = [r for r in rows if r.get("employee_key") in employee_keys]
            rows.sort(key=lambda r: (str(r.get("due_at") or ""), str(r.get("created_at") or "")), reverse=True)
            return deepcopy(rows)

    def find_open_exception(
        self,
        *,
        company_code: str,
        employee_key: str,
        work_date: date,
        shift_key: str,
        kind: str,
    ) -> dict[str, Any] | None:
        company = company_code.upper()
        skey = authority.shift_key_of(shift_key)
        openish = {"open", "assigned", "in_review", "pending_dual_approval", "reopened"}
        with self._lock:
            for row in self.exceptions:
                if (
                    row["company_code"] == company
                    and row["employee_key"] == employee_key
                    and authority.parse_date(row["work_date"]) == work_date
                    and authority.shift_key_of(row.get("shift_key")) == skey
                    and row["kind"] == kind
                    and row["status"] in openish
                ):
                    return deepcopy(row)
        return None

    def insert_case(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            saved = {
                "case_id": row.get("case_id") or _uid(),
                "company_code": str(row["company_code"]).upper(),
                "exception_id": row.get("exception_id"),
                "correction_id": row.get("correction_id"),
                "employee_key": row["employee_key"],
                "employee_phone": digits(row.get("employee_phone")),
                "work_date": row["work_date"],
                "shift_key": authority.shift_key_of(row.get("shift_key")),
                "status": row.get("status") or "requested",
                "kind": row.get("kind"),
                "high_risk": bool(row.get("high_risk")),
                "dual_approval_required": bool(row.get("dual_approval_required")),
                "first_approver_phone": digits(row.get("first_approver_phone")),
                "second_approver_phone": digits(row.get("second_approver_phone")),
                "requested_by_phone": digits(row.get("requested_by_phone")),
                "requested_changes": deepcopy(row.get("requested_changes") or {}),
                "before_snapshot": deepcopy(row.get("before_snapshot") or {}),
                "after_snapshot": deepcopy(row.get("after_snapshot") or {}),
                "decision_note": row.get("decision_note"),
                "apply_idempotency_key": row.get("apply_idempotency_key"),
                "applied_at": row.get("applied_at"),
                "resulting_projection_id": row.get("resulting_projection_id"),
                "row_version": 1,
                "metadata": deepcopy(row.get("metadata") or {}),
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.cases.append(saved)
            self._audit({
                "company_code": saved["company_code"],
                "entity_type": "case",
                "entity_id": saved["case_id"],
                "event_type": "correction_requested",
                "payload": {"status": saved["status"], "correction_id": saved.get("correction_id")},
                "created_by_phone": saved.get("requested_by_phone"),
            })
            return deepcopy(saved)

    def get_case(self, case_id: str, company_code: str) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._lock:
            for row in self.cases:
                if row["case_id"] == case_id and row["company_code"] == company:
                    return deepcopy(row)
        return None

    def list_cases_for_exception(self, exception_id: str, company_code: str) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._lock:
            return deepcopy([
                row for row in self.cases
                if row.get("exception_id") == exception_id and row["company_code"] == company
            ])

    def list_cases(
        self,
        *,
        company_code: str,
        status: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._lock:
            rows = [r for r in self.cases if r["company_code"] == company]
            if status:
                rows = [r for r in rows if r.get("status") == status]
            if employee_keys is not None:
                rows = [r for r in rows if r.get("employee_key") in employee_keys]
            rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
            return deepcopy(rows)

    def list_disputes(
        self,
        *,
        company_code: str,
        status: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._lock:
            rows = [r for r in self.disputes if r["company_code"] == company]
            if status:
                rows = [r for r in rows if r.get("status") == status]
            if employee_keys is not None:
                rows = [r for r in rows if r.get("employee_key") in employee_keys]
            rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
            return deepcopy(rows)

    def update_case(
        self,
        case_id: str,
        company_code: str,
        *,
        expected_row_version: int | None = None,
        **fields: Any,
    ) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._lock:
            for row in self.cases:
                if row["case_id"] != case_id or row["company_code"] != company:
                    continue
                if expected_row_version is not None and int(row["row_version"]) != int(expected_row_version):
                    return {"__conflict__": True, "current": deepcopy(row)}
                for key, value in fields.items():
                    if key == "metadata" and isinstance(value, dict):
                        row[key] = {**(row.get(key) or {}), **value}
                    elif key in {
                        "status", "first_approver_phone", "second_approver_phone", "decision_note",
                        "apply_idempotency_key", "applied_at", "resulting_projection_id",
                        "before_snapshot", "after_snapshot", "correction_id", "high_risk",
                        "dual_approval_required", "metadata",
                    }:
                        if key.endswith("_phone"):
                            row[key] = digits(value)
                        else:
                            row[key] = value
                row["row_version"] = int(row["row_version"]) + 1
                row["updated_at"] = _now()
                return deepcopy(row)
        return None

    def insert_dispute(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            saved = {
                "dispute_id": row.get("dispute_id") or _uid(),
                "company_code": str(row["company_code"]).upper(),
                "exception_id": row.get("exception_id"),
                "case_id": row.get("case_id"),
                "employee_key": row["employee_key"],
                "work_date": row["work_date"],
                "shift_key": authority.shift_key_of(row.get("shift_key")),
                "status": row.get("status") or "open",
                "raised_by_phone": digits(row.get("raised_by_phone")),
                "reason": row.get("reason") or "",
                "resolution_note": row.get("resolution_note"),
                "resolved_by_phone": digits(row.get("resolved_by_phone")),
                "resolved_at": row.get("resolved_at"),
                "row_version": 1,
                "metadata": deepcopy(row.get("metadata") or {}),
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.disputes.append(saved)
            self._audit({
                "company_code": saved["company_code"],
                "entity_type": "dispute",
                "entity_id": saved["dispute_id"],
                "event_type": "dispute_raised",
                "payload": {"reason": saved["reason"], "status": saved["status"]},
                "created_by_phone": saved.get("raised_by_phone"),
            })
            return deepcopy(saved)

    def get_dispute(self, dispute_id: str, company_code: str) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._lock:
            for row in self.disputes:
                if row["dispute_id"] == dispute_id and row["company_code"] == company:
                    return deepcopy(row)
        return None

    def update_dispute(
        self,
        dispute_id: str,
        company_code: str,
        *,
        expected_row_version: int | None = None,
        **fields: Any,
    ) -> dict[str, Any] | None:
        company = company_code.upper()
        with self._lock:
            for row in self.disputes:
                if row["dispute_id"] != dispute_id or row["company_code"] != company:
                    continue
                if expected_row_version is not None and int(row["row_version"]) != int(expected_row_version):
                    return {"__conflict__": True, "current": deepcopy(row)}
                for key, value in fields.items():
                    if key == "metadata" and isinstance(value, dict):
                        row[key] = {**(row.get(key) or {}), **value}
                    elif key in {
                        "status", "resolution_note", "resolved_by_phone", "resolved_at",
                        "case_id", "exception_id", "metadata",
                    }:
                        if key.endswith("_phone"):
                            row[key] = digits(value)
                        else:
                            row[key] = value
                row["row_version"] = int(row["row_version"]) + 1
                row["updated_at"] = _now()
                return deepcopy(row)
        return None

    def add_comment(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            saved = {
                "comment_id": _uid(),
                "company_code": str(row["company_code"]).upper(),
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "author_phone": digits(row.get("author_phone")),
                "body": str(row.get("body") or ""),
                "created_at": _now(),
            }
            self.comments.append(saved)
            self._audit({
                "company_code": saved["company_code"],
                "entity_type": saved["entity_type"],
                "entity_id": saved["entity_id"],
                "event_type": "comment_added",
                "payload": {"comment_id": saved["comment_id"]},
                "created_by_phone": saved["author_phone"],
            })
            return deepcopy(saved)

    def add_attachment(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            saved = {
                "attachment_id": _uid(),
                "company_code": str(row["company_code"]).upper(),
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "filename": row.get("filename") or "attachment",
                "content_type": row.get("content_type") or "application/octet-stream",
                "storage_ref": row.get("storage_ref") or "",
                "uploaded_by_phone": digits(row.get("uploaded_by_phone")),
                "created_at": _now(),
            }
            self.attachments.append(saved)
            self._audit({
                "company_code": saved["company_code"],
                "entity_type": saved["entity_type"],
                "entity_id": saved["entity_id"],
                "event_type": "attachment_added",
                "payload": {"attachment_id": saved["attachment_id"], "filename": saved["filename"]},
                "created_by_phone": saved["uploaded_by_phone"],
            })
            return deepcopy(saved)

    def list_comments(self, *, company_code: str, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._lock:
            return deepcopy([
                c for c in self.comments
                if c["company_code"] == company and c["entity_type"] == entity_type and c["entity_id"] == entity_id
            ])

    def list_attachments(self, *, company_code: str, entity_type: str, entity_id: str) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._lock:
            return deepcopy([
                a for a in self.attachments
                if a["company_code"] == company and a["entity_type"] == entity_type and a["entity_id"] == entity_id
            ])

    def list_audit(self, *, company_code: str, entity_type: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
        company = company_code.upper()
        with self._lock:
            rows = [a for a in self.audit if a["company_code"] == company]
            if entity_type:
                rows = [a for a in rows if a.get("entity_type") == entity_type]
            if entity_id:
                rows = [a for a in rows if a.get("entity_id") == entity_id]
            return deepcopy(rows)

    def get_idempotency(self, company_code: str, key: str) -> dict[str, Any] | None:
        full = f"{company_code.upper()}:{key}"
        with self._lock:
            row = self.idempotency.get(full)
            return deepcopy(row) if row else None

    def put_idempotency(self, company_code: str, key: str, action: str, result: dict[str, Any]) -> dict[str, Any]:
        full = f"{company_code.upper()}:{key}"
        with self._lock:
            saved = {
                "idempotency_key": key,
                "company_code": company_code.upper(),
                "action": action,
                "result": deepcopy(result),
                "created_at": _now(),
            }
            self.idempotency[full] = saved
            return deepcopy(saved)

    def audit_event(self, row: dict[str, Any]) -> None:
        with self._lock:
            self._audit(row)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AttendanceOpsService:
    """HR/manager attendance operations on top of Wave 1 authority."""

    def __init__(
        self,
        store: Any | None = None,
        *,
        authority_service: Any | None = None,
        get_authority: AuthorityFn | None = None,
        scope_allows: ScopeFn | None = None,
        payroll_locked: PayrollLockFn | None = None,
        manager_configured: Callable[[str, str], bool] | None = None,
    ) -> None:
        self.store = store or InMemoryOpsStore()
        self._authority = authority_service
        self._get_authority = get_authority
        self.scope_allows = scope_allows or (lambda company, actor, emp: True)
        self.payroll_locked = payroll_locked or (lambda company, emp, d: False)
        self.manager_configured = manager_configured or (lambda company, actor: True)

    def authority_for(self, company_code: str | None = None) -> Any:
        if self._authority is not None:
            return self._authority
        if self._get_authority is not None:
            return self._get_authority(company_code)
        return authority.get_authority_service(company_code)

    def _deny_scope(self, company: str, actor: str, employee_key: str, *, actor_role: str = "manager") -> dict[str, Any] | None:
        actor_d = digits(actor)
        if actor_role == "manager" and not self.manager_configured(company, actor_d):
            return {"ok": False, "error": "manager_unconfigured", "actor_phone": actor_d}
        if not self.scope_allows(company, actor_d, employee_key):
            return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": employee_key}
        return None

    def _deny_self(self, actor: str, employee_phone: str | None, *, action: str) -> dict[str, Any] | None:
        a = digits(actor)
        e = digits(employee_phone)
        if a and e and a == e:
            return {"ok": False, "error": "manager_self_correction_denied", "action": action}
        return None

    def open_exception(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        kind: str,
        actor_phone: str | None = None,
        shift_key: str = "",
        projection: dict[str, Any] | None = None,
        source: str = "projection",
        source_ref: str | None = None,
        priority: str | None = None,
        owner_phone: str | None = None,
        due_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        actor_role: str = "hr",
    ) -> dict[str, Any]:
        company = company_code.upper()
        if not ops_enabled_for_company(company):
            return {"ok": False, "error": "ops_disabled"}
        if kind not in EXCEPTION_KINDS:
            return {"ok": False, "error": "invalid_exception_kind", "kind": kind}
        emp_key = str(employee.get("employee_key") or "")
        if not emp_key:
            return {"ok": False, "error": "employee_key_required"}
        if not ops_allowed_for(company, employee, employee_key=emp_key):
            return {"ok": False, "error": "ops_synthetic_only_denied", "employee_key": emp_key}
        actor = digits(actor_phone)
        if actor and actor_role == "manager":
            denied = self._deny_scope(company, actor, emp_key, actor_role=actor_role)
            if denied:
                return denied
            denied = self._deny_self(actor, employee.get("phone") or employee.get("employee_phone"), action="open_exception")
            if denied:
                return denied

        existing = self.store.find_open_exception(
            company_code=company,
            employee_key=emp_key,
            work_date=work_date,
            shift_key=shift_key,
            kind=kind,
        )
        if existing:
            return {"ok": True, "exception": existing, "deduped": True}

        pri = priority if priority in PRIORITIES else default_priority(kind)
        before = projection_snapshot(projection)
        row = self.store.insert_exception({
            "company_code": company,
            "employee_key": emp_key,
            "employee_phone": employee.get("phone") or employee.get("employee_phone"),
            "employee_name": employee.get("name") or employee.get("employee_name"),
            "work_date": work_date,
            "shift_key": shift_key,
            "projection_id": (projection or {}).get("projection_id"),
            "kind": kind,
            "status": "assigned" if owner_phone else "open",
            "priority": pri,
            "owner_phone": owner_phone,
            "due_at": due_at or default_due_at(pri),
            "source": source,
            "source_ref": source_ref,
            "before_values": before,
            "payroll_excluded": True,
            "metadata": {**(metadata or {}), "opened_by": actor},
        })
        return {"ok": True, "exception": row, "deduped": False}

    def sync_exceptions_from_projection(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        projection: dict[str, Any],
        actor_phone: str | None = None,
    ) -> dict[str, Any]:
        work_date = authority.parse_date(projection.get("work_date")) or date.today()
        shift_key = authority.shift_key_of(projection.get("shift_key"))
        kinds = classify_projection_exceptions(projection)
        opened = []
        for kind in kinds:
            res = self.open_exception(
                company_code=company_code,
                employee=employee,
                work_date=work_date,
                kind=kind,
                actor_phone=actor_phone,
                shift_key=shift_key,
                projection=projection,
                source="projection",
                actor_role="hr",
            )
            if res.get("ok"):
                opened.append(res["exception"])
        return {"ok": True, "kinds": kinds, "exceptions": opened}

    def assign_exception(
        self,
        *,
        company_code: str,
        exception_id: str,
        owner_phone: str,
        actor_phone: str,
        expected_row_version: int,
        priority: str | None = None,
        due_at: datetime | None = None,
        actor_role: str = "hr",
    ) -> dict[str, Any]:
        company = company_code.upper()
        exc = self.store.get_exception(exception_id, company)
        if not exc:
            return {"ok": False, "error": "exception_not_found"}
        if actor_role == "manager":
            denied = self._deny_scope(company, actor_phone, str(exc["employee_key"]), actor_role=actor_role)
            if denied:
                return denied
        fields: dict[str, Any] = {
            "owner_phone": owner_phone,
            "status": "assigned" if exc.get("status") in {"open", "reopened"} else exc.get("status"),
        }
        if priority in PRIORITIES:
            fields["priority"] = priority
        if due_at is not None:
            fields["due_at"] = due_at
        updated = self.store.update_exception(
            exception_id, company, expected_row_version=expected_row_version, **fields
        )
        if updated and updated.get("__conflict__"):
            return {"ok": False, "error": "stale_row_version", "current": updated.get("current")}
        if not updated:
            return {"ok": False, "error": "exception_not_found"}
        self.store.audit_event({
            "company_code": company,
            "entity_type": "exception",
            "entity_id": exception_id,
            "event_type": "exception_assigned",
            "payload": {"owner_phone": digits(owner_phone)},
            "created_by_phone": digits(actor_phone),
        })
        return {"ok": True, "exception": updated}

    def request_correction(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        requested_by_phone: str,
        changes: dict[str, Any],
        shift: dict[str, Any] | None = None,
        exception_id: str | None = None,
        actor_is_manager: bool = False,
        actor_role: str = "manager",
        kind: str | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        if not ops_enabled_for_company(company):
            return {"ok": False, "error": "ops_disabled"}
        emp_key = str(employee.get("employee_key") or "")
        actor = digits(requested_by_phone)
        emp_phone = digits(employee.get("phone") or employee.get("employee_phone"))
        if not ops_allowed_for(company, employee, employee_key=emp_key, phone=emp_phone):
            return {"ok": False, "error": "ops_synthetic_only_denied", "employee_key": emp_key}

        if actor_is_manager or actor_role == "manager":
            denied = self._deny_scope(company, actor, emp_key, actor_role="manager")
            if denied:
                return denied
            denied = self._deny_self(actor, emp_phone, action="request_correction")
            if denied:
                return denied

        if self.payroll_locked(company, emp_key, work_date):
            return {"ok": False, "error": "payroll_period_locked", "work_date": work_date.isoformat()}

        auth = self.authority_for(company)
        req = auth.request_correction(
            company_code=company,
            employee=employee,
            work_date=work_date,
            requested_by_phone=actor,
            changes=changes,
            shift=shift,
            actor_is_manager=True if actor_is_manager or actor_role == "manager" else False,
        )
        if not req.get("ok"):
            return req

        skey = authority.shift_key_of(shift.get("shift_id") if shift else None)
        current = auth.store.get_current_projection(
            company_code=company,
            employee_key=emp_key,
            work_date=work_date,
            shift_key=skey,
        )
        resolved_kind = kind
        if not resolved_kind and exception_id:
            exc = self.store.get_exception(exception_id, company)
            resolved_kind = (exc or {}).get("kind")
        if not resolved_kind:
            kinds = classify_projection_exceptions(current or {})
            resolved_kind = kinds[0] if kinds else "incomplete_session"

        high_risk = resolved_kind in dual_approval_kinds() or str(changes.get("status") or "") == "absent"
        case = self.store.insert_case({
            "company_code": company,
            "exception_id": exception_id,
            "correction_id": req["correction"]["correction_id"],
            "employee_key": emp_key,
            "employee_phone": emp_phone,
            "work_date": work_date,
            "shift_key": skey,
            "status": "requested",
            "kind": resolved_kind,
            "high_risk": high_risk,
            "dual_approval_required": high_risk,
            "requested_by_phone": actor,
            "requested_changes": changes,
            "before_snapshot": projection_snapshot(current),
            "metadata": {"actor_is_manager": actor_is_manager or actor_role == "manager"},
        })
        if exception_id:
            exc = self.store.get_exception(exception_id, company)
            if exc:
                self.store.update_exception(
                    exception_id,
                    company,
                    expected_row_version=int(exc["row_version"]),
                    status="in_review",
                )
        return {"ok": True, "correction": req["correction"], "case": case}

    def review_case(
        self,
        *,
        company_code: str,
        case_id: str,
        decision: str,
        decided_by_phone: str,
        expected_row_version: int,
        decision_note: str | None = None,
        actor_role: str = "manager",
        employee: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Approve or reject without applying punches. Apply is a separate step."""
        company = company_code.upper()
        decision_n = str(decision or "").lower().strip()
        if decision_n not in {"approved", "rejected"}:
            return {"ok": False, "error": "invalid_decision", "decision": decision}
        case = self.store.get_case(case_id, company)
        if not case:
            return {"ok": False, "error": "case_not_found"}
        if case.get("status") not in {"requested", "under_review", "pending_dual_approval", "reopened"}:
            return {"ok": False, "error": "case_not_reviewable", "case": case}

        actor = digits(decided_by_phone)
        emp_phone = digits((employee or {}).get("phone") or (employee or {}).get("employee_phone") or case.get("employee_phone"))
        if actor_role == "manager":
            denied = self._deny_scope(company, actor, str(case["employee_key"]), actor_role="manager")
            if denied:
                return denied
            denied = self._deny_self(actor, emp_phone, action="review_case")
            if denied:
                return denied

        if decision_n == "rejected":
            updated = self.store.update_case(
                case_id,
                company,
                expected_row_version=expected_row_version,
                status="rejected",
                decision_note=decision_note,
                first_approver_phone=actor if not case.get("first_approver_phone") else case.get("first_approver_phone"),
            )
            if updated and updated.get("__conflict__"):
                return {"ok": False, "error": "stale_row_version", "current": updated.get("current")}
            # Mirror reject onto authority correction record without applying punches.
            auth = self.authority_for(company)
            auth.review_correction(
                company_code=company,
                correction_id=str(case["correction_id"]),
                decision="rejected",
                decided_by_phone=actor,
                decision_note=decision_note,
                employee=employee,
            )
            if case.get("exception_id"):
                exc = self.store.get_exception(str(case["exception_id"]), company)
                if exc:
                    self.store.update_exception(
                        str(case["exception_id"]),
                        company,
                        expected_row_version=int(exc["row_version"]),
                        status="rejected",
                    )
            self.store.audit_event({
                "company_code": company,
                "entity_type": "case",
                "entity_id": case_id,
                "event_type": "correction_rejected",
                "payload": {"note": decision_note},
                "created_by_phone": actor,
            })
            return {"ok": True, "case": updated, "applied": False}

        # Approve path — dual approval for high-risk
        if case.get("dual_approval_required"):
            first = digits(case.get("first_approver_phone"))
            if not first:
                updated = self.store.update_case(
                    case_id,
                    company,
                    expected_row_version=expected_row_version,
                    status="pending_dual_approval",
                    first_approver_phone=actor,
                    decision_note=decision_note,
                )
                if updated and updated.get("__conflict__"):
                    return {"ok": False, "error": "stale_row_version", "current": updated.get("current")}
                if case.get("exception_id"):
                    exc = self.store.get_exception(str(case["exception_id"]), company)
                    if exc:
                        self.store.update_exception(
                            str(case["exception_id"]),
                            company,
                            expected_row_version=int(exc["row_version"]),
                            status="pending_dual_approval",
                        )
                self.store.audit_event({
                    "company_code": company,
                    "entity_type": "case",
                    "entity_id": case_id,
                    "event_type": "dual_approval_first",
                    "payload": {"first_approver": actor},
                    "created_by_phone": actor,
                })
                return {"ok": True, "case": updated, "dual_pending": True, "applied": False}
            if actor == first:
                return {"ok": False, "error": "dual_approval_requires_distinct_approver", "first_approver_phone": first}
            updated = self.store.update_case(
                case_id,
                company,
                expected_row_version=expected_row_version,
                status="approved",
                second_approver_phone=actor,
                decision_note=decision_note,
            )
        else:
            updated = self.store.update_case(
                case_id,
                company,
                expected_row_version=expected_row_version,
                status="approved",
                first_approver_phone=actor,
                decision_note=decision_note,
            )
        if updated and updated.get("__conflict__"):
            return {"ok": False, "error": "stale_row_version", "current": updated.get("current")}
        self.store.audit_event({
            "company_code": company,
            "entity_type": "case",
            "entity_id": case_id,
            "event_type": "correction_approved",
            "payload": {"note": decision_note, "dual": bool(case.get("dual_approval_required"))},
            "created_by_phone": actor,
        })
        return {"ok": True, "case": updated, "applied": False, "ready_to_apply": True}

    def apply_case(
        self,
        *,
        company_code: str,
        case_id: str,
        applied_by_phone: str,
        expected_row_version: int,
        idempotency_key: str,
        employee: dict[str, Any],
        shift: dict[str, Any] | None = None,
        actor_role: str = "hr",
    ) -> dict[str, Any]:
        company = company_code.upper()
        actor = digits(applied_by_phone)
        prior = self.store.get_idempotency(company, idempotency_key)
        if prior:
            return {"ok": True, "idempotent_replay": True, **(prior.get("result") or {})}

        case = self.store.get_case(case_id, company)
        if not case:
            return {"ok": False, "error": "case_not_found"}
        if case.get("status") == "applied":
            result = {"ok": True, "case": case, "applied": True, "already_applied": True}
            self.store.put_idempotency(company, idempotency_key, "apply_case", result)
            return result
        if case.get("status") != "approved":
            return {"ok": False, "error": "case_not_approved", "case": case}

        emp_key = str(case["employee_key"])
        emp_phone = digits(employee.get("phone") or employee.get("employee_phone") or case.get("employee_phone"))
        if actor_role == "manager":
            denied = self._deny_scope(company, actor, emp_key, actor_role="manager")
            if denied:
                return denied
            denied = self._deny_self(actor, emp_phone, action="apply_case")
            if denied:
                return denied

        work_date = authority.parse_date(case["work_date"]) or date.today()
        if self.payroll_locked(company, emp_key, work_date):
            return {"ok": False, "error": "payroll_period_locked", "work_date": work_date.isoformat()}

        auth = self.authority_for(company)
        try:
            applied = auth.review_correction(
                company_code=company,
                correction_id=str(case["correction_id"]),
                decision="approved",
                decided_by_phone=actor,
                decision_note=case.get("decision_note") or "ops_wave3_apply",
                employee=employee,
                shift=shift,
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if "unique" in msg or "duplicate" in msg:
                refreshed = self.store.get_case(case_id, company)
                if refreshed and refreshed.get("status") == "applied":
                    result = {
                        "ok": True,
                        "case": refreshed,
                        "applied": True,
                        "already_applied": True,
                        "before": refreshed.get("before_snapshot"),
                        "after": refreshed.get("after_snapshot"),
                    }
                    self.store.put_idempotency(company, idempotency_key, "apply_case", result)
                    return result
                # Peer may still be committing — treat as conflict fail-closed for distinct keys;
                # for same idempotency key, wait for peer row.
                prior2 = self.store.get_idempotency(company, idempotency_key)
                if prior2:
                    return {"ok": True, "idempotent_replay": True, **(prior2.get("result") or {})}
                return {"ok": False, "error": "concurrent_apply_conflict", "detail": str(exc)[:200]}
            raise
        if not applied.get("ok"):
            # Concurrent apply: peer may have already approved/applied the correction.
            refreshed = self.store.get_case(case_id, company)
            if refreshed and refreshed.get("status") == "applied":
                result = {
                    "ok": True,
                    "case": refreshed,
                    "applied": True,
                    "already_applied": True,
                    "before": refreshed.get("before_snapshot"),
                    "after": refreshed.get("after_snapshot"),
                }
                self.store.put_idempotency(company, idempotency_key, "apply_case", result)
                return result
            if applied.get("error") == "correction_not_open":
                prior2 = self.store.get_idempotency(company, idempotency_key)
                if prior2:
                    return {"ok": True, "idempotent_replay": True, **(prior2.get("result") or {})}
                # Correction already decided by peer; if our case is still approved, peer apply in flight.
                if refreshed and refreshed.get("status") == "approved":
                    return {"ok": False, "error": "concurrent_apply_conflict", "case": refreshed}
            return applied

        after = projection_snapshot(applied.get("projection"))
        updated = self.store.update_case(
            case_id,
            company,
            expected_row_version=expected_row_version,
            status="applied",
            applied_at=_now(),
            apply_idempotency_key=idempotency_key,
            after_snapshot=after,
            resulting_projection_id=(applied.get("projection") or {}).get("projection_id"),
        )
        if updated and updated.get("__conflict__"):
            # Peer won the case row_version race — treat as already applied if now applied.
            refreshed = self.store.get_case(case_id, company)
            if refreshed and refreshed.get("status") == "applied":
                result = {
                    "ok": True,
                    "case": refreshed,
                    "applied": True,
                    "already_applied": True,
                    "before": refreshed.get("before_snapshot"),
                    "after": refreshed.get("after_snapshot"),
                }
                self.store.put_idempotency(company, idempotency_key, "apply_case", result)
                return result
            return {"ok": False, "error": "stale_row_version", "current": updated.get("current")}

        if case.get("exception_id"):
            exc = self.store.get_exception(str(case["exception_id"]), company)
            if exc:
                self.store.update_exception(
                    str(case["exception_id"]),
                    company,
                    expected_row_version=int(exc["row_version"]),
                    status="resolved",
                    after_values=after,
                    payroll_excluded=not bool((applied.get("projection") or {}).get("payroll_eligible")),
                )

        result = {
            "ok": True,
            "case": updated,
            "projection": applied.get("projection"),
            "compat": applied.get("compat"),
            "applied": True,
            "before": case.get("before_snapshot"),
            "after": after,
        }
        self.store.put_idempotency(company, idempotency_key, "apply_case", result)
        self.store.audit_event({
            "company_code": company,
            "entity_type": "case",
            "entity_id": case_id,
            "event_type": "correction_applied",
            "payload": {"idempotency_key": idempotency_key, "after": after},
            "created_by_phone": actor,
        })
        return result

    def raise_dispute(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        raised_by_phone: str,
        reason: str,
        exception_id: str | None = None,
        case_id: str | None = None,
        shift_key: str = "",
    ) -> dict[str, Any]:
        company = company_code.upper()
        emp_key = str(employee.get("employee_key") or "")
        dispute = self.store.insert_dispute({
            "company_code": company,
            "exception_id": exception_id,
            "case_id": case_id,
            "employee_key": emp_key,
            "work_date": work_date,
            "shift_key": shift_key,
            "status": "open",
            "raised_by_phone": raised_by_phone,
            "reason": reason,
        })
        if case_id:
            case = self.store.get_case(case_id, company)
            if case:
                self.store.update_case(
                    case_id,
                    company,
                    expected_row_version=int(case["row_version"]),
                    status="disputed",
                )
        if exception_id:
            exc = self.store.get_exception(exception_id, company)
            if exc:
                self.store.update_exception(
                    exception_id,
                    company,
                    expected_row_version=int(exc["row_version"]),
                    status="in_review",
                    payroll_excluded=True,
                )
        # Mark authority projection disputed when possible
        auth = self.authority_for(company)
        current = auth.store.get_current_projection(
            company_code=company,
            employee_key=emp_key,
            work_date=work_date,
            shift_key=authority.shift_key_of(shift_key),
        )
        if current:
            auth.reproject_day(
                company_code=company,
                employee=employee,
                work_date=work_date,
                shift={"shift_id": current.get("shift_id"), "shift_date": work_date,
                       "start_time": current.get("scheduled_start"), "end_time": current.get("scheduled_end")},
                forced_status=current.get("status") if current.get("status") in {"absent", "approved_leave"} else None,
                created_by_phone=raised_by_phone,
                manual_correction=bool(current.get("manual_correction")),
                approval_status="disputed",
                metadata={"dispute_id": dispute["dispute_id"], "reason": reason},
            )
        return {"ok": True, "dispute": dispute}

    def resolve_dispute(
        self,
        *,
        company_code: str,
        dispute_id: str,
        resolution: str,
        resolved_by_phone: str,
        expected_row_version: int,
        resolution_note: str | None = None,
        actor_role: str = "manager",
        employee: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        resolution_n = str(resolution or "").lower().strip()
        if resolution_n not in {"upheld", "overturned"}:
            return {"ok": False, "error": "invalid_resolution"}
        dispute = self.store.get_dispute(dispute_id, company)
        if not dispute:
            return {"ok": False, "error": "dispute_not_found"}
        if dispute.get("status") not in {"open", "under_review"}:
            return {"ok": False, "error": "dispute_not_open", "dispute": dispute}

        actor = digits(resolved_by_phone)
        if actor_role == "manager":
            denied = self._deny_scope(company, actor, str(dispute["employee_key"]), actor_role="manager")
            if denied:
                return denied
            emp_phone = digits((employee or {}).get("phone") or (employee or {}).get("employee_phone"))
            denied = self._deny_self(actor, emp_phone or None, action="resolve_dispute")
            if denied:
                return denied

        updated = self.store.update_dispute(
            dispute_id,
            company,
            expected_row_version=expected_row_version,
            status=resolution_n,
            resolution_note=resolution_note,
            resolved_by_phone=actor,
            resolved_at=_now(),
        )
        if updated and updated.get("__conflict__"):
            return {"ok": False, "error": "stale_row_version", "current": updated.get("current")}
        self.store.audit_event({
            "company_code": company,
            "entity_type": "dispute",
            "entity_id": dispute_id,
            "event_type": f"dispute_{resolution_n}",
            "payload": {"note": resolution_note},
            "created_by_phone": actor,
        })
        return {"ok": True, "dispute": updated}

    def reopen_exception(
        self,
        *,
        company_code: str,
        exception_id: str,
        actor_phone: str,
        expected_row_version: int,
        evidence_note: str,
        actor_role: str = "hr",
    ) -> dict[str, Any]:
        company = company_code.upper()
        exc = self.store.get_exception(exception_id, company)
        if not exc:
            return {"ok": False, "error": "exception_not_found"}
        if exc.get("status") not in {"resolved", "rejected", "closed"}:
            return {"ok": False, "error": "exception_not_reopenable", "exception": exc}
        if actor_role == "manager":
            denied = self._deny_scope(company, actor_phone, str(exc["employee_key"]), actor_role="manager")
            if denied:
                return denied
        work_date = authority.parse_date(exc["work_date"]) or date.today()
        if self.payroll_locked(company, str(exc["employee_key"]), work_date):
            return {"ok": False, "error": "payroll_period_locked"}

        updated = self.store.update_exception(
            exception_id,
            company,
            expected_row_version=expected_row_version,
            status="reopened",
            payroll_excluded=True,
            metadata={"reopen_evidence": evidence_note, "reopened_by": digits(actor_phone)},
        )
        if updated and updated.get("__conflict__"):
            return {"ok": False, "error": "stale_row_version", "current": updated.get("current")}
        for case in self.store.list_cases_for_exception(exception_id, company):
            if case.get("status") in {"applied", "rejected", "disputed"}:
                self.store.update_case(
                    case["case_id"],
                    company,
                    expected_row_version=int(case["row_version"]),
                    status="reopened",
                    metadata={"reopen_evidence": evidence_note},
                )
        self.store.audit_event({
            "company_code": company,
            "entity_type": "exception",
            "entity_id": exception_id,
            "event_type": "exception_reopened",
            "payload": {"evidence_note": evidence_note},
            "created_by_phone": digits(actor_phone),
        })
        return {"ok": True, "exception": updated}

    def add_comment(
        self,
        *,
        company_code: str,
        entity_type: str,
        entity_id: str,
        author_phone: str,
        body: str,
    ) -> dict[str, Any]:
        if entity_type not in {"exception", "case", "dispute"}:
            return {"ok": False, "error": "invalid_entity_type"}
        row = self.store.add_comment({
            "company_code": company_code,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "author_phone": author_phone,
            "body": body,
        })
        return {"ok": True, "comment": row}

    def add_attachment(
        self,
        *,
        company_code: str,
        entity_type: str,
        entity_id: str,
        uploaded_by_phone: str,
        filename: str,
        storage_ref: str,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        if entity_type not in {"exception", "case", "dispute"}:
            return {"ok": False, "error": "invalid_entity_type"}
        # Refs only — never store blob secrets
        if any(x in storage_ref.lower() for x in ("password", "secret", "token=")):
            return {"ok": False, "error": "invalid_storage_ref"}
        row = self.store.add_attachment({
            "company_code": company_code,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "uploaded_by_phone": uploaded_by_phone,
            "filename": filename,
            "storage_ref": storage_ref,
            "content_type": content_type,
        })
        return {"ok": True, "attachment": row}

    def list_queue(
        self,
        *,
        company_code: str,
        actor_phone: str | None = None,
        actor_role: str = "hr",
        status: str | None = None,
        kind: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        keys = employee_keys
        if actor_role == "manager" and actor_phone:
            if not self.manager_configured(company, digits(actor_phone)):
                return {"ok": False, "error": "manager_unconfigured", "exceptions": [], "count": 0}
            # Scope filter applied by caller via employee_keys; if None, refuse broad list.
            if keys is None:
                return {"ok": False, "error": "manager_scope_required", "exceptions": [], "count": 0}
        rows = self.store.list_exceptions(
            company_code=company,
            status=status,
            kind=kind,
            employee_keys=keys,
        )
        cases = self.store.list_cases(company_code=company, employee_keys=keys)
        disputes = self.store.list_disputes(company_code=company, employee_keys=keys)
        return {
            "ok": True,
            "exceptions": rows,
            "count": len(rows),
            "cases": cases,
            "disputes": disputes,
            "case_count": len(cases),
            "dispute_count": len(disputes),
        }


# ---------------------------------------------------------------------------
# Module singleton
# ---------------------------------------------------------------------------

_LOCK = threading.RLock()
_SERVICE: AttendanceOpsService | None = None


def get_ops_service(
    *,
    store: Any | None = None,
    authority_service: Any | None = None,
    get_authority: AuthorityFn | None = None,
    scope_allows: ScopeFn | None = None,
    payroll_locked: PayrollLockFn | None = None,
    manager_configured: Callable[[str, str], bool] | None = None,
    reset: bool = False,
) -> AttendanceOpsService:
    global _SERVICE
    if store is not None or authority_service is not None:
        return AttendanceOpsService(
            store=store,
            authority_service=authority_service,
            get_authority=get_authority,
            scope_allows=scope_allows,
            payroll_locked=payroll_locked,
            manager_configured=manager_configured,
        )
    with _LOCK:
        if _SERVICE is None or reset:
            if ops_store_mode() == "postgres":
                import attendance_ops_postgres as ops_pg

                _SERVICE = AttendanceOpsService(
                    store=ops_pg.PostgresOpsStore(),
                    get_authority=get_authority or authority.get_authority_service,
                    scope_allows=scope_allows,
                    payroll_locked=payroll_locked,
                    manager_configured=manager_configured,
                )
            else:
                _SERVICE = AttendanceOpsService(
                    get_authority=get_authority or authority.get_authority_service,
                    scope_allows=scope_allows,
                    payroll_locked=payroll_locked,
                    manager_configured=manager_configured,
                )
        return _SERVICE


def reset_ops_services_for_tests() -> None:
    global _SERVICE
    with _LOCK:
        _SERVICE = None


def state_model_doc() -> dict[str, Any]:
    return {
        "exception_kinds": sorted(EXCEPTION_KINDS),
        "exception_statuses": sorted(EXCEPTION_STATUSES),
        "case_statuses": sorted(CASE_STATUSES),
        "dispute_statuses": sorted(DISPUTE_STATUSES),
        "priorities": sorted(PRIORITIES),
        "rules": {
            "raw_punches_immutable": True,
            "corrections_create_new_projection_versions": True,
            "incomplete_or_disputed_excluded_from_payroll": True,
            "locked_payroll_snapshots_immutable": True,
            "leave_reversal_preserves_later_manual_corrections": True,
            "no_manager_self_correction_or_approval": True,
            "approve_reject_apply_separated": True,
            "optimistic_concurrency": "row_version",
            "idempotent_apply": "apply_idempotency_key",
        },
        "dual_approval_kinds": sorted(dual_approval_kinds()),
    }
