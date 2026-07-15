#!/usr/bin/env python3
"""Staging-only DB-backed verifier for HR-3 operator-mobile routes.

The script provisions marker-scoped temporary tenants in the explicitly bound
staging database, drives only the staging HTTP base, forces dry-run delivery,
and removes every fixture in ``finally``. It must never be run in production.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
from typing import Any
import uuid

import requests


PASS = 0
FAIL = 0
COMPANY = "HR3MOB"
OTHER = "HR3OTH"
MARKER = "temporary_hr3_staging_harness"
BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")
STAGING_ORCH = os.environ.get("WATHEFNI_STAGING_ORCH", "/opt/wathefni/staging/orchestrator")


def check(label: str, condition: bool, detail: Any = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" :: {detail}" if detail is not None else ""))


def payload(response: requests.Response) -> dict[str, Any]:
    try:
        value = response.json()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def error_code(response: requests.Response) -> str:
    value = payload(response)
    detail = value.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("error") or "")
    return str(value.get("error") or "")


def bind_staging() -> None:
    expected = {
        "WATHEFNI_POSTGRES_ENV": "/root/.openclaw/secrets/postgres.staging.env",
        "WATHEFNI_WORKSPACE": "/opt/wathefni/staging/workspace",
        "WATHEFNI_DELIVERY_MODE": "dry_run",
        "WATHEFNI_ENV": "staging",
        "WATHEFNI_EXPECTED_DATABASE_HOST": "127.0.0.1",
        "WATHEFNI_EXPECTED_DATABASE_PORT": "5432",
        "WATHEFNI_EXPECTED_DATABASE_NAME": "wathefni_staging",
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER": "wathefni-staging-hr2-isolation-v1",
    }
    for key, value in expected.items():
        existing = str(os.environ.get(key) or "").strip()
        if existing and existing != value:
            raise RuntimeError(f"refusing HR-3 staging verifier: {key}={existing!r}, expected {value!r}")
        os.environ[key] = value
    if not BASE.startswith(("http://127.0.0.1:", "https://staging.")):
        raise RuntimeError(f"refusing non-staging HTTP base: {BASE}")


def main() -> int:
    bind_staging()
    sys.path = [path for path in sys.path if path not in {STAGING_ORCH, "/opt/wathefni/orchestrator"}]
    sys.path.insert(0, STAGING_ORCH)

    import app
    import operator_mobile_data as mobile_data

    if not str(getattr(app, "__file__", "")).startswith(STAGING_ORCH):
        raise RuntimeError(f"HR-3 must import staging app.py, got {app.__file__}")
    identity = app.assert_runtime_environment_binding()
    if (
        identity.application_environment != "staging"
        or identity.database_environment != "staging"
    ):
        raise RuntimeError(f"HR-3 staging identity mismatch: {identity.public()}")
    if not app.delivery_is_dry_run():
        raise RuntimeError("HR-3 staging verifier requires dry-run delivery")

    app.ensure_schema(force=True)
    mobile_data.ensure_operator_mobile_data_schema(app)
    print(f"HR-3 staging verify — {COMPANY} against {BASE}")

    password = f"Hr3-{uuid.uuid4().hex[:14]}!"
    users = {key: str(uuid.uuid4()) for key in ("owner", "manager", "viewer", "other")}
    phones = {
        "owner": "965500390001",
        "manager": "965500390002",
        "viewer": "965500390003",
        "other": "965500390099",
        "a": "965500391001",
        "b": "965500391002",
        "other_employee": "965500391099",
        "candidate": "965500392001",
    }
    employee_a = "hr3-emp-a"
    employee_b = "hr3-emp-b"
    employee_other = "hr3-emp-other"
    branch = app.org_key(COMPANY, "branch", "HQ")
    team_a = app.org_key(COMPANY, "team", "Team A")
    team_b = app.org_key(COMPANY, "team", "Team B")
    app_key = f"{phones['candidate']}-{COMPANY}-HR3_ROLE"
    fixture: dict[str, str] = {}

    def cleanup() -> None:
        employee_keys = [employee_a, employee_b, employee_other]
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM candidate_interview_events WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM candidate_interviews WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM action_results WHERE result->>'company_code' = ANY(%s) OR result->>'company_id' = ANY(%s)",
                ([COMPANY, OTHER], [COMPANY, OTHER]),
            )
            cur.execute(
                "DELETE FROM outbound_delivery_events WHERE account_id = ANY(%s) OR target_phone = ANY(%s) OR payload->>'company_code' = ANY(%s)",
                ([COMPANY, OTHER], list(phones.values()), [COMPANY, OTHER]),
            )
            cur.execute("DELETE FROM pending_actions WHERE account_id = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute(
                "DELETE FROM dashboard_operator_mobile_confirmations WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM dashboard_operator_mobile_sessions WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM dashboard_user_sessions WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM employee_sessions WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM dashboard_user_permission_grants WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute("DELETE FROM hr_tasks WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute(
                "DELETE FROM shift_swap_events WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM shift_swap_requests WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM attendance_events WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM attendance_records WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute("DELETE FROM shift_events WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute(
                "DELETE FROM shift_assignments WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM onboarding_items WHERE employee_key = ANY(%s)",
                (employee_keys,),
            )
            cur.execute(
                "DELETE FROM compliance_documents WHERE employee_key = ANY(%s)",
                (employee_keys,),
            )
            cur.execute(
                "DELETE FROM employee_org_assignments WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute(
                "DELETE FROM manager_scope_members WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute("DELETE FROM manager_scopes WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM company_teams WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute(
                "DELETE FROM company_branches WHERE company_code = ANY(%s)",
                ([COMPANY, OTHER],),
            )
            cur.execute("DELETE FROM employees WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM applications WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute(
                "DELETE FROM candidates WHERE active_company_code = ANY(%s) OR phone = ANY(%s)",
                ([COMPANY, OTHER], list(phones.values())),
            )
            cur.execute("DELETE FROM dashboard_users WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM company_modules WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            conn.commit()

    def login(email: str, company: str = COMPANY) -> tuple[requests.Response, dict[str, Any]]:
        response = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": email, "password": password, "company_code": company},
            timeout=30,
        )
        return response, payload(response)

    def headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def post_confirmed(
        path: str,
        token: str,
        material: dict[str, Any],
        *,
        label: str,
    ) -> tuple[requests.Response, requests.Response, dict[str, Any]]:
        key = f"hr3-{label}-{uuid.uuid4()}"
        prepared = requests.post(
            f"{BASE}{path}",
            headers=headers(token),
            json={**material, "idempotency_key": key, "confirm": False},
            timeout=45,
        )
        prepared_body = payload(prepared)
        confirmation = prepared_body.get("confirmation") or {}
        check(
            f"{label} requires confirmation",
            prepared.status_code == 200 and prepared_body.get("status") == "needs_confirmation",
            prepared.text[:500],
        )
        confirm_material = {
            **material,
            "idempotency_key": key,
            "confirm": True,
            "confirmation_id": confirmation.get("confirmation_id"),
            "confirmation_hash": confirmation.get("confirmation_hash"),
        }
        confirmed = requests.post(
            f"{BASE}{path}",
            headers=headers(token),
            json=confirm_material,
            timeout=90,
        )
        return prepared, confirmed, confirm_material

    cleanup()
    try:
        today = app.kuwait_today()
        start = datetime.now(timezone.utc) + timedelta(days=1)
        with app.db_connect() as conn, conn.cursor() as cur:
            for company in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, status, metadata)
                    VALUES (%s,%s,'active',%s)
                    """,
                    (company, f"{company} HR-3 staging", app.Json({"marker": MARKER})),
                )
                for module in ("onboarding", "compliance", "attendance", "shifts", "pre_hiring"):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, updated_at)
                        VALUES (%s,%s,true,now())
                        """,
                        (company, module),
                    )

            def add_user(key: str, company: str, email: str, role: str, phone: str) -> None:
                cur.execute(
                    """
                    INSERT INTO dashboard_users
                      (user_id, company_code, email, name, phone, role, status,
                       password_hash, accepted_at, metadata, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,'active',%s,now(),%s,now())
                    """,
                    (
                        users[key],
                        company,
                        email,
                        key.title(),
                        phone,
                        role,
                        app.dashboard_password_hash(password),
                        app.Json({"marker": MARKER}),
                    ),
                )

            add_user("owner", COMPANY, "owner@hr3.staging.test", "owner", phones["owner"])
            add_user("manager", COMPANY, "manager@hr3.staging.test", "manager", phones["manager"])
            add_user("viewer", COMPANY, "viewer@hr3.staging.test", "viewer", phones["viewer"])
            add_user("other", OTHER, "owner@hr3oth.staging.test", "owner", phones["other"])

            cur.execute(
                "INSERT INTO company_branches (company_code, branch_key, branch_name, is_active) VALUES (%s,%s,'HQ',true)",
                (COMPANY, branch),
            )
            for key, name in ((team_a, "Team A"), (team_b, "Team B")):
                cur.execute(
                    "INSERT INTO company_teams (company_code, team_key, team_name, branch_key, is_active) VALUES (%s,%s,%s,%s,true)",
                    (COMPANY, key, name, branch),
                )
            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,%s,'team',%s,'manager',true,now())
                """,
                (COMPANY, phones["manager"], users["manager"], team_a),
            )

            for company, key, phone, name in (
                (COMPANY, employee_a, phones["a"], "Aisha HR3"),
                (COMPANY, employee_b, phones["b"], "Bader HR3"),
                (OTHER, employee_other, phones["other_employee"], "Other HR3"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees
                      (company_code, employee_key, phone, name, position_title,
                       employment_status, onboarding_status, raw_json, updated_at)
                    VALUES (%s,%s,%s,%s,'Specialist','active','in_progress',%s,now())
                    """,
                    (company, key, phone, name, app.Json({"marker": MARKER})),
                )
            for key, team in ((employee_a, team_a), (employee_b, team_b)):
                cur.execute(
                    """
                    INSERT INTO employee_org_assignments
                      (company_code, employee_key, branch_key, team_key, is_primary, updated_at)
                    VALUES (%s,%s,%s,%s,true,now())
                    """,
                    (COMPANY, key, branch, team),
                )

            for key in (employee_a, employee_b, employee_other):
                cur.execute(
                    """
                    INSERT INTO onboarding_items
                      (employee_key, item_id, label, item_type, required, document_type, status, raw_json)
                    VALUES (%s,'civil_id','Civil ID','document',true,'civil_id','pending',%s)
                    """,
                    (key, app.Json({"marker": MARKER})),
                )
                cur.execute(
                    """
                    INSERT INTO compliance_documents
                      (company_code, employee_key, document_type, label, status, raw_json, updated_at)
                    VALUES (%s,%s,'civil_id','Civil ID','received',%s,now())
                    """,
                    (
                        OTHER if key == employee_other else COMPANY,
                        key,
                        app.Json({"marker": MARKER}),
                    ),
                )

            for label, company, key, phone, name, status in (
                ("resolve", COMPANY, employee_a, phones["a"], "Aisha HR3", "late"),
                ("stale", COMPANY, employee_b, phones["b"], "Bader HR3", "absent"),
                ("other", OTHER, employee_other, phones["other_employee"], "Other HR3", "late"),
            ):
                cur.execute(
                    """
                    INSERT INTO attendance_records
                      (company_code, employee_key, employee_phone, employee_name,
                       attendance_date, scheduled_start, scheduled_end, status,
                       late_minutes, notes, metadata)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00',%s,%s,%s,%s)
                    RETURNING attendance_id
                    """,
                    (
                        company,
                        key,
                        phone,
                        name,
                        today,
                        status,
                        15 if status == "late" else 0,
                        f"{MARKER}:{label}",
                        app.Json({"marker": MARKER}),
                    ),
                )
                fixture[f"attendance_{label}"] = str(cur.fetchone()["attendance_id"])

            shift_ids: list[str] = []
            for index, (key, phone, name) in enumerate(
                (
                    (employee_a, phones["a"], "Aisha HR3"),
                    (employee_b, phones["b"], "Bader HR3"),
                )
            ):
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name,
                       shift_date, start_time, end_time, status, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'scheduled',%s)
                    RETURNING shift_id
                    """,
                    (
                        COMPANY,
                        key,
                        phone,
                        name,
                        today,
                        f"{9 + index:02d}:00",
                        f"{17 + index:02d}:00",
                        app.Json({"marker": MARKER}),
                    ),
                )
                shift_ids.append(str(cur.fetchone()["shift_id"]))

            for label in ("approve", "reject", "stale"):
                cur.execute(
                    """
                    INSERT INTO shift_swap_requests
                      (company_code, requester_employee_key, requester_employee_phone,
                       requester_employee_name, target_employee_key, target_employee_phone,
                       target_employee_name, requester_shift_id, target_shift_id,
                       shift_date, status, reason, metadata)
                    VALUES (%s,%s,%s,'Aisha HR3',%s,%s,'Bader HR3',%s,%s,%s,'requested',%s,%s)
                    RETURNING swap_id
                    """,
                    (
                        COMPANY,
                        employee_a,
                        phones["a"],
                        employee_b,
                        phones["b"],
                        shift_ids[0],
                        shift_ids[1],
                        today,
                        f"{MARKER}:{label}",
                        app.Json({"marker": MARKER}),
                    ),
                )
                fixture[f"swap_{label}"] = str(cur.fetchone()["swap_id"])

            for company, key, title in (
                (COMPANY, employee_a, "Aisha follow-up"),
                (COMPANY, employee_b, "Bader follow-up"),
                (OTHER, employee_other, "Other follow-up"),
            ):
                cur.execute(
                    """
                    INSERT INTO hr_tasks
                      (company_code, employee_key, task_type, source, title, detail,
                       status, priority, metadata)
                    VALUES (%s,%s,'document_review','hr3',%s,%s,'open','high',%s)
                    RETURNING task_id
                    """,
                    (company, key, title, MARKER, app.Json({"marker": MARKER})),
                )
                fixture[f"task_{key}"] = str(cur.fetchone()["task_id"])

            cur.execute(
                """
                INSERT INTO candidates
                  (phone, name, email, active_company_code, data_source, raw_json, updated_at)
                VALUES (%s,'Lina HR3','lina@hr3.staging.test',%s,'production',%s,now())
                """,
                (phones["candidate"], COMPANY, app.Json({"marker": MARKER})),
            )
            cur.execute(
                """
                INSERT INTO applications
                  (app_key, company_code, phone, position_code, position_title,
                   status, data_source, cv_received, raw_json, updated_at)
                VALUES (%s,%s,%s,'HR3_ROLE','HR3 Specialist',
                        'review_pending','production',true,%s,now())
                """,
                (
                    app_key,
                    COMPANY,
                    phones["candidate"],
                    app.Json({"marker": MARKER, "cv": {"received": True}}),
                ),
            )
            cur.execute(
                """
                INSERT INTO candidate_interviews
                  (company_code, app_key, phone, candidate_name, candidate_email,
                   position_code, position_title, status, feedback_status,
                   scheduled_start, scheduled_end, source, ai_summary)
                VALUES (%s,%s,%s,'Lina HR3','lina@hr3.staging.test',
                        'HR3_ROLE','HR3 Specialist','completed','notes_pending',
                        %s,%s,'hr3_staging',%s)
                RETURNING interview_id
                """,
                (
                    COMPANY,
                    app_key,
                    phones["candidate"],
                    start,
                    start + timedelta(hours=1),
                    app.Json({}),
                ),
            )
            fixture["interview"] = str(cur.fetchone()["interview_id"])
            conn.commit()

        all_permissions = (
            "onboarding.read",
            "onboarding.manage",
            "compliance.read",
            "compliance.manage",
            "attendance.read",
            "employees.read",
            "attendance.manage",
            "shifts.read",
            "shifts.manage",
            "prehire.read",
            "interview.manage",
        )
        for user_key in ("owner", "manager"):
            for permission in all_permissions:
                granted = app.set_dashboard_user_permission_grant(
                    COMPANY,
                    users[user_key],
                    permission,
                    active=True,
                    actor_user_id=users["owner"],
                    reason="HR-3 staging verifier",
                    review_reference="HR-3",
                )
                check(f"{user_key} grant {permission}", granted.get("ok") is True, granted)
        viewer_grant = app.set_dashboard_user_permission_grant(
            COMPANY,
            users["viewer"],
            "employees.read",
            active=True,
            actor_user_id=users["owner"],
            reason="HR-3 staging revocation proof",
            review_reference="HR-3",
        )
        check("viewer employees.read grant", viewer_grant.get("ok") is True, viewer_grant)

        owner_login, owner_body = login("owner@hr3.staging.test")
        manager_login, manager_body = login("manager@hr3.staging.test")
        viewer_login, viewer_body = login("viewer@hr3.staging.test")
        check("owner login", owner_login.status_code == 200, owner_login.text[:300])
        check("manager login", manager_login.status_code == 200, manager_login.text[:300])
        check("viewer login", viewer_login.status_code == 200, viewer_login.text[:300])
        owner_token = str(owner_body.get("access_token") or "")
        manager_token = str(manager_body.get("access_token") or "")
        viewer_token = str(viewer_body.get("access_token") or "")

        me = requests.get(f"{BASE}/dashboard/mobile/me", headers=headers(owner_token), timeout=30)
        features = (((payload(me).get("workspaces") or {}).get("hr") or {}).get("features") or {})
        recruiting = (((payload(me).get("workspaces") or {}).get("recruiting") or {}).get("features") or {})
        check("backend-current capability payload", payload(me).get("permission_authority") == "backend_current", me.text[:300])
        check("HR tasks advertise read only", (features.get("hr_tasks") or {}).get("actions") == ["read"], features.get("hr_tasks"))
        check("attendance resolve advertised", "resolve" in ((features.get("attendance_exceptions") or {}).get("actions") or []))
        check("interview notes write advertised", "write" in ((recruiting.get("interview_notes") or {}).get("actions") or []))

        tasks = requests.get(f"{BASE}/dashboard/mobile/tasks", headers=headers(owner_token), timeout=30)
        task_ids = {item.get("task_id") for item in payload(tasks).get("items") or []}
        check("HR task read", fixture[f"task_{employee_a}"] in task_ids, tasks.text[:400])
        check("cross-tenant task excluded", fixture[f"task_{employee_other}"] not in task_ids, task_ids)
        check("HR task items advertise no resolve", all((item.get("allowed_actions") or []) == ["read"] for item in payload(tasks).get("items") or []))

        onboarding = requests.get(f"{BASE}/dashboard/mobile/onboarding", headers=headers(owner_token), timeout=30)
        onboarding_keys = {(item.get("employee") or {}).get("employee_key") for item in payload(onboarding).get("items") or []}
        check("onboarding list read", employee_a in onboarding_keys, onboarding.text[:400])
        onboarding_detail = requests.get(
            f"{BASE}/dashboard/mobile/onboarding/{employee_a}",
            headers=headers(owner_token),
            timeout=30,
        )
        check("onboarding detail safe", onboarding_detail.status_code == 200 and "storage_url" not in onboarding_detail.text, onboarding_detail.text[:500])

        docs = requests.get(
            f"{BASE}/dashboard/mobile/documents?status=needs_review",
            headers=headers(owner_token),
            timeout=30,
        )
        doc_ids = {item.get("document_id") for item in payload(docs).get("items") or []}
        check("document review list", f"{employee_a}:civil_id" in doc_ids, docs.text[:500])
        check("cross-tenant document excluded", f"{employee_other}:civil_id" not in doc_ids, doc_ids)
        doc_detail = requests.get(
            f"{BASE}/dashboard/mobile/documents/{employee_a}/civil_id",
            headers=headers(owner_token),
            timeout=30,
        )
        check("document detail safe", doc_detail.status_code == 200 and "raw_json" not in doc_detail.text, doc_detail.text[:400])

        attendance = requests.get(
            f"{BASE}/dashboard/mobile/attendance?start_date={today}&end_date={today}",
            headers=headers(owner_token),
            timeout=30,
        )
        attendance_ids = {item.get("attendance_id") for item in payload(attendance).get("items") or []}
        check("attendance list read", fixture["attendance_resolve"] in attendance_ids, attendance.text[:500])
        cross_attendance = requests.get(
            f"{BASE}/dashboard/mobile/attendance/{fixture['attendance_other']}",
            headers=headers(owner_token),
            timeout=30,
        )
        check("cross-tenant attendance hidden", cross_attendance.status_code == 404, cross_attendance.text[:300])

        shifts = requests.get(
            f"{BASE}/dashboard/mobile/shifts?date={today}",
            headers=headers(owner_token),
            timeout=30,
        )
        check(
            "day-scoped shifts",
            shifts.status_code == 200
            and payload(shifts).get("start_date") == today.isoformat()
            and payload(shifts).get("end_date") == today.isoformat(),
            shifts.text[:500],
        )
        swaps = requests.get(
            f"{BASE}/dashboard/mobile/shift-swaps",
            headers=headers(owner_token),
            timeout=30,
        )
        swap_ids = {item.get("swap_id") for item in payload(swaps).get("items") or []}
        check("shift-swap list", fixture["swap_approve"] in swap_ids, swaps.text[:500])
        swap_detail = requests.get(
            f"{BASE}/dashboard/mobile/shift-swaps/{fixture['swap_approve']}",
            headers=headers(owner_token),
            timeout=30,
        )
        check("shift-swap detail omits phones", swap_detail.status_code == 200 and "phone" not in swap_detail.text, swap_detail.text[:500])

        interviews = requests.get(f"{BASE}/dashboard/mobile/interviews", headers=headers(owner_token), timeout=30)
        interview_ids = {item.get("interview_id") for item in payload(interviews).get("items") or []}
        check("interview list read", fixture["interview"] in interview_ids, interviews.text[:500])
        interview_detail = requests.get(
            f"{BASE}/dashboard/mobile/interviews/{fixture['interview']}",
            headers=headers(owner_token),
            timeout=30,
        )
        check("interview detail omits transcript", interview_detail.status_code == 200 and "transcript" not in interview_detail.text, interview_detail.text[:500])

        _, onboarding_confirmed, onboarding_confirm_material = post_confirmed(
            f"/dashboard/mobile/onboarding/{employee_a}/review",
            owner_token,
            {"item_id": "civil_id", "outcome": "received", "note": "HR-3 proof"},
            label="onboarding-review",
        )
        check("onboarding review completes", onboarding_confirmed.status_code == 200 and payload(onboarding_confirmed).get("ok") is True, onboarding_confirmed.text[:2000])
        onboarding_replay = requests.post(
            f"{BASE}/dashboard/mobile/onboarding/{employee_a}/review",
            headers=headers(owner_token),
            json=onboarding_confirm_material,
            timeout=45,
        )
        check(
            "onboarding confirmation replay idempotent",
            onboarding_replay.status_code == 200
            and ((payload(onboarding_replay).get("confirmation") or {}).get("idempotent_replay") is True),
            onboarding_replay.text[:500],
        )

        compliance_review = requests.post(
            f"{BASE}/dashboard/mobile/documents/{employee_a}/civil_id/review",
            headers=headers(owner_token),
            json={"note": "HR-3 staging review", "expected_status": "needs_review"},
            timeout=45,
        )
        check("compliance review audited write", compliance_review.status_code == 200 and payload(compliance_review).get("ok") is True, compliance_review.text[:500])

        _, attendance_confirmed, _ = post_confirmed(
            f"/dashboard/mobile/attendance/{fixture['attendance_resolve']}/resolve",
            owner_token,
            {"status": "present", "notes": "HR-3 correction"},
            label="attendance-resolve",
        )
        check("attendance resolve completes", attendance_confirmed.status_code == 200 and payload(attendance_confirmed).get("ok") is True, attendance_confirmed.text[:500])

        stale_key = f"hr3-attendance-stale-{uuid.uuid4()}"
        stale_prepare = requests.post(
            f"{BASE}/dashboard/mobile/attendance/{fixture['attendance_stale']}/resolve",
            headers=headers(owner_token),
            json={"status": "present", "notes": "stale proof", "idempotency_key": stale_key, "confirm": False},
            timeout=45,
        )
        stale_confirmation = payload(stale_prepare).get("confirmation") or {}
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE attendance_records SET status='completed', updated_at=now() WHERE attendance_id=%s",
                (fixture["attendance_stale"],),
            )
            conn.commit()
        stale_confirm = requests.post(
            f"{BASE}/dashboard/mobile/attendance/{fixture['attendance_stale']}/resolve",
            headers=headers(owner_token),
            json={
                "status": "present",
                "notes": "stale proof",
                "idempotency_key": stale_key,
                "confirm": True,
                "confirmation_id": stale_confirmation.get("confirmation_id"),
                "confirmation_hash": stale_confirmation.get("confirmation_hash"),
            },
            timeout=45,
        )
        check("stale attendance decision rejected", stale_confirm.status_code == 409 and error_code(stale_confirm) == "stale_decision", stale_confirm.text[:500])

        _, swap_approved, _ = post_confirmed(
            f"/dashboard/mobile/shift-swaps/{fixture['swap_approve']}/decision",
            owner_token,
            {"action": "approve"},
            label="swap-approve",
        )
        check("shift swap approve completes", swap_approved.status_code == 200 and payload(swap_approved).get("ok") is True, swap_approved.text[:600])
        _, swap_rejected, _ = post_confirmed(
            f"/dashboard/mobile/shift-swaps/{fixture['swap_reject']}/decision",
            owner_token,
            {"action": "reject"},
            label="swap-reject",
        )
        check("shift swap reject completes", swap_rejected.status_code == 200 and payload(swap_rejected).get("ok") is True, swap_rejected.text[:600])

        swap_stale_key = f"hr3-swap-stale-{uuid.uuid4()}"
        swap_stale_prepare = requests.post(
            f"{BASE}/dashboard/mobile/shift-swaps/{fixture['swap_stale']}/decision",
            headers=headers(owner_token),
            json={"action": "reject", "idempotency_key": swap_stale_key, "confirm": False},
            timeout=45,
        )
        swap_stale_confirmation = payload(swap_stale_prepare).get("confirmation") or {}
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE shift_swap_requests SET status='cancelled', updated_at=now() WHERE swap_id=%s",
                (fixture["swap_stale"],),
            )
            conn.commit()
        swap_stale = requests.post(
            f"{BASE}/dashboard/mobile/shift-swaps/{fixture['swap_stale']}/decision",
            headers=headers(owner_token),
            json={
                "action": "reject",
                "idempotency_key": swap_stale_key,
                "confirm": True,
                "confirmation_id": swap_stale_confirmation.get("confirmation_id"),
                "confirmation_hash": swap_stale_confirmation.get("confirmation_hash"),
            },
            timeout=45,
        )
        check("stale shift-swap decision rejected", swap_stale.status_code == 409 and error_code(swap_stale) in {"stale_decision", "already_decided"}, swap_stale.text[:500])

        notes = requests.post(
            f"{BASE}/dashboard/mobile/interviews/{fixture['interview']}/notes",
            headers=headers(owner_token),
            json={"notes": "Strong verified examples; human review remains required.", "status": "completed", "generate_summary": False},
            timeout=60,
        )
        check("interview notes write", notes.status_code == 200 and ((payload(notes).get("interview") or {}).get("notes_available") is True), notes.text[:600])
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM action_results
                WHERE action_type='interview_feedback'
                  AND result->>'company_code'=%s
                """,
                (COMPANY,),
            )
            note_audits = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT status, payload
                FROM outbound_delivery_events
                WHERE target_phone = ANY(%s)
                  AND subject_type='employee'
                """,
                ([phones["a"], phones["b"]],),
            )
            delivery_rows = [dict(row) for row in cur.fetchall()]
        check("interview notes audit recorded", note_audits >= 1, note_audits)
        check(
            "swap delivery remains dry-run",
            bool(delivery_rows)
            and all(
                row.get("status") == "dry_run"
                and bool((row.get("payload") or {}).get("dry_run"))
                for row in delivery_rows
            ),
            delivery_rows,
        )

        manager_tasks = requests.get(
            f"{BASE}/dashboard/mobile/tasks",
            headers=headers(manager_token),
            timeout=30,
        )
        manager_task_ids = {item.get("task_id") for item in payload(manager_tasks).get("items") or []}
        check("manager sees in-scope task", fixture[f"task_{employee_a}"] in manager_task_ids, manager_task_ids)
        check("manager excludes out-of-scope task", fixture[f"task_{employee_b}"] not in manager_task_ids, manager_task_ids)
        manager_attendance = requests.get(
            f"{BASE}/dashboard/mobile/attendance/{fixture['attendance_stale']}",
            headers=headers(manager_token),
            timeout=30,
        )
        check("manager out-of-scope detail hidden", manager_attendance.status_code == 404, manager_attendance.text[:300])

        browser_user = app.dashboard_user_by_email(COMPANY, "owner@hr3.staging.test") or {}
        browser_token, _ = app.create_dashboard_session(browser_user)
        browser_rejected = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers=headers(browser_token),
            timeout=30,
        )
        check("browser channel rejected", browser_rejected.status_code == 401 and error_code(browser_rejected) == "browser_session_rejected", browser_rejected.text[:300])
        employee_session = app.create_employee_session(COMPANY, employee_a, phones["a"])
        employee_rejected = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers=headers(str(employee_session.get("token") or "")),
            timeout=30,
        )
        check("employee channel rejected", employee_rejected.status_code == 401 and error_code(employee_rejected) == "employee_token_rejected", employee_rejected.text[:300])
        legacy = app.dashboard_configured_token()
        if legacy:
            legacy_rejected = requests.get(
                f"{BASE}/dashboard/mobile/me",
                headers=headers(legacy),
                timeout=30,
            )
            check("legacy authority rejected", legacy_rejected.status_code == 401 and error_code(legacy_rejected) == "legacy_authority_rejected", legacy_rejected.text[:300])
        else:
            check("legacy authority rejected", True, "no shared legacy token configured")

        revoke = app.set_dashboard_user_permission_grant(
            COMPANY,
            users["viewer"],
            "employees.read",
            active=False,
            actor_user_id=users["owner"],
            reason="HR-3 revocation proof",
            review_reference="HR-3",
        )
        check("viewer employees.read grant revoked", revoke.get("ok") is True, revoke)
        revoked = requests.get(
            f"{BASE}/dashboard/mobile/employees",
            headers=headers(viewer_token),
            timeout=30,
        )
        check("grant revocation applies next request", revoked.status_code == 403, revoked.text[:300])

        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE company_modules SET enabled=false, updated_at=now() WHERE company_code=%s AND module_key='shifts'",
                (COMPANY,),
            )
            conn.commit()
        module_blocked = requests.get(
            f"{BASE}/dashboard/mobile/shifts?date={today}",
            headers=headers(owner_token),
            timeout=30,
        )
        check("module disable applies next request", module_blocked.status_code == 403 and error_code(module_blocked) == "module_disabled", module_blocked.text[:300])
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE company_modules SET enabled=true, updated_at=now() WHERE company_code=%s AND module_key='shifts'",
                (COMPANY,),
            )
            cur.execute(
                "UPDATE companies SET status='disabled', updated_at=now() WHERE company_code=%s",
                (COMPANY,),
            )
            conn.commit()
        company_blocked = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers=headers(owner_token),
            timeout=30,
        )
        check("company disable applies next request", company_blocked.status_code == 403 and error_code(company_blocked) == "company_disabled", company_blocked.text[:300])
    finally:
        cleanup()

    print(f"\nHR-3 staging: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
