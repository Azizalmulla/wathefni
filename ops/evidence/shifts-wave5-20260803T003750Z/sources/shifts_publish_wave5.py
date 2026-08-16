#!/usr/bin/env python3
"""Shifts Wave 5 — draft / review / publish, open shifts, coverage (local/staging).

Planning layer above templates/recurrences. Drafts never write operational L0.
Only published schedule versions promote to shift_assignments.

Does NOT: production deploy, real employee enablement, real reminders/timers,
advanced rotations, remote hitches, PAM export, Payroll money, Leave balance
mutation, Attendance authority mutation.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import shifts_authority_wave1 as w1
import shifts_schedule_integrity_wave2 as w2
import shifts_templates_wave4 as w4

SHIFTS_WAVE5_VERSION = "5.0.0"
_ON = {"1", "true", "yes", "on"}

DEFAULT_W5_SYNTHETIC_KEY_MARKERS = ("SHW5", "SHW5-SYNTH|")
DEFAULT_W5_SYNTHETIC_PHONE_PREFIXES = ("965534",)

PERIOD_STATES = ("draft", "in_review", "approved", "published", "superseded", "cancelled")
VERSION_STATES = PERIOD_STATES
OPEN_STATUSES = ("open", "claimed", "approved", "rejected", "assigned", "cancelled")
CLAIM_STATUSES = ("pending", "approved", "rejected", "withdrawn")
COVERAGE_CLASSES = ("covered", "understaffed", "overstaffed", "unresolved_open_shift", "unavailable_employee")

JOB_LOCK_PUBLISH_BASE = 750_500_001

SCHEMA_SQL = (Path(__file__).resolve().parent / "ops" / "sql" / "shifts_publish_wave5_v1.sql").read_text(encoding="utf-8")


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


def _row(cur: Any) -> dict[str, Any] | None:
    r = cur.fetchone()
    return dict(r) if r else None


def _rows(cur: Any) -> list[dict[str, Any]]:
    return [dict(r) for r in cur.fetchall()]


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (date, datetime, time, UUID)):
        return str(obj)
    return obj


def shifts_wave5_enabled() -> bool:
    raw = os.environ.get("WATHEFNI_SHIFTS_WAVE5")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON


def shifts_wave5_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE5_COMPANIES") or "WATHEFNI").strip()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def shifts_wave5_enabled_for_company(company_code: str | None) -> bool:
    if not shifts_wave5_enabled():
        return False
    companies = shifts_wave5_companies()
    return bool(companies) and (company_code or "").upper() in companies


def shifts_wave5_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() == "production"
    return str(raw).strip().lower() in _ON


def wave5_synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return DEFAULT_W5_SYNTHETIC_KEY_MARKERS


def wave5_synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return DEFAULT_W5_SYNTHETIC_PHONE_PREFIXES


def is_wave5_synthetic_employee(
    *,
    employee_key: Any = None,
    phone: Any = None,
    name: Any = None,
    employee: dict[str, Any] | None = None,
) -> bool:
    key = str(employee_key or (employee or {}).get("employee_key") or "")
    phone_d = _digits(phone or (employee or {}).get("phone") or (employee or {}).get("employee_phone"))
    nm = str(name or (employee or {}).get("name") or "")
    for marker in wave5_synthetic_key_markers():
        if marker and (marker in key or marker in nm):
            return True
    for prefix in wave5_synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    raw = (employee or {}).get("raw_json") if isinstance(employee, dict) else None
    if isinstance(raw, dict) and (raw.get("shw5") is True or str(raw.get("shw5") or "").lower() in _ON):
        return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "shifts_wave5_version": SHIFTS_WAVE5_VERSION,
        "payroll_money": False,
        "leave_balances_mutated": False,
        "attendance_authority_mutated": False,
        "templates": True,
        "recurring_schedules": True,
        "rotations": False,
        "publishing": True,
        "open_shifts": True,
        "pam_export": False,
        "draft_publish": True,
        "coverage_rules": True,
        "require_publish_optional": True,
        "complexity_levels": {
            "simple": "manual_l0_publish_optional",
            "medium": "draft_review_publish_open_coverage",
            "enterprise_later": "advanced_rotations_remote_hitches",
        },
        "wave5_synthetic_markers": {
            "key_markers": list(wave5_synthetic_key_markers()),
            "phone_prefixes": list(wave5_synthetic_phone_prefixes()),
        },
    }


def ensure_shifts_publish_wave5_schema(cur: Any) -> None:
    lock_id = JOB_LOCK_PUBLISH_BASE - 7
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute(SCHEMA_SQL)
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


def publish_lock_key(company_code: str, period_id: Any) -> int:
    raw = f"{(company_code or '').upper()}|{period_id}"
    digest = hashlib.md5(raw.encode()).hexdigest()
    return JOB_LOCK_PUBLISH_BASE + (int(digest[:8], 16) % 1_000_000)


def _record_event(
    cur: Any,
    *,
    company_code: str,
    period_id: Any = None,
    version_id: Any = None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    actor_phone: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO shift_schedule_events (company_code, period_id, version_id, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            str(period_id) if period_id else None,
            str(version_id) if version_id else None,
            event_type,
            json.dumps(_jsonable(payload or {})),
            _digits(actor_phone) or None,
        ),
    )


# --- Period / version CRUD ----------------------------------------------------

def create_period(cur: Any, *, company_code: str, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave5_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave5_disabled", **honesty_payload()}
    start = _as_date(payload.get("start_date"))
    end = _as_date(payload.get("end_date"))
    name = str(payload.get("name") or "").strip()
    if not start or not end or end < start or len(name) < 2:
        return {"ok": False, "error": "invalid_period"}
    require_publish = payload.get("require_publish")
    if require_publish is None:
        require_publish = True
    cur.execute(
        """
        INSERT INTO shift_schedule_periods (
          company_code, name, status, start_date, end_date, timezone,
          site_key, branch_key, team_key, require_publish, created_by_phone, updated_by_phone
        ) VALUES (%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            name,
            start,
            end,
            str(payload.get("timezone") or "Asia/Kuwait"),
            str(payload.get("site_key") or "").strip() or None,
            str(payload.get("branch_key") or "").strip() or None,
            str(payload.get("team_key") or "").strip() or None,
            bool(require_publish),
            _digits(actor_phone) or None,
            _digits(actor_phone) or None,
        ),
    )
    period = _row(cur)
    # Seed version 1 draft
    cur.execute(
        """
        INSERT INTO shift_schedule_versions (
          company_code, period_id, version_no, state, created_by_phone, updated_by_phone
        ) VALUES (%s,%s,1,'draft',%s,%s)
        RETURNING *
        """,
        (company, period["period_id"], _digits(actor_phone) or None, _digits(actor_phone) or None),
    )
    version = _row(cur)
    _record_event(
        cur,
        company_code=company,
        period_id=period["period_id"],
        version_id=version["version_id"],
        event_type="period_created",
        payload={"period": period, "version": version},
        actor_phone=actor_phone,
    )
    return {"ok": True, "period": period, "version": version, **honesty_payload()}


