"""Payroll Authority P2 — Attendance + Leave → immutable payroll input snapshots.

Goal: lock the correct facts for future Mode A Wathefni-authoritative payroll.
Does NOT calculate OT/sick/PH/PIFSS money. Does NOT unlock Mode A seal.
payment_processing remains disabled. SYNTHETIC_ONLY remains.

Readiness: assembling | needs_review | ready | locked | superseded
attendance_payroll_mode: required | informational | ignored
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import payroll_authority_snapshot_p1 as p1
import payroll_authority_wave1 as pyw1

PAYROLL_AUTHORITY_P2_VERSION = "1.0.0"
INPUT_SNAPSHOT_SCHEMA = "wathefni.payroll_input_snapshot.v1"
STATUS_ASSEMBLING = "assembling"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_READY = "ready"
STATUS_LOCKED = "locked"
STATUS_SUPERSEDED = "superseded"
ATT_MODE_REQUIRED = "required"
ATT_MODE_INFO = "informational"
ATT_MODE_IGNORED = "ignored"
ATT_MODES = (ATT_MODE_REQUIRED, ATT_MODE_INFO, ATT_MODE_IGNORED)
LEAVE_PAY_CLASS = {
    "unpaid": "unpaid_leave",
    "unpaid_leave": "unpaid_leave",
    "sick": "sick_leave",
    "annual": "paid_leave",
    "paid": "paid_leave",
    "maternity": "paid_leave",
    "paternity": "paid_leave",
    "hajj": "paid_leave",
    "marriage": "paid_leave",
    "bereavement": "paid_leave",
    "other": "other_leave",
}

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_input_snapshot_p2_v1.sql"
SCHEMA_SQL = SCHEMA_SQL_PATH.read_text(encoding="utf-8") if SCHEMA_SQL_PATH.exists() else ""
_SCHEMA_READY = False
_ON = ("1", "true", "yes", "on")
DEFAULT_SYNTHETIC_KEY_MARKERS = (
    "PYW1", "PYW2A", "PYW2B", "PYW3", "PYAUTH", "PYP1", "PYP2", "PYINPUT",
    "ATTW1C", "ATTW2C", "ATTW3", "W1C-SYNTH|", "W2C-SYNTH|", "W3-SYNTH|",
)
DEFAULT_WEEKEND_DAYS = ("fri", "sat")  # Kuwait default; company-overridable via policy_context


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def payroll_authority_p2_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P2", default=True)


def payroll_authority_p2_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_authority_p2_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P2_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_authority_p2_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def is_p2_synthetic_employee(*, employee_key: str | None = None) -> bool:
    key = str(employee_key or "")
    for marker in synthetic_key_markers():
        if marker and marker in key:
            return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_authority_p2_version": PAYROLL_AUTHORITY_P2_VERSION,
        "input_snapshot_schema": INPUT_SNAPSHOT_SCHEMA,
        "money_calculated": False,
        "mode_a_wathefni_seal_unlocked": False,
        "ot_sick_ph_money_calculated": False,
        "pifss_formulas_implemented": False,
        "statutory_formulas_implemented": False,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payment_date_invented": False,
        "synthetic_only": payroll_authority_p2_synthetic_only(),
        "kuwait_first": True,
        "facts_only": True,
        "p1_authority_unchanged": True,
        "payslips_p0_p01_unchanged": True,
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "locked_inputs_immutable": True,
        "source_edits_require_new_version": True,
        "history_never_deleted": True,
        "assemble_idempotent": True,
        "unapproved_leave_excluded": True,
        "unpaid_leave_suppresses_absence_double_count": True,
        "ot_rest_ph_are_facts_not_money": True,
        "fail_closed_when_attendance_required_and_unresolved": True,
        "informational_attendance_does_not_block": True,
    }


def overlap_precedence_rules() -> dict[str, Any]:
    return {
        "only_approved_leave_affects_payroll": True,
        "pending_rejected_cancelled_excluded": True,
        "approved_unpaid_leave_suppresses_attendance_absence": True,
        "paid_leave_not_treated_as_unpaid_absence": True,
        "attendance_absence_plus_unpaid_leave_no_double_count": True,
        "ot_rest_day_ph_work_distinct_facts": True,
        "overnight_shift_anchored_to_shift_work_date": True,
        "timezone_default": "Asia/Kuwait",
    }


def ensure_payroll_input_snapshot_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_012
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        pyw1.ensure_payroll_wave1_schema(cur)
        p1.ensure_payroll_authority_snapshot_schema(cur)
        cur.execute(SCHEMA_SQL)
        _SCHEMA_READY = True
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        except Exception:
            pass


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows(cur: Any) -> list[dict[str, Any]]:
    fetched = cur.fetchall() or []
    if not fetched:
        return []
    if isinstance(fetched[0], dict):
        return [dict(r) for r in fetched]
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in fetched]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def fingerprint_payload(payload: Any) -> str:
    raw = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_audit_reason(reason: str | None) -> dict[str, Any] | None:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    return None


def _refuse_nonsynthetic(employee_key: str, *, cur: Any = None, company_code: str | None = None) -> dict[str, Any] | None:
    if payroll_authority_p2_synthetic_only() and not is_p2_synthetic_employee(employee_key=employee_key):
        if cur is not None and company_code:
            try:
                import payroll_authority_production_p6 as p6

                if p6.employee_production_mutations_allowed(
                    cur, company_code=company_code, employee_key=employee_key
                ):
                    return None
            except Exception:
                pass
        return {"ok": False, "error": "payroll_authority_p2_synthetic_only", "employee_key": employee_key}
    return None


def _record_event(
    cur: Any,
    *,
    company_code: str,
    input_snapshot_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_input_snapshot_events
          (input_snapshot_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            input_snapshot_id,
            (company_code or "").upper(),
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    s = str(value)[:10]
    if not s or s == "None":
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _daterange(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _weekday_key(d: date) -> str:
    return ("mon", "tue", "wed", "thu", "fri", "sat", "sun")[d.weekday()]


def resolve_attendance_payroll_mode(
    cur: Any, *, company_code: str, period: dict[str, Any] | None = None
) -> str:
    if period:
        pinned = str(period.get("attendance_payroll_mode") or "").strip().lower()
        if pinned in ATT_MODES:
            return pinned
    settings = pyw1.ensure_company_settings(cur, company_code=company_code)
    mode = str(settings.get("attendance_payroll_mode") or "").strip().lower()
    if mode in ATT_MODES:
        return mode
    # Default: when source is approved_snapshots, attendance is required for Mode A path;
    # companies can set informational/ignored explicitly.
    return ATT_MODE_REQUIRED


def set_attendance_payroll_mode(
    cur: Any,
    *,
    company_code: str,
    mode: str,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    m = str(mode or "").strip().lower()
    if m not in ATT_MODES:
        return {"ok": False, "error": "invalid_attendance_payroll_mode", "allowed": list(ATT_MODES)}
    ensure_payroll_input_snapshot_schema(cur)
    pyw1.ensure_company_settings(cur, company_code=company_code)
    cur.execute(
        """
        UPDATE payroll_company_settings
        SET attendance_payroll_mode=%s, updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s
        RETURNING *
        """,
        (m, digits_phone(actor_phone), (company_code or "").upper()),
    )
    row = _row(cur)
    return {"ok": True, "settings": _json_safe(row), **honesty_payload()}


def get_current_input_snapshot(
    cur: Any, *, company_code: str, period_start: str | date, period_end: str | date
) -> dict[str, Any] | None:
    ensure_payroll_input_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_input_snapshots
        WHERE company_code=%s AND period_start=%s AND period_end=%s
          AND status IN ('assembling','needs_review','ready','locked')
        ORDER BY assembled_at DESC LIMIT 1
        """,
        ((company_code or "").upper(), str(period_start)[:10], str(period_end)[:10]),
    )
    return _row(cur)


