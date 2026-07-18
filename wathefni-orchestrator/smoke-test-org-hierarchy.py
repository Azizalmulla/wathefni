"""Manager / org-hierarchy V1a isolation harness (staging).

Provisions one throwaway company with two teams and three employees, then grants
two kinds of manager scope and asserts that each manager can only see / decide on
their own people — while HR (no scope) still sees the whole company. Also proves
the WATHEFNI_ORG_HIERARCHY flag gates the new "direct" scope, and that the new
'manager' role carries approve-capable but not company-admin permissions.

This exercises the SAME resolver (manager_scope_context / employee_scope_sql /
manager_scope_allows_employee) that every post-hire read and decision already
calls, so a green run means the existing 35+ scope gates honor direct scope too.

Run on a host with the orchestrator venv + (staging) database, e.g.:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-org-hierarchy.py

NEVER point this at the production database: it writes and deletes a company.
"""

from __future__ import annotations

import sys
from typing import Any, Callable

import app
from psycopg2.extras import Json

COMPANY = "ORGHIERTESTCO"
MARKER = "temporary_org_hierarchy_harness"
TODAY = app.kuwait_today()

# Three employees: A on team A, B on team B, C unassigned (managed directly).
EMP_A = f"orghier-emp-a-{COMPANY}"
EMP_B = f"orghier-emp-b-{COMPANY}"
EMP_C = f"orghier-emp-c-{COMPANY}"
PHONE_A = "96550000000901"
PHONE_B = "96550000000902"
PHONE_C = "96550000000903"

BRANCH_KEY = app.org_key(COMPANY, "branch", "HQ")
TEAM_A_KEY = app.org_key(COMPANY, "team", "Team A")
TEAM_B_KEY = app.org_key(COMPANY, "team", "Team B")

MGR_TEAM_PHONE = "96550000000910"   # manages Team A (team scope)
MGR_DIRECT_PHONE = "96550000000911"  # manages EMP_C only (direct scope)
HR_PHONE = "96550000000912"          # no scope -> sees everything


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


def _flag(on: bool) -> None:
    if on:
        app.os.environ["WATHEFNI_ORG_HIERARCHY"] = "on"
    else:
        app.os.environ.pop("WATHEFNI_ORG_HIERARCHY", None)


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
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                (COMPANY, "Org Hierarchy Harness", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
            )
            columns = _employees_columns(cur)
            _insert_employee(cur, columns, EMP_A, PHONE_A, "Ahmed Teama")
            _insert_employee(cur, columns, EMP_B, PHONE_B, "Badr Teamb")
            _insert_employee(cur, columns, EMP_C, PHONE_C, "Cawthar Direct")
            for emp_key, phone, name in ((EMP_A, PHONE_A, "Ahmed Teama"), (EMP_B, PHONE_B, "Badr Teamb"), (EMP_C, PHONE_C, "Cawthar Direct")):
                cur.execute(
                    "INSERT INTO leave_requests (company_code, employee_key, employee_phone, employee_name, "
                    "start_date, end_date, leave_type, status, metadata) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'time_off','requested',%s)",
                    (COMPANY, emp_key, phone, name, TODAY, TODAY, Json({"smoke": MARKER})),
                )
        conn.commit()

    # Build org structure + scopes through the same helpers the endpoints use.
    _flag(True)
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
            for table in ("manager_scopes", "employee_org_assignments", "company_teams", "company_branches", "leave_requests"):
                cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM employees WHERE company_code=%s", (COMPANY,))
        conn.commit()


def teardown() -> None:
    _purge()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()
    _flag(False)


def _emp(emp_key: str) -> dict[str, Any]:
    return {"employee_key": emp_key, "company_code": COMPANY}


def _leave_company_keys(viewer_phone: str | None) -> set[str]:
    action: dict[str, Any] = {"company_code": COMPANY, "status": "requested"}
    if viewer_phone:
        action["viewer_phone"] = viewer_phone
    res = app.list_leave_requests(action, company_code=COMPANY)
    return {str(r.get("employee_key")) for r in (res.get("leave_requests") or [])}


