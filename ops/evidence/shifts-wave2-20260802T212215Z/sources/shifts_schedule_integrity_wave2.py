"""Shifts Wave 2 — schedule integrity (local/staging).

L0 `shift_assignments` remains current-row authority. Adds:
  - immutable effective-dated assignment versions
  - availability decide + conflict gates
  - swap reassignment lineage
  - Attendance matching (overnight/split, fail-closed on ambiguous)
  - durable reminder queue (idempotent, retry, terminal visibility)
  - seasonal policy foundations (Ramadan / midday restriction) — warn by default
  - lifecycle + leave reconciliation flags (no silent cancel)

Does NOT: templates, recurring, rotations, publish, open shifts, PAM, Payroll money,
Leave balance mutation, UI redesign, production deploy.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

SHIFTS_WAVE2_VERSION = "2.0.0"
KUWAIT_TZ = timezone(timedelta(hours=3), name="Asia/Kuwait")
_ON = {"1", "true", "yes", "on"}

REASON_CODES = (
    "created",
    "rescheduled",
    "cancelled",
    "cancelled_for_leave",
    "cancelled_for_replacement",
    "reassigned_swap",
    "reassigned_manual",
    "availability_ack",
    "reconcile_ack",
    "reconcile_cancel",
    "other",
)

AVAIL_WARN = "warn"
AVAIL_REQUIRE_ACK = "require_ack"
AVAIL_BLOCK = "block"

SEASONAL_WARN = "warn"
SEASONAL_BLOCK = "block"

REMINDER_PENDING = "pending"
REMINDER_CLAIMED = "claimed"
REMINDER_SENT = "sent"
REMINDER_FAILED = "failed"
REMINDER_TERMINAL = "terminal_failed"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS shift_integrity_settings (
  company_code text PRIMARY KEY,
  availability_conflict_mode text NOT NULL DEFAULT 'require_ack',
  seasonal_default_mode text NOT NULL DEFAULT 'warn',
  reminder_max_attempts integer NOT NULL DEFAULT 5,
  reminder_backoff_seconds integer NOT NULL DEFAULT 300,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_avail_conflict_mode_chk
    CHECK (availability_conflict_mode IN ('warn','require_ack','block')),
  CONSTRAINT shift_seasonal_default_mode_chk
    CHECK (seasonal_default_mode IN ('warn','block'))
);

CREATE TABLE IF NOT EXISTS shift_assignment_versions (
  version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  version_no integer NOT NULL,
  is_current boolean NOT NULL DEFAULT false,
  effective_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  reason_code text NOT NULL DEFAULT 'other',
  reason_note text,
  actor_phone text,
  employee_key text,
  previous_employee_key text,
  shift_date date,
  start_time time,
  end_time time,
  ends_next_day boolean NOT NULL DEFAULT false,
  status text,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  lineage jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_version_reason_chk CHECK (reason_code <> ''),
  CONSTRAINT shift_version_uniq UNIQUE (company_code, shift_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_shift_versions_shift
  ON shift_assignment_versions(company_code, shift_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_shift_versions_current
  ON shift_assignment_versions(company_code, shift_id) WHERE is_current;

CREATE TABLE IF NOT EXISTS shift_reminder_queue (
  reminder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  employee_key text,
  planned_send_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  next_attempt_at timestamptz,
  last_error text,
  idempotency_key text NOT NULL,
  delivery_ref text,
  claimed_at timestamptz,
  sent_at timestamptz,
  terminal_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_reminder_status_chk
    CHECK (status IN ('pending','claimed','sent','failed','terminal_failed','cancelled')),
  CONSTRAINT shift_reminder_idem_uniq UNIQUE (company_code, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_shift_reminder_due
  ON shift_reminder_queue(status, next_attempt_at, planned_send_at)
  WHERE status IN ('pending','failed');
CREATE INDEX IF NOT EXISTS idx_shift_reminder_shift
  ON shift_reminder_queue(company_code, shift_id);

CREATE TABLE IF NOT EXISTS shift_seasonal_policies (
  policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  policy_type text NOT NULL,
  name text NOT NULL,
  site_key text,
  branch_key text,
  effective_start date NOT NULL,
  effective_end date NOT NULL,
  window_start time,
  window_end time,
  enforcement_mode text NOT NULL DEFAULT 'warn',
  enabled boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_seasonal_type_chk
    CHECK (policy_type IN ('ramadan','midday_restriction','custom')),
  CONSTRAINT shift_seasonal_mode_chk
    CHECK (enforcement_mode IN ('warn','block'))
);
CREATE INDEX IF NOT EXISTS idx_shift_seasonal_company_dates
  ON shift_seasonal_policies(company_code, effective_start, effective_end)
  WHERE enabled;

CREATE TABLE IF NOT EXISTS shift_reconciliation_flags (
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
  CONSTRAINT shift_recon_type_chk
    CHECK (flag_type IN ('lifecycle_fact_change','approved_leave_conflict','availability_conflict','seasonal_conflict')),
  CONSTRAINT shift_recon_status_chk
    CHECK (status IN ('open','acknowledged','cancelled','cleared'))
);
CREATE INDEX IF NOT EXISTS idx_shift_recon_open
  ON shift_reconciliation_flags(company_code, status, flag_type);

ALTER TABLE shift_assignments
  ADD COLUMN IF NOT EXISTS current_version_no integer NOT NULL DEFAULT 1;
ALTER TABLE shift_assignments
  ADD COLUMN IF NOT EXISTS schedule_reason_code text;
ALTER TABLE shift_assignments
  ADD COLUMN IF NOT EXISTS lineage_json jsonb NOT NULL DEFAULT '{}'::jsonb;
"""


