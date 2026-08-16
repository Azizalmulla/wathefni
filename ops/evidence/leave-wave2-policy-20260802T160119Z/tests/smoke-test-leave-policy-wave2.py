#!/usr/bin/env python3
"""Leave Wave 2 — policy & balance correctness smoke (local/staging)."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

PASS = FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
PHONE_DIGITS = ("".join(ch for ch in SUFFIX if ch.isdigit()) + "000000")[:6]


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label} :: {detail}")


def main() -> int:
    print("    leave policy wave2 — holidays, reservations, reconcile, sick tiers, Kuwait TZ")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import leave_policy_wave2 as w2

    check("version", w2.LEAVE_POLICY_WAVE2_VERSION == "2.0.0")
    check("carryover disabled", w2.carryover_enabled(w2.KUWAIT_PRIVATE_PACK) is False)
    check("eligibility conflict noted", any(r["field"] == "annual_eligibility_months" and r["classification"] == "unresolved" for r in w2.OFFICIAL_SOURCE_MATRIX))
    # Pure chargeable
    week = w2.chargeable_leave_days_kuwait("2026-06-01", "2026-06-07", weekend_days=["fri", "sat"], holiday_dates=set())
    check("weekends excluded", week == Decimal("5"))
    hol = w2.chargeable_leave_days_kuwait("2026-06-01", "2026-06-07", weekend_days=["fri", "sat"], holiday_dates={date(2026, 6, 1)})
    check("holiday excluded", hol == Decimal("4"))
    # Span months/years
    span = w2.chargeable_leave_days_kuwait("2025-12-30", "2026-01-02", weekend_days=["fri", "sat"], holiday_dates={date(2026, 1, 1)})
    # Tue 30, Wed 31, Thu 1(holiday), Fri 2(weekend) -> 2
    check("span year+holiday", span == Decimal("2"), span)
    tiers = w2.sick_tier_breakdown(Decimal("20"), w2.KUWAIT_PRIVATE_PACK["policies"]["sick"]["tiers"])
    check("sick tiers 15+5", tiers[0]["days"] == 15.0 and tiers[1]["days"] == 5.0, tiers)
    # Midnight Kuwait boundary
    before = datetime(2026, 8, 2, 21, 30, tzinfo=ZoneInfo("UTC"))  # 00:30 Aug 3 Kuwait
    check("kuwait date near midnight", w2.kuwait_today_wave2(now=before) == date(2026, 8, 3))

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    os.environ["WATHEFNI_LEAVE_BALANCES"] = "on"
    os.environ.setdefault("WATHEFNI_LEAVE_POLICY_WAVE2", "on")
    app.notify_employee_leave_decision = lambda *a, **k: {"ok": True, "stub": True}

    company = "WATHEFNI"
    if not app.company_has_module(company, "leave"):
        print("skip: leave module off")
        return 1 if FAIL else 0

    phone = f"965526{PHONE_DIGITS}"
    name = f"LVW2-SYNTH| Emp {SUFFIX}"
    emp_key = None

    def cleanup():
        nonlocal emp_key
        if not emp_key:
            return
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT leave_id FROM leave_requests WHERE employee_key=%s", (emp_key,))
                ids = [str(dict(r)["leave_id"]) for r in cur.fetchall()]
                if ids:
                    cur.execute("DELETE FROM leave_events WHERE leave_id = ANY(%s::uuid[])", (ids,))
                    cur.execute("DELETE FROM leave_ledger WHERE leave_id = ANY(%s::uuid[]) OR employee_key=%s", (ids, emp_key))
                    cur.execute("DELETE FROM leave_requests WHERE leave_id = ANY(%s::uuid[])", (ids,))
                cur.execute("DELETE FROM leave_balances WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (emp_key,))
            conn.commit()

    cleanup()
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w2.ensure_leave_policy_wave2_schema(cur)
                w2.seed_kuwait_private_policy_pack(cur)
                w2.bind_company_policy_pack(cur, company)
                w2.seed_fixed_kuwait_holidays(cur, company, year=2026)
            conn.commit()
        app.seed_company_leave_policies(company)
        # Force sick tiers
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE leave_policies SET tiers=%s::jsonb WHERE company_code=%s AND leave_type='sick'",
                    (__import__("json").dumps(w2.KUWAIT_PRIVATE_PACK["policies"]["sick"]["tiers"]), company),
                )
            conn.commit()

        seeded = app.create_company_employee(company, name=name, phone=phone, position_title="W2")
        emp = app.find_employee_by_phone(phone, company_code=company) or {}
        emp_key = str(emp.get("employee_key") or "")
        check("employee seeded", bool(emp_key), seeded)
        today = app.kuwait_today()
        # Treat hire as year-start so catchup accrual has material balance
        hire = date(today.year, 1, 1) if today.month >= 3 else date(today.year - 1, 1, 1)
        emp = {**emp, "hired_at": hire, "start_date": hire, "hire_date": hire}

        # Accrue so there is balance to reserve
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pol = app.get_leave_policy(company, "annual")
                n = app.post_leave_accrual_catchup(cur, company_code=company, employee=emp, policy=pol, as_of=today)
            conn.commit()
        check("accrual posted", n >= 1, n)
        bal0 = app.leave_balances_for_employee(company, emp_key, today.year)
        annual0 = next((b for b in bal0 if b["leave_type"] == "annual"), None)
        check("balance exists", bool(annual0), bal0)
        available0 = float(annual0["current_balance"]) if annual0 else 0
        check("available > 0", available0 > 0, available0)

        # Holiday exclusion on National Day week 2026-02-22..28
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                hols = w2.holiday_dates_for_range(cur, company, date(2026, 2, 22), date(2026, 2, 28))
        check("national+liberation seeded", date(2026, 2, 25) in hols and date(2026, 2, 26) in hols, hols)
        days = w2.chargeable_leave_days_kuwait(
            date(2026, 2, 22), date(2026, 2, 28), weekend_days=["fri", "sat"], holiday_dates=hols
        )
        # Sun22 Mon23 Tue24 Wed25(hol) Thu26(hol) Fri27 Sat28 -> 3
        check("feb week chargeable=3", days == Decimal("3"), days)

        # Request A reserves 2 chargeable weekdays
        start_a = today + timedelta(days=10)
        while start_a.weekday() >= 4:
            start_a += timedelta(days=1)
        end_a = start_a + timedelta(days=1)
        while end_a.weekday() >= 4:
            end_a += timedelta(days=1)
        req_a = app.request_leave(
            {"employee_phone": phone, "leave_type": "annual", "start_date": start_a.isoformat(), "end_date": end_a.isoformat()},
            company_code=company,
            created_by_phone=phone,
        )
        check("request A ok", bool(req_a.get("ok")), req_a)
        leave_a = req_a.get("leave") or {}
        res_a = req_a.get("reservation") or {}
        check("reservation A posted", bool(res_a.get("reserved")), res_a)

        # Concurrent B: ask for more chargeable days than remaining available — must not overspend
        start_b = end_a + timedelta(days=5)
        while start_b.weekday() >= 4:
            start_b += timedelta(days=1)
        end_b = start_b + timedelta(days=90)
        req_b = app.request_leave(
            {"employee_phone": phone, "leave_type": "annual", "start_date": start_b.isoformat(), "end_date": end_b.isoformat()},
            company_code=company,
            created_by_phone=phone,
        )
        check("request B created (observe)", bool(req_b.get("ok")), req_b)
        res_b = req_b.get("reservation") or {}
        check(
            "concurrent B insufficient — no double-reserve",
            res_b.get("insufficient_balance_observe") is True and res_b.get("reserved") is False,
            res_b,
        )

        # Approve A: reservation → consume once
        hr = "96588001111"
        appr = app.approve_leave_request(
            {"leave_id": leave_a.get("leave_id"), "expected_row_version": leave_a.get("row_version") or 1, "allow_shift_conflicts": True},
            company_code=company,
            created_by_phone=hr,
        )
        check("approve A", bool(appr.get("ok")), appr)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                app.observe_leave_consumption(
                    cur,
                    company_code=company,
                    leave={**leave_a, "leave_type": "annual", "status": "approved"},
                    kind="consume",
                    actor_phone=hr,
                )
                cur.execute(
                    "SELECT COUNT(*) AS n FROM leave_ledger WHERE leave_id=%s AND entry_kind='consume'",
                    (leave_a.get("leave_id"),),
                )
                n_consume = int(dict(cur.fetchone())["n"])
                cur.execute(
                    """
                    SELECT COALESCE(SUM(CASE WHEN entry_kind='reservation' THEN days END),0)
                         - COALESCE(SUM(CASE WHEN entry_kind='reservation_release' THEN days END),0) AS open
                    FROM leave_ledger WHERE leave_id=%s
                    """,
                    (leave_a.get("leave_id"),),
                )
                open_a = Decimal(str(dict(cur.fetchone())["open"] or 0))
            conn.commit()
        check("consume exactly once", n_consume == 1, n_consume)
        check("approve converted reservation (open=0)", open_a == 0, open_a)

        # Reject path releases: create C then reject
        start_c = today + timedelta(days=60)
        while start_c.weekday() >= 4:
            start_c += timedelta(days=1)
        req_c = app.request_leave(
            {"employee_phone": phone, "leave_type": "annual", "start_date": start_c.isoformat(), "end_date": start_c.isoformat()},
            company_code=company,
            created_by_phone=phone,
        )
        leave_c = req_c.get("leave") or {}
        check("C reserved before reject", bool((req_c.get("reservation") or {}).get("reserved")), req_c.get("reservation"))
        rej = app.reject_leave_request(
            {"leave_id": leave_c.get("leave_id"), "expected_row_version": leave_c.get("row_version") or 1},
            company_code=company,
            created_by_phone=hr,
        )
        check("reject C", bool(rej.get("ok")), rej)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(CASE WHEN entry_kind='reservation' THEN days END),0)
                         - COALESCE(SUM(CASE WHEN entry_kind='reservation_release' THEN days END),0) AS open
                    FROM leave_ledger WHERE leave_id=%s
                    """,
                    (leave_c.get("leave_id"),),
                )
                open_c = Decimal(str(dict(cur.fetchone())["open"] or 0))
        check("reject released reservation", open_c == 0, open_c)

        # Cancel pending releases reservation
        start_d = today + timedelta(days=75)
        while start_d.weekday() >= 4:
            start_d += timedelta(days=1)
        req_d = app.request_leave(
            {"employee_phone": phone, "leave_type": "annual", "start_date": start_d.isoformat(), "end_date": start_d.isoformat()},
            company_code=company,
            created_by_phone=phone,
        )
        leave_d = req_d.get("leave") or {}
        cancel_d = app.cancel_leave_request(
            {"leave_id": leave_d.get("leave_id"), "expected_row_version": leave_d.get("row_version") or 1},
            company_code=company,
            created_by_phone=hr,
        )
        check("cancel pending D", bool(cancel_d.get("ok")), cancel_d)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(CASE WHEN entry_kind='reservation' THEN days END),0)
                         - COALESCE(SUM(CASE WHEN entry_kind='reservation_release' THEN days END),0) AS open
                    FROM leave_ledger WHERE leave_id=%s
                    """,
                    (leave_d.get("leave_id"),),
                )
                open_d = Decimal(str(dict(cur.fetchone())["open"] or 0))
        check("cancel pending released reservation", open_d == 0, open_d)

        # Expire/stale releases reservation
        import leave_authority_wave1 as leave_w1

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                stale_start = (today - timedelta(days=5)).isoformat()
                stale_end = (today - timedelta(days=4)).isoformat()
                cur.execute(
                    """
                    INSERT INTO leave_requests (
                      company_code, employee_key, employee_phone, employee_name,
                      start_date, end_date, leave_type, status, reason, metadata, row_version
                    ) VALUES (%s,%s,%s,%s,%s,%s,'annual','requested','stale-w2',%s,1)
                    RETURNING *
                    """,
                    (company, emp_key, app.digits(phone), name, stale_start, stale_end, app.Json({})),
                )
                leave_e = dict(cur.fetchone())
                pol = app.get_leave_policy(company, "annual") or {}
                # Force a reservation row even for past dates (observe path)
                w2.reserve_leave_balance(cur, company_code=company, leave=leave_e, policy=pol, actor_phone=phone)
                settings = leave_w1.get_leave_authority_settings(cur, company)
                rows = leave_w1.apply_stale_pending(
                    cur, company_code=company, settings=settings, leave_id=str(leave_e["leave_id"])
                )
                if rows:
                    w2.release_leave_reservation(
                        cur,
                        company_code=company,
                        leave={**rows[0], "leave_type": "annual"},
                        policy=pol,
                        actor_phone=hr,
                        reason="expired_stale",
                    )
                cur.execute(
                    """
                    SELECT COALESCE(SUM(CASE WHEN entry_kind='reservation' THEN days END),0)
                         - COALESCE(SUM(CASE WHEN entry_kind='reservation_release' THEN days END),0) AS open
                    FROM leave_ledger WHERE leave_id=%s
                    """,
                    (leave_e["leave_id"],),
                )
                open_e = Decimal(str(dict(cur.fetchone())["open"] or 0))
            conn.commit()
        check("stale expire released reservation", open_e == 0, open_e)

        # Sick tier banding stored on reservation (no payroll money)
        start_s = today + timedelta(days=100)
        while start_s.weekday() >= 4:
            start_s += timedelta(days=1)
        end_s = start_s + timedelta(days=24)  # ~19 chargeable weekdays → bands 15+4
        req_s = app.request_leave(
            {"employee_phone": phone, "leave_type": "sick", "start_date": start_s.isoformat(), "end_date": end_s.isoformat()},
            company_code=company,
            created_by_phone=phone,
        )
        leave_s = req_s.get("leave") or {}
        tiers_s = (req_s.get("reservation") or {}).get("tier_breakdown") or []
        if not tiers_s and leave_s.get("leave_id"):
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT tier_breakdown FROM leave_ledger WHERE leave_id=%s AND entry_kind='reservation' LIMIT 1",
                        (leave_s.get("leave_id"),),
                    )
                    row = cur.fetchone()
                    tiers_s = (dict(row).get("tier_breakdown") if row else None) or []
        check("sick tiers present", isinstance(tiers_s, list) and len(tiers_s) >= 1, tiers_s)
        check(
            "sick tiers observe-only payroll_owned",
            all(t.get("payroll_owned") is True for t in tiers_s if isinstance(t, dict)),
            tiers_s,
        )

        # Cancel approved reverses balance
        bal_mid = next(b for b in app.leave_balances_for_employee(company, emp_key, today.year) if b["leave_type"] == "annual")
        cancel = app.cancel_leave_request(
            {"leave_id": leave_a.get("leave_id"), "expected_row_version": (appr.get("leave") or {}).get("row_version")},
            company_code=company,
            created_by_phone=hr,
        )
        check("cancel approved", bool(cancel.get("ok")), cancel)
        bal_after = next(b for b in app.leave_balances_for_employee(company, emp_key, today.year) if b["leave_type"] == "annual")
        check("reversal restored balance >= mid", bal_after["current_balance"] >= bal_mid["current_balance"] - 0.01, (bal_mid, bal_after))
        check("attendance reverse path safe", isinstance(cancel.get("attendance_reversed"), list), cancel.get("attendance_reversed"))

        # Reconcile
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                rec = w2.reconcile_ledger_to_balances(
                    cur, company_code=company, employee_key=emp_key, leave_type="annual", period_year=today.year
                )
            conn.commit()
        check("ledger/rollup reconcile", rec.get("ok") is True, rec)

        # Honesty still false
        check("enforced false", app.get_leave_policy(company, "annual").get("enforced") is False)
        check("wave2 pack legal_reviewed false", w2.KUWAIT_PRIVATE_PACK["legal_reviewed"] is False)

    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