def run_checks(checks: Checks) -> None:
    # --- Role definition: manager is approve-capable, not company-admin --------
    mgr_perms = set(app.hr_role_permissions("manager"))
    checks.check("'manager' alias normalizes to manager role", lambda: app.normalize_hr_role("manager") == "manager")
    for perm in ("leave.decide", "attendance.manage", "shifts.manage", "payroll.manage", "leave.read", "analytics.read"):
        checks.check(f"manager role holds {perm}", lambda perm=perm: perm in mgr_perms)
    for perm in ("users.manage", "settings.manage", "payroll.export", "candidate.manage", "candidate.decide", "prehire.read"):
        checks.check(f"manager role must NOT hold {perm}", lambda perm=perm: perm not in mgr_perms)

    # --- Flag ON: scopes are enforced ----------------------------------------
    _flag(True)

    # Team manager: sees/decides only Team A.
    checks.check("team mgr scope is restricted to its team", lambda: app.manager_scope_context(MGR_TEAM_PHONE, COMPANY).get("team_keys") == [TEAM_A_KEY])
    checks.check("team mgr allows team-A employee", lambda: app.manager_scope_allows_employee(_emp(EMP_A), company_code=COMPANY, viewer_phone=MGR_TEAM_PHONE) is True)
    checks.check("team mgr blocks team-B employee", lambda: app.manager_scope_allows_employee(_emp(EMP_B), company_code=COMPANY, viewer_phone=MGR_TEAM_PHONE) is False)
    checks.check("team mgr blocks unassigned employee", lambda: app.manager_scope_allows_employee(_emp(EMP_C), company_code=COMPANY, viewer_phone=MGR_TEAM_PHONE) is False)

    # Direct manager: sees/decides only its hand-picked member.
    ctx_direct = app.manager_scope_context(MGR_DIRECT_PHONE, COMPANY)
    checks.check("direct mgr scope is restricted", lambda: ctx_direct.get("restricted") is True)
    checks.check("direct mgr resolves its direct member", lambda: ctx_direct.get("direct_employee_keys") == [EMP_C])
    checks.check("direct mgr allows its member", lambda: app.manager_scope_allows_employee(_emp(EMP_C), company_code=COMPANY, viewer_phone=MGR_DIRECT_PHONE) is True)
    checks.check("direct mgr blocks non-member", lambda: app.manager_scope_allows_employee(_emp(EMP_A), company_code=COMPANY, viewer_phone=MGR_DIRECT_PHONE) is False)

    # HR (no scope) sees everyone.
    checks.check("HR (no scope) is unrestricted", lambda: app.manager_scope_context(HR_PHONE, COMPANY).get("restricted") is False)
    checks.check("HR (no scope) allows any employee", lambda: app.manager_scope_allows_employee(_emp(EMP_B), company_code=COMPANY, viewer_phone=HR_PHONE) is True)

    # End-to-end company-wide list (employee_scope_sql) honors each scope.
    checks.check("team mgr leave list = only team A", lambda: _leave_company_keys(MGR_TEAM_PHONE) == {EMP_A})
    checks.check("direct mgr leave list = only direct member", lambda: _leave_company_keys(MGR_DIRECT_PHONE) == {EMP_C})
    checks.check("HR leave list = whole company", lambda: _leave_company_keys(HR_PHONE) == {EMP_A, EMP_B, EMP_C})
    checks.check("no viewer (HR endpoints) = whole company", lambda: _leave_company_keys(None) == {EMP_A, EMP_B, EMP_C})

    # Real decision gate: marking out-of-scope absent is denied; in-scope is not.
    token = app.set_active_company_code(COMPANY)
    try:
        denied = app.mark_attendance_absent({"company_code": COMPANY, "subject_phone": PHONE_B, "subject_name": "Badr Teamb", "viewer_phone": MGR_TEAM_PHONE}, company_code=COMPANY, created_by_phone=MGR_TEAM_PHONE)
        checks.check("team mgr CANNOT mark team-B absent (decision gate)", lambda: denied.get("error") == "employee_outside_manager_scope")
        allowed = app.mark_attendance_absent({"company_code": COMPANY, "subject_phone": PHONE_A, "subject_name": "Ahmed Teama", "viewer_phone": MGR_TEAM_PHONE}, company_code=COMPANY, created_by_phone=MGR_TEAM_PHONE)
        checks.check("team mgr is NOT scope-blocked for its own team", lambda: allowed.get("error") != "employee_outside_manager_scope")
        direct_denied = app.mark_attendance_absent({"company_code": COMPANY, "subject_phone": PHONE_A, "subject_name": "Ahmed Teama", "viewer_phone": MGR_DIRECT_PHONE}, company_code=COMPANY, created_by_phone=MGR_DIRECT_PHONE)
        checks.check("direct mgr CANNOT mark a non-member absent", lambda: direct_denied.get("error") == "employee_outside_manager_scope")
        direct_ok = app.mark_attendance_absent({"company_code": COMPANY, "subject_phone": PHONE_C, "subject_name": "Cawthar Direct", "viewer_phone": MGR_DIRECT_PHONE}, company_code=COMPANY, created_by_phone=MGR_DIRECT_PHONE)
        checks.check("direct mgr is NOT scope-blocked for its member", lambda: direct_ok.get("error") != "employee_outside_manager_scope")
    finally:
        app.reset_active_company_code(token)

    # --- Flag OFF: direct scope goes dormant; HR/team unaffected --------------
    _flag(False)
    checks.check("flag OFF: direct mgr is no longer restricted", lambda: app.manager_scope_context(MGR_DIRECT_PHONE, COMPANY).get("restricted") is False)
    checks.check("flag OFF: direct mgr leave list = whole company", lambda: _leave_company_keys(MGR_DIRECT_PHONE) == {EMP_A, EMP_B, EMP_C})
    # Branch/team scoping predates the flag and is intentionally always-on.
    checks.check("flag OFF: team mgr still scoped to team A (pre-existing branch/team)", lambda: _leave_company_keys(MGR_TEAM_PHONE) == {EMP_A})
    _flag(True)

    # --- Endpoint helper validation ------------------------------------------
    checks.check("upsert_manager_scope rejects bad scope_type", lambda: app.upsert_manager_scope(COMPANY, manager_phone=MGR_TEAM_PHONE, scope_type="galaxy").get("error") == "invalid_scope_type")
    checks.check("direct scope requires members", lambda: app.upsert_manager_scope(COMPANY, manager_phone=MGR_TEAM_PHONE, scope_type="direct", employee_keys=[]).get("error") == "members_required")
    checks.check("direct scope rejects unknown employee", lambda: app.upsert_manager_scope(COMPANY, manager_phone=MGR_TEAM_PHONE, scope_type="direct", employee_keys=["does-not-exist"]).get("error") == "employee_not_found")
    checks.check("team scope rejects unknown team", lambda: app.upsert_manager_scope(COMPANY, manager_phone=MGR_TEAM_PHONE, scope_type="team", team_key="nope").get("error") == "team_not_found")

    # Cross-tenant safety: a scope row for our company never leaks to another.
    checks.check("org_overview is company-scoped", lambda: app.org_overview(COMPANY)["company_code"] == COMPANY and all(str(m.get("company_code")) == COMPANY for m in app.org_overview(COMPANY)["managers"]))


def main() -> None:
    env = app.os.environ.get("WATHEFNI_POSTGRES_ENV", "")
    print(f"org hierarchy harness — company {COMPANY} (env: {env or 'default'})")
    setup()
    checks = Checks()
    try:
        run_checks(checks)
    finally:
        teardown()
    code = checks.report()
    if code:
        print("\nORG HIERARCHY HARNESS: FAILURES PRESENT (see punch-list above)")
    else:
        print("\nORG HIERARCHY HARNESS: ALL CHECKS PASSED")
    sys.exit(code)


if __name__ == "__main__":
    main()
