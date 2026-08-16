"""Leave Wave 3 — partial-day, unpaid boundary, evidence workflows (local/staging).

Does NOT enable enforcement (enforced/legal_reviewed remain false).
Does NOT deploy to production or mutate real production balances.
Payroll money calculations remain out of Leave.
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

LEAVE_WORKFLOW_WAVE3_VERSION = "3.0.0"
KUWAIT_TZ = ZoneInfo("Asia/Kuwait")
_ON_VALUES = {"1", "true", "yes", "on"}

DURATION_FULL_DAY = "full_day"
DURATION_HALF_DAY = "half_day"
DURATION_HOURLY = "hourly"
DURATION_UNITS = frozenset({DURATION_FULL_DAY, DURATION_HALF_DAY, DURATION_HOURLY})
HALF_PORTIONS = frozenset({"am", "pm", "first_half", "second_half"})

# Wave 3 status additions (observe / workflow only)
STATUS_NEEDS_INFO = "needs_info"
STATUS_WITHDRAWN = "withdrawn"
WAVE3_STATUSES = frozenset({STATUS_NEEDS_INFO, STATUS_WITHDRAWN})

SENSITIVE_CATEGORIES = frozenset({"medical", "sick", "sensitive", "confidential"})

SCHEMA_SQL = """
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS duration_unit text NOT NULL DEFAULT 'full_day';
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS half_portion text;
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS start_time time;
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS end_time time;
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS shift_id uuid;
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS chargeable_days numeric(8,4) NOT NULL DEFAULT 0;
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS chargeable_hours numeric(8,2) NOT NULL DEFAULT 0;
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS sensitive_category text;
ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS payroll_handoff jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS leave_request_attachments (
  attachment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  leave_id uuid NOT NULL REFERENCES leave_requests(leave_id) ON DELETE CASCADE,
  version int NOT NULL DEFAULT 1,
  filename text NOT NULL,
  content_type text NOT NULL DEFAULT 'application/octet-stream',
  storage_ref text NOT NULL,
  sha256 text,
  category text NOT NULL DEFAULT 'supporting',
  sensitive boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'active',
  replaces_attachment_id uuid,
  uploaded_by_phone text,
  rejected_by_phone text,
  rejected_reason text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT leave_attach_status_chk CHECK (status IN ('active','replaced','rejected','deleted'))
);
CREATE INDEX IF NOT EXISTS idx_leave_attach_leave
  ON leave_request_attachments(company_code, leave_id, status);

