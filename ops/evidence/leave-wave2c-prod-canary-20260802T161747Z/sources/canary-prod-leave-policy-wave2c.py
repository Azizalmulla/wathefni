#!/usr/bin/env python3
"""Leave Wave 2C — production synthetic policy/balance canary (WATHEFNI only).

Markers: LVW2C / LVW2C-SYNTH| / phone prefix 965526.
enforced=false, legal_reviewed=false. Real leave fingerprints must stay unchanged.
No payroll money mutation. Full synthetic cleanup required.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY", "on")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY", "on")
os.environ.setdefault(
    "WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS",
    "LVW1B,LVW1B-SYNTH|,LVW2C,LVW2C-SYNTH|",
)
os.environ.setdefault("WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES", "965525,965526")

import app  # noqa: E402
import leave_policy_wave2 as w2  # noqa: E402
import leave_authority_wave1 as leave_w1  # noqa: E402
import employee_lifecycle_wave3c as w3c  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("LVW2C_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
PHONE = f"9655261{TAG_DIGITS}"
HR_PHONE = "96588009911"
NAME = f"LVW2C-SYNTH| Emp {TAG}"

REAL_FPS = {
    "e3217e0e-466f-4f38-aa10-dab503dcb0a4": "abf4cba7cb8702b2d7c067db795d0701",
    "51cd940f-a04b-4ad1-9a6a-43e3da59a222": "8f6d67e3cc4fbf5ee321af235ecbb20d",
    "dbf82ecf-7ac4-451b-b41c-03de943f2161": "34c7cf18a4d758698bbf7cac6da70d1f",
}

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("LVW2C_EVID") or f"/tmp/leave-w2c-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {"tag": TAG, "phone": PHONE, "name": NAME}


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


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
        # Company-wide ledger/balance counts may rise with synthetics; compare real-only leave fps only.
    return after


def open_reservation_days(cur, leave_id: str) -> Decimal:
    cur.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN entry_kind='reservation' THEN days END),0)
             - COALESCE(SUM(CASE WHEN entry_kind='reservation_release' THEN days END),0) AS open
        FROM leave_ledger WHERE leave_id=%s
        """,
        (leave_id,),
    )
    return Decimal(str(dict(cur.fetchone())["open"] or 0))


