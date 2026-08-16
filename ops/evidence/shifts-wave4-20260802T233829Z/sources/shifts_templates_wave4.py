"""Shifts Wave 4 — templates and recurring schedules (local/staging).

Planning instructions only. Generated L0 shift_assignments remain the sole
operational authority. Materialization writes status=scheduled immediately
(no draft/publish).

Does NOT: rotations, coverage, draft/publish, open shifts, PAM, Payroll money,
Leave balance mutation, Attendance authority mutation, production deploy,
real employee enablement, real reminders, or operator timers.
"""
from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import shifts_authority_wave1 as w1
import shifts_schedule_integrity_wave2 as w2

SHIFTS_WAVE4_VERSION = "4.0.0"
_ON = {"1", "true", "yes", "on"}

DEFAULT_W4_SYNTHETIC_KEY_MARKERS = ("SHW4", "SHW4-SYNTH|")
DEFAULT_W4_SYNTHETIC_PHONE_PREFIXES = ("965532",)
DEFAULT_HORIZON_DAYS = 90
MAX_HORIZON_DAYS = 180

# Advisory lock namespace for materialize(company, recurrence)
JOB_LOCK_MATERIALIZE_BASE = 740_400_001

SCHEMA_SQL = (Path(__file__).resolve().parent / "ops" / "sql" / "shifts_templates_wave4_v1.sql").read_text(
    encoding="utf-8"
)


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    s = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(s[:8], fmt).time()
        except ValueError:
            continue
    return None


def _time_str(value: Any) -> str:
    t = _as_time(value)
    return t.strftime("%H:%M") if t else ""


def shifts_wave4_enabled() -> bool:
    raw = os.environ.get("WATHEFNI_SHIFTS_WAVE4")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON


def shifts_wave4_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE4_COMPANIES") or "WATHEFNI").strip()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def shifts_wave4_enabled_for_company(company_code: str | None) -> bool:
    if not shifts_wave4_enabled():
        return False
    companies = shifts_wave4_companies()
    if not companies:
        return False
    return (company_code or "").upper() in companies


def shifts_wave4_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() == "production"
    return str(raw).strip().lower() in _ON


def wave4_synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return DEFAULT_W4_SYNTHETIC_KEY_MARKERS


def wave4_synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return DEFAULT_W4_SYNTHETIC_PHONE_PREFIXES


def is_wave4_synthetic_employee(
    *,
    employee_key: Any = None,
    phone: Any = None,
    name: Any = None,
    employee: dict[str, Any] | None = None,
) -> bool:
    key = str(employee_key or (employee or {}).get("employee_key") or "")
    phone_d = _digits(phone or (employee or {}).get("phone") or (employee or {}).get("employee_phone"))
    nm = str(name or (employee or {}).get("name") or "")
    for marker in wave4_synthetic_key_markers():
        if marker and (marker in key or marker in nm):
            return True
    for prefix in wave4_synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    raw = (employee or {}).get("raw_json") if isinstance(employee, dict) else None
    if isinstance(raw, dict) and (raw.get("shw4") is True or str(raw.get("shw4") or "").lower() in _ON):
        return True
    return False


def default_horizon_days() -> int:
    try:
        n = int(os.environ.get("WATHEFNI_SHIFTS_WAVE4_DEFAULT_HORIZON_DAYS") or DEFAULT_HORIZON_DAYS)
    except (TypeError, ValueError):
        n = DEFAULT_HORIZON_DAYS
    return max(1, min(n, MAX_HORIZON_DAYS))


def clamp_horizon(days: Any) -> int:
    try:
        n = int(days)
    except (TypeError, ValueError):
        n = default_horizon_days()
    return max(1, min(n, MAX_HORIZON_DAYS))


def honesty_payload() -> dict[str, Any]:
    return {
        "shifts_wave4_version": SHIFTS_WAVE4_VERSION,
        "payroll_money": False,
        "leave_balances_mutated": False,
        "attendance_authority_mutated": False,
        "templates": True,
        "recurring_schedules": True,
        "rotations": False,
        "publishing": False,
        "open_shifts": False,
        "pam_export": False,
        "draft_publish": False,
        "complexity_levels": {
            "simple": "manual_l0_only",
            "medium": "templates_and_weekly_recurrence",
            "enterprise_later": "rotations_coverage_publishing",
        },
        "wave4_synthetic_markers": {
            "key_markers": list(wave4_synthetic_key_markers()),
            "phone_prefixes": list(wave4_synthetic_phone_prefixes()),
        },
    }


def ensure_shifts_templates_wave4_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def planning_fingerprint(template: dict[str, Any], recurrence: dict[str, Any]) -> str:
    parts = [
        str(template.get("template_id") or ""),
        str(template.get("planning_version") or ""),
        str(template.get("start_time") or ""),
        str(template.get("end_time") or ""),
        str(recurrence.get("recurrence_id") or ""),
        str(recurrence.get("planning_version") or ""),
        str(recurrence.get("cycle_type") or ""),
        str(recurrence.get("alternate_template_id") or ""),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]


def occurrence_key(
    *,
    company_code: str,
    recurrence_id: Any,
    employee_key: str,
    shift_date: date,
    template_id: Any,
    start_time: Any,
    end_time: Any,
) -> str:
    return "|".join(
        [
            "SHW4",
            (company_code or "").upper(),
            str(recurrence_id or ""),
            str(employee_key or ""),
            shift_date.isoformat(),
            str(template_id or ""),
            _time_str(start_time),
            _time_str(end_time),
        ]
    )


def materialize_idempotency_key(occ_key: str) -> str:
    return occ_key