def get_input_snapshot_by_id(
    cur: Any, *, company_code: str, input_snapshot_id: str
) -> dict[str, Any] | None:
    ensure_payroll_input_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_input_snapshots
        WHERE company_code=%s AND input_snapshot_id=%s
        """,
        ((company_code or "").upper(), input_snapshot_id),
    )
    return _row(cur)


def list_input_snapshot_employees(
    cur: Any, *, company_code: str, input_snapshot_id: str
) -> list[dict[str, Any]]:
    ensure_payroll_input_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_input_snapshot_employees
        WHERE company_code=%s AND input_snapshot_id=%s
        ORDER BY employee_key
        """,
        ((company_code or "").upper(), input_snapshot_id),
    )
    return _rows(cur)


def list_input_snapshot_lines(
    cur: Any,
    *,
    company_code: str,
    input_snapshot_id: str,
    employee_key: str | None = None,
) -> list[dict[str, Any]]:
    ensure_payroll_input_snapshot_schema(cur)
    if employee_key:
        cur.execute(
            """
            SELECT * FROM payroll_input_snapshot_lines
            WHERE company_code=%s AND input_snapshot_id=%s AND employee_key=%s
            ORDER BY sort_order, fact_date NULLS LAST, created_at
            """,
            ((company_code or "").upper(), input_snapshot_id, employee_key),
        )
    else:
        cur.execute(
            """
            SELECT * FROM payroll_input_snapshot_lines
            WHERE company_code=%s AND input_snapshot_id=%s
            ORDER BY employee_key, sort_order, fact_date NULLS LAST
            """,
            ((company_code or "").upper(), input_snapshot_id),
        )
    return _rows(cur)


def list_input_snapshot_issues(
    cur: Any, *, company_code: str, input_snapshot_id: str
) -> list[dict[str, Any]]:
    ensure_payroll_input_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_input_snapshot_issues
        WHERE company_code=%s AND input_snapshot_id=%s
        ORDER BY CASE severity WHEN 'blocker' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                 employee_key NULLS LAST, fact_date NULLS LAST
        """,
        ((company_code or "").upper(), input_snapshot_id),
    )
    return _rows(cur)


def list_input_snapshot_events(
    cur: Any, *, company_code: str, limit: int = 50
) -> list[dict[str, Any]]:
    ensure_payroll_input_snapshot_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_input_snapshot_events
        WHERE company_code=%s
        ORDER BY created_at DESC LIMIT %s
        """,
        ((company_code or "").upper(), max(1, min(int(limit), 500))),
    )
    return _rows(cur)


def _load_period(cur: Any, *, company_code: str, period_id: str | None, period_start: date, period_end: date) -> dict[str, Any]:
    company = (company_code or "").upper()
    if period_id:
        cur.execute(
            "SELECT * FROM payroll_periods WHERE company_code=%s AND period_id=%s",
            (company, period_id),
        )
        row = _row(cur)
        if row:
            return row
    cur.execute(
        """
        SELECT * FROM payroll_periods
        WHERE company_code=%s AND period_start=%s AND period_end=%s
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, period_start, period_end),
    )
    return _row(cur) or {
        "period_id": None,
        "period_start": period_start,
        "period_end": period_end,
        "attendance_input_source": "approved_snapshots",
    }


def _load_employees(
    cur: Any,
    *,
    company_code: str,
    employee_keys: list[str] | None,
) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    if employee_keys:
        keys = [str(k) for k in employee_keys]
        cur.execute(
            """
            SELECT employee_key, phone, name AS full_name, hire_date, start_date,
                   employment_status AS status, profile, raw_json
            FROM employees
            WHERE company_code=%s AND employee_key = ANY(%s)
            """,
            (company, keys),
        )
        found = {str(r.get("employee_key")): r for r in _rows(cur)}
        out = []
        for k in keys:
            if k in found:
                out.append(found[k])
            else:
                out.append({"employee_key": k})
        return out
    cur.execute(
        """
        SELECT DISTINCT e.employee_key, e.phone, e.name AS full_name, e.hire_date, e.start_date,
               e.employment_status AS status, e.profile, e.raw_json
        FROM employees e
        JOIN payroll_compensation_contracts c
          ON c.company_code=e.company_code AND c.employee_key=e.employee_key AND c.status='approved'
        WHERE e.company_code=%s
        ORDER BY e.employee_key
        LIMIT 500
        """,
        (company,),
    )
    return _rows(cur)


def _emp_meta(emp: dict[str, Any]) -> dict[str, Any]:
    for key in ("profile", "raw_json", "metadata"):
        meta = emp.get(key)
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        if isinstance(meta, dict) and meta:
            return meta
    return {}


def _employment_bounds(emp: dict[str, Any], period_start: date, period_end: date) -> dict[str, Any]:
    meta = _emp_meta(emp)
    hire = (
        _parse_date(emp.get("start_date"))
        or _parse_date(emp.get("hire_date"))
        or _parse_date(meta.get("employment_start"))
        or _parse_date(meta.get("hire_date"))
        or _parse_date(meta.get("start_date"))
    )
    leave = (
        _parse_date(emp.get("end_date"))
        or _parse_date(emp.get("termination_date"))
        or _parse_date(meta.get("employment_end"))
        or _parse_date(meta.get("termination_date"))
        or _parse_date(meta.get("end_date"))
    )
    active_start = max(period_start, hire) if hire and hire > period_start else period_start
    active_end = min(period_end, leave) if leave and leave < period_end else period_end
    if hire and hire > period_end:
        active_start = period_end
        active_end = period_start - timedelta(days=1)  # empty span
    if leave and leave < period_start:
        active_start = period_end
        active_end = period_start - timedelta(days=1)
    return {
        "employment_start": hire,
        "employment_end": leave,
        "active_start": active_start,
        "active_end": active_end,
        "mid_period_hire": bool(hire and period_start < hire <= period_end),
        "mid_period_leaver": bool(leave and period_start <= leave < period_end),
        "active": active_start <= active_end,
    }


def _load_contracts_for_employee(
    cur: Any, *, company_code: str, employee_key: str, period_start: date, period_end: date
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM payroll_compensation_contracts
        WHERE company_code=%s AND employee_key=%s AND status='approved'
          AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to >= %s)
        ORDER BY effective_from ASC
        """,
        ((company_code or "").upper(), employee_key, period_end, period_start),
    )
    return _rows(cur)


def _load_approved_attendance(
    cur: Any, *, company_code: str, period_start: date, period_end: date, employee_keys: list[str]
) -> list[dict[str, Any]]:
    # Prefer approved payroll snapshots when table exists
    try:
        cur.execute(
            """
            SELECT DISTINCT ON (employee_key, work_date, COALESCE(shift_key,'')) *
            FROM attendance_payroll_snapshots
            WHERE company_code=%s AND work_date BETWEEN %s AND %s
              AND employee_key = ANY(%s)
            ORDER BY employee_key, work_date, COALESCE(shift_key,''), projection_version DESC
            """,
            ((company_code or "").upper(), period_start, period_end, employee_keys),
        )
        return _rows(cur)
    except Exception:
        return []


def _load_open_corrections(
    cur: Any, *, company_code: str, period_start: date, period_end: date, employee_keys: list[str]
) -> list[dict[str, Any]]:
    try:
        cur.execute(
            """
            SELECT * FROM attendance_corrections
            WHERE company_code=%s AND employee_key = ANY(%s)
              AND status IN ('requested','disputed')
              AND (
                (work_date IS NOT NULL AND work_date BETWEEN %s AND %s)
                OR (created_at::date BETWEEN %s AND %s)
              )
            """,
            ((company_code or "").upper(), employee_keys, period_start, period_end, period_start, period_end),
        )
        return _rows(cur)
    except Exception:
        return []


