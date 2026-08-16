"""Shifts Wave 6A — rotations, remote roster metadata, compliance, PAM export (staging).

Planning-only rotation engine that feeds Wave 5 draft → review → approve → publish.
Published L0 assignments remain the only schedule authority.

Does NOT: submit to PAM, calculate Payroll money, enable real allowlists/reminders,
deploy to production, or invent a government API.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import shifts_publish_wave5 as w5
import shifts_templates_wave4 as w4

SHIFTS_WAVE6_VERSION = "6.0.0"
PAM_EXPORT_CONTRACT_VERSION = "pam-export@1.0.0"
JOB_LOCK_WAVE6_BASE = 760_600_001

DAY_KINDS = frozenset({"work", "rest", "travel", "standby"})
PATTERN_KINDS = frozenset({
    "n_on_m_off",
    "alternating_day_night",
    "panama_223",
    "four_on_four_off",
    "six_on_one_off",
    "hitch_n_n",
    "custom_sequence",
})
TARGET_TYPES = frozenset({"employee", "crew", "team", "site", "role"})
NON_PUBLISH_ROW_CLASSES = frozenset({"travel", "rest", "standby", "conflict", "cancelled_held", "detached"})

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "shifts_enterprise_wave6_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: str = "") -> tuple[str, ...]:
    raw = os.environ.get(name, default) or default
    return tuple(x.strip() for x in str(raw).split(",") if x.strip())


def _is_production() -> bool:
    return str(os.environ.get("WATHEFNI_ENV") or "").strip().lower() == "production"


def shifts_wave6_enabled() -> bool:
    return _env_bool("WATHEFNI_SHIFTS_WAVE6", default=not _is_production())


def shifts_wave6_companies() -> set[str]:
    return {c.upper() for c in _env_csv("WATHEFNI_SHIFTS_WAVE6_COMPANIES", "WATHEFNI")}


def shifts_wave6_enabled_for_company(company_code: str | None) -> bool:
    if not shifts_wave6_enabled():
        return False
    companies = shifts_wave6_companies()
    if not companies:
        return True
    return (company_code or "").upper() in companies


def shifts_wave6_synthetic_only() -> bool:
    return _env_bool("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_ONLY", default=_is_production())


def wave6_synthetic_key_markers() -> tuple[str, ...]:
    return _env_csv("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS", "SHW6,SHW6-SYNTH|")


def wave6_synthetic_phone_prefixes() -> tuple[str, ...]:
    return _env_csv("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES", "965536")


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def is_wave6_synthetic_employee(
    *,
    employee_key: str | None = None,
    phone: str | None = None,
    name: str | None = None,
    employee: dict[str, Any] | None = None,
) -> bool:
    key = str(employee_key or (employee or {}).get("employee_key") or "")
    nm = str(name or (employee or {}).get("name") or "")
    ph = _digits(phone or (employee or {}).get("phone"))
    for m in wave6_synthetic_key_markers():
        if m and (m in key or m in nm):
            return True
    for p in wave6_synthetic_phone_prefixes():
        if p and ph.startswith(p):
            return True
    raw = (employee or {}).get("raw_json") if employee else None
    if isinstance(raw, dict) and (raw.get("shw6") or raw.get("shw6a")):
        return True
    if isinstance(raw, str):
        low = raw.lower()
        if '"shw6"' in low or '"shw6a"' in low:
            return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "shifts_wave6_version": SHIFTS_WAVE6_VERSION,
        "pam_export_contract_version": PAM_EXPORT_CONTRACT_VERSION,
        "payroll_money": False,
        "leave_balances_mutated": False,
        "attendance_authority_mutated": False,
        "templates": True,
        "recurring_schedules": True,
        "rotations": True,
        "remote_rosters": True,
        "publishing": True,
        "open_shifts": True,
        "pam_export": True,
        "pam_submission": False,
        "draft_publish": True,
        "coverage_rules": True,
        "compliance_profiles": True,
        "require_publish_optional": True,
        "complexity_levels": {
            "simple": "manual_l0_board_unchanged",
            "medium": "draft_review_publish_open_coverage",
            "enterprise": "rotations_remote_compliance_pam_export",
        },
        "wave6_synthetic_markers": {
            "key_markers": list(wave6_synthetic_key_markers()),
            "phone_prefixes": list(wave6_synthetic_phone_prefixes()),
        },
        "rollout_prepared_not_enabled": {
            "hr_allowlist": False,
            "manager_allowlist": False,
            "talal_readonly": False,
            "real_reminders": False,
            "real_job_timers": False,
            "employee_open_shift_claims": False,
        },
    }


def permission_matrix() -> dict[str, Any]:
    return {
        "create_rotation_pattern": ["hr", "admin"],
        "assign_rotation": ["hr", "admin"],
        "preview_rotation": ["hr", "admin", "manager_scoped"],
        "generate_draft_from_rotation": ["hr", "admin"],
        "manage_compliance_profile": ["hr", "admin"],
        "export_pam": ["hr", "admin"],
        "real_mutation_requires": [
            "permission_and_scope",
            "allowlist",
            "audit_reason",
            "concurrency_token",
            "policy_conflict_evaluation",
            "kill_switch",
        ],
    }


def ensure_shifts_enterprise_wave6_schema(cur: Any) -> None:
    lock_id = JOB_LOCK_WAVE6_BASE - 7
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        w5.ensure_shifts_publish_wave5_schema(cur)
        if SCHEMA_SQL.strip():
            cur.execute(SCHEMA_SQL)
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value)[:10]
    try:
        return date.fromisoformat(s)
    except Exception:
        return None


def _as_time(value: Any) -> time | None:
    if value is None or value == "":
        return None
    if isinstance(value, time):
        return value
    s = str(value)
    try:
        if len(s) >= 8 and s[2] == ":":
            return time.fromisoformat(s[:8])
        return time.fromisoformat(s[:5])
    except Exception:
        return None


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


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, (date, datetime, time, uuid.UUID)):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    return obj


def _digits_phone(value: Any) -> str | None:
    d = _digits(value)
    return d or None


def preset_cycle_sequence(pattern_kind: str, payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Build a canonical cycle sequence for known pattern kinds."""
    p = payload or {}
    kind = str(pattern_kind or "").strip()
    if kind == "custom_sequence":
        seq = p.get("cycle_sequence") or []
        out = []
        for item in seq:
            if not isinstance(item, dict):
                continue
            k = str(item.get("kind") or "").strip().lower()
            if k not in DAY_KINDS:
                continue
            slot = str(item.get("template_slot") or "primary").strip().lower()
            out.append({"kind": k, "template_slot": slot})
        return out
    if kind == "four_on_four_off":
        return [{"kind": "work", "template_slot": "primary"}] * 4 + [{"kind": "rest", "template_slot": "primary"}] * 4
    if kind == "six_on_one_off":
        return [{"kind": "work", "template_slot": "primary"}] * 6 + [{"kind": "rest", "template_slot": "primary"}]
    if kind == "n_on_m_off":
        on_days = max(1, int(p.get("on_days") or 1))
        off_days = max(0, int(p.get("off_days") or 0))
        return [{"kind": "work", "template_slot": "primary"}] * on_days + [{"kind": "rest", "template_slot": "primary"}] * off_days
    if kind == "panama_223":
        # Classic 2-2-3 over 14 days
        blocks = [2, 2, 3, 2, 2, 3]
        work = True
        out: list[dict[str, Any]] = []
        for n in blocks:
            kind_day = "work" if work else "rest"
            out.extend([{"kind": kind_day, "template_slot": "primary"}] * n)
            work = not work
        return out
    if kind == "alternating_day_night":
        return [
            {"kind": "work", "template_slot": "day"},
            {"kind": "work", "template_slot": "night"},
        ]
    if kind == "hitch_n_n":
        on_days = max(1, int(p.get("hitch_on_days") or p.get("on_days") or 14))
        off_days = max(0, int(p.get("hitch_off_days") or p.get("off_days") or on_days))
        travel_edges = bool(p.get("travel_edges", True))
        out = []
        if travel_edges:
            out.append({"kind": "travel", "template_slot": "primary"})
            on_work = max(0, on_days - 1)
        else:
            on_work = on_days
        out.extend([{"kind": "work", "template_slot": "primary"}] * on_work)
        if travel_edges:
            out.append({"kind": "travel", "template_slot": "primary"})
            rest_n = max(0, off_days - 1)
        else:
            rest_n = off_days
        out.extend([{"kind": "rest", "template_slot": "primary"}] * rest_n)
        return out
    return []