CREATE TABLE IF NOT EXISTS leave_attachment_audit (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  leave_id uuid,
  attachment_id uuid,
  action text NOT NULL,
  actor_phone text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS leave_payroll_handoff_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  leave_id uuid NOT NULL,
  employee_key text NOT NULL,
  leave_type text NOT NULL,
  classification jsonb NOT NULL DEFAULT '{}'::jsonb,
  monetary_fields_present boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
"""


def leave_workflow_wave3_enabled() -> bool:
    raw = os.environ.get("WATHEFNI_LEAVE_WORKFLOW_WAVE3")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON_VALUES


def ensure_leave_workflow_wave3_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def kuwait_today_w3(*, now: datetime | None = None) -> date:
    dt = now or datetime.now(tz=KUWAIT_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KUWAIT_TZ)
    return dt.astimezone(KUWAIT_TZ).date()


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.astimezone(KUWAIT_TZ).date() if value.tzinfo else value.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.timetz().replace(tzinfo=None) if value.tzinfo else value.time()
    s = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s[:8], fmt).time()
        except ValueError:
            continue
    return None


def _time_to_minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def shift_length_hours(start_t: time | None, end_t: time | None) -> Decimal:
    if not start_t or not end_t:
        return Decimal("8")  # default working day when no shift
    start_m = _time_to_minutes(start_t)
    end_m = _time_to_minutes(end_t)
    if end_m <= start_m:
        end_m += 24 * 60  # overnight
    return (Decimal(end_m - start_m) / Decimal("60")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_duration_from_action(action: dict[str, Any]) -> dict[str, Any]:
    unit = str(action.get("duration_unit") or action.get("leave_duration") or DURATION_FULL_DAY).strip().lower()
    if unit in {"full", "day", "full-day", "fullday"}:
        unit = DURATION_FULL_DAY
    if unit in {"half", "half-day", "halfday"}:
        unit = DURATION_HALF_DAY
    if unit in {"hour", "hours", "hourly", "partial"}:
        unit = DURATION_HOURLY
    if unit not in DURATION_UNITS:
        unit = DURATION_FULL_DAY
    portion = str(action.get("half_portion") or action.get("portion") or "").strip().lower() or None
    if portion in {"morning", "am", "first"}:
        portion = "am"
    if portion in {"afternoon", "pm", "second", "evening"}:
        portion = "pm"
    start_t = _as_time(action.get("start_time"))
    end_t = _as_time(action.get("end_time"))
    hours = action.get("hours")
    try:
        hours_d = Decimal(str(hours)) if hours is not None and str(hours).strip() != "" else None
    except Exception:
        hours_d = None
    return {
        "duration_unit": unit,
        "half_portion": portion if unit == DURATION_HALF_DAY else None,
        "start_time": start_t,
        "end_time": end_t,
        "hours": hours_d,
        "shift_id": action.get("shift_id"),
    }


def classify_leave_temporal_state(leave: dict[str, Any], *, as_of: date | None = None) -> str:
    """future | in_progress | completed"""
    today = as_of or kuwait_today_w3()
    start = _as_date(leave.get("start_date"))
    end = _as_date(leave.get("end_date")) or start
    if not start:
        return "unknown"
    if end and end < today:
        return "completed"
    if start > today:
        return "future"
    return "in_progress"


def effective_shifts_for_day(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    on_date: date,
    shift_id: str | None = None,
) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    if shift_id:
        cur.execute(
            """
            SELECT * FROM shift_assignments
            WHERE company_code=%s AND employee_key=%s AND shift_id=%s AND status='scheduled'
            LIMIT 1
            """,
            (company, employee_key, shift_id),
        )
        row = cur.fetchone()
        return [dict(row)] if row else []
    cur.execute(
        """
        SELECT * FROM shift_assignments
        WHERE company_code=%s AND employee_key=%s AND shift_date=%s AND status='scheduled'
        ORDER BY start_time
        """,
        (company, employee_key, on_date),
    )
    return [dict(r) for r in cur.fetchall()]


def validate_partial_against_shifts(
    *,
    duration: dict[str, Any],
    shifts: list[dict[str, Any]],
    on_date: date,
) -> dict[str, Any]:
    unit = duration["duration_unit"]
    if unit == DURATION_FULL_DAY:
        return {"ok": True, "shift_hours": None}
    if not shifts:
        # Allow observe-only default day length when no rostered shift
        default_h = Decimal("8")
        if unit == DURATION_HALF_DAY:
            return {"ok": True, "shift_hours": default_h, "chargeable_hours": default_h / 2, "warning": "no_shift_default_8h"}
        start_t, end_t = duration.get("start_time"), duration.get("end_time")
        if not start_t or not end_t:
            return {"ok": False, "error": "hourly_requires_start_end_time"}
        hrs = shift_length_hours(start_t, end_t)
        if hrs <= 0:
            return {"ok": False, "error": "invalid_hourly_window"}
        return {"ok": True, "shift_hours": default_h, "chargeable_hours": hrs, "warning": "no_shift_default_8h"}

    # Prefer first shift or matching shift_id
    shift = shifts[0]
    s_start = _as_time(shift.get("start_time"))
    s_end = _as_time(shift.get("end_time"))
    shift_h = shift_length_hours(s_start, s_end)
    if unit == DURATION_HALF_DAY:
        portion = duration.get("half_portion") or "am"
        if portion not in {"am", "pm", "first_half", "second_half"}:
            return {"ok": False, "error": "invalid_half_portion"}
        return {
            "ok": True,
            "shift_id": shift.get("shift_id"),
            "shift_hours": shift_h,
            "chargeable_hours": (shift_h / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "half_portion": "am" if portion in {"am", "first_half"} else "pm",
        }

    # hourly
    start_t, end_t = duration.get("start_time"), duration.get("end_time")
    if duration.get("hours") and (not start_t or not end_t):
        # hours-only: must fit within shift length
        hrs = Decimal(str(duration["hours"]))
        if hrs <= 0:
            return {"ok": False, "error": "invalid_hours"}
        if hrs > shift_h:
            return {"ok": False, "error": "hours_exceed_shift", "shift_hours": float(shift_h)}
        return {"ok": True, "shift_id": shift.get("shift_id"), "shift_hours": shift_h, "chargeable_hours": hrs}

    if not start_t or not end_t:
        return {"ok": False, "error": "hourly_requires_start_end_time"}
    req_h = shift_length_hours(start_t, end_t)
    if req_h <= 0:
        return {"ok": False, "error": "invalid_hourly_window"}
    # Window must fall inside shift (overnight-aware)
    if not _window_inside_shift(start_t, end_t, s_start, s_end):
        # try other splits on same day
        ok_any = False
        for sh in shifts[1:]:
            if _window_inside_shift(start_t, end_t, _as_time(sh.get("start_time")), _as_time(sh.get("end_time"))):
                shift = sh
                shift_h = shift_length_hours(_as_time(sh.get("start_time")), _as_time(sh.get("end_time")))
                ok_any = True
                break
        if not ok_any:
            return {"ok": False, "error": "hourly_outside_effective_shift", "shift_date": on_date.isoformat()}
    if req_h > shift_h:
        return {"ok": False, "error": "hours_exceed_shift", "shift_hours": float(shift_h)}
    return {
        "ok": True,
        "shift_id": shift.get("shift_id"),
        "shift_hours": shift_h,
        "chargeable_hours": req_h,
    }


def _window_inside_shift(req_start: time | None, req_end: time | None, shift_start: time | None, shift_end: time | None) -> bool:
    if not req_start or not req_end or not shift_start or not shift_end:
        return False
    rs, re = _time_to_minutes(req_start), _time_to_minutes(req_end)
    ss, se = _time_to_minutes(shift_start), _time_to_minutes(shift_end)
    if re <= rs:
        re += 24 * 60
    if se <= ss:
        se += 24 * 60
    # also allow request that wraps mapped into overnight shift by +24h on request start if needed
    if rs < ss and re <= se and (rs + 24 * 60) >= ss:
        rs += 24 * 60
        re += 24 * 60
    return rs >= ss and re <= se


def compute_chargeable(
    *,
    start_date: date,
    end_date: date,
    duration: dict[str, Any],
    weekend_days: Any,
    holiday_dates: set[date],
    shift_hours: Decimal | None,
    chargeable_hours: Decimal | None,
) -> dict[str, Any]:
    """Deterministic chargeable days (fractional) + hours."""
    import leave_policy_wave2 as w2

    unit = duration["duration_unit"]
    if unit == DURATION_FULL_DAY:
        days = w2.chargeable_leave_days_kuwait(
            start_date, end_date, weekend_days=weekend_days, holiday_dates=holiday_dates
        )
        # hours = days * typical shift; prefer provided shift_hours else 8
        per = shift_hours or Decimal("8")
        hours = (days * per).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {"chargeable_days": days, "chargeable_hours": hours, "duration_unit": unit}

    # Partial leave is single-calendar-day only in Wave 3
    if start_date != end_date:
        return {"ok": False, "error": "partial_day_must_be_single_date"}
    # If the day itself is weekend/holiday, chargeable is zero (cannot take partial on rest day)
    weekday_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    weekend = {str(w).lower() for w in (weekend_days or [])}
    if weekday_names[start_date.weekday()] in weekend or start_date in (holiday_dates or set()):
        return {"chargeable_days": Decimal("0"), "chargeable_hours": Decimal("0"), "duration_unit": unit, "non_working_day": True}

    per = shift_hours or Decimal("8")
    hrs = chargeable_hours if chargeable_hours is not None else (per / 2 if unit == DURATION_HALF_DAY else Decimal("0"))
    if hrs <= 0:
        return {"ok": False, "error": "zero_chargeable_hours"}
    days = (hrs / per).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if per > 0 else Decimal("0")
    return {"chargeable_days": days, "chargeable_hours": hrs, "duration_unit": unit, "ok": True}


def _norm_half(portion: str | None) -> str:
    return "am" if (portion or "am") in {"am", "first_half", "morning"} else "pm"


def intervals_overlap(
    a_start: date,
    a_end: date,
    a_unit: str,
    a_start_t: time | None,
    a_end_t: time | None,
    a_portion: str | None,
    b_start: date,
    b_end: date,
    b_unit: str,
    b_start_t: time | None,
    b_end_t: time | None,
    b_portion: str | None,
) -> bool:
    """Overlap across full-day and partial-day requests on shared dates."""
    if a_end < b_start or b_end < a_start:
        return False
    d = max(a_start, b_start)
    shared_end = min(a_end, b_end)
    while d <= shared_end:
        a_on = a_start <= d <= a_end
        b_on = b_start <= d <= b_end
        if not (a_on and b_on):
            d += timedelta(days=1)
            continue
        a_full = a_unit == DURATION_FULL_DAY
        b_full = b_unit == DURATION_FULL_DAY
        if a_full or b_full:
            return True
        # Both partial: only meaningful on their anchor day(s)
        if a_unit == DURATION_HALF_DAY and b_unit == DURATION_HALF_DAY:
            if _norm_half(a_portion) == _norm_half(b_portion):
                return True
        elif a_unit == DURATION_HOURLY and b_unit == DURATION_HOURLY:
            if _times_overlap(a_start_t, a_end_t, b_start_t, b_end_t):
                return True
        else:
            # half vs hourly — fail closed (overlap)
            return True
        d += timedelta(days=1)
    return False


def _times_overlap(a0: time | None, a1: time | None, b0: time | None, b1: time | None) -> bool:
    if not a0 or not a1 or not b0 or not b1:
        return True  # fail closed: treat unknown as overlap
    as_, ae = _time_to_minutes(a0), _time_to_minutes(a1)
    bs, be = _time_to_minutes(b0), _time_to_minutes(b1)
    if ae <= as_:
        ae += 24 * 60
    if be <= bs:
        be += 24 * 60
    return as_ < be and bs < ae


def find_overlapping_leaves(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    start_date: date,
    end_date: date,
    duration: dict[str, Any],
    exclude_leave_id: str | None = None,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM leave_requests
        WHERE company_code=%s
          AND employee_key=%s
          AND status IN ('requested','approved','needs_review','needs_info')
          AND start_date <= %s
          AND end_date >= %s
        ORDER BY requested_at DESC
        LIMIT 20
        """,
        ((company_code or "").upper(), employee_key, end_date, start_date),
    )
    out = []
    for row in cur.fetchall():
        d = dict(row)
        if exclude_leave_id and str(d.get("leave_id")) == str(exclude_leave_id):
            continue
        other_unit = str(d.get("duration_unit") or DURATION_FULL_DAY)
        if intervals_overlap(
            start_date,
            end_date,
            duration["duration_unit"],
            duration.get("start_time"),
            duration.get("end_time"),
            duration.get("half_portion"),
            _as_date(d.get("start_date")) or start_date,
            _as_date(d.get("end_date")) or end_date,
            other_unit,
            _as_time(d.get("start_time")),
            _as_time(d.get("end_time")),
            d.get("half_portion"),
        ):
            out.append(d)
    return out