def _load_approved_leave(
    cur: Any, *, company_code: str, period_start: date, period_end: date, employee_keys: list[str]
) -> list[dict[str, Any]]:
    try:
        cur.execute(
            """
            SELECT * FROM leave_requests
            WHERE company_code=%s AND employee_key = ANY(%s)
              AND lower(status)='approved'
              AND start_date <= %s AND end_date >= %s
            ORDER BY employee_key, start_date
            """,
            ((company_code or "").upper(), employee_keys, period_end, period_start),
        )
        return _rows(cur)
    except Exception:
        return []


def _load_non_approved_leave(
    cur: Any, *, company_code: str, period_start: date, period_end: date, employee_keys: list[str]
) -> list[dict[str, Any]]:
    """For provenance/exclusion proof — never assembled into affecting lines."""
    try:
        cur.execute(
            """
            SELECT leave_id, employee_key, status, leave_type, start_date, end_date
            FROM leave_requests
            WHERE company_code=%s AND employee_key = ANY(%s)
              AND lower(status) IN ('requested','pending','rejected','cancelled','withdrawn','needs_review','needs_info')
              AND start_date <= %s AND end_date >= %s
            """,
            ((company_code or "").upper(), employee_keys, period_end, period_start),
        )
        return _rows(cur)
    except Exception:
        return []


def _load_shifts(
    cur: Any, *, company_code: str, period_start: date, period_end: date, employee_keys: list[str]
) -> list[dict[str, Any]]:
    try:
        cur.execute(
            """
            SELECT * FROM shift_assignments
            WHERE company_code=%s AND employee_key = ANY(%s)
              AND shift_date BETWEEN %s AND %s
              AND lower(COALESCE(status,'scheduled')) IN ('scheduled','published','confirmed')
            ORDER BY employee_key, shift_date
            """,
            ((company_code or "").upper(), employee_keys, period_start, period_end),
        )
        return _rows(cur)
    except Exception:
        return []


def _load_holidays(
    cur: Any, *, company_code: str, period_start: date, period_end: date
) -> list[dict[str, Any]]:
    try:
        cur.execute(
            """
            SELECT * FROM public_holidays
            WHERE (company_code=%s OR company_code IS NULL OR company_code='')
              AND holiday_date BETWEEN %s AND %s
            ORDER BY holiday_date
            """,
            ((company_code or "").upper(), period_start, period_end),
        )
        return _rows(cur)
    except Exception:
        return []


def _leave_pay_classification(leave: dict[str, Any]) -> str:
    handoff = leave.get("payroll_handoff") or {}
    if isinstance(handoff, str):
        try:
            handoff = json.loads(handoff)
        except Exception:
            handoff = {}
    if str(handoff.get("classification") or "") == "unpaid_leave":
        return "unpaid_leave"
    lt = str(leave.get("leave_type") or leave.get("type") or "other").strip().lower()
    return LEAVE_PAY_CLASS.get(lt, "other_leave")


def _payload_of_attendance(snap: dict[str, Any]) -> dict[str, Any]:
    payload = snap.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return payload if isinstance(payload, dict) else {}


