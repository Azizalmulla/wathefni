#!/usr/bin/env python3
"""DB-backed HR-2 staging verifier.

Seeds isolated temporary tenants and proves mobile data authority, scope,
confirmation/idempotency, stale conflicts, CV audit, revocation and lifecycle.
Production is never touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid
from datetime import timedelta
from typing import Any

import requests


PASS = 0
FAIL = 0
COMPANY = "HR2MOB"
OTHER = "HR2OTH"
MARKER = "temporary_hr2_staging_harness"
BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")


def check(label: str, condition: bool, detail: Any = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" :: {detail}" if detail is not None else ""))


def body(response: requests.Response) -> dict[str, Any]:
    try:
        value = response.json()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def error_code(response: requests.Response) -> str:
    value = body(response)
    detail = value.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("error") or "")
    return str(value.get("error") or "")


def main() -> int:
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")

    staging_orch = os.environ.get("WATHEFNI_STAGING_ORCH", "/opt/wathefni/staging/orchestrator")
    sys.path = [path for path in sys.path if path not in {staging_orch, "/opt/wathefni/orchestrator"}]
    sys.path.insert(0, staging_orch)
    import app
    import operator_mobile_data as mobile_data

    if not str(getattr(app, "__file__", "")).startswith(staging_orch):
        raise RuntimeError(f"HR-2 must import staging app.py, got {app.__file__}")

    app.ensure_schema(force=True)
    mobile_data.ensure_operator_mobile_data_schema(app)
    print(f"HR-2 staging verify — {COMPANY} against {BASE}")

    password = f"Hr2-{uuid.uuid4().hex[:12]}!"
    users = {
        "owner": str(uuid.uuid4()),
        "manager": str(uuid.uuid4()),
        "viewer": str(uuid.uuid4()),
        "other": str(uuid.uuid4()),
    }
    phones = {
        "owner": "965500290001",
        "manager": "965500290002",
        "viewer": "965500290003",
        "other": "965500290099",
        "emp_a": "965500291001",
        "emp_b": "965500291002",
        "emp_other": "965500291099",
        "candidate": "965500292001",
        "candidate_reject": "965500292002",
        "candidate_hire": "965500292003",
    }
    branch = app.org_key(COMPANY, "branch", "HQ")
    team_a = app.org_key(COMPANY, "team", "Team A")
    team_b = app.org_key(COMPANY, "team", "Team B")
    employee_a = "hr2-emp-a"
    employee_b = "hr2-emp-b"
    other_employee = "hr2-emp-other"
    candidate_app_keys = {
        "shortlist": f"{phones['candidate']}-{COMPANY}-HR2_DESIGN",
        "reject": f"{phones['candidate_reject']}-{COMPANY}-HR2_DESIGN",
        "hire": f"{phones['candidate_hire']}-{COMPANY}-HR2_DESIGN",
    }
    app_key = candidate_app_keys["shortlist"]
    leave_ids: dict[str, str] = {}

    def cleanup() -> None:
        with app.db_connect() as conn, conn.cursor() as cur:
            employee_keys = [
                employee_a,
                employee_b,
                other_employee,
                f"{COMPANY}-{phones['candidate_hire']}",
            ]
            cur.execute(
                "DELETE FROM action_results WHERE result->>'company_code' = ANY(%s) OR result->>'company_id' = ANY(%s)",
                ([COMPANY, OTHER], [COMPANY, OTHER]),
            )
            cur.execute(
                "DELETE FROM outbound_delivery_events WHERE account_id = ANY(%s) OR payload->>'company_code' = ANY(%s)",
                ([COMPANY, OTHER], [COMPANY, OTHER]),
            )
            cur.execute("DELETE FROM pending_actions WHERE account_id = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM dashboard_operator_mobile_confirmations WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM dashboard_operator_mobile_sessions WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM dashboard_user_sessions WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM dashboard_user_permission_grants WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM leave_requests WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM employee_org_assignments WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM manager_scope_members WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM manager_scopes WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM company_teams WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM company_branches WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
            cur.execute("DELETE FROM onboarding_items WHERE employee_key = ANY(%s)", (employee_keys,))
            cur.execute("DELETE FROM employee_documents WHERE employee_key = ANY(%s)", (employee_keys,))
            cur.execute("DELETE FROM compliance_documents WHERE employee_key = ANY(%s)", (employee_keys,))
            cur.execute(
                """
                SELECT employee_key
                FROM employees
                WHERE employee_key='WATHEFNI-'
                  AND company_code='WATHEFNI'
                  AND COALESCE(phone,'')=''
                  AND name='Hessa HR2'
                  AND app_key IS NULL
                """
            )
            if cur.fetchone():
                for table in ("onboarding_items", "employee_documents", "compliance_documents"):
                    cur.execute(f"DELETE FROM {table} WHERE employee_key='WATHEFNI-'")
                cur.execute("DELETE FROM employees WHERE employee_key='WATHEFNI-'")
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
        malformed_root = Path(app.WORKSPACE) / "data" / "companies" / "WATHEFNI" / "employees"
        malformed_employee = malformed_root / "employee.json"
        if malformed_employee.is_file():
            data = json.loads(malformed_employee.read_text())
            if data.get("employee_key") == "WATHEFNI-" and data.get("name") == "Hessa HR2":
                for filename in ("employee.json", "onboarding.json", "compliance.json"):
                    path = malformed_root / filename
                    if path.is_file():
                        path.unlink()

    def login(email: str, company: str = COMPANY) -> tuple[requests.Response, dict[str, Any]]:
        response = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": email, "password": password, "company_code": company},
            timeout=30,
        )
        return response, body(response)

    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    cleanup()
    try:
        today = app.kuwait_today()
        with app.db_connect() as conn, conn.cursor() as cur:
            for company in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, status, metadata)
                    VALUES (%s,%s,'active',%s)
                    """,
                    (company, company, app.Json({"marker": MARKER})),
                )
                for module in ("leave", "pre_hiring", "onboarding", "compliance", "attendance", "shifts"):
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

            add_user("owner", COMPANY, "owner@hr2.staging.test", "owner", phones["owner"])
            add_user("manager", COMPANY, "manager@hr2.staging.test", "manager", phones["manager"])
            add_user("viewer", COMPANY, "viewer@hr2.staging.test", "viewer", phones["viewer"])
            add_user("other", OTHER, "owner@hr2oth.staging.test", "owner", phones["other"])

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

            employees = [
                (COMPANY, employee_a, phones["emp_a"], "Aisha Scope A", "Operations"),
                (COMPANY, employee_b, phones["emp_b"], "Bader Scope B", "Finance"),
                (OTHER, other_employee, phones["emp_other"], "Other Tenant", "Other"),
            ]
            for company, employee_key, phone, name, department in employees:
                cur.execute(
                    """
                    INSERT INTO employees
                      (company_code, employee_key, phone, name,
                       position_title, employment_status, raw_json, updated_at)
                    VALUES (%s,%s,%s,%s,'Specialist','active',%s,now())
                    """,
                    (
                        company,
                        employee_key,
                        phone,
                        name,
                        app.Json({"marker": MARKER, "department": department}),
                    ),
                )
            for employee_key, team in ((employee_a, team_a), (employee_b, team_b)):
                cur.execute(
                    """
                    INSERT INTO employee_org_assignments
                      (company_code, employee_key, branch_key, team_key, is_primary, updated_at)
                    VALUES (%s,%s,%s,%s,true,now())
                    """,
                    (COMPANY, employee_key, branch, team),
                )

            for key, company, employee_key, phone, name in (
                ("approve", COMPANY, employee_a, phones["emp_a"], "Aisha Scope A"),
                ("stale", COMPANY, employee_b, phones["emp_b"], "Bader Scope B"),
                ("other", OTHER, other_employee, phones["emp_other"], "Other Tenant"),
            ):
                cur.execute(
                    """
                    INSERT INTO leave_requests
                      (company_code, employee_key, employee_phone, employee_name,
                       start_date, end_date, leave_type, status, reason, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,'annual','requested',%s,%s)
                    RETURNING leave_id
                    """,
                    (
                        company,
                        employee_key,
                        phone,
                        name,
                        today + timedelta(days=7),
                        today + timedelta(days=9),
                        f"{MARKER}:{key}",
                        app.Json({"marker": MARKER}),
                    ),
                )
                leave_ids[key] = str(cur.fetchone()["leave_id"])

            for action, phone, name in (
                ("shortlist", phones["candidate"], "Lina HR2"),
                ("reject", phones["candidate_reject"], "Rana HR2"),
                ("hire", phones["candidate_hire"], "Hessa HR2"),
            ):
                cur.execute(
                    """
                    INSERT INTO candidates
                      (phone, name, email, active_company_code, data_source, raw_json, updated_at)
                    VALUES (%s,%s,%s,%s,'production',%s,now())
                    """,
                    (
                        phone,
                        name,
                        f"{action}@hr2.staging.test",
                        COMPANY,
                        app.Json({"marker": MARKER, "action": action}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO applications
                      (app_key, company_code, phone, position_code, position_title,
                       status, data_source, cv_received, raw_json, updated_at)
                    VALUES (%s,%s,%s,'HR2_DESIGN','Senior Designer',
                            'review_pending','production',true,%s,now())
                    """,
                    (
                        candidate_app_keys[action],
                        COMPANY,
                        phone,
                        app.Json(
                            {
                                "marker": MARKER,
                                "candidate_name": name,
                                "phone": phone,
                                "company_code": COMPANY,
                                "position_code": "HR2_DESIGN",
                                "position_title": "Senior Designer",
                                "cv": {
                                    "filename": "hr2-missing.pdf",
                                    "path": "/tmp/hr2-missing.pdf",
                                    "storage": {"mime_type": "application/pdf", "status": "missing"},
                                },
                            }
                        ),
                    ),
                )
            conn.commit()

        for permission in ("leave.read", "leave.decide", "employees.read"):
            result = app.set_dashboard_user_permission_grant(
                COMPANY,
                users["viewer"],
                permission,
                active=True,
                actor_user_id=users["owner"],
                reason="hr2 staging verifier",
                review_reference="HR-2",
            )
            check(f"viewer grant {permission}", result.get("ok") is True, result)

        owner_login, owner_body = login("owner@hr2.staging.test")
        manager_login, manager_body = login("manager@hr2.staging.test")
        viewer_login, viewer_body = login("viewer@hr2.staging.test")
        check("owner operator login", owner_login.status_code == 200, owner_login.text[:200])
        check("manager operator login", manager_login.status_code == 200, manager_login.text[:200])
        check("viewer operator login", viewer_login.status_code == 200, viewer_login.text[:200])
        owner_token = str(owner_body.get("access_token") or "")
        manager_token = str(manager_body.get("access_token") or "")
        viewer_token = str(viewer_body.get("access_token") or "")

        me = requests.get(f"{BASE}/dashboard/mobile/me", headers=auth(owner_token), timeout=30)
        check("/me backend-current", me.status_code == 200 and body(me).get("permission_authority") == "backend_current", me.text[:200])
        rec = (((body(me).get("workspaces") or {}).get("recruiting") or {}).get("features") or {})
        check("shortlist confirmation advertised", (rec.get("candidate_shortlist") or {}).get("confirmation_required") is True, rec.get("candidate_shortlist"))

        priorities = requests.get(f"{BASE}/dashboard/mobile/priorities", headers=auth(owner_token), timeout=60)
        priority_types = {section.get("type") for section in body(priorities).get("sections") or []}
        check("priorities mobile read", priorities.status_code == 200, priorities.text[:300])
        check("priorities include leave section", "leave_approvals" in priority_types, priority_types)
        check("priorities include candidate decisions", "candidate_decisions" in priority_types, priority_types)

        leave_list = requests.get(f"{BASE}/dashboard/mobile/leave", headers=auth(owner_token), timeout=30)
        listed_ids = {item.get("leave_id") for item in body(leave_list).get("items") or []}
        check("owner pending leave read", leave_list.status_code == 200 and leave_ids["approve"] in listed_ids, leave_list.text[:300])
        check("cross-tenant leave excluded", leave_ids["other"] not in listed_ids, listed_ids)
        cross = requests.get(
            f"{BASE}/dashboard/mobile/leave/{leave_ids['other']}",
            headers=auth(owner_token),
            timeout=30,
        )
        check("cross-tenant leave detail hidden", cross.status_code == 404, cross.text[:200])

        manager_list = requests.get(f"{BASE}/dashboard/mobile/leave", headers=auth(manager_token), timeout=30)
        manager_ids = {item.get("leave_id") for item in body(manager_list).get("items") or []}
        check("manager sees assigned team leave", leave_ids["approve"] in manager_ids, manager_ids)
        check("manager list excludes other team", leave_ids["stale"] not in manager_ids, manager_ids)
        manager_denied = requests.get(
            f"{BASE}/dashboard/mobile/leave/{leave_ids['stale']}",
            headers=auth(manager_token),
            timeout=30,
        )
        check("manager detail outside scope hidden", manager_denied.status_code == 404, manager_denied.text[:200])

        decision_key = f"hr2-leave-{uuid.uuid4()}"
        prepare = requests.post(
            f"{BASE}/dashboard/mobile/leave/{leave_ids['approve']}/decision",
            headers=auth(owner_token),
            json={"action": "approve", "idempotency_key": decision_key, "confirm": False},
            timeout=30,
        )
        prepared = body(prepare)
        confirmation = prepared.get("confirmation") or {}
        check("leave prepare needs explicit confirmation", prepare.status_code == 200 and prepared.get("status") == "needs_confirmation", prepare.text[:300])
        confirm_payload = {
            "action": "approve",
            "idempotency_key": decision_key,
            "confirm": True,
            "confirmation_id": confirmation.get("confirmation_id"),
            "confirmation_hash": confirmation.get("confirmation_hash"),
        }
        confirmed = requests.post(
            f"{BASE}/dashboard/mobile/leave/{leave_ids['approve']}/decision",
            headers=auth(owner_token),
            json=confirm_payload,
            timeout=60,
        )
        check("leave confirmation completes", confirmed.status_code == 200 and body(confirmed).get("ok") is True, confirmed.text[:400])
        replay = requests.post(
            f"{BASE}/dashboard/mobile/leave/{leave_ids['approve']}/decision",
            headers=auth(owner_token),
            json=confirm_payload,
            timeout=30,
        )
        check(
            "leave confirmation replay is idempotent",
            replay.status_code == 200
            and (body(replay).get("confirmation") or {}).get("idempotent_replay") is True,
            replay.text[:300],
        )

        stale_key = f"hr2-stale-{uuid.uuid4()}"
        stale_prepare = requests.post(
            f"{BASE}/dashboard/mobile/leave/{leave_ids['stale']}/decision",
            headers=auth(owner_token),
            json={"action": "reject", "reason": "Harness stale check", "idempotency_key": stale_key, "confirm": False},
            timeout=30,
        )
        stale_confirmation = body(stale_prepare).get("confirmation") or {}
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE leave_requests SET status='approved', updated_at=now() WHERE leave_id=%s",
                (leave_ids["stale"],),
            )
            conn.commit()
        stale = requests.post(
            f"{BASE}/dashboard/mobile/leave/{leave_ids['stale']}/decision",
            headers=auth(owner_token),
            json={
                "action": "reject",
                "reason": "Harness stale check",
                "idempotency_key": stale_key,
                "confirm": True,
                "confirmation_id": stale_confirmation.get("confirmation_id"),
                "confirmation_hash": stale_confirmation.get("confirmation_hash"),
            },
            timeout=30,
        )
        check("stale leave decision rejected", stale.status_code == 409 and error_code(stale) == "stale_decision", stale.text[:300])

        candidate = requests.get(
            f"{BASE}/dashboard/mobile/candidates/{app_key}",
            headers=auth(owner_token),
            timeout=30,
        )
        check("candidate detail mobile read", candidate.status_code == 200, candidate.text[:300])
        check("candidate response advisory", ((body(candidate).get("candidate") or {}).get("ranking") or {}).get("ai_advisory") is True)
        cv = requests.get(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/cv/preview",
            headers=auth(owner_token),
            timeout=30,
        )
        check("missing CV preview fails safely", cv.status_code == 404, cv.text[:200])
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM action_results
                WHERE action_type LIKE 'candidate_cv_%%'
                  AND result->'action'->>'target'=%s
                """,
                (app_key,),
            )
            cv_audits = int((cur.fetchone() or {}).get("n") or 0)
        check("candidate CV attempt audited", cv_audits >= 1, cv_audits)

        candidate_key = f"hr2-candidate-{uuid.uuid4()}"
        candidate_prepare = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(owner_token),
            json={"action": "shortlist", "reason": "Harness review", "idempotency_key": candidate_key, "confirm": False},
            timeout=30,
        )
        candidate_confirmation = body(candidate_prepare).get("confirmation") or {}
        check("candidate shortlist requires confirmation", body(candidate_prepare).get("status") == "needs_confirmation", candidate_prepare.text[:300])
        candidate_confirm = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(owner_token),
            json={
                "action": "shortlist",
                "reason": "Harness review",
                "idempotency_key": candidate_key,
                "confirm": True,
                "confirmation_id": candidate_confirmation.get("confirmation_id"),
                "confirmation_hash": candidate_confirmation.get("confirmation_hash"),
            },
            timeout=60,
        )
        candidate_result = ((body(candidate_confirm).get("result") or {}).get("result") or {})
        check(
            "candidate shortlist completes through registry",
            candidate_confirm.status_code == 200 and body(candidate_confirm).get("ok") is True,
            candidate_result.get("update") or candidate_confirm.text[:500],
        )
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM applications WHERE app_key=%s", (app_key,))
            candidate_status = str((cur.fetchone() or {}).get("status") or "")
        check("candidate status backend-authoritative", candidate_status == "shortlisted", candidate_status)

        def confirm_candidate_decision(action: str) -> requests.Response:
            target = candidate_app_keys[action]
            key = f"hr2-candidate-{action}-{uuid.uuid4()}"
            prepared_response = requests.post(
                f"{BASE}/dashboard/mobile/candidates/{target}/decision",
                headers=auth(owner_token),
                json={
                    "action": action,
                    "reason": f"HR-2 staging {action} isolation proof",
                    "idempotency_key": key,
                    "confirm": False,
                },
                timeout=30,
            )
            prepared_body = body(prepared_response)
            prepared_confirmation = prepared_body.get("confirmation") or {}
            check(
                f"candidate {action} requires confirmation",
                prepared_response.status_code == 200 and prepared_body.get("status") == "needs_confirmation",
                prepared_response.text[:400],
            )
            return requests.post(
                f"{BASE}/dashboard/mobile/candidates/{target}/decision",
                headers=auth(owner_token),
                json={
                    "action": action,
                    "reason": f"HR-2 staging {action} isolation proof",
                    "idempotency_key": key,
                    "confirm": True,
                    "confirmation_id": prepared_confirmation.get("confirmation_id"),
                    "confirmation_hash": prepared_confirmation.get("confirmation_hash"),
                },
                timeout=90,
            )

        rejected = confirm_candidate_decision("reject")
        check(
            "candidate reject completes in staging",
            rejected.status_code == 200 and body(rejected).get("ok") is True,
            rejected.text[:500],
        )
        hired = confirm_candidate_decision("hire")
        check(
            "candidate hire completes in staging",
            hired.status_code == 200 and body(hired).get("ok") is True,
            hired.text[:500],
        )
        hire_registry_result = ((body(hired).get("result") or {}).get("result") or {})
        hire_posthire = hire_registry_result.get("posthire") or {}
        hire_sheet_sync = (hire_posthire.get("json") or {}).get("sheet_sync") or {}
        check(
            "staging candidate hire suppresses external sheet sync",
            hire_sheet_sync.get("attempted") is False,
            hire_sheet_sync,
        )
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT app_key, status FROM applications WHERE app_key = ANY(%s)",
                (list(candidate_app_keys.values()),),
            )
            statuses = {str(row["app_key"]): str(row["status"]) for row in cur.fetchall()}
            cur.execute(
                "SELECT count(*) AS n FROM employees WHERE company_code=%s AND phone=%s",
                (COMPANY, phones["candidate_hire"]),
            )
            staging_hire_employees = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*) AS n
                FROM action_results
                WHERE action_type = ANY(%s)
                  AND result->>'company_code'=%s
                """,
                (["shortlist_candidate", "reject_candidate", "hire_candidate"], COMPANY),
            )
            candidate_audits = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*) AS n
                FROM outbound_delivery_events
                WHERE target_phone = ANY(%s)
                   OR subject_key = ANY(%s)
                """,
                (
                    [
                        phones["candidate"],
                        phones["candidate_reject"],
                        phones["candidate_hire"],
                    ],
                    list(candidate_app_keys.values()),
                ),
            )
            candidate_notifications = int((cur.fetchone() or {}).get("n") or 0)
        check("candidate reject status remains in staging", statuses.get(candidate_app_keys["reject"]) == "rejected", statuses)
        check("candidate hire status remains in staging", statuses.get(candidate_app_keys["hire"]) == "hired", statuses)
        check("candidate hire provisions staging employee", staging_hire_employees == 1, staging_hire_employees)
        check("candidate decisions remain audited in staging", candidate_audits >= 3, candidate_audits)
        check("candidate decisions emit no external notifications", candidate_notifications == 0, candidate_notifications)

        viewer_before = requests.get(f"{BASE}/dashboard/mobile/employees", headers=auth(viewer_token), timeout=30)
        check("viewer grant-only employee search works", viewer_before.status_code == 200, viewer_before.text[:200])
        revoke = app.set_dashboard_user_permission_grant(
            COMPANY,
            users["viewer"],
            "employees.read",
            active=False,
            actor_user_id=users["owner"],
            reason="hr2 staging revocation",
            review_reference="HR-2",
        )
        check("viewer employees.read grant revoked", revoke.get("ok") is True, revoke)
        viewer_after = requests.get(f"{BASE}/dashboard/mobile/employees", headers=auth(viewer_token), timeout=30)
        check("grant revocation affects next request", viewer_after.status_code == 403, viewer_after.text[:200])

        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE company_modules SET enabled=false, updated_at=now() WHERE company_code=%s AND module_key='leave'",
                (COMPANY,),
            )
            conn.commit()
        module_removed = requests.get(f"{BASE}/dashboard/mobile/leave", headers=auth(owner_token), timeout=30)
        check("module removal affects next request", module_removed.status_code == 403 and error_code(module_removed) == "module_disabled", module_removed.text[:200])
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE company_modules SET enabled=true, updated_at=now() WHERE company_code=%s AND module_key='leave'",
                (COMPANY,),
            )
            conn.commit()

        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE companies SET status='disabled', updated_at=now() WHERE company_code=%s", (COMPANY,))
            conn.commit()
        company_disabled = requests.get(f"{BASE}/dashboard/mobile/me", headers=auth(owner_token), timeout=30)
        check("company disable blocks next request", company_disabled.status_code == 403 and error_code(company_disabled) == "company_disabled", company_disabled.text[:200])
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE companies SET status='active', updated_at=now() WHERE company_code=%s", (COMPANY,))
            conn.commit()

        refreshed_login, refreshed_body = login("owner@hr2.staging.test")
        refresh_token = str(refreshed_body.get("refresh_token") or "")
        refreshed = requests.post(
            f"{BASE}/dashboard/mobile/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=30,
        )
        check("operator refresh rotates", refreshed_login.status_code == 200 and refreshed.status_code == 200, refreshed.text[:200])
        rotated = body(refreshed)
        logout = requests.post(
            f"{BASE}/dashboard/mobile/auth/logout",
            headers=auth(str(rotated.get("access_token") or "")),
            json={"refresh_token": rotated.get("refresh_token")},
            timeout=30,
        )
        check("operator logout", logout.status_code == 200, logout.text[:200])
        logged_out = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers=auth(str(rotated.get("access_token") or "")),
            timeout=30,
        )
        check("logged-out access rejected", logged_out.status_code == 401, logged_out.text[:200])
    finally:
        cleanup()

    print(f"\nHR-2 staging: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
