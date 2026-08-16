#!/usr/bin/env python3
"""Production Readiness R10 — measure real staging latency on representative reads.

Creates a throwaway synthetic company with 80 employees, times:
  * list_employees_page
  * GET /dashboard/posthire/employees
  * GET /app/home
  * GET /health and in-process ready-adjacent DB ping

Fails only on harmful blockers: directory unbounded, or a single measured
read slower than 2.5s. Does not micro-optimize harmless shapes.
"""
from __future__ import annotations

import os
import random
import sys
import time
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R9P{SUFFIX}"[:12]
PASSWORD = f"R10-{uuid.uuid4().hex[:10]}"
HR_EMAIL = f"hr.{SUFFIX.lower()}@r10.test"
HR_PHONE = f"96591{SUFFIX[:5]}"
EMP_PHONE = f"96592{SUFFIX[:5]}"
EMP_KEY = f"{COMPANY}-{EMP_PHONE}"
N = 80
BUDGET_S = 2.5


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def timed(fn):
    start = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - start


def main() -> int:
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")
    os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = EMP_KEY
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    print("    PRODUCTION READINESS R10 — measured staging latency")
    print(f"    tenant: {COMPANY} headcount={N}")

    try:
        import app
        import production_data_safety as pds
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:
        print(f"      SKIP  {exc}")
        return 1

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        return 1

    pds.require_non_production_target()
    pds.require_destructive_scope([COMPANY])
    app.ensure_schema()

    def cleanup() -> None:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for table in (
                    "dashboard_user_permission_grants",
                    "employee_sessions",
                    "dashboard_user_sessions",
                    "dashboard_users",
                    "employees",
                    "company_modules",
                    "companies",
                ):
                    try:
                        cur.execute(f"DELETE FROM {table} WHERE company_code=%s", (COMPANY,))
                    except Exception:
                        conn.rollback()
            conn.commit()

    cleanup()
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, status, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,'R10 Measure','active','{}'::jsonb,'{}'::jsonb, now(), now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (COMPANY,),
                )
                for module in ("leave", "attendance", "employee_app", "payroll"):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                        VALUES (%s,%s,TRUE,'r10','{}'::jsonb, now())
                        ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE
                        """,
                        (COMPANY, module),
                    )
                cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employees'")
                cols = {r["column_name"] if isinstance(r, dict) else r[0] for r in cur.fetchall()}
                for i in range(N):
                    phone = f"96593{SUFFIX[:2]}{i:04d}"
                    key = f"{COMPANY}-{phone}"
                    desired = {
                        "employee_key": key,
                        "phone": phone,
                        "company_code": COMPANY,
                        "name": f"R10 Person {i:03d}",
                        "email": f"p{i}.{SUFFIX.lower()}@r10.test",
                        "employment_status": "active",
                        "status": "active",
                        "raw_json": app.Json({"r10": True}),
                    }
                    if i == 0:
                        desired["employee_key"] = EMP_KEY
                        desired["phone"] = EMP_PHONE
                    if "app_access_enabled" in cols:
                        desired["app_access_enabled"] = True
                    use = [c for c in desired if c in cols]
                    cur.execute(
                        f"INSERT INTO employees ({','.join(use)}) VALUES ({','.join(['%s']*len(use))})",
                        [desired[c] for c in use],
                    )
                hr_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO dashboard_users (user_id, company_code, email, name, phone, role, status, password_hash, created_at, updated_at)
                    VALUES (%s,%s,%s,'R10 HR',%s,'hr_admin','active',%s, now(), now())
                    RETURNING user_id
                    """,
                    (hr_id, COMPANY, HR_EMAIL, HR_PHONE, app.dashboard_password_hash(PASSWORD)),
                )
                row = cur.fetchone() or {}
                hr_id = str((row.get("user_id") if isinstance(row, dict) else row[0]) or hr_id)
                cur.execute(
                    """
                    INSERT INTO dashboard_user_permission_grants
                      (company_code, user_id, permission, status, review_reference, granted_by_user_id, granted_reason)
                    VALUES (%s,%s,'employees.read','active','r10-measure',%s,'r10 directory latency')
                    ON CONFLICT (company_code, user_id, permission) DO UPDATE SET status='active'
                    """,
                    (COMPANY, hr_id, hr_id),
                )
            conn.commit()

        page, page_s = timed(lambda: app.list_employees_page(COMPANY, limit=50, offset=0))
        print(f"      TIME  list_employees_page n=50 {page_s*1000:.0f}ms total={page.get('total_count')}")
        check("paged directory total is 80", int(page.get("total_count") or 0) == N, page.get("total_count"))
        check("paged directory returns at most 50 rows", len(page.get("rows") or []) <= 50)
        check("list_employees_page under budget", page_s < BUDGET_S, f"{page_s:.3f}s")

        client = TestClient(app.app, client=("10.%d.%d.%d" % (random.randrange(256), random.randrange(256), random.randrange(1, 255)), 44100))
        login, login_s = timed(lambda: client.post("/dashboard/auth/login", json={"company_code": COMPANY, "email": HR_EMAIL, "password": PASSWORD}))
        print(f"      TIME  dashboard login {login_s*1000:.0f}ms status={login.status_code}")
        check("HR login 200", login.status_code == 200, login.status_code)
        token = (login.json() or {}).get("access_token")
        listing, list_s = timed(lambda: client.get("/dashboard/posthire/employees?limit=50", headers={"Authorization": f"Bearer {token}"}))
        print(f"      TIME  GET /dashboard/posthire/employees {list_s*1000:.0f}ms status={listing.status_code}")
        check("employees HTTP 200", listing.status_code == 200, listing.status_code)
        check("employees HTTP under budget", list_s < BUDGET_S, f"{list_s:.3f}s")
        body = listing.json() if listing.status_code == 200 else {}
        check("HTTP directory is paged", int(body.get("limit") or 0) <= 500 and len(body.get("employees") or []) <= 50, body.get("limit"))

        emp_token = app.create_employee_session(COMPANY, EMP_KEY, EMP_PHONE)["token"]
        home, home_s = timed(lambda: client.get("/app/home", headers={"Authorization": f"Bearer {emp_token}"}))
        print(f"      TIME  GET /app/home {home_s*1000:.0f}ms status={home.status_code}")
        check("employee Home responds", home.status_code in {200, 403}, home.status_code)
        check("employee Home under budget", home_s < BUDGET_S, f"{home_s:.3f}s")

        health, health_s = timed(lambda: client.get("/health"))
        print(f"      TIME  GET /health {health_s*1000:.0f}ms status={health.status_code}")
        check("health 200", health.status_code == 200)
        check("health under 500ms", health_s < 0.5, f"{health_s:.3f}s")
    finally:
        cleanup()

    print("\n    R10_MEASURED_PERFORMANCE_DB_PASS" if not FAIL else "\n    R10_MEASURED_PERFORMANCE_DB_FAIL")
    print(f"    {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
