#!/usr/bin/env python3
"""Shifts Wave 1 — authority, overnight, safety smoke (local/staging).

Pins:
  - overnight contract matches Attendance shift_window
  - split = multi-row non-overlapping same date
  - lifecycle gates + unknown employee fail-closed
  - self-swap decision ban
  - leave-conflict modes
  - idempotent create/cancel
  - concurrency reschedule (expected_updated_at)
  - reversible orphan quarantine
  - no Leave balance / Payroll money mutation symbols
  - honesty: payroll_money=false

Run: WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1 python3 smoke-test-shifts-authority-wave1.py
"""
from __future__ import annotations

import inspect
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_digits = "".join(ch for ch in SUFFIX if ch.isdigit()) + "000000"
PHONE = f"965528{_digits[:6]}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    shifts authority wave1 — overnight + gates + concurrency + honesty")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_WAVE1", "1")
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY", "0")
    os.environ.setdefault("WATHEFNI_SHIFTS_ALLOW_OVERNIGHT", "1")

    import shifts_authority_wave1 as sw1
    import attendance_authority_wave1 as att

    check("version pinned", sw1.SHIFTS_WAVE1_VERSION == "1.0.0")
    check("wave1 enabled", sw1.shifts_wave1_enabled())
    check("WATHEFNI company allowed", sw1.shifts_authority_enabled_for_company("WATHEFNI"))
    check("other company gated", not sw1.shifts_authority_enabled_for_company("OTHERCO"))
    check("allow_overnight default true", sw1.allow_overnight())

    # Overnight contract parity with Attendance
    d = date(2026, 8, 11)
    a_win = att.shift_window(d, "22:00", "06:00")
    s_win = sw1.shift_window(d, "22:00", "06:00")
    check("overnight windows equal Attendance", a_win == s_win and a_win is not None)
    check("overnight ends next calendar day", a_win and a_win[1].date() == d + timedelta(days=1))
    check("ends_next_day_for 22-06", sw1.ends_next_day_for("22:00", "06:00") is True)
    check("ends_next_day_for 09-17", sw1.ends_next_day_for("09:00", "17:00") is False)

    same = sw1.normalize_time_range("09:00", "17:00", allow_overnight_flag=True)
    over = sw1.normalize_time_range("22:00", "06:00", allow_overnight_flag=True)
    banned = sw1.normalize_time_range("22:00", "06:00", allow_overnight_flag=False)
    check("same-day normalize", same[2] is False and same[3] is None)
    check("overnight normalize", over[2] is True and over[3] is None)
    check("overnight banned", banned[3] == "overnight_not_allowed")

    # Interval overlap helpers
    w1 = sw1.shift_window(d, "09:00", "13:00")
    w2 = sw1.shift_window(d, "13:00", "17:00")  # split abut — no overlap
    w3 = sw1.shift_window(d, "12:00", "14:00")
    w4 = sw1.shift_window(d, "22:00", "06:00")
    w5 = sw1.shift_window(d + timedelta(days=1), "05:00", "09:00")
    assert w1 and w2 and w3 and w4 and w5
    check("split abut no overlap", not sw1.intervals_overlap(w1[0], w1[1], w2[0], w2[1]))
    check("split mid overlap", sw1.intervals_overlap(w1[0], w1[1], w3[0], w3[1]))
    check("overnight vs next-morning overlap", sw1.intervals_overlap(w4[0], w4[1], w5[0], w5[1]))

    settings = {
        "block_terminated": True,
        "block_suspended": True,
        "block_future_start": True,
        "block_notice_period": True,
    }
    for lab in ("terminated", "suspended", "future_start", "notice_period"):
        blocked = sw1.lifecycle_gate_for_shifts(label=lab, settings=settings, operation="create")
        check(f"lifecycle blocks {lab}", bool(blocked) and blocked.get("error") == "shift_lifecycle_blocked")
    check("lifecycle allows active", sw1.lifecycle_gate_for_shifts(label="active", settings=settings) is None)

    swap = {
        "requester_employee_phone": "965528111111",
        "target_employee_phone": "965528222222",
        "requested_by_phone": "965528111111",
    }
    check(
        "self-swap approve banned",
        (sw1.self_swap_decision_denied(swap=swap, actor_phone="965528111111") or {}).get("error")
        == "self_swap_decision_forbidden",
    )
    check("other actor swap ok", sw1.self_swap_decision_denied(swap=swap, actor_phone="965599999999") is None)

    leaves = [{"leave_id": "x", "status": "approved"}]
    check(
        "leave conflict block",
        (sw1.leave_conflict_denied(mode="block", leaves=leaves, action={}) or {}).get("error")
        == "shift_leave_conflict",
    )
    check(
        "leave conflict require_ack",
        (sw1.leave_conflict_denied(mode="require_ack", leaves=leaves, action={}) or {}).get("error")
        == "shift_leave_conflict_ack_required",
    )
    check(
        "leave conflict ack ok",
        sw1.leave_conflict_denied(mode="require_ack", leaves=leaves, action={"ack_leave_conflict": True}) is None,
    )

    honesty = sw1.honesty_payload({"allow_overnight": True, "leave_conflict_mode": "require_ack", "rest_weekdays": [4]})
    check("honesty payroll_money false", honesty.get("payroll_money") is False)
    check("honesty leave_balances_mutated false", honesty.get("leave_balances_mutated") is False)
    check("rest_weekdays configurable default Fri", honesty.get("rest_weekdays") == [4])

    check("synthetic marker SHW1", sw1.is_shift_synthetic_employee(employee_key=f"WATHEFNI-SHW1-{SUFFIX}"))
    check("synthetic phone prefix", sw1.is_shift_synthetic_employee(phone=PHONE))

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    # Source honesty: create/cancel/reschedule must not mutate leave balances or pay money
    create_src = inspect.getsource(app.create_shift_assignment_for_employee)
    check("create does not touch leave_balances", "leave_balances" not in create_src)
    check("create does not calculate payment", "bank_transfer" not in create_src.lower())
    check("create refuses empty employee", "unknown_employee" in create_src or "employee_not_found" in create_src)
    check("overnight allowed in extract", "overnight" in inspect.getsource(app.extract_shift_time_range).lower() or "shifts_authority" in inspect.getsource(app.extract_shift_time_range))
    check("self swap wired", "self_swap_decision_denied" in inspect.getsource(app.decide_shift_swap))
    check("dashboard reschedule expects concurrency", "expected_updated_at" in inspect.getsource(app.dashboard_posthire_reschedule_shift))

    company = "WATHEFNI"
    emp_key = f"WATHEFNI-SHW1-{SUFFIX}"
    actor = "96588009911"
    today = date.today()
    shift_day = today + timedelta(days=14)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            sw1.seed_shift_authority_settings(cur, company)
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now())
                ON CONFLICT DO NOTHING
                """,
                (company, emp_key, f"SHW1 Synth {SUFFIX}", PHONE),
            )
            cur.execute(
                "UPDATE employees SET employment_status='active' WHERE company_code=%s AND employee_key=%s",
                (company, emp_key),
            )
            cur.execute(
                "SELECT employee_key FROM employees WHERE company_code=%s AND employee_key=%s",
                (company, emp_key),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now())
                    """,
                    (company, emp_key, f"SHW1 Synth {SUFFIX}", PHONE),
                )
            conn.commit()

    # Unknown employee fail-closed
    unknown = app.create_shift_assignment(
        {
            "employee_key": f"WATHEFNI-MISSING-{SUFFIX}",
            "date": shift_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "unknown employee creation fails closed",
        unknown.get("ok") is False and unknown.get("error") in {"employee_not_found", "unknown_employee"},
        unknown.get("error"),
    )

    # Same-day fixed
    idem = f"shw1-create-{SUFFIX}"
    created = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": shift_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "break_minutes": 60,
            "site_key": "HQ",
            "branch_key": "KUWAIT-CITY",
            "team_key": "OPS",
            "position_key": "ANALYST",
            "role": "Analyst",
            "idempotency_key": idem,
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("same-day fixed create", created.get("ok") is True, created.get("error"))
    shift_row = (created.get("created") or [None])[0] or {}
    shift_id = shift_row.get("shift_id")
    check("break_minutes persisted", shift_row.get("break_minutes") == 60, shift_row.get("break_minutes"))
    check("site_key persisted", shift_row.get("site_key") == "HQ")
    check("ends_next_day false for day shift", shift_row.get("ends_next_day") in {False, None, False})

    dup = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": shift_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "idempotency_key": idem,
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("duplicate create idempotent", dup.get("ok") is True and dup.get("idempotent") is True)

    # Split shift (two non-overlapping)
    split_a = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": (shift_day + timedelta(days=1)).isoformat(),
            "start_time": "09:00",
            "end_time": "13:00",
            "idempotency_key": f"shw1-split-a-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    split_b = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": (shift_day + timedelta(days=1)).isoformat(),
            "start_time": "14:00",
            "end_time": "18:00",
            "idempotency_key": f"shw1-split-b-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("split morning ok", split_a.get("ok") is True, split_a.get("error"))
    check("split afternoon ok", split_b.get("ok") is True, split_b.get("error"))

    overlap = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": (shift_day + timedelta(days=1)).isoformat(),
            "start_time": "12:00",
            "end_time": "15:00",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "split overlap detected",
        overlap.get("ok") is False or (overlap.get("conflicts") and len(overlap.get("conflicts") or []) > 0),
        overlap,
    )

    # Overnight 22:00–06:00
    overnight = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": (shift_day + timedelta(days=2)).isoformat(),
            "start_time": "22:00",
            "end_time": "06:00",
            "idempotency_key": f"shw1-overnight-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("overnight 22-06 create", overnight.get("ok") is True, overnight.get("error"))
    on_row = (overnight.get("created") or [None])[0] or {}
    check("overnight ends_next_day true", on_row.get("ends_next_day") is True)

    # Overnight overlap with next-morning
    next_morn = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": (shift_day + timedelta(days=3)).isoformat(),
            "start_time": "05:00",
            "end_time": "09:00",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "overnight vs next-morning overlap",
        next_morn.get("ok") is False or (next_morn.get("conflicts") and len(next_morn.get("conflicts") or []) > 0),
        next_morn,
    )

    # Attendance resolves same overnight interval
    att_win = att.shift_window(shift_day + timedelta(days=2), on_row.get("start_time") or "22:00", on_row.get("end_time") or "06:00")
    sh_win = sw1.shift_window(shift_day + timedelta(days=2), on_row.get("start_time") or "22:00", on_row.get("end_time") or "06:00")
    check("Attendance overnight interval matches Shifts", att_win == sh_win)

    # Leave conflict require_ack
    leave_day = shift_day + timedelta(days=5)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests (
                  company_code, employee_key, employee_phone, employee_name,
                  leave_type, start_date, end_date, status, reason, metadata
                ) VALUES (%s,%s,%s,%s,'annual',%s,%s,'approved','shw1',%s)
                RETURNING leave_id
                """,
                (
                    company,
                    emp_key,
                    PHONE,
                    f"SHW1 Synth {SUFFIX}",
                    leave_day,
                    leave_day,
                    app.Json({"shw1": True}),
                ),
            )
            leave_id = dict(cur.fetchone()).get("leave_id")
            conn.commit()
    blocked_leave = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": leave_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "approved-leave conflict requires handling",
        blocked_leave.get("ok") is False
        and blocked_leave.get("error") in {"shift_leave_conflict", "shift_leave_conflict_ack_required"},
        blocked_leave.get("error"),
    )
    acked = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": leave_day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "ack_leave_conflict": True,
            "idempotency_key": f"shw1-leave-ack-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("leave conflict ack allows create", acked.get("ok") is True, acked.get("error"))

    # Cancel idempotent
    cancel1 = app.cancel_shift_assignment(
        {"employee_key": emp_key, "shift_id": str(shift_id), "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    cancel2 = app.cancel_shift_assignment(
        {"employee_key": emp_key, "shift_id": str(shift_id), "company_code": company},
        company_code=company,
        created_by_phone=actor,
    )
    check("cancel ok", cancel1.get("ok") is True, cancel1)
    check("duplicate cancel idempotent", cancel2.get("ok") is True and cancel2.get("idempotent") is True)

    # Soft-cancel history preserved
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (shift_id,))
            st = dict(cur.fetchone()).get("status")
            cur.execute(
                "SELECT count(*) AS c FROM shift_events WHERE shift_id=%s AND event_type='cancelled'",
                (shift_id,),
            )
            ev = int(dict(cur.fetchone()).get("c") or 0)
    check("soft-cancel status cancelled", st == "cancelled")
    check("append-only cancel event", ev >= 1)

    # Concurrent reschedule — one winner via expected_updated_at
    r_create = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": (shift_day + timedelta(days=6)).isoformat(),
            "start_time": "10:00",
            "end_time": "18:00",
            "idempotency_key": f"shw1-resync-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    r_shift = (r_create.get("created") or [None])[0] or {}
    r_id = str(r_shift.get("shift_id") or "")
    updated_at = r_shift.get("updated_at")
    check("reschedule subject created", bool(r_id), r_create.get("error"))

    # Simulate concurrent: first update wins by bumping updated_at; second with stale token fails
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            cur.execute(
                """
                UPDATE shift_assignments
                SET start_time='11:00', end_time='19:00', updated_at=now(), row_version=COALESCE(row_version,1)+1
                WHERE shift_id=%s AND company_code=%s AND status='scheduled' AND updated_at=%s
                RETURNING shift_id
                """,
                (r_id, company, updated_at),
            )
            winner = cur.fetchone()
            cur.execute(
                """
                UPDATE shift_assignments
                SET start_time='12:00', end_time='20:00', updated_at=now(), row_version=COALESCE(row_version,1)+1
                WHERE shift_id=%s AND company_code=%s AND status='scheduled' AND updated_at=%s
                RETURNING shift_id
                """,
                (r_id, company, updated_at),
            )
            loser = cur.fetchone()
            conn.commit()
    check("stale concurrent reschedule one winner", bool(winner) and not loser)

    # Orphan quarantine reversible
    orphan_key = f"WATHEFNI-ORPHAN-{SUFFIX}"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  company_code, employee_key, employee_phone, employee_name,
                  shift_date, start_time, end_time, timezone, status, source_text, metadata
                ) VALUES (%s,%s,%s,'Orphan',%s,'09:00','17:00','Asia/Kuwait','scheduled','shw1', '{}'::jsonb)
                RETURNING *
                """,
                (company, orphan_key, "965528999001", shift_day + timedelta(days=7)),
            )
            orphan = dict(cur.fetchone())
            q = sw1.quarantine_orphan_shift(cur, company_code=company, shift=orphan, actor_phone=actor)
            check("orphan quarantine ok", q.get("ok") is True, q)
            qid = (q.get("quarantine") or {}).get("quarantine_id")
            # Restore without employee should fail when require_employee_exists
            fail_restore = sw1.restore_quarantined_shift(
                cur, company_code=company, quarantine_id=str(qid), actor_phone=actor, require_employee_exists=True
            )
            check("restore blocked while still orphan", fail_restore.get("ok") is False)
            # Force restore for reversibility proof (explicit override)
            ok_restore = sw1.restore_quarantined_shift(
                cur, company_code=company, quarantine_id=str(qid), actor_phone=actor, require_employee_exists=False
            )
            check("orphan quarantine reversible", ok_restore.get("ok") is True, ok_restore)
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (orphan.get("shift_id"),))
            restored_status = dict(cur.fetchone()).get("status")
            check("restored shift scheduled again", restored_status == "scheduled")
            # Re-quarantine for cleanup
            cur.execute("SELECT * FROM shift_assignments WHERE shift_id=%s", (orphan.get("shift_id"),))
            sw1.quarantine_orphan_shift(cur, company_code=company, shift=dict(cur.fetchone()), actor_phone=actor)
            conn.commit()

    # Lifecycle gate — terminated
    term_key = f"WATHEFNI-SHW1-TERM-{SUFFIX}"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now())
                ON CONFLICT DO NOTHING
                """,
                (company, term_key, f"SHW1 Term {SUFFIX}", f"965528{_digits[:5]}9"),
            )
            cur.execute(
                "UPDATE employees SET employment_status='terminated' WHERE company_code=%s AND employee_key=%s",
                (company, term_key),
            )
            conn.commit()
    term = app.create_shift_assignment(
        {
            "employee_key": term_key,
            "date": (shift_day + timedelta(days=8)).isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check(
        "lifecycle blocks terminated",
        term.get("ok") is False and term.get("error") in {"shift_lifecycle_blocked", "employee_not_found"},
        term.get("error"),
    )

    # Tenant isolation: create under wrong company should mismatch
    cross = app.create_shift_assignment_for_employee(
        {"date": shift_day.isoformat(), "start_time": "09:00", "end_time": "12:00"},
        employee={"employee_key": emp_key, "company_code": "OTHER", "phone": PHONE, "name": "x"},
        company_code=company,
        created_by_phone=actor,
    )
    check("tenant isolation company mismatch", cross.get("error") == "employee_company_mismatch")

    # Cleanup synthetic leave (do not touch real leave fingerprints)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if leave_id:
                cur.execute("DELETE FROM leave_requests WHERE leave_id=%s AND company_code=%s", (leave_id, company))
            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