def materialize_lock_key(company_code: str, recurrence_id: Any) -> int:
    raw = f"{(company_code or '').upper()}|{recurrence_id}"
    digest = hashlib.md5(raw.encode()).hexdigest()
    return JOB_LOCK_MATERIALIZE_BASE + (int(digest[:8], 16) % 1_000_000)


# --- CRUD helpers -------------------------------------------------------------

def _row(cur: Any) -> dict[str, Any] | None:
    r = cur.fetchone()
    return dict(r) if r else None


def _rows(cur: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def create_template(cur: Any, *, company_code: str, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    ensure_shifts_templates_wave4_schema(cur)
    company = (company_code or "").upper()
    start = _as_time(payload.get("start_time"))
    end = _as_time(payload.get("end_time"))
    if not start or not end:
        return {"ok": False, "error": "invalid_template_window"}
    name = str(payload.get("name") or "").strip()
    if len(name) < 2:
        return {"ok": False, "error": "template_name_required"}
    ends_next = w1.ends_next_day_for(start, end)
    cur.execute(
        """
        INSERT INTO shift_templates (
          company_code, name, status, start_time, end_time, ends_next_day,
          break_minutes, role, site_key, branch_key, team_key, position_key,
          location, timezone, notes, created_by_phone, updated_by_phone
        ) VALUES (%s,%s,'active',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            name,
            start,
            end,
            ends_next,
            payload.get("break_minutes"),
            str(payload.get("role") or "").strip() or None,
            str(payload.get("site_key") or "").strip() or None,
            str(payload.get("branch_key") or "").strip() or None,
            str(payload.get("team_key") or "").strip() or None,
            str(payload.get("position_key") or "").strip() or None,
            str(payload.get("location") or "").strip() or None,
            str(payload.get("timezone") or "Asia/Kuwait").strip() or "Asia/Kuwait",
            str(payload.get("notes") or "").strip() or None,
            _digits(actor_phone) or None,
            _digits(actor_phone) or None,
        ),
    )
    return {"ok": True, "template": _row(cur), **honesty_payload()}


def get_template(cur: Any, *, company_code: str, template_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_templates WHERE company_code=%s AND template_id=%s",
        ((company_code or "").upper(), str(template_id)),
    )
    return _row(cur)


def list_templates(cur: Any, *, company_code: str, include_archived: bool = False) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    if include_archived:
        cur.execute(
            "SELECT * FROM shift_templates WHERE company_code=%s ORDER BY name, created_at",
            (company,),
        )
    else:
        cur.execute(
            "SELECT * FROM shift_templates WHERE company_code=%s AND status='active' ORDER BY name, created_at",
            (company,),
        )
    return _rows(cur)


def update_template(cur: Any, *, company_code: str, template_id: Any, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    """Bump planning_version. Does not rewrite L0 assignments."""
    ensure_shifts_templates_wave4_schema(cur)
    existing = get_template(cur, company_code=company_code, template_id=template_id)
    if not existing:
        return {"ok": False, "error": "template_not_found"}
    start = _as_time(payload.get("start_time") if "start_time" in payload else existing.get("start_time"))
    end = _as_time(payload.get("end_time") if "end_time" in payload else existing.get("end_time"))
    if not start or not end:
        return {"ok": False, "error": "invalid_template_window"}
    ends_next = w1.ends_next_day_for(start, end)
    name = str(payload.get("name") if "name" in payload else existing.get("name") or "").strip()
    cur.execute(
        """
        UPDATE shift_templates SET
          name=%s, start_time=%s, end_time=%s, ends_next_day=%s,
          break_minutes=%s, role=%s, site_key=%s, branch_key=%s, team_key=%s,
          position_key=%s, location=%s, timezone=%s, notes=%s,
          planning_version=planning_version+1, row_version=row_version+1,
          updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s AND template_id=%s
        RETURNING *
        """,
        (
            name,
            start,
            end,
            ends_next,
            payload.get("break_minutes") if "break_minutes" in payload else existing.get("break_minutes"),
            str(payload.get("role") if "role" in payload else existing.get("role") or "").strip() or None,
            str(payload.get("site_key") if "site_key" in payload else existing.get("site_key") or "").strip() or None,
            str(payload.get("branch_key") if "branch_key" in payload else existing.get("branch_key") or "").strip() or None,
            str(payload.get("team_key") if "team_key" in payload else existing.get("team_key") or "").strip() or None,
            str(payload.get("position_key") if "position_key" in payload else existing.get("position_key") or "").strip() or None,
            str(payload.get("location") if "location" in payload else existing.get("location") or "").strip() or None,
            str(payload.get("timezone") if "timezone" in payload else existing.get("timezone") or "Asia/Kuwait"),
            str(payload.get("notes") if "notes" in payload else existing.get("notes") or "").strip() or None,
            _digits(actor_phone) or None,
            (company_code or "").upper(),
            str(template_id),
        ),
    )
    return {"ok": True, "template": _row(cur), "l0_rewritten": False, **honesty_payload()}


def archive_template(cur: Any, *, company_code: str, template_id: Any, actor_phone: str | None = None) -> dict[str, Any]:
    cur.execute(
        """
        UPDATE shift_templates SET status='archived', planning_version=planning_version+1,
          row_version=row_version+1, updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s AND template_id=%s
        RETURNING *
        """,
        (_digits(actor_phone) or None, (company_code or "").upper(), str(template_id)),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "template_not_found"}
    return {"ok": True, "template": row, **honesty_payload()}


def _record_recurrence_event(cur: Any, *, company_code: str, recurrence_id: Any, event_type: str, payload: dict[str, Any] | None, actor_phone: str | None) -> None:
    cur.execute(
        """
        INSERT INTO shift_recurrence_events (company_code, recurrence_id, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            str(recurrence_id),
            event_type,
            __import__("json").dumps(payload or {}),
            _digits(actor_phone) or None,
        ),
    )


def create_recurrence(cur: Any, *, company_code: str, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    ensure_shifts_templates_wave4_schema(cur)
    company = (company_code or "").upper()
    template_id = payload.get("template_id")
    tmpl = get_template(cur, company_code=company, template_id=template_id)
    if not tmpl or str(tmpl.get("status")) != "active":
        return {"ok": False, "error": "template_not_found_or_archived"}
    alt_id = payload.get("alternate_template_id")
    if alt_id:
        alt = get_template(cur, company_code=company, template_id=alt_id)
        if not alt or str(alt.get("status")) != "active":
            return {"ok": False, "error": "alternate_template_not_found_or_archived"}
    cycle_type = str(payload.get("cycle_type") or "").strip()
    if cycle_type not in {"weekly_weekdays", "n_on_m_off", "alternating_templates"}:
        return {"ok": False, "error": "invalid_cycle_type"}
    target_type = str(payload.get("target_type") or "").strip()
    target_key = str(payload.get("target_key") or "").strip()
    if target_type not in {"employee", "team", "site", "role"} or not target_key:
        return {"ok": False, "error": "invalid_target"}
    effective_start = _as_date(payload.get("effective_start"))
    if not effective_start:
        return {"ok": False, "error": "effective_start_required"}
    effective_end = _as_date(payload.get("effective_end"))
    weekdays = payload.get("weekdays") or []
    if isinstance(weekdays, str):
        weekdays = [int(x) for x in weekdays.split(",") if str(x).strip().isdigit()]
    weekdays = [int(x) for x in weekdays if int(x) in range(7)]
    if cycle_type == "weekly_weekdays" and not weekdays:
        return {"ok": False, "error": "weekdays_required"}
    on_days = int(payload.get("on_days") or 0) or None
    off_days = int(payload.get("off_days") or 0) or None
    if cycle_type == "n_on_m_off" and (not on_days or off_days is None):
        return {"ok": False, "error": "on_off_days_required"}
    if cycle_type == "alternating_templates" and not alt_id:
        return {"ok": False, "error": "alternate_template_required"}
    name = str(payload.get("name") or "").strip() or f"Recurrence {cycle_type}"
    horizon = clamp_horizon(payload.get("horizon_days") or default_horizon_days())
    anchor = _as_date(payload.get("cycle_anchor_date")) or effective_start
    cur.execute(
        """
        INSERT INTO shift_recurrences (
          company_code, name, status, template_id, alternate_template_id, cycle_type,
          weekdays, on_days, off_days, cycle_anchor_date, effective_start, effective_end,
          horizon_days, target_type, target_key, created_by_phone, updated_by_phone
        ) VALUES (%s,%s,'active',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            name,
            str(template_id),
            str(alt_id) if alt_id else None,
            cycle_type,
            weekdays,
            on_days,
            off_days,
            anchor,
            effective_start,
            effective_end,
            horizon,
            target_type,
            target_key,
            _digits(actor_phone) or None,
            _digits(actor_phone) or None,
        ),
    )
    row = _row(cur)
    _record_recurrence_event(cur, company_code=company, recurrence_id=row["recurrence_id"], event_type="created", payload={"recurrence": _jsonable(row)}, actor_phone=actor_phone)
    return {"ok": True, "recurrence": row, **honesty_payload()}


def get_recurrence(cur: Any, *, company_code: str, recurrence_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_recurrences WHERE company_code=%s AND recurrence_id=%s",
        ((company_code or "").upper(), str(recurrence_id)),
    )
    return _row(cur)


def list_recurrences(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT * FROM shift_recurrences WHERE company_code=%s ORDER BY created_at DESC",
        ((company_code or "").upper(),),
    )
    return _rows(cur)


def update_recurrence(cur: Any, *, company_code: str, recurrence_id: Any, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    existing = get_recurrence(cur, company_code=company_code, recurrence_id=recurrence_id)
    if not existing:
        return {"ok": False, "error": "recurrence_not_found"}
    if str(existing.get("status")) == "ended":
        return {"ok": False, "error": "recurrence_ended"}
    fields = {
        "name": str(payload.get("name") if "name" in payload else existing.get("name") or "").strip(),
        "horizon_days": clamp_horizon(payload.get("horizon_days") if "horizon_days" in payload else existing.get("horizon_days")),
        "effective_end": _as_date(payload.get("effective_end")) if "effective_end" in payload else _as_date(existing.get("effective_end")),
        "weekdays": payload.get("weekdays") if "weekdays" in payload else existing.get("weekdays"),
        "on_days": payload.get("on_days") if "on_days" in payload else existing.get("on_days"),
        "off_days": payload.get("off_days") if "off_days" in payload else existing.get("off_days"),
        "template_id": str(payload.get("template_id") if "template_id" in payload else existing.get("template_id")),
        "alternate_template_id": (
            str(payload["alternate_template_id"]) if payload.get("alternate_template_id") else None
        )
        if "alternate_template_id" in payload
        else (str(existing["alternate_template_id"]) if existing.get("alternate_template_id") else None),
        "target_type": str(payload.get("target_type") if "target_type" in payload else existing.get("target_type")),
        "target_key": str(payload.get("target_key") if "target_key" in payload else existing.get("target_key")),
    }
    if isinstance(fields["weekdays"], str):
        fields["weekdays"] = [int(x) for x in fields["weekdays"].split(",") if str(x).strip().isdigit()]
    cur.execute(
        """
        UPDATE shift_recurrences SET
          name=%s, horizon_days=%s, effective_end=%s, weekdays=%s, on_days=%s, off_days=%s,
          template_id=%s, alternate_template_id=%s, target_type=%s, target_key=%s,
          planning_version=planning_version+1, row_version=row_version+1,
          updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s AND recurrence_id=%s
        RETURNING *
        """,
        (
            fields["name"],
            fields["horizon_days"],
            fields["effective_end"],
            fields["weekdays"] or [],
            fields["on_days"],
            fields["off_days"],
            fields["template_id"],
            fields["alternate_template_id"],
            fields["target_type"],
            fields["target_key"],
            _digits(actor_phone) or None,
            (company_code or "").upper(),
            str(recurrence_id),
        ),
    )
    row = _row(cur)
    _record_recurrence_event(cur, company_code=company_code, recurrence_id=recurrence_id, event_type="updated", payload={"recurrence": _jsonable(row)}, actor_phone=actor_phone)
    return {"ok": True, "recurrence": row, "l0_rewritten": False, **honesty_payload()}


def pause_recurrence(cur: Any, *, company_code: str, recurrence_id: Any, actor_phone: str | None = None) -> dict[str, Any]:
    cur.execute(
        """
        UPDATE shift_recurrences SET status='paused', paused_at=now(),
          planning_version=planning_version+1, row_version=row_version+1,
          updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s AND recurrence_id=%s AND status='active'
        RETURNING *
        """,
        (_digits(actor_phone) or None, (company_code or "").upper(), str(recurrence_id)),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "recurrence_not_active"}
    _record_recurrence_event(cur, company_code=company_code, recurrence_id=recurrence_id, event_type="paused", payload={}, actor_phone=actor_phone)
    return {"ok": True, "recurrence": row, **honesty_payload()}


def resume_recurrence(cur: Any, *, company_code: str, recurrence_id: Any, actor_phone: str | None = None) -> dict[str, Any]:
    cur.execute(
        """
        UPDATE shift_recurrences SET status='active', paused_at=NULL,
          planning_version=planning_version+1, row_version=row_version+1,
          updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s AND recurrence_id=%s AND status='paused'
        RETURNING *
        """,
        (_digits(actor_phone) or None, (company_code or "").upper(), str(recurrence_id)),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "recurrence_not_paused"}
    _record_recurrence_event(cur, company_code=company_code, recurrence_id=recurrence_id, event_type="resumed", payload={}, actor_phone=actor_phone)
    return {"ok": True, "recurrence": row, **honesty_payload()}


def end_recurrence(cur: Any, *, company_code: str, recurrence_id: Any, actor_phone: str | None = None) -> dict[str, Any]:
    today = date.today()
    cur.execute(
        """
        UPDATE shift_recurrences SET status='ended', ended_at=now(),
          effective_end=COALESCE(effective_end, %s),
          planning_version=planning_version+1, row_version=row_version+1,
          updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s AND recurrence_id=%s AND status IN ('active','paused')
        RETURNING *
        """,
        (today, _digits(actor_phone) or None, (company_code or "").upper(), str(recurrence_id)),
    )
    row = _row(cur)
    if not row:
        return {"ok": False, "error": "recurrence_not_found_or_ended"}
    _record_recurrence_event(cur, company_code=company_code, recurrence_id=recurrence_id, event_type="ended", payload={}, actor_phone=actor_phone)
    return {"ok": True, "recurrence": row, **honesty_payload()}


def upsert_exception(cur: Any, *, company_code: str, recurrence_id: Any, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    ensure_shifts_templates_wave4_schema(cur)
    rec = get_recurrence(cur, company_code=company_code, recurrence_id=recurrence_id)
    if not rec:
        return {"ok": False, "error": "recurrence_not_found"}
    ex_date = _as_date(payload.get("exception_date") or payload.get("date"))
    kind = str(payload.get("kind") or "").strip()
    if not ex_date or kind not in {"skip", "one_off_override"}:
        return {"ok": False, "error": "invalid_exception"}
    cur.execute(
        """
        INSERT INTO shift_recurrence_exceptions (
          company_code, recurrence_id, exception_date, kind,
          override_template_id, override_start_time, override_end_time, notes, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (recurrence_id, exception_date) DO UPDATE SET
          kind=EXCLUDED.kind,
          override_template_id=EXCLUDED.override_template_id,
          override_start_time=EXCLUDED.override_start_time,
          override_end_time=EXCLUDED.override_end_time,
          notes=EXCLUDED.notes
        RETURNING *
        """,
        (
            (company_code or "").upper(),
            str(recurrence_id),
            ex_date,
            kind,
            str(payload["override_template_id"]) if payload.get("override_template_id") else None,
            _as_time(payload.get("override_start_time")),
            _as_time(payload.get("override_end_time")),
            str(payload.get("notes") or "").strip() or None,
            _digits(actor_phone) or None,
        ),
    )
    row = _row(cur)
    _record_recurrence_event(cur, company_code=company_code, recurrence_id=recurrence_id, event_type="exception_upserted", payload={"exception": _jsonable(row)}, actor_phone=actor_phone)
    return {"ok": True, "exception": row, **honesty_payload()}


def list_exceptions(cur: Any, *, company_code: str, recurrence_id: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM shift_recurrence_exceptions
        WHERE company_code=%s AND recurrence_id=%s
        ORDER BY exception_date
        """,
        ((company_code or "").upper(), str(recurrence_id)),
    )
    return _rows(cur)


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (date, datetime, time, UUID)):
        return str(obj)
    return obj


# --- Expansion ----------------------------------------------------------------

def resolve_target_employees(cur: Any, *, company_code: str, target_type: str, target_key: str) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    key = str(target_key or "").strip()
    if target_type == "employee":
        cur.execute(
            """
            SELECT employee_key, name, phone, company_code, raw_json
            FROM employees WHERE company_code=%s AND employee_key=%s
            """,
            (company, key),
        )
        row = _row(cur)
        return [row] if row else []
    if target_type == "team":
        cur.execute(
            """
            SELECT DISTINCT e.employee_key, e.name, e.phone, e.company_code, e.raw_json
            FROM employees e
            JOIN employee_org_assignments a
              ON a.company_code=e.company_code AND a.employee_key=e.employee_key
            WHERE e.company_code=%s AND coalesce(a.team_key,'')=%s
            ORDER BY e.employee_key
            LIMIT 200
            """,
            (company, key),
        )
        rows = _rows(cur)
        if rows:
            return rows
        # Fallback: raw_json.team_key
        cur.execute(
            """
            SELECT employee_key, name, phone, company_code, raw_json
            FROM employees
            WHERE company_code=%s AND coalesce(raw_json->>'team_key','')=%s
            ORDER BY employee_key LIMIT 200
            """,
            (company, key),
        )
        return _rows(cur)
    if target_type == "site":
        cur.execute(
            """
            SELECT employee_key, name, phone, company_code, raw_json
            FROM employees
            WHERE company_code=%s AND coalesce(raw_json->>'site_key','')=%s
            ORDER BY employee_key LIMIT 200
            """,
            (company, key),
        )
        return _rows(cur)
    if target_type == "role":
        cur.execute(
            """
            SELECT DISTINCT e.employee_key, e.name, e.phone, e.company_code, e.raw_json
            FROM employees e
            LEFT JOIN employee_org_assignments a
              ON a.company_code=e.company_code AND a.employee_key=e.employee_key
            WHERE e.company_code=%s
              AND (coalesce(a.role,'')=%s OR coalesce(e.raw_json->>'role','')=%s)
            ORDER BY e.employee_key
            LIMIT 200
            """,
            (company, key, key),
        )
        return _rows(cur)
    return []


def _weekday_sun0(d: date) -> int:
    """Sunday=0 … Saturday=6 (Kuwait/work-week friendly)."""
    return (d.weekday() + 1) % 7


def _iso_week_index(d: date, anchor: date) -> int:
    """0-based week index from Monday-aligned weeks relative to anchor week."""
    a = anchor - timedelta(days=anchor.weekday())
    b = d - timedelta(days=d.weekday())
    return max(0, (b - a).days // 7)


def expand_occurrence_dates(recurrence: dict[str, Any], *, window_start: date, window_end: date) -> list[date]:
    """Return dates in [window_start, window_end] that the cycle includes (pre-exception)."""
    cycle = str(recurrence.get("cycle_type") or "")
    out: list[date] = []
    d = window_start
    weekdays = set(int(x) for x in (recurrence.get("weekdays") or []) if int(x) in range(7))
    on_days = int(recurrence.get("on_days") or 0)
    off_days = int(recurrence.get("off_days") or 0)
    anchor = _as_date(recurrence.get("cycle_anchor_date")) or _as_date(recurrence.get("effective_start")) or window_start
    while d <= window_end:
        include = False
        if cycle == "weekly_weekdays":
            include = _weekday_sun0(d) in weekdays
        elif cycle == "n_on_m_off" and on_days > 0:
            cycle_len = on_days + max(0, off_days)
            offset = (d - anchor).days
            if offset >= 0 and cycle_len > 0:
                include = (offset % cycle_len) < on_days
        elif cycle == "alternating_templates":
            # Every calendar day in active weeks gets an occurrence; template chosen later.
            include = True
        if include:
            out.append(d)
        d += timedelta(days=1)
    return out


def pick_template_for_date(
    cur: Any,
    *,
    company_code: str,
    recurrence: dict[str, Any],
    day: date,
    exception: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if exception and str(exception.get("kind")) == "one_off_override" and exception.get("override_template_id"):
        return get_template(cur, company_code=company_code, template_id=exception["override_template_id"])
    cycle = str(recurrence.get("cycle_type") or "")
    primary = get_template(cur, company_code=company_code, template_id=recurrence.get("template_id"))
    if cycle == "alternating_templates" and recurrence.get("alternate_template_id"):
        anchor = _as_date(recurrence.get("cycle_anchor_date")) or _as_date(recurrence.get("effective_start")) or day
        week_idx = _iso_week_index(day, anchor)
        if week_idx % 2 == 1:
            return get_template(cur, company_code=company_code, template_id=recurrence["alternate_template_id"])
    return primary


def build_planned_occurrences(
    cur: Any,
    *,
    company_code: str,
    recurrence: dict[str, Any],
    today: date | None = None,
    force_include_today: bool = False,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    today = today or date.today()
    if str(recurrence.get("status")) == "paused":
        return {"ok": True, "occurrences": [], "skipped": "paused", **honesty_payload()}
    if str(recurrence.get("status")) == "ended":
        return {"ok": True, "occurrences": [], "skipped": "ended", **honesty_payload()}

    effective_start = _as_date(recurrence.get("effective_start")) or today
    effective_end = _as_date(recurrence.get("effective_end"))
    horizon = clamp_horizon(recurrence.get("horizon_days") or default_horizon_days())
    # Default: skip current day (historical/current unchanged; regen starts tomorrow)
    window_start = max(effective_start, today if force_include_today else today + timedelta(days=1))
    window_end = today + timedelta(days=horizon)
    if effective_end:
        window_end = min(window_end, effective_end)
    if window_start > window_end:
        return {"ok": True, "occurrences": [], "window": {"start": window_start.isoformat(), "end": window_end.isoformat()}, **honesty_payload()}

    employees = resolve_target_employees(
        cur,
        company_code=company,
        target_type=str(recurrence.get("target_type")),
        target_key=str(recurrence.get("target_key")),
    )
    if shifts_wave4_synthetic_only():
        employees = [
            e
            for e in employees
            if is_wave4_synthetic_employee(employee=e, employee_key=e.get("employee_key"), phone=e.get("phone"), name=e.get("name"))
        ]
    if not employees:
        return {
            "ok": True,
            "occurrences": [],
            "skipped_target": True,
            "target_type": recurrence.get("target_type"),
            "target_key": recurrence.get("target_key"),
            **honesty_payload(),
        }

    exceptions = {str(_as_date(e.get("exception_date"))): e for e in list_exceptions(cur, company_code=company, recurrence_id=recurrence.get("recurrence_id"))}
    dates = expand_occurrence_dates(recurrence, window_start=window_start, window_end=window_end)
    planned: list[dict[str, Any]] = []
    for day in dates:
        ex = exceptions.get(day.isoformat())
        if ex and str(ex.get("kind")) == "skip":
            continue
        tmpl = pick_template_for_date(cur, company_code=company, recurrence=recurrence, day=day, exception=ex)
        if not tmpl or str(tmpl.get("status")) != "active":
            continue
        start_t = _as_time(ex.get("override_start_time") if ex else None) or _as_time(tmpl.get("start_time"))
        end_t = _as_time(ex.get("override_end_time") if ex else None) or _as_time(tmpl.get("end_time"))
        if not start_t or not end_t:
            continue
        ends_next = w1.ends_next_day_for(start_t, end_t)
        fp = planning_fingerprint(tmpl, recurrence)
        for emp in employees:
            ek = str(emp.get("employee_key"))
            ok = occurrence_key(
                company_code=company,
                recurrence_id=recurrence.get("recurrence_id"),
                employee_key=ek,
                shift_date=day,
                template_id=tmpl.get("template_id"),
                start_time=start_t,
                end_time=end_t,
            )
            planned.append(
                {
                    "occurrence_key": ok,
                    "idempotency_key": materialize_idempotency_key(ok),
                    "employee_key": ek,
                    "employee_name": emp.get("name"),
                    "employee_phone": emp.get("phone"),
                    "employee": emp,
                    "shift_date": day.isoformat(),
                    "start_time": _time_str(start_t),
                    "end_time": _time_str(end_t),
                    "ends_next_day": ends_next,
                    "template_id": str(tmpl.get("template_id")),
                    "recurrence_id": str(recurrence.get("recurrence_id")),
                    "generated_from_version": fp,
                    "break_minutes": tmpl.get("break_minutes"),
                    "role": tmpl.get("role"),
                    "site_key": tmpl.get("site_key"),
                    "branch_key": tmpl.get("branch_key"),
                    "team_key": tmpl.get("team_key"),
                    "position_key": tmpl.get("position_key"),
                    "location": tmpl.get("location"),
                    "timezone": tmpl.get("timezone") or "Asia/Kuwait",
                }
            )
    return {
        "ok": True,
        "occurrences": planned,
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "employee_count": len(employees),
        **honesty_payload(),
    }


# --- Preview / materialize ----------------------------------------------------

def _find_existing_by_occurrence(cur: Any, *, company_code: str, occurrence_key_value: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM shift_assignments
        WHERE company_code=%s AND occurrence_key=%s
        ORDER BY CASE WHEN status='scheduled' THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
        """,
        ((company_code or "").upper(), occurrence_key_value),
    )
    return _row(cur)


def _find_existing_by_idempotency(cur: Any, *, company_code: str, idem: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_assignments WHERE company_code=%s AND idempotency_key=%s LIMIT 1",
        ((company_code or "").upper(), idem),
    )
    return _row(cur)


def _windows_match(existing: dict[str, Any], planned: dict[str, Any]) -> bool:
    return (
        str(existing.get("shift_date") or "")[:10] == str(planned.get("shift_date") or "")[:10]
        and _time_str(existing.get("start_time")) == _time_str(planned.get("start_time"))
        and _time_str(existing.get("end_time")) == _time_str(planned.get("end_time"))
        and bool(existing.get("ends_next_day")) == bool(planned.get("ends_next_day"))
    )


def evaluate_planned_conflicts(
    cur: Any,
    *,
    company_code: str,
    planned: dict[str, Any],
    action_acks: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return denial dict if conflict, else None. Uses Wave 1/2 gates."""
    company = (company_code or "").upper()
    emp = planned.get("employee") or {"employee_key": planned.get("employee_key"), "phone": planned.get("employee_phone"), "name": planned.get("employee_name")}
    shift_date = _as_date(planned.get("shift_date"))
    start_time = _as_time(planned.get("start_time"))
    end_time = _as_time(planned.get("end_time"))
    ends_next = bool(planned.get("ends_next_day"))
    if not shift_date or not start_time or not end_time:
        return {"error": "invalid_planned_window"}
    action = dict(action_acks or {})
    if w1.shifts_authority_applies_to(company, emp):
        settings = w1.get_shift_authority_settings(cur, company)
        life = w1.evaluate_assignment_lifecycle(
            cur,
            company_code=company,
            employee=emp,
            settings=settings,
            shift_date=shift_date,
            start_time=start_time,
            end_time=end_time,
            ends_next_day=ends_next,
            operation="create",
            action=action,
        )
        if life:
            return life
        leaves = w1.approved_leave_on_date(cur, company_code=company, employee_key=str(emp.get("employee_key")), shift_date=shift_date)
        leave_denied = w1.leave_conflict_denied(mode=str(settings.get("leave_conflict_mode") or "require_ack"), leaves=leaves, action=action)
        if leave_denied:
            return leave_denied
    if w2.shifts_wave2_applies_to(company, emp):
        integ = w2.get_integrity_settings(cur, company)
        avail_hits = w2.approved_unavailability_overlaps(
            cur,
            company_code=company,
            employee_key=str(emp.get("employee_key")),
            shift_date=shift_date,
            start_time=start_time,
            end_time=end_time,
            ends_next_day=ends_next,
        )
        avail_denied = w2.availability_conflict_denied(mode=str(integ.get("availability_conflict_mode") or "require_ack"), hits=avail_hits, action=action)
        if avail_denied:
            return avail_denied
        seasonal = w2.evaluate_seasonal_policies(
            cur,
            company_code=company,
            shift_date=shift_date,
            start_time=_time_str(start_time),
            end_time=_time_str(end_time),
            site_key=planned.get("site_key"),
        )
        if seasonal.get("denied"):
            return {"error": "seasonal_policy_block", "seasonal": seasonal}
        if seasonal.get("requires_ack") and not (action.get("acknowledge_seasonal") or action.get("ack_seasonal")):
            return {"error": "seasonal_policy_requires_ack", "seasonal": seasonal, "needs_confirmation": True}
    return None


def classify_occurrence(
    cur: Any,
    *,
    company_code: str,
    planned: dict[str, Any],
    action_acks: dict[str, Any] | None = None,
    overlap_checker: Any = None,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    existing = _find_existing_by_occurrence(cur, company_code=company, occurrence_key_value=planned["occurrence_key"])
    if not existing:
        existing = _find_existing_by_idempotency(cur, company_code=company, idem=planned["idempotency_key"])

    out = dict(planned)
    out.pop("employee", None)

    if existing:
        status = str(existing.get("status") or "")
        out["existing_shift_id"] = str(existing.get("shift_id"))
        out["existing_updated_at"] = str(existing.get("updated_at") or "")
        if status == "cancelled":
            out["class"] = "cancelled_held"
            return out
        if bool(existing.get("regen_detached")):
            out["class"] = "detached"
            return out
        if str(existing.get("source_kind") or "manual") != "template_recurrence":
            out["class"] = "detached"
            return out
        if _windows_match(existing, planned) and str(existing.get("generated_from_version") or "") == str(
            planned.get("generated_from_version") or ""
        ):
            out["class"] = "unchanged"
            return out
        sd = _as_date(existing.get("shift_date"))
        if sd and sd > date.today() and status == "scheduled":
            out["class"] = "updated_future"
            return out
        out["class"] = "detached"
        return out

    conflict = evaluate_planned_conflicts(cur, company_code=company, planned=planned, action_acks=action_acks)
    if conflict:
        out["class"] = "conflict"
        out["conflict"] = conflict
        return out
    if overlap_checker:
        try:
            overlaps = overlap_checker(planned)
            if overlaps:
                out["class"] = "conflict"
                out["conflict"] = {"error": "overlap", "overlaps": overlaps}
                return out
        except Exception as exc:  # noqa: BLE001
            out["class"] = "conflict"
            out["conflict"] = {"error": "overlap_check_failed", "detail": str(exc)[:200]}
            return out
    out["class"] = "newly_generated"
    return out


def preview_recurrence(
    cur: Any,
    *,
    company_code: str,
    recurrence_id: Any,
    action_acks: dict[str, Any] | None = None,
    overlap_checker: Any = None,
    sample_limit: int = 40,
) -> dict[str, Any]:
    ensure_shifts_templates_wave4_schema(cur)
    if not shifts_wave4_enabled_for_company(company_code):
        return {"ok": False, "error": "shifts_wave4_disabled", **honesty_payload()}
    rec = get_recurrence(cur, company_code=company_code, recurrence_id=recurrence_id)
    if not rec:
        return {"ok": False, "error": "recurrence_not_found"}
    built = build_planned_occurrences(cur, company_code=company_code, recurrence=rec)
    counts = {
        "unchanged": 0,
        "newly_generated": 0,
        "updated_future": 0,
        "conflict": 0,
        "detached": 0,
        "cancelled_held": 0,
    }
    samples: list[dict[str, Any]] = []
    classified: list[dict[str, Any]] = []
    for planned in built.get("occurrences") or []:
        row = classify_occurrence(
            cur,
            company_code=company_code,
            planned=planned,
            action_acks=action_acks,
            overlap_checker=overlap_checker,
        )
        cls = str(row.get("class") or "conflict")
        counts[cls] = counts.get(cls, 0) + 1
        classified.append(row)
        if len(samples) < sample_limit:
            samples.append(row)
    return {
        "ok": True,
        "recurrence_id": str(recurrence_id),
        "counts": counts,
        "total": sum(counts.values()),
        "window": built.get("window"),
        "samples": samples,
        "classified": classified,
        "skipped": built.get("skipped"),
        "skipped_target": built.get("skipped_target"),
        **honesty_payload(),
    }


def materialize_recurrence(
    cur: Any,
    *,
    company_code: str,
    recurrence_id: Any,
    create_fn: Any,
    reschedule_fn: Any | None = None,
    action_acks: dict[str, Any] | None = None,
    overlap_checker: Any = None,
    actor_phone: str | None = None,
) -> dict[str, Any]:
    """Bounded materialize under advisory lock. create_fn/reschedule_fn injected from app."""
    ensure_shifts_templates_wave4_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave4_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave4_disabled", **honesty_payload()}
    rec = get_recurrence(cur, company_code=company, recurrence_id=recurrence_id)
    if not rec:
        return {"ok": False, "error": "recurrence_not_found"}
    if str(rec.get("status")) != "active":
        return {"ok": False, "error": "recurrence_not_active", "status": rec.get("status"), **honesty_payload()}

    lock_key = materialize_lock_key(company, recurrence_id)
    if not w2.try_job_lock(cur, lock_key):
        return {"ok": False, "error": "materialize_lock_held", "recurrence_id": str(recurrence_id), **honesty_payload()}

    results = {
        "unchanged": 0,
        "newly_generated": 0,
        "updated_future": 0,
        "conflict": 0,
        "detached": 0,
        "cancelled_held": 0,
        "created_ids": [],
        "updated_ids": [],
        "conflicts": [],
    }
    try:
        preview = preview_recurrence(
            cur,
            company_code=company,
            recurrence_id=recurrence_id,
            action_acks=action_acks,
            overlap_checker=overlap_checker,
            sample_limit=10_000,
        )
        if not preview.get("ok"):
            return preview
        for row in preview.get("classified") or []:
            cls = str(row.get("class"))
            if cls == "unchanged":
                results["unchanged"] += 1
                continue
            if cls in {"detached", "cancelled_held"}:
                results[cls] += 1
                continue
            if cls == "conflict":
                results["conflict"] += 1
                results["conflicts"].append(row)
                continue
            if cls == "newly_generated":
                action = {
                    "employee_key": row.get("employee_key"),
                    "employee_name": row.get("employee_name"),
                    "employee_phone": row.get("employee_phone"),
                    "date": row.get("shift_date"),
                    "shift_date": row.get("shift_date"),
                    "start_time": row.get("start_time"),
                    "end_time": row.get("end_time"),
                    "break_minutes": row.get("break_minutes"),
                    "role": row.get("role"),
                    "site_key": row.get("site_key"),
                    "branch_key": row.get("branch_key"),
                    "team_key": row.get("team_key"),
                    "position_key": row.get("position_key"),
                    "location": row.get("location"),
                    "timezone": row.get("timezone"),
                    "idempotency_key": row.get("idempotency_key"),
                    "reason": f"wave4 materialize {recurrence_id}",
                    "source_kind": "template_recurrence",
                    "template_id": row.get("template_id"),
                    "recurrence_id": row.get("recurrence_id"),
                    "occurrence_key": row.get("occurrence_key"),
                    "generated_from_version": row.get("generated_from_version"),
                    **(action_acks or {}),
                }
                created = create_fn(action, company_code=company, created_by_phone=actor_phone)
                if created.get("ok"):
                    results["newly_generated"] += 1
                    sid = None
                    for c in created.get("created") or []:
                        sid = str(c.get("shift_id") or "")
                    if sid:
                        results["created_ids"].append(sid)
                        _stamp_provenance(
                            cur,
                            company_code=company,
                            shift_id=sid,
                            template_id=row.get("template_id"),
                            recurrence_id=row.get("recurrence_id"),
                            occurrence_key=row.get("occurrence_key"),
                            generated_from_version=row.get("generated_from_version"),
                        )
                else:
                    results["conflict"] += 1
                    results["conflicts"].append({"class": "conflict", "create_result": created, **row})
                continue
            if cls == "updated_future" and reschedule_fn:
                rs = reschedule_fn(
                    {
                        "shift_id": row.get("existing_shift_id"),
                        "date": row.get("shift_date"),
                        "shift_date": row.get("shift_date"),
                        "start_time": row.get("start_time"),
                        "end_time": row.get("end_time"),
                        "expected_updated_at": row.get("existing_updated_at"),
                        "reason": f"wave4 regen {recurrence_id}",
                        "reason_code": "template_regen",
                    },
                    company_code=company,
                    created_by_phone=actor_phone,
                )
                if rs.get("ok"):
                    results["updated_future"] += 1
                    results["updated_ids"].append(str(row.get("existing_shift_id")))
                    _stamp_provenance(
                        cur,
                        company_code=company,
                        shift_id=str(row.get("existing_shift_id")),
                        template_id=row.get("template_id"),
                        recurrence_id=row.get("recurrence_id"),
                        occurrence_key=row.get("occurrence_key"),
                        generated_from_version=row.get("generated_from_version"),
                    )
                else:
                    results["conflict"] += 1
                    results["conflicts"].append({"class": "conflict", "reschedule_result": rs, **row})
                continue
            results[cls] = results.get(cls, 0) + 1

        _record_recurrence_event(
            cur,
            company_code=company,
            recurrence_id=recurrence_id,
            event_type="materialized",
            payload={"results": {k: v for k, v in results.items() if k not in {"conflicts", "created_ids", "updated_ids"}}, "counts_preview": preview.get("counts")},
            actor_phone=actor_phone,
        )
        return {"ok": True, "recurrence_id": str(recurrence_id), "results": results, "preview_counts": preview.get("counts"), **honesty_payload()}
    finally:
        w2.release_job_lock(cur, lock_key)


def _stamp_provenance(
    cur: Any,
    *,
    company_code: str,
    shift_id: str,
    template_id: Any,
    recurrence_id: Any,
    occurrence_key: str,
    generated_from_version: str,
) -> None:
    cur.execute(
        """
        UPDATE shift_assignments SET
          source_kind='template_recurrence',
          template_id=%s,
          recurrence_id=%s,
          occurrence_key=%s,
          regen_detached=false,
          generated_from_version=%s,
          updated_at=now()
        WHERE company_code=%s AND shift_id=%s
        """,
        (
            str(template_id) if template_id else None,
            str(recurrence_id) if recurrence_id else None,
            occurrence_key,
            generated_from_version,
            (company_code or "").upper(),
            shift_id,
        ),
    )


def mark_assignment_detached(cur: Any, *, company_code: str, shift_id: Any) -> None:
    """Call after manual reschedule/cancel of a generated assignment."""
    try:
        cur.execute(
            """
            UPDATE shift_assignments SET regen_detached=true, updated_at=now()
            WHERE company_code=%s AND shift_id=%s
              AND source_kind='template_recurrence'
            """,
            ((company_code or "").upper(), str(shift_id)),
        )
    except Exception:
        pass