def _assemble_employee_bundle(
    *,
    emp: dict[str, Any],
    period_start: date,
    period_end: date,
    att_mode: str,
    weekend_days: tuple[str, ...],
    contracts: list[dict[str, Any]],
    att_snaps: list[dict[str, Any]],
    corrections: list[dict[str, Any]],
    leaves: list[dict[str, Any]],
    excluded_leaves: list[dict[str, Any]],
    shifts: list[dict[str, Any]],
    holidays: list[dict[str, Any]],
) -> dict[str, Any]:
    key = str(emp.get("employee_key") or "")
    bounds = _employment_bounds(emp, period_start, period_end)
    lines: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    sort_i = 0

    lines.append(
        {
            "line_kind": "employment_span",
            "fact_date": bounds["active_start"] if bounds["active"] else period_start,
            "fact_end_date": bounds["active_end"] if bounds["active"] else period_start,
            "classification": "employment",
            "label_en": "Employment active span in period",
            "label_ar": "مدة التوظيف الفعّالة في الفترة",
            "provenance": {
                "employment_start": _json_safe(bounds["employment_start"]),
                "employment_end": _json_safe(bounds["employment_end"]),
                "mid_period_hire": bounds["mid_period_hire"],
                "mid_period_leaver": bounds["mid_period_leaver"],
            },
            "sort_order": sort_i,
        }
    )
    sort_i += 1

    for c in contracts:
        lines.append(
            {
                "line_kind": "compensation_span",
                "fact_date": _parse_date(c.get("effective_from")),
                "fact_end_date": _parse_date(c.get("effective_to")),
                "classification": "compensation",
                "source_table": "payroll_compensation_contracts",
                "source_id": str(c.get("contract_id") or ""),
                "source_version": str(c.get("row_version") or ""),
                "label_en": "Compensation contract effective span",
                "label_ar": "مدة عقد التعويض السارية",
                "fact_payload": {
                    "currency": c.get("currency"),
                    "status": c.get("status"),
                },
                "provenance": {"contract_id": str(c.get("contract_id") or "")},
                "sort_order": sort_i,
            }
        )
        sort_i += 1

    holiday_dates = {_parse_date(h.get("holiday_date")) for h in holidays}
    holiday_dates.discard(None)
    holiday_by_date = {_parse_date(h.get("holiday_date")): h for h in holidays}

    unpaid_leave_dates: set[date] = set()
    paid_leave_dates: set[date] = set()
    sick_leave_dates: set[date] = set()

    for lv in leaves:
        ls = _parse_date(lv.get("start_date"))
        le = _parse_date(lv.get("end_date"))
        if not ls or not le:
            continue
        # Clip to active employment ∩ period
        clip_s = max(ls, bounds["active_start"], period_start) if bounds["active"] else None
        clip_e = min(le, bounds["active_end"], period_end) if bounds["active"] else None
        if not clip_s or not clip_e or clip_s > clip_e:
            continue
        pay_class = _leave_pay_classification(lv)
        for d in _daterange(clip_s, clip_e):
            if pay_class == "unpaid_leave":
                unpaid_leave_dates.add(d)
            elif pay_class == "sick_leave":
                sick_leave_dates.add(d)
            elif pay_class == "paid_leave":
                paid_leave_dates.add(d)
        handoff = lv.get("payroll_handoff") or {}
        if isinstance(handoff, str):
            try:
                handoff = json.loads(handoff)
            except Exception:
                handoff = {}
        lines.append(
            {
                "line_kind": "leave_interval",
                "fact_date": clip_s,
                "fact_end_date": clip_e,
                "classification": pay_class,
                "chargeable_days": float(lv.get("chargeable_days") or handoff.get("chargeable_days") or 0) or None,
                "chargeable_hours": float(lv.get("chargeable_hours") or handoff.get("chargeable_hours") or 0) or None,
                "leave_id": str(lv.get("leave_id") or ""),
                "source_table": "leave_requests",
                "source_id": str(lv.get("leave_id") or ""),
                "label_en": f"Approved {pay_class.replace('_', ' ')}",
                "label_ar": "إجازة معتمدة",
                "fact_payload": {
                    "leave_type": lv.get("leave_type"),
                    "status": lv.get("status"),
                    "duration_unit": lv.get("duration_unit"),
                    "payroll_handoff": handoff if isinstance(handoff, dict) else {},
                    "original_start": str(ls),
                    "original_end": str(le),
                    "spans_period_boundary": ls < period_start or le > period_end,
                },
                "provenance": {
                    "leave_id": str(lv.get("leave_id") or ""),
                    "approval_state": "approved",
                    "pay_classification": pay_class,
                },
                "precedence_rule": "approved_leave_only",
                "sort_order": sort_i,
            }
        )
        sort_i += 1

    # Explicitly note excluded leave for audit (info only, not affecting)
    for lv in excluded_leaves:
        issues.append(
            {
                "severity": "info",
                "code": "leave_excluded_not_approved",
                "message_en": f"Leave {lv.get('leave_id')} status={lv.get('status')} excluded from payroll inputs",
                "message_ar": "إجازة غير معتمدة مستبعدة من مدخلات الرواتب",
                "fact_date": _parse_date(lv.get("start_date")),
                "source_table": "leave_requests",
                "source_id": str(lv.get("leave_id") or ""),
                "blocks_lock": False,
                "payload": {"status": lv.get("status"), "leave_type": lv.get("leave_type")},
            }
        )

    shifts_by_date: dict[date, list[dict[str, Any]]] = {}
    for sh in shifts:
        d = _parse_date(sh.get("shift_date"))
        if d:
            shifts_by_date.setdefault(d, []).append(sh)

    att_by_date: dict[date, list[dict[str, Any]]] = {}
    for snap in att_snaps:
        d = _parse_date(snap.get("work_date"))
        if d:
            att_by_date.setdefault(d, []).append(snap)

    corr_by_date: dict[date, list[dict[str, Any]]] = {}
    for corr in corrections:
        d = _parse_date(corr.get("work_date")) or _parse_date(str(corr.get("created_at") or "")[:10])
        if d:
            corr_by_date.setdefault(d, []).append(corr)
            lines.append(
                {
                    "line_kind": "attendance_correction",
                    "fact_date": d,
                    "classification": "unresolved_correction",
                    "source_table": "attendance_corrections",
                    "source_id": str(corr.get("correction_id") or corr.get("id") or ""),
                    "label_en": "Unresolved attendance correction",
                    "label_ar": "تصحيح حضور غير محسوم",
                    "fact_payload": {
                        "status": corr.get("status"),
                        "requested_changes": corr.get("requested_changes"),
                    },
                    "provenance": {"correction_id": str(corr.get("correction_id") or "")},
                    "sort_order": sort_i,
                }
            )
            sort_i += 1
            if att_mode == ATT_MODE_REQUIRED:
                issues.append(
                    {
                        "severity": "blocker",
                        "code": "unresolved_attendance_correction",
                        "message_en": "Unresolved attendance correction blocks lock",
                        "message_ar": "تصحيح حضور غير محسوم يمنع القفل",
                        "fact_date": d,
                        "source_table": "attendance_corrections",
                        "source_id": str(corr.get("correction_id") or ""),
                        "blocks_lock": True,
                        "payload": {"status": corr.get("status")},
                    }
                )
            elif att_mode == ATT_MODE_INFO:
                issues.append(
                    {
                        "severity": "warning",
                        "code": "unresolved_attendance_correction_informational",
                        "message_en": "Unresolved correction noted (informational mode)",
                        "message_ar": "تصحيح غير محسوم (وضع معلوماتي)",
                        "fact_date": d,
                        "blocks_lock": False,
                        "payload": {},
                    }
                )

    if bounds["active"]:
        for d in _daterange(bounds["active_start"], bounds["active_end"]):
            is_weekend = _weekday_key(d) in weekend_days
            is_ph = d in holiday_dates
            day_shifts = shifts_by_date.get(d, [])
            expected = False
            overnight = False
            expected_minutes = None
            for sh in day_shifts:
                expected = True
                overnight = overnight or bool(sh.get("ends_next_day"))
                lines.append(
                    {
                        "line_kind": "schedule_day",
                        "fact_date": d,
                        "classification": "scheduled",
                        "is_rest_day": is_weekend,
                        "is_public_holiday": is_ph,
                        "overnight_shift": overnight,
                        "shift_id": str(sh.get("shift_id") or sh.get("id") or ""),
                        "source_table": "shift_assignments",
                        "source_id": str(sh.get("shift_id") or ""),
                        "label_en": "Scheduled shift",
                        "label_ar": "وردية مجدولة",
                        "fact_payload": {
                            "start_time": str(sh.get("start_time") or ""),
                            "end_time": str(sh.get("end_time") or ""),
                            "timezone": sh.get("timezone") or "Asia/Kuwait",
                            "ends_next_day": bool(sh.get("ends_next_day")),
                        },
                        "provenance": {"shift_date": str(d), "shift_id": str(sh.get("shift_id") or "")},
                        "sort_order": sort_i,
                    }
                )
                sort_i += 1
            if not day_shifts and not is_weekend and not is_ph:
                # No explicit schedule — still a potential workday under default KW week
                expected = True

            if is_ph:
                h = holiday_by_date.get(d) or {}
                lines.append(
                    {
                        "line_kind": "calendar_day",
                        "fact_date": d,
                        "classification": "public_holiday",
                        "is_public_holiday": True,
                        "holiday_id": str(h.get("holiday_id") or h.get("id") or ""),
                        "source_table": "public_holidays",
                        "source_id": str(h.get("holiday_id") or h.get("id") or str(d)),
                        "label_en": str(h.get("name") or "Public holiday"),
                        "label_ar": "عطلة رسمية",
                        "fact_payload": {"name": h.get("name")},
                        "sort_order": sort_i,
                    }
                )
                sort_i += 1
            elif is_weekend:
                lines.append(
                    {
                        "line_kind": "calendar_day",
                        "fact_date": d,
                        "classification": "rest_day",
                        "is_rest_day": True,
                        "label_en": "Rest day",
                        "label_ar": "يوم راحة",
                        "fact_payload": {"weekday": _weekday_key(d)},
                        "sort_order": sort_i,
                    }
                )
                sort_i += 1

            day_atts = att_by_date.get(d, [])
            if att_mode == ATT_MODE_IGNORED:
                continue

            if not day_atts:
                if expected and att_mode == ATT_MODE_REQUIRED and d not in unpaid_leave_dates and d not in paid_leave_dates and d not in sick_leave_dates and not is_weekend and not is_ph:
                    lines.append(
                        {
                            "line_kind": "attendance_incomplete",
                            "fact_date": d,
                            "classification": "missing_approved_attendance",
                            "label_en": "Missing approved attendance",
                            "label_ar": "حضور معتمد مفقود",
                            "sort_order": sort_i,
                        }
                    )
                    sort_i += 1
                    issues.append(
                        {
                            "severity": "blocker",
                            "code": "missing_approved_attendance",
                            "message_en": f"Missing approved attendance for {d.isoformat()}",
                            "message_ar": "حضور معتمد مفقود",
                            "fact_date": d,
                            "blocks_lock": True,
                            "payload": {"expected_work_day": True},
                        }
                    )
                elif expected and att_mode == ATT_MODE_INFO and d not in unpaid_leave_dates and not is_weekend and not is_ph:
                    issues.append(
                        {
                            "severity": "warning",
                            "code": "missing_attendance_informational",
                            "message_en": f"Missing attendance noted (informational) {d.isoformat()}",
                            "message_ar": "حضور مفقود (معلوماتي)",
                            "fact_date": d,
                            "blocks_lock": False,
                            "payload": {},
                        }
                    )
                continue

            for snap in day_atts:
                payload = _payload_of_attendance(snap)
                status = str(payload.get("status") or snap.get("status") or "").lower()
                worked = float(payload.get("worked_minutes") or snap.get("worked_minutes_cache") or 0)
                late = float(payload.get("late_minutes") or 0)
                early = float(payload.get("early_leave_minutes") or payload.get("early_departure_minutes") or 0)
                scheduled = float(payload.get("scheduled_minutes") or 0)
                if not scheduled:
                    # derive from scheduled_start/end if present — leave None if unknown
                    scheduled = 0.0
                ot_fact = max(0.0, worked - scheduled) if scheduled else None
                overnight = bool(payload.get("ends_next_day") or payload.get("overnight_shift"))
                absent = status in ("absent",) or (worked <= 0 and status not in ("approved_leave", "void", "present", "late", "completed"))

                # Double-count prevention
                suppressed = False
                suppression_reason = None
                precedence = None
                if absent and d in unpaid_leave_dates:
                    suppressed = True
                    suppression_reason = "approved_unpaid_leave_suppresses_absence"
                    precedence = "unpaid_leave_over_attendance_absence"
                    lines.append(
                        {
                            "line_kind": "suppressed_absence",
                            "fact_date": d,
                            "classification": "suppressed_absence",
                            "suppressed": True,
                            "suppression_reason": suppression_reason,
                            "precedence_rule": precedence,
                            "attendance_snapshot_id": str(snap.get("snapshot_id") or ""),
                            "projection_id": str(snap.get("projection_id") or ""),
                            "source_table": "attendance_payroll_snapshots",
                            "source_id": str(snap.get("snapshot_id") or ""),
                            "label_en": "Absence suppressed by approved unpaid leave",
                            "label_ar": "الغياب مُلغى بسبب إجازة بدون راتب معتمدة",
                            "sort_order": sort_i,
                        }
                    )
                    sort_i += 1

                if d in paid_leave_dates and absent:
                    # Paid leave must not appear as unpaid absence
                    suppressed = True
                    suppression_reason = "paid_leave_not_unpaid_absence"
                    precedence = "paid_leave_over_absence"

                line_kind = "attendance_day"
                if status in ("incomplete",) or payload.get("incomplete"):
                    line_kind = "attendance_incomplete"
                    if att_mode == ATT_MODE_REQUIRED:
                        issues.append(
                            {
                                "severity": "blocker",
                                "code": "incomplete_attendance",
                                "message_en": f"Incomplete attendance on {d.isoformat()}",
                                "message_ar": "حضور غير مكتمل",
                                "fact_date": d,
                                "blocks_lock": True,
                                "source_table": "attendance_payroll_snapshots",
                                "source_id": str(snap.get("snapshot_id") or ""),
                                "payload": {"status": status},
                            }
                        )

                if not suppressed:
                    lines.append(
                        {
                            "line_kind": line_kind,
                            "fact_date": d,
                            "classification": status or "attendance",
                            "expected_minutes": scheduled or None,
                            "worked_minutes": worked,
                            "absent_minutes": (scheduled - worked) if scheduled and absent else (None if not absent else scheduled or None),
                            "late_minutes": late or None,
                            "early_departure_minutes": early or None,
                            "overtime_minutes_fact": ot_fact,
                            "is_rest_day": is_weekend,
                            "is_public_holiday": is_ph,
                            "overnight_shift": overnight,
                            "suppressed": False,
                            "attendance_snapshot_id": str(snap.get("snapshot_id") or ""),
                            "projection_id": str(snap.get("projection_id") or ""),
                            "shift_id": str(snap.get("shift_id") or ""),
                            "source_table": "attendance_payroll_snapshots",
                            "source_id": str(snap.get("snapshot_id") or ""),
                            "source_version": str(snap.get("projection_version") or ""),
                            "label_en": "Approved attendance day",
                            "label_ar": "يوم حضور معتمد",
                            "fact_payload": {
                                "status": status,
                                "check_in_at": payload.get("check_in_at"),
                                "check_out_at": payload.get("check_out_at"),
                                "approval_status": payload.get("approval_status") or "approved",
                                "money_impact": None,
                            },
                            "provenance": {
                                "attendance_snapshot_id": str(snap.get("snapshot_id") or ""),
                                "projection_id": str(snap.get("projection_id") or ""),
                                "projection_version": snap.get("projection_version"),
                                "approved_at": _json_safe(snap.get("approved_at")),
                            },
                            "sort_order": sort_i,
                        }
                    )
                    sort_i += 1

                # Distinct OT / rest-day / PH work facts (no money)
                if ot_fact and ot_fact > 0 and not suppressed:
                    lines.append(
                        {
                            "line_kind": "overtime_fact",
                            "fact_date": d,
                            "classification": "overtime_hours_fact",
                            "overtime_minutes_fact": ot_fact,
                            "worked_minutes": worked,
                            "expected_minutes": scheduled or None,
                            "attendance_snapshot_id": str(snap.get("snapshot_id") or ""),
                            "source_table": "attendance_payroll_snapshots",
                            "source_id": str(snap.get("snapshot_id") or ""),
                            "label_en": "Overtime hours (fact only — no pay calc)",
                            "label_ar": "ساعات عمل إضافي (واقعة فقط — بلا احتساب أجر)",
                            "fact_payload": {"money_impact": None, "counsel_gated_pay": True},
                            "precedence_rule": "ot_fact_not_money",
                            "sort_order": sort_i,
                        }
                    )
                    sort_i += 1
                if worked > 0 and is_weekend and not suppressed:
                    lines.append(
                        {
                            "line_kind": "rest_day_work_fact",
                            "fact_date": d,
                            "classification": "rest_day_work",
                            "worked_minutes": worked,
                            "is_rest_day": True,
                            "attendance_snapshot_id": str(snap.get("snapshot_id") or ""),
                            "source_table": "attendance_payroll_snapshots",
                            "source_id": str(snap.get("snapshot_id") or ""),
                            "label_en": "Rest-day work (fact only — no pay calc)",
                            "label_ar": "عمل في يوم راحة (واقعة فقط)",
                            "fact_payload": {"money_impact": None, "counsel_gated_pay": True},
                            "sort_order": sort_i,
                        }
                    )
                    sort_i += 1
                if worked > 0 and is_ph and not suppressed:
                    lines.append(
                        {
                            "line_kind": "public_holiday_work_fact",
                            "fact_date": d,
                            "classification": "public_holiday_work",
                            "worked_minutes": worked,
                            "is_public_holiday": True,
                            "attendance_snapshot_id": str(snap.get("snapshot_id") or ""),
                            "source_table": "attendance_payroll_snapshots",
                            "source_id": str(snap.get("snapshot_id") or ""),
                            "label_en": "Public-holiday work (fact only — no pay calc)",
                            "label_ar": "عمل في عطلة رسمية (واقعة فقط)",
                            "fact_payload": {"money_impact": None, "counsel_gated_pay": True},
                            "sort_order": sort_i,
                        }
                    )
                    sort_i += 1

    att_summary = {
        "approved_days": len(att_snaps),
        "unresolved_corrections": len(corrections),
        "suppressed_absences": sum(1 for ln in lines if ln.get("line_kind") == "suppressed_absence"),
        "ot_fact_lines": sum(1 for ln in lines if ln.get("line_kind") == "overtime_fact"),
        "rest_day_work_facts": sum(1 for ln in lines if ln.get("line_kind") == "rest_day_work_fact"),
        "ph_work_facts": sum(1 for ln in lines if ln.get("line_kind") == "public_holiday_work_fact"),
        "incomplete_or_missing": sum(1 for ln in lines if ln.get("line_kind") == "attendance_incomplete"),
    }
    leave_summary = {
        "approved_intervals": len(leaves),
        "excluded_non_approved": len(excluded_leaves),
        "unpaid_dates": len(unpaid_leave_dates),
        "paid_dates": len(paid_leave_dates),
        "sick_dates": len(sick_leave_dates),
    }
    blockers = [i for i in issues if i.get("severity") == "blocker"]
    if blockers:
        readiness = "blocked" if att_mode == ATT_MODE_REQUIRED else "needs_review"
    elif any(i.get("severity") == "warning" for i in issues):
        readiness = "needs_review" if att_mode == ATT_MODE_REQUIRED else "ready"
    else:
        readiness = "ready"

    # Informational mode: blockers become non-blocking for employee readiness
    if att_mode == ATT_MODE_INFO:
        for i in issues:
            if i.get("severity") == "blocker":
                i["severity"] = "warning"
                i["blocks_lock"] = False
                i["code"] = str(i.get("code") or "") + "_informational"
        readiness = "ready"
    if att_mode == ATT_MODE_IGNORED:
        issues = [i for i in issues if not str(i.get("code") or "").startswith("missing") and "attendance" not in str(i.get("code") or "")]
        readiness = "ready"

    return {
        "employee_key": key,
        "bounds": bounds,
        "contracts": contracts,
        "lines": lines,
        "issues": issues,
        "attendance_summary": att_summary,
        "leave_summary": leave_summary,
        "readiness_status": readiness,
        "issue_codes": [str(i.get("code")) for i in issues],
    }


