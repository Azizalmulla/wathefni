#!/usr/bin/env python3
"""Shifts Wave 6B — production WATHEFNI synthetic rotations/compliance/PAM/notifications canary.

Markers: SHW6B / 965537* only. Real allowlists empty. Real mutation gate on.
Real reminders off. Real notification provider delivery off (mock adapters only).
Timers/jobs disabled. No real employee publishing, PAM submission, or Payroll money.

Proves: rotation patterns (four_on_four_off, panama_223, six_on_one_off,
alternating_day_night, hitch_n_n 14/14 with remote metadata, custom_sequence with
travel/rest/work/standby), compliance profile evaluation (warn-only), draft → review →
approve → publish with non-work rows skipped, PAM export from a published version,
multi-channel notification outbox (dedupe, channel ladder, ack-once, retry/terminal-failed,
drafts-do-not-notify, tenant isolation, invalidate-on-cancel), fingerprint stability, and
residual-zero cleanup (wave6b_scope).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")

# Wave 6 rotations/compliance/PAM gate — SHW6B markers only
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS", "SHW6B,SHW6B-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES", "965537")

# Wave 6B notifications outbox gate — mock adapters only, real delivery never enabled
os.environ.setdefault("WATHEFNI_SHIFTS_NOTIFICATIONS_WAVE6B", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_NOTIFICATIONS_WAVE6B_COMPANIES", "WATHEFNI")
os.environ["WATHEFNI_SHIFTS_NOTIFICATIONS_REAL_DELIVERY"] = "0"

# Wave 5 publish/open/coverage gate — include SHW6B so rotation drafts can publish
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY", "1")

# Wave 4 templates/recurrences gate — include SHW6B so SYNTHETIC_ONLY templates work
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY", "1")

# Real reminders/timers stay off; HR/manager allowlists assumed empty (verified via w3 checks below)
os.environ.setdefault("WATHEFNI_SHIFTS_REAL_REMINDERS", "0")


def _merge_env_csv(key: str, *values: str) -> None:
    existing = [p.strip() for p in (os.environ.get(key) or "").split(",") if p.strip()]
    for v in values:
        if v not in existing:
            existing.append(v)
    os.environ[key] = ",".join(existing) if existing else ",".join(values)


_merge_env_csv("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS", "SHW5B", "SHW5B-SYNTH|", "SHW6B", "SHW6B-SYNTH|")
_merge_env_csv("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES", "965535", "965537")
_merge_env_csv("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS", "SHW4B", "SHW4B-SYNTH|", "SHW6B", "SHW6B-SYNTH|")
_merge_env_csv("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES", "965533", "965537")

import app  # noqa: E402
import shifts_enterprise_wave6 as w6  # noqa: E402
import shifts_publish_wave5 as w5  # noqa: E402
import shifts_templates_wave4 as w4  # noqa: E402
import shifts_wave3_controlled as w3  # noqa: E402
import shifts_schedule_integrity_wave2 as w2  # noqa: E402
import shifts_notifications_wave6b as n6  # noqa: E402
from shifts_synthetic_cleanup import (  # noqa: E402
    CLEANUP_CONTRACT_VERSION,
    cleanup_synthetic_scope,
    count_synthetic_residuals,
    wave6b_scope,
)

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW6B_TAG") or uuid.uuid4().hex[:8].upper()
EVID = Path(os.environ.get("SHW6B_EVID") or f"/tmp/shw6b-prod-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

KEY = f"WATHEFNI-SHW6B-{TAG}"
KEY_B = f"WATHEFNI-SHW6B-B-{TAG}"
_digits = "".join(ch for ch in TAG if ch.isdigit()) or "123456"
PHONE = f"965537{_digits[:6].ljust(6, '0')}"
PHONE_B = f"965537{_digits[1:6].ljust(5, '0')}9"
NAME = f"SHW6B-SYNTH| Emp {TAG}"
NAME_B = f"SHW6B-SYNTH| EmpB {TAG}"
ACTOR = "96588009911"

PASS = FAIL = 0
RESULTS: dict = {"tag": TAG, "checks": [], "ids": {}}

ACKS = {
    "acknowledge_availability": True,
    "ack_availability_conflict": True,
    "allow_availability_conflicts": True,
    "allow_leave_conflicts": True,
    "ack_leave_conflict": True,
    "acknowledge_seasonal": True,
    "ack_seasonal": True,
    "confirm_overlap": True,
}


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    RESULTS["checks"].append({"name": name, "ok": bool(ok), "detail": detail if not ok else None})
    if ok:
        PASS += 1
        print(f"PASS  {name}", flush=True)
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}", flush=True)


def fp_assignment(r: dict) -> str:
    parts = [
        str(r.get(k) or "")
        for k in (
            "shift_id",
            "employee_key",
            "employee_phone",
            "shift_date",
            "start_time",
            "end_time",
            "status",
            "updated_at",
            "role",
            "location",
            "timezone",
            "source_kind",
            "occurrence_key",
            "regen_detached",
            "schedule_period_id",
            "schedule_version_id",
            "schedule_source",
        )
    ]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def fp_simple(r: dict, keys: tuple[str, ...]) -> str:
    return hashlib.md5("|".join(str(r.get(k) or "") for k in keys).encode()).hexdigest()


def seed_employee(cur, key: str, name: str, phone: str) -> None:
    raw = {"shw6b": True, "tag": TAG}
    payload = json.dumps(raw)
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
        ON CONFLICT DO NOTHING
        """,
        (COMPANY, key, name, phone, payload),
    )
    cur.execute(
        """
        UPDATE employees SET name=%s, phone=%s, employment_status='active', raw_json=%s::jsonb, updated_at=now()
        WHERE company_code=%s AND employee_key=%s
        """,
        (name, phone, payload, COMPANY, key),
    )
    cur.execute("SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s", (COMPANY, key))
    if not cur.fetchone():
        raise RuntimeError(f"failed to seed {key}")