# --- Pattern / assignment CRUD ------------------------------------------------

def create_rotation_pattern(
    cur: Any,
    *,
    company_code: str,
    payload: dict[str, Any],
    actor_phone: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_enterprise_wave6_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave6_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6_disabled", **honesty_payload()}
    kind = str(payload.get("pattern_kind") or "").strip()
    name = str(payload.get("name") or "").strip()
    if kind not in PATTERN_KINDS or len(name) < 2:
        return {"ok": False, "error": "invalid_pattern"}
    seq = preset_cycle_sequence(kind, payload)
    if not seq:
        return {"ok": False, "error": "empty_cycle_sequence"}
    remote_defaults = payload.get("remote_defaults") if isinstance(payload.get("remote_defaults"), dict) else {}
    cur.execute(
        """
        INSERT INTO shift_rotation_patterns (
          company_code, name, pattern_kind, on_days, off_days, hitch_on_days, hitch_off_days,
          cycle_sequence, day_template_id, night_template_id, timezone, remote_defaults,
          created_by_phone, updated_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            name,
            kind,
            int(payload["on_days"]) if payload.get("on_days") is not None else None,
            int(payload["off_days"]) if payload.get("off_days") is not None else None,
            int(payload["hitch_on_days"]) if payload.get("hitch_on_days") is not None else None,
            int(payload["hitch_off_days"]) if payload.get("hitch_off_days") is not None else None,
            json.dumps(_jsonable(seq)),
            payload.get("day_template_id") or payload.get("template_id"),
            payload.get("night_template_id") or payload.get("alternate_template_id"),
            str(payload.get("timezone") or "Asia/Kuwait"),
            json.dumps(_jsonable(remote_defaults)),
            _digits_phone(actor_phone),
            _digits_phone(actor_phone),
        ),
    )
    pattern = _row(cur)
    _record_event(cur, company_code=company, pattern_id=pattern["pattern_id"], event_type="pattern_created", payload={"name": name, "kind": kind}, actor_phone=actor_phone)
    return {"ok": True, "pattern": pattern, **honesty_payload()}


def get_rotation_pattern(cur: Any, *, company_code: str, pattern_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_rotation_patterns WHERE company_code=%s AND pattern_id=%s",
        ((company_code or "").upper(), str(pattern_id)),
    )
    return _row(cur)


def list_rotation_patterns(cur: Any, *, company_code: str, include_archived: bool = False) -> list[dict[str, Any]]:
    company = (company_code or "").upper()
    if include_archived:
        cur.execute("SELECT * FROM shift_rotation_patterns WHERE company_code=%s ORDER BY created_at DESC", (company,))
    else:
        cur.execute(
            "SELECT * FROM shift_rotation_patterns WHERE company_code=%s AND status='active' ORDER BY created_at DESC",
            (company,),
        )
    return _rows(cur)


def assign_rotation(
    cur: Any,
    *,
    company_code: str,
    payload: dict[str, Any],
    actor_phone: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_enterprise_wave6_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave6_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6_disabled", **honesty_payload()}
    pattern = get_rotation_pattern(cur, company_code=company, pattern_id=payload.get("pattern_id"))
    if not pattern or str(pattern.get("status")) != "active":
        return {"ok": False, "error": "pattern_not_found"}
    target_type = str(payload.get("target_type") or "employee").strip()
    target_key = str(payload.get("target_key") or payload.get("employee_key") or "").strip()
    if target_type not in TARGET_TYPES or not target_key:
        return {"ok": False, "error": "invalid_target"}
    anchor = _as_date(payload.get("cycle_anchor_date")) or _as_date(payload.get("effective_start"))
    start = _as_date(payload.get("effective_start")) or anchor
    end = _as_date(payload.get("effective_end"))
    if not anchor or not start:
        return {"ok": False, "error": "invalid_dates"}
    if end and end < start:
        return {"ok": False, "error": "invalid_dates"}
    offset = int(payload.get("cycle_offset") or 0)
    if offset < 0:
        return {"ok": False, "error": "invalid_offset"}
    name = str(payload.get("name") or f"{pattern.get('name')} @ {target_key}").strip()
    warnings = payload.get("access_warnings") if isinstance(payload.get("access_warnings"), list) else []
    certs = payload.get("certification_warnings") if isinstance(payload.get("certification_warnings"), list) else []
    remote_meta = payload.get("remote_meta") if isinstance(payload.get("remote_meta"), dict) else {}
    # Merge pattern remote defaults without money fields
    defaults = pattern.get("remote_defaults") if isinstance(pattern.get("remote_defaults"), dict) else {}
    if isinstance(defaults, str):
        try:
            defaults = json.loads(defaults)
        except Exception:
            defaults = {}
    for k in ("allowance", "money", "amount", "payroll", "pay"):
        remote_meta.pop(k, None)
        if isinstance(defaults, dict):
            defaults.pop(k, None)

    cur.execute(
        """
        INSERT INTO shift_rotation_assignments (
          company_code, pattern_id, name, target_type, target_key,
          employee_key, employee_name, employee_phone, cycle_offset, cycle_anchor_date,
          effective_start, effective_end, remote_site_key, camp_key, transport_required,
          transport_group, pickup_location, accommodation_required, mobilization_date,
          demobilization_date, access_warnings, certification_warnings, remote_meta,
          created_by_phone, updated_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s
        )
        RETURNING *
        """,
        (
            company,
            pattern["pattern_id"],
            name,
            target_type,
            target_key,
            payload.get("employee_key") or (target_key if target_type == "employee" else None),
            payload.get("employee_name"),
            _digits_phone(payload.get("employee_phone")),
            offset,
            anchor,
            start,
            end,
            payload.get("remote_site_key") or defaults.get("remote_site_key"),
            payload.get("camp_key") or defaults.get("camp_key"),
            bool(payload.get("transport_required", defaults.get("transport_required", False))),
            payload.get("transport_group") or defaults.get("transport_group"),
            payload.get("pickup_location") or defaults.get("pickup_location"),
            bool(payload.get("accommodation_required", defaults.get("accommodation_required", False))),
            _as_date(payload.get("mobilization_date")),
            _as_date(payload.get("demobilization_date")),
            json.dumps(_jsonable(warnings)),
            json.dumps(_jsonable(certs)),
            json.dumps(_jsonable({**(defaults if isinstance(defaults, dict) else {}), **remote_meta})),
            _digits_phone(actor_phone),
            _digits_phone(actor_phone),
        ),
    )
    assignment = _row(cur)
    _record_event(
        cur,
        company_code=company,
        pattern_id=pattern["pattern_id"],
        assignment_id=assignment["assignment_id"],
        event_type="assignment_created",
        payload={"target_type": target_type, "target_key": target_key, "cycle_offset": offset},
        actor_phone=actor_phone,
    )
    return {"ok": True, "assignment": assignment, "pattern": pattern, **honesty_payload()}


def get_rotation_assignment(cur: Any, *, company_code: str, assignment_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_rotation_assignments WHERE company_code=%s AND assignment_id=%s",
        ((company_code or "").upper(), str(assignment_id)),
    )
    return _row(cur)


def list_rotation_assignments(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM shift_rotation_assignments
        WHERE company_code=%s AND status IN ('active','paused')
        ORDER BY created_at DESC
        """,
        ((company_code or "").upper(),),
    )
    return _rows(cur)


def _record_event(
    cur: Any,
    *,
    company_code: str,
    pattern_id: Any = None,
    assignment_id: Any = None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    actor_phone: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO shift_rotation_events (company_code, pattern_id, assignment_id, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            str(pattern_id) if pattern_id else None,
            str(assignment_id) if assignment_id else None,
            event_type,
            json.dumps(_jsonable(payload or {})),
            _digits_phone(actor_phone),
        ),
    )


def _parse_sequence(pattern: dict[str, Any]) -> list[dict[str, Any]]:
    seq = pattern.get("cycle_sequence")
    if isinstance(seq, str):
        try:
            seq = json.loads(seq)
        except Exception:
            seq = []
    if not isinstance(seq, list):
        return []
    out = []
    for item in seq:
        if isinstance(item, dict) and str(item.get("kind") or "").lower() in DAY_KINDS:
            out.append({
                "kind": str(item["kind"]).lower(),
                "template_slot": str(item.get("template_slot") or "primary").lower(),
            })
    return out


def expand_rotation_days(
    *,
    pattern: dict[str, Any],
    assignment: dict[str, Any],
    window_start: date,
    window_end: date,
) -> list[dict[str, Any]]:
    """Expand cycle into dated planning days (work/rest/travel/standby)."""
    seq = _parse_sequence(pattern)
    if not seq:
        return []
    anchor = _as_date(assignment.get("cycle_anchor_date")) or window_start
    eff_start = _as_date(assignment.get("effective_start")) or anchor
    eff_end = _as_date(assignment.get("effective_end"))
    offset = int(assignment.get("cycle_offset") or 0)
    cycle_len = len(seq)
    out: list[dict[str, Any]] = []
    d = window_start
    while d <= window_end:
        if d < eff_start or (eff_end and d > eff_end):
            d += timedelta(days=1)
            continue
        if d < anchor:
            d += timedelta(days=1)
            continue
        idx = ((d - anchor).days + offset) % cycle_len
        step = seq[idx]
        out.append({
            "shift_date": d,
            "day_kind": step["kind"],
            "template_slot": step["template_slot"],
            "cycle_index": idx,
            "occurrence_key": f"ROT|{assignment.get('assignment_id')}|{d.isoformat()}|{step['kind']}|{idx}",
        })
        d += timedelta(days=1)
    return out


def _pick_template(
    cur: Any,
    *,
    company_code: str,
    pattern: dict[str, Any],
    slot: str,
) -> dict[str, Any] | None:
    day_id = pattern.get("day_template_id")
    night_id = pattern.get("night_template_id")
    if slot in {"night", "alternate"} and night_id:
        return w4.get_template(cur, company_code=company_code, template_id=night_id)
    if day_id:
        return w4.get_template(cur, company_code=company_code, template_id=day_id)
    if night_id:
        return w4.get_template(cur, company_code=company_code, template_id=night_id)
    return None


def preview_rotation(
    cur: Any,
    *,
    company_code: str,
    assignment_id: Any,
    window_start: date | None = None,
    window_end: date | None = None,
    sample_limit: int = 60,
) -> dict[str, Any]:
    ensure_shifts_enterprise_wave6_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave6_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6_disabled", **honesty_payload()}
    assignment = get_rotation_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not assignment:
        return {"ok": False, "error": "assignment_not_found"}
    pattern = get_rotation_pattern(cur, company_code=company, pattern_id=assignment["pattern_id"])
    if not pattern:
        return {"ok": False, "error": "pattern_not_found"}
    start = window_start or (_as_date(assignment["effective_start"]) or date.today())
    end = window_end or (start + timedelta(days=27))
    days = expand_rotation_days(pattern=pattern, assignment=assignment, window_start=start, window_end=end)
    counts = {"work": 0, "rest": 0, "travel": 0, "standby": 0}
    for day in days:
        counts[str(day["day_kind"])] = counts.get(str(day["day_kind"]), 0) + 1
    sample = []
    for day in days[: max(1, sample_limit)]:
        tpl = None
        if day["day_kind"] == "work":
            tpl = _pick_template(cur, company_code=company, pattern=pattern, slot=day["template_slot"])
        sample.append({
            **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in day.items()},
            "template_id": tpl.get("template_id") if tpl else None,
            "starts": str(tpl.get("start_time"))[:8] if tpl else None,
            "ends": str(tpl.get("end_time"))[:8] if tpl else None,
            "ends_next_day": bool(tpl.get("ends_next_day")) if tpl else False,
        })
    return {
        "ok": True,
        "assignment": assignment,
        "pattern": pattern,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "counts": counts,
        "sample": sample,
        "total_days": len(days),
        "l0_written": False,
        "remote": {
            "remote_site_key": assignment.get("remote_site_key"),
            "camp_key": assignment.get("camp_key"),
            "transport_required": assignment.get("transport_required"),
            "accommodation_required": assignment.get("accommodation_required"),
            "mobilization_date": str(assignment.get("mobilization_date") or "")[:10] or None,
            "demobilization_date": str(assignment.get("demobilization_date") or "")[:10] or None,
        },
        **honesty_payload(),
    }


