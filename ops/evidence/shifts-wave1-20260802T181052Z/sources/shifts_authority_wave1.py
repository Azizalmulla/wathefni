"""Shifts Wave 1 — authority, safety & overnight foundation (local/staging).

L0 assignment remains canonical. Does NOT build templates/recurring/publish/open shifts.
Does NOT calculate Payroll money. Does NOT mutate Leave balances.

Overnight contract matches Attendance `shift_window`: end_time <= start_time ⇒ ends next day.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

SHIFTS_WAVE1_VERSION = "1.0.0"
KUWAIT_TZ = timezone(timedelta(hours=3), name="Asia/Kuwait")
_ON = {"1", "true", "yes", "on"}

DEFAULT_SYNTHETIC_KEY_MARKERS = ("SHW1", "SHW1-SYNTH|")
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965528",)

# Python weekday: Mon=0 … Fri=4, Sat=5, Sun=6. Default rest preference Fri only
# (not a hard legal sole rest day — configurable).
DEFAULT_REST_WEEKDAYS = (4,)

LEAVE_CONFLICT_BLOCK = "block"
LEAVE_CONFLICT_REQUIRE_ACK = "require_ack"
LEAVE_CONFLICT_CANCEL_SHIFT = "cancel_shift"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shift_authority_settings (
  company_code text PRIMARY KEY,
  allow_overnight boolean NOT NULL DEFAULT true,
  rest_weekdays integer[] NOT NULL DEFAULT ARRAY[4],
  leave_conflict_mode text NOT NULL DEFAULT 'require_ack',
  block_terminated boolean NOT NULL DEFAULT true,
  block_suspended boolean NOT NULL DEFAULT true,
  block_future_start boolean NOT NULL DEFAULT true,
  block_notice_period boolean NOT NULL DEFAULT true,
  synthetic_only boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_leave_conflict_mode_chk
    CHECK (leave_conflict_mode IN ('block','require_ack','cancel_shift'))
);

CREATE TABLE IF NOT EXISTS shift_orphan_quarantine (
  quarantine_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  employee_key text,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason text NOT NULL DEFAULT 'orphan_employee_key',
  status text NOT NULL DEFAULT 'quarantined',
  quarantined_by_phone text,
  restored_by_phone text,
  quarantined_at timestamptz NOT NULL DEFAULT now(),
  restored_at timestamptz,
  CONSTRAINT shift_orphan_status_chk CHECK (status IN ('quarantined','restored','purged'))
);
CREATE INDEX IF NOT EXISTS idx_shift_orphan_company_status
  ON shift_orphan_quarantine(company_code, status);

ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS ends_next_day boolean NOT NULL DEFAULT false;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS break_minutes integer;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS site_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS branch_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS team_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS position_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS idempotency_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shift_assignments_idempotency
  ON shift_assignments(company_code, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';
"""


def shifts_wave1_enabled() -> bool:
    raw = os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_WAVE1")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON


def shifts_authority_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_COMPANIES") or "").strip()
    if not raw:
        return {"WATHEFNI"}  # Wave 1 qualification: WATHEFNI only by default
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def shifts_authority_enabled_for_company(company_code: str | None) -> bool:
    if not shifts_wave1_enabled():
        return False
    allowed = shifts_authority_companies()
    if not allowed:
        return True
    return str(company_code or "").strip().upper() in allowed


def shifts_authority_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_PHONE_PREFIXES


def digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_shift_synthetic_employee(
    employee: dict[str, Any] | None = None,
    *,
    employee_key: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> bool:
    key = str((employee or {}).get("employee_key") or employee_key or "")
    phone_d = digits((employee or {}).get("phone") or (employee or {}).get("employee_phone") or phone)
    nm = str((employee or {}).get("name") or name or "")
    for marker in synthetic_key_markers():
        if marker and (marker in key or marker in nm):
            return True
    for prefix in synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    return False


def shifts_authority_applies_to(
    company_code: str | None,
    employee: dict[str, Any] | None = None,
    *,
    employee_key: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> bool:
    """True when Wave 1 gates should run for this subject."""
    if not shifts_authority_enabled_for_company(company_code):
        return False
    settings_synthetic = shifts_authority_synthetic_only()
    if not settings_synthetic:
        return True
    return is_shift_synthetic_employee(
        employee, employee_key=employee_key, phone=phone, name=name
    )


def ensure_shifts_authority_wave1_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def seed_shift_authority_settings(cur: Any, company_code: str) -> None:
    company = (company_code or "").upper()
    if not company:
        return
    cur.execute(
        """
        INSERT INTO shift_authority_settings (company_code)
        VALUES (%s)
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def get_shift_authority_settings(cur: Any, company_code: str) -> dict[str, Any]:
    company = (company_code or "").upper()
    ensure_shifts_authority_wave1_schema(cur)
    seed_shift_authority_settings(cur, company)
    cur.execute("SELECT * FROM shift_authority_settings WHERE company_code=%s LIMIT 1", (company,))
    row = cur.fetchone()
    d = dict(row) if row else {}
    rest = d.get("rest_weekdays") or list(DEFAULT_REST_WEEKDAYS)
    if isinstance(rest, tuple):
        rest = list(rest)
    allow_overnight_env = os.environ.get("WATHEFNI_SHIFTS_ALLOW_OVERNIGHT")
    allow_overnight = bool(d.get("allow_overnight", True))
    if allow_overnight_env is not None and str(allow_overnight_env).strip() != "":
        allow_overnight = str(allow_overnight_env).strip().lower() in _ON
    mode = str(d.get("leave_conflict_mode") or LEAVE_CONFLICT_REQUIRE_ACK).strip().lower()
    if mode not in {LEAVE_CONFLICT_BLOCK, LEAVE_CONFLICT_REQUIRE_ACK, LEAVE_CONFLICT_CANCEL_SHIFT}:
        mode = LEAVE_CONFLICT_REQUIRE_ACK
    env_mode = str(os.environ.get("WATHEFNI_SHIFTS_LEAVE_CONFLICT_MODE") or "").strip().lower()
    if env_mode in {LEAVE_CONFLICT_BLOCK, LEAVE_CONFLICT_REQUIRE_ACK, LEAVE_CONFLICT_CANCEL_SHIFT}:
        mode = env_mode
    return {
        "company_code": company,
        "allow_overnight": allow_overnight,
        "rest_weekdays": [int(x) for x in rest],
        "leave_conflict_mode": mode,
        "block_terminated": bool(d.get("block_terminated", True)),
        "block_suspended": bool(d.get("block_suspended", True)),
        "block_future_start": bool(d.get("block_future_start", True)),
        "block_notice_period": bool(d.get("block_notice_period", True)),
        "synthetic_only": bool(d.get("synthetic_only", False)) or shifts_authority_synthetic_only(),
    }


def allow_overnight(settings: dict[str, Any] | None = None) -> bool:
    if settings is not None:
        return bool(settings.get("allow_overnight", True))
    raw = os.environ.get("WATHEFNI_SHIFTS_ALLOW_OVERNIGHT")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() in _ON


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
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def ends_next_day_for(start_time: Any, end_time: Any) -> bool:
    st = parse_time(start_time)
    et = parse_time(end_time)
    if not st or not et:
        return False
    return et <= st


def shift_window(
    work_date: date,
    start_time: Any,
    end_time: Any,
    *,
    ends_next_day: bool | None = None,
    tz: timezone = KUWAIT_TZ,
) -> tuple[datetime, datetime] | None:
    """Attendance-compatible [start, end) window. Overnight when end <= start.

    Matches attendance_authority_wave1.shift_window: if et <= st, end += 1 day.
    Optional ends_next_day reinforces that contract when clocks already imply overnight.
    """
    st = parse_time(start_time)
    et = parse_time(end_time)
    if not st or not et:
        return None
    start_dt = datetime.combine(work_date, st, tzinfo=tz)
    end_dt = datetime.combine(work_date, et, tzinfo=tz)
    overnight = et <= st
    if ends_next_day is True and overnight:
        overnight = True
    if overnight:
        end_dt += timedelta(days=1)
    return start_dt, end_dt


def intervals_overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


def normalize_time_range(
    start_time: Any,
    end_time: Any,
    *,
    allow_overnight_flag: bool,
) -> tuple[time | None, time | None, bool, str | None]:
    """Return (start, end, ends_next_day, error)."""
    st = parse_time(start_time)
    et = parse_time(end_time)
    if not st or not et:
        return None, None, False, "missing_shift_time"
    if et <= st:
        if not allow_overnight_flag:
            return st, et, False, "overnight_not_allowed"
        return st, et, True, None
    return st, et, False, None


def lifecycle_gate_for_shifts(
    *,
    label: str,
    settings: dict[str, Any],
    operation: str = "create",
) -> dict[str, Any] | None:
    lab = str(label or "unknown")
    op = str(operation or "create")
    if lab in {"terminated", "left"} and settings.get("block_terminated", True):
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Shifts are not allowed for terminated employees.",
        }
    if lab == "suspended" and settings.get("block_suspended", True):
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Shifts are not allowed while the employee is suspended.",
        }
    if lab == "future_start" and settings.get("block_future_start", True):
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Shifts are not allowed before the employee start date.",
        }
    if lab == "notice_period" and settings.get("block_notice_period", True):
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Shifts are not allowed during notice period under current policy.",
        }
    return None


def self_swap_decision_denied(
    *,
    swap: dict[str, Any],
    actor_phone: str | None,
) -> dict[str, Any] | None:
    actor = digits(actor_phone)
    if not actor:
        return None
    parties = {
        digits(swap.get("requester_employee_phone")),
        digits(swap.get("target_employee_phone")),
        digits(swap.get("requested_by_phone")),
    }
    parties.discard("")
    if actor in parties:
        return {
            "ok": False,
            "error": "self_swap_decision_forbidden",
            "message": "You cannot approve or reject a shift swap that involves you.",
        }
    return None


def find_overlapping_shifts(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    shift_date: date,
    start_time: Any,
    end_time: Any,
    ends_next_day: bool = False,
    exclude_shift_id: str | None = None,
) -> list[dict[str, Any]]:
    """Overnight-aware overlap across same-day, split, and cross-midnight windows."""
    company = (company_code or "").upper()
    win = shift_window(shift_date, start_time, end_time, ends_next_day=ends_next_day)
    if not win or not employee_key:
        return []
    start_dt, end_dt = win
    # Neighbour dates for overnight collisions
    dates = {shift_date, shift_date - timedelta(days=1), shift_date + timedelta(days=1)}
    cur.execute(
        """
        SELECT *
        FROM shift_assignments
        WHERE company_code=%s
          AND employee_key=%s
          AND status='scheduled'
          AND shift_date = ANY(%s::date[])
        ORDER BY shift_date, start_time
        """,
        (company, employee_key, sorted(dates)),
    )
    overlaps: list[dict[str, Any]] = []
    for row in cur.fetchall():
        d = dict(row)
        if exclude_shift_id and str(d.get("shift_id")) == str(exclude_shift_id):
            continue
        other_date = parse_date(d.get("shift_date"))
        if not other_date:
            continue
        other_end_next = bool(d.get("ends_next_day")) or ends_next_day_for(d.get("start_time"), d.get("end_time"))
        other = shift_window(other_date, d.get("start_time"), d.get("end_time"), ends_next_day=other_end_next)
        if not other:
            continue
        if intervals_overlap(start_dt, end_dt, other[0], other[1]):
            overlaps.append(d)
    return overlaps


def approved_leave_on_date(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    shift_date: date,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM leave_requests
        WHERE company_code=%s
          AND employee_key=%s
          AND status='approved'
          AND start_date <= %s AND end_date >= %s
        ORDER BY start_date
        LIMIT 20
        """,
        ((company_code or "").upper(), employee_key, shift_date, shift_date),
    )
    return [dict(r) for r in cur.fetchall()]


def leave_conflict_denied(
    *,
    mode: str,
    leaves: list[dict[str, Any]],
    action: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not leaves:
        return None
    m = str(mode or LEAVE_CONFLICT_REQUIRE_ACK).lower()
    ack = bool((action or {}).get("allow_leave_conflicts") or (action or {}).get("ack_leave_conflict"))
    cancel = bool((action or {}).get("cancel_conflicting_leave_shifts"))  # reserved
    _ = cancel
    if m == LEAVE_CONFLICT_BLOCK:
        return {
            "ok": False,
            "error": "shift_leave_conflict",
            "leave_conflict_mode": m,
            "leaves": leaves,
            "message": "This shift overlaps approved leave and is blocked by policy.",
        }
    if m == LEAVE_CONFLICT_REQUIRE_ACK and not ack:
        return {
            "ok": False,
            "error": "shift_leave_conflict_ack_required",
            "needs_confirmation": True,
            "leave_conflict_mode": m,
            "leaves": leaves,
            "message": "This shift overlaps approved leave. Acknowledge the conflict to continue.",
        }
    # cancel_shift mode on create: still require explicit ack; actual cancel is leave-approve path
    if m == LEAVE_CONFLICT_CANCEL_SHIFT and not ack:
        return {
            "ok": False,
            "error": "shift_leave_conflict_ack_required",
            "needs_confirmation": True,
            "leave_conflict_mode": m,
            "leaves": leaves,
            "message": "Approved leave overlaps this date. Acknowledge or cancel conflicting shifts first.",
        }
    return None


def synthetic_gate_denied(
    *,
    settings: dict[str, Any],
    employee: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not settings.get("synthetic_only"):
        return None
    if is_shift_synthetic_employee(employee):
        return None
    return {
        "ok": False,
        "error": "shifts_synthetic_only_gate",
        "message": "Shifts authority Wave 1 is synthetic-only for this environment.",
    }


def quarantine_orphan_shift(
    cur: Any,
    *,
    company_code: str,
    shift: dict[str, Any],
    actor_phone: str | None,
    reason: str = "orphan_employee_key",
) -> dict[str, Any]:
    """Cancel scheduled orphan and record reversible quarantine snapshot."""
    import json

    company = (company_code or "").upper()
    shift_id = shift.get("shift_id")
    ensure_shifts_authority_wave1_schema(cur)
    cur.execute(
        """
        UPDATE shift_assignments
        SET status='cancelled', updated_at=now(), row_version=COALESCE(row_version,1)+1
        WHERE shift_id=%s AND company_code=%s AND status='scheduled'
        RETURNING *
        """,
        (shift_id, company),
    )
    updated = cur.fetchone()
    cur.execute(
        """
        INSERT INTO shift_orphan_quarantine (
          company_code, shift_id, employee_key, snapshot, reason, status, quarantined_by_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s,'quarantined',%s)
        RETURNING *
        """,
        (
            company,
            shift_id,
            shift.get("employee_key"),
            json.dumps({k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v for k, v in dict(shift).items()}, default=str),
            reason,
            digits(actor_phone),
        ),
    )
    q = dict(cur.fetchone())
    return {"ok": True, "quarantine": q, "shift": dict(updated) if updated else shift}


def restore_quarantined_shift(
    cur: Any,
    *,
    company_code: str,
    quarantine_id: str,
    actor_phone: str | None,
    require_employee_exists: bool = True,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    ensure_shifts_authority_wave1_schema(cur)
    cur.execute(
        """
        SELECT * FROM shift_orphan_quarantine
        WHERE quarantine_id=%s AND company_code=%s AND status='quarantined'
        LIMIT 1
        """,
        (quarantine_id, company),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "quarantine_not_found"}
    q = dict(row)
    emp_key = q.get("employee_key")
    if require_employee_exists and emp_key:
        cur.execute(
            "SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s LIMIT 1",
            (company, emp_key),
        )
        if not cur.fetchone():
            return {"ok": False, "error": "employee_still_missing", "employee_key": emp_key}
    cur.execute(
        """
        UPDATE shift_assignments
        SET status='scheduled', updated_at=now(), row_version=COALESCE(row_version,1)+1
        WHERE shift_id=%s AND company_code=%s
        RETURNING *
        """,
        (q.get("shift_id"), company),
    )
    restored = cur.fetchone()
    if not restored:
        return {"ok": False, "error": "shift_not_found"}
    cur.execute(
        """
        UPDATE shift_orphan_quarantine
        SET status='restored', restored_at=now(), restored_by_phone=%s
        WHERE quarantine_id=%s
        RETURNING *
        """,
        (digits(actor_phone), quarantine_id),
    )
    return {"ok": True, "quarantine": dict(cur.fetchone()), "shift": dict(restored)}


def list_orphan_scheduled_shifts(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT s.*
        FROM shift_assignments s
        LEFT JOIN employees e
          ON e.company_code=s.company_code AND e.employee_key=s.employee_key
        WHERE s.company_code=%s AND s.status='scheduled' AND e.employee_key IS NULL
        ORDER BY s.shift_date, s.start_time
        """,
        (company,),
    )
    return [dict(r) for r in cur.fetchall()]


def honesty_payload(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    s = settings or {}
    return {
        "shifts_wave1_version": SHIFTS_WAVE1_VERSION,
        "allow_overnight": bool(s.get("allow_overnight", True)),
        "leave_conflict_mode": s.get("leave_conflict_mode") or LEAVE_CONFLICT_REQUIRE_ACK,
        "rest_weekdays": s.get("rest_weekdays") or list(DEFAULT_REST_WEEKDAYS),
        "payroll_money": False,
        "leave_balances_mutated": False,
        "note": "Shifts records scheduled hours only; Attendance owns worked time; Payroll owns money.",
    }
