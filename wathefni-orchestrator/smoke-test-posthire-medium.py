"""Post-hire medium-severity fixes smoke test (staging).

Covers the batched medium fixes from the post-hire audit:

1. Payroll "capped" overtime actually caps pay.
   Before: overtime_policy='capped' only added a flag; every overtime minute was
   still paid. Now payable_minutes drops by the excess (overtime - cap).

2. Attendance dashboard pages instead of silently truncating.
   list_attendance now returns total_count/has_more and honours limit/offset, so
   a busy window (>1000 records) is fully reachable, company-scoped, no dup/gap.

3. Payroll "N timesheets need review" banner is a true count.
   list_timesheets returns draft_count over the WHOLE period, not the loaded page.

4. Shift-swap review queue isn't truncated at 20.
   list_shift_swaps honours a caller limit (dashboard passes 200) so the pending
   queue + its banner count aren't capped at 20; the default stays 20 for brevity.

5. Employee 360 upcoming-shift count is a true aggregate (not len of a LIMIT 10
   preview).

Run on a host with the orchestrator venv + (staging) database:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-posthire-medium.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY_A = "PHMEDIUMA"  # subject
COMPANY_B = "PHMEDIUMB"  # cross-tenant control
MARKER = "temporary_posthire_medium_smoke"

STATE: dict[str, Any] = {}


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"      PASS  {label}")
        for label in self.failed:
            print(f"      FAIL  {label}")
        print(f"\n    {len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    cur.execute("DELETE FROM shift_swap_requests WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM attendance_records WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM shift_assignments WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM payroll_timesheets WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM employees WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,))


ATT_COUNT_A = 25
SWAP_COUNT_A = 25
FUTURE_SHIFTS_A = 12
DRAFT_A = 5
APPROVED_A = 2


def setup() -> None:
    today = app.kuwait_today()
    STATE["today"] = today
    period_start = today.replace(day=1)
    period_end = today
    STATE["period"] = (period_start, period_end)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Posthire Medium {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                for module in ("attendance", "shifts", "payroll", "leave"):
                    cur.execute(
                        "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                        "VALUES (%s,%s,TRUE,'smoke',now()) "
                        "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                        (company, module),
                    )
                cur.execute(
                    "INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,now(),now()) ON CONFLICT (employee_key) DO NOTHING",
                    (company, f"{company}-emp0", f"{company} Worker", f"9650000{company[-1]}00", Json({"smoke": MARKER})),
                )

            # (2) 25 attendance records for A within the last two weeks; 1 for B.
            for i in range(ATT_COUNT_A):
                cur.execute(
                    """
                    INSERT INTO attendance_records (company_code, employee_key, employee_name, attendance_date, status)
                    VALUES (%s,%s,%s,%s,'present')
                    """,
                    (COMPANY_A, f"{COMPANY_A}-att{i}", f"Att {i}", today - timedelta(days=i % 13)),
                )
            cur.execute(
                "INSERT INTO attendance_records (company_code, employee_key, employee_name, attendance_date, status) VALUES (%s,%s,%s,%s,'present')",
                (COMPANY_B, f"{COMPANY_B}-att0", "B Att", today),
            )

            # (3) 5 draft + 2 approved timesheets for A in one period.
            for i in range(DRAFT_A):
                cur.execute(
                    "INSERT INTO payroll_timesheets (company_code, employee_key, employee_name, period_start, period_end, status) VALUES (%s,%s,%s,%s,%s,'draft')",
                    (COMPANY_A, f"{COMPANY_A}-ts-d{i}", f"Draft {i}", period_start, period_end),
                )
            for i in range(APPROVED_A):
                cur.execute(
                    "INSERT INTO payroll_timesheets (company_code, employee_key, employee_name, period_start, period_end, status) VALUES (%s,%s,%s,%s,%s,'approved')",
                    (COMPANY_A, f"{COMPANY_A}-ts-a{i}", f"Approved {i}", period_start, period_end),
                )

            # (4) 25 requested shift swaps for A.
            for i in range(SWAP_COUNT_A):
                cur.execute(
                    """
                    INSERT INTO shift_swap_requests (company_code, requester_employee_key, requester_employee_name, shift_date, status)
                    VALUES (%s,%s,%s,%s,'requested')
                    """,
                    (COMPANY_A, f"{COMPANY_A}-swapemp{i}", f"Swap {i}", today + timedelta(days=1 + (i % 5))),
                )

            # (5) 12 future shifts for A's emp0.
            for i in range(FUTURE_SHIFTS_A):
                cur.execute(
                    """
                    INSERT INTO shift_assignments (company_code, employee_key, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (COMPANY_A, f"{COMPANY_A}-emp0", f"{COMPANY_A} Worker", today + timedelta(days=1 + i)),
                )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def run_overtime_cap_checks(checks: Checks) -> None:
    # 10h worked, 8h scheduled -> 2h (120m) overtime; cap at 1h (60m). The excess
    # 60m must be removed from payable; only 9h (540m) is payable.
    row = {"worked_minutes": 600, "scheduled_minutes": 480, "overtime_minutes": 120, "approved_leave_minutes": 0, "absent_minutes": 0, "late_minutes": 0, "early_leave_minutes": 0}
    capped_policy = {"overtime_policy": "capped", "overtime_cap_minutes": 60, "leave_policy": "review_only"}
    paid_policy = {"overtime_policy": "paid", "leave_policy": "review_only"}
    capped = app.payroll_preview_from_timesheet(row, capped_policy)
    paid = app.payroll_preview_from_timesheet(row, paid_policy)
    checks.check("capped policy removes the excess overtime from payable", lambda: capped["payable_minutes"] == 540)
    checks.check("capped policy reports the capped excess (60m)", lambda: capped["overtime_capped_minutes"] == 60)
    checks.check("capped policy flags overtime_capped", lambda: "overtime_capped" in capped["policy_flags"])
    checks.check("uncapped 'paid' policy still pays all worked minutes", lambda: paid["payable_minutes"] == 600)