def assemble_payroll_inputs(
    cur: Any,
    *,
    company_code: str,
    period_start: str | date,
    period_end: str | date,
    period_id: str | None = None,
    employee_keys: list[str] | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    weekend_days: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble versioned payroll input snapshot from canonical Attendance/Leave/Shift sources."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if not payroll_authority_p2_enabled_for_company(company_code):
        return {"ok": False, "error": "payroll_authority_p2_disabled_for_company"}
    ensure_payroll_input_snapshot_schema(cur)
    company = (company_code or "").upper()
    p_start = _parse_date(period_start)
    p_end = _parse_date(period_end)
    if not p_start or not p_end or p_end < p_start:
        return {"ok": False, "error": "invalid_period"}

    period = _load_period(cur, company_code=company, period_id=period_id, period_start=p_start, period_end=p_end)
    att_mode = resolve_attendance_payroll_mode(cur, company_code=company, period=period)
    att_source = str(period.get("attendance_input_source") or "approved_snapshots")
    weekends = tuple(str(x).lower() for x in (weekend_days or DEFAULT_WEEKEND_DAYS))

    employees = _load_employees(cur, company_code=company, employee_keys=employee_keys)
    if payroll_authority_p2_synthetic_only():
        filtered = []
        for e in employees:
            key = str(e.get("employee_key") or "")
            allowed = is_p2_synthetic_employee(employee_key=key)
            if not allowed:
                try:
                    import payroll_authority_production_p6 as p6

                    allowed = p6.employee_production_mutations_allowed(
                        cur, company_code=company, employee_key=key
                    )
                except Exception:
                    allowed = False
            if allowed:
                filtered.append(e)
        employees = filtered
    if not employees:
        return {"ok": False, "error": "no_employees_to_assemble"}

    keys = [str(e.get("employee_key")) for e in employees]
    all_att = _load_approved_attendance(cur, company_code=company, period_start=p_start, period_end=p_end, employee_keys=keys)
    all_corr = _load_open_corrections(cur, company_code=company, period_start=p_start, period_end=p_end, employee_keys=keys)
    all_leave = _load_approved_leave(cur, company_code=company, period_start=p_start, period_end=p_end, employee_keys=keys)
    all_excl = _load_non_approved_leave(cur, company_code=company, period_start=p_start, period_end=p_end, employee_keys=keys)
    all_shifts = _load_shifts(cur, company_code=company, period_start=p_start, period_end=p_end, employee_keys=keys)
    holidays = _load_holidays(cur, company_code=company, period_start=p_start, period_end=p_end)

    bundles = []
    for emp in employees:
        key = str(emp.get("employee_key"))
        contracts = _load_contracts_for_employee(
            cur, company_code=company, employee_key=key, period_start=p_start, period_end=p_end
        )
        bundles.append(
            _assemble_employee_bundle(
                emp=emp,
                period_start=p_start,
                period_end=p_end,
                att_mode=att_mode,
                weekend_days=weekends,
                contracts=contracts,
                att_snaps=[a for a in all_att if str(a.get("employee_key")) == key],
                corrections=[c for c in all_corr if str(c.get("employee_key")) == key],
                leaves=[l for l in all_leave if str(l.get("employee_key")) == key],
                excluded_leaves=[l for l in all_excl if str(l.get("employee_key")) == key],
                shifts=[s for s in all_shifts if str(s.get("employee_key")) == key],
                holidays=holidays,
            )
        )

    content = {
        "schema": INPUT_SNAPSHOT_SCHEMA,
        "company_code": company,
        "period_start": str(p_start),
        "period_end": str(p_end),
        "attendance_payroll_mode": att_mode,
        "attendance_input_source": att_source,
        "timezone": "Asia/Kuwait",
        "weekend_days": list(weekends),
        "overlap_precedence": overlap_precedence_rules(),
        "employees": [
            {
                "employee_key": b["employee_key"],
                "bounds": _json_safe(b["bounds"]),
                "attendance_summary": b["attendance_summary"],
                "leave_summary": b["leave_summary"],
                "readiness_status": b["readiness_status"],
                "lines": _json_safe(b["lines"]),
                "issues": _json_safe(b["issues"]),
            }
            for b in bundles
        ],
        "money_calculated": False,
        "payment_processing": "disabled",
    }
    content_fp = fingerprint_payload(content)
    source_fp = fingerprint_payload(
        {
            "attendance_snapshot_ids": sorted(str(a.get("snapshot_id") or "") for a in all_att),
            "leave_ids": sorted(str(l.get("leave_id") or "") for l in all_leave),
            "correction_ids": sorted(str(c.get("correction_id") or c.get("id") or "") for c in all_corr),
            "shift_ids": sorted(str(s.get("shift_id") or "") for s in all_shifts),
            "holiday_dates": sorted(str(h.get("holiday_date") or "")[:10] for h in holidays),
            "contract_ids": sorted(
                str(c.get("contract_id") or "")
                for b in bundles
                for c in b["contracts"]
            ),
        }
    )

    existing = get_current_input_snapshot(cur, company_code=company, period_start=p_start, period_end=p_end)
    if existing and str(existing.get("status")) == STATUS_LOCKED:
        if str(existing.get("content_fingerprint") or "") == content_fp:
            return {
                "ok": True,
                "idempotent": True,
                "input_snapshot": _json_safe(existing),
                **honesty_payload(),
            }
        return {
            "ok": False,
            "error": "locked_input_snapshot_immutable",
            "message": "Locked input snapshot cannot be silently rewritten; use supersede_input_snapshot.",
            "input_snapshot_id": str(existing.get("input_snapshot_id")),
            **honesty_payload(),
        }

    if existing and str(existing.get("content_fingerprint") or "") == content_fp and str(existing.get("status")) in (
        STATUS_ASSEMBLING,
        STATUS_NEEDS_REVIEW,
        STATUS_READY,
    ):
        return {
            "ok": True,
            "idempotent": True,
            "input_snapshot": _json_safe(existing),
            **honesty_payload(),
        }

    # Supersede prior non-locked current if content changed
    replaces_id = None
    if existing and str(existing.get("content_fingerprint") or "") != content_fp:
        replaces_id = str(existing.get("input_snapshot_id") or "")
        cur.execute(
            """
            UPDATE payroll_input_snapshots
            SET status='superseded', updated_at=now(), row_version=row_version+1,
                decision_note=COALESCE(decision_note,'') || ' | superseded_by_reassemble'
            WHERE company_code=%s AND input_snapshot_id=%s
              AND status IN ('assembling','needs_review','ready')
            RETURNING *
            """,
            (company, existing.get("input_snapshot_id")),
        )
        _row(cur)

    blocker_count = sum(1 for b in bundles for i in b["issues"] if i.get("severity") == "blocker" and i.get("blocks_lock"))
    warning_count = sum(1 for b in bundles for i in b["issues"] if i.get("severity") == "warning")
    if blocker_count > 0:
        status = STATUS_NEEDS_REVIEW
    elif warning_count > 0 and att_mode == ATT_MODE_REQUIRED:
        status = STATUS_NEEDS_REVIEW
    else:
        status = STATUS_READY

    snap_id = str(uuid.uuid4())
    source_counts = {
        "employees": len(bundles),
        "attendance_snapshots": len(all_att),
        "leave_approved": len(all_leave),
        "leave_excluded": len(all_excl),
        "corrections_open": len(all_corr),
        "shifts": len(all_shifts),
        "holidays": len(holidays),
    }
    policy_context = {
        "attendance_payroll_mode": att_mode,
        "attendance_input_source": att_source,
        "weekend_days": list(weekends),
        "timezone": "Asia/Kuwait",
        "overlap_precedence": overlap_precedence_rules(),
        "lateness_money": False,
        "ot_money": False,
        "sick_fraction_money": False,
        "ph_rest_day_money": False,
    }
    provenance = {
        "assembled_from": [
            "attendance_payroll_snapshots",
            "attendance_corrections",
            "leave_requests",
            "shift_assignments",
            "public_holidays",
            "payroll_compensation_contracts",
            "employees",
        ],
        "source_fingerprint": source_fp,
        "period_id": str(period.get("period_id") or "") or None,
    }

    cur.execute(
        """
        INSERT INTO payroll_input_snapshots (
          input_snapshot_id, company_code, period_id, period_start, period_end,
          status, attendance_payroll_mode, attendance_input_source, timezone,
          content_fingerprint, source_fingerprint, policy_context, source_counts,
          employee_count, issue_blocker_count, issue_warning_count,
          snapshot_payload, provenance, replaces_snapshot_id,
          assembled_by_phone, decision_note
        ) VALUES (
          %s,%s,%s,%s,%s,
          %s,%s,%s,'Asia/Kuwait',
          %s,%s,%s::jsonb,%s::jsonb,
          %s,%s,%s,
          %s::jsonb,%s::jsonb,%s,
          %s,%s
        )
        RETURNING *
        """,
        (
            snap_id,
            company,
            period.get("period_id"),
            p_start,
            p_end,
            status,
            att_mode,
            att_source,
            content_fp,
            source_fp,
            json.dumps(_json_safe(policy_context)),
            json.dumps(_json_safe(source_counts)),
            len(bundles),
            blocker_count,
            warning_count,
            json.dumps(_json_safe(content)),
            json.dumps(_json_safe(provenance)),
            replaces_id,
            digits_phone(actor_phone),
            str(reason).strip(),
        ),
    )
    header = _row(cur) or {}

    if replaces_id:
        cur.execute(
            """
            UPDATE payroll_input_snapshots
            SET superseded_by=%s, updated_at=now()
            WHERE company_code=%s AND input_snapshot_id=%s
            """,
            (snap_id, company, replaces_id),
        )

    for b in bundles:
        bounds = b["bounds"]
        cur.execute(
            """
            INSERT INTO payroll_input_snapshot_employees (
              input_snapshot_id, company_code, employee_key,
              employment_start, employment_end, active_start, active_end,
              mid_period_hire, mid_period_leaver, contract_ids, compensation_effective,
              attendance_summary, leave_summary, readiness_status, issue_codes, provenance
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s::jsonb
            )
            """,
            (
                snap_id,
                company,
                b["employee_key"],
                bounds.get("employment_start"),
                bounds.get("employment_end"),
                bounds.get("active_start") if bounds.get("active") else p_start,
                bounds.get("active_end") if bounds.get("active") else p_start,
                bounds.get("mid_period_hire"),
                bounds.get("mid_period_leaver"),
                json.dumps([str(c.get("contract_id")) for c in b["contracts"]]),
                json.dumps(
                    _json_safe(
                        [
                            {
                                "contract_id": str(c.get("contract_id")),
                                "effective_from": c.get("effective_from"),
                                "effective_to": c.get("effective_to"),
                            }
                            for c in b["contracts"]
                        ]
                    )
                ),
                json.dumps(_json_safe(b["attendance_summary"])),
                json.dumps(_json_safe(b["leave_summary"])),
                b["readiness_status"],
                json.dumps(b["issue_codes"]),
                json.dumps({"bounds": _json_safe(bounds)}),
            ),
        )
        for ln in b["lines"]:
            cur.execute(
                """
                INSERT INTO payroll_input_snapshot_lines (
                  input_snapshot_id, company_code, employee_key, line_kind,
                  fact_date, fact_end_date, classification,
                  expected_minutes, worked_minutes, absent_minutes, late_minutes,
                  early_departure_minutes, overtime_minutes_fact,
                  chargeable_days, chargeable_hours,
                  is_rest_day, is_public_holiday, overnight_shift,
                  suppressed, suppression_reason, precedence_rule,
                  source_table, source_id, source_version,
                  leave_id, attendance_snapshot_id, projection_id, shift_id, holiday_id,
                  label_en, label_ar, fact_payload, provenance, sort_order
                ) VALUES (
                  %s,%s,%s,%s,
                  %s,%s,%s,
                  %s,%s,%s,%s,
                  %s,%s,
                  %s,%s,
                  %s,%s,%s,
                  %s,%s,%s,
                  %s,%s,%s,
                  %s,%s,%s,%s,%s,
                  %s,%s,%s::jsonb,%s::jsonb,%s
                )
                """,
                (
                    snap_id,
                    company,
                    b["employee_key"],
                    ln.get("line_kind"),
                    ln.get("fact_date"),
                    ln.get("fact_end_date"),
                    ln.get("classification"),
                    ln.get("expected_minutes"),
                    ln.get("worked_minutes"),
                    ln.get("absent_minutes"),
                    ln.get("late_minutes"),
                    ln.get("early_departure_minutes"),
                    ln.get("overtime_minutes_fact"),
                    ln.get("chargeable_days"),
                    ln.get("chargeable_hours"),
                    bool(ln.get("is_rest_day")),
                    bool(ln.get("is_public_holiday")),
                    bool(ln.get("overnight_shift")),
                    bool(ln.get("suppressed")),
                    ln.get("suppression_reason"),
                    ln.get("precedence_rule"),
                    ln.get("source_table"),
                    ln.get("source_id"),
                    ln.get("source_version"),
                    ln.get("leave_id"),
                    ln.get("attendance_snapshot_id"),
                    ln.get("projection_id"),
                    ln.get("shift_id"),
                    ln.get("holiday_id"),
                    ln.get("label_en"),
                    ln.get("label_ar"),
                    json.dumps(_json_safe(ln.get("fact_payload") or {})),
                    json.dumps(_json_safe(ln.get("provenance") or {})),
                    int(ln.get("sort_order") or 0),
                ),
            )
        for iss in b["issues"]:
            cur.execute(
                """
                INSERT INTO payroll_input_snapshot_issues (
                  input_snapshot_id, company_code, employee_key, severity, code,
                  message_en, message_ar, fact_date, source_table, source_id,
                  blocks_lock, payload
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                """,
                (
                    snap_id,
                    company,
                    b["employee_key"],
                    iss.get("severity"),
                    iss.get("code"),
                    iss.get("message_en"),
                    iss.get("message_ar"),
                    iss.get("fact_date"),
                    iss.get("source_table"),
                    iss.get("source_id"),
                    bool(iss.get("blocks_lock")),
                    json.dumps(_json_safe(iss.get("payload") or {})),
                ),
            )

    _record_event(
        cur,
        company_code=company,
        input_snapshot_id=snap_id,
        event_type="input_snapshot_assembled",
        payload={
            "status": status,
            "content_fingerprint": content_fp,
            "source_fingerprint": source_fp,
            "blocker_count": blocker_count,
            "replaces_snapshot_id": replaces_id,
            "reason": str(reason).strip(),
        },
        actor_phone=actor_phone,
    )
    header = get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=snap_id) or header
    return {
        "ok": True,
        "idempotent": False,
        "input_snapshot": _json_safe(header),
        "employees": list_input_snapshot_employees(cur, company_code=company, input_snapshot_id=snap_id),
        "issues": list_input_snapshot_issues(cur, company_code=company, input_snapshot_id=snap_id),
        **honesty_payload(),
    }