def generate_draft_from_rotation(
    cur: Any,
    *,
    company_code: str,
    period_id: Any,
    assignment_id: Any,
    actor_phone: str | None = None,
    action_acks: dict[str, Any] | None = None,
    include_non_work_rows: bool = True,
) -> dict[str, Any]:
    """Expand a rotation assignment into Wave 5 draft rows only — never writes L0."""
    ensure_shifts_enterprise_wave6_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave6_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6_disabled", **honesty_payload()}
    if not w5.shifts_wave5_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave5_disabled", **honesty_payload()}

    period = w5.get_period(cur, company_code=company, period_id=period_id)
    if not period or str(period.get("status")) in {"cancelled", "superseded"}:
        return {"ok": False, "error": "period_not_editable"}
    version = w5._latest_editable_version(cur, company_code=company, period_id=period_id)
    if not version or str(version.get("state")) not in {"draft", "in_review"}:
        return {"ok": False, "error": "no_editable_draft_version"}
    if str(version.get("state")) == "in_review":
        return {"ok": False, "error": "version_locked_in_review"}

    assignment = get_rotation_assignment(cur, company_code=company, assignment_id=assignment_id)
    if not assignment or str(assignment.get("status")) not in {"active", "paused"}:
        return {"ok": False, "error": "assignment_not_found"}
    pattern = get_rotation_pattern(cur, company_code=company, pattern_id=assignment["pattern_id"])
    if not pattern:
        return {"ok": False, "error": "pattern_not_found"}

    p_start = _as_date(period["start_date"])
    p_end = _as_date(period["end_date"])
    if not p_start or not p_end:
        return {"ok": False, "error": "invalid_period"}

    # Only future-or-period window days; never rewrite published/historical L0
    today = date.today()
    eligible_start = max(p_start, today + timedelta(days=1))
    if eligible_start > p_end:
        # Allow synthetic staging windows that start in the future relative to "today"
        eligible_start = p_start

    days = expand_rotation_days(pattern=pattern, assignment=assignment, window_start=eligible_start, window_end=p_end)

    # Resolve employee(s)
    employees: list[dict[str, Any]] = []
    if assignment.get("employee_key"):
        employees = [{
            "employee_key": assignment.get("employee_key"),
            "name": assignment.get("employee_name"),
            "phone": assignment.get("employee_phone"),
        }]
    else:
        employees = w4.resolve_target_employees(
            cur,
            company_code=company,
            target_type=str(assignment.get("target_type")),
            target_key=str(assignment.get("target_key")),
        )
    if shifts_wave6_synthetic_only():
        employees = [
            e for e in employees
            if is_wave6_synthetic_employee(employee=e, employee_key=e.get("employee_key"), phone=e.get("phone"), name=e.get("name"))
            or w5.is_wave5_synthetic_employee(employee=e, employee_key=e.get("employee_key"), phone=e.get("phone"), name=e.get("name"))
            or w4.is_wave4_synthetic_employee(employee=e, employee_key=e.get("employee_key"), phone=e.get("phone"), name=e.get("name"))
        ]
    if not employees:
        return {"ok": False, "error": "no_target_employees", **honesty_payload()}

    # Held/cancelled detection — do not silently reintroduce
    held_keys: set[str] = set()
    cur.execute(
        """
        SELECT employee_key, shift_date::text AS d, coalesce(occurrence_key,'') AS ok
        FROM shift_assignments
        WHERE company_code=%s AND status='cancelled'
          AND shift_date BETWEEN %s AND %s
          AND (coalesce(occurrence_key,'') LIKE %s OR employee_key = ANY(%s))
        """,
        (
            company,
            p_start,
            p_end,
            f"%{assignment.get('assignment_id')}%",
            [e.get("employee_key") for e in employees],
        ),
    )
    for r in _rows(cur):
        held_keys.add(f"{r.get('employee_key')}|{str(r.get('d'))[:10]}")

    # Detached regenerated rows
    cur.execute(
        """
        SELECT employee_key, shift_date::text AS d
        FROM shift_assignments
        WHERE company_code=%s AND coalesce(regen_detached,false)=true
          AND shift_date BETWEEN %s AND %s
          AND employee_key = ANY(%s)
        """,
        (company, p_start, p_end, [e.get("employee_key") for e in employees]),
    )
    detached_keys = {f"{r.get('employee_key')}|{str(r.get('d'))[:10]}" for r in _rows(cur)}

    cur.execute("DELETE FROM shift_schedule_draft_rows WHERE version_id=%s", (version["version_id"],))
    inserted = 0
    sequence_audit: list[dict[str, Any]] = []
    for day in days:
        for emp in employees:
            ek = str(emp.get("employee_key") or "")
            hold_key = f"{ek}|{day['shift_date'].isoformat()}"
            day_kind = day["day_kind"]
            sequence_audit.append({
                "date": day["shift_date"].isoformat(),
                "employee_key": ek,
                "day_kind": day_kind,
                "cycle_index": day["cycle_index"],
            })
            if day_kind != "work" and not include_non_work_rows:
                continue
            row_class = day_kind if day_kind != "work" else "ready"
            if hold_key in held_keys:
                row_class = "cancelled_held"
            elif hold_key in detached_keys:
                row_class = "detached"
            tpl = None
            start_t = time(0, 0)
            end_t = time(0, 0)
            ends_next = False
            role = None
            site = assignment.get("remote_site_key") or period.get("site_key")
            if day_kind == "work":
                tpl = _pick_template(cur, company_code=company, pattern=pattern, slot=day["template_slot"])
                if not tpl:
                    return {"ok": False, "error": "template_required_for_work_day", "slot": day["template_slot"]}
                start_t = _as_time(tpl.get("start_time")) or time(8, 0)
                end_t = _as_time(tpl.get("end_time")) or time(16, 0)
                ends_next = bool(tpl.get("ends_next_day"))
                role = tpl.get("role")
                site = tpl.get("site_key") or site
            conflict: dict[str, Any] = {}
            if day_kind == "work" and row_class == "ready":
                planned = {
                    "employee_key": ek,
                    "employee_name": emp.get("name") or emp.get("employee_name"),
                    "employee_phone": emp.get("phone") or emp.get("employee_phone"),
                    "shift_date": day["shift_date"],
                    "start_time": start_t,
                    "end_time": end_t,
                    "ends_next_day": ends_next,
                    "role": role,
                    "site_key": site,
                    "branch_key": period.get("branch_key") or (tpl or {}).get("branch_key"),
                    "team_key": period.get("team_key") or (tpl or {}).get("team_key"),
                    "location": (tpl or {}).get("location"),
                    "timezone": pattern.get("timezone") or "Asia/Kuwait",
                    "template_id": (tpl or {}).get("template_id"),
                    "occurrence_key": day["occurrence_key"],
                    "idempotency_key": w4.materialize_idempotency_key(day["occurrence_key"]),
                }
                classified = w4.classify_occurrence(cur, company_code=company, planned=planned, action_acks=action_acks)
                row_class = classified.get("class") or row_class
                conflict = classified.get("conflict") or {}
                emp_name = classified.get("employee_name")
                emp_phone = classified.get("employee_phone")
            else:
                emp_name = emp.get("name") or emp.get("employee_name")
                emp_phone = emp.get("phone") or emp.get("employee_phone")

            cur.execute(
                """
                INSERT INTO shift_schedule_draft_rows (
                  company_code, period_id, version_id, employee_key, employee_name, employee_phone,
                  shift_date, start_time, end_time, ends_next_day, role, site_key, branch_key, team_key,
                  location, timezone, template_id, recurrence_id, occurrence_key, source_kind, row_class,
                  conflict_payload, rotation_pattern_id, rotation_assignment_id, day_kind
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,'rotation',%s,%s::jsonb,%s,%s,%s
                )
                """,
                (
                    company,
                    period["period_id"],
                    version["version_id"],
                    ek,
                    emp_name,
                    _digits_phone(emp_phone),
                    day["shift_date"],
                    start_t,
                    end_t,
                    ends_next,
                    role,
                    site,
                    period.get("branch_key"),
                    period.get("team_key"),
                    assignment.get("camp_key") or (tpl or {}).get("location"),
                    pattern.get("timezone") or "Asia/Kuwait",
                    (tpl or {}).get("template_id"),
                    day["occurrence_key"],
                    row_class,
                    json.dumps(_jsonable(conflict)),
                    pattern["pattern_id"],
                    assignment["assignment_id"],
                    day_kind,
                ),
            )
            inserted += 1

    compliance = evaluate_compliance_for_version(cur, company_code=company, version_id=version["version_id"], period=period)
    coverage = w5.evaluate_coverage_for_version(cur, company_code=company, version_id=version["version_id"], period=period)
    fp = hashlib.sha256(
        json.dumps({"n": inserted, "assignment": str(assignment_id), "comp": compliance.get("summary")}, sort_keys=True, default=str).encode()
    ).hexdigest()[:24]
    draft_payload = {
        "source": "rotation",
        "assignment_id": str(assignment_id),
        "pattern_id": str(pattern["pattern_id"]),
        "inserted": inserted,
        "sequence_sample": sequence_audit[:40],
        "remote": {
            "remote_site_key": assignment.get("remote_site_key"),
            "camp_key": assignment.get("camp_key"),
            "transport_required": assignment.get("transport_required"),
            "accommodation_required": assignment.get("accommodation_required"),
        },
        "compliance_summary": compliance.get("summary"),
    }
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
            json.dumps(_jsonable(draft_payload)),
            json.dumps(_jsonable({"coverage": coverage, "compliance": compliance})),
            _digits_phone(actor_phone),
            version["version_id"],
        ),
    )
    version = _row(cur)
    w5._record_event(
        cur,
        company_code=company,
        period_id=period_id,
        version_id=version["version_id"],
        event_type="draft_generated_from_rotation",
        payload={"inserted": inserted, "assignment_id": str(assignment_id)},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "period_id": str(period_id),
        "version": version,
        "draft_rows": inserted,
        "coverage": coverage,
        "compliance": compliance,
        "l0_written": False,
        "eligible_window": {"start": eligible_start.isoformat(), "end": p_end.isoformat()},
        **honesty_payload(),
    }


