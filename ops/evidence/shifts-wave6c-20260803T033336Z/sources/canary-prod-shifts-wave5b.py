#!/usr/bin/env python3
"""Shifts Wave 5B — production WATHEFNI synthetic publish/open/coverage canary.

Markers: SHW5B / 965535* only. Real allowlists empty. Real mutation gate on.
Real reminders off. Timers/jobs disabled. No real employee publishing.

Proves: draft/review/publish, coverage rules, open-shift workflow, rollback,
fingerprint stability, and residual-zero cleanup (wave5b_scope).
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

# Wave 5 synthetic gate — SHW5B markers only
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS", "SHW5B,SHW5B-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES", "965535")

# Wave 4 templates/recurrences — include SHW5B so SYNTHETIC_ONLY templates work
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY", "1")


def _merge_env_csv(key: str, *values: str) -> None:
    existing = [p.strip() for p in (os.environ.get(key) or "").split(",") if p.strip()]
    for v in values:
        if v not in existing:
            existing.append(v)
    os.environ[key] = ",".join(existing) if existing else ",".join(values)


_merge_env_csv("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS", "SHW5B", "SHW5B-SYNTH|")
_merge_env_csv("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES", "965535")

import app  # noqa: E402
import shifts_publish_wave5 as w5  # noqa: E402
import shifts_templates_wave4 as w4  # noqa: E402
import shifts_wave3_controlled as w3  # noqa: E402
import shifts_controlled_wave6c as _shifts_w6c  # noqa: E402
import shifts_schedule_integrity_wave2 as w2  # noqa: E402
from shifts_synthetic_cleanup import (  # noqa: E402
    CLEANUP_CONTRACT_VERSION,
    cleanup_synthetic_scope,
    count_synthetic_residuals,
    wave5b_scope,
)

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW5B_TAG") or uuid.uuid4().hex[:8].upper()
EVID = Path(os.environ.get("SHW5B_EVID") or f"/tmp/shw5b-prod-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

KEY = f"WATHEFNI-SHW5B-{TAG}"
KEY_B = f"WATHEFNI-SHW5B-B-{TAG}"
_digits = "".join(ch for ch in TAG if ch.isdigit()) or "123456"
PHONE = f"965535{_digits[:6].ljust(6, '0')}"
PHONE_B = f"965535{_digits[1:6].ljust(5, '0')}9"
NAME = f"SHW5B-SYNTH| Emp {TAG}"
NAME_B = f"SHW5B-SYNTH| EmpB {TAG}"
TEAM = f"SHW5B-TEAM-{TAG}"
SITE = f"SHW5B-SITE-{TAG}"
ROLE = f"SHW5B-ROLE-{TAG}"
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


def seed_employee(cur, key: str, name: str, phone: str, *, team: str | None = None, site: str | None = None, role: str | None = None) -> None:
    raw = {"shw5b": True, "tag": TAG}
    if team:
        raw["team_key"] = team
    if site:
        raw["site_key"] = site
    if role:
        raw["role"] = role
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
    """Fingerprint non-SHW5B real schedule lineage for drift detection."""
    out: dict = {
        "assignments": {},
        "templates": {},
        "recurrences": {},
        "exceptions": {},
        "assignment_versions": {},
        "schedule_periods": {},
        "schedule_versions": {},
        "open_shifts": {},
        "coverage_rules": {},
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
              AND coalesce(employee_key,'') NOT LIKE '%%SHW5B%%'
              AND coalesce(employee_phone,'') NOT LIKE '965535%%'
              AND coalesce(occurrence_key,'') NOT LIKE '%%SHW5B%%'
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
              AND coalesce(employee_key,'') NOT LIKE '%%SHW5B%%'
              AND coalesce(employee_phone,'') NOT LIKE '965535%%'
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
            WHERE company_code=%s AND name NOT LIKE '%%SHW5B%%'
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

    cur.execute(
        """
        SELECT recurrence_id::text, name, status, cycle_type, target_type, target_key,
               planning_version, updated_at::text
        FROM shift_recurrences
        WHERE company_code=%s AND name NOT LIKE '%%SHW5B%%' AND coalesce(target_key,'') NOT LIKE '%%SHW5B%%'
        ORDER BY recurrence_id::text
        """,
        (COMPANY,),
    )
    for r in cur.fetchall():
        d = dict(r)
        out["recurrences"][d["recurrence_id"]] = fp_simple(
            d, ("recurrence_id", "name", "status", "cycle_type", "target_type", "target_key", "planning_version", "updated_at")
        )

    cur.execute(
        """
        SELECT e.exception_id::text, e.recurrence_id::text, e.exception_date::text, e.kind
        FROM shift_recurrence_exceptions e
        JOIN shift_recurrences r ON r.recurrence_id=e.recurrence_id
        WHERE e.company_code=%s AND r.name NOT LIKE '%%SHW5B%%'
        ORDER BY e.exception_id::text
        """,
        (COMPANY,),
    )
    for r in cur.fetchall():
        d = dict(r)
        out["exceptions"][d["exception_id"]] = fp_simple(d, ("exception_id", "recurrence_id", "exception_date", "kind"))

    try:
        cur.execute(
            """
            SELECT version_id::text, shift_id::text, employee_key, reason_code, created_at::text
            FROM shift_assignment_versions
            WHERE company_code=%s
              AND coalesce(employee_key,'') NOT LIKE '%%SHW5B%%'
            ORDER BY version_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["assignment_versions"][d["version_id"]] = fp_simple(
                d, ("version_id", "shift_id", "employee_key", "reason_code", "created_at")
            )
    except Exception:
        pass

    try:
        w5.ensure_shifts_publish_wave5_schema(cur)
        cur.execute(
            """
            SELECT period_id::text, name, status, start_date::text, end_date::text,
                   require_publish::text, updated_at::text
            FROM shift_schedule_periods
            WHERE company_code=%s AND name NOT LIKE '%%SHW5B%%'
            ORDER BY period_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["schedule_periods"][d["period_id"]] = fp_simple(
                d, ("period_id", "name", "status", "start_date", "end_date", "require_publish", "updated_at")
            )

        cur.execute(
            """
            SELECT v.version_id::text, v.period_id::text, v.version_no::text, v.state, v.updated_at::text
            FROM shift_schedule_versions v
            JOIN shift_schedule_periods p ON p.period_id=v.period_id
            WHERE v.company_code=%s AND p.name NOT LIKE '%%SHW5B%%'
            ORDER BY v.version_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["schedule_versions"][d["version_id"]] = fp_simple(
                d, ("version_id", "period_id", "version_no", "state", "updated_at")
            )

        cur.execute(
            """
            SELECT open_shift_id::text, shift_date::text, start_time::text, end_time::text,
                   status, coalesce(notes,'') notes, updated_at::text
            FROM shift_open_shifts
            WHERE company_code=%s AND coalesce(notes,'') NOT LIKE '%%SHW5B%%'
            ORDER BY open_shift_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["open_shifts"][d["open_shift_id"]] = fp_simple(
                d, ("open_shift_id", "shift_date", "start_time", "end_time", "status", "notes", "updated_at")
            )

        cur.execute(
            """
            SELECT rule_id::text, name, enforcement_mode, min_staff::text, enabled::text, updated_at::text
            FROM shift_coverage_rules
            WHERE company_code=%s AND name NOT LIKE '%%SHW5B%%'
            ORDER BY rule_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["coverage_rules"][d["rule_id"]] = fp_simple(
                d, ("rule_id", "name", "enforcement_mode", "min_staff", "enabled", "updated_at")
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
                  AND coalesce(employee_key,'') NOT LIKE '%%SHW5B%%'
                  AND coalesce(employee_phone,'') NOT LIKE '965535%%'
              )
            """,
            (COMPANY, COMPANY),
        )
        out["events"] = int(dict(cur.fetchone())["c"])
    except Exception:
        out["events"] = -1

    return out


def main() -> int:
    print(f"SHW5B prod canary tag={TAG} evid={EVID} cleanup={CLEANUP_CONTRACT_VERSION}", flush=True)
    app.send_octopus_whatsapp = lambda *a, **k: {"ok": True, "skipped": "shw5b"}  # type: ignore
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "skipped": "shw5b"}  # type: ignore
    app.notify_employee_shift_created = lambda *a, **k: {"ok": True, "skipped": "shw5b"}  # type: ignore
    app.notify_employee_shift_cancelled = lambda *a, **k: {"ok": True, "skipped": "shw5b"}  # type: ignore
    app.notify_hr_admins = lambda *a, **k: {"ok": True, "skipped": "shw5b"}  # type: ignore

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
    check("db_is_wathefni", db == "wathefni", db)

    check("wave5_enabled", w5.shifts_wave5_enabled())
    check("wave5_company", w5.shifts_wave5_enabled_for_company(COMPANY))
    check("wave5_synthetic_only", w5.shifts_wave5_synthetic_only())
    check("version_5_0", w5.SHIFTS_WAVE5_VERSION == "5.0.0")
    check("shw5b_synth_w5", w5.is_wave5_synthetic_employee(employee_key=KEY, phone=PHONE, name=NAME))
    check("shw5b_synth_w4", w4.is_wave4_synthetic_employee(employee_key=KEY, phone=PHONE, name=NAME))
    check("real_phone_not_synth", not w5.is_wave5_synthetic_employee(employee_key="EMP-1", phone="96550001111"))

    check("w3_gate_on", w3.real_mutation_gate_enabled())
    check("allowlists_within_approved_boundary", _shifts_w6c.allowlists_within_approved_boundary(), sorted(w3.hr_mutation_allowlist()) + sorted(w3.manager_mutation_allowlist()))
    check("real_reminders_off", not w3.real_reminders_enabled())
    check(
        "real_mutation_blocked",
        w3.real_mutation_denied(actor_phone=ACTOR, is_synthetic_subject=False, company_code=COMPANY) is not None,
    )
    check(
        "synth_mutation_allowed",
        w3.real_mutation_denied(actor_phone=ACTOR, is_synthetic_subject=True, company_code=COMPANY) is None,
    )

    h = w5.honesty_payload()
    check("honesty_publishing_true", h.get("publishing") is True)
    check("honesty_open_shifts_true", h.get("open_shifts") is True)
    check("honesty_draft_publish_true", h.get("draft_publish") is True)
    check("honesty_coverage_rules_true", h.get("coverage_rules") is True)
    check("honesty_rotations_false", h.get("rotations") is False)
    check("honesty_pam_export_false", h.get("pam_export") is False)
    check("honesty_payroll_false", h.get("payroll_money") is False)
    check("honesty_leave_false", h.get("leave_balances_mutated") is False)
    check("honesty_attendance_false", h.get("attendance_authority_mutated") is False)
    check("w4_honesty_publishing_false", w4.honesty_payload().get("publishing") is False)
    check("w3_honesty_templates_false", w3.honesty_payload().get("templates") is False)

    src = Path(w5.__file__).read_text(encoding="utf-8")
    check("no_leave_balances_sql", "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src)
    check("cleanup_contract", CLEANUP_CONTRACT_VERSION.startswith("1."))

    today = date.today()
    start = today + timedelta(days=2)
    end = today + timedelta(days=10)

    known_ids: dict[str, object] = {"shift_ids": [], "version_ids": [], "open_shift_ids": [], "coverage_rule_names": []}
    pub1: dict = {}

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w5.ensure_shifts_publish_wave5_schema(cur)
            w4.ensure_shifts_templates_wave4_schema(cur)
            before = snapshot_real_fps(cur)
            (EVID / "fps-before.json").write_text(json.dumps(before, indent=2, default=str))
            RESULTS["fps_before_counts"] = {k: (len(v) if isinstance(v, dict) else v) for k, v in before.items()}

            seed_employee(cur, KEY, NAME, PHONE, team=TEAM, site=SITE, role=ROLE)
            seed_employee(cur, KEY_B, NAME_B, PHONE_B, team=TEAM, site=SITE, role=ROLE)
            cur.execute("SAVEPOINT shw5b_org")
            try:
                for k in (KEY, KEY_B):
                    cur.execute(
                        """
                        INSERT INTO employee_org_assignments (company_code, employee_key, team_key, role, is_primary, metadata, updated_at)
                        VALUES (%s,%s,%s,%s, true, '{}'::jsonb, now())
                        ON CONFLICT DO NOTHING
                        """,
                        (COMPANY, k, TEAM, ROLE),
                    )
                cur.execute("RELEASE SAVEPOINT shw5b_org")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT shw5b_org")
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            day_t = w4.create_template(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW5B Day {TAG}", "start_time": "09:00", "end_time": "17:00", "role": ROLE, "site_key": SITE},
            )
            check("day_template", day_t.get("ok"), day_t)
            day_id = str((day_t.get("template") or {}).get("template_id"))

            night_t = w4.create_template(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW5B Night {TAG}", "start_time": "22:00", "end_time": "06:00"},
            )
            check("overnight_template", night_t.get("ok") and bool((night_t.get("template") or {}).get("ends_next_day")), night_t)
            night_id = str((night_t.get("template") or {}).get("template_id"))

            weekly = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW5B Weekly {TAG}",
                    "template_id": day_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4, 5, 6],
                    "effective_start": start.isoformat(),
                    "effective_end": (start + timedelta(days=14)).isoformat(),
                    "horizon_days": 30,
                    "target_type": "employee",
                    "target_key": KEY,
                },
            )
            check("weekly_recurrence", weekly.get("ok"), weekly)
            weekly_id = str((weekly.get("recurrence") or {}).get("recurrence_id"))

            period_res = w5.create_period(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW5B Period {TAG}",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "require_publish": True,
                    "team_key": TEAM,
                },
                actor_phone=PHONE,
            )
            check("create_period", period_res.get("ok"), period_res)
            period_id = str((period_res.get("period") or {}).get("period_id"))
            version_id = str((period_res.get("version") or {}).get("version_id"))
            known_ids["period_id"] = period_id
            known_ids["version_ids"] = [version_id]

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'
                """,
                (COMPANY, KEY),
            )
            l0_before = int(dict(cur.fetchone())["c"])

            draft_gen = w5.generate_draft_from_recurrence(
                cur,
                company_code=COMPANY,
                period_id=period_id,
                recurrence_id=weekly_id,
                actor_phone=PHONE,
                action_acks=ACKS,
            )
            check("generate_draft_ok", draft_gen.get("ok"), draft_gen)
            check("draft_rows_gt_0", int(draft_gen.get("draft_rows") or 0) > 0, draft_gen.get("draft_rows"))
            check("l0_written_false", draft_gen.get("l0_written") is False, draft_gen)

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'
                """,
                (COMPANY, KEY),
            )
            l0_after_draft = int(dict(cur.fetchone())["c"])
            check("L0_unchanged_after_draft", l0_after_draft == l0_before, {"before": l0_before, "after": l0_after_draft})
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            tr1 = w5.transition_version(cur, company_code=COMPANY, version_id=version_id, to_state="in_review", actor_phone=PHONE)
            check("transition_in_review", tr1.get("ok"), tr1)

            tr_return = w5.transition_version(
                cur,
                company_code=COMPANY,
                version_id=version_id,
                to_state="draft",
                actor_phone=PHONE,
                note=f"SHW5B return {TAG}",
            )
            check("return_to_draft_with_note", tr_return.get("ok"), tr_return)

            tr2 = w5.transition_version(cur, company_code=COMPANY, version_id=version_id, to_state="in_review", actor_phone=PHONE)
            check("transition_in_review_again", tr2.get("ok"), tr2)

            tr3 = w5.transition_version(cur, company_code=COMPANY, version_id=version_id, to_state="approved", actor_phone=PHONE)
            check("transition_approved", tr3.get("ok"), tr3)

            diff = w5.review_diff(cur, company_code=COMPANY, version_id=version_id)
            check("review_diff_ok", diff.get("ok"), diff)

            warn_name = f"SHW5B Warn {TAG}"
            warn_rule = w5.upsert_coverage_rule(
                cur,
                company_code=COMPANY,
                payload={
                    "name": warn_name,
                    "effective_start": start.isoformat(),
                    "effective_end": end.isoformat(),
                    "window_start": "09:00",
                    "window_end": "17:00",
                    "min_staff": 999,
                    "enforcement_mode": "warn",
                    "role": ROLE,
                },
                actor_phone=PHONE,
            )
            check("coverage_warn_rule", warn_rule.get("ok"), warn_rule)
            known_ids["coverage_rule_names"] = [warn_name]

            period_row = w5.get_period(cur, company_code=COMPANY, period_id=period_id)
            cov_warn = w5.evaluate_coverage_for_version(cur, company_code=COMPANY, version_id=version_id, period=period_row)
            check("understaffed_warning", int((cov_warn.get("summary") or {}).get("understaffed") or 0) > 0, cov_warn.get("summary"))
            check("warn_blocks_publish_false", cov_warn.get("blocks_publish") is False, cov_warn)

            block_name = f"SHW5B Block {TAG}"
            block_rule = w5.upsert_coverage_rule(
                cur,
                company_code=COMPANY,
                payload={
                    "name": block_name,
                    "effective_start": start.isoformat(),
                    "effective_end": end.isoformat(),
                    "window_start": "09:00",
                    "window_end": "17:00",
                    "min_staff": 999,
                    "enforcement_mode": "block",
                    "role": ROLE,
                },
                actor_phone=PHONE,
            )
            check("coverage_block_rule", block_rule.get("ok"), block_rule)
            known_ids["coverage_rule_names"] = list(known_ids.get("coverage_rule_names") or []) + [block_name]

            cov_block = w5.evaluate_coverage_for_version(cur, company_code=COMPANY, version_id=version_id, period=period_row)
            check("block_blocks_publish_true", cov_block.get("blocks_publish") is True, cov_block)

            pub_blocked = w5.publish_version(
                cur,
                company_code=COMPANY,
                version_id=version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                publish_idempotency_key=f"SHW5B-PUB|{TAG}",
                action_acks=ACKS,
            )
            check("publish_blocked_by_coverage", pub_blocked.get("error") == "coverage_block", pub_blocked)

            cur.execute(
                "UPDATE shift_coverage_rules SET enabled=false, updated_at=now() WHERE company_code=%s AND name=%s",
                (COMPANY, block_name),
            )
            cur.execute(
                """
                UPDATE shift_coverage_rules SET min_staff=1, enforcement_mode='warn', updated_at=now()
                WHERE company_code=%s AND name=%s
                """,
                (COMPANY, warn_name),
            )

            overnight_name = f"SHW5B OvernightCov {TAG}"
            overnight_cov = w5.upsert_coverage_rule(
                cur,
                company_code=COMPANY,
                payload={
                    "name": overnight_name,
                    "effective_start": start.isoformat(),
                    "effective_end": end.isoformat(),
                    "window_start": "22:00",
                    "window_end": "06:00",
                    "ends_next_day": True,
                    "min_staff": 0,
                    "enforcement_mode": "warn",
                },
                actor_phone=PHONE,
            )
            check("overnight_coverage_rule", overnight_cov.get("ok"), overnight_cov)
            known_ids["coverage_rule_names"] = list(known_ids.get("coverage_rule_names") or []) + [overnight_name]

            unresolved = w5.create_open_shift(
                cur,
                company_code=COMPANY,
                payload={
                    "period_id": period_id,
                    "shift_date": (start + timedelta(days=1)).isoformat(),
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "notes": f"SHW5B unresolved {TAG}",
                    "role": ROLE,
                },
                actor_phone=PHONE,
            )
            check("unresolved_open_shift", unresolved.get("ok"), unresolved)
            unresolved_id = str((unresolved.get("open_shift") or {}).get("open_shift_id"))
            known_ids["open_shift_ids"] = list(known_ids.get("open_shift_ids") or []) + [unresolved_id]

            cov_open = w5.evaluate_coverage_for_version(cur, company_code=COMPANY, version_id=version_id, period=period_row)
            check(
                "coverage_unresolved_open_shift",
                int((cov_open.get("summary") or {}).get("unresolved_open_shift") or 0) > 0,
                cov_open.get("summary"),
            )
            cur.execute(
                "UPDATE shift_open_shifts SET status='cancelled', updated_at=now() WHERE open_shift_id=%s",
                (unresolved_id,),
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pub1 = w5.publish_version(
                cur,
                company_code=COMPANY,
                version_id=version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                publish_idempotency_key=f"SHW5B-PUB|{TAG}",
                action_acks=ACKS,
            )
            check("publish_ok", pub1.get("ok"), pub1)
            first_version_id = version_id
            if pub1.get("results", {}).get("created_ids"):
                known_ids["shift_ids"] = list(pub1["results"]["created_ids"])

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND schedule_period_id=%s AND schedule_version_id=%s
                  AND schedule_source='published' AND status <> 'cancelled'
                """,
                (COMPANY, period_id, version_id),
            )
            pub_l0 = int(dict(cur.fetchone())["c"])
            check("published_L0_provenance", pub_l0 > 0, pub_l0)

            pub1b = w5.publish_version(
                cur,
                company_code=COMPANY,
                version_id=version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                publish_idempotency_key=f"SHW5B-PUB|{TAG}",
                action_acks=ACKS,
            )
            check("republish_idempotent", pub1b.get("ok") and pub1b.get("idempotent") is True, pub1b)

            lock_key = w5.publish_lock_key(COMPANY, period_id)
            lock_result: dict = {}

            def other_publish():
                with app.db_connect() as c2:
                    with c2.cursor() as cur2:
                        lock_result["res"] = w5.publish_version(
                            cur2,
                            company_code=COMPANY,
                            version_id=version_id,
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

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            draft2 = w5.create_draft_from_published(cur, company_code=COMPANY, period_id=period_id, actor_phone=PHONE)
            check("create_draft_from_published", draft2.get("ok"), draft2)
            version2_id = str((draft2.get("version") or {}).get("version_id"))
            known_ids["version_ids"] = list(known_ids.get("version_ids") or []) + [version2_id]

            w5.transition_version(cur, company_code=COMPANY, version_id=version2_id, to_state="in_review", actor_phone=PHONE)
            w5.transition_version(cur, company_code=COMPANY, version_id=version2_id, to_state="approved", actor_phone=PHONE)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pub2 = w5.publish_version(
                cur,
                company_code=COMPANY,
                version_id=version2_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                publish_idempotency_key=f"SHW5B-PUB2|{TAG}",
                action_acks=ACKS,
            )
            check("publish_second_version", pub2.get("ok"), pub2)
            if pub2.get("results", {}).get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(pub2["results"]["created_ids"])
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            rollback = w5.rollback_to_version(
                cur,
                company_code=COMPANY,
                period_id=period_id,
                target_version_id=first_version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                action_acks=ACKS,
            )
            check("rollback_to_version", rollback.get("ok"), rollback)
            if rollback.get("publish", {}).get("results", {}).get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(rollback["publish"]["results"]["created_ids"])

            check(
                "skipped_locked_field_present",
                "skipped_locked" in (pub1.get("results") or {}),
                pub1.get("results"),
            )
        conn.commit()

    emp_a = {"employee_key": KEY, "phone": PHONE, "name": NAME}
    emp_b = {"employee_key": KEY_B, "phone": PHONE_B, "name": NAME_B}
    claim_a_id = claim_b_id = ""

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            open_night_date = (end + timedelta(days=3)).isoformat()
            open_night = w5.create_open_shift(
                cur,
                company_code=COMPANY,
                payload={
                    "period_id": period_id,
                    "shift_date": open_night_date,
                    "start_time": "22:00",
                    "end_time": "06:00",
                    "notes": f"SHW5B overnight claim {TAG}",
                    "role": ROLE,
                },
                actor_phone=PHONE,
            )
            check("overnight_open_shift", open_night.get("ok"), open_night)
            open_night_id = str((open_night.get("open_shift") or {}).get("open_shift_id"))
            known_ids["open_shift_ids"] = list(known_ids.get("open_shift_ids") or []) + [open_night_id]

            claim_a = w5.claim_open_shift(cur, company_code=COMPANY, open_shift_id=open_night_id, employee=emp_a, actor_phone=PHONE)
            check("claim_by_A", claim_a.get("ok"), claim_a)
            claim_a_id = str((claim_a.get("claim") or {}).get("claim_id"))

            self_denied = w5.decide_open_shift_claim(
                cur,
                company_code=COMPANY,
                claim_id=claim_a_id,
                decision="approved",
                actor_phone=PHONE,
                actor_employee_key=KEY,
                create_fn=app.create_shift_assignment,
                action_acks=ACKS,
            )
            check("self_approval_denied", self_denied.get("error") == "self_approval_denied", self_denied)

            claim_b = w5.claim_open_shift(cur, company_code=COMPANY, open_shift_id=open_night_id, employee=emp_b, actor_phone=PHONE_B)
            check("claim_by_B", claim_b.get("ok"), claim_b)
            claim_b_id = str((claim_b.get("claim") or {}).get("claim_id"))
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            approve_a = w5.decide_open_shift_claim(
                cur,
                company_code=COMPANY,
                claim_id=claim_a_id,
                decision="approved",
                actor_phone=PHONE_B,
                actor_employee_key=KEY_B,
                create_fn=app.create_shift_assignment,
                action_acks=ACKS,
            )
            check("approve_A_wins", approve_a.get("ok"), approve_a)
            if approve_a.get("shift_id"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + [approve_a["shift_id"]]

            approve_b = w5.decide_open_shift_claim(
                cur,
                company_code=COMPANY,
                claim_id=claim_b_id,
                decision="approved",
                actor_phone=PHONE,
                actor_employee_key=KEY,
                create_fn=app.create_shift_assignment,
                action_acks=ACKS,
            )
            check(
                "second_approve_B_rejected",
                approve_b.get("error") in {"claim_not_pending", "open_shift_already_resolved"},
                approve_b,
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            open_direct = w5.create_open_shift(
                cur,
                company_code=COMPANY,
                payload={
                    "period_id": period_id,
                    "shift_date": (end + timedelta(days=5)).isoformat(),
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "notes": f"SHW5B direct {TAG}",
                    "role": ROLE,
                },
                actor_phone=PHONE,
            )
            check("open_shift_for_direct_assign", open_direct.get("ok"), open_direct)
            open_direct_id = str((open_direct.get("open_shift") or {}).get("open_shift_id"))
            known_ids["open_shift_ids"] = list(known_ids.get("open_shift_ids") or []) + [open_direct_id]
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            direct = w5.assign_open_shift_direct(
                cur,
                company_code=COMPANY,
                open_shift_id=open_direct_id,
                employee_key=KEY_B,
                create_fn=app.create_shift_assignment,
                actor_phone=PHONE,
                action_acks=ACKS,
            )
            check("direct_assign_open_shift", direct.get("ok"), direct)
            if direct.get("shift_id"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + [direct["shift_id"]]

            cur.execute(
                """
                SELECT shift_date::text, start_time::text, end_time::text, ends_next_day
                FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND schedule_source='published'
                  AND status='scheduled'
                ORDER BY shift_date LIMIT 1
                """,
                (COMPANY, KEY),
            )
            overlap_src = cur.fetchone()
            if overlap_src:
                ov = dict(overlap_src)
                open_overlap = w5.create_open_shift(
                    cur,
                    company_code=COMPANY,
                    payload={
                        "period_id": period_id,
                        "shift_date": ov["shift_date"][:10],
                        "start_time": ov["start_time"][:5],
                        "end_time": ov["end_time"][:5],
                        "notes": f"SHW5B overlap gate {TAG}",
                        "role": ROLE,
                    },
                    actor_phone=PHONE,
                )
                open_overlap_id = str((open_overlap.get("open_shift") or {}).get("open_shift_id"))
                known_ids["open_shift_ids"] = list(known_ids.get("open_shift_ids") or []) + [open_overlap_id]
                claim_ov = w5.claim_open_shift(
                    cur,
                    company_code=COMPANY,
                    open_shift_id=open_overlap_id,
                    employee=emp_a,
                    actor_phone=PHONE,
                )
                if claim_ov.get("ok"):
                    gate = w5.decide_open_shift_claim(
                        cur,
                        company_code=COMPANY,
                        claim_id=claim_ov["claim"]["claim_id"],
                        decision="approved",
                        actor_phone=PHONE_B,
                        actor_employee_key=KEY_B,
                        create_fn=app.create_shift_assignment,
                        action_acks={},
                    )
                    check("gate_conflict_without_ack", gate.get("error") == "gate_conflict", gate)
                else:
                    check("gate_conflict_without_ack", False, claim_ov)
            else:
                check("gate_conflict_without_ack", False, "no published assignment to overlap")

            opt_period = w5.create_period(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW5B Optional {TAG}",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "require_publish": False,
                },
                actor_phone=PHONE,
            )
            check("optional_require_publish_period", opt_period.get("ok"), opt_period)
        conn.commit()

    manual = app.create_shift_assignment(
        {
            "employee_key": KEY,
            "employee_name": NAME,
            "employee_phone": PHONE,
            "date": (end + timedelta(days=7)).isoformat(),
            "shift_date": (end + timedelta(days=7)).isoformat(),
            "start_time": "10:00",
            "end_time": "14:00",
            "idempotency_key": f"SHW5B-MANUAL|{TAG}",
            "reason": f"wave5b manual optional period {TAG}",
            **ACKS,
        },
        company_code=COMPANY,
        created_by_phone=PHONE,
    )
    check("manual_L0_optional_period", manual.get("ok"), manual)
    if manual.get("created"):
        for c in manual["created"]:
            sid = str(c.get("shift_id") or "")
            if sid:
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + [sid]

    RESULTS["ids"] = {
        "period_id": known_ids.get("period_id"),
        "version_ids": known_ids.get("version_ids"),
        "open_shift_ids": known_ids.get("open_shift_ids"),
        "coverage_rule_names": known_ids.get("coverage_rule_names"),
        "shift_ids": known_ids.get("shift_ids"),
        "employees": [KEY, KEY_B],
        "day_template": day_id,
        "night_template": night_id,
        "weekly_recurrence": weekly_id,
    }
    (EVID / "ids.json").write_text(json.dumps(RESULTS["ids"], indent=2, default=str))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = snapshot_real_fps(cur)
            (EVID / "fps-after.json").write_text(json.dumps(after, indent=2, default=str))
            check("real_assignment_fps_unchanged", before["assignments"] == after["assignments"])
            check("real_template_fps_unchanged", before["templates"] == after["templates"])
            check("real_recurrence_fps_unchanged", before["recurrences"] == after["recurrences"])
            check("real_exception_fps_unchanged", before["exceptions"] == after["exceptions"])
            check("real_assignment_version_fps_unchanged", before["assignment_versions"] == after["assignment_versions"])
            check("real_schedule_period_fps_unchanged", before["schedule_periods"] == after["schedule_periods"])
            check("real_schedule_version_fps_unchanged", before["schedule_versions"] == after["schedule_versions"])
            check("real_open_shift_fps_unchanged", before["open_shifts"] == after["open_shifts"])
            check("real_coverage_fps_unchanged", before["coverage_rules"] == after["coverage_rules"])
            check("real_event_count_unchanged", before["events"] == after["events"], {"before": before["events"], "after": after["events"]})

    scope = wave5b_scope(company_code=COMPANY, tag=TAG, extra_employee_keys=(KEY, KEY_B))
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
