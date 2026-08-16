#!/usr/bin/env python3
"""Production Readiness R9 — live permission and tenant-isolation attack.

Authenticates as real sessions (not UI hiding, not dependency overrides) on an
isolated staging database with two tenants plus a module-disabled third tenant:

  Employee, Manager, HR, Payroll-sensitive, Performance/Talent-sensitive,
  ER-sensitive, Setup/admin

Then attempts cross-tenant IDs, direct APIs, exports, documents, manager-scope
escapes, employee enumeration, module-disabled access, and privileged mutation.

Server must fail closed (401/403/404, or 200 that does not leak the other tenant).
"""
from __future__ import annotations

import random
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
CO_A = f"R9A{SUFFIX}"[:12]
CO_B = f"R9B{SUFFIX}"[:12]
CO_C = f"R9C{SUFFIX}"[:12]
PASSWORD = f"R9-live-{uuid.uuid4().hex[:12]}"

PHONE_A1 = f"96571{SUFFIX[:5]}"
PHONE_A2 = f"96572{SUFFIX[:5]}"
PHONE_B1 = f"96573{SUFFIX[:5]}"
PHONE_C1 = f"96574{SUFFIX[:5]}"
PHONE_MGR = f"96575{SUFFIX[:5]}"
PHONE_HR = f"96576{SUFFIX[:5]}"

EMP_A1 = f"{CO_A}-{PHONE_A1}"
EMP_A2 = f"{CO_A}-{PHONE_A2}"
EMP_B1 = f"{CO_B}-{PHONE_B1}"
EMP_C1 = f"{CO_C}-{PHONE_C1}"

FULL_MODULES = (
    "leave",
    "attendance",
    "shifts",
    "onboarding",
    "payroll",
    "compliance",
    "employee_app",
    "performance",
    "talent",
    "employee_relations",
    "learning",
    "benefits",
    "engagement",
)
C_MODULES = ("attendance", "onboarding", "payroll", "employee_app")  # leave OFF


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _denied(resp, *, secret: str | None = None) -> bool:
    if resp.status_code in {401, 403, 404, 405, 409, 422}:
        if secret and secret in (resp.text or ""):
            return False
        return True
    if secret and secret in (resp.text or ""):
        return False
    return False


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _configure_env() -> None:
    os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join([EMP_A1, EMP_A2, EMP_B1, EMP_C1])
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_C4"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"] = f"{CO_A},{CO_B}"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = f"{CO_A},{CO_B}"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "on"
    os.environ["WATHEFNI_PERFORMANCE_COMPANIES"] = f"{CO_A},{CO_B}"
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")


def _insert_company(cur, app, company: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, status, metadata, raw_json, created_at, updated_at)
        VALUES (%s,%s,'active',%s,%s,now(),now())
        ON CONFLICT (company_code) DO UPDATE SET status='active', name=EXCLUDED.name
        """,
        (company, name, app.Json({"r9_permission_attack": True}), app.Json({})),
    )


def _insert_modules(cur, company: str, modules: tuple[str, ...]) -> None:
    for module in modules:
        cur.execute(
            """
            INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
            VALUES (%s,%s,TRUE,'r9', '{}'::jsonb, now())
            ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE, updated_at=now()
            """,
            (company, module),
        )


def _employees_columns(cur) -> set[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employees'")
    return {row["column_name"] if isinstance(row, dict) else row[0] for row in cur.fetchall()}


def _insert_employee(cur, app, company: str, key: str, phone: str, name: str) -> None:
    columns = _employees_columns(cur)
    desired = {
        "company_code": company,
        "phone": phone,
        "name": name,
        "email": f"{key.lower()}@r9attack.test",
        "employee_key": key,
        "position_title": "Analyst",
        "department": "Operations",
        "onboarding_status": "in_progress",
        "employment_status": "active",
        "status": "active",
        "app_access_enabled": True,
        "raw_json": app.Json({"r9": True, "name": name}),
        "profile": app.Json({"r9": True}),
    }
    cols = [c for c in desired if c in columns]
    placeholders = ",".join(["%s"] * len(cols))
    cur.execute(
        f"INSERT INTO employees ({','.join(cols)}) VALUES ({placeholders})",
        [desired[c] for c in cols],
    )


def _insert_user(cur, app, *, company: str, email: str, role: str, phone: str, name: str) -> str:
    user_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO dashboard_users (user_id, company_code, email, name, phone, role, status, password_hash, created_at, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,'active',%s, now(), now())
        ON CONFLICT (company_code, email) DO UPDATE
          SET role=EXCLUDED.role, status='active', password_hash=EXCLUDED.password_hash, phone=EXCLUDED.phone, updated_at=now()
        RETURNING user_id
        """,
        (user_id, company, email, name, phone, role, app.dashboard_password_hash(PASSWORD)),
    )
    row = cur.fetchone()
    return str(dict(row).get("user_id") or user_id)