def lock_payroll_input_snapshot(
    cur: Any,
    *,
    company_code: str,
    input_snapshot_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_input_snapshot_schema(cur)
    company = (company_code or "").upper()
    snap = get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=input_snapshot_id)
    if not snap:
        return {"ok": False, "error": "input_snapshot_not_found"}
    if str(snap.get("status")) == STATUS_LOCKED:
        return {"ok": True, "idempotent": True, "input_snapshot": _json_safe(snap), **honesty_payload()}
    if str(snap.get("status")) == STATUS_SUPERSEDED:
        return {"ok": False, "error": "input_snapshot_superseded"}
    if str(snap.get("status")) == STATUS_NEEDS_REVIEW and not force:
        return {
            "ok": False,
            "error": "input_snapshot_needs_review",
            "message": "Fail closed: unresolved payroll inputs must be reviewed before lock.",
            "issue_blocker_count": snap.get("issue_blocker_count"),
            **honesty_payload(),
        }
    if str(snap.get("status")) not in (STATUS_READY, STATUS_NEEDS_REVIEW):
        return {"ok": False, "error": "input_snapshot_not_lockable", "status": snap.get("status")}

    cur.execute(
        """
        UPDATE payroll_input_snapshots
        SET status='locked', locked_at=now(), locked_by_phone=%s,
            decision_note=COALESCE(decision_note,'') || ' | locked:' || %s,
            updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND input_snapshot_id=%s
          AND status IN ('ready','needs_review')
        RETURNING *
        """,
        (digits_phone(actor_phone), str(reason).strip(), company, input_snapshot_id),
    )
    locked = _row(cur)
    if not locked:
        return {"ok": False, "error": "input_snapshot_lock_race"}
    _record_event(
        cur,
        company_code=company,
        input_snapshot_id=input_snapshot_id,
        event_type="input_snapshot_locked",
        payload={"reason": str(reason).strip(), "force": force},
        actor_phone=actor_phone,
    )
    return {"ok": True, "idempotent": False, "input_snapshot": _json_safe(locked), **honesty_payload()}


