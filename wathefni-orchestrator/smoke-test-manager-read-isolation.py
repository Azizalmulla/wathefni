"""Manager-scoped READ isolation harness (staging).

Manager scoping was already enforced on *decisions* (approve leave, mark absent,
…). This pins the matching guarantee on *reads*: a scoped manager hitting the
post-hire list/detail endpoints must only ever see their own people, while HR
(no scope) still sees the whole company.

It provisions one throwaway company with two teams + three employees, grants a
team manager and a direct manager, then drives the real dashboard read endpoints
(employees / onboarding list + detail / compliance payload / employee 360) with
each viewer and asserts the visible employee set.

Reuses the SAME resolver (manager_scope_employee_keys / manager_scope_context /
manager_scope_allows_employee) the decision gates use, so a green run means the
read path and the decision path agree on who a manager may see.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-manager-read-isolation.py

NEVER point this at the production database: it writes and deletes a company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

try:
    import app
    from psycopg2.extras import Json
except ModuleNotFoundError as exc:
    if exc.name in {"psycopg2", "app"} or (exc.name or "").startswith("psycopg2"):
        print("SKIP: psycopg2 not available locally; full run happens on staging.")
        sys.exit(0)
    raise

COMPANY = "MGRREADTESTCO"
MARKER = "temporary_manager_read_harness"

EMP_A = f"mgrread-emp-a-{COMPANY}"
EMP_B = f"mgrread-emp-b-{COMPANY}"
EMP_C = f"mgrread-emp-c-{COMPANY}"
PHONE_A = "96550000000801"
PHONE_B = "96550000000802"
PHONE_C = "96550000000803"

BRANCH_KEY = app.org_key(COMPANY, "branch", "HQ")
TEAM_A_KEY = app.org_key(COMPANY, "team", "Team A")
TEAM_B_KEY = app.org_key(COMPANY, "team", "Team B")

MGR_TEAM_PHONE = "96550000000810"    # manages Team A (team scope) -> sees EMP_A
MGR_DIRECT_PHONE = "96550000000811"  # manages EMP_C only (direct scope)
HR_PHONE = "96550000000812"          # no scope -> sees everyone

MODULES = ["onboarding", "compliance", "attendance", "leave", "payroll", "shifts"]


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
            print(f"  PASS  {label}")
        for label in self.failed:
            print(f"  FAIL  {label}")
        print(f"\n{len(self.passed)} passed, {len(self.failed)} failed")
        return 1 if self.failed else 0


def _ctx(viewer_phone: str | None) -> dict[str, Any]:
    # Owner identity so the strict require_entitlement reads (onboarding) pass on
    # role; the manager scope being exercised is carried purely by hr_phone, which
    # is what every post-hire read now threads through to the scope resolver.
    return {
        "company_code": COMPANY,
        "permissions": [],
        "hr_phone": viewer_phone,
        "access": {"role": "owner", "permissions": []},
        "actor_role": "owner",
        "actor_user_id": "smoke-mgr-read",
        "hr_user": {"role": "owner", "status": "active", "company_code": COMPANY},
    }


def _employees_columns(cur: Any) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employees'")
    return {row["column_name"] for row in cur.fetchall()}


def _insert_employee(cur: Any, columns: set[str], emp_key: str, phone: str, name: str) -> None:
    desired: dict[str, Any] = {
        "company_code": COMPANY,
        "phone": phone,
        "name": name,
        "email": f"{emp_key}@example.com",
        "employee_key": emp_key,
        "position_title": "Field Technician",
        "department": "Operations",
        "onboarding_status": "in_progress",
        "status": "active",
        "raw_json": Json({"smoke": MARKER, "name": name}),
        "profile": Json({"smoke": MARKER}),
    }
    cols = [c for c in desired if c in columns]
    placeholders = ",".join(["%s"] * len(cols))
    cur.execute(f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})", [desired[c] for c in cols])


def setup() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO UPDATE SET metadata=EXCLUDED.metadata",
                (COMPANY, "Manager Read Harness", Json({"smoke": MARKER, "modules": MODULES}), Json({"smoke": MARKER})),
            )
            columns = _employees_columns(cur)
            _insert_employee(cur, columns, EMP_A, PHONE_A, "Ahmed Teama")
            _insert_employee(cur, columns, EMP_B, PHONE_B, "Badr Teamb")
            _insert_employee(cur, columns, EMP_C, PHONE_C, "Cawthar Direct")
        conn.commit()

    app.os.environ["WATHEFNI_ORG_HIERARCHY"] = "on"
    assert app.upsert_org_branch(COMPANY, name="HQ", branch_key=BRANCH_KEY)["ok"], "branch create"
    assert app.upsert_org_team(COMPANY, name="Team A", branch_key=BRANCH_KEY, team_key=TEAM_A_KEY)["ok"], "team A create"
    assert app.upsert_org_team(COMPANY, name="Team B", branch_key=BRANCH_KEY, team_key=TEAM_B_KEY)["ok"], "team B create"
    assert app.set_employee_org_assignment(COMPANY, employee_key=EMP_A, team_key=TEAM_A_KEY)["ok"], "assign A"
    assert app.set_employee_org_assignment(COMPANY, employee_key=EMP_B, team_key=TEAM_B_KEY)["ok"], "assign B"
    assert app.upsert_manager_scope(COMPANY, manager_phone=MGR_TEAM_PHONE, scope_type="team", team_key=TEAM_A_KEY)["ok"], "team scope"
    assert app.upsert_manager_scope(COMPANY, manager_phone=MGR_DIRECT_PHONE, scope_type="direct", employee_keys=[EMP_C])["ok"], "direct scope"


def _purge() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM manager_scope_members WHERE scope_id IN (SELECT scope_id FROM manager_scopes WHERE company_code=%s)",
                (COMPANY,),
            )
            for table in ("manager_scopes", "employee_org_assignments", "company_teams", "company_branches", "onboarding_items"):
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
                except Exception:
                    conn.rollback()
            cur.execute("DELETE FROM employees WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,))
        conn.commit()


def teardown() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()
    app.os.environ.pop("WATHEFNI_ORG_HIERARCHY", None)


def _employees_seen(viewer_phone: str | None) -> set[str]:
    res = app.dashboard_posthire_employees(_ctx(viewer_phone))
    return {str(e.get("employee_key")) for e in (res.get("employees") or [])}


def _onboarding_seen(viewer_phone: str | None) -> set[str]:
    res = app.dashboard_posthire_onboarding(_ctx(viewer_phone))
    return {str(e.get("employee_key")) for e in (res.get("in_progress") or [])}


def _compliance_employees_total(viewer_phone: str | None) -> int:
    res = app.dashboard_compliance_payload(COMPANY, viewer_phone=viewer_phone)
    return int((res.get("summary") or {}).get("employees_total") or 0)


def _profile_resolves(viewer_phone: str | None, emp_key: str) -> bool:
    try:
        app.dashboard_employee_profile(_ctx(viewer_phone), emp_key)
        return True
    except app.HTTPException:
        return False


def _onboarding_detail_resolves(viewer_phone: str | None, emp_key: str) -> bool:
    try:
        app.dashboard_posthire_onboarding_detail(emp_key, _ctx(viewer_phone))
        return True
    except app.HTTPException:
        return False


def run_checks(checks: Checks) -> None:
    # --- Employees directory list -------------------------------------------
    checks.check("HR sees all 3 employees", lambda: _employees_seen(HR_PHONE) == {EMP_A, EMP_B, EMP_C})
    checks.check("no-viewer (server context) sees all 3", lambda: _employees_seen(None) == {EMP_A, EMP_B, EMP_C})
    checks.check("team mgr employees = only team A", lambda: _employees_seen(MGR_TEAM_PHONE) == {EMP_A})
    checks.check("direct mgr employees = only direct member", lambda: _employees_seen(MGR_DIRECT_PHONE) == {EMP_C})

    # --- Onboarding list -----------------------------------------------------
    checks.check("HR onboarding = all 3", lambda: _onboarding_seen(HR_PHONE) == {EMP_A, EMP_B, EMP_C})
    checks.check("team mgr onboarding = only team A", lambda: _onboarding_seen(MGR_TEAM_PHONE) == {EMP_A})
    checks.check("direct mgr onboarding = only direct member", lambda: _onboarding_seen(MGR_DIRECT_PHONE) == {EMP_C})

    # --- Compliance payload (employees_total reflects scope) -----------------
    checks.check("HR compliance covers all 3", lambda: _compliance_employees_total(HR_PHONE) == 3)
    checks.check("team mgr compliance covers only its 1", lambda: _compliance_employees_total(MGR_TEAM_PHONE) == 1)
    checks.check("direct mgr compliance covers only its 1", lambda: _compliance_employees_total(MGR_DIRECT_PHONE) == 1)

    # --- Employee 360 profile guard -----------------------------------------
    checks.check("HR can open any profile", lambda: _profile_resolves(HR_PHONE, EMP_B) is True)
    checks.check("team mgr can open in-scope profile", lambda: _profile_resolves(MGR_TEAM_PHONE, EMP_A) is True)
    checks.check("team mgr CANNOT open out-of-scope profile (404)", lambda: _profile_resolves(MGR_TEAM_PHONE, EMP_B) is False)
    checks.check("direct mgr CANNOT open non-member profile (404)", lambda: _profile_resolves(MGR_DIRECT_PHONE, EMP_A) is False)

    # --- Onboarding detail guard --------------------------------------------
    checks.check("team mgr can open in-scope onboarding detail", lambda: _onboarding_detail_resolves(MGR_TEAM_PHONE, EMP_A) is True)
    checks.check("team mgr CANNOT open out-of-scope onboarding detail (404)", lambda: _onboarding_detail_resolves(MGR_TEAM_PHONE, EMP_B) is False)


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"manager read-isolation harness — company {COMPANY} (env: {env or 'default'})")
    try:
        import psycopg2  # noqa: F401
    except ModuleNotFoundError:
        print("SKIP: psycopg2 not available locally; full run happens on staging.")
        sys.exit(0)
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nMANAGER READ-ISOLATION: FAILURES PRESENT")
    else:
        print("\nMANAGER READ-ISOLATION: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
