#!/usr/bin/env python3
"""Shifts Wave 5 — draft/review/publish, open shifts, coverage smoke (local/staging).

Proves planning → draft → review → publish contract, open-shift workflow, coverage
rules, rollback, and optional direct L0. Synthetic SHW5 / 965534* only.
Does NOT: production deploy, Payroll money, Leave balance mutation, Attendance
authority mutation, real allowlists, timers, real reminders, PAM export.
"""
from __future__ import annotations

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

# Wave 5 synthetic gate
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS", "SHW5,SHW5-SYNTH|")
os.environ.setdefault("WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES", "965534")

# Wave 4 templates/recurrences (SHW5-named; no wave4 synthetic gate on create/classify)
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
    import shifts_publish_wave5 as w5
    import shifts_templates_wave4 as w4
    import shifts_synthetic_cleanup as cleanup
    import shifts_wave3_controlled as w3
    import shifts_schedule_integrity_wave2 as w2

    tag = uuid.uuid4().hex[:8].upper()
    company = "WATHEFNI"
    key = f"WATHEFNI-SHW5-{tag}"
    key_b = f"WATHEFNI-SHW5-B-{tag}"
    _digits = "".join(ch for ch in tag if ch.isdigit()) or "123456"
    phone = f"965534{_digits[:6].ljust(6, '0')}"
    phone_b = f"965534{_digits[1:6].ljust(5, '0')}9"
    name = f"SHW5-SYNTH| Emp {tag}"
    name_b = f"SHW5-SYNTH| EmpB {tag}"
    team_key = f"SHW5-TEAM-{tag}"
    today = date.today()
    start = today + timedelta(days=2)
    end = today + timedelta(days=10)
    acks = {
        "acknowledge_availability": True,
        "ack_availability_conflict": True,
        "allow_availability_conflicts": True,
        "allow_leave_conflicts": True,
        "ack_leave_conflict": True,
        "acknowledge_seasonal": True,
        "ack_seasonal": True,
        "confirm_overlap": True,
    }

    known_ids: dict[str, object] = {"shift_ids": []}

    # --- Honesty / unit (no DB) ------------------------------------------------
    check("version 5.0.0", w5.SHIFTS_WAVE5_VERSION == "5.0.0")
    check("wave5 enabled", w5.shifts_wave5_enabled())
    check("company WATHEFNI", w5.shifts_wave5_enabled_for_company(company))
    h = w5.honesty_payload()
    check("honesty publishing true", h.get("publishing") is True)
    check("honesty open_shifts true", h.get("open_shifts") is True)
    check("honesty draft_publish true", h.get("draft_publish") is True)
    check("honesty coverage_rules true", h.get("coverage_rules") is True)
    check("honesty payroll false", h.get("payroll_money") is False)
    check("honesty leave false", h.get("leave_balances_mutated") is False)
    check("honesty attendance false", h.get("attendance_authority_mutated") is False)
    check("honesty rotations false", h.get("rotations") is False)
    check("honesty pam_export false", h.get("pam_export") is False)
    check("w4 honesty publishing false", w4.honesty_payload().get("publishing") is False)
    check("w3 honesty templates false", w3.honesty_payload().get("templates") is False)
    check("shw5 synthetic key", w5.is_wave5_synthetic_employee(employee_key=key, phone=phone, name=name))
    check("real phone not synth", not w5.is_wave5_synthetic_employee(employee_key="EMP-1", phone="96550001111"))
    check("permission_matrix self_approval false", w5.permission_matrix().get("self_approval") is False)
    src = Path(w5.__file__).read_text(encoding="utf-8")
    check("no leave_balances mutation SQL", "UPDATE leave_balances" not in src and "INSERT INTO leave_balances" not in src)
    check("no payroll money calc", '"payroll_money": False' in src.replace("'", '"'))
    check("PERIOD_STATES complete", set(w5.PERIOD_STATES) >= {"draft", "in_review", "approved", "published", "superseded", "cancelled"})
    check("VERSION_STATES complete", set(w5.VERSION_STATES) >= {"draft", "in_review", "approved", "published", "superseded", "cancelled"})

    # --- DB section ------------------------------------------------------------
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w5.ensure_shifts_publish_wave5_schema(cur)
            w4.ensure_shifts_templates_wave4_schema(cur)

            # 1. Seed employees
            for k, p, n in ((key, phone, name), (key_b, phone_b, name_b)):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,%s::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (company, k, n, p, json.dumps({"shw5": True, "tag": tag, "team_key": team_key})),
                )
                cur.execute(
                    """
                    UPDATE employees SET name=%s, phone=%s, employment_status='active', raw_json=%s::jsonb, updated_at=now()
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (n, p, json.dumps({"shw5": True, "tag": tag, "team_key": team_key}), company, k),
                )
                cur.execute("SELECT 1 FROM employees WHERE company_code=%s AND employee_key=%s", (company, k))
                if not cur.fetchone():
                    raise RuntimeError(f"failed to seed employee {k}")
            try:
                cur.execute("SAVEPOINT shw5_org_seed")
                for k in (key, key_b):
                    cur.execute(
                        """
                        INSERT INTO employee_org_assignments (company_code, employee_key, team_key, role, is_primary, metadata, updated_at)
                        VALUES (%s,%s,%s,'ops', true, '{}'::jsonb, now())
                        ON CONFLICT DO NOTHING
                        """,
                        (company, k, team_key),
                    )
                cur.execute("RELEASE SAVEPOINT shw5_org_seed")
            except Exception:
                try:
                    cur.execute("ROLLBACK TO SAVEPOINT shw5_org_seed")
                except Exception:
                    pass
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w5.ensure_shifts_publish_wave5_schema(cur)
            w4.ensure_shifts_templates_wave4_schema(cur)

            # 2. Templates
            day_t = w4.create_template(
                cur,
                company_code=company,
                payload={"name": f"SHW5 Day {tag}", "start_time": "09:00", "end_time": "17:00", "role": "ops", "site_key": "SITE-A"},
            )
            check("day template", day_t.get("ok") and day_t.get("template"), day_t)
            day_id = str((day_t.get("template") or {}).get("template_id"))

            night_t = w4.create_template(
                cur,
                company_code=company,
                payload={"name": f"SHW5 Night {tag}", "start_time": "22:00", "end_time": "06:00"},
            )
            check("overnight template", night_t.get("ok") and bool((night_t.get("template") or {}).get("ends_next_day")), night_t)
            night_id = str((night_t.get("template") or {}).get("template_id"))

            # 3. Weekly recurrence
            weekly = w4.create_recurrence(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW5 Weekly {tag}",
                    "template_id": day_id,
                    "cycle_type": "weekly_weekdays",
                    "weekdays": [0, 1, 2, 3, 4, 5, 6],
                    "effective_start": start.isoformat(),
                    "effective_end": (start + timedelta(days=14)).isoformat(),
                    "horizon_days": 30,
                    "target_type": "employee",
                    "target_key": key,
                },
            )
            check("weekly recurrence", weekly.get("ok"), weekly)
            weekly_id = str((weekly.get("recurrence") or {}).get("recurrence_id"))

            # 4. Schedule period
            period_res = w5.create_period(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW5 Period {tag}",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "require_publish": True,
                    "team_key": team_key,
                },
                actor_phone=phone,
            )
            check("create period", period_res.get("ok"), period_res)
            period_id = str((period_res.get("period") or {}).get("period_id"))
            version_id = str((period_res.get("version") or {}).get("version_id"))
            known_ids["period_id"] = period_id

            # L0 count before draft
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'
                """,
                (company, key),
            )
            l0_before = int(dict(cur.fetchone())["c"])

            # 5. Generate draft from recurrence
            draft_gen = w5.generate_draft_from_recurrence(
                cur,
                company_code=company,
                period_id=period_id,
                recurrence_id=weekly_id,
                actor_phone=phone,
                action_acks=acks,
            )
            check("generate_draft ok", draft_gen.get("ok"), draft_gen)
            check("draft_rows > 0", int(draft_gen.get("draft_rows") or 0) > 0, draft_gen.get("draft_rows"))
            check("l0_written false", draft_gen.get("l0_written") is False, draft_gen)

            # 6. L0 unchanged after draft
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND status <> 'cancelled'
                """,
                (company, key),
            )
            l0_after_draft = int(dict(cur.fetchone())["c"])
            check("L0 unchanged after draft", l0_after_draft == l0_before, {"before": l0_before, "after": l0_after_draft})
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 7. Transition draft → in_review → approved
            tr1 = w5.transition_version(cur, company_code=company, version_id=version_id, to_state="in_review", actor_phone=phone)
            check("transition in_review", tr1.get("ok"), tr1)
            tr2 = w5.transition_version(cur, company_code=company, version_id=version_id, to_state="approved", actor_phone=phone)
            check("transition approved", tr2.get("ok"), tr2)

            # 8. Review diff
            diff = w5.review_diff(cur, company_code=company, version_id=version_id)
            check("review_diff ok", diff.get("ok"), diff)

            # 9. Coverage — warn rule (understaffed, no block)
            warn_rule = w5.upsert_coverage_rule(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW5 Warn {tag}",
                    "effective_start": start.isoformat(),
                    "effective_end": end.isoformat(),
                    "window_start": "09:00",
                    "window_end": "17:00",
                    "min_staff": 999,
                    "enforcement_mode": "warn",
                    "role": "ops",
                },
                actor_phone=phone,
            )
            check("coverage warn rule", warn_rule.get("ok"), warn_rule)
            period_row = w5.get_period(cur, company_code=company, period_id=period_id)
            cov_warn = w5.evaluate_coverage_for_version(cur, company_code=company, version_id=version_id, period=period_row)
            check("understaffed warning", int((cov_warn.get("summary") or {}).get("understaffed") or 0) > 0, cov_warn.get("summary"))
            check("warn blocks_publish false", cov_warn.get("blocks_publish") is False, cov_warn)

            # Block rule
            block_rule = w5.upsert_coverage_rule(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW5 Block {tag}",
                    "effective_start": start.isoformat(),
                    "effective_end": end.isoformat(),
                    "window_start": "09:00",
                    "window_end": "17:00",
                    "min_staff": 999,
                    "enforcement_mode": "block",
                    "role": "ops",
                },
                actor_phone=phone,
            )
            check("coverage block rule", block_rule.get("ok"), block_rule)
            cov_block = w5.evaluate_coverage_for_version(cur, company_code=company, version_id=version_id, period=period_row)
            check("block blocks_publish true", cov_block.get("blocks_publish") is True, cov_block)

            pub_blocked = w5.publish_version(
                cur,
                company_code=company,
                version_id=version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                publish_idempotency_key=f"SHW5-PUB|{tag}",
                action_acks=acks,
            )
            check("publish blocked by coverage", pub_blocked.get("error") == "coverage_block", pub_blocked)

            # Relax block so publish can proceed
            cur.execute(
                """
                UPDATE shift_coverage_rules SET enabled=false, updated_at=now()
                WHERE company_code=%s AND name=%s
                """,
                (company, f"SHW5 Block {tag}"),
            )
            cur.execute(
                """
                UPDATE shift_coverage_rules SET min_staff=1, enforcement_mode='warn', updated_at=now()
                WHERE company_code=%s AND name=%s
                """,
                (company, f"SHW5 Warn {tag}"),
            )

            # Overnight coverage window rule (calculation path)
            overnight_cov = w5.upsert_coverage_rule(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW5 OvernightCov {tag}",
                    "effective_start": start.isoformat(),
                    "effective_end": end.isoformat(),
                    "window_start": "22:00",
                    "window_end": "06:00",
                    "ends_next_day": True,
                    "min_staff": 0,
                    "enforcement_mode": "warn",
                },
                actor_phone=phone,
            )
            check("overnight coverage rule", overnight_cov.get("ok"), overnight_cov)

            # 10. Unresolved open shift in coverage findings
            unresolved = w5.create_open_shift(
                cur,
                company_code=company,
                payload={
                    "period_id": period_id,
                    "shift_date": (start + timedelta(days=1)).isoformat(),
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "notes": f"SHW5 unresolved {tag}",
                    "role": "ops",
                },
                actor_phone=phone,
            )
            check("unresolved open shift", unresolved.get("ok"), unresolved)
            unresolved_id = str((unresolved.get("open_shift") or {}).get("open_shift_id"))
            known_ids.setdefault("open_shift_ids", []).append(unresolved_id)

            cov_open = w5.evaluate_coverage_for_version(cur, company_code=company, version_id=version_id, period=period_row)
            check(
                "coverage unresolved_open_shift",
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
            # 11. Publish version (fresh txn — avoids DDL deadlock with create_fn)
            pub1 = w5.publish_version(
                cur,
                company_code=company,
                version_id=version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                publish_idempotency_key=f"SHW5-PUB|{tag}",
                action_acks=acks,
            )
            check("publish ok", pub1.get("ok"), pub1)
            first_version_id = version_id
            if pub1.get("results", {}).get("created_ids"):
                known_ids["shift_ids"] = list(pub1["results"]["created_ids"])

            # 12. Published L0 metadata
            cur.execute(
                """
                SELECT count(*) AS c FROM shift_assignments
                WHERE company_code=%s AND schedule_period_id=%s AND schedule_version_id=%s
                  AND schedule_source='published' AND status <> 'cancelled'
                """,
                (company, period_id, version_id),
            )
            pub_l0 = int(dict(cur.fetchone())["c"])
            check("published L0 with schedule metadata", pub_l0 > 0, pub_l0)

            # 13. Idempotent republish
            pub1b = w5.publish_version(
                cur,
                company_code=company,
                version_id=version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                publish_idempotency_key=f"SHW5-PUB|{tag}",
                action_acks=acks,
            )
            check("republish idempotent", pub1b.get("ok") and pub1b.get("idempotent") is True, pub1b)

            # 14. Concurrent publish lock
            lock_key = w5.publish_lock_key(company, period_id)
            lock_result: dict = {}

            def other_publish():
                with app.db_connect() as c2:
                    with c2.cursor() as cur2:
                        lock_result["res"] = w5.publish_version(
                            cur2,
                            company_code=company,
                            version_id=version_id,
                            create_fn=app.create_shift_assignment,
                            actor_phone=phone,
                            action_acks=acks,
                        )
                    c2.commit()

            got_lock = w2.try_job_lock(cur, lock_key)
            check("test lock acquired", got_lock)
            t = threading.Thread(target=other_publish)
            t.start()
            t.join(timeout=15)
            w2.release_job_lock(cur, lock_key)
            check(
                "concurrent publish lock held",
                (lock_result.get("res") or {}).get("error") == "publish_lock_held",
                lock_result.get("res"),
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 15–16. Second version draft and publish
            draft2 = w5.create_draft_from_published(cur, company_code=company, period_id=period_id, actor_phone=phone)
            check("create_draft_from_published", draft2.get("ok"), draft2)
            version2_id = str((draft2.get("version") or {}).get("version_id"))
            known_ids.setdefault("version_ids", []).append(version2_id)

            w5.transition_version(cur, company_code=company, version_id=version2_id, to_state="in_review", actor_phone=phone)
            w5.transition_version(cur, company_code=company, version_id=version2_id, to_state="approved", actor_phone=phone)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pub2 = w5.publish_version(
                cur,
                company_code=company,
                version_id=version2_id,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                publish_idempotency_key=f"SHW5-PUB2|{tag}",
                action_acks=acks,
            )
            check("publish second version", pub2.get("ok"), pub2)
            if pub2.get("results", {}).get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(pub2["results"]["created_ids"])
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 17. Rollback to first published version
            rollback = w5.rollback_to_version(
                cur,
                company_code=company,
                period_id=period_id,
                target_version_id=first_version_id,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                action_acks=acks,
            )
            check("rollback_to_version", rollback.get("ok"), rollback)
            if rollback.get("publish", {}).get("results", {}).get("created_ids"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + list(rollback["publish"]["results"]["created_ids"])

            # 18. Locked historical — skipped_locked on publish (optional proof)
            check(
                "skipped_locked field present",
                "skipped_locked" in (pub1.get("results") or {}),
                pub1.get("results"),
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 19. Open shift claim / approve workflow (overnight 22–06)
            # Use dates outside the published weekly window so overnight does not collide with L0.
            open_night_date = (end + timedelta(days=3)).isoformat()
            open_night = w5.create_open_shift(
                cur,
                company_code=company,
                payload={
                    "period_id": period_id,
                    "shift_date": open_night_date,
                    "start_time": "22:00",
                    "end_time": "06:00",
                    "notes": f"SHW5 overnight claim {tag}",
                    "role": "ops",
                },
                actor_phone=phone,
            )
            check("overnight open shift", open_night.get("ok"), open_night)
            open_night_id = str((open_night.get("open_shift") or {}).get("open_shift_id"))
            known_ids.setdefault("open_shift_ids", []).append(open_night_id)

            emp_a = {"employee_key": key, "phone": phone, "name": name}
            emp_b = {"employee_key": key_b, "phone": phone_b, "name": name_b}
            claim_a = w5.claim_open_shift(cur, company_code=company, open_shift_id=open_night_id, employee=emp_a, actor_phone=phone)
            check("claim by A", claim_a.get("ok"), claim_a)
            claim_a_id = str((claim_a.get("claim") or {}).get("claim_id"))

            self_denied = w5.decide_open_shift_claim(
                cur,
                company_code=company,
                claim_id=claim_a_id,
                decision="approved",
                actor_phone=phone,
                actor_employee_key=key,
                create_fn=app.create_shift_assignment,
                action_acks=acks,
            )
            check("self-approval denied", self_denied.get("error") == "self_approval_denied", self_denied)

            claim_b = w5.claim_open_shift(cur, company_code=company, open_shift_id=open_night_id, employee=emp_b, actor_phone=phone_b)
            check("claim by B", claim_b.get("ok"), claim_b)
            claim_b_id = str((claim_b.get("claim") or {}).get("claim_id"))
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            approve_a = w5.decide_open_shift_claim(
                cur,
                company_code=company,
                claim_id=claim_a_id,
                decision="approved",
                actor_phone=phone_b,
                actor_employee_key=key_b,
                create_fn=app.create_shift_assignment,
                action_acks=acks,
            )
            check("approve A wins", approve_a.get("ok"), approve_a)
            if approve_a.get("shift_id"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + [approve_a["shift_id"]]

            approve_b = w5.decide_open_shift_claim(
                cur,
                company_code=company,
                claim_id=claim_b_id,
                decision="approved",
                actor_phone=phone,
                actor_employee_key=key,
                create_fn=app.create_shift_assignment,
                action_acks=acks,
            )
            check(
                "second approve B rejected",
                approve_b.get("error") in {"claim_not_pending", "open_shift_already_resolved"},
                approve_b,
            )
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # 20. Direct assign another open shift
            open_direct = w5.create_open_shift(
                cur,
                company_code=company,
                payload={
                    "period_id": period_id,
                    "shift_date": (end + timedelta(days=5)).isoformat(),
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "notes": f"SHW5 direct {tag}",
                    "role": "ops",
                },
                actor_phone=phone,
            )
            check("open shift for direct assign", open_direct.get("ok"), open_direct)
            open_direct_id = str((open_direct.get("open_shift") or {}).get("open_shift_id"))
            known_ids.setdefault("open_shift_ids", []).append(open_direct_id)
        conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            direct = w5.assign_open_shift_direct(
                cur,
                company_code=company,
                open_shift_id=open_direct_id,
                employee_key=key_b,
                create_fn=app.create_shift_assignment,
                actor_phone=phone,
                action_acks=acks,
            )
            check("direct assign open shift", direct.get("ok"), direct)
            if direct.get("shift_id"):
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + [direct["shift_id"]]

            # 21. Gate conflict — overlapping open shift without ack
            cur.execute(
                """
                SELECT shift_date::text, start_time::text, end_time::text, ends_next_day
                FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s AND schedule_source='published'
                  AND status='scheduled'
                ORDER BY shift_date LIMIT 1
                """,
                (company, key),
            )
            overlap_src = cur.fetchone()
            if overlap_src:
                ov = dict(overlap_src)
                open_overlap = w5.create_open_shift(
                    cur,
                    company_code=company,
                    payload={
                        "period_id": period_id,
                        "shift_date": ov["shift_date"][:10],
                        "start_time": ov["start_time"][:5],
                        "end_time": ov["end_time"][:5],
                        "notes": f"SHW5 overlap gate {tag}",
                        "role": "ops",
                    },
                    actor_phone=phone,
                )
                open_overlap_id = str((open_overlap.get("open_shift") or {}).get("open_shift_id"))
                known_ids.setdefault("open_shift_ids", []).append(open_overlap_id)
                claim_ov = w5.claim_open_shift(
                    cur,
                    company_code=company,
                    open_shift_id=open_overlap_id,
                    employee=emp_a,
                    actor_phone=phone,
                )
                if claim_ov.get("ok"):
                    gate = w5.decide_open_shift_claim(
                        cur,
                        company_code=company,
                        claim_id=claim_ov["claim"]["claim_id"],
                        decision="approved",
                        actor_phone=phone_b,
                        actor_employee_key=key_b,
                        create_fn=app.create_shift_assignment,
                        action_acks={},
                    )
                    check(
                        "gate_conflict without ack",
                        gate.get("error") == "gate_conflict",
                        gate,
                    )
                else:
                    check("gate_conflict without ack", False, claim_ov)
            else:
                check("gate_conflict without ack", False, "no published assignment to overlap")

            # 22. Manual L0 when require_publish optional period exists
            opt_period = w5.create_period(
                cur,
                company_code=company,
                payload={
                    "name": f"SHW5 Optional {tag}",
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "require_publish": False,
                },
                actor_phone=phone,
            )
            check("optional require_publish period", opt_period.get("ok"), opt_period)
        conn.commit()

    manual = app.create_shift_assignment(
        {
            "employee_key": key,
            "employee_name": name,
            "employee_phone": phone,
            "date": (end + timedelta(days=7)).isoformat(),
            "shift_date": (end + timedelta(days=7)).isoformat(),
            "start_time": "10:00",
            "end_time": "14:00",
            "idempotency_key": f"SHW5-MANUAL|{tag}",
            "reason": f"wave5 manual optional period {tag}",
            **acks,
        },
        company_code=company,
        created_by_phone=phone,
    )
    check("manual L0 with optional period", manual.get("ok"), manual)
    if manual.get("created"):
        for c in manual["created"]:
            sid = str(c.get("shift_id") or "")
            if sid:
                known_ids["shift_ids"] = list(known_ids.get("shift_ids") or []) + [sid]

    # 23. Cleanup
    scope = cleanup.wave5_scope(company_code=company, tag=tag, extra_employee_keys=(key, key_b))
    cleaned = cleanup.cleanup_synthetic_scope(app.db_connect, scope, known_ids=known_ids)
    check("cleanup residual_total", int(cleaned.get("residual_total") or 0) == 0, cleaned)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