# --- Compliance ---------------------------------------------------------------

def upsert_compliance_profile(
    cur: Any,
    *,
    company_code: str,
    payload: dict[str, Any],
    actor_phone: str | None = None,
) -> dict[str, Any]:
    ensure_shifts_enterprise_wave6_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave6_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6_disabled", **honesty_payload()}
    name = str(payload.get("name") or "").strip()
    rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
    if len(name) < 2:
        return {"ok": False, "error": "invalid_profile"}
    # Strip any monetary keys from rules
    cleaned = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        r = {k: v for k, v in rule.items() if k not in {"money", "amount", "allowance", "payroll"}}
        cleaned.append(r)
    mode = str(payload.get("default_enforcement") or "warn").strip().lower()
    if mode not in {"warn", "block"}:
        mode = "warn"
    cur.execute(
        """
        INSERT INTO shift_compliance_profiles (
          company_code, name, sector_key, enabled, default_enforcement, rules,
          effective_start, effective_end, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
        ON CONFLICT (company_code, name) DO UPDATE SET
          sector_key=EXCLUDED.sector_key,
          enabled=EXCLUDED.enabled,
          default_enforcement=EXCLUDED.default_enforcement,
          rules=EXCLUDED.rules,
          effective_start=EXCLUDED.effective_start,
          effective_end=EXCLUDED.effective_end,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            name,
            payload.get("sector_key"),
            bool(payload.get("enabled", True)),
            mode,
            json.dumps(_jsonable(cleaned)),
            _as_date(payload.get("effective_start")),
            _as_date(payload.get("effective_end")),
            _digits_phone(actor_phone),
        ),
    )
    return {"ok": True, "profile": _row(cur), **honesty_payload()}


def list_compliance_profiles(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT * FROM shift_compliance_profiles WHERE company_code=%s ORDER BY name",
        ((company_code or "").upper(),),
    )
    return _rows(cur)


def _hours_between(start_t: time, end_t: time, ends_next_day: bool) -> float:
    s = datetime.combine(date.today(), start_t)
    e = datetime.combine(date.today(), end_t)
    if ends_next_day or e <= s:
        e += timedelta(days=1)
    return max(0.0, (e - s).total_seconds() / 3600.0)


def evaluate_compliance_for_version(
    cur: Any,
    *,
    company_code: str,
    version_id: Any,
    period: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate company compliance profiles against draft rows. Default = warn."""
    company = (company_code or "").upper()
    profiles = [p for p in list_compliance_profiles(cur, company_code=company) if p.get("enabled")]
    draft = w5.list_draft_rows(cur, company_code=company, version_id=version_id)
    work_rows = [r for r in draft if str(r.get("day_kind") or "work") == "work" or str(r.get("row_class")) not in NON_PUBLISH_ROW_CLASSES]
    findings: list[dict[str, Any]] = []
    blocks = False

    for profile in profiles:
        rules = profile.get("rules") or []
        if isinstance(rules, str):
            try:
                rules = json.loads(rules)
            except Exception:
                rules = []
        default_mode = str(profile.get("default_enforcement") or "warn")
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rtype = str(rule.get("type") or "").strip()
            mode = str(rule.get("enforcement") or default_mode).strip().lower()
            if mode not in {"warn", "block"}:
                mode = "warn"
            site_filter = rule.get("site_key")

            if rtype == "ramadan_hours":
                max_h = float(rule.get("max_daily_hours") or 6)
                rs = _as_date(rule.get("effective_start"))
                re_ = _as_date(rule.get("effective_end"))
                for row in work_rows:
                    d = _as_date(row.get("shift_date"))
                    if not d or (rs and d < rs) or (re_ and d > re_):
                        continue
                    if site_filter and str(row.get("site_key") or "") != str(site_filter):
                        continue
                    st = _as_time(row.get("start_time")) or time(0, 0)
                    et = _as_time(row.get("end_time")) or time(0, 0)
                    hrs = _hours_between(st, et, bool(row.get("ends_next_day")))
                    if hrs > max_h + 1e-6:
                        findings.append({
                            "type": rtype,
                            "mode": mode,
                            "employee_key": row.get("employee_key"),
                            "shift_date": str(d),
                            "hours": round(hrs, 2),
                            "max_daily_hours": max_h,
                            "profile": profile.get("name"),
                        })
                        if mode == "block":
                            blocks = True

            elif rtype == "midday_restriction":
                # Outdoor midday window (e.g. 11:00–16:00) by effective dates / site
                win_start = _as_time(rule.get("window_start") or "11:00") or time(11, 0)
                win_end = _as_time(rule.get("window_end") or "16:00") or time(16, 0)
                rs = _as_date(rule.get("effective_start"))
                re_ = _as_date(rule.get("effective_end"))
                for row in work_rows:
                    d = _as_date(row.get("shift_date"))
                    if not d or (rs and d < rs) or (re_ and d > re_):
                        continue
                    if site_filter and str(row.get("site_key") or "") != str(site_filter):
                        continue
                    st = _as_time(row.get("start_time")) or time(0, 0)
                    et = _as_time(row.get("end_time")) or time(0, 0)
                    # Overlap with midday window on start day
                    if st < win_end and (et > win_start or bool(row.get("ends_next_day"))):
                        if st < win_end and (bool(row.get("ends_next_day")) or et > win_start):
                            findings.append({
                                "type": rtype,
                                "mode": mode,
                                "employee_key": row.get("employee_key"),
                                "shift_date": str(d),
                                "window": f"{win_start.strftime('%H:%M')}-{win_end.strftime('%H:%M')}",
                                "profile": profile.get("name"),
                                "site_key": row.get("site_key"),
                            })
                            if mode == "block":
                                blocks = True

            elif rtype == "daily_hours_warning":
                max_h = float(rule.get("max_daily_hours") or 10)
                for row in work_rows:
                    st = _as_time(row.get("start_time")) or time(0, 0)
                    et = _as_time(row.get("end_time")) or time(0, 0)
                    hrs = _hours_between(st, et, bool(row.get("ends_next_day")))
                    if hrs > max_h + 1e-6:
                        findings.append({
                            "type": rtype,
                            "mode": mode,
                            "employee_key": row.get("employee_key"),
                            "shift_date": str(row.get("shift_date"))[:10],
                            "hours": round(hrs, 2),
                            "max_daily_hours": max_h,
                            "profile": profile.get("name"),
                        })
                        if mode == "block":
                            blocks = True

            elif rtype == "weekly_hours_warning":
                max_w = float(rule.get("max_weekly_hours") or 48)
                buckets: dict[str, float] = {}
                for row in work_rows:
                    d = _as_date(row.get("shift_date"))
                    if not d:
                        continue
                    # Week starts Sunday (Kuwait common roster view)
                    week = (d - timedelta(days=(d.weekday() + 1) % 7)).isoformat()
                    key = f"{row.get('employee_key')}|{week}"
                    st = _as_time(row.get("start_time")) or time(0, 0)
                    et = _as_time(row.get("end_time")) or time(0, 0)
                    buckets[key] = buckets.get(key, 0.0) + _hours_between(st, et, bool(row.get("ends_next_day")))
                for key, hrs in buckets.items():
                    if hrs > max_w + 1e-6:
                        ek, week = key.split("|", 1)
                        findings.append({
                            "type": rtype,
                            "mode": mode,
                            "employee_key": ek,
                            "week_start": week,
                            "hours": round(hrs, 2),
                            "max_weekly_hours": max_w,
                            "profile": profile.get("name"),
                        })
                        if mode == "block":
                            blocks = True

            elif rtype == "weekly_rest_days":
                required = set(int(x) for x in (rule.get("rest_weekdays_sun0") or [5]) if int(x) in range(7))
                # Sun=0 … Sat=6
                worked: dict[str, set[int]] = {}
                for row in work_rows:
                    d = _as_date(row.get("shift_date"))
                    if not d:
                        continue
                    ek = str(row.get("employee_key") or "")
                    worked.setdefault(ek, set()).add((d.weekday() + 1) % 7)
                for ek, days_worked in worked.items():
                    missing = required - days_worked  # required rest days that still look free is inverted
                    # Warn when a required rest weekday has work
                    conflict_days = required & days_worked
                    if conflict_days:
                        findings.append({
                            "type": rtype,
                            "mode": mode,
                            "employee_key": ek,
                            "worked_on_rest_weekdays": sorted(conflict_days),
                            "profile": profile.get("name"),
                        })
                        if mode == "block":
                            blocks = True

            elif rtype == "public_holiday_warning":
                holidays = set()
                for h in rule.get("dates") or []:
                    hd = _as_date(h)
                    if hd:
                        holidays.add(hd)
                for row in work_rows:
                    d = _as_date(row.get("shift_date"))
                    if d and d in holidays:
                        findings.append({
                            "type": rtype,
                            "mode": mode,
                            "employee_key": row.get("employee_key"),
                            "shift_date": str(d),
                            "profile": profile.get("name"),
                        })
                        if mode == "block":
                            blocks = True

            elif rtype == "break_metadata_warning":
                min_break = float(rule.get("min_break_hours") or 0.5)
                max_consec = float(rule.get("max_consecutive_hours") or 6)
                for row in work_rows:
                    st = _as_time(row.get("start_time")) or time(0, 0)
                    et = _as_time(row.get("end_time")) or time(0, 0)
                    hrs = _hours_between(st, et, bool(row.get("ends_next_day")))
                    if hrs > max_consec + 1e-6:
                        findings.append({
                            "type": rtype,
                            "mode": mode,
                            "employee_key": row.get("employee_key"),
                            "shift_date": str(row.get("shift_date"))[:10],
                            "hours": round(hrs, 2),
                            "max_consecutive_hours": max_consec,
                            "min_break_hours": min_break,
                            "note": "break_metadata_only_no_payroll",
                            "profile": profile.get("name"),
                        })
                        if mode == "block":
                            blocks = True

    summary = {
        "findings": len(findings),
        "warnings": sum(1 for f in findings if f.get("mode") == "warn"),
        "blocks": sum(1 for f in findings if f.get("mode") == "block"),
        "blocks_publish": blocks,
        "profiles": len(profiles),
    }
    return {
        "ok": True,
        "summary": summary,
        "findings": findings,
        "blocks_publish": blocks,
        "payroll_money": False,
        **honesty_payload(),
    }


def publish_blocked_by_compliance(compliance: dict[str, Any] | None) -> bool:
    return bool((compliance or {}).get("blocks_publish"))


# --- PAM export ---------------------------------------------------------------

def build_pam_export(
    cur: Any,
    *,
    company_code: str,
    version_id: Any,
    locale: str = "both",
    actor_phone: str | None = None,
) -> dict[str, Any]:
    """Deterministic read-only PAM-style declaration from a published schedule version."""
    ensure_shifts_enterprise_wave6_schema(cur)
    company = (company_code or "").upper()
    if not shifts_wave6_enabled_for_company(company):
        return {"ok": False, "error": "shifts_wave6_disabled", **honesty_payload()}
    version = w5.get_version(cur, company_code=company, version_id=version_id)
    if not version:
        return {"ok": False, "error": "version_not_found"}
    if str(version.get("state")) != "published":
        return {"ok": False, "error": "version_not_published", "hint": "PAM export requires a published version"}
    period = w5.get_period(cur, company_code=company, period_id=version["period_id"])
    draft = w5.list_draft_rows(cur, company_code=company, version_id=version_id)
    work_rows = [
        r for r in draft
        if str(r.get("day_kind") or "work") == "work"
        and str(r.get("row_class") or "") not in NON_PUBLISH_ROW_CLASSES
    ]

    # Weekly rest inference from non-work draft rows when present
    rest_by_emp: dict[str, list[str]] = {}
    holidays: list[str] = []
    for r in draft:
        if str(r.get("day_kind")) == "rest":
            rest_by_emp.setdefault(str(r.get("employee_key") or ""), []).append(str(r.get("shift_date"))[:10])

    declared = []
    for r in sorted(work_rows, key=lambda x: (str(x.get("shift_date")), str(x.get("employee_key")))):
        declared.append({
            "employee_key": r.get("employee_key"),
            "employee_name": r.get("employee_name"),
            "date": str(r.get("shift_date"))[:10],
            "start_time": str(r.get("start_time"))[:8],
            "end_time": str(r.get("end_time"))[:8],
            "ends_next_day": bool(r.get("ends_next_day")),
            "break_minutes": None,  # metadata reserved; not invented
            "site_key": r.get("site_key"),
            "branch_key": r.get("branch_key"),
            "role": r.get("role"),
            "schedule_period_id": str(period.get("period_id") if period else ""),
            "schedule_version_id": str(version_id),
            "rotation_assignment_id": str(r.get("rotation_assignment_id") or "") or None,
        })

    unsupported = [
        {
            "code": "no_government_submission",
            "en": "Export is read-only. No submission to PAM or any government API is performed.",
            "ar": "التصدير للقراءة فقط. لا يتم الإرسال إلى نظام العمل الآلي أو أي واجهة حكومية.",
        },
        {
            "code": "manual_submission_required",
            "en": "Operator must review and submit manually through official channels if required.",
            "ar": "يجب على المشغّل المراجعة والإرسال يدوياً عبر القنوات الرسمية عند الحاجة.",
        },
        {
            "code": "breaks_not_inferred",
            "en": "Break minutes are not invented; include only when present on the published plan.",
            "ar": "دقائق الاستراحة لا تُختلق؛ تُدرج فقط إن وُجدت في الخطة المنشورة.",
        },
    ]

    payload = {
        "contract_version": PAM_EXPORT_CONTRACT_VERSION,
        "company_code": company,
        "period": {
            "period_id": str(period.get("period_id") if period else ""),
            "name": period.get("name") if period else None,
            "start_date": str(period.get("start_date") if period else "")[:10],
            "end_date": str(period.get("end_date") if period else "")[:10],
            "timezone": (period or {}).get("timezone") or "Asia/Kuwait",
            "site_key": (period or {}).get("site_key"),
            "branch_key": (period or {}).get("branch_key"),
        },
        "version": {
            "version_id": str(version_id),
            "version_no": version.get("version_no"),
            "fingerprint": version.get("fingerprint"),
            "published_at": str(version.get("published_at") or ""),
        },
        "declared_daily_working_periods": declared,
        "weekly_rest_days": rest_by_emp,
        "holidays": holidays,
        "payroll_money": False,
        "submission": False,
    }
    fingerprint = hashlib.sha256(json.dumps(_jsonable(payload), sort_keys=True, default=str).encode()).hexdigest()

    def _csv(rows: list[dict[str, Any]], lang: str) -> str:
        headers = (
            ["employee_key", "employee_name", "date", "start_time", "end_time", "ends_next_day", "site_key", "branch_key", "role", "version_id"]
            if lang == "en"
            else ["رمز_الموظف", "اسم_الموظف", "التاريخ", "بداية", "نهاية", "يمتد_لليوم_التالي", "الموقع", "الفرع", "الدور", "الإصدار"]
        )
        lines = [",".join(headers)]
        for r in rows:
            vals = [
                r.get("employee_key"),
                r.get("employee_name"),
                r.get("date"),
                r.get("start_time"),
                r.get("end_time"),
                r.get("ends_next_day"),
                r.get("site_key"),
                r.get("branch_key"),
                r.get("role"),
                r.get("schedule_version_id"),
            ]
            lines.append(",".join('"' + str(v if v is not None else "").replace('"', '""') + '"' for v in vals))
        return "\n".join(lines) + "\n"

    def _report(lang: str) -> str:
        if lang == "ar":
            return (
                f"تصدير إقرار جداول العمل (PAM) — عقد {PAM_EXPORT_CONTRACT_VERSION}\n"
                f"الشركة: {company}\n"
                f"الفترة: {payload['period']['name']} ({payload['period']['start_date']} → {payload['period']['end_date']})\n"
                f"الإصدار المنشور: {version_id} / بصمة {fingerprint[:16]}\n"
                f"عدد الفترات المعلنة: {len(declared)}\n"
                f"الحالة: يتطلب إرسالاً يدوياً — لا إرسال آلي\n"
                f"لا حساب مالي للرواتب في هذا التصدير.\n"
            )
        return (
            f"PAM-style working-time declaration — contract {PAM_EXPORT_CONTRACT_VERSION}\n"
            f"Company: {company}\n"
            f"Period: {payload['period']['name']} ({payload['period']['start_date']} → {payload['period']['end_date']})\n"
            f"Published version: {version_id} / fingerprint {fingerprint[:16]}\n"
            f"Declared periods: {len(declared)}\n"
            f"Status: manual_submission_required — no automated submission\n"
            f"No Payroll money calculation in this export.\n"
        )

    loc = str(locale or "both").lower()
    if loc not in {"en", "ar", "both"}:
        loc = "both"
    csv_en = _csv(declared, "en") if loc in {"en", "both"} else None
    csv_ar = _csv(declared, "ar") if loc in {"ar", "both"} else None
    report_en = _report("en") if loc in {"en", "both"} else None
    report_ar = _report("ar") if loc in {"ar", "both"} else None

    cur.execute(
        """
        INSERT INTO shift_pam_exports (
          company_code, period_id, version_id, export_contract_version, locale, status,
          fingerprint, payload, csv_en, csv_ar, report_en, report_ar, unsupported_notes, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,'manual_submission_required',%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            period.get("period_id") if period else None,
            version_id,
            PAM_EXPORT_CONTRACT_VERSION,
            loc,
            fingerprint,
            json.dumps(_jsonable(payload)),
            csv_en,
            csv_ar,
            report_en,
            report_ar,
            json.dumps(_jsonable(unsupported)),
            _digits_phone(actor_phone),
        ),
    )
    export_row = _row(cur)
    return {
        "ok": True,
        "export": export_row,
        "fingerprint": fingerprint,
        "contract_version": PAM_EXPORT_CONTRACT_VERSION,
        "csv_en": csv_en,
        "csv_ar": csv_ar,
        "report_en": report_en,
        "report_ar": report_ar,
        "unsupported_notes": unsupported,
        "submission": False,
        **honesty_payload(),
    }


def get_pam_export(cur: Any, *, company_code: str, export_id: Any) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM shift_pam_exports WHERE company_code=%s AND export_id=%s",
        ((company_code or "").upper(), str(export_id)),
    )
    return _row(cur)


def list_pam_exports(cur: Any, *, company_code: str, limit: int = 20) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT export_id, company_code, period_id, version_id, export_contract_version, locale, status,
               fingerprint, created_at, created_by_phone
        FROM shift_pam_exports
        WHERE company_code=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        ((company_code or "").upper(), max(1, min(100, int(limit)))),
    )
    return _rows(cur)
