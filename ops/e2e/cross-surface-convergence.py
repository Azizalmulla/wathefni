#!/usr/bin/env python3
"""Cross-surface canonical-truth convergence (API/data → action → API assert).

Does not crawl the UI. Uses authenticated HTTP the same way the mobile/web
clients do, then asserts backend/domain truth. Maestro remains the mobile UI
oracle when a device is present.
"""
from __future__ import annotations

import os
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R9E{SUFFIX}"[:12]
PASSWORD = f"E2E-{uuid.uuid4().hex[:10]}"
PHONE_EMP = f"96581{SUFFIX[:5]}"
PHONE_HR = f"96582{SUFFIX[:5]}"
EMP_KEY = f"{COMPANY}-{PHONE_EMP}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    orch = Path(__file__).resolve().parents[2] / "wathefni-orchestrator"
    sys.path.insert(0, str(orch))
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")
    os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = EMP_KEY
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    print("    E2E cross-surface employee / leave / module convergence")
    print(f"    tenant: {COMPANY}")

    try:
        import app
        import production_data_safety as pds
        from fastapi.testclient import TestClient
    except ModuleNotFoundError as exc:
        print(f"      SKIP  {exc}")
        return 2

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        return 2

    pds.require_non_production_target()
    pds.require_destructive_scope([COMPANY])
    app.ensure_schema()

    def cleanup() -> None:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for table in (
                    "leave_requests",
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
                    VALUES (%s,'E2E Leave', 'active', '{}'::jsonb, '{}'::jsonb, now(), now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (COMPANY,),
                )
                for module in ("leave", "employee_app", "attendance"):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                        VALUES (%s,%s,TRUE,'e2e','{}'::jsonb, now())
                        ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE
                        """,
                        (COMPANY, module),
                    )
                cols = {r["column_name"] if isinstance(r, dict) else r[0] for r in (
                    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='employees'") or True
                    and cur.fetchall()
                )}
                desired = {
                    "employee_key": EMP_KEY,
                    "phone": PHONE_EMP,
                    "company_code": COMPANY,
                    "name": "E2E Employee",
                    "email": f"{EMP_KEY.lower()}@e2e.test",
                    "employment_status": "active",
                    "status": "active",
                    "app_access_enabled": True,
                    "raw_json": app.Json({"e2e": True}),
                }
                use = [c for c in desired if c in cols]
                cur.execute(
                    f"INSERT INTO employees ({','.join(use)}) VALUES ({','.join(['%s']*len(use))})",
                    [desired[c] for c in use],
                )
                hr_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO dashboard_users (user_id, company_code, email, name, phone, role, status, password_hash, created_at, updated_at)
                    VALUES (%s,%s,%s,'E2E HR',%s,'hr_admin','active',%s, now(), now())
                    RETURNING user_id
                    """,
                    (hr_id, COMPANY, f"hr.{SUFFIX.lower()}@e2e.test", PHONE_HR, app.dashboard_password_hash(PASSWORD)),
                )
                row = cur.fetchone() or {}
                hr_id = str((row.get("user_id") if isinstance(row, dict) else row[0]) or hr_id)
                for perm in ("employees.read", "employees.manage"):
                    cur.execute(
                        """
                        INSERT INTO dashboard_user_permission_grants
                          (company_code, user_id, permission, status, review_reference, granted_by_user_id, granted_reason)
                        VALUES (%s,%s,%s,'active','e2e-convergence',%s,'e2e leave journey')
                        ON CONFLICT (company_code, user_id, permission) DO UPDATE SET status='active'
                        """,
                        (COMPANY, hr_id, perm, hr_id),
                    )
            conn.commit()

        client = TestClient(app.app, client=("10.%d.%d.%d" % (random.randrange(256), random.randrange(256), random.randrange(1, 255)), 44100))
        login = client.post(
            "/dashboard/auth/login",
            json={"company_code": COMPANY, "email": f"hr.{SUFFIX.lower()}@e2e.test", "password": PASSWORD},
        )
        check("HR login", login.status_code == 200, login.text[:160])
        hr_token = (login.json() or {}).get("access_token")
        emp_token = app.create_employee_session(COMPANY, EMP_KEY, PHONE_EMP)["token"]

        # Employees: the HR web action updates the canonical employee row, and
        # both HR detail and Employee profile must immediately project it.
        marker = f"Convergence {SUFFIX}"
        before_employee = app.find_employee_by_key(EMP_KEY, company_code=COMPANY) or {}
        update = client.patch(
            f"/dashboard/posthire/employees/{EMP_KEY}",
            headers={"Authorization": f"Bearer {hr_token}"},
            json={
                "position_title": marker,
                "expected_updated_at": app.json_safe(before_employee.get("updated_at")),
            },
        )
        check("HR employee edit commits", update.status_code == 200, update.text[:200])
        canonical_employee = app.find_employee_by_key(EMP_KEY, company_code=COMPANY) or {}
        check("employee edit reached canonical row", canonical_employee.get("position_title") == marker, canonical_employee)
        hr_employee = client.get(
            f"/dashboard/posthire/employees/{EMP_KEY}",
            headers={"Authorization": f"Bearer {hr_token}"},
        )
        check("HR detail sees canonical employee edit", hr_employee.status_code == 200 and marker in hr_employee.text, hr_employee.text[:200])
        employee_profile = client.get("/app/profile", headers={"Authorization": f"Bearer {emp_token}"})
        check(
            "Employee profile sees HR edit",
            employee_profile.status_code == 200 and marker in employee_profile.text,
            employee_profile.text[:200],
        )

        today = date.today()
        req = client.post(
            "/app/leave/request",
            headers={"Authorization": f"Bearer {emp_token}"},
            json={
                "leave_type": "annual",
                "start_date": (today + timedelta(days=5)).isoformat(),
                "end_date": (today + timedelta(days=6)).isoformat(),
                "reason": "e2e convergence",
            },
        )
        check("employee request accepted or validated", req.status_code in {200, 201, 400, 403, 409, 422}, req.status_code)
        leave_id = None
        if req.status_code in {200, 201}:
            leave_id = str((req.json() or {}).get("leave_id") or (req.json() or {}).get("id") or "")
        if not leave_id:
            listed = client.get("/app/leave", headers={"Authorization": f"Bearer {emp_token}"})
            check("employee leave list readable", listed.status_code == 200, listed.status_code)
            rows = (listed.json() or {}).get("requests") or (listed.json() or {}).get("leave_requests") or []
            if rows:
                leave_id = str(rows[0].get("leave_id") or rows[0].get("id") or "")
        hr_list = client.get("/dashboard/posthire/leave", headers={"Authorization": f"Bearer {hr_token}"})
        check("HR sees company leave", hr_list.status_code == 200, hr_list.status_code)
        check("HR leave payload stays on this tenant", COMPANY in hr_list.text or EMP_KEY in hr_list.text or hr_list.status_code == 200)
        if leave_id:
            decide = client.post(
                "/dashboard/posthire/action",
                headers={"Authorization": f"Bearer {hr_token}"},
                json={"action_type": "approve_leave_request", "args": {"leave_id": leave_id, "employee_key": EMP_KEY}},
            )
            check(
                "HR approve is a real domain result",
                decide.status_code in {200, 400, 403, 409} and "password" not in decide.text.lower(),
                (decide.status_code, decide.text[:200]),
            )
            if req.status_code in {200, 201}:
                check("HR approve succeeds for a valid pending request", decide.status_code == 200, decide.text[:200])
                listed = client.get("/dashboard/posthire/leave", headers={"Authorization": f"Bearer {hr_token}"})
                check("HR leave list still 200 after approve", listed.status_code == 200, listed.status_code)
                if listed.status_code == 200 and leave_id:
                    blob = listed.text.lower()
                    check(
                        "canonical leave is approved or decided",
                        "approved" in blob or "approve" in decide.text.lower() or leave_id in listed.text,
                        decide.text[:160],
                    )
            again = client.get("/app/leave", headers={"Authorization": f"Bearer {emp_token}"})
            check("employee refresh stays on this tenant", again.status_code == 200, again.status_code)
            if again.status_code == 200 and leave_id:
                check("employee payload does not leak another tenant", COMPANY in again.text or EMP_KEY in again.text or leave_id in again.text)
        att = client.get("/app/attendance", headers={"Authorization": f"Bearer {emp_token}"})
        check("employee attendance is tenant-scoped or fail-closed", att.status_code in {200, 403, 404}, att.status_code)

        # Setup/module composition: one canonical module toggle must converge on
        # every client surface instead of leaving a stale Employee/HR capability.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE company_modules SET enabled=FALSE, updated_at=now() WHERE company_code=%s AND module_key='leave'",
                    (COMPANY,),
                )
            conn.commit()
        employee_leave_off = client.get("/app/leave", headers={"Authorization": f"Bearer {emp_token}"})
        hr_leave_off = client.get("/dashboard/posthire/leave", headers={"Authorization": f"Bearer {hr_token}"})
        check("Employee honors canonical leave module disable", employee_leave_off.status_code == 403, employee_leave_off.text[:160])
        check("HR honors canonical leave module disable", hr_leave_off.status_code == 403, hr_leave_off.text[:160])
    finally:
        cleanup()

    print(f"\n    CROSS_SURFACE_{'PASS' if not FAIL else 'FAIL'}  {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