def get_period(cur: Any, *, company_code: str, period_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_schedule_periods WHERE company_code=%s AND period_id=%s",
        ((company_code or "").upper(), str(period_id)),
    )
    return _row(cur)


def list_periods(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM shift_schedule_periods
        WHERE company_code=%s
        ORDER BY start_date DESC, created_at DESC
        LIMIT 200
        """,
        ((company_code or "").upper(),),
    )
    return _rows(cur)


def get_version(cur: Any, *, company_code: str, version_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_schedule_versions WHERE company_code=%s AND version_id=%s",
        ((company_code or "").upper(), str(version_id)),
    )
    return _row(cur)


def list_versions(cur: Any, *, company_code: str, period_id: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM shift_schedule_versions
        WHERE company_code=%s AND period_id=%s
        ORDER BY version_no DESC
        """,
        ((company_code or "").upper(), str(period_id)),
    )
    return _rows(cur)


def _latest_editable_version(cur: Any, *, company_code: str, period_id: Any) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM shift_schedule_versions
        WHERE company_code=%s AND period_id=%s AND state IN ('draft','in_review','approved')
        ORDER BY version_no DESC LIMIT 1
        """,
        ((company_code or "").upper(), str(period_id)),
    )
    return _row(cur)


def _next_version_no(cur: Any, *, period_id: Any) -> int:
    cur.execute("SELECT coalesce(max(version_no),0)+1 AS n FROM shift_schedule_versions WHERE period_id=%s", (str(period_id),))
    return int(dict(cur.fetchone())["n"])


# --- Draft generation from Wave 4 --------------------------------------------

def generate_draft_from_recurrence(
    cur: Any,
    *,
    company_code: str,
    period_id: Any,
    recurrence_id: Any,
    actor_phone: str | None = None,
    action_acks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Expand Wave 4 recurrence into draft rows only — never writes L0."""
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave5_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave5_disabled", **honesty_payload()}
    period = get_period(cur, company_code=company, period_id=period_id)
    if not period or str(period.get("status")) in {"cancelled", "superseded"}:
        return {"ok": False, "error": "period_not_editable"}
    version = _latest_editable_version(cur, company_code=company, period_id=period_id)
    if not version or str(version.get("state")) not in {"draft", "in_review"}:
        return {"ok": False, "error": "no_editable_draft_version", "hint": "create a new draft from published first"}
    if str(version.get("state")) == "in_review":
        return {"ok": False, "error": "version_locked_in_review"}

    w4.ensure_shifts_templates_wave4_schema(cur)
    rec = w4.get_recurrence(cur, company_code=company, recurrence_id=recurrence_id)
    if not rec:
        return {"ok": False, "error": "recurrence_not_found"}

    # Temporarily align expansion window to period dates via preview classifier path
    built = w4.build_planned_occurrences(cur, company_code=company, recurrence=rec, today=_as_date(period["start_date"]) - timedelta(days=1), force_include_today=True)
    # Filter to period window
    p_start = _as_date(period["start_date"])
    p_end = _as_date(period["end_date"])
    planned = []
    for occ in built.get("occurrences") or []:
        d = _as_date(occ.get("shift_date"))
        if d and p_start and p_end and p_start <= d <= p_end:
            planned.append(occ)

    # Clear existing draft rows for this version (regen)
    cur.execute("DELETE FROM shift_schedule_draft_rows WHERE version_id=%s", (version["version_id"],))
    inserted = 0
    for occ in planned:
        classified = w4.classify_occurrence(cur, company_code=company, planned=occ, action_acks=action_acks)
        cur.execute(
            """
            INSERT INTO shift_schedule_draft_rows (
              company_code, period_id, version_id, employee_key, employee_name, employee_phone,
              shift_date, start_time, end_time, ends_next_day, role, site_key, branch_key, team_key,
              location, timezone, template_id, recurrence_id, occurrence_key, source_kind, row_class, conflict_payload
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'template_recurrence',%s,%s::jsonb)
            """,
            (
                company,
                period["period_id"],
                version["version_id"],
                classified.get("employee_key"),
                classified.get("employee_name"),
                classified.get("employee_phone"),
                _as_date(classified.get("shift_date")),
                _as_time(classified.get("start_time")),
                _as_time(classified.get("end_time")),
                bool(classified.get("ends_next_day")),
                classified.get("role"),
                classified.get("site_key"),
                classified.get("branch_key"),
                classified.get("team_key"),
                classified.get("location"),
                classified.get("timezone") or "Asia/Kuwait",
                classified.get("template_id"),
                classified.get("recurrence_id"),
                classified.get("occurrence_key"),
                classified.get("class"),
                json.dumps(_jsonable(classified.get("conflict") or {})),
            ),
        )
        inserted += 1

    coverage = evaluate_coverage_for_version(cur, company_code=company, version_id=version["version_id"], period=period)
    fp = hashlib.sha256(json.dumps({"n": inserted, "cov": coverage.get("summary")}, sort_keys=True, default=str).encode()).hexdigest()[:24]
    cur.execute(
        """
        UPDATE shift_schedule_versions SET
          fingerprint=%s, draft_payload=%s::jsonb, coverage_snapshot=%s::jsonb,
          updated_by_phone=%s, updated_at=now()
        WHERE version_id=%s
        RETURNING *
        """,
        (
            fp,
            json.dumps({"recurrence_id": str(recurrence_id), "inserted": inserted}),
            json.dumps(_jsonable(coverage)),
            _digits(actor_phone) or None,
            version["version_id"],
        ),
    )
    version = _row(cur)
    _record_event(
        cur,
        company_code=company,
        period_id=period_id,
        version_id=version["version_id"],
        event_type="draft_generated",
        payload={"inserted": inserted, "recurrence_id": str(recurrence_id)},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "period_id": str(period_id),
        "version": version,
        "draft_rows": inserted,
        "coverage": coverage,
        "l0_written": False,
        **honesty_payload(),
    }