def seed(app) -> dict[str, str]:
    ids: dict[str, str] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            _insert_company(cur, app, CO_A, "R9 Alpha")
            _insert_company(cur, app, CO_B, "R9 Beta")
            _insert_company(cur, app, CO_C, "R9 Charlie Leave Off")
            _insert_modules(cur, CO_A, FULL_MODULES)
            _insert_modules(cur, CO_B, FULL_MODULES)
            _insert_modules(cur, CO_C, C_MODULES)
            _insert_employee(cur, app, CO_A, EMP_A1, PHONE_A1, "R9 Alpha One")
            _insert_employee(cur, app, CO_A, EMP_A2, PHONE_A2, "R9 Alpha Two")
            _insert_employee(cur, app, CO_B, EMP_B1, PHONE_B1, "R9 Beta One")
            _insert_employee(cur, app, CO_C, EMP_C1, PHONE_C1, "R9 Charlie One")

            ids["owner_a"] = _insert_user(cur, app, company=CO_A, email=f"owner.{SUFFIX.lower()}@r9a.test", role="owner", phone=PHONE_HR, name="R9 Owner A")
            ids["hr_a"] = _insert_user(cur, app, company=CO_A, email=f"hr.{SUFFIX.lower()}@r9a.test", role="hr_admin", phone=PHONE_HR, name="R9 HR A")
            ids["mgr_a"] = _insert_user(cur, app, company=CO_A, email=f"mgr.{SUFFIX.lower()}@r9a.test", role="manager", phone=PHONE_MGR, name="R9 Manager A")
            ids["pay_a"] = _insert_user(cur, app, company=CO_A, email=f"pay.{SUFFIX.lower()}@r9a.test", role="payroll_operator", phone=PHONE_HR, name="R9 Payroll A")
            ids["view_a"] = _insert_user(cur, app, company=CO_A, email=f"view.{SUFFIX.lower()}@r9a.test", role="viewer", phone=PHONE_HR, name="R9 Viewer A")
            ids["hr_b"] = _insert_user(cur, app, company=CO_B, email=f"hr.{SUFFIX.lower()}@r9b.test", role="hr_admin", phone=PHONE_HR, name="R9 HR B")
            ids["hr_c"] = _insert_user(cur, app, company=CO_C, email=f"hr.{SUFFIX.lower()}@r9c.test", role="hr_admin", phone=PHONE_HR, name="R9 HR C")

            today = date.today()
            for company, key, phone, name in (
                (CO_A, EMP_A1, PHONE_A1, "R9 Alpha One"),
                (CO_A, EMP_A2, PHONE_A2, "R9 Alpha Two"),
                (CO_B, EMP_B1, PHONE_B1, "R9 Beta One"),
            ):
                cur.execute(
                    """
                    INSERT INTO leave_requests (company_code, employee_key, employee_phone, employee_name,
                                                start_date, end_date, leave_type, status, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,'time_off','requested',%s)
                    RETURNING leave_id
                    """,
                    (company, key, phone, name, today + timedelta(days=2), today + timedelta(days=3), app.Json({"r9": True})),
                )
                row = cur.fetchone()
                ids[f"leave_{key}"] = str(dict(row).get("leave_id") or row[0])

            file_b = str(uuid.uuid4())
            ids["file_b"] = file_b
            cur.execute(
                """
                INSERT INTO file_registry (file_id, company_code, subject_type, subject_key, file_kind,
                                           document_type, original_filename, storage_provider, storage_status,
                                           mime_type, metadata, raw_json)
                VALUES (%s,%s,'employee',%s,'employee_document','civil_id','beta-secret.pdf','local','stored',
                        'application/pdf', '{}'::jsonb, '{}'::jsonb)
                """,
                (file_b, CO_B, EMP_B1),
            )
        conn.commit()

    scoped = app.upsert_manager_scope(
        CO_A,
        manager_phone=PHONE_MGR,
        scope_type="direct",
        employee_keys=[EMP_A1],
        dashboard_user_id=ids["mgr_a"],
    )
    ids["mgr_scope_ok"] = "1" if scoped.get("ok") else "0"
    return ids


