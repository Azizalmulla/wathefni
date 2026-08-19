#!/usr/bin/env python3
"""Attendance Wave 1 — immutable punch authority and deterministic day engine.

Dark-launch foundation for local/staging. Defaults OFF via
WATHEFNI_ATTENDANCE_AUTHORITY (+ optional company allowlist).

Does not enable device import, QR/GPS/kiosk, or real employee clocking UX.
Does not mutate Employees 360 / Onboarding / pre-hiring / Wave D.
"""

from __future__ import annotations

import copy
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable

_ON_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})

KUWAIT_TZ = timezone(timedelta(hours=3))
AUTHORITY_VERSION = "attendance_authority_wave1_v1"

PUNCH_DIRECTIONS = frozenset({"in", "out", "break_start", "break_end"})
# Connector/capture sources (Wave 2B) feed the same immutable ledger as HR/import.
PUNCH_SOURCES = frozenset({
    "whatsapp",
    "import",
    "hr",
    "leave",
    "absence_scan",
    "correction",
    "system",
    "biotime",
    "csv",
    "sftp",
    "file_import",
    "capture",
})

DAY_STATUSES = frozenset({
    "incomplete",
    "present",
    "late",
    "completed",
    "absent",
    "approved_leave",
    "void",
})
EXCEPTION_STATES = frozenset({
    "none",
    "missing_check_in",
    "missing_check_out",
    "ambiguous_punches",
    "incomplete_session",
})
APPROVAL_STATES = frozenset({"unapproved", "approved", "rejected", "disputed"})
CORRECTION_STATES = frozenset({"requested", "approved", "rejected", "disputed"})

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS attendance_punches (
  punch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employee_phone text,
  employee_name text,
  punched_at timestamptz NOT NULL,
  direction text NOT NULL,
  source text NOT NULL,
  source_event_id text NOT NULL,
  shift_id uuid,
  shift_key text NOT NULL DEFAULT '',
  work_date date NOT NULL,
  break_paid boolean,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, source, source_event_id)
);
CREATE INDEX IF NOT EXISTS idx_att_punches_emp_day
  ON attendance_punches(company_code, employee_key, work_date, punched_at);