def list_draft_rows(cur: Any, *, company_code: str, version_id: Any) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM shift_schedule_draft_rows
        WHERE company_code=%s AND version_id=%s
        ORDER BY shift_date, start_time, employee_key
        """,
        ((company_code or "").upper(), str(version_id)),
    )
    return _rows(cur)


def resolve_draft_conflicts(
    cur: Any,
    *,
    company_code: str,
    version_id: Any,
    resolutions: list[dict[str, Any]],
    actor_phone: str | None = None,
) -> dict[str, Any]:
    """Bulk acknowledge (force include) or cancel conflict draft rows before publish."""
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    version = get_version(cur, company_code=company, version_id=version_id)
    if not version or str(version.get("state")) not in {"draft", "in_review", "approved"}:
        return {"ok": False, "error": "version_not_editable"}
    acknowledged = 0
    cancelled = 0
    for item in resolutions or []:
        rid = str(item.get("draft_row_id") or "")
        action = str(item.get("action") or "").lower()
        if not rid or action not in {"acknowledge", "cancel"}:
            continue
        if action == "acknowledge":
            cur.execute(
                """
                UPDATE shift_schedule_draft_rows
                SET row_class='ready', conflict_payload = conflict_payload || '{"acknowledged":true}'::jsonb
                WHERE company_code=%s AND version_id=%s AND draft_row_id=%s
                  AND row_class IN ('conflict','cancelled_held')
                """,
                (company, version_id, rid),
            )
            acknowledged += cur.rowcount
        else:
            cur.execute(
                """
                UPDATE shift_schedule_draft_rows
                SET row_class='cancelled_held', conflict_payload = conflict_payload || '{"bulk_cancelled":true}'::jsonb
                WHERE company_code=%s AND version_id=%s AND draft_row_id=%s
                """,
                (company, version_id, rid),
            )
            cancelled += cur.rowcount
    _record_event(
        cur,
        company_code=company,
        period_id=version.get("period_id"),
        version_id=version_id,
        event_type="draft_conflicts_resolved",
        payload={"acknowledged": acknowledged, "cancelled": cancelled},
        actor_phone=actor_phone,
    )
    return {"ok": True, "acknowledged": acknowledged, "cancelled": cancelled, **honesty_payload()}


# --- State machine ------------------------------------------------------------

_ALLOWED_TRANSITIONS = {
    "draft": {"in_review", "cancelled"},
    "in_review": {"approved", "draft", "cancelled"},
    "approved": {"published", "draft", "cancelled"},
    "published": set(),  # immutable; new draft created instead
    "superseded": set(),
    "cancelled": set(),
}


def transition_version(
    cur: Any,
    *,
    company_code: str,
    version_id: Any,
    to_state: str,
    actor_phone: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    version = get_version(cur, company_code=company, version_id=version_id)
    if not version:
        return {"ok": False, "error": "version_not_found"}
    current = str(version.get("state"))
    target = str(to_state)
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        return {"ok": False, "error": "invalid_transition", "from": current, "to": target}
    if target == "published":
        return {"ok": False, "error": "use_publish_endpoint"}

    fields = ["state=%s", "updated_by_phone=%s", "updated_at=now()"]
    params: list[Any] = [target, _digits(actor_phone) or None]
    if target == "in_review":
        fields.append("submitted_at=now()")
    if target == "approved":
        fields.append("approved_at=now()")
    cur.execute(
        f"UPDATE shift_schedule_versions SET {', '.join(fields)} WHERE version_id=%s RETURNING *",
        (*params, version_id),
    )
    version = _row(cur)
    # Mirror period status for active planning states
    if target in {"draft", "in_review", "approved", "cancelled"}:
        cur.execute(
            "UPDATE shift_schedule_periods SET status=%s, updated_at=now(), updated_by_phone=%s WHERE period_id=%s",
            (target if target != "approved" else "approved", _digits(actor_phone) or None, version["period_id"]),
        )
    _record_event(
        cur,
        company_code=company,
        period_id=version["period_id"],
        version_id=version_id,
        event_type=f"version_{target}",
        payload={"from": current, "to": target, "note": note},
        actor_phone=actor_phone,
    )
    return {"ok": True, "version": version, **honesty_payload()}


def review_diff(
    cur: Any,
    *,
    company_code: str,
    version_id: Any,
) -> dict[str, Any]:
    """Diff proposed draft vs currently published L0 for the period."""
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    version = get_version(cur, company_code=company, version_id=version_id)
    if not version:
        return {"ok": False, "error": "version_not_found"}
    period = get_period(cur, company_code=company, period_id=version["period_id"])
    draft = list_draft_rows(cur, company_code=company, version_id=version_id)
    published_version_id = period.get("published_version_id") if period else None
    published_rows: list[dict[str, Any]] = []
    if published_version_id:
        cur.execute(
            """
            SELECT shift_id::text, employee_key, shift_date::text, start_time::text, end_time::text,
                   ends_next_day, status, occurrence_key, schedule_version_id::text
            FROM shift_assignments
            WHERE company_code=%s AND schedule_period_id=%s AND schedule_version_id=%s
              AND status <> 'cancelled'
            """,
            (company, version["period_id"], published_version_id),
        )
        published_rows = _rows(cur)

    def _key(r: dict[str, Any]) -> str:
        return "|".join(
            [
                str(r.get("employee_key") or ""),
                str(r.get("shift_date") or "")[:10],
                _time_str(r.get("start_time")),
                _time_str(r.get("end_time")),
            ]
        )

    draft_map = {_key(r): r for r in draft}
    pub_map = {_key(r): r for r in published_rows}
    added = [draft_map[k] for k in draft_map.keys() - pub_map.keys()]
    removed = [pub_map[k] for k in pub_map.keys() - draft_map.keys()]
    changed = []
    for k in draft_map.keys() & pub_map.keys():
        d, p = draft_map[k], pub_map[k]
        if bool(d.get("ends_next_day")) != bool(p.get("ends_next_day")) or str(d.get("role") or "") != str(p.get("role") or ""):
            changed.append({"draft": d, "published": p})
    diff = {
        "added": len(added),
        "removed": len(removed),
        "changed": len(changed),
        "samples": {"added": _jsonable(added[:10]), "removed": _jsonable(removed[:10]), "changed": _jsonable(changed[:10])},
    }
    cur.execute(
        "UPDATE shift_schedule_versions SET review_diff=%s::jsonb, updated_at=now() WHERE version_id=%s",
        (json.dumps(diff), version_id),
    )
    return {"ok": True, "diff": diff, "draft_count": len(draft), "published_count": len(published_rows), **honesty_payload()}


# --- Publish / rollback -------------------------------------------------------

def _is_locked_assignment(row: dict[str, Any], *, today: date) -> bool:
    """Historical or already-started (shift_date < today, or today without force)."""
    sd = _as_date(row.get("shift_date"))
    if not sd:
        return True
    return sd < today


def publish_version(
    cur: Any,
    *,
    company_code: str,
    version_id: Any,
    create_fn: Any,
    actor_phone: str | None = None,
    expected_row_version: int | None = None,
    publish_idempotency_key: str | None = None,
    action_acks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Promote approved/draft-approved version to L0 under advisory lock."""
    company = (company_code or "").upper()
    version = get_version(cur, company_code=company, version_id=version_id)
    if not version:
        return {"ok": False, "error": "version_not_found", **honesty_payload()}
    period = get_period(cur, company_code=company, period_id=version["period_id"])
    if not period:
        return {"ok": False, "error": "period_not_found", **honesty_payload()}

    lock_key = publish_lock_key(company, period["period_id"])
    if not w2.try_job_lock(cur, lock_key):
        return {"ok": False, "error": "publish_lock_held", **honesty_payload()}

    results = {"created": 0, "skipped_locked": 0, "conflicts": 0, "created_ids": [], "conflict_rows": []}
    try:
        ensure_shifts_publish_wave5_schema(cur)
        version = get_version(cur, company_code=company, version_id=version_id)
        period = get_period(cur, company_code=company, period_id=version["period_id"])
        if str(version.get("state")) == "published":
            # Idempotent replay
            return {"ok": True, "idempotent": True, "version": version, "results": results, **honesty_payload()}
        if str(version.get("state")) != "approved":
            return {"ok": False, "error": "version_not_approved", "state": version.get("state"), **honesty_payload()}

        if expected_row_version is not None and int(period.get("row_version") or 0) != int(expected_row_version):
            return {"ok": False, "error": "stale_period", "expected": expected_row_version, "actual": period.get("row_version"), **honesty_payload()}

        idem = str(publish_idempotency_key or "").strip() or None
        if idem:
            cur.execute(
                "SELECT * FROM shift_schedule_versions WHERE company_code=%s AND publish_idempotency_key=%s LIMIT 1",
                (company, idem),
            )
            existing_idem = _row(cur)
            if existing_idem and str(existing_idem.get("version_id")) != str(version_id):
                return {"ok": False, "error": "publish_idempotency_conflict", **honesty_payload()}
            if existing_idem and str(existing_idem.get("state")) == "published":
                return {"ok": True, "idempotent": True, "version": existing_idem, **honesty_payload()}

        coverage = evaluate_coverage_for_version(cur, company_code=company, version_id=version_id, period=period)
        if coverage.get("blocks_publish"):
            return {"ok": False, "error": "coverage_block", "coverage": coverage, **honesty_payload()}

        # Release relation locks before sibling create_fn DDL (Wave 4 deadlock pattern)
        try:
            cur.connection.commit()
        except Exception:
            pass

        today = date.today()
        draft = list_draft_rows(cur, company_code=company, version_id=version_id)
        prev_published = period.get("published_version_id")

        for row in draft:
            if str(row.get("row_class")) in {"conflict", "cancelled_held", "detached"}:
                results["conflicts"] += 1
                results["conflict_rows"].append(row)
                continue
            if _is_locked_assignment(row, today=today):
                results["skipped_locked"] += 1
                continue
            # Already-materialized unchanged rows (clone/rollback) — retain, do not duplicate
            if row.get("published_shift_id") and str(row.get("row_class") or "") in {"", "unchanged", "ready"}:
                # Verify L0 still exists and is active
                cur.execute(
                    "SELECT shift_id FROM shift_assignments WHERE shift_id=%s AND status <> 'cancelled'",
                    (row["published_shift_id"],),
                )
                if cur.fetchone():
                    # Retarget provenance to this published version without recreating
                    cur.execute(
                        """
                        UPDATE shift_assignments SET
                          schedule_period_id=%s, schedule_version_id=%s, schedule_source='published',
                          updated_at=now()
                        WHERE shift_id=%s
                        """,
                        (period["period_id"], version_id, row["published_shift_id"]),
                    )
                    results["created"] += 1
                    results["created_ids"].append(str(row["published_shift_id"]))
                    try:
                        cur.connection.commit()
                    except Exception:
                        pass
                    continue
            action = {
                "employee_key": row.get("employee_key"),
                "employee_name": row.get("employee_name"),
                "employee_phone": row.get("employee_phone"),
                "date": str(row.get("shift_date"))[:10],
                "shift_date": str(row.get("shift_date"))[:10],
                "start_time": _time_str(row.get("start_time")),
                "end_time": _time_str(row.get("end_time")),
                "role": row.get("role"),
                "site_key": row.get("site_key"),
                "branch_key": row.get("branch_key"),
                "team_key": row.get("team_key"),
                "location": row.get("location"),
                "timezone": row.get("timezone") or "Asia/Kuwait",
                "idempotency_key": f"SHW5|{company}|{version_id}|{row.get('occurrence_key') or row.get('draft_row_id')}",
                "reason": f"wave5 publish {version_id}",
                "source_kind": "template_recurrence" if row.get("recurrence_id") else "manual",
                "template_id": row.get("template_id"),
                "recurrence_id": row.get("recurrence_id"),
                "occurrence_key": row.get("occurrence_key"),
                **(action_acks or {}),
            }
            # Commit before create_fn so DDL/schema ensure cannot deadlock with this txn
            try:
                cur.connection.commit()
            except Exception:
                pass
            created = create_fn(action, company_code=company, created_by_phone=actor_phone)
            if created.get("ok"):
                sid = None
                for c in created.get("created") or []:
                    sid = str(c.get("shift_id") or "")
                if sid:
                    results["created"] += 1
                    results["created_ids"].append(sid)
                    cur.execute(
                        """
                        UPDATE shift_assignments SET
                          schedule_period_id=%s, schedule_version_id=%s, schedule_source='published',
                          updated_at=now()
                        WHERE shift_id=%s
                        """,
                        (period["period_id"], version_id, sid),
                    )
                    cur.execute(
                        "UPDATE shift_schedule_draft_rows SET published_shift_id=%s WHERE draft_row_id=%s",
                        (sid, row["draft_row_id"]),
                    )
                    try:
                        cur.connection.commit()
                    except Exception:
                        pass
            else:
                results["conflicts"] += 1
                results["conflict_rows"].append({"draft": row, "create_result": created})

        # Supersede previous published version (non-destructive)
        if prev_published and str(prev_published) != str(version_id):
            cur.execute(
                "UPDATE shift_schedule_versions SET state='superseded', updated_at=now() WHERE version_id=%s AND state='published'",
                (prev_published,),
            )

        cur.execute(
            """
            UPDATE shift_schedule_versions SET
              state='published', published_at=now(), publish_idempotency_key=coalesce(%s, publish_idempotency_key),
              coverage_snapshot=%s::jsonb, updated_by_phone=%s, updated_at=now()
            WHERE version_id=%s
            RETURNING *
            """,
            (idem, json.dumps(_jsonable(coverage)), _digits(actor_phone) or None, version_id),
        )
        version = _row(cur)
        cur.execute(
            """
            UPDATE shift_schedule_periods SET
              status='published', published_version_id=%s, row_version=row_version+1,
              updated_by_phone=%s, updated_at=now()
            WHERE period_id=%s
            RETURNING *
            """,
            (version_id, _digits(actor_phone) or None, period["period_id"]),
        )
        period = _row(cur)
        _record_event(
            cur,
            company_code=company,
            period_id=period["period_id"],
            version_id=version_id,
            event_type="published",
            payload={"results": {k: v for k, v in results.items() if k != "conflict_rows"}, "coverage_summary": coverage.get("summary")},
            actor_phone=actor_phone,
        )
        return {"ok": True, "version": version, "period": period, "results": results, "coverage": coverage, **honesty_payload()}
    finally:
        w2.release_job_lock(cur, lock_key)


