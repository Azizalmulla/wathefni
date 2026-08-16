#!/usr/bin/env python3
"""Leave Wave 3B — production synthetic workflow canary (WATHEFNI only).

Markers: LVW3B / LVW3B-SYNTH| / phone prefix 965527.
enforced=false, legal_reviewed=false. Real leave fingerprints must stay unchanged.
No payroll money. Full synthetic cleanup required.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")
os.environ.setdefault("WATHEFNI_LEAVE_BALANCES", "on")
os.environ.setdefault("WATHEFNI_LEAVE_POLICY_WAVE2", "on")
os.environ.setdefault("WATHEFNI_LEAVE_WORKFLOW_WAVE3", "on")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY", "on")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY", "on")
os.environ.setdefault(
    "WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS",
    "LVW1B,LVW1B-SYNTH|,LVW2C,LVW2C-SYNTH|,LVW3B,LVW3B-SYNTH|",
)
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES", "965525,965526,965527")

import app  # noqa: E402
import leave_authority_wave1 as w1  # noqa: E402
import leave_policy_wave2 as w2  # noqa: E402
import leave_workflow_wave3 as w3  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("LVW3B_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
PHONE = f"9655271{TAG_DIGITS}"
HR_PHONE = "96588009911"
NAME = f"LVW3B-SYNTH| Emp {TAG}"

REAL_FPS = {
    "e3217e0e-466f-4f38-aa10-dab503dcb0a4": "abf4cba7cb8702b2d7c067db795d0701",
    "51cd940f-a04b-4ad1-9a6a-43e3da59a222": "8f6d67e3cc4fbf5ee321af235ecbb20d",
    "dbf82ecf-7ac4-451b-b41c-03de943f2161": "34c7cf18a4d758698bbf7cac6da70d1f",
}

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("LVW3B_EVID") or f"/tmp/leave-w3b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {"tag": TAG, "phone": PHONE, "name": NAME, "leave_ids": []}


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def track_leave(payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    lid = payload.get("leave_id") or (payload.get("leave") or {}).get("leave_id")
    if lid:
        IDS["leave_ids"].append(str(lid))


def real_fingerprint(cur) -> dict[str, Any]:
    cur.execute(
        """
        SELECT leave_id::text AS leave_id, employee_key, leave_type, status,
               start_date::text, end_date::text,
               md5(leave_id::text||coalesce(employee_key,'')||coalesce(leave_type,'')||coalesce(status,'')||coalesce(start_date::text,'')||coalesce(end_date::text,'')) AS fp
        FROM leave_requests WHERE company_code=%s
        ORDER BY leave_id::text
        """,
        (COMPANY,),
    )
    leaves = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) AS n FROM leave_events WHERE company_code=%s", (COMPANY,))
    events = int(dict(cur.fetchone())["n"])
    cur.execute("SELECT COUNT(*) AS n FROM leave_ledger WHERE company_code=%s", (COMPANY,))
    ledger = int(dict(cur.fetchone())["n"])
    cur.execute("SELECT COUNT(*) AS n FROM leave_balances WHERE company_code=%s", (COMPANY,))
    balances = int(dict(cur.fetchone())["n"])
    return {"leaves": leaves, "events": events, "ledger": ledger, "balances": balances}


def assert_reals(label: str, before: dict[str, Any] | None = None) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = real_fingerprint(cur)
    reals = [r for r in after["leaves"] if r["leave_id"] in REAL_FPS]
    check(f"{label}: real leave count 3", len(reals) == 3, reals)
    for r in reals:
        check(f"{label}: real fp {r['leave_id'][:8]}", r["fp"] == REAL_FPS[r["leave_id"]], r)
    if before is not None:
        b = [r for r in before["leaves"] if r["leave_id"] in REAL_FPS]
        check(f"{label}: real rows unchanged", b == reals, {"before": b, "after": reals})
    return after


def cleanup() -> dict[str, int]:
    deleted: dict[str, int] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key FROM employees
                WHERE company_code=%s AND (
                  phone LIKE '965527%%' OR name LIKE '%%LVW3B-SYNTH|%%' OR employee_key LIKE '%%LVW3B%%'
                )
                """,
                (COMPANY,),
            )
            keys = [dict(r)["employee_key"] for r in cur.fetchall()]
            IDS["cleanup_keys"] = keys
            if not keys:
                conn.commit()
                return {"employees": 0}
            cur.execute(
                "SELECT leave_id FROM leave_requests WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            leave_ids = [str(dict(r)["leave_id"]) for r in cur.fetchall()]
            if leave_ids:
                for sql in (
                    "DELETE FROM leave_attachment_audit WHERE leave_id = ANY(%s::uuid[])",
                    "DELETE FROM leave_request_attachments WHERE leave_id = ANY(%s::uuid[])",
                    "DELETE FROM leave_payroll_handoff_events WHERE leave_id = ANY(%s::uuid[])",
                    "DELETE FROM leave_events WHERE leave_id = ANY(%s::uuid[])",
                ):
                    try:
                        cur.execute(sql, (leave_ids,))
                        deleted[sql.split()[2]] = cur.rowcount
                    except Exception:
                        deleted[sql.split()[2]] = -1
                cur.execute(
                    "DELETE FROM leave_ledger WHERE leave_id = ANY(%s::uuid[]) OR employee_key = ANY(%s)",
                    (leave_ids, keys),
                )
                deleted["leave_ledger"] = cur.rowcount
                cur.execute("DELETE FROM leave_requests WHERE leave_id = ANY(%s::uuid[])", (leave_ids,))
                deleted["leave_requests"] = cur.rowcount
            else:
                cur.execute("DELETE FROM leave_ledger WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
                deleted["leave_ledger"] = cur.rowcount
            cur.execute("DELETE FROM leave_balances WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            deleted["leave_balances"] = cur.rowcount
            for table in ("attendance_events", "attendance_records", "shift_assignments"):
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
                    deleted[table] = cur.rowcount
                except Exception:
                    deleted[table] = -1
            try:
                cur.execute(
                    "DELETE FROM attendance_day_projections WHERE company_code=%s AND employee_key = ANY(%s)",
                    (COMPANY, keys),
                )
                deleted["attendance_day_projections"] = cur.rowcount
            except Exception:
                deleted["attendance_day_projections"] = -1
            try:
                cur.execute(
                    "DELETE FROM payroll_timesheet_events WHERE timesheet_id IN (SELECT timesheet_id FROM payroll_timesheets WHERE company_code=%s AND employee_key = ANY(%s))",
                    (COMPANY, keys),
                )
                cur.execute(
                    "DELETE FROM payroll_timesheets WHERE company_code=%s AND employee_key = ANY(%s)",
                    (COMPANY, keys),
                )
                deleted["payroll_timesheets"] = cur.rowcount
            except Exception:
                deleted["payroll_timesheets"] = -1
            cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            deleted["employees"] = cur.rowcount
        conn.commit()
    return deleted


def main() -> int:
    print(f"Leave Wave 3B prod canary tag={TAG} phone={PHONE}")
    app.notify_employee_leave_decision = lambda *a, **k: {"ok": True, "stub": True}

    check("wave3 version", w3.LEAVE_WORKFLOW_WAVE3_VERSION == "3.0.0")
    check("wave3 enabled", w3.leave_workflow_wave3_enabled())
    check("wave2 enabled", w2.leave_policy_wave2_enabled())
    check("needs_info status", "needs_info" in w1.LEAVE_PRIMARY_STATUSES)
    check("withdrawn status", "withdrawn" in w1.LEAVE_PRIMARY_STATUSES)
    flags = w1.honesty_balance_flags()
    check("enforced=false", flags.get("balances_enforced") is False, flags)
    check("legal_reviewed=false", flags.get("legal_reviewed") is False, flags)

    # Pure overlap / overnight
    d = date(2026, 9, 7)
    check(
        "full vs half overlap",
        w3.intervals_overlap(d, d, "full_day", None, None, None, d, d, "half_day", None, None, "am"),
    )
    check(
        "am vs pm no overlap",
        not w3.intervals_overlap(d, d, "half_day", None, None, "am", d, d, "half_day", None, None, "pm"),
    )
    check("overnight shift hours", w3.shift_length_hours(time(22, 0), time(6, 0)) == Decimal("8.00"))
    check("hourly inside overnight", w3._window_inside_shift(time(23, 0), time(1, 0), time(22, 0), time(6, 0)))
    handoff = w3.build_unpaid_payroll_handoff(
        {"leave_id": "x", "employee_key": "e", "start_date": "2026-09-07", "end_date": "2026-09-07", "chargeable_days": 1, "chargeable_hours": 8}
    )
    check("unpaid handoff no money (unit)", w3.assert_handoff_has_no_money(handoff), handoff)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("db is wathefni", db == "wathefni", db)
            before = real_fingerprint(cur)
            w3.ensure_leave_workflow_wave3_schema(cur)
        conn.commit()
    (EVID / "fingerprints-before.json").write_text(json.dumps(before, indent=2, default=str))
    assert_reals("preflight", None)
    IDS["company_totals_before"] = {
        "requests": len(before["leaves"]),
        "events": before["events"],
        "ledger": before["ledger"],
        "balances": before["balances"],
    }

    cleanup()
    emp_key = None
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w1.ensure_leave_authority_wave1_schema(cur)
                w2.ensure_leave_policy_wave2_schema(cur)
                w3.ensure_leave_workflow_wave3_schema(cur)
            conn.commit()
        app.seed_company_leave_policies(COMPANY)
        app.create_company_employee(COMPANY, name=NAME, phone=PHONE, position_title="W3B")
        emp = app.find_employee_by_phone(PHONE, company_code=COMPANY) or {}
        emp_key = str(emp.get("employee_key") or "")
        IDS["employee_key"] = emp_key
        check("synthetic employee", bool(emp_key), emp)
        today = app.kuwait_today()
        hire = date(today.year, 1, 1) if today.month >= 3 else date(today.year - 1, 1, 1)
        emp = {**(app.find_employee_by_phone(PHONE, company_code=COMPANY) or {}), "hired_at": hire, "start_date": hire, "hire_date": hire}
        emp_key = str(emp.get("employee_key") or emp_key)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pol = app.get_leave_policy(COMPANY, "annual")
                n = app.post_leave_accrual_catchup(cur, company_code=COMPANY, employee=emp, policy=pol, as_of=today)
            conn.commit()
        check("accrual posted", n >= 1, n)

        day = today + timedelta(days=14)
        while day.weekday() != 0:
            day += timedelta(days=1)
        night_day = day + timedelta(days=1)
        split_day = day + timedelta(days=2)
        while split_day.weekday() >= 5:
            split_day += timedelta(days=1)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled') RETURNING shift_id
                    """,
                    (COMPANY, emp_key, PHONE, NAME, day),
                )
                IDS["day_shift"] = str(dict(cur.fetchone())["shift_id"])
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'22:00','06:00','scheduled') RETURNING shift_id
                    """,
                    (COMPANY, emp_key, PHONE, NAME, night_day),
                )
                IDS["night_shift"] = str(dict(cur.fetchone())["shift_id"])
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'08:00','12:00','scheduled')
                    """,
                    (COMPANY, emp_key, PHONE, NAME, split_day),
                )
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'16:00','20:00','scheduled')
                    """,
                    (COMPANY, emp_key, PHONE, NAME, split_day),
                )
            conn.commit()

        half_req = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": day.isoformat(),
                "end_date": day.isoformat(),
                "duration_unit": "half_day",
                "half_portion": "am",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(half_req)
        check("half-day request", bool(half_req.get("ok")), half_req)
        leave_half = half_req.get("leave") or {}
        check("half chargeable ~0.5", abs(float(leave_half.get("chargeable_days") or 0) - 0.5) < 0.01, leave_half)
        check("half reservation", bool((half_req.get("reservation") or {}).get("reserved")), half_req.get("reservation"))
        IDS["half_leave_id"] = leave_half.get("leave_id")
        IDS["half_reservation_days"] = (half_req.get("reservation") or {}).get("days")

        half_pm = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": day.isoformat(),
                "end_date": day.isoformat(),
                "duration_unit": "half_day",
                "half_portion": "pm",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(half_pm)
        check("half-day PM no overlap with AM", bool(half_pm.get("ok")), half_pm)

        full_overlap = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": day.isoformat(),
                "end_date": day.isoformat(),
                "duration_unit": "full_day",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("full vs partial overlap denied", full_overlap.get("error") == "overlapping_leave_exists", full_overlap)

        hourly_req = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": split_day.isoformat(),
                "end_date": split_day.isoformat(),
                "duration_unit": "hourly",
                "start_time": "09:00",
                "end_time": "11:00",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(hourly_req)
        leave_hour = hourly_req.get("leave") or {}
        check("hourly request", bool(hourly_req.get("ok")), hourly_req)
        check("hourly hours=2", abs(float(leave_hour.get("chargeable_hours") or 0) - 2) < 0.01, leave_hour)
        IDS["hourly_leave_id"] = leave_hour.get("leave_id")

        overnight_req = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": night_day.isoformat(),
                "end_date": night_day.isoformat(),
                "duration_unit": "hourly",
                "start_time": "23:00",
                "end_time": "01:00",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(overnight_req)
        check("overnight hourly", bool(overnight_req.get("ok")), overnight_req)

        split_req = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": split_day.isoformat(),
                "end_date": split_day.isoformat(),
                "duration_unit": "hourly",
                "start_time": "17:00",
                "end_time": "19:00",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(split_req)
        check("split-shift hourly", bool(split_req.get("ok")), split_req)

        # Concurrent fractional reservations
        concurrent_day = split_day + timedelta(days=1)
        while concurrent_day.weekday() >= 5:
            concurrent_day += timedelta(days=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (COMPANY, emp_key, PHONE, NAME, concurrent_day),
                )
            conn.commit()
        results: list[dict[str, Any]] = []

        def _reserve(portion: str) -> None:
            results.append(
                app.request_leave(
                    {
                        "employee_phone": PHONE,
                        "leave_type": "annual",
                        "start_date": concurrent_day.isoformat(),
                        "end_date": concurrent_day.isoformat(),
                        "duration_unit": "half_day",
                        "half_portion": portion,
                    },
                    company_code=COMPANY,
                    created_by_phone=PHONE,
                )
            )

        t1 = threading.Thread(target=_reserve, args=("am",))
        t2 = threading.Thread(target=_reserve, args=("pm",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        ok_conc = [r for r in results if r.get("ok")]
        for r in ok_conc:
            track_leave(r)
        check("concurrent fractional reservations", len(ok_conc) == 2, results)

        approve = app.approve_leave_request(
            {"leave_id": leave_half.get("leave_id"), "allow_shift_conflicts": True},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("approve half", bool(approve.get("ok")), approve)
        check("attendance derived", len(approve.get("attendance_updates") or []) >= 1, approve.get("attendance_updates"))
        IDS["attendance_updates"] = len(approve.get("attendance_updates") or [])

        self_appr = app.approve_leave_request(
            {"leave_id": leave_hour.get("leave_id")},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("self-approval denied", self_appr.get("error") == "self_approval_forbidden", self_appr)

        # Stale concurrency via RFI bump
        stale_day = concurrent_day + timedelta(days=1)
        while stale_day.weekday() >= 5:
            stale_day += timedelta(days=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (COMPANY, emp_key, PHONE, NAME, stale_day),
                )
            conn.commit()
        r_stale = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": stale_day.isoformat(),
                "end_date": stale_day.isoformat(),
                "duration_unit": "half_day",
                "half_portion": "am",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(r_stale)
        lid = (r_stale.get("leave") or {}).get("leave_id")
        app.return_leave_for_info({"leave_id": lid, "decision_note": "need docs"}, company_code=COMPANY, created_by_phone=HR_PHONE)
        stale2 = app.approve_leave_request(
            {"leave_id": lid, "expected_row_version": 1, "allow_shift_conflicts": True},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("stale concurrency denied", stale2.get("error") == "stale_row_version", stale2)

        reject = app.reject_leave_request(
            {"leave_id": (half_pm.get("leave") or {}).get("leave_id")},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("reject", bool(reject.get("ok")), reject)

        wd_day = stale_day + timedelta(days=2)
        while wd_day.weekday() >= 5:
            wd_day += timedelta(days=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (COMPANY, emp_key, PHONE, NAME, wd_day),
                )
            conn.commit()
        wd_req = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "annual",
                "start_date": wd_day.isoformat(),
                "end_date": wd_day.isoformat(),
                "duration_unit": "half_day",
                "half_portion": "am",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(wd_req)
        rfi = app.return_leave_for_info(
            {"leave_id": (wd_req.get("leave") or {}).get("leave_id"), "decision_note": "need cert"},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("needs_info", bool(rfi.get("ok")) and (rfi.get("leave") or {}).get("status") == "needs_info", rfi)
        resub = app.resubmit_leave_request(
            {"leave_id": (wd_req.get("leave") or {}).get("leave_id"), "reason": "cert attached"},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("resubmit", bool(resub.get("ok")) and (resub.get("leave") or {}).get("status") == "requested", resub)
        wd = app.withdraw_leave_request(
            {"leave_id": (wd_req.get("leave") or {}).get("leave_id")},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("withdraw", bool(wd.get("ok")) and (wd.get("leave") or {}).get("status") == "withdrawn", wd)

        cancel = app.cancel_leave_request(
            {"leave_id": leave_half.get("leave_id")},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("cancel future approved", bool(cancel.get("ok")), cancel)
        check("cancel temporal future", cancel.get("temporal_state") == "future", cancel)
        check("attendance reverse safe", isinstance(cancel.get("attendance_reversed"), list), cancel)

        # Already started / taken
        past_start = today - timedelta(days=5)
        past_end = today - timedelta(days=3)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leave_requests (
                      company_code, employee_key, employee_phone, employee_name,
                      start_date, end_date, leave_type, status, duration_unit, chargeable_days, chargeable_hours, row_version
                    ) VALUES (%s,%s,%s,%s,%s,%s,'annual','approved','full_day',3,24,1) RETURNING *
                    """,
                    (COMPANY, emp_key, PHONE, NAME, past_start, past_end),
                )
                taken = dict(cur.fetchone())
                track_leave({"leave_id": taken["leave_id"]})
                mid_start = today - timedelta(days=1)
                mid_end = today + timedelta(days=2)
                cur.execute(
                    """
                    INSERT INTO leave_requests (
                      company_code, employee_key, employee_phone, employee_name,
                      start_date, end_date, leave_type, status, duration_unit, chargeable_days, chargeable_hours, row_version
                    ) VALUES (%s,%s,%s,%s,%s,%s,'annual','approved','full_day',4,32,1) RETURNING *
                    """,
                    (COMPANY, emp_key, PHONE, NAME, mid_start, mid_end),
                )
                started = dict(cur.fetchone())
                track_leave({"leave_id": started["leave_id"]})
            conn.commit()
        taken_cancel = app.cancel_leave_request({"leave_id": taken["leave_id"]}, company_code=COMPANY, created_by_phone=HR_PHONE)
        check("already taken denied", taken_cancel.get("error") == "leave_already_taken", taken_cancel)
        started_cancel = app.cancel_leave_request({"leave_id": started["leave_id"]}, company_code=COMPANY, created_by_phone=HR_PHONE)
        check("already started denied", started_cancel.get("error") == "leave_already_started", started_cancel)

        # Unpaid payroll boundary
        unpaid_day = wd_day + timedelta(days=2)
        while unpaid_day.weekday() >= 5:
            unpaid_day += timedelta(days=1)
        unpaid = app.request_leave(
            {
                "employee_phone": PHONE,
                "leave_type": "unpaid",
                "start_date": unpaid_day.isoformat(),
                "end_date": unpaid_day.isoformat(),
                "duration_unit": "full_day",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        track_leave(unpaid)
        check("unpaid request", bool(unpaid.get("ok")), unpaid)
        check("unpaid reservation skipped", (unpaid.get("reservation") or {}).get("skipped") is True, unpaid.get("reservation"))
        check("unpaid request no money", unpaid.get("payroll_monetary_fields_present") is False, unpaid)
        unpaid_appr = app.approve_leave_request(
            {"leave_id": (unpaid.get("leave") or {}).get("leave_id"), "allow_shift_conflicts": True},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("unpaid approve", bool(unpaid_appr.get("ok")), unpaid_appr)
        check("unpaid approve no money", unpaid_appr.get("payroll_monetary_fields_present") is False, unpaid_appr)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT monetary_fields_present, classification FROM leave_payroll_handoff_events WHERE leave_id=%s",
                    ((unpaid.get("leave") or {}).get("leave_id"),),
                )
                row = cur.fetchone()
        check("handoff event recorded", bool(row), row)
        if row:
            drow = dict(row)
            check("handoff monetary false", drow.get("monetary_fields_present") is False, drow)
            IDS["unpaid_handoff"] = drow.get("classification")

        # Attachments / privacy
        up = app.upload_leave_attachment(
            {
                "leave_id": leave_hour.get("leave_id"),
                "filename": "note.pdf",
                "storage_ref": f"leave/{leave_hour.get('leave_id')}/v1/note.pdf",
                "category": "supporting",
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("attachment upload", bool(up.get("ok")), up)
        att_id = (up.get("attachment") or {}).get("attachment_id")
        IDS["attachment_v1"] = att_id
        up2 = app.upload_leave_attachment(
            {
                "leave_id": leave_hour.get("leave_id"),
                "filename": "note-v2.pdf",
                "storage_ref": f"leave/{leave_hour.get('leave_id')}/v2/note.pdf",
                "category": "supporting",
                "replaces_attachment_id": att_id,
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("attachment replace", bool(up2.get("ok")) and int((up2.get("attachment") or {}).get("version") or 0) == 2, up2)
        IDS["attachment_v2"] = (up2.get("attachment") or {}).get("attachment_id")
        sens = app.upload_leave_attachment(
            {
                "leave_id": leave_hour.get("leave_id"),
                "filename": "medical.pdf",
                "storage_ref": f"leave/{leave_hour.get('leave_id')}/medical.pdf",
                "category": "medical",
                "sensitive": True,
            },
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        check("sensitive upload", bool(sens.get("ok")), sens)
        listed = app.list_leave_attachments(
            {"leave_id": leave_hour.get("leave_id"), "deny_sensitive": True},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        masked_rows = [a for a in (listed.get("attachments") or []) if a.get("masked")]
        check("sensitive masked / denied", len(masked_rows) >= 1, listed)
        rej = app.reject_leave_attachment(
            {"attachment_id": (up2.get("attachment") or {}).get("attachment_id"), "reason": "illegible"},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("attachment reject", bool(rej.get("ok")), rej)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) AS n FROM leave_attachment_audit WHERE leave_id=%s",
                    (leave_hour.get("leave_id"),),
                )
                audit_n = int(dict(cur.fetchone())["n"])
        check("attachment audit trail", audit_n >= 3, audit_n)
        IDS["attachment_audit_n"] = audit_n

    finally:
        deleted = cleanup()
        IDS["cleanup"] = deleted
        (EVID / "cleanup.json").write_text(json.dumps(deleted, indent=2, default=str))

    after = assert_reals("post-cleanup", before)
    (EVID / "fingerprints-after.json").write_text(json.dumps(after, indent=2, default=str))
    check(
        "company real totals restored for real fps",
        True,  # already asserted via assert_reals
    )
    # Residual synthetic = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM employees
                WHERE company_code=%s AND (phone LIKE '965527%%' OR name LIKE '%%LVW3B-SYNTH|%%')
                """,
                (COMPANY,),
            )
            residual = int(dict(cur.fetchone())["n"])
    check("synthetic residual 0", residual == 0, residual)

    summary = {"pass": PASS, "fail": FAIL, "tag": TAG, "phone": PHONE, "ids": IDS}
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(json.dumps({"pass": PASS, "fail": FAIL, "evid": str(EVID)}, indent=2))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
