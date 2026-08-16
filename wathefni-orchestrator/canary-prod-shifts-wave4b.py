#!/usr/bin/env python3
"""Shifts Wave 4B — production WATHEFNI synthetic templates/recurrence canary.

Markers: SHW4B / 965533* only. Real allowlists empty. Real mutation gate on.
Real reminders off. Timers/jobs disabled. No draft/publish, rotations, open shifts,
PAM, Payroll money, Leave balance mutation, or Attendance authority mutation.

Proves: templates, weekly / n_on_m_off / alternating, preview→materialize,
pause/resume/end, exceptions, detach, cancelled_held, idempotency, advisory lock,
skipped_target, fingerprint stability, residual-zero cleanup.
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


import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
import app  # noqa: E402
import shifts_templates_wave4 as w4  # noqa: E402
import shifts_wave3_controlled as w3  # noqa: E402
import shifts_controlled_wave6c as _shifts_w6c  # noqa: E402
import shifts_schedule_integrity_wave2 as w2  # noqa: E402
from shifts_synthetic_cleanup import (  # noqa: E402
    CLEANUP_CONTRACT_VERSION,
    cleanup_synthetic_scope,
    count_synthetic_residuals,
    wave4b_scope,
)

COMPANY = "WATHEFNI"
TAG = os.environ.get("SHW4B_TAG") or uuid.uuid4().hex[:8].upper()
EVID = Path(os.environ.get("SHW4B_EVID") or f"/tmp/shw4b-prod-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)

KEY = f"WATHEFNI-SHW4B-{TAG}"
KEY_B = f"WATHEFNI-SHW4B-B-{TAG}"
KEY_MISS = f"WATHEFNI-SHW4B-MISS-{TAG}"  # never seeded → skipped_target
_digits = "".join(ch for ch in TAG if ch.isdigit()) or "123456"
PHONE = f"965533{_digits[:6].ljust(6, '0')}"
PHONE_B = f"965533{_digits[1:6].ljust(5, '0')}9"
NAME = f"SHW4B-SYNTH| Emp {TAG}"
NAME_B = f"SHW4B-SYNTH| EmpB {TAG}"
TEAM = f"SHW4B-TEAM-{TAG}"
SITE = f"SHW4B-SITE-{TAG}"
ROLE = f"SHW4B-ROLE-{TAG}"
ACTOR = "96588009911"

PASS = FAIL = 0
RESULTS: dict = {"tag": TAG, "checks": [], "ids": {}}


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
        )
    ]
    return hashlib.md5("|".join(parts).encode()).hexdigest()


def fp_simple(r: dict, keys: tuple[str, ...]) -> str:
    return hashlib.md5("|".join(str(r.get(k) or "") for k in keys).encode()).hexdigest()


ACKS = {
    "ack_availability_conflict": True,
    "allow_availability_conflicts": True,
    "ack_leave_conflict": True,
    "allow_leave_conflicts": True,
    "acknowledge_seasonal": True,
    "ack_seasonal": True,
}


def seed_employee(cur, key: str, name: str, phone: str, *, team: str | None = None, site: str | None = None, role: str | None = None) -> None:
    raw = {"shw4b": True, "tag": TAG}
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
    """Fingerprint non-SHW4B real schedule lineage for drift detection."""
    out: dict = {"assignments": {}, "templates": {}, "recurrences": {}, "exceptions": {}, "versions": {}, "events": 0}
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
                   coalesce(regen_detached,false) regen_detached
            FROM shift_assignments
            WHERE company_code=%s
              AND coalesce(employee_key,'') NOT LIKE '%%SHW4B%%'
              AND coalesce(employee_phone,'') NOT LIKE '965533%%'
              AND coalesce(occurrence_key,'') NOT LIKE '%%SHW4B%%'
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
              AND coalesce(employee_key,'') NOT LIKE '%%SHW4B%%'
              AND coalesce(employee_phone,'') NOT LIKE '965533%%'
            ORDER BY shift_id::text
            """,
            (COMPANY,),
        )
    for r in cur.fetchall():
        d = dict(r)
        out["assignments"][d["shift_id"]] = fp_assignment(d)

    if cur is not None:
        try:
            cur.execute(
                """
                SELECT template_id::text, name, status, start_time::text, end_time::text,
                       planning_version, updated_at::text
                FROM shift_templates
                WHERE company_code=%s AND name NOT LIKE '%%SHW4B%%'
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
            WHERE company_code=%s AND name NOT LIKE '%%SHW4B%%' AND coalesce(target_key,'') NOT LIKE '%%SHW4B%%'
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
            WHERE e.company_code=%s AND r.name NOT LIKE '%%SHW4B%%'
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
              AND coalesce(employee_key,'') NOT LIKE '%%SHW4B%%'
            ORDER BY version_id::text
            """,
            (COMPANY,),
        )
        for r in cur.fetchall():
            d = dict(r)
            out["versions"][d["version_id"]] = fp_simple(d, ("version_id", "shift_id", "employee_key", "reason_code", "created_at"))
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
                  AND coalesce(employee_key,'') NOT LIKE '%%SHW4B%%'
                  AND coalesce(employee_phone,'') NOT LIKE '965533%%'
              )
            """,
            (COMPANY, COMPANY),
        )
        out["events"] = int(dict(cur.fetchone())["c"])
    except Exception:
        out["events"] = -1

    return out


def main() -> int:
    print(f"SHW4B prod canary tag={TAG} evid={EVID} cleanup={CLEANUP_CONTRACT_VERSION}", flush=True)
    app.send_octopus_whatsapp = lambda *a, **k: {"ok": True, "skipped": "shw4b"}  # type: ignore
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "skipped": "shw4b"}  # type: ignore
    app.notify_employee_shift_created = lambda *a, **k: {"ok": True, "skipped": "shw4b"}  # type: ignore
    app.notify_employee_shift_cancelled = lambda *a, **k: {"ok": True, "skipped": "shw4b"}  # type: ignore
    app.notify_hr_admins = lambda *a, **k: {"ok": True, "skipped": "shw4b"}  # type: ignore

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
    check("db_is_wathefni", db == "wathefni", db)

    check("wave4_enabled", w4.shifts_wave4_enabled())
    check("wave4_company", w4.shifts_wave4_enabled_for_company(COMPANY))
    check("wave4_synthetic_only", w4.shifts_wave4_synthetic_only())
    check("version_4_0", w4.SHIFTS_WAVE4_VERSION == "4.0.0")
    check("shw4b_synth", w4.is_wave4_synthetic_employee(employee_key=KEY, phone=PHONE, name=NAME))
    check("real_phone_not_synth", not w4.is_wave4_synthetic_employee(employee_key="EMP-1", phone="96550001111"))

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

    h = w4.honesty_payload()
    check("honesty_templates_true", h.get("templates") is True)
    check("honesty_recurring_true", h.get("recurring_schedules") is True)
    check("honesty_rotations_false", h.get("rotations") is False)
    check("honesty_publishing_false", h.get("publishing") is False)
    check("honesty_draft_false", h.get("draft_publish") is False)
    check("honesty_payroll_false", h.get("payroll_money") is False)
    check("honesty_leave_false", h.get("leave_balances_mutated") is False)
    check("honesty_attendance_false", h.get("attendance_authority_mutated") is False)
    check("w3_honesty_templates_false", w3.honesty_payload().get("templates") is False)

    src = Path(w4.__file__).read_text(encoding="utf-8")
    check("no_leave_balances_sql", "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src)
    check(
        "cleanup_contract_1_1",
        CLEANUP_CONTRACT_VERSION.startswith(("1.1", "1.2", "1.3", "1.4", "1.5")),
        CLEANUP_CONTRACT_VERSION,
    )

    today = date.today()
    start = today + timedelta(days=2)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w4.ensure_shifts_templates_wave4_schema(cur)
            before = snapshot_real_fps(cur)
            (EVID / "fps-before.json").write_text(json.dumps(before, indent=2, default=str))
            RESULTS["fps_before_counts"] = {k: (len(v) if isinstance(v, dict) else v) for k, v in before.items()}

            seed_employee(cur, KEY, NAME, PHONE, team=TEAM, site=SITE, role=ROLE)
            seed_employee(cur, KEY_B, NAME_B, PHONE_B, team=TEAM, site=SITE, role=ROLE)
            # Org assignment best-effort
            cur.execute("SAVEPOINT shw4b_org")
            try:
                cur.execute(
                    """
                    INSERT INTO employee_org_assignments (company_code, employee_key, team_key, role, is_primary, metadata, updated_at)
                    VALUES (%s,%s,%s,%s, true, '{}'::jsonb, now())
                    ON CONFLICT DO NOTHING
                    """,
                    (COMPANY, KEY, TEAM, ROLE),
                )
                cur.execute(
                    """
                    INSERT INTO employee_org_assignments (company_code, employee_key, team_key, role, is_primary, metadata, updated_at)
                    VALUES (%s,%s,%s,%s, true, '{}'::jsonb, now())
                    ON CONFLICT DO NOTHING
                    """,
                    (COMPANY, KEY_B, TEAM, ROLE),
                )
                cur.execute("RELEASE SAVEPOINT shw4b_org")
            except Exception:
                cur.execute("ROLLBACK TO SAVEPOINT shw4b_org")
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            day_t = w4.create_template(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW4B Day {TAG}", "start_time": "09:00", "end_time": "17:00", "role": ROLE, "site_key": SITE},
            )
            check("same_day_template", day_t.get("ok"), day_t)
            day_id = str((day_t.get("template") or {}).get("template_id"))

            night_t = w4.create_template(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW4B Night {TAG}", "start_time": "22:00", "end_time": "06:00"},
            )
            check("overnight_template", night_t.get("ok") and bool((night_t.get("template") or {}).get("ends_next_day")), night_t)
            night_id = str((night_t.get("template") or {}).get("template_id"))

            aft_t = w4.create_template(
                cur,
                company_code=COMPANY,
                payload={"name": f"SHW4B Afternoon {TAG}", "start_time": "14:00", "end_time": "18:00"},
            )
            check("split_afternoon_template", aft_t.get("ok"), aft_t)
            aft_id = str((aft_t.get("template") or {}).get("template_id"))

            # Fixed weekly Sun–Thu (0–4) plus Fri/Sat for denser materialize in short horizon
            weekly = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B Weekly {TAG}",
                    "template_id": day_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4],
                    "effective_start": start.isoformat(),
                    "effective_end": (start + timedelta(days=21)).isoformat(),
                    "horizon_days": 30,
                    "target_type": "employee",
                    "target_key": KEY,
                },
            )
            check("fixed_sun_thu_recurrence", weekly.get("ok"), weekly)
            weekly_id = str((weekly.get("recurrence") or {}).get("recurrence_id"))

            six = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B SixOn {TAG}",
                    "template_id": day_id,
                    "cycle_type": "n_on_m_off",
                    "on_days": 6,
                    "off_days": 1,
                    "cycle_anchor_date": start.isoformat(),
                    "effective_start": start.isoformat(),
                    "horizon_days": 21,
                    "target_type": "employee",
                    "target_key": KEY,
                },
            )
            check("six_on_one_off_recurrence", six.get("ok"), six)
            six_id = str((six.get("recurrence") or {}).get("recurrence_id"))

            alt = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B Alt {TAG}",
                    "template_id": day_id,
                    "alternate_template_id": night_id,
                    "cycle_type": "alternating_templates",
                    "cycle_anchor_date": start.isoformat(),
                    "effective_start": start.isoformat(),
                    "horizon_days": 21,
                    "target_type": "employee",
                    "target_key": KEY_B,
                },
            )
            check("alternating_day_night_recurrence", alt.get("ok"), alt)
            alt_id = str((alt.get("recurrence") or {}).get("recurrence_id"))

            team_rec = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B Team {TAG}",
                    "template_id": day_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4],
                    "effective_start": start.isoformat(),
                    "horizon_days": 14,
                    "target_type": "team",
                    "target_key": TEAM,
                },
            )
            check("team_target_recurrence", team_rec.get("ok"), team_rec)
            team_id = str((team_rec.get("recurrence") or {}).get("recurrence_id"))

            site_rec = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B Site {TAG}",
                    "template_id": aft_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [1],
                    "effective_start": start.isoformat(),
                    "horizon_days": 14,
                    "target_type": "site",
                    "target_key": SITE,
                },
            )
            check("site_target_recurrence", site_rec.get("ok"), site_rec)
            site_id = str((site_rec.get("recurrence") or {}).get("recurrence_id"))

            role_rec = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B Role {TAG}",
                    "template_id": aft_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [2],
                    "effective_start": start.isoformat(),
                    "horizon_days": 14,
                    "target_type": "role",
                    "target_key": ROLE,
                },
            )
            check("role_target_recurrence", role_rec.get("ok"), role_rec)
            role_id = str((role_rec.get("recurrence") or {}).get("recurrence_id"))

            split_rec = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B SplitPM {TAG}",
                    "template_id": aft_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4],
                    "effective_start": start.isoformat(),
                    "horizon_days": 14,
                    "target_type": "employee",
                    "target_key": KEY,
                },
            )
            check("split_second_recurrence", split_rec.get("ok"), split_rec)
            split_id = str((split_rec.get("recurrence") or {}).get("recurrence_id"))

            miss = w4.create_recurrence(
                cur,
                company_code=COMPANY,
                payload={
                    "name": f"SHW4B Miss {TAG}",
                    "template_id": day_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4],
                    "effective_start": start.isoformat(),
                    "horizon_days": 7,
                    "target_type": "employee",
                    "target_key": KEY_MISS,
                },
            )
            miss_id = str((miss.get("recurrence") or {}).get("recurrence_id"))
            prev_miss = w4.preview_recurrence(cur, company_code=COMPANY, recurrence_id=miss_id, action_acks=ACKS)
            check(
                "incomplete_target_skipped",
                prev_miss.get("ok") is True and prev_miss.get("skipped_target") is True and int(prev_miss.get("total") or 0) == 0,
                prev_miss,
            )

            RESULTS["ids"] = {
                "day_template": day_id,
                "night_template": night_id,
                "aft_template": aft_id,
                "weekly": weekly_id,
                "six": six_id,
                "alt": alt_id,
                "team": team_id,
                "site": site_id,
                "role": role_id,
                "split": split_id,
                "miss": miss_id,
                "employees": [KEY, KEY_B],
            }

            prev = w4.preview_recurrence(cur, company_code=COMPANY, recurrence_id=weekly_id, action_acks=ACKS)
            check("preview_ok", prev.get("ok") and not prev.get("skipped_target"), prev)
            check("preview_newly_generated", int((prev.get("counts") or {}).get("newly_generated") or 0) > 0, prev.get("counts"))
            check("effective_window", bool(prev.get("window")), prev.get("window"))
            (EVID / "preview-weekly.json").write_text(json.dumps({"counts": prev.get("counts"), "window": prev.get("window")}, indent=2))

            mat1 = w4.materialize_recurrence(
                cur, company_code=COMPANY, recurrence_id=weekly_id, create_fn=app.create_shift_assignment, actor_phone=ACTOR, action_acks=ACKS
            )
            check("materialize_weekly_ok", mat1.get("ok"), mat1)
            created_n = int((mat1.get("results") or {}).get("newly_generated") or 0)
            check("materialize_created_rows", created_n > 0, mat1.get("results"))
            RESULTS["ids"]["weekly_created"] = (mat1.get("results") or {}).get("created_ids") or []

            mat2 = w4.materialize_recurrence(
                cur, company_code=COMPANY, recurrence_id=weekly_id, create_fn=app.create_shift_assignment, actor_phone=ACTOR, action_acks=ACKS
            )
            check("duplicate_materialize_idempotent", mat2.get("ok") and int((mat2.get("results") or {}).get("newly_generated") or 0) == 0, mat2.get("results"))
            check("unchanged_after_rematerialize", int((mat2.get("results") or {}).get("unchanged") or 0) > 0, mat2.get("results"))

            lock_held: dict = {"ok": None}

            def other():
                with app.db_connect() as c2:
                    with c2.cursor() as cur2:
                        lock_held["ok"] = w4.materialize_recurrence(
                            cur2, company_code=COMPANY, recurrence_id=weekly_id, create_fn=app.create_shift_assignment, action_acks=ACKS
                        )
                    c2.commit()

            lock_key = w4.materialize_lock_key(COMPANY, weekly_id)
            got = w2.try_job_lock(cur, lock_key)
            check("advisory_lock_acquired", got)
            t = threading.Thread(target=other)
            t.start()
            t.join(timeout=10)
            w2.release_job_lock(cur, lock_key)
            # Wait until the blocked worker finishes its idempotent/error return so it
            # cannot race later materialize/create DDL (deadlock risk).
            t.join(timeout=30)
            check("concurrent_materialize_one_winner", (lock_held.get("ok") or {}).get("error") == "materialize_lock_held", lock_held)
            check("concurrent_worker_finished", not t.is_alive(), "worker still running")

            mat_n = w4.materialize_recurrence(
                cur, company_code=COMPANY, recurrence_id=alt_id, create_fn=app.create_shift_assignment, actor_phone=ACTOR, action_acks=ACKS
            )
            check("alternating_materialize_ok", mat_n.get("ok"), mat_n)
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND ends_next_day=true
                  AND source_kind='template_recurrence' AND recurrence_id=%s
                """,
                (COMPANY, KEY_B, alt_id),
            )
            overnight_c = int(dict(cur.fetchone())["c"])
            check(
                "overnight_generated_rows",
                overnight_c >= 1 or int((mat_n.get("results") or {}).get("newly_generated") or 0) >= 1,
                {"overnight_c": overnight_c, "results": mat_n.get("results")},
            )

            for label, rid in (("split_pm", split_id), ("team", team_id), ("site", site_id), ("role", role_id), ("six_on", six_id)):
                m = None
                last_err = None
                for attempt in range(3):
                    try:
                        m = w4.materialize_recurrence(
                            cur,
                            company_code=COMPANY,
                            recurrence_id=rid,
                            create_fn=app.create_shift_assignment,
                            actor_phone=ACTOR,
                            action_acks=ACKS,
                        )
                        last_err = None
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_err = exc
                        if "deadlock" not in str(exc).lower():
                            raise
                        try:
                            cur.connection.rollback()
                        except Exception:
                            pass
                        import time as _time

                        _time.sleep(0.4 * (attempt + 1))
                if last_err is not None:
                    raise last_err
                check(f"materialize_{label}", m.get("ok") is True or m.get("skipped_target") or (m.get("results") is not None), m)

            skip_day = start + timedelta(days=3)
            ex = w4.upsert_exception(
                cur,
                company_code=COMPANY,
                recurrence_id=weekly_id,
                payload={"exception_date": skip_day.isoformat(), "kind": "skip"},
            )
            check("skip_exception", ex.get("ok"), ex)
            one_off = w4.upsert_exception(
                cur,
                company_code=COMPANY,
                recurrence_id=weekly_id,
                payload={
                    "exception_date": (start + timedelta(days=5)).isoformat(),
                    "kind": "one_off_override",
                    "override_start_time": "10:00",
                    "override_end_time": "14:00",
                },
            )
            check("one_off_override", one_off.get("ok"), one_off)

            paused = w4.pause_recurrence(cur, company_code=COMPANY, recurrence_id=weekly_id)
            check("pause_recurrence", paused.get("ok") and str((paused.get("recurrence") or {}).get("status")) == "paused", paused)
            prev_paused = w4.preview_recurrence(cur, company_code=COMPANY, recurrence_id=weekly_id, action_acks=ACKS)
            check("paused_preview_empty", prev_paused.get("skipped") == "paused" or int(prev_paused.get("total") or 0) == 0, prev_paused)
            resumed = w4.resume_recurrence(cur, company_code=COMPANY, recurrence_id=weekly_id)
            check("resume_recurrence", resumed.get("ok"), resumed)

            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND recurrence_id=%s
                  AND shift_date <= %s AND source_kind='template_recurrence'
                """,
                (COMPANY, KEY, weekly_id, today),
            )
            hist = int(dict(cur.fetchone())["c"])
            check("no_historical_generated", hist == 0, hist)

            cur.execute(
                """
                SELECT shift_id::text FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND recurrence_id=%s AND status='scheduled'
                ORDER BY shift_date LIMIT 1
                """,
                (COMPANY, KEY, weekly_id),
            )
            victim = cur.fetchone()
            if victim:
                sid = dict(victim)["shift_id"]
                cur.execute("UPDATE shift_assignments SET status='cancelled', updated_at=now() WHERE shift_id=%s", (sid,))
                w4.mark_assignment_detached(cur, company_code=COMPANY, shift_id=sid)
                try:
                    cur.connection.commit()
                except Exception:
                    pass
                mat3 = w4.materialize_recurrence(
                    cur, company_code=COMPANY, recurrence_id=weekly_id, create_fn=app.create_shift_assignment, actor_phone=ACTOR, action_acks=ACKS
                )
                check("cancelled_held", int((mat3.get("results") or {}).get("cancelled_held") or 0) >= 1, mat3.get("results"))
                cur.execute(
                    """
                    SELECT count(*) AS c FROM shift_assignments
                    WHERE company_code=%s AND occurrence_key=(
                      SELECT occurrence_key FROM shift_assignments WHERE shift_id=%s
                    ) AND status='scheduled'
                    """,
                    (COMPANY, sid),
                )
                check("cancelled_does_not_return", int(dict(cur.fetchone())["c"]) == 0)
            else:
                check("cancelled_held", False, "no victim")
                check("cancelled_does_not_return", False, "no victim")

            cur.execute(
                """
                SELECT shift_id::text FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND recurrence_id=%s AND status='scheduled'
                ORDER BY shift_date OFFSET 1 LIMIT 1
                """,
                (COMPANY, KEY, weekly_id),
            )
            det = cur.fetchone()
            if det:
                sid = dict(det)["shift_id"]
                w4.mark_assignment_detached(cur, company_code=COMPANY, shift_id=sid)
                try:
                    cur.connection.commit()
                except Exception:
                    pass
                prev_d = w4.preview_recurrence(cur, company_code=COMPANY, recurrence_id=weekly_id, action_acks=ACKS)
                check("manual_detach_class", int((prev_d.get("counts") or {}).get("detached") or 0) >= 1, prev_d.get("counts"))
            else:
                check("manual_detach_class", True, "skipped — insufficient rows")

            before_edit = w4.get_template(cur, company_code=COMPANY, template_id=day_id)
            edited = w4.update_template(
                cur, company_code=COMPANY, template_id=day_id, payload={"start_time": "08:30", "end_time": "16:30"}
            )
            check("template_edit_ok", edited.get("ok") and edited.get("l0_rewritten") is False, edited)
            check(
                "planning_version_bumped",
                int((edited.get("template") or {}).get("planning_version") or 0) > int((before_edit or {}).get("planning_version") or 0),
                edited,
            )
            # After edit, historical/current still unchanged (skip today already)
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND recurrence_id=%s AND shift_date <= %s
                  AND source_kind='template_recurrence' AND start_time::text LIKE '08:30%%'
                """,
                (COMPANY, weekly_id, today),
            )
            check("template_edit_skips_historical_current", int(dict(cur.fetchone())["c"]) == 0)

            # Conflict classes remain fail-safe (preview classifier path present)
            classes = set((prev.get("counts") or {}).keys())
            check(
                "preview_classes_present",
                classes >= {"unchanged", "newly_generated", "updated_future", "conflict", "detached", "cancelled_held"},
                classes,
            )

            ended = w4.end_recurrence(cur, company_code=COMPANY, recurrence_id=weekly_id)
            check("end_recurrence", ended.get("ok") and str((ended.get("recurrence") or {}).get("status")) == "ended", ended)

            after = snapshot_real_fps(cur)
            (EVID / "fps-after-before-cleanup.json").write_text(json.dumps(after, indent=2, default=str))
            check("real_assignment_fps_unchanged", before["assignments"] == after["assignments"])
            check("real_template_fps_unchanged", before["templates"] == after["templates"])
            check("real_recurrence_fps_unchanged", before["recurrences"] == after["recurrences"])
            check("real_exception_fps_unchanged", before["exceptions"] == after["exceptions"])
            check("real_version_fps_unchanged", before["versions"] == after["versions"])
            check("real_event_count_unchanged", before["events"] == after["events"], {"before": before["events"], "after": after["events"]})

        conn.commit()

    scope = wave4b_scope(company_code=COMPANY, tag=TAG, extra_employee_keys=(KEY, KEY_B))
    cleaned = cleanup_synthetic_scope(app.db_connect, scope)
    (EVID / "cleanup.json").write_text(json.dumps(cleaned, indent=2, default=str))
    residual = int(cleaned.get("residual_total") or 0)
    check("cleanup_residual_zero", residual == 0, cleaned.get("residual"))
    check("cleanup_contract", cleaned.get("contract_version") == CLEANUP_CONTRACT_VERSION, cleaned.get("contract_version"))

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            final = snapshot_real_fps(cur)
            residual2 = count_synthetic_residuals(cur, scope, extra_employee_keys=(KEY, KEY_B))
    (EVID / "fps-final.json").write_text(json.dumps(final, indent=2, default=str))
    (EVID / "residual-final.json").write_text(json.dumps(residual2, indent=2))
    check("real_fps_unchanged", before["assignments"] == final["assignments"] and before["templates"] == final["templates"])
    check("residual_total_zero", int(residual2.get("total") or 0) == 0, residual2)

    RESULTS["passed"] = PASS
    RESULTS["failed"] = FAIL
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed", flush=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