def _page_attendance_ids(company: str, *, limit: int) -> tuple[list[str], int]:
    today = STATE["today"]
    seen: list[str] = []
    offset = 0
    total = 0
    for _ in range(1000):
        res = app.list_attendance(
            {"company_code": company, "start_date": (today - timedelta(days=20)).isoformat(), "end_date": today.isoformat(), "limit": limit, "offset": offset},
            company_code=company,
        )
        total = int(res.get("total_count") or 0)
        rows = res.get("attendance") or []
        seen.extend(str(r.get("attendance_id")) for r in rows)
        if not rows or (offset + len(rows)) >= total:
            break
        offset += len(rows)
    return seen, total


def run_attendance_pagination_checks(checks: Checks) -> None:
    today = STATE["today"]
    page = app.list_attendance(
        {"company_code": COMPANY_A, "start_date": (today - timedelta(days=20)).isoformat(), "end_date": today.isoformat(), "limit": 10, "offset": 0},
        company_code=COMPANY_A,
    )
    checks.check("attendance page caps at limit=10", lambda: len(page.get("attendance") or []) == 10)
    checks.check("attendance total_count is the true count (25)", lambda: page.get("total_count") == ATT_COUNT_A)
    checks.check("attendance has_more true when truncated", lambda: page.get("has_more") is True)

    seen, total = _page_attendance_ids(COMPANY_A, limit=7)
    checks.check("attendance paging total == true count", lambda: total == ATT_COUNT_A)
    checks.check("attendance paging visits every record once, no dup/gap", lambda: len(seen) == ATT_COUNT_A and len(set(seen)) == ATT_COUNT_A)

    b = app.list_attendance(
        {"company_code": COMPANY_B, "start_date": (today - timedelta(days=20)).isoformat(), "end_date": today.isoformat(), "limit": 50},
        company_code=COMPANY_B,
    )
    checks.check("attendance is tenant-scoped (B sees only its 1 record)", lambda: b.get("total_count") == 1)


def run_payroll_draft_count_checks(checks: Checks) -> None:
    start, end = STATE["period"]
    res = app.list_timesheets(
        {"company_code": COMPANY_A, "start_date": start.isoformat(), "end_date": end.isoformat(), "limit": 2, "offset": 0},
        company_code=COMPANY_A,
    )
    checks.check("timesheet page caps at limit=2", lambda: len(res.get("timesheets") or []) == 2)
    checks.check("timesheet total_count == 7 (5 draft + 2 approved)", lambda: res.get("total_count") == DRAFT_A + APPROVED_A)
    checks.check("draft_count is a TRUE period count (5), not the loaded page", lambda: res.get("draft_count") == DRAFT_A)


def run_shift_swap_checks(checks: Checks) -> None:
    default = app.list_shift_swaps({"company_code": COMPANY_A, "status": "requested"}, company_code=COMPANY_A)
    dashboard = app.list_shift_swaps({"company_code": COMPANY_A, "status": "requested", "limit": 200}, company_code=COMPANY_A)
    checks.check("shift-swap default stays brief (<=20 for WhatsApp)", lambda: len(default.get("swaps") or []) == 20)
    checks.check("shift-swap dashboard limit surfaces the whole pending queue (25)", lambda: len(dashboard.get("swaps") or []) == SWAP_COUNT_A)


def run_emp360_shift_count_checks(checks: Checks) -> None:
    ctx = {
        "company_code": COMPANY_A,
        "hr_phone": None,
        "permissions": ["employees.read", "shifts.read"],
        "access": {"role": "owner", "permissions": ["employees.read", "shifts.read"]},
        "actor_user_id": "smoke-medium",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "smoke-medium",
        "permission_subject_company": COMPANY_A,
        "actor_role": "owner",
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY_A},
    }
    profile = app.dashboard_employee_profile(ctx, f"{COMPANY_A}-emp0")
    shifts_section = (profile.get("sections") or {}).get("shifts") or {}
    checks.check("employee 360 upcoming_count is a TRUE count (12), not capped at 10", lambda: shifts_section.get("upcoming_count") == FUTURE_SHIFTS_A)
    checks.check("employee 360 upcoming shift preview stays capped at 10", lambda: len(shifts_section.get("items") or []) <= 10)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"post-hire medium smoke — companies {COMPANY_A}/{COMPANY_B} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_overtime_cap_checks(checks)
        run_attendance_pagination_checks(checks)
        run_payroll_draft_count_checks(checks)
        run_shift_swap_checks(checks)
        run_emp360_shift_count_checks(checks)
    finally:
        teardown()
    code = checks.report()
    print("    POSTHIRE MEDIUM: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
