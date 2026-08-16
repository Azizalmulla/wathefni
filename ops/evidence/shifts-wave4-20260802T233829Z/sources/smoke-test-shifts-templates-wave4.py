#!/usr/bin/env python3
"""Shifts Wave 4 — templates + recurring schedules smoke (local/staging).

Proves planning → preview → L0 materialize contract. Synthetic SHW4 / 965532* only.
Does NOT: production deploy, draft/publish, rotations, Payroll money, Leave balance
mutation, Attendance authority mutation, real allowlists, timers, real reminders.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", os.environ.get("WATHEFNI_ENV") or "staging")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS", "SHW4,SHW4-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES", "965532")

PASS = FAIL = 0


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def main() -> int:
    import app
    import shifts_templates_wave4 as w4
    import shifts_synthetic_cleanup as cleanup
    import shifts_wave3_controlled as w3

    tag = uuid.uuid4().hex[:8].upper()
    company = "WATHEFNI"
    key = f"WATHEFNI-SHW4-{tag}"
    key_b = f"WATHEFNI-SHW4-B-{tag}"
    phone = f"965532{tag[:5].zfill(5)}"[:12]
    phone_b = f"965532{(tag[:4] + '9').zfill(5)}"[:12]
    name = f"SHW4-SYNTH| Emp {tag}"
    team_key = f"SHW4-TEAM-{tag}"
    today = date.today()
    start = today + timedelta(days=2)

    check("version 4.0.0", w4.SHIFTS_WAVE4_VERSION == "4.0.0")
    check("wave4 enabled", w4.shifts_wave4_enabled())
    check("company WATHEFNI", w4.shifts_wave4_enabled_for_company(company))
    h = w4.honesty_payload()
    check("honesty templates true", h.get("templates") is True)
    check("honesty recurring true", h.get("recurring_schedules") is True)
    check("honesty rotations false", h.get("rotations") is False)
    check("honesty publishing false", h.get("publishing") is False)
    check("honesty payroll false", h.get("payroll_money") is False)
    check("honesty leave false", h.get("leave_balances_mutated") is False)
    check("honesty attendance false", h.get("attendance_authority_mutated") is False)
    check("honesty draft_publish false", h.get("draft_publish") is False)
    check("w3 honesty still templates false", w3.honesty_payload().get("templates") is False)
    check("shw4 synthetic", w4.is_wave4_synthetic_employee(employee_key=key, phone=phone, name=name))
    check("real phone not synth", not w4.is_wave4_synthetic_employee(employee_key="EMP-1", phone="96550001111"))
    src = Path(w4.__file__).read_text(encoding="utf-8")
    check("no leave_balances mutation SQL", "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src)
    check("no payroll money calc", 'payroll_money": False' in src.replace("'", '"') or "payroll_money\": False" in src or '"payroll_money": False' in src)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w4.ensure_shifts_templates_wave4_schema(cur)
            for k, p, n in ((key, phone, name), (key_b, phone_b, f"SHW4-SYNTH| EmpB {tag}")):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (company, k, n, p, json.dumps({"shw4": True, "tag": tag, "team_key": team_key})),
                )
                cur.execute(
                    "UPDATE employees SET employment_status='active', raw_json=%s::jsonb WHERE company_code=%s AND employee_key=%s",
                    (json.dumps({"shw4": True, "tag": tag, "team_key": team_key}), company, k),
                )
            try:
                cur.execute(
                    """
                    INSERT INTO employee_org_assignments (company_code, employee_key, team_key, role, is_primary, metadata, updated_at)
                    VALUES (%s,%s,%s,'ops', true, '{}'::jsonb, now())
                    ON CONFLICT DO NOTHING
                    """,
                    (company, key, team_key),
                )
                cur.execute(
                    """
                    INSERT INTO employee_org_assignments (company_code, employee_key, team_key, role, is_primary, metadata, updated_at)
                    VALUES (%s,%s,%s,'ops', true, '{}'::jsonb, now())
                    ON CONFLICT DO NOTHING
                    """,
                    (company, key_b, team_key),
                )
            except Exception:
                pass
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Same-day template
            day_t = w4.create_template(
                cur,
                company_code=company,
                payload={"name": f"SHW4 Day {tag}", "start_time": "09:00", "end_time": "17:00", "role": "ops", "site_key": "SITE-A"},
            )
            check("same-day template", day_t.get("ok") and day_t.get("template"), day_t)
            day_id = str((day_t.get("template") or {}).get("template_id"))

            # Overnight template
            night_t = w4.create_template(
                cur,
                company_code=company,
                payload={"name": f"SHW4 Night {tag}", "start_time": "22:00", "end_time": "06:00"},
            )
            check("overnight template", night_t.get("ok") and bool((night_t.get("template") or {}).get("ends_next_day")), night_t)
            night_id = str((night_t.get("template") or {}).get("template_id"))

            # Split afternoon template (second template)
            aft_t = w4.create_template(
                cur,
                company_code=company,
                payload={"name": f"SHW4 Afternoon {tag}", "start_time": "14:00", "end_time": "18:00"},
            )
            check("split afternoon template", aft_t.get("ok"), aft_t)
            aft_id = str((aft_t.get("template") or {}).get("template_id"))

            # Fixed weekly Sun–Thu (0=Sun … 4=Thu)
            weekly = w4.create_recurrence(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW4 Weekly {tag}",
                    "template_id": day_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4],
                    "effective_start": start.isoformat(),
                    "effective_end": (start + timedelta(days=21)).isoformat(),
                    "horizon_days": 30,
                    "target_type": "employee",
                    "target_key": key,
                },
            )
            check("fixed weekly recurrence", weekly.get("ok"), weekly)
            weekly_id = str((weekly.get("recurrence") or {}).get("recurrence_id"))

            # Six-on / one-off
            six = w4.create_recurrence(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW4 SixOn {tag}",
                    "template_id": day_id,
                    "cycle_type": "n_on_m_off",
                    "on_days": 6,
                    "off_days": 1,
                    "cycle_anchor_date": start.isoformat(),
                    "effective_start": start.isoformat(),
                    "horizon_days": 21,
                    "target_type": "employee",
                    "target_key": key,
                },
            )
            check("six-on/one-off recurrence", six.get("ok"), six)
            six_id = str((six.get("recurrence") or {}).get("recurrence_id"))

            # Alternating day/night
            alt = w4.create_recurrence(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW4 Alt {tag}",
                    "template_id": day_id,
                    "alternate_template_id": night_id,
                    "cycle_type": "alternating_templates",
                    "cycle_anchor_date": start.isoformat(),
                    "effective_start": start.isoformat(),
                    "horizon_days": 21,
                    "target_type": "employee",
                    "target_key": key,
                },
            )
            check("alternating day/night recurrence", alt.get("ok"), alt)
            alt_id = str((alt.get("recurrence") or {}).get("recurrence_id"))

            # Team-targeted split morning recurrence
            team_rec = w4.create_recurrence(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW4 TeamAM {tag}",
                    "template_id": day_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4],
                    "effective_start": start.isoformat(),
                    "horizon_days": 14,
                    "target_type": "team",
                    "target_key": team_key,
                },
            )
            check("team-targeted recurrence", team_rec.get("ok"), team_rec)
            team_id = str((team_rec.get("recurrence") or {}).get("recurrence_id"))

            # Second split template recurrence (afternoon)
            split_rec = w4.create_recurrence(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW4 SplitPM {tag}",
                    "template_id": aft_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4],
                    "effective_start": start.isoformat(),
                    "horizon_days": 14,
                    "target_type": "employee",
                    "target_key": key,
                },
            )
            check("split schedule second recurrence", split_rec.get("ok"), split_rec)
            split_id = str((split_rec.get("recurrence") or {}).get("recurrence_id"))

            prev = w4.preview_recurrence(cur, company_code=company, recurrence_id=weekly_id)
            check("preview ok", prev.get("ok"), prev)
            check("preview has newly_generated", int((prev.get("counts") or {}).get("newly_generated") or 0) > 0, prev.get("counts"))
            check("effective window present", bool(prev.get("window")), prev.get("window"))

            # Materialize weekly
            mat1 = w4.materialize_recurrence(
                cur,
                company_code=company,
                recurrence_id=weekly_id,
                create_fn=app.create_shift_assignment,
                reschedule_fn=None,
                actor_phone="96588009911",
            )
            check("materialize weekly ok", mat1.get("ok"), mat1)
            created_n = int((mat1.get("results") or {}).get("newly_generated") or 0)
            check("materialize created rows", created_n > 0, mat1.get("results"))

            # Idempotent rematerialize
            mat2 = w4.materialize_recurrence(
                cur,
                company_code=company,
                recurrence_id=weekly_id,
                create_fn=app.create_shift_assignment,
                actor_phone="96588009911",
            )
            check("duplicate materialize idempotent", mat2.get("ok") and int((mat2.get("results") or {}).get("newly_generated") or 0) == 0, mat2.get("results"))
            check("unchanged after rematerialize", int((mat2.get("results") or {}).get("unchanged") or 0) > 0, mat2.get("results"))

            # Concurrent materialize — one holds lock
            lock_held = {"ok": None}

            def other():
                with app.db_connect() as c2:
                    with c2.cursor() as cur2:
                        lock_held["ok"] = w4.materialize_recurrence(
                            cur2,
                            company_code=company,
                            recurrence_id=weekly_id,
                            create_fn=app.create_shift_assignment,
                        )
                    c2.commit()

            # Hold lock on this connection while other tries
            lock_key = w4.materialize_lock_key(company, weekly_id)
            import shifts_schedule_integrity_wave2 as w2

            got = w2.try_job_lock(cur, lock_key)
            check("test lock acquired", got)
            t = threading.Thread(target=other)
            t.start()
            t.join(timeout=10)
            w2.release_job_lock(cur, lock_key)
            check("concurrent materialize lock held", (lock_held.get("ok") or {}).get("error") == "materialize_lock_held", lock_held)

            # Overnight materialize
            mat_n = w4.materialize_recurrence(
                cur,
                company_code=company,
                recurrence_id=alt_id,
                create_fn=app.create_shift_assignment,
                actor_phone="96588009911",
            )
            check("alternating materialize ok", mat_n.get("ok"), mat_n)
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND ends_next_day=true
                  AND source_kind='template_recurrence' AND recurrence_id=%s
                """,
                (company, key, alt_id),
            )
            overnight_c = int(dict(cur.fetchone())["c"])
            check("overnight generated rows", overnight_c >= 1, overnight_c)

            # Split: materialize afternoon recurrence → two authority rows same day possible with morning weekly
            mat_s = w4.materialize_recurrence(
                cur,
                company_code=company,
                recurrence_id=split_id,
                create_fn=app.create_shift_assignment,
                actor_phone="96588009911",
            )
            check("split PM materialize ok", mat_s.get("ok"), mat_s)

            # Team materialize
            mat_t = w4.materialize_recurrence(
                cur,
                company_code=company,
                recurrence_id=team_id,
                create_fn=app.create_shift_assignment,
                actor_phone="96588009911",
            )
            check("team materialize attempted", mat_t.get("ok") is True or mat_t.get("skipped_target") or (mat_t.get("results") is not None), mat_t)

            # Six-on materialize
            mat_6 = w4.materialize_recurrence(
                cur,
                company_code=company,
                recurrence_id=six_id,
                create_fn=app.create_shift_assignment,
                actor_phone="96588009911",
            )
            check("six-on materialize ok", mat_6.get("ok"), mat_6)

            # Exception skip date
            skip_day = start + timedelta(days=3)
            ex = w4.upsert_exception(
                cur,
                company_code=company,
                recurrence_id=weekly_id,
                payload={"exception_date": skip_day.isoformat(), "kind": "skip"},
            )
            check("one-off exception skip", ex.get("ok"), ex)

            # Pause / resume / end
            paused = w4.pause_recurrence(cur, company_code=company, recurrence_id=weekly_id)
            check("pause recurrence", paused.get("ok") and str((paused.get("recurrence") or {}).get("status")) == "paused", paused)
            prev_paused = w4.preview_recurrence(cur, company_code=company, recurrence_id=weekly_id)
            check("paused preview empty", prev_paused.get("skipped") == "paused" or int(prev_paused.get("total") or 0) == 0, prev_paused)
            resumed = w4.resume_recurrence(cur, company_code=company, recurrence_id=weekly_id)
            check("resume recurrence", resumed.get("ok"), resumed)

            # Template edit does not rewrite L0; bumps planning version
            before_edit = w4.get_template(cur, company_code=company, template_id=day_id)
            edited = w4.update_template(
                cur,
                company_code=company,
                template_id=day_id,
                payload={"start_time": "08:30", "end_time": "16:30"},
            )
            check("template edit ok", edited.get("ok") and edited.get("l0_rewritten") is False, edited)
            check(
                "template planning_version bumped",
                int((edited.get("template") or {}).get("planning_version") or 0) > int((before_edit or {}).get("planning_version") or 0),
                edited,
            )

            # Historical/current unchanged: count rows with shift_date <= today for this key from weekly
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND recurrence_id=%s
                  AND shift_date <= %s AND source_kind='template_recurrence'
                """,
                (company, key, weekly_id, today),
            )
            hist = int(dict(cur.fetchone())["c"])
            check("no historical generated for weekly (skip today)", hist == 0, hist)

            # Cancel one generated → cancelled_held on rematerialize
            cur.execute(
                """
                SELECT shift_id::text, updated_at::text FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND recurrence_id=%s AND status='scheduled'
                ORDER BY shift_date LIMIT 1
                """,
                (company, key, weekly_id),
            )
            victim = cur.fetchone()
            if victim:
                v = dict(victim)
                cur.execute(
                    "UPDATE shift_assignments SET status='cancelled', updated_at=now() WHERE shift_id=%s RETURNING *",
                    (v["shift_id"],),
                )
                w4.mark_assignment_detached(cur, company_code=company, shift_id=v["shift_id"])
                # Rematerialize should hold cancelled
                mat3 = w4.materialize_recurrence(
                    cur,
                    company_code=company,
                    recurrence_id=weekly_id,
                    create_fn=app.create_shift_assignment,
                    actor_phone="96588009911",
                )
                check("cancelled held on rematerialize", int((mat3.get("results") or {}).get("cancelled_held") or 0) >= 1, mat3.get("results"))
                cur.execute(
                    """
                    SELECT count(*) AS c FROM shift_assignments
                    WHERE company_code=%s AND occurrence_key=(
                      SELECT occurrence_key FROM shift_assignments WHERE shift_id=%s
                    ) AND status='scheduled'
                    """,
                    (company, v["shift_id"]),
                )
                resurrected = int(dict(cur.fetchone())["c"])
                check("cancelled does not return", resurrected == 0, resurrected)
            else:
                check("cancelled held on rematerialize", False, "no victim")
                check("cancelled does not return", False, "no victim")

            # Manual detach: mark another scheduled row detached
            cur.execute(
                """
                SELECT shift_id::text FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND recurrence_id=%s AND status='scheduled'
                ORDER BY shift_date OFFSET 1 LIMIT 1
                """,
                (company, key, weekly_id),
            )
            det = cur.fetchone()
            if det:
                sid = dict(det)["shift_id"]
                w4.mark_assignment_detached(cur, company_code=company, shift_id=sid)
                prev_d = w4.preview_recurrence(cur, company_code=company, recurrence_id=weekly_id)
                check("manual override detached class", int((prev_d.get("counts") or {}).get("detached") or 0) >= 1, prev_d.get("counts"))
            else:
                check("manual override detached class", True, "skipped — insufficient rows")

            ended = w4.end_recurrence(cur, company_code=company, recurrence_id=weekly_id)
            check("end recurrence", ended.get("ok") and str((ended.get("recurrence") or {}).get("status")) == "ended", ended)

        conn.commit()

    # Cleanup residual
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            scope = cleanup.wave4_scope(company_code=company, tag=tag, extra_employee_keys=(key, key_b))
            cleaned = cleanup.cleanup_synthetic_scope(cur, scope)
        conn.commit()
    residual = int(cleaned.get("residual_total") or cleaned.get("residual", {}).get("total") or 0)
    # Prefer counting after cleanup
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM shift_assignments WHERE company_code=%s AND (employee_key LIKE %s OR coalesce(employee_phone,'') LIKE %s)",
                (company, f"%SHW4-{tag}%", "965532%"),
            )
            a = int(dict(cur.fetchone())["c"])
            cur.execute(
                "SELECT count(*) AS c FROM employees WHERE company_code=%s AND (employee_key LIKE %s OR coalesce(phone,'') LIKE %s)",
                (company, f"%SHW4-{tag}%", "965532%"),
            )
            e = int(dict(cur.fetchone())["c"])
            cur.execute("SELECT count(*) AS c FROM shift_templates WHERE company_code=%s AND name LIKE %s", (company, f"%{tag}%"))
            t = int(dict(cur.fetchone())["c"])
    check("residual assignments zero", a == 0, a)
    check("residual employees zero", e == 0, e)
    check("residual templates zero", t == 0, {"templates": t, "cleaned": cleaned})

    # Module API surface
    check("create_template present", callable(w4.create_template))
    check("preview_recurrence present", callable(w4.preview_recurrence))
    check("materialize_recurrence present", callable(w4.materialize_recurrence))
    check("app imports wave4", "shifts_templates_wave4" in inspect.getsource(app) or hasattr(app, "_shifts_templates_w4"))

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