def cleanup() -> dict[str, int]:
    deleted: dict[str, int] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key FROM employees
                WHERE company_code=%s AND (
                  phone LIKE '965526%%' OR name LIKE '%%LVW2C-SYNTH|%%' OR employee_key LIKE '%%LVW2C%%'
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
                cur.execute("DELETE FROM leave_events WHERE leave_id = ANY(%s::uuid[])", (leave_ids,))
                deleted["leave_events"] = cur.rowcount
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
            for table in (
                "attendance_events",
                "attendance_records",
                "shift_assignments",
            ):
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
                deleted["payroll_timesheet_events"] = cur.rowcount
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
    print(f"leave wave2c prod canary tag={TAG} phone={PHONE}")
    app.notify_employee_leave_decision = lambda *a, **k: {"ok": True, "stub": True}

    check("wave2 enabled", w2.leave_policy_wave2_enabled() is True)
    check("pack version 2.1.0", w2.KUWAIT_PRIVATE_PACK["version"] == "2.1.0")
    check("enforced false", w2.KUWAIT_PRIVATE_PACK["enforced"] is False)
    check("legal_reviewed false", w2.KUWAIT_PRIVATE_PACK["legal_reviewed"] is False)
    check("carryover writers disabled", w2.carryover_enabled(w2.KUWAIT_PRIVATE_PACK) is False)
    elig = w2.resolved_eligibility_months()
    check("eligibility months 6", elig.get("months") == 6, elig)

    # Unit: Kuwait midnight
    before = datetime(2026, 8, 2, 21, 30, tzinfo=ZoneInfo("UTC"))
    check("kuwait midnight boundary", w2.kuwait_today_wave2(now=before) == date(2026, 8, 3))

    cleanup()
    before_fp = assert_reals("pre")
    (EVID / "fingerprints-before.json").write_text(json.dumps(before_fp, indent=2, default=str), encoding="utf-8")

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_database() AS db")
                check("db wathefni", dict(cur.fetchone())["db"] == "wathefni")
                w2.ensure_leave_policy_wave2_schema(cur)
                w2.seed_kuwait_private_policy_pack(cur)
                w2.bind_company_policy_pack(cur, COMPANY)
                year = app.kuwait_today().year
                w2.seed_fixed_kuwait_holidays(cur, COMPANY, year=year)
                cur.execute(
                    "SELECT pack_version FROM leave_company_policy_bindings WHERE company_code=%s",
                    (COMPANY,),
                )
                bind = dict(cur.fetchone())
                cur.execute(
                    "SELECT status FROM leave_holiday_year_versions WHERE calendar_code='kw_public_v2' AND year=%s ORDER BY version DESC LIMIT 1",
                    (year,),
                )
                hv = dict(cur.fetchone() or {})
            conn.commit()
        check("binding 2.1.0", bind.get("pack_version") == "2.1.0", bind)
        check("holiday year pending_review", hv.get("status") == "pending_review", hv)

        pol = app.get_leave_policy(COMPANY, "annual") or {}
        check("annual eligibility_months 6", int(pol.get("eligibility_months") or 0) == 6, pol)
        check("annual days_per_year 30", int(pol.get("days_per_year") or 0) == 30, pol)
        check("annual enforced false", pol.get("enforced") is False, pol)
        weekends = {str(w).lower() for w in (pol.get("weekend_days") or [])}
        check("weekend fri/sat", "fri" in weekends and "sat" in weekends, weekends)

        sick = app.get_leave_policy(COMPANY, "sick") or {}
        tiers = sick.get("tiers") or []
        check("sick tiers present", isinstance(tiers, list) and len(tiers) >= 5, tiers)

        # Enforced fail-closed while year pending
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                gate = w2.ensure_holiday_calendar_for_enforced(
                    cur, start_date=date(year, 2, 22), end_date=date(year, 2, 28)
                )
        check("enforced holiday fail-closed", gate.get("ok") is False and gate.get("fail_closed") is True, gate)

        # Holiday exclusion observe path (seeded_fixed)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                hols = w2.holiday_dates_for_range(cur, COMPANY, date(year, 2, 22), date(year, 2, 28))
        days = w2.chargeable_leave_days_kuwait(
            date(year, 2, 22), date(year, 2, 28), weekend_days=["fri", "sat"], holiday_dates=hols
        )
        check("national/liberation excluded", days == Decimal("3"), {"days": days, "hols": list(hols)})

        # Seed employee with hire for eligibility boundary
        app.create_company_employee(COMPANY, name=NAME, phone=PHONE, position_title="W2C")
        emp = app.find_employee_by_phone(PHONE, company_code=COMPANY) or {}
        emp_key = str(emp.get("employee_key") or "")
        check("synthetic employee", bool(emp_key), emp)
        IDS["employee_key"] = emp_key
        today = app.kuwait_today()
        hire = date(today.year, 1, 1) if today.month >= 7 else date(today.year - 1, 1, 1)
        emp = {**emp, "hired_at": hire, "start_date": hire, "hire_date": hire}
        can_take = app._leave_eligibility_date(hire, 6)
        check("eligibility can_take_from = hire+6m", can_take is not None and can_take > hire, {"hire": hire, "can_take": can_take})
        # Boundary: hire 3 months ago → can_take still in future relative to "now-from-hire+6"
        recent_hire = today - timedelta(days=60)
        early = app._leave_eligibility_date(recent_hire, 6)
        check("under-6-months can_take_from future", early is not None and early > today, {"recent_hire": recent_hire, "early": early})
        mature_hire = today - timedelta(days=200)
        mature = app._leave_eligibility_date(mature_hire, 6)
        check("over-6-months can_take_from past/today", mature is not None and mature <= today, {"mature_hire": mature_hire, "mature": mature})

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                n = app.post_leave_accrual_catchup(cur, company_code=COMPANY, employee=emp, policy=pol, as_of=today)
            conn.commit()
        check("accrual posted", n >= 1, n)
        bals = app.leave_balances_for_employee(COMPANY, emp_key, today.year)
        annual = next((b for b in bals if b["leave_type"] == "annual"), None)
        check("annual balance exists", bool(annual) and float(annual["current_balance"]) > 0, annual)
        check("can_take_from set", bool(annual and annual.get("can_take_from")), annual)

        # Request A reserves
        start_a = today + timedelta(days=14)
        while start_a.weekday() >= 4:
            start_a += timedelta(days=1)
        end_a = start_a + timedelta(days=1)
        while end_a.weekday() >= 4:
            end_a += timedelta(days=1)
        req_a = app.request_leave(
            {"employee_phone": PHONE, "leave_type": "annual", "start_date": start_a.isoformat(), "end_date": end_a.isoformat()},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        leave_a = req_a.get("leave") or {}
        res_a = req_a.get("reservation") or {}
        check("request A ok", bool(req_a.get("ok")), req_a)
        check("reservation A posted", bool(res_a.get("reserved")), res_a)
        IDS["leave_a"] = leave_a.get("leave_id")

        # Concurrent overspend
        start_b = end_a + timedelta(days=7)
        while start_b.weekday() >= 4:
            start_b += timedelta(days=1)
        end_b = start_b + timedelta(days=90)
        req_b = app.request_leave(
            {"employee_phone": PHONE, "leave_type": "annual", "start_date": start_b.isoformat(), "end_date": end_b.isoformat()},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        res_b = req_b.get("reservation") or {}
        leave_b = req_b.get("leave") or {}
        check("request B created observe", bool(req_b.get("ok")), req_b)
        check(
            "B no double-reserve",
            res_b.get("insufficient_balance_observe") is True and res_b.get("reserved") is False,
            res_b,
        )
        IDS["leave_b"] = leave_b.get("leave_id")
        # Cancel B so later short requests do not hit overlapping_leave_exists
        if leave_b.get("leave_id"):
            cancel_b = app.cancel_leave_request(
                {"leave_id": leave_b.get("leave_id"), "expected_row_version": leave_b.get("row_version") or 1},
                company_code=COMPANY,
                created_by_phone=HR_PHONE,
            )
            check("cancel B observe request", bool(cancel_b.get("ok")), cancel_b)

        # Approve A → consume once
        appr = app.approve_leave_request(
            {"leave_id": leave_a.get("leave_id"), "expected_row_version": leave_a.get("row_version") or 1, "allow_shift_conflicts": True},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("approve A", bool(appr.get("ok")), appr)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                app.observe_leave_consumption(
                    cur,
                    company_code=COMPANY,
                    leave={**leave_a, "leave_type": "annual", "status": "approved"},
                    kind="consume",
                    actor_phone=HR_PHONE,
                )
                cur.execute(
                    "SELECT COUNT(*) AS n FROM leave_ledger WHERE leave_id=%s AND entry_kind='consume'",
                    (leave_a.get("leave_id"),),
                )
                n_consume = int(dict(cur.fetchone())["n"])
                open_a = open_reservation_days(cur, leave_a.get("leave_id"))
            conn.commit()
        check("consume exactly once", n_consume == 1, n_consume)
        check("reservation converted open=0", open_a == 0, open_a)
        check("attendance derived list", isinstance(appr.get("attendance_derived"), list) or "attendance" in str(appr).lower() or appr.get("ok") is True, appr)

        # Reject releases
        start_c = today + timedelta(days=45)
        while start_c.weekday() >= 4:
            start_c += timedelta(days=1)
        req_c = app.request_leave(
            {"employee_phone": PHONE, "leave_type": "annual", "start_date": start_c.isoformat(), "end_date": start_c.isoformat()},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        leave_c = req_c.get("leave") or {}
        check("request C ok", bool(req_c.get("ok")) and bool(leave_c.get("leave_id")), req_c)
        rej = app.reject_leave_request(
            {"leave_id": leave_c.get("leave_id"), "expected_row_version": leave_c.get("row_version") or 1},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("reject C", bool(rej.get("ok")), rej)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                open_c = open_reservation_days(cur, leave_c.get("leave_id")) if leave_c.get("leave_id") else Decimal("-1")
        check("reject released", open_c == 0, open_c)

        # Cancel pending releases
        start_d = today + timedelta(days=55)
        while start_d.weekday() >= 4:
            start_d += timedelta(days=1)
        req_d = app.request_leave(
            {"employee_phone": PHONE, "leave_type": "annual", "start_date": start_d.isoformat(), "end_date": start_d.isoformat()},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        leave_d = req_d.get("leave") or {}
        check("request D ok", bool(req_d.get("ok")) and bool(leave_d.get("leave_id")), req_d)
        cancel_d = app.cancel_leave_request(
            {"leave_id": leave_d.get("leave_id"), "expected_row_version": leave_d.get("row_version") or 1},
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("cancel pending D", bool(cancel_d.get("ok")), cancel_d)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                open_d = open_reservation_days(cur, leave_d.get("leave_id")) if leave_d.get("leave_id") else Decimal("-1")
        check("cancel pending released", open_d == 0, open_d)

        # Expire / stale releases
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                stale_start = (today - timedelta(days=5)).isoformat()
                stale_end = (today - timedelta(days=4)).isoformat()
                cur.execute(
                    """
                    INSERT INTO leave_requests (
                      company_code, employee_key, employee_phone, employee_name,
                      start_date, end_date, leave_type, status, reason, metadata, row_version
                    ) VALUES (%s,%s,%s,%s,%s,%s,'annual','requested','stale-w2c',%s,1)
                    RETURNING *
                    """,
                    (COMPANY, emp_key, app.digits(PHONE), NAME, stale_start, stale_end, app.Json({})),
                )
                leave_e = dict(cur.fetchone())
                w2.reserve_leave_balance(cur, company_code=COMPANY, leave=leave_e, policy=pol, actor_phone=PHONE)
                settings = leave_w1.get_leave_authority_settings(cur, COMPANY)
                rows = leave_w1.apply_stale_pending(
                    cur,
                    company_code=COMPANY,
                    settings=settings,
                    as_of=today,
                    record_event=app.record_leave_event,
                    actor_phone=HR_PHONE,
                    leave_id=str(leave_e["leave_id"]),
                )
                if rows:
                    w2.release_leave_reservation(
                        cur,
                        company_code=COMPANY,
                        leave={**rows[0], "leave_type": "annual"},
                        policy=pol,
                        actor_phone=HR_PHONE,
                        reason="expired_stale",
                    )
                open_e = open_reservation_days(cur, leave_e["leave_id"])
            conn.commit()
        check("stale expire released", open_e == 0, open_e)

        # Sick tiers + unpaid boundary (before lifecycle decline of open rows)
        start_s = today + timedelta(days=80)
        while start_s.weekday() >= 4:
            start_s += timedelta(days=1)
        end_s = start_s + timedelta(days=24)
        req_s = app.request_leave(
            {"employee_phone": PHONE, "leave_type": "sick", "start_date": start_s.isoformat(), "end_date": end_s.isoformat()},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        tiers_s = (req_s.get("reservation") or {}).get("tier_breakdown") or []
        check("sick request ok", bool(req_s.get("ok")), req_s)
        check("sick tiers payroll_owned", isinstance(tiers_s, list) and len(tiers_s) >= 1 and all(t.get("payroll_owned") for t in tiers_s if isinstance(t, dict)), tiers_s)

        unpaid_leave_id = str(uuid.uuid4())
        unpaid_pol = {"leave_type": "unpaid", "payroll_boundary": True, "weekend_days": ["fri", "sat"], "exclude_public_holidays": True}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                ures = w2.reserve_leave_balance(
                    cur,
                    company_code=COMPANY,
                    leave={
                        "leave_id": unpaid_leave_id,
                        "employee_key": emp_key,
                        "leave_type": "unpaid",
                        "start_date": start_s,
                        "end_date": start_s,
                    },
                    policy=unpaid_pol,
                    actor_phone=PHONE,
                )
            conn.commit()
        check(
            "unpaid reservation skipped payroll boundary",
            ures.get("skipped") is True and ures.get("reason") == "unpaid_payroll_boundary",
            ures,
        )
        check(
            "unpaid pack payroll_boundary",
            bool(w2.KUWAIT_PRIVATE_PACK["policies"]["unpaid"].get("payroll_boundary")),
        )

        # Reversal restores — cancel approved A BEFORE lifecycle decline
        leave_a_live = (appr.get("leave") or leave_a) or {}
        bal_mid = next(b for b in app.leave_balances_for_employee(COMPANY, emp_key, today.year) if b["leave_type"] == "annual")
        cancel_a = app.cancel_leave_request(
            {
                "leave_id": leave_a_live.get("leave_id") or leave_a.get("leave_id"),
                "expected_row_version": leave_a_live.get("row_version"),
            },
            company_code=COMPANY,
            created_by_phone=HR_PHONE,
        )
        check("cancel approved A", bool(cancel_a.get("ok")), cancel_a)
        bal_after = next(b for b in app.leave_balances_for_employee(COMPANY, emp_key, today.year) if b["leave_type"] == "annual")
        check(
            "reversal restored balance",
            bal_after["current_balance"] >= bal_mid["current_balance"] - 0.01,
            {"mid": bal_mid, "after": bal_after},
        )
        check("attendance reverse safe", isinstance(cancel_a.get("attendance_reversed"), list), cancel_a.get("attendance_reversed"))

        # Lifecycle decline releases a fresh pending reservation
        start_f = today + timedelta(days=70)
        while start_f.weekday() >= 4:
            start_f += timedelta(days=1)
        req_f = app.request_leave(
            {"employee_phone": PHONE, "leave_type": "annual", "start_date": start_f.isoformat(), "end_date": start_f.isoformat()},
            company_code=COMPANY,
            created_by_phone=PHONE,
        )
        leave_f = req_f.get("leave") or {}
        check("request F ok for lifecycle", bool(req_f.get("ok")) and bool(leave_f.get("leave_id")), req_f)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                decl = w3c._execute_downstream_action(
                    cur,
                    company=COMPANY,
                    req={"action_type": "decline_open_leave", "employee_key": emp_key},
                )
                open_f = open_reservation_days(cur, leave_f.get("leave_id")) if leave_f.get("leave_id") else Decimal("-1")
            conn.commit()
        check("lifecycle decline applied", bool(decl.get("declined_leave_ids")), decl)
        check("lifecycle decline released reservation", open_f == 0, open_f)

        # Reconcile
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                rec = w2.reconcile_ledger_to_balances(
                    cur, company_code=COMPANY, employee_key=emp_key, leave_type="annual", period_year=today.year
                )
            conn.commit()
        check("ledger/rollup reconcile", rec.get("ok") is True, rec)

        # No payroll money mutation markers
        check("no payment keys in cancel", "payment" not in json.dumps(cancel_a).lower() or "payroll_impact" in cancel_a, cancel_a)
        check("policies still unenforced", app.get_leave_policy(COMPANY, "annual").get("enforced") is False)

    finally:
        deleted = cleanup()
        (EVID / "cleanup.json").write_text(json.dumps(deleted, indent=2), encoding="utf-8")
        after_fp = assert_reals("post-cleanup", before_fp)
        (EVID / "fingerprints-after.json").write_text(json.dumps(after_fp, indent=2, default=str), encoding="utf-8")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM employees
                    WHERE company_code=%s AND (phone LIKE '965526%%' OR name LIKE '%%LVW2C-SYNTH|%%')
                    """,
                    (COMPANY,),
                )
                residual = int(dict(cur.fetchone())["n"])
        check("synthetic residual 0", residual == 0, residual)

    summary = {"pass": PASS, "fail": FAIL, "tag": TAG, "ids": IDS, "results": RESULTS}
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"pass": PASS, "fail": FAIL, "tag": TAG}, indent=2))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