def shifts_wave2_enabled() -> bool:
    raw = os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_WAVE2")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON


def ensure_shifts_integrity_wave2_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def seed_shift_integrity_settings(cur: Any, company_code: str) -> None:
    company = (company_code or "").upper()
    if not company:
        return
    cur.execute(
        """
        INSERT INTO shift_integrity_settings (company_code)
        VALUES (%s) ON CONFLICT (company_code) DO NOTHING
        """,
        (company,),
    )


def get_integrity_settings(cur: Any, company_code: str) -> dict[str, Any]:
    ensure_shifts_integrity_wave2_schema(cur)
    seed_shift_integrity_settings(cur, company_code)
    cur.execute("SELECT * FROM shift_integrity_settings WHERE company_code=%s", ((company_code or "").upper(),))
    row = cur.fetchone()
    d = dict(row) if row else {}
    return {
        "availability_conflict_mode": str(d.get("availability_conflict_mode") or AVAIL_REQUIRE_ACK),
        "seasonal_default_mode": str(d.get("seasonal_default_mode") or SEASONAL_WARN),
        "reminder_max_attempts": int(d.get("reminder_max_attempts") or 5),
        "reminder_backoff_seconds": int(d.get("reminder_backoff_seconds") or 300),
    }


def set_integrity_settings(cur: Any, company_code: str, **fields: Any) -> dict[str, Any]:
    ensure_shifts_integrity_wave2_schema(cur)
    seed_shift_integrity_settings(cur, company_code)
    allowed = {
        "availability_conflict_mode",
        "seasonal_default_mode",
        "reminder_max_attempts",
        "reminder_backoff_seconds",
    }
    sets = []
    params: list[Any] = []
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        sets.append(f"{k}=%s")
        params.append(v)
    if sets:
        params.append((company_code or "").upper())
        cur.execute(
            f"UPDATE shift_integrity_settings SET {', '.join(sets)}, updated_at=now() WHERE company_code=%s",
            params,
        )
    return get_integrity_settings(cur, company_code)


def honesty_payload() -> dict[str, Any]:
    return {
        "shifts_wave2_version": SHIFTS_WAVE2_VERSION,
        "payroll_money": False,
        "leave_balances_mutated": False,
        "owns_planned_intervals": True,
        "attendance_owns_worked_time": True,
        "leave_owns_leave_decisions": True,
    }


def _snapshot(shift: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in dict(shift or {}).items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _as_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.timetz().replace(tzinfo=None) if value.tzinfo else value.time()
    text = str(value)
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text[:8], fmt).time()
        except Exception:
            continue
    return None


def normalize_reason_code(raw: Any, default: str = "other") -> str:
    code = str(raw or default).strip().lower() or default
    return code if code in REASON_CODES else default


