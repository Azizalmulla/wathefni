"""Shifts Wave 1 — authority, safety & overnight foundation (local/staging).

L0 assignment remains canonical. Does NOT build templates/recurring/publish/open shifts.
Does NOT calculate Payroll money. Does NOT mutate Leave balances.

Overnight contract matches Attendance `shift_window`: end_time <= start_time ⇒ ends next day.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

SHIFTS_WAVE1_VERSION = "1.1.0"
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

BEYOND_END_BLOCK = "block"
BEYOND_END_REQUIRE_ACK = "require_ack"
BEYOND_END_CANCEL = "cancel"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shift_authority_settings (
  company_code text PRIMARY KEY,
  allow_overnight boolean NOT NULL DEFAULT true,
  rest_weekdays integer[] NOT NULL DEFAULT ARRAY[4],
  leave_conflict_mode text NOT NULL DEFAULT 'require_ack',
  block_terminated boolean NOT NULL DEFAULT true,
  block_suspended boolean NOT NULL DEFAULT true,
  block_future_start boolean NOT NULL DEFAULT true,
  block_notice_period boolean NOT NULL DEFAULT false,
  garden_leave_during_notice boolean NOT NULL DEFAULT false,
  beyond_end_mode text NOT NULL DEFAULT 'require_ack',
  synthetic_only boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_leave_conflict_mode_chk
    CHECK (leave_conflict_mode IN ('block','require_ack','cancel_shift')),
  CONSTRAINT shift_beyond_end_mode_chk
    CHECK (beyond_end_mode IN ('block','require_ack','cancel'))
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

CREATE TABLE IF NOT EXISTS shift_lifecycle_flags (
  flag_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  employee_key text,
  flag_type text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  acknowledged_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  CONSTRAINT shift_lifecycle_flag_type_chk
    CHECK (flag_type IN ('beyond_employment_end','orphan_employee_key')),
  CONSTRAINT shift_lifecycle_flag_status_chk
    CHECK (status IN ('open','acknowledged','cancelled','cleared'))
);
CREATE INDEX IF NOT EXISTS idx_shift_lifecycle_flags_company_status
  ON shift_lifecycle_flags(company_code, status, flag_type);

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

-- Wave 1A additive columns on settings (idempotent for already-migrated tenants)
ALTER TABLE shift_authority_settings
  ADD COLUMN IF NOT EXISTS garden_leave_during_notice boolean NOT NULL DEFAULT false;
ALTER TABLE shift_authority_settings
  ADD COLUMN IF NOT EXISTS beyond_end_mode text NOT NULL DEFAULT 'require_ack';
ALTER TABLE shift_authority_settings
  ALTER COLUMN block_notice_period SET DEFAULT false;
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
    beyond = str(d.get("beyond_end_mode") or BEYOND_END_REQUIRE_ACK).strip().lower()
    if beyond not in {BEYOND_END_BLOCK, BEYOND_END_REQUIRE_ACK, BEYOND_END_CANCEL}:
        beyond = BEYOND_END_REQUIRE_ACK
    # Wave 1A: notice is not blanket-blocked. Default false unless garden leave.
    notice_blanket = bool(d.get("block_notice_period", False))
    garden = bool(d.get("garden_leave_during_notice", False))
    garden_env = os.environ.get("WATHEFNI_SHIFTS_GARDEN_LEAVE")
    if garden_env is not None and str(garden_env).strip() != "":
        garden = str(garden_env).strip().lower() in _ON
    return {
        "company_code": company,
        "allow_overnight": allow_overnight,
        "rest_weekdays": [int(x) for x in rest],
        "leave_conflict_mode": mode,
        "block_terminated": bool(d.get("block_terminated", True)),
        "block_suspended": bool(d.get("block_suspended", True)),
        "block_future_start": bool(d.get("block_future_start", True)),
        "block_notice_period": notice_blanket,
        "garden_leave_during_notice": garden,
        "beyond_end_mode": beyond,
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


def _as_date(value: Any) -> date | None:
    return parse_date(value)


def _day_start(d: date, tz: timezone = KUWAIT_TZ) -> datetime:
    return datetime.combine(d, time.min, tzinfo=tz)


def _day_end_exclusive(d: date, tz: timezone = KUWAIT_TZ) -> datetime:
    """Exclusive end of calendar day d (start of next day)."""
    return datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz)


def load_employment_lifecycle_facts(
    cur: Any,
    *,
    company_code: str,
    employee: dict[str, Any] | None,
) -> dict[str, Any]:
    """Load start/end/suspension/notice facts for interval-aware shift gates."""
    company = (company_code or "").upper()
    emp = employee or {}
    key = str(emp.get("employee_key") or "")
    facts: dict[str, Any] = {
        "employee_key": key,
        "lifecycle_state": None,
        "hub_status": str(emp.get("employment_status") or emp.get("status") or "").strip().lower(),
        "start_date": None,
        "end_date": None,
        "last_working_day": None,
        "termination_effective_on": None,
        "notice_starts_on": None,
        "suspended_on": None,
        "suspension_ends_on": None,
        "garden_leave": False,
    }
    for field in ("start_date", "hire_date", "hired_at"):
        parsed = _as_date(emp.get(field))
        if parsed:
            facts["start_date"] = parsed
            break
    for field in ("end_date", "termination_date", "left_on"):
        parsed = _as_date(emp.get(field))
        if parsed:
            facts["end_date"] = parsed
            break

    if key and company:
        try:
            cur.execute(
                """
                SELECT e.lifecycle_state, e.start_date, e.end_date, e.last_working_day,
                       e.termination_effective_on, e.notice_starts_on, e.suspended_on,
                       e.suspension_reason
                FROM employee_employments e
                LEFT JOIN employee_key_authority_map m
                  ON m.company_code=e.company_code AND m.employment_id=e.employment_id AND m.mapping_status='active'
                WHERE e.company_code=%s
                  AND (e.legacy_employee_key=%s OR m.employee_key=%s)
                ORDER BY e.updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (company, key, key),
            )
            row = cur.fetchone()
            if row:
                er = dict(row)
                facts["lifecycle_state"] = str(er.get("lifecycle_state") or "").strip().lower() or None
                facts["start_date"] = _as_date(er.get("start_date")) or facts["start_date"]
                facts["end_date"] = _as_date(er.get("end_date")) or facts["end_date"]
                facts["last_working_day"] = _as_date(er.get("last_working_day"))
                facts["termination_effective_on"] = _as_date(er.get("termination_effective_on"))
                facts["notice_starts_on"] = _as_date(er.get("notice_starts_on"))
                facts["suspended_on"] = _as_date(er.get("suspended_on"))
                reason = str(er.get("suspension_reason") or "").lower()
                if "garden" in reason:
                    facts["garden_leave"] = True
        except Exception:
            pass
    return facts