def supersede_input_snapshot(
    cur: Any,
    *,
    company_code: str,
    input_snapshot_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Mark locked/current snapshot superseded and assemble a new version from current sources."""
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_input_snapshot_schema(cur)
    company = (company_code or "").upper()
    prior = get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=input_snapshot_id)
    if not prior:
        return {"ok": False, "error": "input_snapshot_not_found"}
    if str(prior.get("status")) == STATUS_SUPERSEDED:
        return {"ok": False, "error": "input_snapshot_already_superseded"}

    cur.execute(
        """
        UPDATE payroll_input_snapshots
        SET status='superseded', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | superseded:' || %s
        WHERE company_code=%s AND input_snapshot_id=%s
          AND status IN ('assembling','needs_review','ready','locked')
        RETURNING *
        """,
        (str(reason).strip(), company, input_snapshot_id),
    )
    superseded = _row(cur)
    if not superseded:
        return {"ok": False, "error": "input_snapshot_supersede_race"}

    assembled = assemble_payroll_inputs(
        cur,
        company_code=company,
        period_start=prior.get("period_start"),
        period_end=prior.get("period_end"),
        period_id=str(prior.get("period_id") or "") or None,
        employee_keys=employee_keys,
        actor_phone=actor_phone,
        reason=str(reason).strip(),
    )
    if not assembled.get("ok"):
        # rollback status? keep superseded and return error — caller must reassemble
        return assembled
    new_id = str((assembled.get("input_snapshot") or {}).get("input_snapshot_id") or "")
    cur.execute(
        """
        UPDATE payroll_input_snapshots
        SET superseded_by=%s, updated_at=now()
        WHERE company_code=%s AND input_snapshot_id=%s
        """,
        (new_id, company, input_snapshot_id),
    )
    cur.execute(
        """
        UPDATE payroll_input_snapshots
        SET replaces_snapshot_id=COALESCE(replaces_snapshot_id, %s), updated_at=now()
        WHERE company_code=%s AND input_snapshot_id=%s
        """,
        (input_snapshot_id, company, new_id),
    )
    _record_event(
        cur,
        company_code=company,
        input_snapshot_id=input_snapshot_id,
        event_type="input_snapshot_superseded",
        payload={"superseded_by": new_id, "reason": str(reason).strip()},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "superseded_snapshot": _json_safe(superseded),
        "input_snapshot": assembled.get("input_snapshot"),
        "employees": assembled.get("employees"),
        "issues": assembled.get("issues"),
        **honesty_payload(),
    }


def refuse_mutate_locked_input(
    cur: Any, *, company_code: str, input_snapshot_id: str
) -> dict[str, Any]:
    snap = get_input_snapshot_by_id(cur, company_code=company_code, input_snapshot_id=input_snapshot_id)
    if not snap:
        return {"ok": False, "error": "input_snapshot_not_found"}
    if str(snap.get("status")) != STATUS_LOCKED:
        return {"ok": False, "error": "input_snapshot_not_locked"}
    return {
        "ok": False,
        "error": "locked_input_snapshot_immutable",
        "message": "Locked payroll inputs cannot be silently mutated; supersede + reassemble.",
        "content_fingerprint": snap.get("content_fingerprint"),
        **honesty_payload(),
    }


def link_authority_snapshot_to_inputs(
    cur: Any,
    *,
    company_code: str,
    authority_snapshot_id: str,
    input_snapshot_id: str,
) -> dict[str, Any]:
    """P1 bridge: sealed money may reference the locked input snapshot used."""
    ensure_payroll_input_snapshot_schema(cur)
    company = (company_code or "").upper()
    inp = get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=input_snapshot_id)
    if not inp or str(inp.get("status")) != STATUS_LOCKED:
        return {"ok": False, "error": "input_snapshot_must_be_locked"}
    auth = p1.get_sealed_snapshot_by_id(
        cur, company_code=company, authority_snapshot_id=authority_snapshot_id
    )
    if not auth:
        return {"ok": False, "error": "authority_snapshot_not_found"}
    cur.execute(
        """
        UPDATE payroll_authority_snapshots
        SET input_snapshot_id=%s, updated_at=now()
        WHERE company_code=%s AND authority_snapshot_id=%s
        RETURNING *
        """,
        (input_snapshot_id, company, authority_snapshot_id),
    )
    row = _row(cur)
    return {"ok": True, "authority_snapshot": _json_safe(row), **honesty_payload()}


def input_readiness_summary(
    cur: Any, *, company_code: str, period_start: str | date, period_end: str | date
) -> dict[str, Any]:
    ensure_payroll_input_snapshot_schema(cur)
    snap = get_current_input_snapshot(
        cur, company_code=company_code, period_start=period_start, period_end=period_end
    )
    if not snap:
        return {
            "ok": True,
            "has_snapshot": False,
            "status": None,
            "ready": False,
            "blockers": ["no_input_snapshot"],
            **honesty_payload(),
        }
    issues = list_input_snapshot_issues(
        cur, company_code=company_code, input_snapshot_id=str(snap.get("input_snapshot_id"))
    )
    blockers = [i for i in issues if i.get("severity") == "blocker" and i.get("blocks_lock")]
    employees = list_input_snapshot_employees(
        cur, company_code=company_code, input_snapshot_id=str(snap.get("input_snapshot_id"))
    )
    return {
        "ok": True,
        "has_snapshot": True,
        "input_snapshot": _json_safe(snap),
        "status": snap.get("status"),
        "ready": str(snap.get("status")) in (STATUS_READY, STATUS_LOCKED) and not blockers,
        "blockers": [_json_safe(b) for b in blockers],
        "warnings": [_json_safe(i) for i in issues if i.get("severity") == "warning"],
        "employees": _json_safe(employees),
        "overlap_precedence": overlap_precedence_rules(),
        **honesty_payload(),
    }