def build_unpaid_payroll_handoff(leave: dict[str, Any]) -> dict[str, Any]:
    """Classification inputs only — never salary amounts or fractions applied as money."""
    return {
        "leave_id": str(leave.get("leave_id") or ""),
        "employee_key": str(leave.get("employee_key") or ""),
        "leave_type": "unpaid",
        "start_date": str(leave.get("start_date") or "")[:10],
        "end_date": str(leave.get("end_date") or "")[:10],
        "duration_unit": leave.get("duration_unit") or DURATION_FULL_DAY,
        "chargeable_days": float(leave.get("chargeable_days") or 0),
        "chargeable_hours": float(leave.get("chargeable_hours") or 0),
        "classification": "unpaid_leave",
        "payroll_owned": True,
        "monetary_fields": None,
        "salary_deduction": None,
        "pay_fraction": None,
        "note": "Leave provides classification/duration only; Payroll owns monetary impact.",
    }


def assert_handoff_has_no_money(handoff: dict[str, Any]) -> bool:
    """True when handoff contains classification/duration only (no money fields)."""
    if handoff.get("monetary_fields") not in (None, {}, []):
        return False
    if handoff.get("salary_deduction") is not None:
        return False
    if handoff.get("pay_fraction") is not None:
        return False
    for key in ("amount", "amount_kd", "wage", "deduction_kd", "salary", "currency_amount"):
        if handoff.get(key) is not None:
            return False
    return True


