"""Post-hire high-severity fixes smoke test (staging).

Covers the high-severity issues found in the post-hire module audit:

1. Leave mutations are tenant-scoped.
   Before: approve/reject/cancel resolved a leave request by leave_id alone, so
   a guessed/leaked UUID from another company could be acted on cross-tenant.
   Now: leave_request_by_id + resolve_leave_request are company-scoped, and the
   UPDATE carries `AND company_code=%s` as defense-in-depth.

2. Leave's pending queue no longer hides requests by date window.
   Before: the pending/awaiting-decision queue applied the ~31-day active date
   window, so a request whose leave dates fell outside it silently vanished from
   the approval queue. Now: status='requested' ignores the date window entirely
   (a pending decision doesn't depend on when the leave falls), while the
   approved/upcoming view still honours the window.

3. Timesheet approve/reject is tenant-scoped.
   Same class as (1) but on the money path: timesheet_by_id + resolve_timesheets
   are company-scoped and the UPDATE carries `AND company_code=%s`.

4. Employee 360's "leave pending" count is a true aggregate.
   Before: it was len() of a LIMIT 10 preview, so an employee with >10 pending
   requests was undercounted. Now: a COUNT(*) drives both the section count and
   the "awaiting a decision" next-action label.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-posthire-highsev.py

NEVER point this at the production database: it writes and deletes test companies.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY_A = "PHHIGHSEVA"  # subject
COMPANY_B = "PHHIGHSEVB"  # cross-tenant control
MARKER = "temporary_posthire_highsev_smoke"


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


# --- seeded ids (populated in setup) ---------------------------------------
STATE: dict[str, Any] = {}


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    cur.execute("DELETE FROM leave_events WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM leave_requests WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM payroll_timesheets WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM employees WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", (companies,))


def setup() -> None:
    today = app.kuwait_today()
    far_future_start = today + timedelta(days=300)
    far_future_end = today + timedelta(days=305)
    STATE["today"] = today
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Posthire HighSev {company[-1]}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
                for module in ("leave", "payroll"):
                    cur.execute(
                        "INSERT INTO company_modules (company_code, module_key, enabled, source, updated_at) "
                        "VALUES (%s,%s,TRUE,'smoke',now()) "
                        "ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE",
                        (company, module),
                    )

            # An employee in each company (needed for the Employee 360 profile).
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,%s,now(),now()) ON CONFLICT (employee_key) DO NOTHING",
                    (company, f"{company}-emp0", f"{company} Worker", f"9650000{company[-1]}00", Json({"smoke": MARKER})),
                )

            # (1)+(3) cross-tenant: a requested leave + a draft timesheet in B.
            cur.execute(
                """
                INSERT INTO leave_requests (company_code, employee_key, employee_name, start_date, end_date, leave_type, status, reason)
                VALUES (%s,%s,%s,%s,%s,'annual','requested',%s)
                RETURNING leave_id
                """,
                (COMPANY_B, f"{COMPANY_B}-emp0", "B Worker", today + timedelta(days=2), today + timedelta(days=4), MARKER),
            )
            STATE["b_leave_id"] = str(cur.fetchone()["leave_id"])

            cur.execute(
                """
                INSERT INTO payroll_timesheets (company_code, employee_key, employee_name, period_start, period_end, status)
                VALUES (%s,%s,%s,%s,%s,'draft')
                RETURNING timesheet_id
                """,
                (COMPANY_B, f"{COMPANY_B}-emp0", "B Worker", today.replace(day=1), today, ),
            )
            STATE["b_timesheet_id"] = str(cur.fetchone()["timesheet_id"])

            # (2) A pending request whose dates fall FAR outside the active window,
            # and an approved request equally far out (the window control).
            cur.execute(
                """
                INSERT INTO leave_requests (company_code, employee_key, employee_name, start_date, end_date, leave_type, status, reason)
                VALUES (%s,%s,%s,%s,%s,'annual','requested',%s)
                RETURNING leave_id
                """,
                (COMPANY_A, f"{COMPANY_A}-farpending", "Far Pending", far_future_start, far_future_end, MARKER),
            )
            STATE["a_far_pending_id"] = str(cur.fetchone()["leave_id"])
            cur.execute(
                """
                INSERT INTO leave_requests (company_code, employee_key, employee_name, start_date, end_date, leave_type, status, reason)
                VALUES (%s,%s,%s,%s,%s,'annual','approved',%s)
                """,
                (COMPANY_A, f"{COMPANY_A}-farapproved", "Far Approved", far_future_start, far_future_end, MARKER),
            )

            # (4) 12 pending requests for a single Company A employee (> LIMIT 10 preview).
            for i in range(12):
                cur.execute(
                    """
                    INSERT INTO leave_requests (company_code, employee_key, employee_name, start_date, end_date, leave_type, status, reason)
                    VALUES (%s,%s,%s,%s,%s,'annual','requested',%s)
                    """,
                    (
                        COMPANY_A,
                        f"{COMPANY_A}-emp0",
                        f"{COMPANY_A} Worker",
                        today + timedelta(days=10 + i),
                        today + timedelta(days=11 + i),
                        MARKER,
                    ),
                )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def run_leave_tenant_checks(checks: Checks) -> None:
    b_id = STATE["b_leave_id"]

    # resolve-level: a B leave never resolves under A, always resolves under B.
    checks.check(
        "leave resolve: B request is invisible to company A",
        lambda: app.resolve_leave_request({"leave_id": b_id}, company_code=COMPANY_A, statuses=("requested",)) is None,
    )
    checks.check(
        "leave resolve: B request resolves under company B",
        lambda: (app.resolve_leave_request({"leave_id": b_id}, company_code=COMPANY_B, statuses=("requested",)) or {}).get("leave_id") == b_id,
    )

    # end-to-end mutations: cross-tenant approve/reject/cancel must not find it.
    for verb, fn in (
        ("approve", app.approve_leave_request),
        ("reject", app.reject_leave_request),
        ("cancel", app.cancel_leave_request),
    ):
        checks.check(
            f"leave {verb}: cross-tenant returns leave_request_not_found",
            lambda fn=fn: fn({"leave_id": b_id}, company_code=COMPANY_A, created_by_phone="96599999999").get("error") == "leave_request_not_found",
        )

    # same-tenant approve still works (proves the company_code UPDATE guard is correct).
    res = app.approve_leave_request({"leave_id": b_id}, company_code=COMPANY_B, created_by_phone="96588888888")
    checks.check("leave approve: same-tenant approval succeeds", lambda: res.get("ok") is True)
    checks.check("leave approve: row is now approved", lambda: (res.get("leave") or {}).get("status") == "approved")


def run_leave_window_checks(checks: Checks) -> None:
    today = STATE["today"]
    # A narrow active window that does NOT contain the far-future requests.
    narrow = {"start_date": today.isoformat(), "end_date": (today + timedelta(days=7)).isoformat()}

    pending = app.list_leave_requests({"company_code": COMPANY_A, "status": "requested", **narrow, "limit": 500}, company_code=COMPANY_A)
    pending_ids = {str(r.get("leave_id")) for r in (pending.get("leave_requests") or [])}
    checks.check(
        "leave pending queue includes a far-future request (window no longer hides it)",
        lambda: STATE["a_far_pending_id"] in pending_ids,
    )

    approved = app.list_leave_requests({"company_code": COMPANY_A, "status": "approved", **narrow, "limit": 500}, company_code=COMPANY_A)
    approved_names = {str(r.get("employee_name")) for r in (approved.get("leave_requests") or [])}
    checks.check(
        "leave approved/upcoming view STILL honours the date window",
        lambda: "Far Approved" not in approved_names,
    )


def run_timesheet_tenant_checks(checks: Checks) -> None:
    b_id = STATE["b_timesheet_id"]
    checks.check(
        "timesheet resolve: B timesheet invisible to company A",
        lambda: app.resolve_timesheets({"timesheet_id": b_id}, company_code=COMPANY_A, statuses=("draft",)) == [],
    )
    checks.check(
        "timesheet resolve: B timesheet resolves under company B",
        lambda: [t.get("timesheet_id") for t in app.resolve_timesheets({"timesheet_id": b_id}, company_code=COMPANY_B, statuses=("draft",))] == [b_id],
    )
    checks.check(
        "timesheet approve: cross-tenant returns timesheet_not_found",
        lambda: app.approve_timesheet({"timesheet_id": b_id}, company_code=COMPANY_A, created_by_phone="96599999999").get("error") == "timesheet_not_found",
    )
    checks.check(
        "timesheet reject: cross-tenant returns timesheet_not_found",
        lambda: app.reject_timesheet({"timesheet_id": b_id}, company_code=COMPANY_A, created_by_phone="96599999999").get("error") == "timesheet_not_found",
    )
    res = app.approve_timesheet({"timesheet_id": b_id}, company_code=COMPANY_B, created_by_phone="96588888888")
    checks.check("timesheet approve: same-tenant approval succeeds", lambda: res.get("ok") is True and res.get("count") == 1)


def run_emp360_count_checks(checks: Checks) -> None:
    ctx = {
        "company_code": COMPANY_A,
        "hr_phone": None,
        "permissions": ["employees.read", "leave.read", "payroll.read"],
        "access": {"role": "owner", "permissions": ["employees.read", "leave.read", "payroll.read"]},
        "actor_user_id": "smoke-highsev",
        "permission_authority": "backend_current",
        "permission_subject_user_id": "smoke-highsev",
        "permission_subject_company": COMPANY_A,
        "actor_role": "owner",
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY_A},
    }
    profile = app.dashboard_employee_profile(ctx, f"{COMPANY_A}-emp0")
    leave_section = (profile.get("sections") or {}).get("leave") or {}
    checks.check(
        "employee 360 leave pending_count is a TRUE count (12), not capped at 10",
        lambda: leave_section.get("pending_count") == 12,
    )
    checks.check(
        "employee 360 leave items preview is still capped at 10",
        lambda: len(leave_section.get("items") or []) <= 10,
    )
    next_actions = profile.get("next_actions") or []
    leave_action = next((a for a in next_actions if a.get("module") == "leave"), None)
    checks.check(
        "employee 360 leave next-action label uses the true count (12)",
        lambda: leave_action is not None and "12 leave request" in str(leave_action.get("label")),
    )


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"post-hire high-severity smoke — companies {COMPANY_A}/{COMPANY_B} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_leave_tenant_checks(checks)
        run_leave_window_checks(checks)
        run_timesheet_tenant_checks(checks)
        run_emp360_count_checks(checks)
    finally:
        teardown()
    code = checks.report()
    print("    POSTHIRE HIGH-SEV: " + ("ALL CHECKS PASSED" if not code else "FAILURES PRESENT"))
    sys.exit(code)


if __name__ == "__main__":
    main()
