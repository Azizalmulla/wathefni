#!/usr/bin/env python3
"""Shifts Wave 1 / 1A — authority, overnight, lifecycle semantics smoke (local/staging).

Pins:
  - overnight contract matches Attendance shift_window
  - split = multi-row non-overlapping same date
  - Wave 1A interval-aware lifecycle (future_start/notice/suspension/beyond-end)
  - unknown employee fail-closed
  - self-swap decision ban + E2E swap fixture
  - leave-conflict modes
  - idempotent create/cancel
  - concurrency reschedule (expected_updated_at) via dashboard API
  - overnight create + dashboard overnight reschedule
  - reversible orphan quarantine with audit integrity
  - no Leave balance / Payroll money mutation symbols

Run: WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1 python3 smoke-test-shifts-authority-wave1.py
"""
from __future__ import annotations

import inspect
import os
import sys
import uuid
from datetime import date, timedelta, timezone
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_digits = "".join(ch for ch in SUFFIX if ch.isdigit()) + "000000"
PHONE = f"965528{_digits[:6]}"
PHONE_B = f"965528{_digits[1:6]}9"


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
    print("    shifts authority wave1a — lifecycle + overnight + swap + dashboard")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_WAVE1", "1")
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY", "0")
    os.environ.setdefault("WATHEFNI_SHIFTS_ALLOW_OVERNIGHT", "1")

    import shifts_authority_wave1 as sw1
    import attendance_authority_wave1 as att

    check("version pinned 1.1.0", sw1.SHIFTS_WAVE1_VERSION == "1.1.0")
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
    w2 = sw1.shift_window(d, "13:00", "17:00")
    w3 = sw1.shift_window(d, "12:00", "14:00")
    w4 = sw1.shift_window(d, "22:00", "06:00")
    w5 = sw1.shift_window(d + timedelta(days=1), "05:00", "09:00")
    assert w1 and w2 and w3 and w4 and w5
    check("split abut no overlap", not sw1.intervals_overlap(w1[0], w1[1], w2[0], w2[1]))
    check("split mid overlap", sw1.intervals_overlap(w1[0], w1[1], w3[0], w3[1]))
    check("overnight vs next-morning overlap", sw1.intervals_overlap(w4[0], w4[1], w5[0], w5[1]))

    # --- Wave 1A corrected lifecycle matrix (interval-aware) -----------------
    base_settings = {
        "block_terminated": True,
        "block_suspended": True,
        "block_future_start": True,
        "block_notice_period": False,
        "garden_leave_during_notice": False,
        "beyond_end_mode": "require_ack",
    }
    start_d = date(2026, 9, 1)
    end_d = date(2026, 9, 30)

    def win(day: date, st: str, et: str):
        return sw1.shift_window(day, st, et)

    facts_future = {"lifecycle_state": "pending_start", "start_date": start_d, "hub_status": "pending_start"}
    before = win(date(2026, 8, 31), "09:00", "17:00")
    on_start = win(start_d, "09:00", "17:00")
    assert before and on_start
    check(
        "pending_start blocks before start date",
        (sw1.evaluate_shift_lifecycle(facts=facts_future, shift_start=before[0], shift_end=before[1], settings=base_settings) or {}).get("lifecycle")
        == "future_start",
    )
    check(
        "pending_start blocks on start date until activation",
        (sw1.evaluate_shift_lifecycle(facts=facts_future, shift_start=on_start[0], shift_end=on_start[1], settings=base_settings) or {}).get("lifecycle")
        == "future_start",
    )
    facts_activated = {"lifecycle_state": "active", "start_date": start_d, "hub_status": "active"}
    check(
        "active allows on start date",
        sw1.evaluate_shift_lifecycle(facts=facts_activated, shift_start=on_start[0], shift_end=on_start[1], settings=base_settings) is None,
    )

    facts_notice = {
        "lifecycle_state": "notice_period",
        "start_date": date(2026, 1, 1),
        "notice_starts_on": date(2026, 9, 1),
        "last_working_day": end_d,
        "end_date": end_d,
        "hub_status": "active",
    }
    mid_notice = win(date(2026, 9, 15), "09:00", "17:00")
    after_end = win(date(2026, 10, 1), "09:00", "17:00")
    assert mid_notice and after_end
    check(
        "notice allows through last working day",
        sw1.evaluate_shift_lifecycle(facts=facts_notice, shift_start=mid_notice[0], shift_end=mid_notice[1], settings=base_settings) is None,
    )
    check(
        "notice blocks past employment end",
        (sw1.evaluate_shift_lifecycle(facts=facts_notice, shift_start=after_end[0], shift_end=after_end[1], settings=base_settings) or {}).get("lifecycle")
        == "beyond_employment_end",
    )
    garden_settings = {**base_settings, "garden_leave_during_notice": True}
    check(
        "garden leave blocks notice assignments",
        (sw1.evaluate_shift_lifecycle(facts=facts_notice, shift_start=mid_notice[0], shift_end=mid_notice[1], settings=garden_settings) or {}).get("lifecycle")
        == "notice_period",
    )

    facts_sus = {
        "lifecycle_state": "suspended",
        "start_date": date(2026, 1, 1),
        "suspended_on": date(2026, 9, 10),
        "suspension_ends_on": date(2026, 9, 12),
        "hub_status": "suspended",
    }
    in_sus = win(date(2026, 9, 11), "09:00", "17:00")
    out_sus = win(date(2026, 9, 14), "09:00", "17:00")
    assert in_sus and out_sus
    check(
        "suspended blocks overlapping interval",
        (sw1.evaluate_shift_lifecycle(facts=facts_sus, shift_start=in_sus[0], shift_end=in_sus[1], settings=base_settings) or {}).get("lifecycle")
        == "suspended",
    )
    check(
        "suspended allows outside suspension window",
        sw1.evaluate_shift_lifecycle(facts=facts_sus, shift_start=out_sus[0], shift_end=out_sus[1], settings=base_settings) is None,
    )

    facts_term = {
        "lifecycle_state": "terminated",
        "start_date": date(2026, 1, 1),
        "end_date": end_d,
        "hub_status": "terminated",
    }
    last_day = win(end_d, "09:00", "17:00")
    overnight_past = win(end_d, "22:00", "06:00")
    assert last_day and overnight_past
    check(
        "terminated allows on last working day daytime",
        sw1.evaluate_shift_lifecycle(facts=facts_term, shift_start=last_day[0], shift_end=last_day[1], settings=base_settings) is None,
    )
    check(
        "terminated blocks overnight past employment end",
        (sw1.evaluate_shift_lifecycle(facts=facts_term, shift_start=overnight_past[0], shift_end=overnight_past[1], settings=base_settings) or {}).get("lifecycle")
        == "beyond_employment_end",
    )

    flag_denied = sw1.evaluate_shift_lifecycle(
        facts=facts_term,
        shift_start=after_end[0],
        shift_end=after_end[1],
        settings=base_settings,
        operation="flag_existing",
    )
    check(
        "existing beyond-end requires ack (not silent delete)",
        bool(flag_denied) and flag_denied.get("error") == "shift_beyond_employment_end_ack_required",
    )
    check(
        "notice label no longer blanket-blocks by default",
        sw1.lifecycle_gate_for_shifts(label="notice_period", settings=base_settings) is None,
    )

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

    # Neutralize outbound WhatsApp / HR notify so staging smoke never blocks on delivery.
    app.notify_employee_shift_cancelled = lambda **k: {"ok": True, "stub": True}
    app.notify_employee_shift_created = lambda **k: {"ok": True, "stub": True}
    app.notify_hr_admins = lambda **k: {"ok": True, "stub": True}
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "stub": True}

    create_src = inspect.getsource(app.create_shift_assignment_for_employee)
    check("create does not touch leave_balances", "leave_balances" not in create_src)
    check("create does not calculate payment", "bank_transfer" not in create_src.lower())
    check("create refuses empty employee", "unknown_employee" in create_src or "employee_not_found" in create_src)
    check("overnight allowed in extract", "shifts_authority" in inspect.getsource(app.extract_shift_time_range))
    check("self swap wired", "self_swap_decision_denied" in inspect.getsource(app.decide_shift_swap))
    check("dashboard reschedule expects concurrency", "expected_updated_at" in inspect.getsource(app.dashboard_posthire_reschedule_shift))
    check("create uses interval lifecycle", "evaluate_assignment_lifecycle" in create_src)

    dist_root = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or (orch.parent / "apps" / "wathefni-dashboard" / "dist"))
    token_hit = False
    if dist_root.is_dir():
        for asset in dist_root.glob("assets/*.js"):
            if "expected_updated_at" in asset.read_text(errors="ignore"):
                token_hit = True
                break
    check(
        "dashboard dist embeds expected_updated_at" if dist_root.is_dir() else "dashboard dist check skipped (no dist)",
        token_hit or not dist_root.is_dir(),
    )

    company = "WATHEFNI"
    emp_key = f"WATHEFNI-SHW1-{SUFFIX}"
    emp_key_b = f"WATHEFNI-SHW1B-{SUFFIX}"
    actor = "96588009911"
    today = date.today()
    shift_day = today + timedelta(days=14)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            sw1.ensure_shifts_authority_wave1_schema(cur)
            sw1.seed_shift_authority_settings(cur, company)
            for key, phone, name in (
                (emp_key, PHONE, f"SHW1 Synth {SUFFIX}"),
                (emp_key_b, PHONE_B, f"SHW1B Synth {SUFFIX}"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (company, key, name, phone),
                )
                cur.execute(
                    "UPDATE employees SET employment_status='active' WHERE company_code=%s AND employee_key=%s",
                    (company, key),
                )
            conn.commit()

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
    check("ends_next_day false for day shift", shift_row.get("ends_next_day") in {False, None})

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
    on_id = str(on_row.get("shift_id") or "")

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

    att_win = att.shift_window(shift_day + timedelta(days=2), on_row.get("start_time") or "22:00", on_row.get("end_time") or "06:00")
    sh_win = sw1.shift_window(shift_day + timedelta(days=2), on_row.get("start_time") or "22:00", on_row.get("end_time") or "06:00")
    check("Attendance overnight interval matches Shifts", att_win == sh_win)

    owner_ctx = {
        "company_code": company,
        "permissions": ["shifts.read", "shifts.manage"],
        "access": {"role": "owner", "permissions": ["shifts.read", "shifts.manage"]},
        "actor_user_id": f"shw1a-{SUFFIX}",
        "permission_authority": "backend_current",
        "permission_subject_user_id": f"shw1a-{SUFFIX}",
        "permission_subject_company": company,
        "actor_role": "owner",
        "hr_phone": actor,
        "hr_user": {"role": "owner", "status": "active", "company_code": company},
    }
    if on_id:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM shift_assignments WHERE shift_id=%s", (on_id,))
                cur_row = dict(cur.fetchone())
        expected_iso = cur_row.get("updated_at")
        expected_iso = expected_iso.isoformat() if hasattr(expected_iso, "isoformat") else str(expected_iso)
        client_body = {
            "shift_date": str(cur_row.get("shift_date")),
            "start_time": "21:00",
            "end_time": "05:00",
            "expected_updated_at": expected_iso,
        }
        check("client payload includes expected_updated_at", bool(client_body["expected_updated_at"]))
        try:
            resched = app.dashboard_posthire_reschedule_shift(
                on_id,
                app.ShiftRescheduleRequest(**client_body),
                context=owner_ctx,
            )
            check("dashboard overnight reschedule ok", resched.get("ok") is True and resched.get("status") == "rescheduled", resched)
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT ends_next_day, start_time FROM shift_assignments WHERE shift_id=%s", (on_id,))
                    moved = dict(cur.fetchone())
            check("dashboard overnight ends_next_day persisted", moved.get("ends_next_day") is True)
            check("dashboard overnight start moved", str(moved.get("start_time")).startswith("21:00"))
        except app.HTTPException as exc:
            check("dashboard overnight reschedule ok", False, getattr(exc, "detail", exc))

        try:
            app.dashboard_posthire_reschedule_shift(
                on_id,
                app.ShiftRescheduleRequest(
                    shift_date=str(cur_row.get("shift_date")),
                    start_time="20:00",
                    end_time="04:00",
                    expected_updated_at=expected_iso,
                ),
                context=owner_ctx,
            )
            check("dashboard stale concurrency denied", False)
        except app.HTTPException as exc:
            check("dashboard stale concurrency denied", exc.status_code == 409)

    leave_day = shift_day + timedelta(days=5)
    leave_id = None
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
                (company, emp_key, PHONE, f"SHW1 Synth {SUFFIX}", leave_day, leave_day, app.Json({"shw1": True})),
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

    # --- E2E swap fixture -------------------------------------------------
    swap_day = shift_day + timedelta(days=9)
    req_shift = app.create_shift_assignment(
        {
            "employee_key": emp_key,
            "date": swap_day.isoformat(),
            "start_time": "08:00",
            "end_time": "12:00",
            "idempotency_key": f"shw1-swap-req-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    tgt_shift = app.create_shift_assignment(
        {
            "employee_key": emp_key_b,
            "date": swap_day.isoformat(),
            "start_time": "13:00",
            "end_time": "17:00",
            "idempotency_key": f"shw1-swap-tgt-{SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=actor,
    )
    check("swap fixture requester shift", req_shift.get("ok") is True, req_shift.get("error"))
    check("swap fixture target shift", tgt_shift.get("ok") is True, tgt_shift.get("error"))
    req_sid = str(((req_shift.get("created") or [{}])[0]).get("shift_id") or "")
    tgt_sid = str(((tgt_shift.get("created") or [{}])[0]).get("shift_id") or "")
    swap_req = app.request_shift_swap(
        {
            "employee_key": emp_key,
            "target_phone": PHONE_B,
            "shift_id": req_sid,
            "target_shift_id": tgt_sid,
            "date": swap_day.isoformat(),
            "reason": f"shw1a swap {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE,
    )
    check("swap request ok", swap_req.get("ok") is True, swap_req.get("error"))
    swap_id = str((swap_req.get("swap") or {}).get("swap_id") or "")

    self_dec = app.approve_shift_swap(
        {"swap_id": swap_id, "company_code": company},
        company_code=company,
        created_by_phone=PHONE,
    )
    check(
        "swap self-decision denied",
        self_dec.get("ok") is False and self_dec.get("error") == "self_swap_decision_forbidden",
        self_dec.get("error"),
    )

    print("      … rejecting scoped swap (decision path without assignment mutation)", flush=True)
    scoped = app.reject_shift_swap(
        {"swap_id": swap_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
        account_id=None,
    )
    print(f"      … scoped reject ok={scoped.get('ok')} err={scoped.get('error')}", flush=True)
    check("swap scoped decision ok", scoped.get("ok") is True, scoped.get("error"))

    print("      … replay swap decision", flush=True)
    replay = app.reject_shift_swap(
        {"swap_id": swap_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
        account_id=None,
    )
    check("swap idempotent replay", replay.get("ok") is True and replay.get("idempotent") is True, replay)

    # Fresh swap for approve assignment path + stale race
    swap2 = app.request_shift_swap(
        {
            "employee_key": emp_key_b,
            "target_employee_key": emp_key,
            "target_phone": PHONE,
            "shift_id": tgt_sid,
            "target_shift_id": req_sid,
            "date": swap_day.isoformat(),
            "reason": f"shw1a swap2 {SUFFIX}",
            "company_code": company,
        },
        company_code=company,
        created_by_phone=PHONE_B,
    )
    swap2_id = str((swap2.get("swap") or {}).get("swap_id") or "")
    print("      … approving assignment swap", flush=True)
    first = app.approve_shift_swap(
        {"swap_id": swap2_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
        account_id=None,
    )
    print(f"      … approve ok={first.get('ok')} err={first.get('error')}", flush=True)
    check("swap first decision wins", first.get("ok") is True, first.get("error"))
    second = app.reject_shift_swap(
        {"swap_id": swap2_id, "company_code": company},
        company_code=company,
        created_by_phone=actor,
        account_id=None,
    )
    check(
        "swap stale second decision denied or idempotent-reject",
        second.get("ok") is False
        or second.get("idempotent") is True
        or second.get("error") in {"stale_swap_decision", "shift_swap_not_found"},
        second,
    )

    # Orphan quarantine + audit integrity
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
            q = sw1.quarantine_orphan_shift(
                cur, company_code=company, shift=orphan, actor_phone=actor, record_event=app.record_shift_event
            )
            check("orphan quarantine ok", q.get("ok") is True, q)
            qid = (q.get("quarantine") or {}).get("quarantine_id")
            cur.execute(
                "SELECT count(*) AS c FROM shift_events WHERE shift_id=%s AND event_type='orphan_quarantined'",
                (orphan.get("shift_id"),),
            )
            check("orphan quarantine audit event", int(dict(cur.fetchone()).get("c") or 0) >= 1)
            cur.execute(
                "SELECT status FROM shift_lifecycle_flags WHERE shift_id=%s AND flag_type='orphan_employee_key' ORDER BY created_at DESC LIMIT 1",
                (orphan.get("shift_id"),),
            )
            flag_row = cur.fetchone()
            check("orphan lifecycle flag open", flag_row and dict(flag_row).get("status") == "open")

            fail_restore = sw1.restore_quarantined_shift(
                cur, company_code=company, quarantine_id=str(qid), actor_phone=actor, require_employee_exists=True
            )
            check("restore blocked while still orphan", fail_restore.get("ok") is False)
            ok_restore = sw1.restore_quarantined_shift(
                cur,
                company_code=company,
                quarantine_id=str(qid),
                actor_phone=actor,
                require_employee_exists=False,
                record_event=app.record_shift_event,
            )
            check("orphan quarantine reversible", ok_restore.get("ok") is True, ok_restore)
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (orphan.get("shift_id"),))
            check("restored shift scheduled again", dict(cur.fetchone()).get("status") == "scheduled")
            cur.execute(
                "SELECT count(*) AS c FROM shift_events WHERE shift_id=%s AND event_type='orphan_restored'",
                (orphan.get("shift_id"),),
            )
            check("orphan restore audit event", int(dict(cur.fetchone()).get("c") or 0) >= 1)
            cur.execute("SELECT * FROM shift_assignments WHERE shift_id=%s", (orphan.get("shift_id"),))
            sw1.quarantine_orphan_shift(
                cur, company_code=company, shift=dict(cur.fetchone()), actor_phone=actor, record_event=app.record_shift_event
            )
            conn.commit()

    # Beyond-end existing: flag + cancel, never silent delete
    beyond_day = shift_day + timedelta(days=20)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  company_code, employee_key, employee_phone, employee_name,
                  shift_date, start_time, end_time, timezone, status, source_text, metadata
                ) VALUES (%s,%s,%s,%s,%s,'09:00','17:00','Asia/Kuwait','scheduled','shw1-beyond', '{}'::jsonb)
                RETURNING *
                """,
                (company, emp_key, PHONE, f"SHW1 Synth {SUFFIX}", beyond_day),
            )
            beyond_shift = dict(cur.fetchone())
            facts = {
                "lifecycle_state": "terminated",
                "start_date": date(2020, 1, 1),
                "end_date": beyond_day - timedelta(days=1),
                "hub_status": "terminated",
            }
            flagged = sw1.flag_beyond_employment_end_shift(
                cur, company_code=company, shift=beyond_shift, facts=facts, actor_phone=actor
            )
            check("beyond-end flagged audited", flagged.get("ok") is True)
            cur.execute("SELECT count(*) AS c FROM shift_assignments WHERE shift_id=%s", (beyond_shift.get("shift_id"),))
            before_count = int(dict(cur.fetchone()).get("c") or 0)
            cancelled = sw1.acknowledge_or_cancel_beyond_end(
                cur,
                company_code=company,
                shift_id=str(beyond_shift.get("shift_id")),
                actor_phone=actor,
                mode="cancel",
                record_event=app.record_shift_event,
            )
            cur.execute("SELECT count(*) AS c FROM shift_assignments WHERE shift_id=%s", (beyond_shift.get("shift_id"),))
            after_count = int(dict(cur.fetchone()).get("c") or 0)
            cur.execute("SELECT status FROM shift_assignments WHERE shift_id=%s", (beyond_shift.get("shift_id"),))
            beyond_status = dict(cur.fetchone()).get("status")
            check("beyond-end never silent-deleted", before_count == after_count == 1)
            check("beyond-end soft-cancelled", cancelled.get("ok") is True and beyond_status == "cancelled")
            conn.commit()

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

    cross = app.create_shift_assignment_for_employee(
        {"date": shift_day.isoformat(), "start_time": "09:00", "end_time": "12:00"},
        employee={"employee_key": emp_key, "company_code": "OTHER", "phone": PHONE, "name": "x"},
        company_code=company,
        created_by_phone=actor,
    )
    check("tenant isolation company mismatch", cross.get("error") == "employee_company_mismatch")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if leave_id:
                cur.execute("DELETE FROM leave_requests WHERE leave_id=%s AND company_code=%s", (leave_id, company))
            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