def mask_attachment_for_viewer(row: dict[str, Any], *, allowed: bool) -> dict[str, Any]:
    d = dict(row)
    if allowed:
        return d
    if d.get("sensitive") or str(d.get("category") or "").lower() in SENSITIVE_CATEGORIES:
        return {
            "attachment_id": d.get("attachment_id"),
            "leave_id": d.get("leave_id"),
            "version": d.get("version"),
            "status": d.get("status"),
            "category": d.get("category"),
            "sensitive": True,
            "masked": True,
            "filename": "[redacted]",
            "storage_ref": None,
            "content_type": None,
            "error": "attachment_access_denied",
        }
    return d


def add_leave_attachment(
    cur: Any,
    *,
    company_code: str,
    leave_id: str,
    filename: str,
    storage_ref: str,
    content_type: str = "application/octet-stream",
    category: str = "supporting",
    sensitive: bool = False,
    uploaded_by_phone: str | None = None,
    sha256: str | None = None,
    replaces_attachment_id: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    version = 1
    if replaces_attachment_id:
        cur.execute(
            "SELECT version FROM leave_request_attachments WHERE attachment_id=%s AND leave_id=%s",
            (replaces_attachment_id, leave_id),
        )
        prev = cur.fetchone()
        version = int(dict(prev)["version"]) + 1 if prev else 1
        cur.execute(
            """
            UPDATE leave_request_attachments
            SET status='replaced', updated_at=now()
            WHERE attachment_id=%s AND leave_id=%s AND status='active'
            """,
            (replaces_attachment_id, leave_id),
        )
    cur.execute(
        """
        INSERT INTO leave_request_attachments (
          company_code, leave_id, version, filename, content_type, storage_ref, sha256,
          category, sensitive, status, replaces_attachment_id, uploaded_by_phone, provenance
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company,
            leave_id,
            version,
            filename,
            content_type,
            storage_ref,
            sha256,
            category,
            bool(sensitive) or str(category).lower() in SENSITIVE_CATEGORIES,
            replaces_attachment_id,
            uploaded_by_phone,
            __import__("json").dumps(provenance or {"source": "wave3"}),
        ),
    )
    row = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO leave_attachment_audit (company_code, leave_id, attachment_id, action, actor_phone, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company,
            leave_id,
            row["attachment_id"],
            "replaced" if replaces_attachment_id else "uploaded",
            uploaded_by_phone,
            __import__("json").dumps({"filename": filename, "version": version}),
        ),
    )
    return row


def reject_leave_attachment(
    cur: Any,
    *,
    company_code: str,
    attachment_id: str,
    actor_phone: str | None,
    reason: str | None = None,
) -> dict[str, Any]:
    cur.execute(
        """
        UPDATE leave_request_attachments
        SET status='rejected', rejected_by_phone=%s, rejected_reason=%s, updated_at=now()
        WHERE attachment_id=%s AND company_code=%s AND status='active'
        RETURNING *
        """,
        (actor_phone, reason, attachment_id, (company_code or "").upper()),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "attachment_not_found"}
    d = dict(row)
    cur.execute(
        """
        INSERT INTO leave_attachment_audit (company_code, leave_id, attachment_id, action, actor_phone, payload)
        VALUES (%s,%s,%s,'rejected',%s,%s::jsonb)
        """,
        (d["company_code"], d["leave_id"], attachment_id, actor_phone, __import__("json").dumps({"reason": reason})),
    )
    return {"ok": True, "attachment": d}


def list_leave_attachments(
    cur: Any,
    *,
    company_code: str,
    leave_id: str,
    viewer_allowed_sensitive: bool,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM leave_request_attachments
        WHERE company_code=%s AND leave_id=%s AND status IN ('active','rejected','replaced')
        ORDER BY version DESC, created_at DESC
        """,
        ((company_code or "").upper(), leave_id),
    )
    return [mask_attachment_for_viewer(dict(r), allowed=viewer_allowed_sensitive) for r in cur.fetchall()]


def record_payroll_handoff(cur: Any, *, company_code: str, leave: dict[str, Any], handoff: dict[str, Any]) -> dict[str, Any]:
    money = not assert_handoff_has_no_money(handoff)
    cur.execute(
        """
        INSERT INTO leave_payroll_handoff_events (
          company_code, leave_id, employee_key, leave_type, classification, monetary_fields_present
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s)
        RETURNING *
        """,
        (
            (company_code or "").upper(),
            leave.get("leave_id"),
            leave.get("employee_key"),
            leave.get("leave_type") or "unpaid",
            __import__("json").dumps(handoff),
            money,
        ),
    )
    return dict(cur.fetchone())