def record_assignment_version(
    cur: Any,
    *,
    company_code: str,
    shift: dict[str, Any],
    reason_code: str,
    actor_phone: str | None = None,
    reason_note: str | None = None,
    previous_employee_key: str | None = None,
    lineage: dict[str, Any] | None = None,
    supersede_current: bool = True,
) -> dict[str, Any]:
    """Append immutable version; mark as current-row authority pointer."""
    ensure_shifts_integrity_wave2_schema(cur)
    company = (company_code or "").upper()
    shift_id = shift.get("shift_id")
    if supersede_current:
        cur.execute(
            """
            UPDATE shift_assignment_versions
            SET is_current=false, superseded_at=COALESCE(superseded_at, now())
            WHERE company_code=%s AND shift_id=%s AND is_current=true
            """,
            (company, shift_id),
        )
    cur.execute(
        """
        SELECT COALESCE(MAX(version_no), 0) AS n
        FROM shift_assignment_versions WHERE company_code=%s AND shift_id=%s
        """,
        (company, shift_id),
    )
    next_no = int(dict(cur.fetchone()).get("n") or 0) + 1
    code = normalize_reason_code(reason_code)
    cur.execute(
        """
        INSERT INTO shift_assignment_versions (
          company_code, shift_id, version_no, is_current, reason_code, reason_note,
          actor_phone, employee_key, previous_employee_key, shift_date, start_time, end_time,
          ends_next_day, status, snapshot, lineage
        ) VALUES (%s,%s,%s,true,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            shift_id,
            next_no,
            code,
            reason_note,
            "".join(ch for ch in str(actor_phone or "") if ch.isdigit()) or None,
            shift.get("employee_key"),
            previous_employee_key,
            shift.get("shift_date"),
            shift.get("start_time"),
            shift.get("end_time"),
            bool(shift.get("ends_next_day")),
            shift.get("status"),
            __import__("json").dumps(_snapshot(shift)),
            __import__("json").dumps(lineage or {}),
        ),
    )
    ver = dict(cur.fetchone())
    cur.execute(
        """
        UPDATE shift_assignments
        SET current_version_no=%s, schedule_reason_code=%s,
            lineage_json=COALESCE(lineage_json,'{}'::jsonb) || %s::jsonb,
            updated_at=now()
        WHERE shift_id=%s AND company_code=%s
        """,
        (
            next_no,
            code,
            __import__("json").dumps(
                {
                    "current_version_no": next_no,
                    "last_reason_code": code,
                    **(lineage or {}),
                }
            ),
            shift_id,
            company,
        ),
    )
    return ver


def list_assignment_versions(cur: Any, *, company_code: str, shift_id: str) -> list[dict[str, Any]]:
    ensure_shifts_integrity_wave2_schema(cur)
    cur.execute(
        """
        SELECT * FROM shift_assignment_versions
        WHERE company_code=%s AND shift_id=%s
        ORDER BY version_no
        """,
        ((company_code or "").upper(), shift_id),
    )
    return [dict(r) for r in cur.fetchall()]


# --- Availability -----------------------------------------------------------------

def decide_availability(
    cur: Any,
    *,
    company_code: str,
    availability_id: str,
    decision: str,
    actor_phone: str | None,
    decision_note: str | None = None,
    record_event: Any | None = None,
) -> dict[str, Any]:
    ensure_shifts_integrity_wave2_schema(cur)
    company = (company_code or "").upper()
    status = "approved" if str(decision).lower() in {"approve", "approved"} else "rejected"
    cur.execute(
        """
        SELECT * FROM employee_availability_requests
        WHERE company_code=%s AND availability_id=%s
        LIMIT 1
        """,
        (company, availability_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "availability_not_found"}
    avail = dict(row)
    if str(avail.get("status")) != "requested":
        if str(avail.get("status")) == status:
            return {"ok": True, "idempotent": True, "availability": avail}
        return {"ok": False, "error": "stale_availability_decision", "availability": avail}
    cur.execute(
        """
        UPDATE employee_availability_requests
        SET status=%s, decision_note=%s, decided_by_phone=%s, decided_at=now()
        WHERE company_code=%s AND availability_id=%s AND status='requested'
        RETURNING *
        """,
        (
            status,
            decision_note,
            "".join(ch for ch in str(actor_phone or "") if ch.isdigit()) or None,
            company,
            availability_id,
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_availability_decision"}
    avail = dict(updated)
    if record_event:
        record_event(
            cur,
            availability=avail,
            company_code=company,
            event_type=status,
            payload={"availability": avail, "decision_note": decision_note},
            created_by_phone=actor_phone,
        )
    return {"ok": True, "availability": avail}


def approved_unavailability_overlaps(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    shift_date: date,
    start_time: Any,
    end_time: Any,
    ends_next_day: bool = False,
) -> list[dict[str, Any]]:
    """Return approved unavailable windows overlapping the planned interval."""
    import shifts_authority_wave1 as sw1

    win = sw1.shift_window(shift_date, start_time, end_time)
    if not win:
        return []
    cur.execute(
        """
        SELECT * FROM employee_availability_requests
        WHERE company_code=%s
          AND employee_key=%s
          AND status='approved'
          AND availability_type='unavailable'
          AND start_date <= %s
          AND end_date >= %s
        ORDER BY start_date, start_time NULLS FIRST
        """,
        ((company_code or "").upper(), employee_key, win[1].date(), shift_date),
    )
    hits: list[dict[str, Any]] = []
    for row in cur.fetchall():
        av = dict(row)
        d0 = _as_date(av.get("start_date")) or shift_date
        d1 = _as_date(av.get("end_date")) or d0
        st = _as_time(av.get("start_time")) or time(0, 0)
        et = _as_time(av.get("end_time")) or time(23, 59, 59)
        # whole-day unavailable when times null-ish covered by defaults
        day = d0
        while day <= d1:
            a_win = sw1.shift_window(day, st.strftime("%H:%M"), et.strftime("%H:%M"))
            if a_win and sw1.intervals_overlap(win[0], win[1], a_win[0], a_win[1]):
                hits.append(av)
                break
            day += timedelta(days=1)
    return hits


def availability_conflict_denied(
    *,
    mode: str,
    conflicts: list[dict[str, Any]],
    action: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not conflicts:
        return None
    m = str(mode or AVAIL_REQUIRE_ACK).lower()
    ack = bool((action or {}).get("ack_availability_conflict") or (action or {}).get("allow_availability_conflicts"))
    if m == AVAIL_WARN:
        return None  # caller may attach warnings
    if m == AVAIL_BLOCK:
        return {
            "ok": False,
            "error": "shift_availability_conflict",
            "availability_conflict_mode": m,
            "conflicts": conflicts,
            "message": "This shift overlaps approved unavailability and is blocked.",
        }
    if m == AVAIL_REQUIRE_ACK and not ack:
        return {
            "ok": False,
            "error": "shift_availability_conflict_ack_required",
            "needs_confirmation": True,
            "availability_conflict_mode": m,
            "conflicts": conflicts,
            "message": "This shift overlaps approved unavailability. Acknowledge to continue.",
        }
    return None


# --- Attendance matching ----------------------------------------------------------

def match_shift_for_attendance(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    attendance_date: date,
    at_time: time | None = None,
    shift_id: str | None = None,
) -> dict[str, Any]:
    """Deterministic assignment match for Attendance. Ambiguous → fail closed.

    Overnight: interval may start prior calendar day.
    Split: exact time (if provided) must fall in exactly one window; else ambiguous.
    """
    import shifts_authority_wave1 as sw1

    company = (company_code or "").upper()
    if shift_id:
        cur.execute(
            """
            SELECT * FROM shift_assignments
            WHERE shift_id=%s AND company_code=%s AND employee_key=%s AND status='scheduled'
            LIMIT 1
            """,
            (shift_id, company, employee_key),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "shift_not_found", "matches": []}
        return {"ok": True, "shift": dict(row), "matches": [dict(row)]}

    # Candidates: same day + previous day (overnight spill)
    days = [attendance_date, attendance_date - timedelta(days=1)]
    cur.execute(
        """
        SELECT * FROM shift_assignments
        WHERE company_code=%s AND employee_key=%s AND status='scheduled'
          AND shift_date = ANY(%s)
        ORDER BY shift_date, start_time
        """,
        (company, employee_key, days),
    )
    rows = [dict(r) for r in cur.fetchall()]
    covering: list[dict[str, Any]] = []
    same_day: list[dict[str, Any]] = []
    point = datetime.combine(attendance_date, at_time or time(12, 0), tzinfo=KUWAIT_TZ)
    for row in rows:
        sd = _as_date(row.get("shift_date"))
        if not sd:
            continue
        win = sw1.shift_window(sd, row.get("start_time"), row.get("end_time"))
        if not win:
            continue
        if sd == attendance_date:
            same_day.append(row)
        if at_time is None:
            # date-level: include if window intersects attendance calendar day
            day_start = datetime.combine(attendance_date, time(0, 0), tzinfo=KUWAIT_TZ)
            day_end = day_start + timedelta(days=1)
            if sw1.intervals_overlap(win[0], win[1], day_start, day_end):
                covering.append(row)
        else:
            if win[0] <= point < win[1]:
                covering.append(row)

    if at_time is None:
        # Prefer same-day scheduled; fail closed if multiple same-day (split without time)
        if len(same_day) == 1:
            return {"ok": True, "shift": same_day[0], "matches": same_day}
        if len(same_day) > 1:
            return {
                "ok": False,
                "error": "ambiguous_shift_match",
                "matches": same_day,
                "message": "Multiple split shifts on this date; provide shift_id or punch time.",
            }
        if len(covering) == 1:
            return {"ok": True, "shift": covering[0], "matches": covering}
        if len(covering) > 1:
            return {"ok": False, "error": "ambiguous_shift_match", "matches": covering}
        return {"ok": False, "error": "shift_not_found", "matches": []}

    if len(covering) == 1:
        return {"ok": True, "shift": covering[0], "matches": covering}
    if len(covering) > 1:
        return {"ok": False, "error": "ambiguous_shift_match", "matches": covering}
    return {"ok": False, "error": "shift_not_found", "matches": []}


# --- Reminders --------------------------------------------------------------------

def reminder_idempotency_key(shift: dict[str, Any]) -> str:
    """Key includes planned window so reschedule creates a fresh reminder lane."""
    return "|".join(
        [
            str(shift.get("shift_id") or ""),
            str(shift.get("shift_date") or ""),
            str(shift.get("start_time") or ""),
            str(shift.get("end_time") or ""),
        ]
    )


def enqueue_shift_reminder(
    cur: Any,
    *,
    company_code: str,
    shift: dict[str, Any],
    hours_before: int = 2,
    settings: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    ensure_shifts_integrity_wave2_schema(cur)
    if str(shift.get("status")) != "scheduled":
        return None
    settings = settings or get_integrity_settings(cur, company_code)
    sd = _as_date(shift.get("shift_date"))
    st = _as_time(shift.get("start_time"))
    if not sd or not st:
        return None
    start_dt = datetime.combine(sd, st, tzinfo=KUWAIT_TZ)
    planned = start_dt - timedelta(hours=max(1, min(int(hours_before), 24)))
    key = reminder_idempotency_key(shift)
    cur.execute(
        """
        INSERT INTO shift_reminder_queue (
          company_code, shift_id, employee_key, planned_send_at, status,
          next_attempt_at, max_attempts, idempotency_key
        ) VALUES (%s,%s,%s,%s,'pending',%s,%s,%s)
        ON CONFLICT (company_code, idempotency_key) DO NOTHING
        RETURNING *
        """,
        (
            (company_code or "").upper(),
            shift.get("shift_id"),
            shift.get("employee_key"),
            planned,
            planned,
            int(settings.get("reminder_max_attempts") or 5),
            key,
        ),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def cancel_pending_reminders_for_shift(cur: Any, *, company_code: str, shift_id: str) -> int:
    ensure_shifts_integrity_wave2_schema(cur)
    cur.execute(
        """
        UPDATE shift_reminder_queue
        SET status='cancelled', updated_at=now()
        WHERE company_code=%s AND shift_id=%s AND status IN ('pending','failed')
        """,
        ((company_code or "").upper(), shift_id),
    )
    return cur.rowcount or 0


def claim_due_reminders(cur: Any, *, now: datetime | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_shifts_integrity_wave2_schema(cur)
    now = now or datetime.now(timezone.utc)
    cur.execute(
        """
        UPDATE shift_reminder_queue q
        SET status='claimed', claimed_at=now(), attempt_count=attempt_count+1, updated_at=now()
        WHERE reminder_id IN (
          SELECT reminder_id FROM shift_reminder_queue
          WHERE status IN ('pending','failed')
            AND COALESCE(next_attempt_at, planned_send_at) <= %s
            AND attempt_count < max_attempts
          ORDER BY planned_send_at
          LIMIT %s
          FOR UPDATE SKIP LOCKED
        )
        RETURNING *
        """,
        (now, max(1, min(limit, 200))),
    )
    return [dict(r) for r in cur.fetchall()]


def complete_reminder_send(
    cur: Any,
    *,
    reminder: dict[str, Any],
    ok: bool,
    error: str | None = None,
    delivery_ref: str | None = None,
    backoff_seconds: int = 300,
) -> dict[str, Any]:
    ensure_shifts_integrity_wave2_schema(cur)
    rid = reminder.get("reminder_id")
    if ok:
        cur.execute(
            """
            UPDATE shift_reminder_queue
            SET status='sent', sent_at=now(), delivery_ref=%s, last_error=NULL, updated_at=now()
            WHERE reminder_id=%s
            RETURNING *
            """,
            (delivery_ref, rid),
        )
        row = cur.fetchone()
        cur.execute(
            "UPDATE shift_assignments SET reminder_sent_at=now(), updated_at=now() WHERE shift_id=%s",
            (reminder.get("shift_id"),),
        )
        return dict(row) if row else {}
    attempts = int(reminder.get("attempt_count") or 1)
    max_a = int(reminder.get("max_attempts") or 5)
    if attempts >= max_a:
        cur.execute(
            """
            UPDATE shift_reminder_queue
            SET status='terminal_failed', terminal_at=now(), last_error=%s, updated_at=now()
            WHERE reminder_id=%s
            RETURNING *
            """,
            (error, rid),
        )
    else:
        cur.execute(
            """
            UPDATE shift_reminder_queue
            SET status='failed', last_error=%s,
                next_attempt_at=now() + (%s || ' seconds')::interval,
                updated_at=now()
            WHERE reminder_id=%s
            RETURNING *
            """,
            (error, str(int(backoff_seconds)), rid),
        )
    row = cur.fetchone()
    return dict(row) if row else {}


def list_terminal_reminder_failures(cur: Any, *, company_code: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_shifts_integrity_wave2_schema(cur)
    cur.execute(
        """
        SELECT * FROM shift_reminder_queue
        WHERE company_code=%s AND status='terminal_failed'
        ORDER BY terminal_at DESC NULLS LAST
        LIMIT %s
        """,
        ((company_code or "").upper(), max(1, min(limit, 200))),
    )
    return [dict(r) for r in cur.fetchall()]


# --- Seasonal policies ------------------------------------------------------------

def upsert_seasonal_policy(cur: Any, *, company_code: str, policy: dict[str, Any]) -> dict[str, Any]:
    ensure_shifts_integrity_wave2_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        INSERT INTO shift_seasonal_policies (
          company_code, policy_type, name, site_key, branch_key,
          effective_start, effective_end, window_start, window_end,
          enforcement_mode, enabled, metadata
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            str(policy.get("policy_type") or "custom"),
            str(policy.get("name") or "policy"),
            policy.get("site_key"),
            policy.get("branch_key"),
            policy.get("effective_start"),
            policy.get("effective_end"),
            policy.get("window_start"),
            policy.get("window_end"),
            str(policy.get("enforcement_mode") or SEASONAL_WARN),
            bool(policy.get("enabled", True)),
            __import__("json").dumps(policy.get("metadata") or {}),
        ),
    )
    return dict(cur.fetchone())


def evaluate_seasonal_policies(
    cur: Any,
    *,
    company_code: str,
    shift_date: date,
    start_time: Any,
    end_time: Any,
    site_key: str | None = None,
    branch_key: str | None = None,
    ends_next_day: bool = False,
) -> dict[str, Any]:
    """Return warnings and optional hard denial for seasonal profiles."""
    import shifts_authority_wave1 as sw1

    ensure_shifts_integrity_wave2_schema(cur)
    win = sw1.shift_window(shift_date, start_time, end_time)
    if not win:
        return {"warnings": [], "denied": None}
    cur.execute(
        """
        SELECT * FROM shift_seasonal_policies
        WHERE company_code=%s AND enabled=true
          AND effective_start <= %s AND effective_end >= %s
        ORDER BY policy_type, effective_start
        """,
        ((company_code or "").upper(), shift_date, shift_date),
    )
    warnings: list[dict[str, Any]] = []
    denied = None
    for row in cur.fetchall():
        pol = dict(row)
        # Site/branch scoped policies apply only when the assignment matches.
        if pol.get("site_key") and (not site_key or str(pol["site_key"]) != str(site_key)):
            continue
        if pol.get("branch_key") and (not branch_key or str(pol["branch_key"]) != str(branch_key)):
            continue
        ptype = str(pol.get("policy_type") or "")
        hit = False
        detail: dict[str, Any] = {"policy": pol}
        if ptype == "ramadan":
            # Profile active by effective dates; optional preferred window warn if outside
            hit = True
            detail["message"] = "Ramadan schedule profile is in effect for this date."
            ws, we = _as_time(pol.get("window_start")), _as_time(pol.get("window_end"))
            if ws and we:
                pref = sw1.shift_window(shift_date, ws.strftime("%H:%M"), we.strftime("%H:%M"))
                if pref and not (win[0] >= pref[0] and win[1] <= pref[1]):
                    detail["message"] = "Shift falls outside Ramadan preferred window."
        elif ptype == "midday_restriction":
            ws = _as_time(pol.get("window_start")) or time(11, 0)
            we = _as_time(pol.get("window_end")) or time(16, 0)
            ban = sw1.shift_window(shift_date, ws.strftime("%H:%M"), we.strftime("%H:%M"))
            if ban and sw1.intervals_overlap(win[0], win[1], ban[0], ban[1]):
                hit = True
                detail["message"] = "Shift overlaps outdoor/construction midday restriction window."
        else:
            hit = True
            detail["message"] = "Seasonal policy applies."
        if not hit:
            continue
        mode = str(pol.get("enforcement_mode") or SEASONAL_WARN)
        entry = {**detail, "enforcement_mode": mode, "policy_type": ptype}
        if mode == SEASONAL_BLOCK and denied is None:
            denied = {
                "ok": False,
                "error": "shift_seasonal_policy_blocked",
                "policy": pol,
                "message": detail.get("message"),
            }
        else:
            warnings.append(entry)
    return {"warnings": warnings, "denied": denied}


# --- Reconciliation ---------------------------------------------------------------

def open_reconciliation_flag(
    cur: Any,
    *,
    company_code: str,
    shift: dict[str, Any],
    flag_type: str,
    details: dict[str, Any] | None = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_integrity_wave2_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        SELECT flag_id FROM shift_reconciliation_flags
        WHERE company_code=%s AND shift_id=%s AND flag_type=%s AND status='open'
        LIMIT 1
        """,
        (company, shift.get("shift_id"), flag_type),
    )
    if cur.fetchone():
        cur.execute(
            """
            SELECT * FROM shift_reconciliation_flags
            WHERE company_code=%s AND shift_id=%s AND flag_type=%s AND status='open'
            LIMIT 1
            """,
            (company, shift.get("shift_id"), flag_type),
        )
        return {"ok": True, "idempotent": True, "flag": dict(cur.fetchone())}
    cur.execute(
        """
        INSERT INTO shift_reconciliation_flags (
          company_code, shift_id, employee_key, flag_type, status, details, created_by_phone
        ) VALUES (%s,%s,%s,%s,'open',%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            shift.get("shift_id"),
            shift.get("employee_key"),
            flag_type,
            __import__("json").dumps(details or {}),
            "".join(ch for ch in str(actor_phone or "") if ch.isdigit()) or None,
        ),
    )
    return {"ok": True, "flag": dict(cur.fetchone())}


def acknowledge_or_cancel_reconciliation(
    cur: Any,
    *,
    company_code: str,
    flag_id: str,
    action: str,
    actor_phone: str | None,
    record_event: Any | None = None,
) -> dict[str, Any]:
    """Audited ack or soft-cancel of conflicting shift — never silent delete."""
    ensure_shifts_integrity_wave2_schema(cur)
    company = (company_code or "").upper()
    act = str(action or "").lower()
    cur.execute(
        "SELECT * FROM shift_reconciliation_flags WHERE company_code=%s AND flag_id=%s",
        (company, flag_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "reconciliation_flag_not_found"}
    flag = dict(row)
    if act == "acknowledge":
        cur.execute(
            """
            UPDATE shift_reconciliation_flags
            SET status='acknowledged', acknowledged_by_phone=%s, resolved_at=now()
            WHERE flag_id=%s AND company_code=%s AND status='open'
            RETURNING *
            """,
            ("".join(ch for ch in str(actor_phone or "") if ch.isdigit()) or None, flag_id, company),
        )
        updated = cur.fetchone()
        return {"ok": bool(updated), "flag": dict(updated) if updated else flag}
    if act == "cancel":
        cur.execute(
            """
            UPDATE shift_assignments
            SET status='cancelled', updated_at=now(),
                row_version=COALESCE(row_version,1)+1,
                schedule_reason_code='reconcile_cancel'
            WHERE shift_id=%s AND company_code=%s AND status='scheduled'
            RETURNING *
            """,
            (flag.get("shift_id"), company),
        )
        shift = cur.fetchone()
        cur.execute(
            """
            UPDATE shift_reconciliation_flags
            SET status='cancelled', acknowledged_by_phone=%s, resolved_at=now()
            WHERE flag_id=%s AND company_code=%s
            RETURNING *
            """,
            ("".join(ch for ch in str(actor_phone or "") if ch.isdigit()) or None, flag_id, company),
        )
        updated = dict(cur.fetchone() or flag)
        if shift and record_event:
            record_event(
                cur,
                shift=dict(shift),
                company_code=company,
                event_type="cancelled",
                payload={"reason_code": "reconcile_cancel", "flag": updated},
                created_by_phone=actor_phone,
            )
            record_assignment_version(
                cur,
                company_code=company,
                shift=dict(shift),
                reason_code="reconcile_cancel",
                actor_phone=actor_phone,
            )
        return {"ok": True, "flag": updated, "shift": dict(shift) if shift else None}
    return {"ok": False, "error": "invalid_reconciliation_action"}


def reconcile_lifecycle_future_shifts(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Flag future scheduled shifts that violate current employment lifecycle facts."""
    import shifts_authority_wave1 as sw1

    ensure_shifts_integrity_wave2_schema(cur)
    company = (company_code or "").upper()
    as_of = as_of or datetime.now(KUWAIT_TZ).date()
    params: list[Any] = [company, as_of]
    emp_clause = ""
    if employee_key:
        emp_clause = "AND employee_key=%s"
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT * FROM shift_assignments
        WHERE company_code=%s AND status='scheduled' AND shift_date >= %s
        {emp_clause}
        ORDER BY shift_date, start_time
        """,
        params,
    )
    settings = sw1.get_shift_authority_settings(cur, company)
    flagged = []
    for row in cur.fetchall():
        shift = dict(row)
        emp = {"employee_key": shift.get("employee_key"), "company_code": company}
        denied = sw1.evaluate_assignment_lifecycle(
            cur,
            company_code=company,
            employee=emp,
            settings=settings,
            shift_date=_as_date(shift.get("shift_date")),
            start_time=shift.get("start_time"),
            end_time=shift.get("end_time"),
            ends_next_day=bool(shift.get("ends_next_day")),
            operation="flag_existing",
            action={},
        )
        if denied:
            res = open_reconciliation_flag(
                cur,
                company_code=company,
                shift=shift,
                flag_type="lifecycle_fact_change",
                details={"lifecycle": denied},
            )
            flagged.append(res.get("flag"))
    return {"ok": True, "flagged": flagged, "count": len(flagged)}


def reconcile_approved_leave_conflicts(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Flag scheduled shifts overlapping newly relevant approved leave — no auto-cancel."""
    import shifts_authority_wave1 as sw1

    ensure_shifts_integrity_wave2_schema(cur)
    company = (company_code or "").upper()
    as_of = as_of or datetime.now(KUWAIT_TZ).date()
    params: list[Any] = [company, as_of]
    emp_clause = ""
    if employee_key:
        emp_clause = "AND employee_key=%s"
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT * FROM shift_assignments
        WHERE company_code=%s AND status='scheduled' AND shift_date >= %s
        {emp_clause}
        ORDER BY shift_date, start_time
        """,
        params,
    )
    flagged = []
    for row in cur.fetchall():
        shift = dict(row)
        sd = _as_date(shift.get("shift_date"))
        if not sd:
            continue
        leaves = sw1.approved_leave_on_date(
            cur, company_code=company, employee_key=str(shift.get("employee_key")), shift_date=sd
        )
        if leaves:
            res = open_reconciliation_flag(
                cur,
                company_code=company,
                shift=shift,
                flag_type="approved_leave_conflict",
                details={"leaves": leaves},
            )
            flagged.append(res.get("flag"))
    return {"ok": True, "flagged": flagged, "count": len(flagged)}