def effective_employment_end(facts: dict[str, Any]) -> date | None:
    """Last calendar day the employee may be assigned (inclusive)."""
    for key in ("last_working_day", "termination_effective_on", "end_date"):
        d = _as_date(facts.get(key))
        if d:
            return d
    return None


def effective_employment_start(facts: dict[str, Any]) -> date | None:
    return _as_date(facts.get("start_date"))


def shift_interval_beyond_employment_end(
    shift_start: datetime,
    shift_end: datetime,
    end_date: date,
) -> bool:
    """True when any part of [shift_start, shift_end) is after end_date (exclusive day end)."""
    return shift_end > _day_end_exclusive(end_date) or shift_start >= _day_end_exclusive(end_date)


def evaluate_shift_lifecycle(
    *,
    facts: dict[str, Any],
    shift_start: datetime,
    shift_end: datetime,
    settings: dict[str, Any],
    operation: str = "create",
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Interval-aware lifecycle gate. Returns error dict or None if allowed.

    Wave 1A semantics:
      - future_start: block only when interval starts before employment start
      - notice_period: allow through effective end unless garden leave / blanket policy
      - suspended: block only when interval overlaps suspension window
      - terminated/left: block intervals after effective employment end
    """
    op = str(operation or "create")
    action = action or {}
    ack_beyond = bool(
        action.get("ack_beyond_employment_end")
        or action.get("allow_beyond_employment_end")
        or action.get("acknowledge_beyond_end")
    )
    state = str(facts.get("lifecycle_state") or "").strip().lower()
    hub = str(facts.get("hub_status") or "").strip().lower()
    start_d = effective_employment_start(facts)
    end_d = effective_employment_end(facts)

    # --- Before employment start ---
    if settings.get("block_future_start", True) and start_d:
        if shift_start < _day_start(start_d):
            return {
                "ok": False,
                "error": "shift_lifecycle_blocked",
                "lifecycle": "future_start",
                "operation": op,
                "employment_start": start_d.isoformat(),
                "shift_start": shift_start.isoformat(),
                "message": "Shifts cannot start before the employee effective start date.",
            }

    # --- Suspension overlap only ---
    if settings.get("block_suspended", True):
        suspended_on = _as_date(facts.get("suspended_on"))
        is_suspended = state == "suspended" or hub == "suspended" or bool(suspended_on and state != "active")
        if is_suspended and suspended_on:
            sus_start = _day_start(suspended_on)
            sus_end_d = _as_date(facts.get("suspension_ends_on"))
            sus_end = _day_end_exclusive(sus_end_d) if sus_end_d else datetime.max.replace(tzinfo=KUWAIT_TZ)
            if intervals_overlap(shift_start, shift_end, sus_start, sus_end):
                return {
                    "ok": False,
                    "error": "shift_lifecycle_blocked",
                    "lifecycle": "suspended",
                    "operation": op,
                    "suspension_start": suspended_on.isoformat(),
                    "suspension_end": sus_end_d.isoformat() if sus_end_d else None,
                    "message": "Shifts cannot overlap the employee's suspension period.",
                }
        elif is_suspended and not suspended_on and state == "suspended":
            # Suspended without dated window — fail closed for the whole open period.
            return {
                "ok": False,
                "error": "shift_lifecycle_blocked",
                "lifecycle": "suspended",
                "operation": op,
                "message": "Shifts are not allowed while the employee is suspended.",
            }

    # --- Garden leave / optional blanket notice block ---
    in_notice = state in {"notice_period", "notice"} or bool(facts.get("notice_starts_on"))
    garden = bool(settings.get("garden_leave_during_notice")) or bool(facts.get("garden_leave"))
    if in_notice and (garden or settings.get("block_notice_period", False)):
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": "notice_period",
            "operation": op,
            "garden_leave": True if garden else False,
            "message": (
                "Shifts are not allowed during garden leave."
                if garden
                else "Shifts are blocked during notice period by company policy."
            ),
        }

    # --- After employment end (terminated / left / notice past last day) ---
    terminatedish = state in {"terminated", "left"} or hub in {"terminated", "left"}
    if terminatedish and not end_d:
        # Fail closed when terminated/left without an effective end date.
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": "terminated",
            "operation": op,
            "message": "Shifts are not allowed for terminated employees without an effective end date on file.",
        }
    if end_d and shift_interval_beyond_employment_end(shift_start, shift_end, end_d):
        beyond_mode = str(settings.get("beyond_end_mode") or BEYOND_END_REQUIRE_ACK).lower()
        # New/rescheduled assignments: never schedule work past employment end unless
        # an explicit ack is allowed for reschedule-only require_ack mode (rare).
        if op in {"create", "reschedule"}:
            if op == "create" or beyond_mode == BEYOND_END_BLOCK or not ack_beyond:
                return {
                    "ok": False,
                    "error": "shift_lifecycle_blocked",
                    "lifecycle": "beyond_employment_end",
                    "operation": op,
                    "employment_end": end_d.isoformat(),
                    "shift_start": shift_start.isoformat(),
                    "shift_end": shift_end.isoformat(),
                    "needs_confirmation": beyond_mode == BEYOND_END_REQUIRE_ACK and op == "reschedule",
                    "beyond_end_mode": beyond_mode,
                    "message": "Shifts cannot extend past the employee effective end date.",
                }
        if op == "flag_existing":
            if beyond_mode == BEYOND_END_BLOCK:
                return {
                    "ok": False,
                    "error": "shift_beyond_employment_end",
                    "lifecycle": "beyond_employment_end",
                    "needs_confirmation": False,
                    "beyond_end_mode": beyond_mode,
                    "employment_end": end_d.isoformat(),
                    "message": "Existing shift extends past employment end and must be cancelled.",
                }
            if beyond_mode == BEYOND_END_REQUIRE_ACK and not ack_beyond:
                return {
                    "ok": False,
                    "error": "shift_beyond_employment_end_ack_required",
                    "lifecycle": "beyond_employment_end",
                    "needs_confirmation": True,
                    "beyond_end_mode": beyond_mode,
                    "employment_end": end_d.isoformat(),
                    "message": "Existing shift extends past employment end. Acknowledge or cancel it — never silent-delete.",
                }
    return None


def lifecycle_gate_for_shifts(
    *,
    label: str | None = None,
    settings: dict[str, Any],
    operation: str = "create",
    facts: dict[str, Any] | None = None,
    shift_start: datetime | None = None,
    shift_end: datetime | None = None,
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Wave 1A: prefer interval+facts. Label-only path retained for narrow unit probes."""
    if facts is not None and shift_start is not None and shift_end is not None:
        return evaluate_shift_lifecycle(
            facts=facts,
            shift_start=shift_start,
            shift_end=shift_end,
            settings=settings,
            operation=operation,
            action=action,
        )
    # Legacy label probes — notice no longer blanket-blocks by default.
    lab = str(label or "unknown")
    op = str(operation or "create")
    if lab in {"terminated", "left"} and settings.get("block_terminated", True):
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Shifts are not allowed after employment has ended.",
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
            "message": "Shifts cannot start before the employee effective start date.",
        }
    if lab == "notice_period" and (
        settings.get("block_notice_period", False) or settings.get("garden_leave_during_notice", False)
    ):
        return {
            "ok": False,
            "error": "shift_lifecycle_blocked",
            "lifecycle": lab,
            "operation": op,
            "message": "Shifts are blocked during notice under garden-leave / company policy.",
        }
    return None