def snapshot_real_fps(cur) -> dict:
    """Fingerprint non-SHW6B real schedule lineage for drift detection."""
    out: dict = {
        "assignments": {},
        "templates": {},
        "rotation_patterns": {},
        "rotation_assignments": {},
        "compliance_profiles": {},
        "notification_events": {},
        "channel_preferences": {},
        "schedule_periods": {},
        "schedule_versions": {},
        "events": 0,
    }
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name='shift_assignments' AND column_name='source_kind'
        """
    )
    has_prov = bool(cur.fetchone())
    if has_prov:
        cur.execute(
            """
            SELECT shift_id::text, employee_key, coalesce(employee_phone,'') employee_phone, shift_date::text,
                   start_time::text, end_time::text, status, updated_at::text,
                   coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone,
                   coalesce(source_kind,'manual') source_kind, coalesce(occurrence_key,'') occurrence_key,
                   coalesce(regen_detached,false) regen_detached,
                   coalesce(schedule_period_id::text,'') schedule_period_id,
                   coalesce(schedule_version_id::text,'') schedule_version_id,
                   coalesce(schedule_source,'') schedule_source
            FROM shift_assignments
            WHERE company_code=%s
              AND coalesce(employee_key,'') NOT LIKE '%%SHW6B%%'
              AND coalesce(employee_phone,'') NOT LIKE '965537%%'
              AND coalesce(occurrence_key,'') NOT LIKE '%%SHW6B%%'
            ORDER BY shift_id::text
            """,
            (COMPANY,),
        )
    else:
        cur.execute(
            """
            SELECT shift_id::text, employee_key, coalesce(employee_phone,'') employee_phone, shift_date::text,
                   start_time::text, end_time::text, status, updated_at::text,
                   coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone
            FROM shift_assignments
            WHERE company_code=%s
              AND coalesce(employee_key,'') NOT LIKE '%%SHW6B%%'
              AND coalesce(employee_phone,'') NOT LIKE '965537%%'
            ORDER BY shift_id::text
            """,
            (COMPANY,),
        )
    for r in cur.fetchall():
        d = dict(r)
        out["assignments"][d["shift_id"]] = fp_assignment(d)

    try:
        cur.execute(
            """
            SELECT template_id::text, name, status, start_time::text, end_time::text,
                   planning_version, updated_at::text
            FROM shift_templates
            WHERE company_code=%s AND name NOT LIKE '%%SHW6B%%'
            ORDER BY template_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["templates"][d["template_id"]] = fp_simple(
                d, ("template_id", "name", "status", "start_time", "end_time", "planning_version", "updated_at")
            )
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        w4.ensure_shifts_templates_wave4_schema(cur)

    try:
        w6.ensure_shifts_enterprise_wave6_schema(cur)
        cur.execute(
            """
            SELECT pattern_id::text, name, status, pattern_kind, updated_at::text
            FROM shift_rotation_patterns
            WHERE company_code=%s AND name NOT LIKE '%%SHW6B%%'
            ORDER BY pattern_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["rotation_patterns"][d["pattern_id"]] = fp_simple(
                d, ("pattern_id", "name", "status", "pattern_kind", "updated_at")
            )

        cur.execute(
            """
            SELECT assignment_id::text, name, status, target_key, cycle_offset::text, updated_at::text
            FROM shift_rotation_assignments
            WHERE company_code=%s AND name NOT LIKE '%%SHW6B%%' AND coalesce(target_key,'') NOT LIKE '%%SHW6B%%'
            ORDER BY assignment_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["rotation_assignments"][d["assignment_id"]] = fp_simple(
                d, ("assignment_id", "name", "status", "target_key", "cycle_offset", "updated_at")
            )

        cur.execute(
            """
            SELECT name, enabled::text, default_enforcement, updated_at::text
            FROM shift_compliance_profiles
            WHERE company_code=%s AND name NOT LIKE '%%SHW6B%%'
            ORDER BY name
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["compliance_profiles"][d["name"]] = fp_simple(
                d, ("name", "enabled", "default_enforcement", "updated_at")
            )
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass

    try:
        n6.ensure_shifts_notifications_wave6b_schema(cur)
        cur.execute(
            """
            SELECT event_id::text, event_type, employee_key, status, updated_at::text
            FROM shift_notification_events
            WHERE company_code=%s AND coalesce(employee_key,'') NOT LIKE '%%SHW6B%%'
            ORDER BY event_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["notification_events"][d["event_id"]] = fp_simple(
                d, ("event_id", "event_type", "employee_key", "status", "updated_at")
            )

        cur.execute(
            """
            SELECT preference_id::text, scope_type, scope_key, updated_at::text
            FROM shift_channel_preferences
            WHERE company_code=%s AND coalesce(scope_key,'') NOT LIKE '%%SHW6B%%'
            ORDER BY preference_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["channel_preferences"][d["preference_id"]] = fp_simple(
                d, ("preference_id", "scope_type", "scope_key", "updated_at")
            )
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass

    try:
        w5.ensure_shifts_publish_wave5_schema(cur)
        cur.execute(
            """
            SELECT period_id::text, name, status, start_date::text, end_date::text, updated_at::text
            FROM shift_schedule_periods
            WHERE company_code=%s AND name NOT LIKE '%%SHW6B%%'
            ORDER BY period_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["schedule_periods"][d["period_id"]] = fp_simple(
                d, ("period_id", "name", "status", "start_date", "end_date", "updated_at")
            )

        cur.execute(
            """
            SELECT v.version_id::text, v.period_id::text, v.version_no::text, v.state, v.updated_at::text
            FROM shift_schedule_versions v
            JOIN shift_schedule_periods p ON p.period_id=v.period_id
            WHERE v.company_code=%s AND p.name NOT LIKE '%%SHW6B%%'
            ORDER BY v.version_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["schedule_versions"][d["version_id"]] = fp_simple(
                d, ("version_id", "period_id", "version_no", "state", "updated_at")
            )
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass

    try:
        cur.execute(
            """
            SELECT count(*) AS c FROM shift_events
            WHERE company_code=%s
              AND shift_id IN (
                SELECT shift_id FROM shift_assignments
                WHERE company_code=%s
                  AND coalesce(employee_key,'') NOT LIKE '%%SHW6B%%'
                  AND coalesce(employee_phone,'') NOT LIKE '965537%%'
              )
            """,
            (COMPANY, COMPANY),
        )
        out["events"] = int(dict(cur.fetchone())["c"])
    except Exception:
        out["events"] = -1

    return out


def main() -> int:
    print(f"SHW6B prod canary tag={TAG} evid={EVID} cleanup={CLEANUP_CONTRACT_VERSION}", flush=True)
    app.send_octopus_whatsapp = lambda *a, **k: {"ok": True, "skipped": "shw6b"}  # type: ignore
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "skipped": "shw6b"}  # type: ignore
    app.notify_employee_shift_created = lambda *a, **k: {"ok": True, "skipped": "shw6b"}  # type: ignore
    app.notify_employee_shift_cancelled = lambda *a, **k: {"ok": True, "skipped": "shw6b"}  # type: ignore
    app.notify_hr_admins = lambda *a, **k: {"ok": True, "skipped": "shw6b"}  # type: ignore
    n6.reset_mock_ledger()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
    check("db_is_wathefni", db == "wathefni", db)

    check("wave6_enabled", w6.shifts_wave6_enabled())
    check("wave6_company", w6.shifts_wave6_enabled_for_company(COMPANY))
    check("wave6_synthetic_only", w6.shifts_wave6_synthetic_only())
    check("version_6_0_0", w6.SHIFTS_WAVE6_VERSION == "6.0.0")
    check("shw6b_synth_w6", w6.is_wave6_synthetic_employee(employee_key=KEY, phone=PHONE, name=NAME))
    check("real_phone_not_synth_w6", not w6.is_wave6_synthetic_employee(employee_key="EMP-1", phone="96550001111"))

    check("notifications_wave6b_enabled", n6.shifts_notifications_wave6b_enabled())
    check("notifications_wave6b_company", n6.shifts_notifications_wave6b_enabled_for_company(COMPANY))
    check("notifications_version_6_1_0", n6.SHIFTS_NOTIFICATIONS_WAVE6B_VERSION == "6.1.0")
    check("real_delivery_blocked", n6.real_delivery_blocked())

    check("w5_synth_w6b", w5.is_wave5_synthetic_employee(employee_key=KEY, phone=PHONE, name=NAME))
    check("w4_synth_w6b", w4.is_wave4_synthetic_employee(employee_key=KEY, phone=PHONE, name=NAME))

    check("w3_gate_on", w3.real_mutation_gate_enabled())
    check("allowlists_empty", not w3.hr_mutation_allowlist() and not w3.manager_mutation_allowlist())
    check("real_reminders_off", not w3.real_reminders_enabled())
    check(
        "real_mutation_blocked",
        w3.real_mutation_denied(actor_phone=ACTOR, is_synthetic_subject=False, company_code=COMPANY) is not None,
    )
    check(
        "synth_mutation_allowed",
        w3.real_mutation_denied(actor_phone=ACTOR, is_synthetic_subject=True, company_code=COMPANY) is None,
    )

    h6 = w6.honesty_payload()
    check("honesty_rotations_true", h6.get("rotations") is True)
    check("honesty_remote_rosters_true", h6.get("remote_rosters") is True)
    check("honesty_pam_export_true", h6.get("pam_export") is True)
    check("honesty_pam_submission_false", h6.get("pam_submission") is False)
    check("honesty_compliance_profiles_true", h6.get("compliance_profiles") is True)
    check("honesty_payroll_false", h6.get("payroll_money") is False)
    check("honesty_leave_false", h6.get("leave_balances_mutated") is False)
    check("honesty_attendance_false", h6.get("attendance_authority_mutated") is False)

    hn6 = n6.honesty_payload()
    check("notif_honesty_multi_channel_true", hn6.get("multi_channel_outbox") is True)
    check("notif_honesty_real_provider_false", hn6.get("real_provider_delivery") is False)
    check("notif_honesty_mock_only_true", hn6.get("mock_adapters_only") is True)
    check("notif_honesty_drafts_do_not_notify_true", hn6.get("drafts_do_not_notify") is True)
    check("notif_honesty_payroll_false", hn6.get("payroll_money") is False)
    check("notif_honesty_pam_submission_false", hn6.get("pam_submission") is False)
    check("notif_honesty_whatsapp_channel", "whatsapp" in (hn6.get("channels") or []))
    check("notif_honesty_teams_channel", "teams" in (hn6.get("channels") or []))
    check("notif_honesty_telegram_channel", "telegram" in (hn6.get("channels") or []))
    check("notif_honesty_email_channel", "email" in (hn6.get("channels") or []))
    check("notif_honesty_sms_channel", "sms" in (hn6.get("channels") or []))

    check("w5_honesty_rotations_false", w5.honesty_payload().get("rotations") is False)
    check("w4_honesty_publishing_false", w4.honesty_payload().get("publishing") is False)
    check("w3_honesty_templates_false", w3.honesty_payload().get("templates") is False)

    src6 = Path(w6.__file__).read_text(encoding="utf-8")
    check("no_leave_balances_sql_w6", "UPDATE leave_balances" not in src6 and "INSERT INTO leave_balances" not in src6)
    src_n6 = Path(n6.__file__).read_text(encoding="utf-8")
    check("no_real_provider_send_sql_n6", "requests.post" not in src_n6 and "twilio" not in src_n6.lower())
    check("cleanup_contract_1_4", CLEANUP_CONTRACT_VERSION.startswith("1.4"))

    today = date.today()
    start1 = today + timedelta(days=7)
    end1 = today + timedelta(days=20)
    start2 = today + timedelta(days=21)
    end2 = today + timedelta(days=34)

    known_ids: dict[str, object] = {"shift_ids": [], "version_ids": []}
    before: dict = {}

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w6.ensure_shifts_enterprise_wave6_schema(cur)
            n6.ensure_shifts_notifications_wave6b_schema(cur)
            w4.ensure_shifts_templates_wave4_schema(cur)
            before = snapshot_real_fps(cur)
            (EVID / "fps-before.json").write_text(json.dumps(before, indent=2, default=str))
            RESULTS["fps_before_counts"] = {k: (len(v) if isinstance(v, dict) else v) for k, v in before.items()}

            seed_employee(cur, KEY, NAME, PHONE)
            seed_employee(cur, KEY_B, NAME_B, PHONE_B)
        conn.commit()

    # --- Templates + rotation patterns + assignments ---------------------------
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            day_t = w4.create_template(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW6B Day {TAG}", "start_time": "09:00", "end_time": "17:00", "role": "ops", "site_key": "SHW6B-SITE"},
            )
            check("day_template", day_t.get("ok"), day_t)
            day_id = str((day_t.get("template") or {}).get("template_id"))

            night_t = w4.create_template(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW6B Night {TAG}", "start_time": "22:00", "end_time": "06:00"},
            )
            check("night_template_ends_next_day", night_t.get("ok") and bool((night_t.get("template") or {}).get("ends_next_day")), night_t)
            night_id = str((night_t.get("template") or {}).get("template_id"))

            pattern_4on4 = w6.create_rotation_pattern(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW6B 4x4 {TAG}", "pattern_kind": "four_on_four_off", "day_template_id": day_id},
                actor_phone=PHONE,
            )
            check("pattern_four_on_four_off", pattern_4on4.get("ok"), pattern_4on4)
            pattern_4on4_id = str((pattern_4on4.get("pattern") or {}).get("pattern_id"))

            pattern_panama = w6.create_rotation_pattern(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW6B Panama {TAG}", "pattern_kind": "panama_223", "day_template_id": day_id},
                actor_phone=PHONE,
            )
            check("pattern_panama_223", pattern_panama.get("ok"), pattern_panama)
            pattern_panama_id = str((pattern_panama.get("pattern") or {}).get("pattern_id"))

            pattern_6on1 = w6.create_rotation_pattern(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW6B 6on1 {TAG}", "pattern_kind": "six_on_one_off", "day_template_id": day_id},
                actor_phone=PHONE,
            )
            check("pattern_six_on_one_off", pattern_6on1.get("ok"), pattern_6on1)
            pattern_6on1_id = str((pattern_6on1.get("pattern") or {}).get("pattern_id"))

            pattern_altdn = w6.create_rotation_pattern(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW6B AltDN {TAG}",
                    "pattern_kind": "alternating_day_night",
                    "day_template_id": day_id,
                    "night_template_id": night_id,
                },
                actor_phone=PHONE,
            )
            check("pattern_alternating_day_night", pattern_altdn.get("ok"), pattern_altdn)
            pattern_altdn_id = str((pattern_altdn.get("pattern") or {}).get("pattern_id"))

            pattern_hitch = w6.create_rotation_pattern(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW6B Hitch {TAG}",
                    "pattern_kind": "hitch_n_n",
                    "hitch_on_days": 14,
                    "hitch_off_days": 14,
                    "travel_edges": True,
                    "day_template_id": day_id,
                    "remote_defaults": {"remote_site_key": "SHW6B-CAMP-1", "transport_required": True},
                },
                actor_phone=PHONE,
            )
            check("pattern_hitch_n_n_14_14", pattern_hitch.get("ok"), pattern_hitch)
            pattern_hitch_id = str((pattern_hitch.get("pattern") or {}).get("pattern_id"))

            pattern_custom = w6.create_rotation_pattern(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW6B Custom {TAG}",
                    "pattern_kind": "custom_sequence",
                    "day_template_id": day_id,
                    "cycle_sequence": [
                        {"kind": "travel", "template_slot": "primary"},
                        {"kind": "work", "template_slot": "primary"},
                        {"kind": "work", "template_slot": "primary"},
                        {"kind": "standby", "template_slot": "primary"},
                        {"kind": "rest", "template_slot": "primary"},
                        {"kind": "rest", "template_slot": "primary"},
                        {"kind": "travel", "template_slot": "primary"},
                    ],
                },
                actor_phone=PHONE,
            )
            check("pattern_custom_sequence", pattern_custom.get("ok"), pattern_custom)
            pattern_custom_id = str((pattern_custom.get("pattern") or {}).get("pattern_id"))

            assign_4on4 = w6.assign_rotation(
                cur,
                company_code=COMPANY,
                payload={
                    "pattern_id": pattern_4on4_id,
                    "target_type": "employee",
                    "target_key": KEY,
                    "employee_key": KEY,
                    "employee_name": NAME,
                    "employee_phone": PHONE,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 0,
                },
                actor_phone=PHONE,
            )
            check("assign_four_on_four_off", assign_4on4.get("ok"), assign_4on4)
            assign_4on4_id = str((assign_4on4.get("assignment") or {}).get("assignment_id"))

            assign_altdn = w6.assign_rotation(
                cur,
                company_code=COMPANY,
                payload={
                    "pattern_id": pattern_altdn_id,
                    "target_type": "employee",
                    "target_key": KEY_B,
                    "employee_key": KEY_B,
                    "employee_name": NAME_B,
                    "employee_phone": PHONE_B,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 4,
                },
                actor_phone=PHONE,
            )
            check("assign_alternating_day_night", assign_altdn.get("ok"), assign_altdn)
            assign_altdn_id = str((assign_altdn.get("assignment") or {}).get("assignment_id"))

            assign_hitch = w6.assign_rotation(
                cur,
                company_code=COMPANY,
                payload={
                    "pattern_id": pattern_hitch_id,
                    "target_type": "employee",
                    "target_key": KEY,
                    "employee_key": KEY,
                    "employee_name": NAME,
                    "employee_phone": PHONE,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 7,
                    "remote_site_key": "SHW6B-CAMP-1",
                    "camp_key": "SHW6B-CAMP-1-BLOCK-A",
                    "transport_required": True,
                    "transport_group": f"SHW6B-BUS-{TAG}",
                    "pickup_location": "SHW6B-GATE-2",
                    "accommodation_required": True,
                    "mobilization_date": start1.isoformat(),
                    "demobilization_date": end2.isoformat(),
                },
                actor_phone=PHONE,
            )
            check("assign_hitch_n_n", assign_hitch.get("ok"), assign_hitch)
            assign_hitch_id = str((assign_hitch.get("assignment") or {}).get("assignment_id"))
            hitch_row = assign_hitch.get("assignment") or {}
            check("hitch_remote_metadata_present", bool(hitch_row.get("remote_site_key")) and bool(hitch_row.get("transport_required")), hitch_row)
            check(
                "hitch_offset_differs_from_4on4",
                int(hitch_row.get("cycle_offset") or -1) != int((assign_4on4.get("assignment") or {}).get("cycle_offset") or -1),
                hitch_row,
            )

            assign_panama = w6.assign_rotation(
                cur,
                company_code=COMPANY,
                payload={
                    "pattern_id": pattern_panama_id,
                    "target_type": "employee",
                    "target_key": KEY_B,
                    "employee_key": KEY_B,
                    "employee_name": NAME_B,
                    "employee_phone": PHONE_B,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 2,
                },
                actor_phone=PHONE,
            )
            check("assign_panama_223", assign_panama.get("ok"), assign_panama)
            assign_panama_id = str((assign_panama.get("assignment") or {}).get("assignment_id"))

            assign_6on1 = w6.assign_rotation(
                cur,
                company_code=COMPANY,
                payload={
                    "pattern_id": pattern_6on1_id,
                    "target_type": "employee",
                    "target_key": KEY,
                    "employee_key": KEY,
                    "employee_name": NAME,
                    "employee_phone": PHONE,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 1,
                },
                actor_phone=PHONE,
            )
            check("assign_six_on_one_off", assign_6on1.get("ok"), assign_6on1)
            assign_6on1_id = str((assign_6on1.get("assignment") or {}).get("assignment_id"))

            assign_custom = w6.assign_rotation(
                cur,
                company_code=COMPANY,
                payload={
                    "pattern_id": pattern_custom_id,
                    "target_type": "employee",
                    "target_key": KEY_B,
                    "employee_key": KEY_B,
                    "employee_name": NAME_B,
                    "employee_phone": PHONE_B,
                    "cycle_anchor_date": start1.isoformat(),
                    "effective_start": start1.isoformat(),
                    "cycle_offset": 0,
                },
                actor_phone=PHONE,
            )
            check("assign_custom_sequence", assign_custom.get("ok"), assign_custom)
            assign_custom_id = str((assign_custom.get("assignment") or {}).get("assignment_id"))

            preview_hitch = w6.preview_rotation(cur, company_code=COMPANY, assignment_id=assign_hitch_id)
            check("preview_hitch_ok", preview_hitch.get("ok"), preview_hitch)
            counts_hitch = preview_hitch.get("counts") or {}
            check("preview_hitch_work_gt_0", counts_hitch.get("work", 0) > 0, counts_hitch)
            check("preview_hitch_rest_gt_0", counts_hitch.get("rest", 0) > 0, counts_hitch)
            check("preview_hitch_travel_gt_0", counts_hitch.get("travel", 0) > 0, counts_hitch)
            check("preview_hitch_remote_fields", bool((preview_hitch.get("remote") or {}).get("remote_site_key")), preview_hitch.get("remote"))

            preview_custom = w6.preview_rotation(cur, company_code=COMPANY, assignment_id=assign_custom_id)
            check("preview_custom_ok", preview_custom.get("ok"), preview_custom)
            counts_custom = preview_custom.get("counts") or {}
            check("preview_custom_work_gt_0", counts_custom.get("work", 0) > 0, counts_custom)
            check("preview_custom_rest_gt_0", counts_custom.get("rest", 0) > 0, counts_custom)
            check("preview_custom_travel_gt_0", counts_custom.get("travel", 0) > 0, counts_custom)
            check("preview_custom_standby_gt_0", counts_custom.get("standby", 0) > 0, counts_custom)

            preview_panama = w6.preview_rotation(cur, company_code=COMPANY, assignment_id=assign_panama_id)
            check("preview_panama_ok", preview_panama.get("ok"), preview_panama)
            preview_6on1 = w6.preview_rotation(cur, company_code=COMPANY, assignment_id=assign_6on1_id)
            check("preview_six_on_one_off_ok", preview_6on1.get("ok"), preview_6on1)
        conn.commit()

    # --- Period 1: four-on-four-off draft -> compliance -> review -> publish ---
    version1_id = ""
    period1_id = ""
    period2_id = ""
    pub1: dict = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            period1_res = w5.create_period(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW6B Period {TAG}",
                    "start_date": start1.isoformat(),
                    "end_date": end1.isoformat(),
                    "require_publish": True,
                },
                actor_phone=PHONE,
            )
            check("create_period1", period1_res.get("ok"), period1_res)
            period1_id = str((period1_res.get("period") or {}).get("period_id"))
            version1_id = str((period1_res.get("version") or {}).get("version_id"))
            known_ids["period_id"] = period1_id
            known_ids["version_ids"] = [version1_id]

            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'",
                (COMPANY, KEY),
            )
            l0_before = int(dict(cur.fetchone())["c"])

            draft1 = w6.generate_draft_from_rotation(
                cur,
                company_code=COMPANY,
                period_id=period1_id,
                assignment_id=assign_4on4_id,
                actor_phone=PHONE,
                action_acks=ACKS,
                include_non_work_rows=True,
            )
            check("generate_draft_from_rotation_ok", draft1.get("ok"), draft1)
            check("draft_rows_gt_0", int(draft1.get("draft_rows") or 0) > 0, draft1.get("draft_rows"))
            check("l0_written_false", draft1.get("l0_written") is False, draft1)

            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'",
                (COMPANY, KEY),
            )
            l0_after_draft = int(dict(cur.fetchone())["c"])
            check("L0_unchanged_after_draft", l0_after_draft == l0_before, {"before": l0_before, "after": l0_after_draft})

            draft_rows = w5.list_draft_rows(cur, company_code=COMPANY, version_id=version1_id)
            day_kinds = {r.get("day_kind") for r in draft_rows}
            check("draft_includes_work", "work" in day_kinds, day_kinds)
            check("draft_includes_rest", "rest" in day_kinds, day_kinds)

            work_rows = sorted((r for r in draft_rows if r.get("day_kind") == "work"), key=lambda r: str(r.get("shift_date")))
            check("at_least_one_work_row", len(work_rows) > 0, len(work_rows))
            work_date = date.fromisoformat(str(work_rows[0]["shift_date"])[:10])
            weekday_sun0 = (work_date.weekday() + 1) % 7

            profile = w6.upsert_compliance_profile(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW6B Compliance {TAG}",
                    "sector_key": "industrial",
                    "enabled": True,
                    "default_enforcement": "warn",
                    "effective_start": start1.isoformat(),
                    "effective_end": end1.isoformat(),
                    "rules": [
                        {
                            "type": "ramadan_hours",
                            "enforcement": "warn",
                            "max_daily_hours": 6,
                            "effective_start": start1.isoformat(),
                            "effective_end": end1.isoformat(),
                        },
                        {
                            "type": "midday_restriction",
                            "enforcement": "warn",
                            "window_start": "11:00",
                            "window_end": "16:00",
                            "effective_start": start1.isoformat(),
                            "effective_end": end1.isoformat(),
                        },
                        {"type": "daily_hours_warning", "enforcement": "warn", "max_daily_hours": 6},
                        {"type": "weekly_rest_days", "enforcement": "warn", "rest_weekdays_sun0": [weekday_sun0]},
                        {"type": "public_holiday_warning", "enforcement": "warn", "dates": [work_date.isoformat()]},
                    ],
                },
                actor_phone=PHONE,
            )
            check("compliance_profile_upsert", profile.get("ok"), profile)

            compliance = w6.evaluate_compliance_for_version(cur, company_code=COMPANY, version_id=version1_id, period=period1_res.get("period"))
            check("compliance_evaluate_ok", compliance.get("ok"), compliance)
            check("compliance_payroll_false", compliance.get("payroll_money") is False, compliance)
            findings = compliance.get("findings") or []
            types_found = {f.get("type") for f in findings}
            check("compliance_ramadan_hours_warn", any(f.get("type") == "ramadan_hours" and f.get("mode") == "warn" for f in findings), findings)
            check("compliance_midday_restriction_warn", any(f.get("type") == "midday_restriction" and f.get("mode") == "warn" for f in findings), findings)
            check("compliance_daily_hours_warning_present", "daily_hours_warning" in types_found, types_found)
            check("compliance_weekly_rest_days_present", "weekly_rest_days" in types_found, types_found)
            check("compliance_public_holiday_warning_present", "public_holiday_warning" in types_found, types_found)
            check("compliance_blocks_publish_false", compliance.get("blocks_publish") is False, compliance)

            tr1 = w5.transition_version(cur, company_code=COMPANY, version_id=version1_id, to_state="in_review", actor_phone=PHONE)
            check("transition_in_review", tr1.get("ok"), tr1)
            diff = w5.review_diff(cur, company_code=COMPANY, version_id=version1_id)
            check("review_diff_ok", diff.get("ok"), diff)
            tr_return = w5.transition_version(
                cur, company_code=COMPANY, version_id=version1_id, to_state="draft", actor_phone=PHONE, note=f"SHW6B return {TAG}"
            )
            check("return_to_draft_with_note", tr_return.get("ok"), tr_return)
            tr2 = w5.transition_version(cur, company_code=COMPANY, version_id=version1_id, to_state="in_review", actor_phone=PHONE)
            check("transition_in_review_again", tr2.get("ok"), tr2)
            tr3 = w5.transition_version(cur, company_code=COMPANY, version_id=version1_id, to_state="approved", actor_phone=PHONE)
            check("transition_approved", tr3.get("ok"), tr3)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pub1 = w5.publish_version(
                cur,
                company_code=COMPANY,
                version_id=version1_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                publish_idempotency_key=f"SHW6B-PUB1|{TAG}",
                action_acks=ACKS,
            )
            check("publish_version1_ok", pub1.get("ok"), pub1)
            results1 = pub1.get("results") or {}
            check("publish_created_work_rows", int(results1.get("created") or 0) > 0, results1)
            check("publish_skipped_non_work_rows", int(results1.get("skipped_non_work") or 0) > 0, results1)
            if results1.get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(results1["created_ids"])

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND schedule_version_id=%s AND schedule_source='published' AND status <> 'cancelled'
                """,
                (COMPANY, version1_id),
            )
            pub_l0 = int(dict(cur.fetchone())["c"])
            check("published_L0_rows_present", pub_l0 > 0, pub_l0)

            pub1b = w5.publish_version(
                cur,
                company_code=COMPANY,
                version_id=version1_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                publish_idempotency_key=f"SHW6B-PUB1|{TAG}",
                action_acks=ACKS,
            )
            check("republish_idempotent", pub1b.get("ok") and pub1b.get("idempotent") is True, pub1b)

            lock_key = w5.publish_lock_key(COMPANY, period1_id)
            lock_result: dict = {}

            def other_publish():
                with app.db_connect() as c2:
                    with c2.cursor() as cur2:
                        lock_result["res"] = w5.publish_version(
                            cur2,
                            company_code=COMPANY,
                            version_id=version1_id,
                            create_fn=app.create_shift_assignment,
                            actor_phone=PHONE,
                            action_acks=ACKS,
                        )
                    c2.commit()

            got_lock = w2.try_job_lock(cur, lock_key)
            check("test_lock_acquired", got_lock)
            t = threading.Thread(target=other_publish)
            t.start()
            t.join(timeout=15)
            w2.release_job_lock(cur, lock_key)
            t.join(timeout=30)
            check(
                "concurrent_publish_lock_held",
                (lock_result.get("res") or {}).get("error") == "publish_lock_held",
                lock_result.get("res"),
            )
            check("concurrent_worker_finished", not t.is_alive(), "worker still running")
        conn.commit()

    # --- Period 2: alternating day/night (overnight) draft -> publish ----------
    version2_id = ""
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            period2_res = w5.create_period(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW6B Overnight Period {TAG}",
                    "start_date": start2.isoformat(),
                    "end_date": end2.isoformat(),
                    "require_publish": True,
                },
                actor_phone=PHONE,
            )
            check("create_period2_overnight", period2_res.get("ok"), period2_res)
            period2_id = str((period2_res.get("period") or {}).get("period_id"))
            version2_id = str((period2_res.get("version") or {}).get("version_id"))
            known_ids["version_ids"] = list(known_ids.get("version_ids") or []) + [version2_id]

            draft2 = w6.generate_draft_from_rotation(
                cur,
                company_code=COMPANY,
                period_id=period2_id,
                assignment_id=assign_altdn_id,
                actor_phone=PHONE,
                action_acks=ACKS,
            )
            check("generate_draft_from_rotation_altdn_ok", draft2.get("ok"), draft2)
            check("draft2_l0_written_false", draft2.get("l0_written") is False, draft2)

            tr_b1 = w5.transition_version(cur, company_code=COMPANY, version_id=version2_id, to_state="in_review", actor_phone=PHONE)
            check("transition_altdn_in_review", tr_b1.get("ok"), tr_b1)
            tr_b2 = w5.transition_version(cur, company_code=COMPANY, version_id=version2_id, to_state="approved", actor_phone=PHONE)
            check("transition_altdn_approved", tr_b2.get("ok"), tr_b2)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pub2 = w5.publish_version(
                cur,
                company_code=COMPANY,
                version_id=version2_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                publish_idempotency_key=f"SHW6B-PUB2|{TAG}",
                action_acks=ACKS,
            )
            check("publish_altdn_version_ok", pub2.get("ok"), pub2)
            results2 = pub2.get("results") or {}
            check("publish_altdn_created_rows", int(results2.get("created") or 0) > 0, results2)
            if results2.get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(results2["created_ids"])

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND schedule_version_id=%s
                  AND ends_next_day=true AND schedule_source='published' AND status <> 'cancelled'
                """,
                (COMPANY, KEY_B, version2_id),
            )
            overnight_l0 = int(dict(cur.fetchone())["c"])
            check("overnight_L0_rows_via_night_template", overnight_l0 > 0, overnight_l0)
        conn.commit()

    # --- PAM export from published version --------------------------------------
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pam = w6.build_pam_export(cur, company_code=COMPANY, version_id=version1_id, locale="both", actor_phone=PHONE)
            check("pam_export_ok", pam.get("ok"), pam)
            check("pam_export_fingerprint_present", bool(pam.get("fingerprint")), pam.get("fingerprint"))
            check("pam_export_csv_en_present", bool(pam.get("csv_en")), pam.get("csv_en") is not None)
            check("pam_export_csv_ar_present", bool(pam.get("csv_ar")), pam.get("csv_ar") is not None)
            check("pam_export_report_en_present", bool(pam.get("report_en")), pam.get("report_en") is not None)
            check("pam_export_report_ar_present", bool(pam.get("report_ar")), pam.get("report_ar") is not None)
            check(
                "pam_export_status_manual_submission_required",
                (pam.get("export") or {}).get("status") == "manual_submission_required",
                pam.get("export"),
            )
            check("pam_export_submission_false", pam.get("submission") is False, pam)
        conn.commit()

    # --- Multi-channel notifications ---------------------------------------------
    key_shift_id = ""
    keyb_shift_id = ""
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT shift_id::text FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled' ORDER BY shift_date LIMIT 1",
                (COMPANY, KEY),
            )
            row = cur.fetchone()
            key_shift_id = dict(row)["shift_id"] if row else ""
            cur.execute(
                "SELECT shift_id::text FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled' ORDER BY shift_date LIMIT 1",
                (COMPANY, KEY_B),
            )
            row = cur.fetchone()
            keyb_shift_id = dict(row)["shift_id"] if row else ""
    check("key_published_shift_found", bool(key_shift_id), key_shift_id)
    check("keyb_published_shift_found", bool(keyb_shift_id), keyb_shift_id)

    event_key_id = ""
    event_keyb_id = ""
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Default ladder for KEY (no prefs set): app-first with WhatsApp fallback slot.
            plan_key_default = n6.resolve_channel_plan(cur, company_code=COMPANY, employee_key=KEY)
            check("plan_key_default_source", plan_key_default.get("source") == "default_app_first", plan_key_default)
            check("plan_key_default_app_first", (plan_key_default.get("channel_order") or [None])[0] == "app", plan_key_default)
            check("plan_key_default_whatsapp_fallback", "whatsapp" in (plan_key_default.get("channel_order") or []), plan_key_default)

            # Employee-scoped preference for KEY_B: Teams-preferred, Telegram-enabled, email/SMS available.
            pref_b = n6.upsert_channel_preferences(
                cur,
                company_code=COMPANY,
                scope_type="employee",
                scope_key=KEY_B,
                channel_order=["teams", "app", "whatsapp"],
                enabled_channels=["teams", "app", "whatsapp", "telegram", "email", "sms"],
                fallback_enabled=True,
            )
            check("pref_keyb_teams_preferred_upsert", pref_b.get("ok"), pref_b)
            plan_keyb = n6.resolve_channel_plan(cur, company_code=COMPANY, employee_key=KEY_B)
            check("plan_keyb_source_employee", plan_keyb.get("source") == f"employee:{KEY_B}", plan_keyb)
            check("plan_keyb_teams_preferred", (plan_keyb.get("channel_order") or [None])[0] == "teams", plan_keyb)
            check("plan_keyb_telegram_enabled", "telegram" in (plan_keyb.get("enabled_channels") or []), plan_keyb)
            check("plan_keyb_email_sms_available", {"email", "sms"} <= set(plan_keyb.get("enabled_channels") or []), plan_keyb)

            # schedule_published event for KEY from publish (not draft) -> delivered via app (first in default ladder).
            evt_key = n6.emit_notification_event(
                cur,
                company_code=COMPANY,
                event_type="schedule_published",
                employee_key=KEY,
                employee_phone=PHONE,
                employee_name=NAME,
                shift_id=key_shift_id,
                schedule_period_id=period1_id,
                schedule_version_id=version1_id,
                payload={"reason": "shw6b publish"},
                from_draft=False,
            )
            check("emit_schedule_published_key_ok", evt_key.get("ok"), evt_key)
            check("emit_schedule_published_key_not_dup", evt_key.get("duplicate_suppressed") is False, evt_key)
            event_key_id = str((evt_key.get("event") or {}).get("event_id"))

            deliv_key = n6.process_event_deliveries(cur, company_code=COMPANY, event_id=event_key_id)
            check("deliver_key_ok", deliv_key.get("ok"), deliv_key)
            check("deliver_key_any_delivered", deliv_key.get("any_delivered") is True, deliv_key)
            check("deliver_key_real_sent_false", deliv_key.get("real_sent") is False, deliv_key)
            first_delivery_key = (deliv_key.get("deliveries") or [{}])[0]
            check("deliver_key_first_channel_app", first_delivery_key.get("channel") == "app", first_delivery_key)
            check("deliver_key_first_delivered", first_delivery_key.get("status") == "delivered", first_delivery_key)

            # Duplicate suppression: same dedupe (auto-generated from event_type+shift+version).
            evt_key_dup = n6.emit_notification_event(
                cur,
                company_code=COMPANY,
                event_type="schedule_published",
                employee_key=KEY,
                employee_phone=PHONE,
                employee_name=NAME,
                shift_id=key_shift_id,
                schedule_period_id=period1_id,
                schedule_version_id=version1_id,
                payload={"reason": "shw6b publish retry"},
                from_draft=False,
            )
            check("emit_schedule_published_key_dup_suppressed", evt_key_dup.get("duplicate_suppressed") is True, evt_key_dup)

            # Ack via whatsapp then app: second ack is already_acked.
            ack1 = n6.acknowledge_event(cur, company_code=COMPANY, event_id=event_key_id, channel="whatsapp", actor_phone=PHONE, actor_employee_key=KEY)
            check("ack_key_via_whatsapp_ok", ack1.get("ok") and ack1.get("already_acked") is False, ack1)
            ack2 = n6.acknowledge_event(cur, company_code=COMPANY, event_id=event_key_id, channel="app", actor_phone=PHONE, actor_employee_key=KEY)
            check("ack_key_via_app_already_acked", ack2.get("ok") and ack2.get("already_acked") is True, ack2)

            # shift_assigned event for KEY_B -> delivered via Teams (preferred channel).
            evt_keyb = n6.emit_notification_event(
                cur,
                company_code=COMPANY,
                event_type="shift_assigned",
                employee_key=KEY_B,
                employee_phone=PHONE_B,
                employee_name=NAME_B,
                shift_id=keyb_shift_id,
                schedule_period_id=period2_id,
                schedule_version_id=version2_id,
                payload={"reason": "shw6b altdn assigned"},
                from_draft=False,
            )
            check("emit_shift_assigned_keyb_ok", evt_keyb.get("ok"), evt_keyb)
            event_keyb_id = str((evt_keyb.get("event") or {}).get("event_id"))
            deliv_keyb = n6.process_event_deliveries(cur, company_code=COMPANY, event_id=event_keyb_id)
            check("deliver_keyb_ok", deliv_keyb.get("ok"), deliv_keyb)
            first_delivery_keyb = (deliv_keyb.get("deliveries") or [{}])[0]
            check("deliver_keyb_first_channel_teams", first_delivery_keyb.get("channel") == "teams", first_delivery_keyb)

            # drafts_do_not_notify
            evt_draft = n6.emit_notification_event(
                cur,
                company_code=COMPANY,
                event_type="upcoming_shift_reminder",
                employee_key=KEY,
                employee_phone=PHONE,
                shift_id=key_shift_id,
                from_draft=True,
            )
            check("drafts_do_not_notify", evt_draft.get("error") == "drafts_do_not_notify" and evt_draft.get("suppressed") is True, evt_draft)

            # Tenant isolation: attempt to notify using an employee_key that belongs to a different company (if any exist).
            cur.execute("SELECT employee_key FROM employees WHERE company_code <> %s LIMIT 1", (COMPANY,))
            other_row = cur.fetchone()
            if other_row:
                other_key = dict(other_row)["employee_key"]
                tenant_probe = n6.emit_notification_event(
                    cur,
                    company_code=COMPANY,
                    event_type="shift_assigned",
                    employee_key=other_key,
                    payload={"probe": "shw6b tenant isolation"},
                    dedupe_key=f"SHW6B-TENANT-PROBE|{TAG}",
                    from_draft=False,
                )
                check("tenant_isolation_violation_blocked", tenant_probe.get("error") == "tenant_isolation_violation", tenant_probe)
            else:
                check("tenant_isolation_no_other_company_data", True, "no other-company employee available to probe")
        conn.commit()

    # --- Retry ladder: mock_fail_once recovers; permanent unsupported goes terminal_failed ---
    retry_event_id = ""
    terminal_event_id = ""
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Overwrite KEY_B's plan to a single non-fallback channel for deterministic retry testing.
            n6.upsert_channel_preferences(
                cur,
                company_code=COMPANY,
                scope_type="employee",
                scope_key=KEY_B,
                channel_order=["sms"],
                enabled_channels=["sms"],
                fallback_enabled=False,
            )

            retry_dedupe = f"SHW6B-RETRY|{TAG}"
            n6.mock_fail_once("sms", dedupe_key=retry_dedupe)
            evt_retry = n6.emit_notification_event(
                cur,
                company_code=COMPANY,
                event_type="shift_changed",
                employee_key=KEY_B,
                employee_phone=PHONE_B,
                shift_id=keyb_shift_id,
                payload={"reason": "shw6b retry-recovery test"},
                dedupe_key=retry_dedupe,
                from_draft=False,
            )
            check("emit_retry_event_ok", evt_retry.get("ok"), evt_retry)
            retry_event_id = str((evt_retry.get("event") or {}).get("event_id"))

            deliv_retry1 = n6.process_event_deliveries(cur, company_code=COMPANY, event_id=retry_event_id, stop_on_first_success=False)
            check("deliver_retry1_first_attempt_failed", deliv_retry1.get("any_delivered") is False, deliv_retry1)
            check("deliver_retry1_real_sent_false", deliv_retry1.get("real_sent") is False, deliv_retry1)

            retry_result = n6.retry_failed_deliveries(cur, company_code=COMPANY, event_id=retry_event_id, max_attempts=3)
            check("retry_recovers_after_fail_once", int(retry_result.get("retried") or 0) >= 1 and not retry_result.get("terminal"), retry_result)

            cur.execute("SELECT status FROM shift_notification_events WHERE event_id=%s", (retry_event_id,))
            retry_event_status = dict(cur.fetchone() or {}).get("status")
            check("retry_event_delivered_after_recovery", retry_event_status == "delivered", retry_event_status)

            # Terminal-failed path: permanently unsupported channel, retried past max_attempts.
            n6.mock_mark_unsupported("sms")
            terminal_dedupe = f"SHW6B-TERMINAL|{TAG}"
            evt_terminal = n6.emit_notification_event(
                cur,
                company_code=COMPANY,
                event_type="shift_changed",
                employee_key=KEY_B,
                employee_phone=PHONE_B,
                shift_id=keyb_shift_id,
                payload={"reason": "shw6b terminal-failed test"},
                dedupe_key=terminal_dedupe,
                from_draft=False,
            )
            check("emit_terminal_event_ok", evt_terminal.get("ok"), evt_terminal)
            terminal_event_id = str((evt_terminal.get("event") or {}).get("event_id"))

            deliv_terminal1 = n6.process_event_deliveries(cur, company_code=COMPANY, event_id=terminal_event_id, stop_on_first_success=False)
            check("deliver_terminal1_failed", deliv_terminal1.get("any_delivered") is False, deliv_terminal1)

            terminal_result = n6.retry_failed_deliveries(cur, company_code=COMPANY, event_id=terminal_event_id, max_attempts=2)
            terminal_rows = terminal_result.get("terminal") or []
            check("terminal_failed_reached", len(terminal_rows) > 0 and all(str(t.get("status")) == "terminal_failed" for t in terminal_rows), terminal_result)
        conn.commit()

    # --- Invalidate notifications on shift cancel path --------------------------
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            invalidate_shift_id = keyb_shift_id
            evt_pending = n6.emit_notification_event(
                cur,
                company_code=COMPANY,
                event_type="shift_assigned",
                employee_key=KEY_B,
                employee_phone=PHONE_B,
                shift_id=invalidate_shift_id,
                payload={"reason": "shw6b invalidate-on-cancel"},
                dedupe_key=f"SHW6B-INVALIDATE|{TAG}",
                requires_ack=True,
                from_draft=False,
            )
            check("emit_pending_for_invalidate_ok", evt_pending.get("ok"), evt_pending)

            cur.execute(
                "UPDATE shift_assignments SET status='cancelled', updated_at=now() WHERE shift_id=%s AND company_code=%s",
                (invalidate_shift_id, COMPANY),
            )
            check("shift_soft_cancelled_for_invalidate_test", cur.rowcount == 1, cur.rowcount)

            invalidate_res = n6.invalidate_notifications_for_shift(cur, company_code=COMPANY, shift_id=invalidate_shift_id)
            check("invalidate_notifications_ok", invalidate_res.get("ok"), invalidate_res)
            check("invalidate_notifications_gt_0", int(invalidate_res.get("invalidated") or 0) > 0, invalidate_res)

            cur.execute(
                "SELECT status FROM shift_notification_events WHERE company_code=%s AND shift_id=%s AND event_type='shift_assigned' ORDER BY created_at DESC LIMIT 1",
                (COMPANY, invalidate_shift_id),
            )
            row = cur.fetchone()
            check("event_status_invalidated", bool(row) and dict(row).get("status") == "invalidated", dict(row) if row else None)
        conn.commit()

    # --- Fingerprint + residual-zero cleanup -------------------------------------
    RESULTS["ids"] = {
        "period_id": known_ids.get("period_id"),
        "version_ids": known_ids.get("version_ids"),
        "shift_ids": known_ids.get("shift_ids"),
        "employees": [KEY, KEY_B],
        "day_template": day_id,
        "night_template": night_id,
        "patterns": {
            "four_on_four_off": pattern_4on4_id,
            "panama_223": pattern_panama_id,
            "six_on_one_off": pattern_6on1_id,
            "alternating_day_night": pattern_altdn_id,
            "hitch_n_n": pattern_hitch_id,
            "custom_sequence": pattern_custom_id,
        },
        "events": {"key": event_key_id, "keyb": event_keyb_id, "retry": retry_event_id, "terminal": terminal_event_id},
    }
    (EVID / "ids.json").write_text(json.dumps(RESULTS["ids"], indent=2, default=str))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = snapshot_real_fps(cur)
            (EVID / "fps-after.json").write_text(json.dumps(after, indent=2, default=str))
            check("real_assignment_fps_unchanged", before["assignments"] == after["assignments"])
            check("real_template_fps_unchanged", before["templates"] == after["templates"])
            check("real_rotation_pattern_fps_unchanged", before["rotation_patterns"] == after["rotation_patterns"])
            check("real_rotation_assignment_fps_unchanged", before["rotation_assignments"] == after["rotation_assignments"])
            check("real_compliance_profile_fps_unchanged", before["compliance_profiles"] == after["compliance_profiles"])
            check("real_notification_event_fps_unchanged", before["notification_events"] == after["notification_events"])
            check("real_channel_preference_fps_unchanged", before["channel_preferences"] == after["channel_preferences"])
            check("real_schedule_period_fps_unchanged", before["schedule_periods"] == after["schedule_periods"])
            check("real_schedule_version_fps_unchanged", before["schedule_versions"] == after["schedule_versions"])
            check("real_event_count_unchanged", before["events"] == after["events"], {"before": before["events"], "after": after["events"]})

    scope = wave6b_scope(company_code=COMPANY, tag=TAG, extra_employee_keys=(KEY, KEY_B))
    cleaned = cleanup_synthetic_scope(app.db_connect, scope, known_ids=known_ids)
    (EVID / "cleanup.json").write_text(json.dumps(cleaned, indent=2, default=str))
    residual = int(cleaned.get("residual_total") or 0)
    check("cleanup_residual_zero", residual == 0, cleaned.get("residual"))
    check("cleanup_contract_version", cleaned.get("contract_version") == CLEANUP_CONTRACT_VERSION, cleaned.get("contract_version"))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            final = snapshot_real_fps(cur)
            residual2 = count_synthetic_residuals(cur, scope, extra_employee_keys=(KEY, KEY_B))
    (EVID / "residual-final.json").write_text(json.dumps(residual2, indent=2, default=str))
    check(
        "real_fps_unchanged_after_cleanup",
        before["assignments"] == final["assignments"] and before["templates"] == final["templates"],
    )
    check("residual_total_zero", int(residual2.get("total") or 0) == 0, residual2)

    RESULTS["passed"] = PASS
    RESULTS["failed"] = FAIL
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