def create_draft_from_published(
    cur: Any,
    *,
    company_code: str,
    period_id: Any,
    actor_phone: str | None = None,
    rollback_of_version_id: Any = None,
) -> dict[str, Any]:
    """New editable draft version cloned from published (or explicit rollback target)."""
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    period = get_period(cur, company_code=company, period_id=period_id)
    if not period:
        return {"ok": False, "error": "period_not_found"}
    source_id = rollback_of_version_id or period.get("published_version_id")
    if not source_id:
        return {"ok": False, "error": "no_published_version"}
    source = get_version(cur, company_code=company, version_id=source_id)
    if not source:
        return {"ok": False, "error": "source_version_not_found"}

    n = _next_version_no(cur, period_id=period_id)
    cur.execute(
        """
        INSERT INTO shift_schedule_versions (
          company_code, period_id, version_no, state, based_on_version_id, rollback_of_version_id,
          created_by_phone, updated_by_phone
        ) VALUES (%s,%s,%s,'draft',%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            period_id,
            n,
            source_id,
            str(rollback_of_version_id) if rollback_of_version_id else None,
            _digits(actor_phone) or None,
            _digits(actor_phone) or None,
        ),
    )
    version = _row(cur)

    # Clone published L0 (or source draft rows) into new draft — no L0 mutation
    if rollback_of_version_id or str(source.get("state")) == "published":
        cur.execute(
            """
            SELECT * FROM shift_assignments
            WHERE company_code=%s AND schedule_period_id=%s AND schedule_version_id=%s
              AND status <> 'cancelled'
            """,
            (company, period_id, source_id),
        )
        for a in _rows(cur):
            cur.execute(
                """
                INSERT INTO shift_schedule_draft_rows (
                  company_code, period_id, version_id, employee_key, employee_name, employee_phone,
                  shift_date, start_time, end_time, ends_next_day, role, site_key, branch_key, team_key,
                  location, timezone, template_id, recurrence_id, occurrence_key, source_kind, row_class, published_shift_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'unchanged',%s)
                """,
                (
                    company,
                    period_id,
                    version["version_id"],
                    a.get("employee_key"),
                    a.get("employee_name"),
                    a.get("employee_phone"),
                    a.get("shift_date"),
                    a.get("start_time"),
                    a.get("end_time"),
                    bool(a.get("ends_next_day")),
                    a.get("role"),
                    a.get("site_key"),
                    a.get("branch_key"),
                    a.get("team_key"),
                    a.get("location"),
                    a.get("timezone") or "Asia/Kuwait",
                    a.get("template_id"),
                    a.get("recurrence_id"),
                    a.get("occurrence_key"),
                    "rollback" if rollback_of_version_id else "draft",
                    a.get("shift_id"),
                ),
            )
    else:
        cur.execute(
            """
            INSERT INTO shift_schedule_draft_rows (
              company_code, period_id, version_id, employee_key, employee_name, employee_phone,
              shift_date, start_time, end_time, ends_next_day, role, site_key, branch_key, team_key,
              location, timezone, template_id, recurrence_id, occurrence_key, source_kind, row_class, conflict_payload
            )
            SELECT company_code, period_id, %s, employee_key, employee_name, employee_phone,
                   shift_date, start_time, end_time, ends_next_day, role, site_key, branch_key, team_key,
                   location, timezone, template_id, recurrence_id, occurrence_key, source_kind, row_class, conflict_payload
            FROM shift_schedule_draft_rows WHERE version_id=%s
            """,
            (version["version_id"], source_id),
        )

    cur.execute(
        "UPDATE shift_schedule_periods SET status='draft', updated_at=now(), updated_by_phone=%s WHERE period_id=%s",
        (_digits(actor_phone) or None, period_id),
    )
    _record_event(
        cur,
        company_code=company,
        period_id=period_id,
        version_id=version["version_id"],
        event_type="draft_from_published" if not rollback_of_version_id else "rollback_draft",
        payload={"based_on": str(source_id), "rollback_of": str(rollback_of_version_id) if rollback_of_version_id else None},
        actor_phone=actor_phone,
    )
    return {"ok": True, "version": version, "period_id": str(period_id), **honesty_payload()}


def rollback_to_version(
    cur: Any,
    *,
    company_code: str,
    period_id: Any,
    target_version_id: Any,
    create_fn: Any,
    actor_phone: str | None = None,
    action_acks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create audited draft from prior published version and publish it (new version)."""
    drafted = create_draft_from_published(
        cur,
        company_code=company_code,
        period_id=period_id,
        actor_phone=actor_phone,
        rollback_of_version_id=target_version_id,
    )
    if not drafted.get("ok"):
        return drafted
    version_id = drafted["version"]["version_id"]
    # Approve then publish
    transition_version(cur, company_code=company_code, version_id=version_id, to_state="in_review", actor_phone=actor_phone)
    transition_version(cur, company_code=company_code, version_id=version_id, to_state="approved", actor_phone=actor_phone)
    published = publish_version(
        cur,
        company_code=company_code,
        version_id=version_id,
        create_fn=create_fn,
        actor_phone=actor_phone,
        action_acks=action_acks,
        publish_idempotency_key=f"SHW5-ROLLBACK|{period_id}|{target_version_id}|{version_id}",
    )
    return {"ok": bool(published.get("ok")), "draft": drafted, "publish": published, **honesty_payload()}


# --- Open shifts --------------------------------------------------------------

def create_open_shift(cur: Any, *, company_code: str, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave5_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave5_disabled", **honesty_payload()}
    start = _as_time(payload.get("start_time"))
    end = _as_time(payload.get("end_time"))
    shift_date = _as_date(payload.get("shift_date") or payload.get("date"))
    if not start or not end or not shift_date:
        return {"ok": False, "error": "invalid_open_shift_window"}
    ends_next = w1.ends_next_day_for(start, end)
    cur.execute(
        """
        INSERT INTO shift_open_shifts (
          company_code, period_id, status, shift_date, start_time, end_time, ends_next_day,
          role, site_key, branch_key, team_key, location, timezone, notes, created_by_phone, updated_by_phone
        ) VALUES (%s,%s,'open',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            str(payload["period_id"]) if payload.get("period_id") else None,
            shift_date,
            start,
            end,
            ends_next,
            str(payload.get("role") or "").strip() or None,
            str(payload.get("site_key") or "").strip() or None,
            str(payload.get("branch_key") or "").strip() or None,
            str(payload.get("team_key") or "").strip() or None,
            str(payload.get("location") or "").strip() or None,
            str(payload.get("timezone") or "Asia/Kuwait"),
            str(payload.get("notes") or "").strip() or None,
            _digits(actor_phone) or None,
            _digits(actor_phone) or None,
        ),
    )
    row = _row(cur)
    return {"ok": True, "open_shift": row, **honesty_payload()}


def get_open_shift(cur: Any, *, company_code: str, open_shift_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_open_shifts WHERE company_code=%s AND open_shift_id=%s",
        ((company_code or "").upper(), str(open_shift_id)),
    )
    return _row(cur)


def list_open_shifts(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM shift_open_shifts
        WHERE company_code=%s AND status IN ('open','claimed','approved')
        ORDER BY shift_date, start_time
        LIMIT 200
        """,
        ((company_code or "").upper(),),
    )
    return _rows(cur)


def claim_open_shift(
    cur: Any,
    *,
    company_code: str,
    open_shift_id: Any,
    employee: dict[str, Any],
    actor_phone: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    os_row = get_open_shift(cur, company_code=company, open_shift_id=open_shift_id)
    if not os_row or str(os_row.get("status")) not in {"open", "claimed"}:
        return {"ok": False, "error": "open_shift_not_claimable"}
    ek = str(employee.get("employee_key") or "")
    if shifts_wave5_synthetic_only() and not is_wave5_synthetic_employee(employee=employee, employee_key=ek, phone=employee.get("phone")):
        return {"ok": False, "error": "synthetic_only"}
    # Self-approval denial is for decide path; claim is request
    try:
        cur.execute(
            """
            INSERT INTO shift_open_shift_claims (
              company_code, open_shift_id, employee_key, employee_phone, employee_name, status
            ) VALUES (%s,%s,%s,%s,%s,'pending')
            RETURNING *
            """,
            (company, open_shift_id, ek, _digits(employee.get("phone")), employee.get("name")),
        )
        claim = _row(cur)
    except Exception as exc:  # noqa: BLE001
        if "unique" in str(exc).lower() or "duplicate" in str(exc).lower():
            return {"ok": False, "error": "already_claimed"}
        raise
    cur.execute(
        "UPDATE shift_open_shifts SET status='claimed', row_version=row_version+1, updated_at=now() WHERE open_shift_id=%s AND status IN ('open','claimed') RETURNING *",
        (open_shift_id,),
    )
    os_row = _row(cur) or os_row
    return {"ok": True, "claim": claim, "open_shift": os_row, **honesty_payload()}


def decide_open_shift_claim(
    cur: Any,
    *,
    company_code: str,
    claim_id: Any,
    decision: str,
    actor_phone: str | None = None,
    actor_employee_key: str | None = None,
    create_fn: Any | None = None,
    expected_row_version: int | None = None,
    action_acks: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Approve/reject claim. Approve converts to L0 with one-winner concurrency."""
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    decision = str(decision or "").lower()
    if decision not in {"approved", "rejected"}:
        return {"ok": False, "error": "invalid_decision"}
    cur.execute(
        "SELECT * FROM shift_open_shift_claims WHERE company_code=%s AND claim_id=%s",
        (company, str(claim_id)),
    )
    claim = _row(cur)
    if not claim or str(claim.get("status")) != "pending":
        return {"ok": False, "error": "claim_not_pending"}
    # Self-approval denied
    if actor_employee_key and str(actor_employee_key) == str(claim.get("employee_key")):
        return {"ok": False, "error": "self_approval_denied", **honesty_payload()}

    os_row = get_open_shift(cur, company_code=company, open_shift_id=claim["open_shift_id"])
    if not os_row:
        return {"ok": False, "error": "open_shift_not_found"}
    if expected_row_version is not None and int(os_row.get("row_version") or 0) != int(expected_row_version):
        return {"ok": False, "error": "stale_open_shift", **honesty_payload()}

    if decision == "rejected":
        cur.execute(
            """
            UPDATE shift_open_shift_claims SET status='rejected', decision_note=%s, decided_by_phone=%s, decided_at=now()
            WHERE claim_id=%s RETURNING *
            """,
            (note, _digits(actor_phone) or None, claim_id),
        )
        claim = _row(cur)
        return {"ok": True, "claim": claim, **honesty_payload()}

    # Approve — one winner: lock open shift row
    cur.execute(
        "SELECT * FROM shift_open_shifts WHERE open_shift_id=%s FOR UPDATE",
        (claim["open_shift_id"],),
    )
    os_row = _row(cur)
    if not os_row or str(os_row.get("status")) in {"assigned", "cancelled"}:
        return {"ok": False, "error": "open_shift_already_resolved", **honesty_payload()}

    if not create_fn:
        return {"ok": False, "error": "create_fn_required"}

    # Load employee
    cur.execute(
        "SELECT employee_key, name, phone, company_code, raw_json FROM employees WHERE company_code=%s AND employee_key=%s",
        (company, claim["employee_key"]),
    )
    emp = _row(cur)
    if not emp:
        return {"ok": False, "error": "employee_not_found"}

    action = {
        "employee_key": emp["employee_key"],
        "employee_name": emp.get("name"),
        "employee_phone": emp.get("phone"),
        "date": str(os_row.get("shift_date"))[:10],
        "shift_date": str(os_row.get("shift_date"))[:10],
        "start_time": _time_str(os_row.get("start_time")),
        "end_time": _time_str(os_row.get("end_time")),
        "role": os_row.get("role"),
        "site_key": os_row.get("site_key"),
        "branch_key": os_row.get("branch_key"),
        "team_key": os_row.get("team_key"),
        "location": os_row.get("location"),
        "timezone": os_row.get("timezone") or "Asia/Kuwait",
        "idempotency_key": f"SHW5-OPEN|{company}|{os_row['open_shift_id']}|{emp['employee_key']}",
        "reason": f"wave5 open shift assign {os_row['open_shift_id']}",
        "source_kind": "manual",
        **(action_acks or {}),
    }
    # Gate via classify-style checks
    planned = {
        "employee": emp,
        "employee_key": emp["employee_key"],
        "employee_phone": emp.get("phone"),
        "employee_name": emp.get("name"),
        "shift_date": action["shift_date"],
        "start_time": action["start_time"],
        "end_time": action["end_time"],
        "ends_next_day": bool(os_row.get("ends_next_day")),
        "site_key": os_row.get("site_key"),
        "occurrence_key": action["idempotency_key"],
        "idempotency_key": action["idempotency_key"],
    }
    conflict = w4.evaluate_planned_conflicts(cur, company_code=company, planned=planned, action_acks=action_acks)
    if conflict:
        return {"ok": False, "error": "gate_conflict", "conflict": conflict, **honesty_payload()}

    try:
        cur.connection.commit()
    except Exception:
        pass
    created = create_fn(action, company_code=company, created_by_phone=actor_phone)
    if not created.get("ok"):
        return {"ok": False, "error": "create_failed", "create_result": created, **honesty_payload()}

    sid = None
    for c in created.get("created") or []:
        sid = str(c.get("shift_id") or "")
    cur.execute(
        """
        UPDATE shift_open_shifts SET
          status='assigned', assigned_employee_key=%s, assigned_shift_id=%s,
          row_version=row_version+1, updated_by_phone=%s, updated_at=now()
        WHERE open_shift_id=%s
        RETURNING *
        """,
        (emp["employee_key"], sid, _digits(actor_phone) or None, os_row["open_shift_id"]),
    )
    os_row = _row(cur)
    cur.execute(
        """
        UPDATE shift_open_shift_claims SET status='approved', decision_note=%s, decided_by_phone=%s, decided_at=now()
        WHERE claim_id=%s RETURNING *
        """,
        (note, _digits(actor_phone) or None, claim_id),
    )
    claim = _row(cur)
    # Reject other pending claims
    cur.execute(
        """
        UPDATE shift_open_shift_claims SET status='rejected', decision_note='other_claim_won', decided_at=now()
        WHERE open_shift_id=%s AND claim_id<>%s AND status='pending'
        """,
        (os_row["open_shift_id"], claim_id),
    )
    if sid:
        cur.execute(
            """
            UPDATE shift_assignments SET schedule_source='open_shift', updated_at=now()
            WHERE shift_id=%s
            """,
            (sid,),
        )
    return {"ok": True, "claim": claim, "open_shift": os_row, "shift_id": sid, "created": created, **honesty_payload()}


def assign_open_shift_direct(
    cur: Any,
    *,
    company_code: str,
    open_shift_id: Any,
    employee_key: str,
    create_fn: Any,
    actor_phone: str | None = None,
    action_acks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """HR/manager direct assign without claim workflow."""
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    cur.execute("SELECT employee_key, name, phone, company_code, raw_json FROM employees WHERE company_code=%s AND employee_key=%s", (company, employee_key))
    emp = _row(cur)
    if not emp:
        return {"ok": False, "error": "employee_not_found"}
    # Fabricate approved claim path
    claim_ins = claim_open_shift(cur, company_code=company, open_shift_id=open_shift_id, employee=emp, actor_phone=actor_phone)
    if not claim_ins.get("ok") and claim_ins.get("error") != "already_claimed":
        return claim_ins
    if claim_ins.get("error") == "already_claimed":
        cur.execute(
            "SELECT * FROM shift_open_shift_claims WHERE open_shift_id=%s AND employee_key=%s",
            (open_shift_id, employee_key),
        )
        claim = _row(cur)
    else:
        claim = claim_ins["claim"]
    return decide_open_shift_claim(
        cur,
        company_code=company,
        claim_id=claim["claim_id"],
        decision="approved",
        actor_phone=actor_phone,
        actor_employee_key=None,
        create_fn=create_fn,
        action_acks=action_acks,
        note="direct_assign",
    )


# --- Coverage -----------------------------------------------------------------

def upsert_coverage_rule(cur: Any, *, company_code: str, payload: dict[str, Any], actor_phone: str | None = None) -> dict[str, Any]:
    ensure_shifts_publish_wave5_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave5_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave5_disabled", **honesty_payload()}
    name = str(payload.get("name") or "").strip()
    start = _as_date(payload.get("effective_start"))
    ws = _as_time(payload.get("window_start"))
    we = _as_time(payload.get("window_end"))
    if not name or not start or not ws or not we:
        return {"ok": False, "error": "invalid_coverage_rule"}
    ends_next = bool(payload["ends_next_day"]) if "ends_next_day" in payload else w1.ends_next_day_for(ws, we)
    mode = str(payload.get("enforcement_mode") or "warn").lower()
    if mode not in {"warn", "block"}:
        mode = "warn"
    cur.execute(
        """
        INSERT INTO shift_coverage_rules (
          company_code, name, enabled, role, site_key, branch_key, team_key,
          effective_start, effective_end, window_start, window_end, ends_next_day,
          min_staff, enforcement_mode, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            name,
            bool(payload.get("enabled", True)),
            str(payload.get("role") or "").strip() or None,
            str(payload.get("site_key") or "").strip() or None,
            str(payload.get("branch_key") or "").strip() or None,
            str(payload.get("team_key") or "").strip() or None,
            start,
            _as_date(payload.get("effective_end")),
            ws,
            we,
            ends_next,
            int(payload.get("min_staff") or 1),
            mode,
            _digits(actor_phone) or None,
        ),
    )
    return {"ok": True, "rule": _row(cur), **honesty_payload()}


def list_coverage_rules(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT * FROM shift_coverage_rules WHERE company_code=%s ORDER BY name",
        ((company_code or "").upper(),),
    )
    return _rows(cur)


def _time_in_window(t: time, ws: time, we: time, ends_next: bool) -> bool:
    if not ends_next:
        return ws <= t < we if ws < we else t >= ws or t < we
    return t >= ws or t < we


def evaluate_coverage_for_version(
    cur: Any,
    *,
    company_code: str,
    version_id: Any,
    period: dict[str, Any] | None = None,
) -> dict[str, Any]:
    company = (company_code or "").upper()
    draft = list_draft_rows(cur, company_code=company, version_id=version_id)
    rules = [r for r in list_coverage_rules(cur, company_code=company) if r.get("enabled")]
    open_shifts = [o for o in list_open_shifts(cur, company_code=company) if str(o.get("status")) in {"open", "claimed"}]

    findings: list[dict[str, Any]] = []
    blocks = False
    summary = {c: 0 for c in COVERAGE_CLASSES}

    # Unresolved open shifts
    for o in open_shifts:
        findings.append({"class": "unresolved_open_shift", "open_shift_id": str(o.get("open_shift_id")), "shift_date": str(o.get("shift_date"))[:10]})
        summary["unresolved_open_shift"] += 1

    p_start = _as_date((period or {}).get("start_date"))
    p_end = _as_date((period or {}).get("end_date"))

    for rule in rules:
        rs = _as_date(rule.get("effective_start"))
        re = _as_date(rule.get("effective_end"))
        ws = _as_time(rule.get("window_start"))
        we = _as_time(rule.get("window_end"))
        if not rs or not ws or not we:
            continue
        day = max(filter(None, [rs, p_start])) if p_start else rs
        end = min(filter(None, [re or p_end, p_end or re])) if (re or p_end) else (p_end or rs)
        if not end or day > end:
            continue
        d = day
        while d <= end:
            # Count draft staff matching scope overlapping window
            count = 0
            for row in draft:
                if str(row.get("row_class")) in {"conflict", "cancelled_held"}:
                    continue
                rd = _as_date(row.get("shift_date"))
                if rd != d:
                    continue
                if rule.get("role") and str(row.get("role") or "") != str(rule.get("role")):
                    continue
                if rule.get("site_key") and str(row.get("site_key") or "") != str(rule.get("site_key")):
                    continue
                if rule.get("branch_key") and str(row.get("branch_key") or "") != str(rule.get("branch_key")):
                    continue
                if rule.get("team_key") and str(row.get("team_key") or "") != str(rule.get("team_key")):
                    continue
                st = _as_time(row.get("start_time"))
                if st and _time_in_window(st, ws, we, bool(rule.get("ends_next_day"))):
                    count += 1
            min_staff = int(rule.get("min_staff") or 0)
            if count < min_staff:
                cls = "understaffed"
                if str(rule.get("enforcement_mode")) == "block":
                    blocks = True
            elif count > min_staff * 2 and min_staff > 0:
                cls = "overstaffed"
            else:
                cls = "covered"
            findings.append(
                {
                    "class": cls,
                    "rule_id": str(rule.get("rule_id")),
                    "rule_name": rule.get("name"),
                    "date": d.isoformat(),
                    "staffed": count,
                    "min_staff": min_staff,
                    "enforcement_mode": rule.get("enforcement_mode"),
                }
            )
            summary[cls] = summary.get(cls, 0) + 1
            d += timedelta(days=1)

    return {
        "ok": True,
        "summary": summary,
        "findings": findings[:200],
        "blocks_publish": blocks,
        "finding_count": len(findings),
    }


def permission_matrix() -> dict[str, Any]:
    return {
        "hr_owner": ["period.crud", "draft.generate", "review.submit", "review.approve", "publish", "rollback", "open_shift.crud", "open_shift.decide", "coverage.crud"],
        "manager_scoped": ["draft.generate", "review.submit", "open_shift.claim_decide_scoped", "coverage.read"],
        "employee": ["open_shift.claim"],
        "self_approval": False,
        "simple_companies": "direct_assignment_publish_optional",
        "medium_enterprise": "require_publish_enabled",
    }
