"""Second-company tenant isolation harness (staging).

Provisions two throwaway companies (A and B) that deliberately share a colliding
employee — same phone AND same name — plus overlapping post-hire records
(attendance, leave, shifts, timesheets). It then exercises the real read and
employee-resolution code paths under each company's active scope and asserts
that nothing ever leaks across the tenant boundary.

Unlike the per-domain smoke tests, this is a *harness*: it records PASS/FAIL for
every check instead of aborting on the first failure, prints a punch-list, and
exits non-zero if any check fails. That makes it the validation gate for the
company_code scoping work (find_employee_by_phone / latest_employee) — those
checks are expected to be RED until that hardening lands, GREEN afterwards.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-tenant-isolation-harness.py

NEVER point this at the production database: it writes and deletes companies.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY_A = "TENANTISOTESTA"
COMPANY_B = "TENANTISOTESTB"
# Same phone + same name in both companies: the worst-case collision a multi-tenant
# read must survive. EMP_KEY is namespaced per company so rows stay distinct.
SHARED_PHONE = "96550000000801"
SHARED_NAME = "Salem Isolationtest"
EMP_KEY_A = f"{SHARED_PHONE}-{COMPANY_A}"
EMP_KEY_B = f"{SHARED_PHONE}-{COMPANY_B}"
# A phone that exists only in company A, used to validate the pre-scope
# phone->company bootstrap (employee_company_code_for_phone).
UNIQUE_PHONE_A = "96550000000811"
EMP_KEY_A_UNIQUE = f"{UNIQUE_PHONE_A}-{COMPANY_A}"
MARKER = "temporary_tenant_isolation_harness"
TODAY = app.kuwait_today()


# --- check runner ----------------------------------------------------------

class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, fn: Callable[[], bool]) -> None:
        try:
            ok = bool(fn())
        except Exception as exc:  # a throwing check is a failed check, never a crash
            self.failed.append(f"{label} -> raised {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        for label in self.passed:
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


# --- provisioning ----------------------------------------------------------

def _employees_columns(cur: Any) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name='employees'"
    )
    return {row["column_name"] for row in cur.fetchall()}


def _insert_employee(cur: Any, columns: set[str], company: str, emp_key: str, phone: str = SHARED_PHONE, name: str = SHARED_NAME) -> None:
    # The employees table is legacy/pre-provisioned; only set columns that exist.
    desired: dict[str, Any] = {
        "company_code": company,
        "phone": phone,
        "name": name,
        "email": f"{emp_key}@example.com",
        "employee_key": emp_key,
        "position_title": "Field Technician",
        "department": "Operations",
        "onboarding_status": "in_progress",
        "status": "active",
        "raw_json": Json({"smoke": MARKER, "name": SHARED_NAME, "onboarding_status": "in_progress"}),
        "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    placeholders = ",".join(["%s"] * len(cols))
    cur.execute(
        f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})",
        [desired[c] for c in cols],
    )


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company, name in ((COMPANY_A, "Isolation Harness A"), (COMPANY_B, "Isolation Harness B")):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, name, Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
            # Clean slate for the post-hire + employee rows we own.
            _purge(cur)
            columns = _employees_columns(cur)
            _insert_employee(cur, columns, COMPANY_A, EMP_KEY_A)
            _insert_employee(cur, columns, COMPANY_B, EMP_KEY_B)
            _insert_employee(cur, columns, COMPANY_A, EMP_KEY_A_UNIQUE, phone=UNIQUE_PHONE_A, name="Unique Companya")
            for company, emp_key in ((COMPANY_A, EMP_KEY_A), (COMPANY_B, EMP_KEY_B)):
                cur.execute(
                    "INSERT INTO shift_assignments (company_code, employee_key, employee_phone, employee_name, "
                    "shift_date, start_time, end_time, status, metadata) "
                    "VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled',%s)",
                    (company, emp_key, SHARED_PHONE, SHARED_NAME, TODAY, Json({"smoke": MARKER})),
                )
                cur.execute(
                    "INSERT INTO attendance_records (company_code, employee_key, employee_phone, employee_name, "
                    "attendance_date, scheduled_start, scheduled_end, status, late_minutes, metadata) "
                    "VALUES (%s,%s,%s,%s,%s,'09:00','17:00','present',0,%s)",
                    (company, emp_key, SHARED_PHONE, SHARED_NAME, TODAY, Json({"smoke": MARKER})),
                )
                cur.execute(
                    "INSERT INTO leave_requests (company_code, employee_key, employee_phone, employee_name, "
                    "start_date, end_date, leave_type, status, metadata) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'time_off','requested',%s)",
                    (company, emp_key, SHARED_PHONE, SHARED_NAME, TODAY, TODAY, Json({"smoke": MARKER})),
                )
                cur.execute(
                    "INSERT INTO payroll_timesheets (company_code, employee_key, employee_phone, employee_name, "
                    "period_start, period_end, status, scheduled_minutes, worked_minutes, snapshot) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'draft',480,480,%s)",
                    (company, emp_key, SHARED_PHONE, SHARED_NAME, TODAY, TODAY, Json({"smoke": MARKER})),
                )
        conn.commit()


def _purge(cur: Any) -> None:
    companies = [COMPANY_A, COMPANY_B]
    for table in (
        "attendance_records",
        "leave_requests",
        "shift_assignments",
        "payroll_timesheets",
    ):
        cur.execute(f"DELETE FROM {table} WHERE company_code = ANY(%s)", (companies,))
    cur.execute("DELETE FROM employees WHERE company_code = ANY(%s)", (companies,))


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _purge(cur)
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


# --- checks ----------------------------------------------------------------

def _company_codes(rows: list[dict[str, Any]]) -> set[str]:
    return {str(r.get("company_code") or "").upper() for r in rows if isinstance(r, dict)}


def run_checks(checks: Checks) -> None:
    # 1) Directory + post-hire reads are explicitly company-scoped (the endpoints
    #    always pass company_code). Each company sees only its own rows.
    for company, other in ((COMPANY_A, COMPANY_B), (COMPANY_B, COMPANY_A)):
        token = app.set_active_company_code(company)
        try:
            emps = app.company_employees(company)
            checks.check(
                f"company_employees({company}) returns only {company}",
                lambda emps=emps, company=company, other=other: _company_codes(emps) <= {company} and other not in _company_codes(emps),
            )

            att = app.list_attendance({"company_code": company, "start_date": TODAY.isoformat(), "end_date": TODAY.isoformat()}, company_code=company)
            checks.check(
                f"list_attendance({company}) excludes {other}",
                lambda att=att, other=other: other not in _company_codes(att.get("attendance") or []),
            )

            lv = app.list_leave_requests({"company_code": company, "status": "requested"}, company_code=company)
            checks.check(
                f"list_leave_requests({company}) excludes {other}",
                lambda lv=lv, other=other: other not in _company_codes(lv.get("leave_requests") or []),
            )

            sh = app.list_shifts({"company_code": company, "start_date": TODAY.isoformat(), "end_date": TODAY.isoformat()}, company_code=company)
            checks.check(
                f"list_shifts({company}) excludes {other}",
                lambda sh=sh, other=other: other not in _company_codes(sh.get("shifts") or []),
            )

            ts = app.list_timesheets({"company_code": company}, company_code=company)
            checks.check(
                f"list_timesheets({company}) excludes {other}",
                lambda ts=ts, other=other: other not in _company_codes(ts.get("timesheets") or []),
            )
        finally:
            app.reset_active_company_code(token)

    # 2) Employee resolution helpers must honour the active company on a phone
    #    collision. These are the audit-flagged risk points.
    for company in (COMPANY_A, COMPANY_B):
        token = app.set_active_company_code(company)
        try:
            by_phone = app.find_employee_by_phone(SHARED_PHONE)
            checks.check(
                f"find_employee_by_phone under {company} resolves {company}'s employee",
                lambda by_phone=by_phone, company=company: bool(by_phone) and str(by_phone.get("company_code")).upper() == company,
            )

            by_name = app.find_employee_by_name(SHARED_NAME, company_code=company)
            checks.check(
                f"find_employee_by_name under {company} resolves {company}'s employee",
                lambda by_name=by_name, company=company: bool(by_name) and str(by_name.get("company_code")).upper() == company,
            )

            latest = app.latest_employee()
            checks.check(
                f"latest_employee under {company} stays within {company}",
                lambda latest=latest, company=company: bool(latest) and str(latest.get("company_code")).upper() == company,
            )

            resolved = app.resolve_employee_for_direct_action({"subject_phone": SHARED_PHONE}, allow_latest=True)
            checks.check(
                f"resolve_employee_for_direct_action(phone) under {company} resolves {company}",
                lambda resolved=resolved, company=company: bool(resolved) and str(resolved.get("company_code")).upper() == company,
            )
        finally:
            app.reset_active_company_code(token)

    # 3) Fail closed: with no active company and no explicit scope, phone-based
    #    resolution must not reach across every company.
    checks.check("no active company is set for fail-closed checks", lambda: app.active_company_code() is None)
    checks.check(
        "find_employee_by_name fails closed without company scope",
        lambda: app.find_employee_by_name(SHARED_NAME) is None,
    )
    checks.check(
        "find_employee_by_phone fails closed without company scope",
        lambda: app.find_employee_by_phone(SHARED_PHONE) is None,
    )
    checks.check(
        "latest_employee fails closed without company scope",
        lambda: app.latest_employee() is None,
    )

    # 4) Pre-scope bootstrap: phone->company resolution is intentionally
    #    cross-company (no active scope) and must still resolve correctly so
    #    employee self-service routes to the right tenant.
    checks.check(
        "employee_company_code_for_phone resolves a company-unique phone to its company",
        lambda: app.employee_company_code_for_phone(UNIQUE_PHONE_A) == COMPANY_A,
    )
    checks.check(
        "employee_company_code_for_phone resolves a shared phone to a real owning company",
        lambda: app.employee_company_code_for_phone(SHARED_PHONE) in {COMPANY_A, COMPANY_B},
    )


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"tenant isolation harness — companies {COMPANY_A} / {COMPANY_B} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nTENANT ISOLATION HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nTENANT ISOLATION HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
