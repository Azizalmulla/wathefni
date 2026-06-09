"""Smoke test: leave balances P1 (accrual + observe-only consumption + reads).

Leave balances are dark-launched behind WATHEFNI_LEAVE_BALANCES and are strictly
observe-only in P1: accrual + consumption are tracked into an append-only ledger
and materialized into balances, but NOTHING blocks or alters a leave decision,
and every legal figure lives in editable policy rows (never hardcoded into
behaviour). This test pins:

  - chargeable_leave_days: pure math excludes configured weekend rest days and
    public holidays, inclusive range, reversed/empty ranges -> 0
  - the dark-launch flag defaults OFF, flips ON via env; the accrual sweep is a
    no-op while OFF (no ledger rows can sneak through)
  - seeding is idempotent and inert (enforced=false, legal_reviewed=false)
  - accrual (staging DB): calendar-year monthly catch-up accrues entitlement/12
    per elapsed month, pro-rata for the hire month, and is idempotent on re-run
  - observe-only consumption: an approved leave posts a consume entry that lowers
    the balance by exactly the chargeable days; a reversal restores it; both are
    idempotent and never raise

Run (staging has psycopg2): python3 smoke-test-leave-balances.py
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    leave balances P1 — chargeable days + flag gate + accrual + observe-only consumption")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    # --- 1) chargeable_leave_days pure math ----------------------------------
    # Mon 2026-06-01 .. Sun 2026-06-07: Fri(05)+Sat(06) are weekend -> 5 chargeable.
    full_week = app.chargeable_leave_days("2026-06-01", "2026-06-07", weekend_days=["fri", "sat"], holiday_dates=set())
    check("week excludes fri/sat (5 of 7)", full_week == Decimal("5"))
    with_holiday = app.chargeable_leave_days("2026-06-01", "2026-06-07", weekend_days=["fri", "sat"], holiday_dates={date(2026, 6, 1)})
    check("public holiday is excluded (4 of 7)", with_holiday == Decimal("4"))
    single = app.chargeable_leave_days("2026-06-01", "2026-06-01", weekend_days=["fri", "sat"], holiday_dates=set())
    check("single working day counts 1", single == Decimal("1"))
    check("reversed range -> 0", app.chargeable_leave_days("2026-06-07", "2026-06-01", weekend_days=["fri", "sat"], holiday_dates=set()) == Decimal("0"))

    # --- 2) dark-launch flag --------------------------------------------------
    orig_flag = os.environ.get("WATHEFNI_LEAVE_BALANCES")
    os.environ.pop("WATHEFNI_LEAVE_BALANCES", None)
    check("flag defaults OFF when unset", app.leave_balances_enabled() is False)
    os.environ["WATHEFNI_LEAVE_BALANCES"] = "off"
    check("flag stays OFF for 'off'", app.leave_balances_enabled() is False)
    check("accrual sweep is a no-op while OFF", app.run_leave_accrual_sweep().get("skipped") is True)
    os.environ["WATHEFNI_LEAVE_BALANCES"] = "on"
    check("flag flips ON for 'on'", app.leave_balances_enabled() is True)

    # --- 3) seeding is idempotent + inert ------------------------------------
    company = f"ZZLEAVE{SUFFIX}".upper()
    emp_key = f"zz_leave_{SUFFIX}"
    try:
        app.seed_leave_policy_presets()
        app.seed_leave_policy_presets()  # idempotent
        app.seed_company_leave_policies(company)
        app.seed_company_leave_policies(company)  # idempotent
        annual_policy = app.get_leave_policy(company, "annual")
        check("annual policy seeded for company", annual_policy is not None)
        if annual_policy:
            check("seeded policy is not enforced", bool(annual_policy.get("enforced")) is False)
            check("seeded policy is not legal_reviewed", bool(annual_policy.get("legal_reviewed")) is False)
            check("annual entitlement is the preset value", Decimal(str(annual_policy.get("days_per_year"))) == Decimal("30"))

        # --- 4) accrual catch-up + idempotency -------------------------------
        as_of = date(2026, 6, 30)  # 6 elapsed months in 2026
        emp_old = {"employee_key": emp_key, "hired_at": date(2020, 1, 1)}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                posted = app.post_leave_accrual_catchup(cur, company_code=company, employee=emp_old, policy=annual_policy, as_of=as_of)
            conn.commit()
        check("accrual posted 6 monthly entries", posted == 6)
        bal = app.leave_balances_for_employee(company, emp_key, period_year=2026)
        annual = next((b for b in bal if b["leave_type"] == "annual"), None)
        check("balance row materialized", annual is not None)
        if annual:
            check("accrued = entitlement/12 * 6 months (15.0)", abs(annual["accrued_to_date"] - 15.0) < 0.001)
            check("current balance = 15.0 (no consumption yet)", abs(annual["current_balance"] - 15.0) < 0.001)
        # re-run is idempotent (no new accrual rows, balance unchanged)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                reposted = app.post_leave_accrual_catchup(cur, company_code=company, employee=emp_old, policy=annual_policy, as_of=as_of)
            conn.commit()
        check("accrual re-run posts 0 new entries", reposted == 0)

        # pro-rata for a mid-month hire
        emp_new_key = f"zz_leave_new_{SUFFIX}"
        emp_new = {"employee_key": emp_new_key, "hired_at": date(2026, 6, 16)}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                app.post_leave_accrual_catchup(cur, company_code=company, employee=emp_new, policy=annual_policy, as_of=as_of)
            conn.commit()
        bal_new = next((b for b in app.leave_balances_for_employee(company, emp_new_key, 2026) if b["leave_type"] == "annual"), None)
        # June 16..30 = 15 of 30 days -> 2.5 * 0.5 = 1.25
        check("mid-month hire accrues pro-rata (~1.25)", bal_new is not None and abs(bal_new["accrued_to_date"] - 1.25) < 0.01)

        # --- 5) observe-only consume + reversal ------------------------------
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leave_requests (company_code, employee_key, start_date, end_date, leave_type, status)
                    VALUES (%s,%s,%s,%s,'annual','approved') RETURNING leave_id
                    """,
                    (company, emp_key, "2026-06-01", "2026-06-04"),
                )
                leave_id = dict(cur.fetchone())["leave_id"]
            conn.commit()
        days = app.chargeable_leave_days("2026-06-01", "2026-06-04", weekend_days=["fri", "sat"], holiday_dates=set())
        leave = {"leave_id": leave_id, "employee_key": emp_key, "leave_type": "annual", "start_date": date(2026, 6, 1), "end_date": date(2026, 6, 4)}
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                app.observe_leave_consumption(cur, company_code=company, leave=leave, kind="consume")
                app.observe_leave_consumption(cur, company_code=company, leave=leave, kind="consume")  # idempotent
            conn.commit()
        after_consume = next((b for b in app.leave_balances_for_employee(company, emp_key, 2026) if b["leave_type"] == "annual"), None)
        check("consume lowers balance by exactly chargeable days", after_consume is not None and abs(after_consume["current_balance"] - (15.0 - float(days))) < 0.001)
        check("consume is observe-only (consumed reflects charge once)", after_consume is not None and abs(after_consume["consumed"] - float(days)) < 0.001)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                app.observe_leave_consumption(cur, company_code=company, leave=leave, kind="reversal")
                app.observe_leave_consumption(cur, company_code=company, leave=leave, kind="reversal")  # idempotent
            conn.commit()
        after_reversal = next((b for b in app.leave_balances_for_employee(company, emp_key, 2026) if b["leave_type"] == "annual"), None)
        check("reversal restores the balance to 15.0", after_reversal is not None and abs(after_reversal["current_balance"] - 15.0) < 0.001)
    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM leave_ledger WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM leave_balances WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM leave_requests WHERE company_code=%s", (company,))
                cur.execute("DELETE FROM leave_policies WHERE company_code=%s", (company,))
            conn.commit()
        if orig_flag is None:
            os.environ.pop("WATHEFNI_LEAVE_BALANCES", None)
        else:
            os.environ["WATHEFNI_LEAVE_BALANCES"] = orig_flag

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    LEAVE BALANCES: FAILURES")
        return 1
    print("    LEAVE BALANCES: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