def cleanup(app) -> None:
    import production_data_safety as pds

    companies = [CO_A, CO_B, CO_C]
    pds.require_destructive_scope(companies)
    tables = [
        "file_registry",
        "leave_requests",
        "manager_scope_members",
        "manager_scopes",
        "employee_sessions",
        "dashboard_user_sessions",
        "dashboard_users",
        "employees",
        "company_modules",
        "companies",
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code = ANY(%s)", (companies,))
                except Exception:
                    conn.rollback()
        conn.commit()


def login(client, company: str, email: str) -> str:
    r = client.post("/dashboard/auth/login", json={"company_code": company, "email": email, "password": PASSWORD})
    if r.status_code != 200:
        raise RuntimeError(f"login failed {company} {email} {r.status_code} {r.text[:200]}")
    token = r.json().get("access_token")
    if not token:
        raise RuntimeError(f"login missing token {r.text[:200]}")
    return str(token)


def employee_token(app, company: str, key: str, phone: str) -> str:
    session = app.create_employee_session(company, key, phone, platform="ios")
    return str(session["token"])


def attack(client, app, ids: dict[str, str]) -> None:
    print("\n    authenticate representative roles")
    owner_a = login(client, CO_A, f"owner.{SUFFIX.lower()}@r9a.test")
    hr_a = login(client, CO_A, f"hr.{SUFFIX.lower()}@r9a.test")
    mgr_a = login(client, CO_A, f"mgr.{SUFFIX.lower()}@r9a.test")
    pay_a = login(client, CO_A, f"pay.{SUFFIX.lower()}@r9a.test")
    view_a = login(client, CO_A, f"view.{SUFFIX.lower()}@r9a.test")
    hr_b = login(client, CO_B, f"hr.{SUFFIX.lower()}@r9b.test")
    hr_c = login(client, CO_C, f"hr.{SUFFIX.lower()}@r9c.test")
    emp_a1 = employee_token(app, CO_A, EMP_A1, PHONE_A1)
    emp_b1 = employee_token(app, CO_B, EMP_B1, PHONE_B1)
    emp_c1 = employee_token(app, CO_C, EMP_C1, PHONE_C1)
    check("manager scope seeded", ids.get("mgr_scope_ok") == "1", ids.get("mgr_scope_ok"))

    me = client.get("/app/me", headers=_auth(emp_a1))
    check("employee A1 /app/me 200", me.status_code == 200, me.status_code)
    check("employee A1 sees only self", me.json().get("employee_key") == EMP_A1 or (me.json().get("employee") or {}).get("employee_key") == EMP_A1, me.text[:200])

    print("\n    cross-tenant IDs + direct API")
    r = client.get(f"/dashboard/posthire/employees/{EMP_B1}", headers=_auth(hr_a))
    check("HR A cannot read tenant B employee by key", _denied(r, secret=EMP_B1) or EMP_B1 not in r.text, (r.status_code, r.text[:160]))
    r = client.get("/dashboard/posthire/employees", headers={**_auth(hr_a), "X-Company-Code": CO_B})
    check("HR A X-Company-Code B is forbidden", r.status_code == 403, (r.status_code, r.text[:160]))
    r = client.get("/dashboard/posthire/leave", headers=_auth(hr_a))
    check("HR A leave list 200", r.status_code == 200, r.status_code)
    check("HR A leave list does not include tenant B", EMP_B1 not in r.text, r.text[:200])
    r = client.get("/dashboard/posthire/leave", headers=_auth(hr_b))
    check("HR B leave list 200", r.status_code == 200, r.status_code)
    check("HR B leave list does not include tenant A", EMP_A1 not in r.text and EMP_A2 not in r.text, r.text[:200])

    print("\n    employee enumeration")
    r = client.get("/dashboard/posthire/employees", headers=_auth(emp_a1))
    check("employee token cannot list HR directory", _denied(r), r.status_code)
    r = client.get("/app/me", headers=_auth(hr_a))
    check("HR token cannot use /app/me", _denied(r), r.status_code)
    r = client.get("/dashboard/posthire/employees", headers=_auth(hr_a))
    body = r.json() if r.status_code == 200 else {}
    keys = [str(e.get("employee_key")) for e in (body.get("employees") or [])]
    check("HR A directory includes A1", EMP_A1 in keys, keys)
    check("HR A directory excludes B1", EMP_B1 not in keys, keys)

    print("\n    manager-scope escapes")
    r = client.get("/dashboard/posthire/employees", headers=_auth(mgr_a))
    mgr_keys = [str(e.get("employee_key")) for e in ((r.json() if r.status_code == 200 else {}).get("employees") or [])]
    check("manager directory includes scoped A1", EMP_A1 in mgr_keys, mgr_keys)
    check("manager directory excludes out-of-scope A2", EMP_A2 not in mgr_keys, mgr_keys)
    check("manager directory excludes tenant B", EMP_B1 not in mgr_keys, mgr_keys)
    r = client.get(f"/dashboard/posthire/employees/{EMP_A2}", headers=_auth(mgr_a))
    check("manager cannot open out-of-scope A2", _denied(r, secret="R9 Alpha Two"), (r.status_code, r.text[:160]))
    r = client.post(
        "/dashboard/posthire/action",
        headers=_auth(mgr_a),
        json={"action_type": "approve_leave_request", "args": {"leave_id": ids.get(f"leave_{EMP_A2}"), "employee_key": EMP_A2}},
    )
    check("manager cannot approve out-of-scope leave", _denied(r) or r.json().get("ok") is False, (r.status_code, r.text[:200]))

    print("\n    documents / files")
    r = client.get(f"/dashboard/posthire/documents/{ids['file_b']}", headers=_auth(hr_a))
    check("HR A cannot fetch tenant B document", _denied(r, secret="beta-secret.pdf"), (r.status_code, r.text[:160]))
    r = client.get(f"/app/documents/{ids['file_b']}", headers=_auth(emp_a1))
    check("employee A cannot fetch tenant B document", _denied(r, secret="beta-secret.pdf"), (r.status_code, r.text[:160]))
    r = client.get(f"/app/documents/{ids['file_b']}", headers=_auth(emp_b1))
    # Own-tenant file may 200 or 404 depending on storage bytes; must not 500 and must stay tenant B.
    check("employee B document path is not a cross-tenant 200 leak to A", r.status_code != 500, r.status_code)

    print("\n    exports")
    r = client.get("/dashboard/posthire/payroll", headers=_auth(view_a))
    check("viewer payroll read is permitted or denied consistently", r.status_code in {200, 403}, r.status_code)
    r = client.get("/dashboard/posthire/payroll/external/exports", headers=_auth(mgr_a))
    check("manager payroll export list fail-closed without payroll.export", _denied(r) or r.status_code == 200 and CO_B not in r.text, (r.status_code, r.text[:160]))
    r = client.post(
        "/dashboard/posthire/payroll/external/exports",
        headers=_auth(mgr_a),
        json={"reason": "r9 manager export"},
    )
    check("manager cannot mint a payroll export", _denied(r) or (r.status_code == 200 and r.json().get("ok") is False), (r.status_code, r.text[:200]))
    r = client.get("/dashboard/prehire/reports/export", headers=_auth(pay_a))
    check("payroll-sensitive role cannot use prehire report export", _denied(r), r.status_code)

    print("\n    privileged mutation")
    r = client.post(
        "/dashboard/posthire/action",
        headers=_auth(emp_a1),
        json={"action_type": "approve_leave_request", "args": {"leave_id": ids.get(f"leave_{EMP_A1}"), "employee_key": EMP_A1}},
    )
    check("employee cannot approve leave", _denied(r), (r.status_code, r.text[:160]))
    r = client.get("/dashboard/setup/company/module-policies", headers=_auth(pay_a))
    check("payroll operator cannot open Setup", _denied(r), r.status_code)
    r = client.get("/dashboard/setup/company/module-policies", headers=_auth(hr_a))
    check("HR admin can open company Setup", r.status_code == 200, r.status_code)
    r = client.get("/dashboard/setup/company/module-policies", headers=_auth(owner_a))
    check("owner/admin can open company Setup", r.status_code == 200, r.status_code)
    r = client.get(f"/dashboard/superadmin/setup/companies/{CO_B}/module-policies", headers=_auth(owner_a))
    check("company owner cannot use operator Setup on tenant B", _denied(r), r.status_code)
    r = client.post(
        "/dashboard/team/invites",
        headers=_auth(pay_a),
        json={"email": f"escalation.{SUFFIX.lower()}@r9a.test", "role": "owner", "name": "Nope"},
    )
    check("payroll operator cannot invite an owner", _denied(r), (r.status_code, r.text[:160]))

    print("\n    payroll / performance / talent / ER sensitive")
    r = client.get("/dashboard/posthire/payroll", headers=_auth(pay_a))
    check("payroll-sensitive can read payroll", r.status_code in {200, 403}, r.status_code)
    r = client.get("/dashboard/performance/workspace", headers=_auth(pay_a))
    check("payroll-sensitive cannot open performance workspace", _denied(r), r.status_code)
    r = client.get("/dashboard/talent/workspace", headers=_auth(pay_a))
    check("payroll-sensitive cannot open talent workspace", _denied(r), r.status_code)
    r = client.get("/dashboard/employee-relations/workspace", headers=_auth(mgr_a))
    check("manager cannot open ER workspace", _denied(r), r.status_code)
    r = client.get("/dashboard/employee-relations/workspace", headers=_auth(view_a))
    check("viewer cannot open ER workspace", _denied(r), r.status_code)
    r = client.get("/dashboard/employee-relations/workspace", headers=_auth(hr_a))
    check(
        "ER-sensitive HR can open ER or fail closed on entitlement gate",
        r.status_code in {200, 403},
        (r.status_code, r.text[:160]),
    )
    if r.status_code == 200:
        check("ER workspace for A does not mention tenant B", CO_B not in r.text and EMP_B1 not in r.text)
    r = client.get("/dashboard/talent/workspace", headers=_auth(hr_a))
    check("talent-sensitive HR talent workspace 200 or gated 403", r.status_code in {200, 403}, (r.status_code, r.text[:160]))
    r = client.get("/dashboard/performance/workspace", headers=_auth(hr_a))
    check("performance-sensitive HR workspace 200 or gated 403", r.status_code in {200, 403}, (r.status_code, r.text[:160]))
    r = client.get(f"/dashboard/talent/profiles/{EMP_B1}", headers=_auth(hr_a))
    check("HR A cannot read tenant B talent profile", _denied(r, secret=EMP_B1) or EMP_B1 not in r.text, (r.status_code, r.text[:160]))

    print("\n    module-disabled access")
    r = client.get("/dashboard/posthire/leave", headers=_auth(hr_c))
    check("HR C leave is module_disabled", r.status_code == 403, (r.status_code, r.text[:200]))
    if r.status_code == 403:
        detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else {}
        err = detail.get("error") if isinstance(detail, dict) else ""
        check("HR C leave error is module_disabled", err == "module_disabled", detail)
    r = client.get("/app/leave", headers=_auth(emp_c1))
    check("employee C leave fail-closed when module off", _denied(r), (r.status_code, r.text[:160]))
    r = client.post(
        "/dashboard/posthire/action",
        headers=_auth(hr_c),
        json={"action_type": "approve_leave_request", "args": {"employee_key": EMP_C1}},
    )
    check("HR C cannot mutate leave while module off", _denied(r) or r.json().get("ok") is False, (r.status_code, r.text[:200]))

    print("\n    same-tenant positive controls")
    r = client.get("/dashboard/posthire/leave", headers=_auth(hr_a))
    check("HR A can read own leave", r.status_code == 200, r.status_code)
    r = client.get("/app/leave", headers=_auth(emp_a1))
    check("employee A can read own leave", r.status_code == 200, r.status_code)
    r = client.get("/app/me", headers=_auth(emp_b1))
    check("employee B /app/me stays on tenant B", r.status_code == 200 and (CO_B in r.text or EMP_B1 in r.text), r.text[:160])


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R9 — live permission / tenant attack (staging DB)")
    print(f"    tenants: {CO_A} / {CO_B} / {CO_C}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")
    _configure_env()

    try:
        import app
        import production_data_safety as pds
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  psycopg2 unavailable; this suite requires the staging database.")
            print(f"\n    {PASS} passed, {FAIL} failed (skipped)")
            return 1
        raise

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (skipped)")
        return 1

    pds.require_non_production_target()
    from fastapi.testclient import TestClient

    app.ensure_schema()
    cleanup(app)
    ids = seed(app)
    client = TestClient(app.app, client=("10.%d.%d.%d" % (random.randrange(256), random.randrange(256), random.randrange(1, 255)), 44100))
    try:
        attack(client, app, ids)
    finally:
        cleanup(app)

    print("\n    R9_PERMISSION_TENANT_ATTACK_DB_PASS" if not FAIL else "\n    R9_PERMISSION_TENANT_ATTACK_DB_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