CREATE INDEX IF NOT EXISTS idx_att_punches_company_source
  ON attendance_punches(company_code, source, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_day_projections (
  projection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employee_phone text,
  employee_name text,
  work_date date NOT NULL,
  shift_id uuid,
  shift_key text NOT NULL DEFAULT '',
  version integer NOT NULL,
  is_current boolean NOT NULL DEFAULT true,
  status text NOT NULL,
  exception_state text NOT NULL DEFAULT 'none',
  approval_status text NOT NULL DEFAULT 'unapproved',
  payroll_eligible boolean NOT NULL DEFAULT false,
  check_in_at timestamptz,
  check_out_at timestamptz,
  scheduled_start time,
  scheduled_end time,
  late_minutes integer NOT NULL DEFAULT 0,
  early_leave_minutes integer NOT NULL DEFAULT 0,
  worked_minutes integer NOT NULL DEFAULT 0,
  unpaid_break_minutes integer NOT NULL DEFAULT 0,
  paid_break_minutes integer NOT NULL DEFAULT 0,
  sessions jsonb NOT NULL DEFAULT '[]'::jsonb,
  breaks jsonb NOT NULL DEFAULT '[]'::jsonb,
  source_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  authority text NOT NULL DEFAULT 'attendance_authority_wave1_v1',
  leave_id text,
  derived_from_leave boolean NOT NULL DEFAULT false,
  manual_correction boolean NOT NULL DEFAULT false,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  superseded_by uuid,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, employee_key, work_date, shift_key, version)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_att_day_current
  ON attendance_day_projections(company_code, employee_key, work_date, shift_key)
  WHERE is_current = true;
CREATE INDEX IF NOT EXISTS idx_att_day_company_date
  ON attendance_day_projections(company_code, work_date, approval_status)
  WHERE is_current = true;

CREATE TABLE IF NOT EXISTS attendance_corrections (
  correction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employee_phone text,
  work_date date NOT NULL,
  shift_key text NOT NULL DEFAULT '',
  projection_id uuid,
  status text NOT NULL DEFAULT 'requested',
  requested_changes jsonb NOT NULL DEFAULT '{}'::jsonb,
  requested_by_phone text NOT NULL,
  decision_note text,
  decided_by_phone text,
  decided_at timestamptz,
  dispute_reason text,
  resulting_projection_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_att_corrections_company_status
  ON attendance_corrections(company_code, status, created_at DESC);

CREATE TABLE IF NOT EXISTS attendance_payroll_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employee_phone text,
  employee_name text,
  work_date date NOT NULL,
  shift_id uuid,
  shift_key text NOT NULL DEFAULT '',
  projection_id uuid NOT NULL,
  projection_version integer NOT NULL,
  approved_at timestamptz NOT NULL DEFAULT now(),
  approved_by_phone text,
  payload jsonb NOT NULL,
  UNIQUE (company_code, employee_key, work_date, shift_key, projection_version)
);
CREATE INDEX IF NOT EXISTS idx_att_payroll_snap_period
  ON attendance_payroll_snapshots(company_code, work_date, employee_key);
"""


# ---------------------------------------------------------------------------
# Dark flags
# ---------------------------------------------------------------------------

def attendance_authority_enabled() -> bool:
    return (os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY") or "").strip().lower() in _ON_VALUES


def attendance_authority_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def attendance_authority_enabled_for_company(company_code: str | None) -> bool:
    if not attendance_authority_enabled():
        return False
    allowed = attendance_authority_companies()
    if not allowed:
        return True
    return str(company_code or "").strip().upper() in allowed


# Wave 1C/2C — strict synthetic allowlist (production canary).
# Distinct from Onboarding Wave 2B phones (965523) and the four real employees.
DEFAULT_ATTENDANCE_SYNTHETIC_KEY_MARKERS = (
    "ATTW1C",
    "ATTW2C",
    "ATTW2E",
    "ATTW2G",
    "ATTW3",
    "W1C-SYNTH|",
    "W2C-SYNTH|",
    "W2E-SYNTH|",
    "W2G-SYNTH|",
    "W3-SYNTH|",
)
DEFAULT_ATTENDANCE_SYNTHETIC_PHONE_PREFIXES = ("965524",)
FOUR_REAL_ATTENDANCE_KEYS = frozenset({
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
})


def attendance_authority_synthetic_only() -> bool:
    """When on, authority writes/reads apply only to synthetic employees."""
    return (os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY") or "").strip().lower() in _ON_VALUES


def attendance_authority_synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_ATTENDANCE_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_ATTENDANCE_SYNTHETIC_KEY_MARKERS


def attendance_authority_synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_ATTENDANCE_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_ATTENDANCE_SYNTHETIC_PHONE_PREFIXES


def is_attendance_synthetic_employee(employee: dict[str, Any] | None = None, *, employee_key: str | None = None, phone: str | None = None) -> bool:
    key = str((employee or {}).get("employee_key") or employee_key or "").strip()
    phone_d = digits((employee or {}).get("phone") or (employee or {}).get("employee_phone") or phone)
    if key in FOUR_REAL_ATTENDANCE_KEYS:
        return False
    if phone_d in {digits(k.split("-")[-1]) for k in FOUR_REAL_ATTENDANCE_KEYS}:
        return False
    for marker in attendance_authority_synthetic_key_markers():
        if marker and marker in key:
            return True
    for prefix in attendance_authority_synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    return False


def attendance_authority_allowed_for(company_code: str | None, employee: dict[str, Any] | None = None, *, employee_key: str | None = None, phone: str | None = None) -> bool:
    """Company gate + optional synthetic-only employee gate.

    Production canary must set SYNTHETIC_ONLY=on so real WATHEFNI employees
    remain on the legacy attendance path even when AUTHORITY=on for WATHEFNI.
    """
    if not attendance_authority_enabled_for_company(company_code):
        return False
    # Fail closed in production if synthetic-only is not explicitly configured.
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and not attendance_authority_synthetic_only():
        return False
    if not attendance_authority_synthetic_only():
        return True
    return is_attendance_synthetic_employee(employee, employee_key=employee_key, phone=phone)


# ensure_attendance_authority_schema is defined at bottom (includes Wave 1B DDL).


# ---------------------------------------------------------------------------
# Pure Kuwait / overnight calculator
# ---------------------------------------------------------------------------

def digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def shift_key_of(shift_id: Any) -> str:
    if shift_id is None:
        return ""
    text = str(shift_id).strip()
    return "" if text.lower() in {"", "none", "null"} else text


def as_kuwait(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KUWAIT_TZ)
    return dt.astimezone(KUWAIT_TZ)


def parse_time(value: Any) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text[:8] if fmt == "%H:%M:%S" else text[:5], fmt).time()
        except ValueError:
            continue
    return None


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return as_kuwait(value).date() if value.tzinfo else value.date()
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def shift_window(
    work_date: date,
    start_time: Any,
    end_time: Any,
    *,
    tz: timezone = KUWAIT_TZ,
) -> tuple[datetime, datetime] | None:
    """Return [start, end) window. Overnight shifts (end <= start) cross midnight."""
    st = parse_time(start_time)
    et = parse_time(end_time)
    if not st or not et:
        return None
    start_dt = datetime.combine(work_date, st, tzinfo=tz)
    end_dt = datetime.combine(work_date, et, tzinfo=tz)
    if et <= st:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def scheduled_minutes(start_time: Any, end_time: Any) -> int:
    win = shift_window(date(2000, 1, 1), start_time, end_time)
    if not win:
        return 0
    return int((win[1] - win[0]).total_seconds() // 60)


def minutes_between(start: datetime | None, end: datetime | None) -> int:
    if not start or not end:
        return 0
    a = as_kuwait(start)
    b = as_kuwait(end)
    if not a or not b:
        return 0
    return max(0, int((b - a).total_seconds() // 60))


def late_minutes(check_in: datetime | None, work_date: date, start_time: Any) -> int:
    st = parse_time(start_time)
    if not check_in or not st:
        return 0
    start_dt = datetime.combine(work_date, st, tzinfo=KUWAIT_TZ)
    ci = as_kuwait(check_in)
    return max(0, int((ci - start_dt).total_seconds() // 60))


def early_leave_minutes(check_out: datetime | None, work_date: date, start_time: Any, end_time: Any) -> int:
    win = shift_window(work_date, start_time, end_time)
    if not check_out or not win:
        return 0
    co = as_kuwait(check_out)
    end_dt = win[1]
    return max(0, int((end_dt - co).total_seconds() // 60))


def attribute_work_date(
    punched_at: datetime,
    *,
    shift: dict[str, Any] | None = None,
    explicit_work_date: date | None = None,
) -> date:
    if explicit_work_date:
        return explicit_work_date
    punch = as_kuwait(punched_at)
    assert punch is not None
    if shift:
        shift_date = parse_date(shift.get("shift_date") or shift.get("work_date") or shift.get("attendance_date"))
        if shift_date:
            win = shift_window(shift_date, shift.get("start_time") or shift.get("scheduled_start"), shift.get("end_time") or shift.get("scheduled_end"))
            if win:
                grace_start = win[0] - timedelta(hours=4)
                grace_end = win[1] + timedelta(hours=4)
                if grace_start <= punch <= grace_end:
                    return shift_date
    return punch.date()


@dataclass
class SessionSegment:
    session_index: int
    check_in_at: datetime | None
    check_out_at: datetime | None
    worked_minutes: int = 0
    open: bool = False


@dataclass
class BreakSegment:
    break_index: int
    start_at: datetime | None
    end_at: datetime | None
    paid: bool = False
    minutes: int = 0
    open: bool = False


@dataclass
class DayCalculation:
    work_date: date
    shift_id: str | None
    shift_key: str
    scheduled_start: time | None
    scheduled_end: time | None
    check_in_at: datetime | None
    check_out_at: datetime | None
    sessions: list[SessionSegment]
    breaks: list[BreakSegment]
    status: str
    exception_state: str
    late_minutes: int
    early_leave_minutes: int
    worked_minutes: int
    unpaid_break_minutes: int
    paid_break_minutes: int
    source_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["work_date"] = self.work_date.isoformat()
        payload["scheduled_start"] = self.scheduled_start.isoformat() if self.scheduled_start else None
        payload["scheduled_end"] = self.scheduled_end.isoformat() if self.scheduled_end else None
        for key in ("check_in_at", "check_out_at"):
            val = getattr(self, key)
            payload[key] = val.isoformat() if val else None
        payload["sessions"] = [
            {
                **asdict(s),
                "check_in_at": s.check_in_at.isoformat() if s.check_in_at else None,
                "check_out_at": s.check_out_at.isoformat() if s.check_out_at else None,
            }
            for s in self.sessions
        ]
        payload["breaks"] = [
            {
                **asdict(b),
                "start_at": b.start_at.isoformat() if b.start_at else None,
                "end_at": b.end_at.isoformat() if b.end_at else None,
            }
            for b in self.breaks
        ]
        return payload


def build_sessions_and_breaks(punches: list[dict[str, Any]]) -> tuple[list[SessionSegment], list[BreakSegment], str]:
    """Pair punches into sessions and breaks. Returns (sessions, breaks, exception)."""
    ordered = sorted(punches, key=lambda p: (as_kuwait(p["punched_at"]), str(p.get("punch_id") or "")))
    sessions: list[SessionSegment] = []
    breaks: list[BreakSegment] = []
    exception = "none"
    open_session: SessionSegment | None = None
    open_break: BreakSegment | None = None
    ambiguous = False

    for punch in ordered:
        direction = str(punch.get("direction") or "").lower()
        at = as_kuwait(punch["punched_at"])
        if direction == "in":
            if open_session and open_session.check_out_at is None:
                ambiguous = True
                # Close previous open session at this punch (treat as forced boundary).
                open_session.open = False
            open_session = SessionSegment(session_index=len(sessions) + 1, check_in_at=at, check_out_at=None, open=True)
            sessions.append(open_session)
        elif direction == "out":
            if open_session is None:
                # Orphan out — create incomplete session with checkout only.
                sessions.append(SessionSegment(session_index=len(sessions) + 1, check_in_at=None, check_out_at=at, open=False))
                ambiguous = True
            else:
                open_session.check_out_at = at
                open_session.worked_minutes = minutes_between(open_session.check_in_at, at)
                open_session.open = False
                open_session = None
        elif direction == "break_start":
            if open_break is not None:
                ambiguous = True
                open_break.open = False
            paid = bool(punch.get("break_paid"))
            open_break = BreakSegment(break_index=len(breaks) + 1, start_at=at, end_at=None, paid=paid, open=True)
            breaks.append(open_break)
        elif direction == "break_end":
            if open_break is None:
                ambiguous = True
                paid = bool(punch.get("break_paid"))
                breaks.append(BreakSegment(break_index=len(breaks) + 1, start_at=None, end_at=at, paid=paid, open=False))
            else:
                open_break.end_at = at
                open_break.minutes = minutes_between(open_break.start_at, at)
                open_break.open = False
                open_break = None
        else:
            ambiguous = True

    if open_session is not None:
        exception = "missing_check_out"
    if open_break is not None:
        ambiguous = True
    if any(s.check_in_at is None and s.check_out_at is not None for s in sessions):
        if exception == "none":
            exception = "missing_check_in"
    if ambiguous and exception == "none":
        exception = "ambiguous_punches"
    if any(s.open for s in sessions) and exception == "none":
        exception = "incomplete_session"
    return sessions, breaks, exception


def project_day_from_punches(
    punches: list[dict[str, Any]],
    *,
    work_date: date,
    shift: dict[str, Any] | None = None,
    forced_status: str | None = None,
) -> DayCalculation:
    shift_id = str(shift.get("shift_id")) if shift and shift.get("shift_id") else None
    skey = shift_key_of(shift_id)
    scheduled_start = parse_time((shift or {}).get("start_time") or (shift or {}).get("scheduled_start"))
    scheduled_end = parse_time((shift or {}).get("end_time") or (shift or {}).get("scheduled_end"))
    source_counts: dict[str, int] = {}
    for p in punches:
        src = str(p.get("source") or "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    if forced_status == "absent":
        return DayCalculation(
            work_date=work_date,
            shift_id=shift_id,
            shift_key=skey,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            check_in_at=None,
            check_out_at=None,
            sessions=[],
            breaks=[],
            status="absent",
            exception_state="none",
            late_minutes=0,
            early_leave_minutes=0,
            worked_minutes=0,
            unpaid_break_minutes=0,
            paid_break_minutes=0,
            source_counts=source_counts,
        )
    if forced_status == "approved_leave":
        return DayCalculation(
            work_date=work_date,
            shift_id=shift_id,
            shift_key=skey,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            check_in_at=None,
            check_out_at=None,
            sessions=[],
            breaks=[],
            status="approved_leave",
            exception_state="none",
            late_minutes=0,
            early_leave_minutes=0,
            worked_minutes=0,
            unpaid_break_minutes=0,
            paid_break_minutes=0,
            source_counts=source_counts,
        )

    sessions, breaks, exception = build_sessions_and_breaks(punches)
    check_ins = [s.check_in_at for s in sessions if s.check_in_at]
    check_outs = [s.check_out_at for s in sessions if s.check_out_at]
    check_in_at = min(check_ins) if check_ins else None
    check_out_at = max(check_outs) if check_outs else None

    unpaid = sum(b.minutes for b in breaks if not b.paid and b.minutes)
    paid = sum(b.minutes for b in breaks if b.paid and b.minutes)
    raw_worked = sum(s.worked_minutes for s in sessions if s.worked_minutes)
    # Unpaid breaks reduce paid worked time when nested in sessions.
    worked = max(0, raw_worked - unpaid)

    late = late_minutes(check_in_at, work_date, scheduled_start) if scheduled_start else 0
    early = early_leave_minutes(check_out_at, work_date, scheduled_start, scheduled_end) if scheduled_end else 0

    if not punches:
        status = "incomplete"
        exception = "missing_check_in"
    elif check_in_at and check_out_at and exception == "none":
        status = "late" if late else "completed"
    elif check_in_at and not check_out_at:
        status = "late" if late else "present"
        if exception == "none":
            exception = "missing_check_out"
    elif check_out_at and not check_in_at:
        status = "incomplete"
        if exception == "none":
            exception = "missing_check_in"
    else:
        status = "incomplete"

    return DayCalculation(
        work_date=work_date,
        shift_id=shift_id,
        shift_key=skey,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        check_in_at=check_in_at,
        check_out_at=check_out_at,
        sessions=sessions,
        breaks=breaks,
        status=status,
        exception_state=exception,
        late_minutes=late,
        early_leave_minutes=early,
        worked_minutes=worked,
        unpaid_break_minutes=unpaid,
        paid_break_minutes=paid,
        source_counts=source_counts,
    )


ATTENDANCE_LIFE_STATES = (
    "captured",
    "incomplete",
    "needs_review",
    "approved",
    "disputed",
    "locked",
    "absent",
    "on_leave",
)

_EXCEPTION_EXCLUSION_LABELS = {
    "missing_check_in": ("Missing check-in", "دخول ناقص"),
    "missing_check_out": ("Missing check-out", "خروج ناقص"),
    "ambiguous_punches": ("Ambiguous punches", "بصمات غامضة"),
    "incomplete_session": ("Incomplete session", "جلسة غير مكتملة"),
}


def _attendance_row_meta(row: dict[str, Any] | None) -> dict[str, Any]:
    data = row if isinstance(row, dict) else {}
    meta = data.get("metadata")
    if isinstance(meta, str):
        try:
            import json
            parsed = json.loads(meta)
            meta = parsed if isinstance(parsed, dict) else {}
        except Exception:
            meta = {}
    return meta if isinstance(meta, dict) else {}


def derive_attendance_life_state(row: dict[str, Any] | None) -> str:
    """Canonical attendance life-state from fields this API already owns."""
    data = row if isinstance(row, dict) else {}
    meta = _attendance_row_meta(data)
    exception = str(data.get("exception_state") or meta.get("exception_state") or "none")
    approval = str(data.get("approval_status") or meta.get("approval_status") or "").lower()
    status = str(data.get("status") or "").lower()
    locked = bool(data.get("payroll_locked") or meta.get("payroll_locked"))
    if locked:
        return "locked"
    if approval == "disputed" or status == "disputed":
        return "disputed"
    if approval == "approved":
        return "approved"
    if status == "approved_leave":
        return "on_leave"
    if status == "absent":
        return "absent"
    if exception and exception != "none":
        return "incomplete"
    late = int(data.get("late_minutes") or 0)
    early = int(data.get("early_leave_minutes") or meta.get("early_leave_minutes") or 0)
    if approval == "rejected" or late > 0 or early > 0:
        return "needs_review"
    if status in {"incomplete", "void"}:
        return "incomplete"
    return "captured"


def attendance_life_state(row: dict[str, Any] | None) -> str:
    data = row if isinstance(row, dict) else {}
    meta = _attendance_row_meta(data)
    provided = str(data.get("life_state") or meta.get("life_state") or "").strip().lower()
    if provided in ATTENDANCE_LIFE_STATES:
        return provided
    return derive_attendance_life_state(data)


def derive_payroll_exclusion_reasons(row: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Return (en, ar) payroll exclusion sentences, or (None, None) when eligible."""
    data = row if isinstance(row, dict) else {}
    meta = _attendance_row_meta(data)
    eligible = data.get("payroll_eligible")
    if eligible is None:
        eligible = meta.get("payroll_eligible")
    locked = bool(data.get("payroll_locked") or meta.get("payroll_locked"))
    exception = str(data.get("exception_state") or meta.get("exception_state") or "none")
    approval = str(data.get("approval_status") or meta.get("approval_status") or "").lower()
    status = str(data.get("status") or "").lower()
    if locked:
        return (
            "This period is locked in Payroll — attendance cannot be changed.",
            "الفترة مقفلة في كشف الرواتب — لا يمكن تعديل الحضور.",
        )
    if eligible is True and approval == "approved":
        return None, None
    if approval == "disputed":
        return (
            "Excluded from Payroll because this day is disputed until resolved.",
            "مستبعد من الرواتب لأن السجل متنازع عليه حتى يتم الحل.",
        )
    if exception and exception != "none":
        kind_en, kind_ar = _EXCEPTION_EXCLUSION_LABELS.get(
            exception,
            (exception.replace("_", " "), exception),
        )
        return (
            f"Excluded from Payroll: {kind_en}. Complete the correction, then approve the day.",
            f"مستبعد من الرواتب: {kind_ar}. أكمل التصحيح ثم اعتمد اليوم.",
        )
    if status in {"incomplete", "absent"}:
        return (
            "Excluded from Payroll until the record is reviewed and approved.",
            "مستبعد من الرواتب حتى يُراجع ويُعتمد السجل.",
        )
    if approval != "approved":
        return (
            "Excluded from Payroll until attendance is approved.",
            "مستبعد من الرواتب حتى يتم اعتماد الحضور.",
        )
    if eligible is False:
        return (
            "Excluded from Payroll for this day.",
            "مستبعد من الرواتب لهذا اليوم.",
        )
    return None, None


def payroll_exclusion_reason(row: dict[str, Any] | None, locale: str = "en") -> str | None:
    data = row if isinstance(row, dict) else {}
    meta = _attendance_row_meta(data)
    lang = "ar" if str(locale or "").strip().lower().startswith("ar") else "en"
    if lang == "ar":
        provided = str(
            data.get("payroll_exclusion_reason_ar")
            or meta.get("payroll_exclusion_reason_ar")
            or ""
        ).strip()
        if provided:
            return provided
    provided = str(
        data.get("payroll_exclusion_reason_en")
        or meta.get("payroll_exclusion_reason_en")
        or data.get("payroll_exclusion_reason")
        or meta.get("payroll_exclusion_reason")
        or ""
    ).strip()
    if provided:
        return provided
    en, ar = derive_payroll_exclusion_reasons(data)
    return ar if lang == "ar" else en


def attach_attendance_life_contract(row: dict[str, Any] | None) -> dict[str, Any]:
    """Stamp canonical life_state / payroll exclusion onto an attendance row."""
    data = row if isinstance(row, dict) else {}
    meta = dict(_attendance_row_meta(data))
    life = derive_attendance_life_state(data)
    en, ar = derive_payroll_exclusion_reasons(data)
    data["life_state"] = life
    data["payroll_exclusion_reason"] = en
    data["payroll_exclusion_reason_en"] = en
    data["payroll_exclusion_reason_ar"] = ar
    meta["life_state"] = life
    meta["payroll_exclusion_reason"] = en
    meta["payroll_exclusion_reason_en"] = en
    meta["payroll_exclusion_reason_ar"] = ar
    data["metadata"] = meta
    return data


def projection_to_compat_record(proj: dict[str, Any]) -> dict[str, Any]:
    """Map a day projection to the legacy attendance_records shape for clients."""
    proj_meta = proj.get("metadata") if isinstance(proj.get("metadata"), dict) else {}
    payroll_locked = proj.get("payroll_locked")
    if payroll_locked is None:
        payroll_locked = proj_meta.get("payroll_locked")
    record = {
        "attendance_id": proj.get("projection_id") or proj.get("attendance_id"),
        "company_code": proj.get("company_code"),
        "employee_key": proj.get("employee_key"),
        "employee_phone": proj.get("employee_phone"),
        "employee_name": proj.get("employee_name"),
        "shift_id": proj.get("shift_id"),
        "attendance_date": proj.get("work_date") or proj.get("attendance_date"),
        "scheduled_start": proj.get("scheduled_start"),
        "scheduled_end": proj.get("scheduled_end"),
        "check_in_at": proj.get("check_in_at"),
        "check_out_at": proj.get("check_out_at"),
        "status": proj.get("status"),
        "late_minutes": int(proj.get("late_minutes") or 0),
        "early_leave_minutes": int(proj.get("early_leave_minutes") or 0),
        "notes": proj_meta.get("notes") if proj_meta else proj.get("notes"),
        "source_text": proj_meta.get("source_text") if proj_meta else None,
        "approval_status": proj.get("approval_status"),
        "payroll_eligible": proj.get("payroll_eligible"),
        "payroll_locked": payroll_locked,
        "exception_state": proj.get("exception_state"),
        "metadata": {
            **proj_meta,
            "authority": AUTHORITY_VERSION,
            "projection_version": proj.get("version"),
            "exception_state": proj.get("exception_state"),
            "approval_status": proj.get("approval_status"),
            "payroll_eligible": proj.get("payroll_eligible"),
            "payroll_locked": payroll_locked,
            "sessions": proj.get("sessions") or [],
            "breaks": proj.get("breaks") or [],
            "worked_minutes": proj.get("worked_minutes"),
            "shift_key": proj.get("shift_key") or "",
        },
        "created_by_phone": proj.get("created_by_phone"),
        "created_at": proj.get("created_at"),
        "updated_at": proj.get("updated_at"),
    }
    return attach_attendance_life_contract(record)


# ---------------------------------------------------------------------------
# In-memory authority store (local/staging qualification without prod DB)
# ---------------------------------------------------------------------------

class InMemoryAuthorityStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.punches: list[dict[str, Any]] = []
        self.projections: list[dict[str, Any]] = []
        self.corrections: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []

    def append_punch(self, punch: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Returns (row, created). Duplicate (company, source, source_event_id) returns existing."""
        with self._lock:
            key = (
                str(punch["company_code"]).upper(),
                str(punch["source"]),
                str(punch["source_event_id"]),
            )
            for existing in self.punches:
                ek = (
                    str(existing["company_code"]).upper(),
                    str(existing["source"]),
                    str(existing["source_event_id"]),
                )
                if ek == key:
                    return copy.deepcopy(existing), False
            row = copy.deepcopy(punch)
            row.setdefault("punch_id", str(uuid.uuid4()))
            row.setdefault("created_at", datetime.now(KUWAIT_TZ))
            self.punches.append(row)
            return copy.deepcopy(row), True

    def list_punches(
        self,
        *,
        company_code: str,
        employee_key: str,
        work_date: date,
        shift_key: str = "",
    ) -> list[dict[str, Any]]:
        with self._lock:
            out = [
                copy.deepcopy(p)
                for p in self.punches
                if str(p["company_code"]).upper() == company_code.upper()
                and p["employee_key"] == employee_key
                and parse_date(p["work_date"]) == work_date
                and shift_key_of(p.get("shift_key")) == shift_key_of(shift_key)
            ]
            out.sort(key=lambda p: as_kuwait(p["punched_at"]) or datetime.min.replace(tzinfo=KUWAIT_TZ))
            return out

    def get_current_projection(
        self,
        *,
        company_code: str,
        employee_key: str,
        work_date: date,
        shift_key: str = "",
    ) -> dict[str, Any] | None:
        with self._lock:
            matches = [
                p
                for p in self.projections
                if str(p["company_code"]).upper() == company_code.upper()
                and p["employee_key"] == employee_key
                and parse_date(p["work_date"]) == work_date
                and shift_key_of(p.get("shift_key")) == shift_key_of(shift_key)
                and p.get("is_current")
            ]
            return copy.deepcopy(matches[-1]) if matches else None

    def insert_projection(self, proj: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            company = str(proj["company_code"]).upper()
            employee_key = proj["employee_key"]
            work_date = parse_date(proj["work_date"])
            skey = shift_key_of(proj.get("shift_key"))
            current = [
                p
                for p in self.projections
                if str(p["company_code"]).upper() == company
                and p["employee_key"] == employee_key
                and parse_date(p["work_date"]) == work_date
                and shift_key_of(p.get("shift_key")) == skey
                and p.get("is_current")
            ]
            version = 1
            if current:
                version = max(int(p.get("version") or 0) for p in current) + 1
                for p in current:
                    p["is_current"] = False
                    p["updated_at"] = datetime.now(KUWAIT_TZ)
            row = copy.deepcopy(proj)
            row["company_code"] = company
            row["shift_key"] = skey
            row["version"] = version
            row["is_current"] = True
            row.setdefault("projection_id", str(uuid.uuid4()))
            row.setdefault("created_at", datetime.now(KUWAIT_TZ))
            row["updated_at"] = datetime.now(KUWAIT_TZ)
            # link superseded
            for p in current:
                p["superseded_by"] = row["projection_id"]
            self.projections.append(row)
            return copy.deepcopy(row)

    def list_current_projections(
        self,
        *,
        company_code: str,
        start_date: date,
        end_date: date,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for p in self.projections:
                if not p.get("is_current"):
                    continue
                if str(p["company_code"]).upper() != company_code.upper():
                    continue
                wd = parse_date(p["work_date"])
                if not wd or wd < start_date or wd > end_date:
                    continue
                if employee_key and p["employee_key"] != employee_key:
                    continue
                if employee_keys is not None and p["employee_key"] not in employee_keys:
                    continue
                out.append(copy.deepcopy(p))
            out.sort(key=lambda r: (parse_date(r["work_date"]) or date.min, str(r.get("employee_name") or "")))
            return out

    def insert_correction(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            item = copy.deepcopy(row)
            item.setdefault("correction_id", str(uuid.uuid4()))
            item.setdefault("created_at", datetime.now(KUWAIT_TZ))
            item["updated_at"] = datetime.now(KUWAIT_TZ)
            self.corrections.append(item)
            return copy.deepcopy(item)

    def get_correction(self, correction_id: str, company_code: str) -> dict[str, Any] | None:
        with self._lock:
            for c in self.corrections:
                if c["correction_id"] == correction_id and str(c["company_code"]).upper() == company_code.upper():
                    return copy.deepcopy(c)
            return None

    def update_correction(self, correction_id: str, company_code: str, **fields: Any) -> dict[str, Any] | None:
        with self._lock:
            for c in self.corrections:
                if c["correction_id"] == correction_id and str(c["company_code"]).upper() == company_code.upper():
                    c.update(fields)
                    c["updated_at"] = datetime.now(KUWAIT_TZ)
                    return copy.deepcopy(c)
            return None

    def upsert_payroll_snapshot(self, snap: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            key = (
                str(snap["company_code"]).upper(),
                snap["employee_key"],
                parse_date(snap["work_date"]),
                shift_key_of(snap.get("shift_key")),
                int(snap["projection_version"]),
            )
            for existing in self.snapshots:
                ek = (
                    str(existing["company_code"]).upper(),
                    existing["employee_key"],
                    parse_date(existing["work_date"]),
                    shift_key_of(existing.get("shift_key")),
                    int(existing["projection_version"]),
                )
                if ek == key:
                    return copy.deepcopy(existing)
            row = copy.deepcopy(snap)
            row.setdefault("snapshot_id", str(uuid.uuid4()))
            row.setdefault("approved_at", datetime.now(KUWAIT_TZ))
            self.snapshots.append(row)
            return copy.deepcopy(row)

    def list_payroll_snapshots(
        self,
        *,
        company_code: str,
        start_date: date,
        end_date: date,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            # Latest approved version per employee-day-shift
            best: dict[tuple[str, date, str], dict[str, Any]] = {}
            for s in self.snapshots:
                if str(s["company_code"]).upper() != company_code.upper():
                    continue
                wd = parse_date(s["work_date"])
                if not wd or wd < start_date or wd > end_date:
                    continue
                if employee_key and s["employee_key"] != employee_key:
                    continue
                if employee_keys is not None and s["employee_key"] not in employee_keys:
                    continue
                k = (s["employee_key"], wd, shift_key_of(s.get("shift_key")))
                prev = best.get(k)
                if not prev or int(s["projection_version"]) > int(prev["projection_version"]):
                    best[k] = copy.deepcopy(s)
            return sorted(best.values(), key=lambda r: (parse_date(r["work_date"]) or date.min, r["employee_key"]))


# ---------------------------------------------------------------------------
# Canonical write service
# ---------------------------------------------------------------------------

class AttendanceAuthorityService:
    """Single write path for WhatsApp, import, HR, leave, and absence scan."""

    def __init__(self, store: Any | None = None) -> None:
        self.store = store or InMemoryAuthorityStore()

    def _day_tx(self, company: str, employee_key: str, work_date: date, shift_key: str = ""):
        if hasattr(self.store, "employee_day_transaction"):
            return self.store.employee_day_transaction(company, employee_key, work_date, shift_key)
        from contextlib import nullcontext

        return nullcontext()

    def ingest_punch(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        punched_at: datetime,
        direction: str,
        source: str,
        source_event_id: str,
        shift: dict[str, Any] | None = None,
        work_date: date | None = None,
        break_paid: bool | None = None,
        created_by_phone: str | None = None,
        metadata: dict[str, Any] | None = None,
        reproject: bool = True,
    ) -> dict[str, Any]:
        company = company_code.upper()
        direction_n = str(direction or "").lower().strip()
        source_n = str(source or "").lower().strip()
        if direction_n not in PUNCH_DIRECTIONS:
            return {"ok": False, "error": "invalid_direction", "direction": direction}
        if source_n not in PUNCH_SOURCES:
            return {"ok": False, "error": "invalid_source", "source": source}
        if not source_event_id:
            return {"ok": False, "error": "missing_source_event_id"}
        punch_at = as_kuwait(punched_at)
        assert punch_at is not None
        wd = attribute_work_date(punch_at, shift=shift, explicit_work_date=work_date)
        shift_id = str(shift.get("shift_id")) if shift and shift.get("shift_id") else None
        skey = shift_key_of(shift_id)
        punch = {
            "company_code": company,
            "employee_key": employee.get("employee_key"),
            "employee_phone": digits(employee.get("phone") or employee.get("employee_phone")),
            "employee_name": employee.get("name") or employee.get("employee_name"),
            "punched_at": punch_at,
            "direction": direction_n,
            "source": source_n,
            "source_event_id": str(source_event_id),
            "shift_id": shift_id,
            "shift_key": skey,
            "work_date": wd,
            "break_paid": break_paid,
            "metadata": metadata or {},
            "created_by_phone": digits(created_by_phone),
        }
        with self._day_tx(company, str(employee.get("employee_key")), wd, skey):
            row, created = self.store.append_punch(punch)
            result: dict[str, Any] = {
                "ok": True,
                "created": created,
                "duplicate": not created,
                "punch": row,
            }
            if reproject:
                proj = self.reproject_day(
                    company_code=company,
                    employee=employee,
                    work_date=wd,
                    shift=shift,
                    created_by_phone=created_by_phone,
                )
                result["projection"] = proj.get("projection")
                result["compat"] = proj.get("compat")
            return result

    def reproject_day(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        shift: dict[str, Any] | None = None,
        forced_status: str | None = None,
        created_by_phone: str | None = None,
        leave_id: str | None = None,
        derived_from_leave: bool = False,
        manual_correction: bool = False,
        metadata: dict[str, Any] | None = None,
        approval_status: str = "unapproved",
    ) -> dict[str, Any]:
        company = company_code.upper()
        skey = shift_key_of(shift.get("shift_id") if shift else None)
        punches = self.store.list_punches(
            company_code=company,
            employee_key=str(employee.get("employee_key")),
            work_date=work_date,
            shift_key=skey,
        )
        # Presence punches supersede a prior absence / leave when punches arrive.
        effective_forced = forced_status
        if punches and forced_status in {"absent", "approved_leave"}:
            effective_forced = None
        calc = project_day_from_punches(punches, work_date=work_date, shift=shift, forced_status=effective_forced)
        payroll_eligible = (
            approval_status == "approved"
            and calc.status in {"completed", "late", "present", "absent", "approved_leave"}
            and calc.exception_state == "none"
            and calc.status != "incomplete"
        )
        # Incomplete / exception days are never payroll eligible.
        if calc.exception_state != "none" or calc.status in {"incomplete", "void"}:
            payroll_eligible = False
        if approval_status != "approved":
            payroll_eligible = False

        proj = {
            "company_code": company,
            "employee_key": employee.get("employee_key"),
            "employee_phone": digits(employee.get("phone") or employee.get("employee_phone")),
            "employee_name": employee.get("name") or employee.get("employee_name"),
            "work_date": work_date,
            "shift_id": calc.shift_id,
            "shift_key": calc.shift_key,
            "status": calc.status,
            "exception_state": calc.exception_state,
            "approval_status": approval_status,
            "payroll_eligible": payroll_eligible,
            "check_in_at": calc.check_in_at,
            "check_out_at": calc.check_out_at,
            "scheduled_start": calc.scheduled_start,
            "scheduled_end": calc.scheduled_end,
            "late_minutes": calc.late_minutes,
            "early_leave_minutes": calc.early_leave_minutes,
            "worked_minutes": calc.worked_minutes,
            "unpaid_break_minutes": calc.unpaid_break_minutes,
            "paid_break_minutes": calc.paid_break_minutes,
            "sessions": [
                {
                    **asdict(s),
                    "check_in_at": s.check_in_at.isoformat() if s.check_in_at else None,
                    "check_out_at": s.check_out_at.isoformat() if s.check_out_at else None,
                }
                for s in calc.sessions
            ],
            "breaks": [
                {
                    **asdict(b),
                    "start_at": b.start_at.isoformat() if b.start_at else None,
                    "end_at": b.end_at.isoformat() if b.end_at else None,
                }
                for b in calc.breaks
            ],
            "source_counts": calc.source_counts,
            "authority": AUTHORITY_VERSION,
            "leave_id": leave_id,
            "derived_from_leave": derived_from_leave,
            "manual_correction": manual_correction,
            "metadata": metadata or {},
            "created_by_phone": digits(created_by_phone),
        }
        saved = self.store.insert_projection(proj)
        return {"ok": True, "projection": saved, "compat": projection_to_compat_record(saved), "calculation": calc.to_dict()}

    def mark_absent(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        shift: dict[str, Any] | None = None,
        source: str = "absence_scan",
        source_event_id: str,
        created_by_phone: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        skey = shift_key_of(shift.get("shift_id") if shift else None)
        with self._day_tx(company, str(employee.get("employee_key")), work_date, skey):
            existing_punches = self.store.list_punches(
                company_code=company,
                employee_key=str(employee.get("employee_key")),
                work_date=work_date,
                shift_key=skey,
            )
            if any(p.get("direction") == "in" for p in existing_punches):
                return {
                    "ok": False,
                    "error": "check_in_already_exists",
                    "race": "absence_vs_check_in",
                    "punches": existing_punches,
                }
            current = self.store.get_current_projection(
                company_code=company,
                employee_key=str(employee.get("employee_key")),
                work_date=work_date,
                shift_key=skey,
            )
            if current and current.get("status") not in {"absent", "void"} and current.get("check_in_at"):
                return {"ok": False, "error": "attendance_already_present", "projection": current}

            if current and current.get("status") == "absent":
                meta = current.get("metadata") or {}
                if meta.get("source_event_id") == source_event_id:
                    return {"ok": True, "duplicate": True, "projection": current, "compat": projection_to_compat_record(current)}

            return self.reproject_day(
                company_code=company,
                employee=employee,
                work_date=work_date,
                shift=shift,
                forced_status="absent",
                created_by_phone=created_by_phone,
                metadata={"source": source, "source_event_id": source_event_id, "notes": notes},
            )

    def apply_leave(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        leave_id: str,
        shift: dict[str, Any] | None = None,
        created_by_phone: str | None = None,
    ) -> dict[str, Any]:
        return self.reproject_day(
            company_code=company_code,
            employee=employee,
            work_date=work_date,
            shift=shift,
            forced_status="approved_leave",
            leave_id=leave_id,
            derived_from_leave=True,
            created_by_phone=created_by_phone,
            metadata={"source": "leave", "leave_id": leave_id},
        )

    def reverse_leave(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        leave_id: str,
        shift: dict[str, Any] | None = None,
        created_by_phone: str | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        skey = shift_key_of(shift.get("shift_id") if shift else None)
        current = self.store.get_current_projection(
            company_code=company,
            employee_key=str(employee.get("employee_key")),
            work_date=work_date,
            shift_key=skey,
        )
        if not current:
            return {"ok": True, "reversed": False, "reason": "no_projection"}
        if current.get("manual_correction"):
            return {
                "ok": True,
                "reversed": False,
                "reason": "manual_correction_preserved",
                "projection": current,
            }
        if not current.get("derived_from_leave"):
            return {"ok": True, "reversed": False, "reason": "not_leave_derived", "projection": current}
        if str(current.get("leave_id") or "") != str(leave_id):
            return {"ok": True, "reversed": False, "reason": "leave_id_mismatch", "projection": current}
        # Void leave-derived version; reproject from remaining punches (may be empty → incomplete).
        return self.reproject_day(
            company_code=company,
            employee=employee,
            work_date=work_date,
            shift=shift,
            forced_status=None,
            created_by_phone=created_by_phone,
            metadata={"source": "leave_reversal", "leave_id": leave_id, "reversed": True},
        )

    def request_correction(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        requested_by_phone: str,
        changes: dict[str, Any],
        shift: dict[str, Any] | None = None,
        actor_is_manager: bool = False,
    ) -> dict[str, Any]:
        company = company_code.upper()
        emp_phone = digits(employee.get("phone") or employee.get("employee_phone"))
        actor = digits(requested_by_phone)
        # Explicit manager self-correction denial.
        if actor_is_manager and actor and emp_phone and actor == emp_phone:
            return {
                "ok": False,
                "error": "manager_self_correction_denied",
                "employee_key": employee.get("employee_key"),
            }
        skey = shift_key_of(shift.get("shift_id") if shift else None)
        current = self.store.get_current_projection(
            company_code=company,
            employee_key=str(employee.get("employee_key")),
            work_date=work_date,
            shift_key=skey,
        )
        row = self.store.insert_correction(
            {
                "company_code": company,
                "employee_key": employee.get("employee_key"),
                "employee_phone": emp_phone,
                "work_date": work_date,
                "shift_key": skey,
                "projection_id": (current or {}).get("projection_id"),
                "status": "requested",
                "requested_changes": changes,
                "requested_by_phone": actor,
                "metadata": {"actor_is_manager": actor_is_manager},
            }
        )
        return {"ok": True, "correction": row}

    def review_correction(
        self,
        *,
        company_code: str,
        correction_id: str,
        decision: str,
        decided_by_phone: str,
        decision_note: str | None = None,
        dispute_reason: str | None = None,
        employee: dict[str, Any] | None = None,
        shift: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        decision_n = str(decision or "").lower().strip()
        if decision_n not in {"approved", "rejected", "disputed"}:
            return {"ok": False, "error": "invalid_decision", "decision": decision}
        corr = self.store.get_correction(correction_id, company)
        if not corr:
            return {"ok": False, "error": "correction_not_found"}
        if corr.get("status") != "requested":
            return {"ok": False, "error": "correction_not_open", "correction": corr}

        updated = self.store.update_correction(
            correction_id,
            company,
            status=decision_n,
            decision_note=decision_note,
            decided_by_phone=digits(decided_by_phone),
            decided_at=datetime.now(KUWAIT_TZ),
            dispute_reason=dispute_reason if decision_n == "disputed" else None,
        )
        result: dict[str, Any] = {"ok": True, "correction": updated}
        if decision_n != "approved":
            # Mark current projection approval_status accordingly without inventing punches.
            if employee:
                current = self.store.get_current_projection(
                    company_code=company,
                    employee_key=str(corr["employee_key"]),
                    work_date=parse_date(corr["work_date"]) or date.today(),
                    shift_key=shift_key_of(corr.get("shift_key")),
                )
                if current:
                    proj = self.reproject_day(
                        company_code=company,
                        employee=employee,
                        work_date=parse_date(corr["work_date"]) or date.today(),
                        shift=shift,
                        forced_status=current.get("status") if current.get("status") in {"absent", "approved_leave"} else None,
                        created_by_phone=decided_by_phone,
                        manual_correction=False,
                        approval_status=decision_n,
                        metadata={"correction_id": correction_id, "decision": decision_n},
                    )
                    # Restore punch-based calc if not forced.
                    if current.get("status") not in {"absent", "approved_leave"}:
                        # reproject already used punches
                        pass
                    result["projection"] = proj.get("projection")
            return result

        # Approved: apply requested changes as correction punches + new version.
        if not employee:
            return {"ok": False, "error": "employee_required_for_approve", "correction": updated}
        changes = corr.get("requested_changes") or {}
        work_date = parse_date(corr["work_date"]) or date.today()
        # Optional explicit punches in changes.
        applied_punches = []
        for idx, punch_spec in enumerate(changes.get("punches") or []):
            direction = punch_spec.get("direction")
            at = punch_spec.get("punched_at")
            if isinstance(at, str):
                at = datetime.fromisoformat(at.replace("Z", "+00:00"))
            if not direction or not at:
                continue
            pr = self.ingest_punch(
                company_code=company,
                employee=employee,
                punched_at=as_kuwait(at),  # type: ignore[arg-type]
                direction=direction,
                source="correction",
                source_event_id=f"correction:{correction_id}:{idx}",
                shift=shift,
                work_date=work_date,
                break_paid=punch_spec.get("break_paid"),
                created_by_phone=decided_by_phone,
                metadata={"correction_id": correction_id},
                reproject=False,
            )
            applied_punches.append(pr)

        # Convenience: check_in_at / check_out_at fields
        if changes.get("check_in_at"):
            at = changes["check_in_at"]
            if isinstance(at, str):
                at = datetime.fromisoformat(at.replace("Z", "+00:00"))
            pr = self.ingest_punch(
                company_code=company,
                employee=employee,
                punched_at=as_kuwait(at),  # type: ignore[arg-type]
                direction="in",
                source="correction",
                source_event_id=f"correction:{correction_id}:check_in",
                shift=shift,
                work_date=work_date,
                created_by_phone=decided_by_phone,
                reproject=False,
            )
            applied_punches.append(pr)
        if changes.get("check_out_at"):
            at = changes["check_out_at"]
            if isinstance(at, str):
                at = datetime.fromisoformat(at.replace("Z", "+00:00"))
            pr = self.ingest_punch(
                company_code=company,
                employee=employee,
                punched_at=as_kuwait(at),  # type: ignore[arg-type]
                direction="out",
                source="correction",
                source_event_id=f"correction:{correction_id}:check_out",
                shift=shift,
                work_date=work_date,
                created_by_phone=decided_by_phone,
                reproject=False,
            )
            applied_punches.append(pr)

        forced = changes.get("status") if changes.get("status") in {"absent", "approved_leave"} else None
        proj = self.reproject_day(
            company_code=company,
            employee=employee,
            work_date=work_date,
            shift=shift,
            forced_status=forced,
            created_by_phone=decided_by_phone,
            manual_correction=True,
            approval_status="unapproved",
            metadata={"correction_id": correction_id, "source": "correction"},
        )
        self.store.update_correction(
            correction_id,
            company,
            resulting_projection_id=(proj.get("projection") or {}).get("projection_id"),
        )
        result["projection"] = proj.get("projection")
        result["compat"] = proj.get("compat")
        result["applied_punches"] = applied_punches
        return result

    def approve_day(
        self,
        *,
        company_code: str,
        employee: dict[str, Any],
        work_date: date,
        approved_by_phone: str,
        shift: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        company = company_code.upper()
        skey = shift_key_of(shift.get("shift_id") if shift else None)
        with self._day_tx(company, str(employee.get("employee_key")), work_date, skey):
            current = self.store.get_current_projection(
                company_code=company,
                employee_key=str(employee.get("employee_key")),
                work_date=work_date,
                shift_key=skey,
            )
            if not current:
                return {"ok": False, "error": "projection_not_found"}
            if current.get("exception_state") not in {None, "none"}:
                return {"ok": False, "error": "incomplete_or_exception_not_approvable", "projection": current}
            if current.get("status") in {"incomplete", "void"}:
                return {"ok": False, "error": "incomplete_or_exception_not_approvable", "projection": current}

            forced = current.get("status") if current.get("status") in {"absent", "approved_leave"} else None
            proj = self.reproject_day(
                company_code=company,
                employee=employee,
                work_date=work_date,
                shift=shift or {
                    "shift_id": current.get("shift_id"),
                    "shift_date": work_date,
                    "start_time": current.get("scheduled_start"),
                    "end_time": current.get("scheduled_end"),
                },
                forced_status=forced,
                created_by_phone=approved_by_phone,
                leave_id=current.get("leave_id"),
                derived_from_leave=bool(current.get("derived_from_leave")),
                manual_correction=bool(current.get("manual_correction")),
                approval_status="approved",
                metadata={**(current.get("metadata") or {}), "approved_by": digits(approved_by_phone)},
            )
            saved = proj["projection"]
            if not saved.get("payroll_eligible"):
                return {"ok": False, "error": "not_payroll_eligible", "projection": saved}

            snap = self.store.upsert_payroll_snapshot(
                {
                    "company_code": company,
                    "employee_key": saved["employee_key"],
                    "employee_phone": saved.get("employee_phone"),
                    "employee_name": saved.get("employee_name"),
                    "work_date": work_date,
                    "shift_id": saved.get("shift_id"),
                    "shift_key": saved.get("shift_key") or "",
                    "projection_id": saved["projection_id"],
                    "projection_version": int(saved["version"]),
                    "approved_by_phone": digits(approved_by_phone),
                    "payload": {
                        "status": saved.get("status"),
                        "check_in_at": saved.get("check_in_at").isoformat() if isinstance(saved.get("check_in_at"), datetime) else saved.get("check_in_at"),
                        "check_out_at": saved.get("check_out_at").isoformat() if isinstance(saved.get("check_out_at"), datetime) else saved.get("check_out_at"),
                        "scheduled_start": saved.get("scheduled_start").isoformat() if isinstance(saved.get("scheduled_start"), time) else saved.get("scheduled_start"),
                        "scheduled_end": saved.get("scheduled_end").isoformat() if isinstance(saved.get("scheduled_end"), time) else saved.get("scheduled_end"),
                        "late_minutes": saved.get("late_minutes"),
                        "early_leave_minutes": saved.get("early_leave_minutes"),
                        "worked_minutes": saved.get("worked_minutes"),
                        "unpaid_break_minutes": saved.get("unpaid_break_minutes"),
                        "paid_break_minutes": saved.get("paid_break_minutes"),
                        "sessions": saved.get("sessions"),
                        "breaks": saved.get("breaks"),
                        "exception_state": saved.get("exception_state"),
                        "authority": AUTHORITY_VERSION,
                    },
                }
            )
            return {"ok": True, "projection": saved, "snapshot": snap, "compat": proj.get("compat")}

    def list_compat_attendance(
        self,
        *,
        company_code: str,
        start_date: date,
        end_date: date,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.store.list_current_projections(
            company_code=company_code,
            start_date=start_date,
            end_date=end_date,
            employee_key=employee_key,
            employee_keys=employee_keys,
        )
        return [projection_to_compat_record(r) for r in rows if r.get("status") != "void"]

    def list_payroll_hours_from_snapshots(
        self,
        *,
        company_code: str,
        start_date: date,
        end_date: date,
        employee_key: str | None = None,
        employee_keys: set[str] | None = None,
        shifts: list[dict[str, Any]] | None = None,
        leaves: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        snaps = self.store.list_payroll_snapshots(
            company_code=company_code,
            start_date=start_date,
            end_date=end_date,
            employee_key=employee_key,
            employee_keys=employee_keys,
        )
        summaries: dict[str, dict[str, Any]] = {}

        def ensure(key: str, *, name: str | None = None, phone: str | None = None) -> dict[str, Any]:
            s = summaries.setdefault(
                key,
                {
                    "employee_key": key,
                    "employee_name": name or "",
                    "employee_phone": digits(phone),
                    "scheduled_minutes": 0,
                    "worked_minutes": 0,
                    "approved_leave_minutes": 0,
                    "absent_minutes": 0,
                    "late_minutes": 0,
                    "early_leave_minutes": 0,
                    "overtime_minutes": 0,
                    "shift_count": 0,
                    "attendance_count": 0,
                    "approved_leave_days": 0,
                    "snapshot_count": 0,
                },
            )
            if name and not s.get("employee_name"):
                s["employee_name"] = name
            if phone and not s.get("employee_phone"):
                s["employee_phone"] = digits(phone)
            return s

        for shift in shifts or []:
            key = str(shift.get("employee_key") or "")
            if not key:
                continue
            if employee_key and key != employee_key:
                continue
            if employee_keys is not None and key not in employee_keys:
                continue
            s = ensure(key, name=shift.get("employee_name"), phone=shift.get("employee_phone"))
            mins = scheduled_minutes(shift.get("start_time"), shift.get("end_time"))
            s["scheduled_minutes"] += mins
            s["shift_count"] += 1

        for snap in snaps:
            key = str(snap.get("employee_key") or "")
            if not key:
                continue
            s = ensure(key, name=snap.get("employee_name"), phone=snap.get("employee_phone"))
            payload = snap.get("payload") or {}
            s["attendance_count"] += 1
            s["snapshot_count"] += 1
            s["late_minutes"] += int(payload.get("late_minutes") or 0)
            s["early_leave_minutes"] += int(payload.get("early_leave_minutes") or 0)
            s["worked_minutes"] += int(payload.get("worked_minutes") or 0)
            status = str(payload.get("status") or "")
            sched = scheduled_minutes(payload.get("scheduled_start"), payload.get("scheduled_end"))
            if status == "absent":
                s["absent_minutes"] += sched
            elif status == "approved_leave":
                s["approved_leave_minutes"] += sched
                s["approved_leave_days"] += 1

        for leave in leaves or []:
            key = str(leave.get("employee_key") or "")
            if key:
                ensure(key, name=leave.get("employee_name"), phone=leave.get("employee_phone"))

        for s in summaries.values():
            s["overtime_minutes"] = max(0, int(s["worked_minutes"]) - int(s["scheduled_minutes"]))
            if s["absent_minutes"]:
                s["payroll_status"] = "Needs review"
            elif s["late_minutes"] or s["early_leave_minutes"]:
                s["payroll_status"] = "Review exceptions"
            else:
                s["payroll_status"] = "Ready"

        out = sorted(summaries.values(), key=lambda item: (str(item.get("employee_name") or "").lower(), item["employee_key"]))
        return {
            "ok": True,
            "company_code": company_code.upper(),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "summaries": out,
            "count": len(out),
            "source_counts": {"approved_snapshots": len(snaps), "shifts": len(shifts or []), "approved_leave": len(leaves or [])},
            "authority": "approved_attendance_snapshots",
            "label": "approved_attendance",
            "money_authority": "approved_timesheets",
            "unapproved_excluded": True,
        }


# Module-level default service for pure local tests / staged wiring.
_DEFAULT_SERVICES: dict[str, AttendanceAuthorityService] = {}
_DEFAULT_LOCK = threading.Lock()
_PG_STORE_SINGLETON: Any | None = None


def get_authority_service(company_code: str | None = None, *, store: Any | None = None) -> AttendanceAuthorityService:
    """Return authority service.

    Store selection:
      - explicit `store` argument
      - WATHEFNI_ATTENDANCE_AUTHORITY_STORE=memory → in-memory (tests)
      - postgres (default when authority enabled) → shared PostgresAuthorityStore
      - otherwise in-memory per company key
    """
    if store is not None:
        return AttendanceAuthorityService(store=store)
    try:
        import attendance_authority_postgres as pg

        mode = pg.authority_store_mode()
    except Exception:
        mode = "memory"
        pg = None  # type: ignore

    if mode == "postgres" and pg is not None:
        global _PG_STORE_SINGLETON
        with _DEFAULT_LOCK:
            if _PG_STORE_SINGLETON is None:
                # Lazy import app.db_connect to avoid circular import at module load.
                def _connect():
                    import app as _app

                    return _app.db_connect()

                _PG_STORE_SINGLETON = pg.PostgresAuthorityStore(_connect)
            return AttendanceAuthorityService(store=_PG_STORE_SINGLETON)

    key = str(company_code or "_default").upper()
    with _DEFAULT_LOCK:
        if key not in _DEFAULT_SERVICES:
            _DEFAULT_SERVICES[key] = AttendanceAuthorityService()
        return _DEFAULT_SERVICES[key]


def reset_authority_services_for_tests() -> None:
    global _PG_STORE_SINGLETON
    with _DEFAULT_LOCK:
        _DEFAULT_SERVICES.clear()
        _PG_STORE_SINGLETON = None


def ensure_attendance_authority_schema(cur: Any) -> None:
    cur.execute(SCHEMA_DDL)
    try:
        import attendance_authority_postgres as pg

        cur.execute(pg.WAVE1B_SCHEMA_DDL)
    except Exception:
        # Wave 1B module optional during pure Wave 1 imports.
        pass