def flag_beyond_employment_end_shift(
    cur: Any,
    *,
    company_code: str,
    shift: dict[str, Any],
    facts: dict[str, Any],
    actor_phone: str | None,
) -> dict[str, Any]:
    """Record an audited flag for an existing scheduled shift past employment end. Never deletes."""
    import json

    company = (company_code or "").upper()
    ensure_shifts_authority_wave1_schema(cur)
    end_d = effective_employment_end(facts)
    cur.execute(
        """
        INSERT INTO shift_lifecycle_flags (
          company_code, shift_id, employee_key, flag_type, status, details, created_by_phone
        ) VALUES (%s,%s,%s,'beyond_employment_end','open',%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            shift.get("shift_id"),
            shift.get("employee_key"),
            json.dumps(
                {
                    "employment_end": end_d.isoformat() if end_d else None,
                    "shift_date": str(shift.get("shift_date")),
                    "start_time": str(shift.get("start_time")),
                    "end_time": str(shift.get("end_time")),
                    "ends_next_day": bool(shift.get("ends_next_day")),
                    "policy": "audited_flag_never_silent_delete",
                },
                default=str,
            ),
            digits(actor_phone),
        ),
    )
    return {"ok": True, "flag": dict(cur.fetchone())}


def acknowledge_or_cancel_beyond_end(
    cur: Any,
    *,
    company_code: str,
    shift_id: str,
    actor_phone: str | None,
    mode: str,
    record_event: Any | None = None,
) -> dict[str, Any]:
    """Handle flagged beyond-end shifts via acknowledge or soft-cancel — never hard delete."""
    company = (company_code or "").upper()
    ensure_shifts_authority_wave1_schema(cur)
    m = str(mode or "").lower()
    cur.execute(
        "SELECT * FROM shift_assignments WHERE shift_id=%s AND company_code=%s LIMIT 1",
        (shift_id, company),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "shift_not_found"}
    shift = dict(row)
    if m == "cancel":
        cur.execute(
            """
            UPDATE shift_assignments
            SET status='cancelled', updated_at=now(), row_version=COALESCE(row_version,1)+1
            WHERE shift_id=%s AND company_code=%s AND status='scheduled'
            RETURNING *
            """,
            (shift_id, company),
        )
        cancelled = cur.fetchone()
        if cancelled and record_event:
            record_event(
                cur,
                shift=dict(cancelled),
                company_code=company,
                event_type="cancelled_beyond_employment_end",
                payload={"shift": dict(cancelled), "reason": "beyond_employment_end"},
                created_by_phone=actor_phone,
            )
        cur.execute(
            """
            UPDATE shift_lifecycle_flags
            SET status='cancelled', resolved_at=now(), acknowledged_by_phone=%s
            WHERE company_code=%s AND shift_id=%s AND status='open' AND flag_type='beyond_employment_end'
            """,
            (digits(actor_phone), company, shift_id),
        )
        return {"ok": True, "action": "cancelled", "shift": dict(cancelled) if cancelled else shift}
    if m in {"ack", "acknowledge"}:
        cur.execute(
            """
            UPDATE shift_lifecycle_flags
            SET status='acknowledged', resolved_at=now(), acknowledged_by_phone=%s
            WHERE company_code=%s AND shift_id=%s AND status='open' AND flag_type='beyond_employment_end'
            RETURNING *
            """,
            (digits(actor_phone), company, shift_id),
        )
        flags = [dict(r) for r in cur.fetchall()]
        if record_event:
            record_event(
                cur,
                shift=shift,
                company_code=company,
                event_type="beyond_employment_end_acknowledged",
                payload={"shift": shift, "flags": flags},
                created_by_phone=actor_phone,
            )
        return {"ok": True, "action": "acknowledged", "flags": flags, "shift": shift}
    return {"ok": False, "error": "invalid_beyond_end_action"}


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
    record_event: Any | None = None,
) -> dict[str, Any]:
    """Cancel scheduled orphan and record reversible quarantine snapshot + audit."""
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
    snapshot = {
        k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
        for k, v in dict(shift).items()
    }
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
            json.dumps(snapshot, default=str),
            reason,
            digits(actor_phone),
        ),
    )
    q = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO shift_lifecycle_flags (
          company_code, shift_id, employee_key, flag_type, status, details, created_by_phone
        ) VALUES (%s,%s,%s,'orphan_employee_key','open',%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            shift_id,
            shift.get("employee_key"),
            json.dumps({"quarantine_id": str(q.get("quarantine_id")), "reason": reason}, default=str),
            digits(actor_phone),
        ),
    )
    flag = dict(cur.fetchone())
    cancelled = dict(updated) if updated else dict(shift)
    if record_event:
        record_event(
            cur,
            shift=cancelled,
            company_code=company,
            event_type="orphan_quarantined",
            payload={"quarantine": q, "flag": flag, "snapshot": snapshot},
            created_by_phone=actor_phone,
        )
    return {"ok": True, "quarantine": q, "flag": flag, "shift": cancelled}


def restore_quarantined_shift(
    cur: Any,
    *,
    company_code: str,
    quarantine_id: str,
    actor_phone: str | None,
    require_employee_exists: bool = True,
    record_event: Any | None = None,
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
    q2 = dict(cur.fetchone())
    cur.execute(
        """
        UPDATE shift_lifecycle_flags
        SET status='cleared', resolved_at=now(), acknowledged_by_phone=%s
        WHERE company_code=%s AND shift_id=%s AND flag_type='orphan_employee_key' AND status='open'
        """,
        (digits(actor_phone), company, q.get("shift_id")),
    )
    shift = dict(restored)
    if record_event:
        record_event(
            cur,
            shift=shift,
            company_code=company,
            event_type="orphan_restored",
            payload={"quarantine": q2},
            created_by_phone=actor_phone,
        )
    return {"ok": True, "quarantine": q2, "shift": shift}


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


def evaluate_assignment_lifecycle(
    cur: Any,
    *,
    company_code: str,
    employee: dict[str, Any],
    settings: dict[str, Any],
    shift_date: date,
    start_time: Any,
    end_time: Any,
    ends_next_day: bool = False,
    operation: str = "create",
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Convenience: load facts + evaluate overnight-aware interval."""
    win = shift_window(shift_date, start_time, end_time, ends_next_day=ends_next_day)
    if not win:
        return {"ok": False, "error": "invalid_shift_time_range", "operation": operation}
    facts = load_employment_lifecycle_facts(cur, company_code=company_code, employee=employee)
    return evaluate_shift_lifecycle(
        facts=facts,
        shift_start=win[0],
        shift_end=win[1],
        settings=settings,
        operation=operation,
        action=action,
    )


def honesty_payload(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    s = settings or {}
    return {
        "shifts_wave1_version": SHIFTS_WAVE1_VERSION,
        "allow_overnight": bool(s.get("allow_overnight", True)),
        "leave_conflict_mode": s.get("leave_conflict_mode") or LEAVE_CONFLICT_REQUIRE_ACK,
        "beyond_end_mode": s.get("beyond_end_mode") or BEYOND_END_REQUIRE_ACK,
        "garden_leave_during_notice": bool(s.get("garden_leave_during_notice", False)),
        "rest_weekdays": s.get("rest_weekdays") or list(DEFAULT_REST_WEEKDAYS),
        "payroll_money": False,
        "leave_balances_mutated": False,
        "note": "Shifts records scheduled hours only; Attendance owns worked time; Payroll owns money.",
    }
