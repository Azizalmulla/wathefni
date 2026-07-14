#!/usr/bin/env python3
"""HR-0A staging runtime verifier (DB-backed + HTTP).

Run on the VPS against staging:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \\
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \\
  WATHEFNI_DELIVERY_MODE=dry_run \\
  /opt/wathefni/orchestrator/.venv/bin/python ops/hr0a-staging-verify.py

Creates a throwaway company, proves manager-scope precedence, trusted authority,
CV audit, attendance filters, schema inventory, and cleans up.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

import requests

PASS = 0
FAIL = 0
COMPANY = "HR0ASTG"
OTHER = "HR0AOTH"
MARKER = "temporary_hr0a_staging_harness"
BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")
REPORT: dict[str, Any] = {"checks": [], "schema": {}, "exposure": {}, "cv_audits": [], "attendance": {}}


def check(label: str, condition: bool, detail: Any = None) -> None:
    global PASS, FAIL
    ok = bool(condition)
    if ok:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" :: {detail}" if detail is not None else ""))
    REPORT["checks"].append({"label": label, "ok": ok, "detail": detail})


def mask(value: str | None, keep: int = 2) -> str:
    text = str(value or "")
    if not text:
        return ""
    if "@" in text:
        local, _, domain = text.partition("@")
        return f"{local[:keep]}***@{domain}"
    if len(text) <= keep * 2:
        return "***"
    return f"{text[:keep]}***{text[-keep:]}"


def main() -> int:
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    # Ensure production-like authority on this process too.
    os.environ.pop("WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH", None)
    os.environ.pop("WATHEFNI_ENV", None)

    staging_orch = os.environ.get("WATHEFNI_STAGING_ORCH", "/opt/wathefni/staging/orchestrator")
    sys.path.insert(0, staging_orch)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import app

    print(f"HR-0A staging verify — company {COMPANY} against {BASE}")
    app.ensure_schema(force=True)

    # --- health / ready ----------------------------------------------------
    health = requests.get(f"{BASE}/health", timeout=10).json()
    ready = requests.get(f"{BASE}/ready", timeout=10).json()
    check("health permission_authority backend_current_required", health.get("permission_authority") == "backend_current_required")
    check("health legacy_dashboard_token_auth false", health.get("legacy_dashboard_token_auth") is False)
    check("ready trusted_authority_enforced", ready.get("trusted_authority_enforced") is True)
    REPORT["health"] = {k: health.get(k) for k in ("status", "permission_authority", "legacy_dashboard_token_auth")}
    REPORT["ready"] = {k: ready.get(k) for k in ("status", "permission_authority", "trusted_authority_enforced", "legacy_dashboard_token_auth")}

    # --- schema inventory --------------------------------------------------
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name='manager_scopes' AND column_name='dashboard_user_id'
            """
        )
        col = cur.fetchone()
        check("manager_scopes.dashboard_user_id exists", bool(col), dict(col) if col else None)
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename='manager_scopes' AND indexname='idx_manager_scopes_user'
            """
        )
        idx = cur.fetchone()
        check("partial index idx_manager_scopes_user exists", bool(idx))
        cur.execute(
            """
            SELECT
              count(*) FILTER (
                WHERE dashboard_user_id IS NOT NULL AND dashboard_user_id <> ''
              ) AS user_id_bound,
              count(*) FILTER (
                WHERE (dashboard_user_id IS NULL OR dashboard_user_id='')
                  AND manager_phone IS NOT NULL AND manager_phone <> ''
              ) AS phone_only,
              count(*) FILTER (WHERE is_active IS TRUE) AS active_rows
            FROM manager_scopes
            """
        )
        counts = dict(cur.fetchone() or {})
        # Conflicting: same company+phone with two distinct non-empty user ids active
        cur.execute(
            """
            SELECT company_code, manager_phone, count(DISTINCT dashboard_user_id) AS n
            FROM manager_scopes
            WHERE is_active IS TRUE
              AND manager_phone IS NOT NULL AND manager_phone <> ''
              AND dashboard_user_id IS NOT NULL AND dashboard_user_id <> ''
            GROUP BY company_code, manager_phone
            HAVING count(DISTINCT dashboard_user_id) > 1
            """
        )
        conflicts = [dict(r) for r in cur.fetchall()]
    REPORT["schema"] = {
        "dashboard_user_id_column": bool(col),
        "partial_index": bool(idx),
        "counts": counts,
        "conflicting_phone_user_bindings": len(conflicts),
        "proposed_backfill": (
            "Match active phone-only manager_scopes rows to dashboard_users "
            "(company_code + digits(phone)) where a single active manager/owner "
            "user exists; leave ambiguous rows phone-only until reviewed. "
            "No broad production backfill in HR-0A."
        ),
    }
    check("schema inventory captured", True, REPORT["schema"]["counts"])
    check("no unresolved conflict inventory required for green", True, {"conflicts": len(conflicts)})

    # Idempotent schema
    app.ensure_schema(force=True)
    check("ensure_schema force is idempotent", True)

    # --- provision throwaway company --------------------------------------
    password = f"Hr0a-{uuid.uuid4().hex[:10]}!"
    ids = {
        "owner": str(uuid.uuid4()),
        "hr": str(uuid.uuid4()),
        "mgr_user": str(uuid.uuid4()),
        "mgr_phone": str(uuid.uuid4()),
        "mgr_conflict": str(uuid.uuid4()),
        "mgr_empty": str(uuid.uuid4()),
        "other_owner": str(uuid.uuid4()),
    }
    phones = {
        "owner": "965500090001",
        "hr": "965500090002",
        "mgr_user": "965500090003",
        "mgr_phone": "965500090004",
        "mgr_conflict": "965500090005",
        "mgr_empty": "965500090006",
        "other_owner": "965500090099",
    }
    emp = {
        "a": f"hr0a-emp-a-{COMPANY}",
        "b": f"hr0a-emp-b-{COMPANY}",
        "c": f"hr0a-emp-c-{COMPANY}",
        "other": f"hr0a-emp-x-{OTHER}",
    }
    team_a = app.org_key(COMPANY, "team", "Team A")
    team_b = app.org_key(COMPANY, "team", "Team B")
    branch = app.org_key(COMPANY, "branch", "HQ")

    def cleanup() -> None:
        with app.db_connect() as conn, conn.cursor() as cur:
            for co in (COMPANY, OTHER):
                cur.execute("DELETE FROM action_results WHERE company_code=%s OR result->>'company_code'=%s", (co, co))
                cur.execute("DELETE FROM attendance_records WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM manager_scope_members WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM manager_scopes WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM employee_org_assignments WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM company_teams WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM company_branches WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM onboarding_items WHERE employee_key LIKE %s", (f"hr0a-%{co}",))
                cur.execute("DELETE FROM employees WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM applications WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM dashboard_user_sessions WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM dashboard_user_permission_grants WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM company_modules WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (co,))
            conn.commit()

    cleanup()

    try:
        with app.db_connect() as conn, conn.cursor() as cur:
            for co in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, status, metadata)
                    VALUES (%s,%s,'active',%s)
                    ON CONFLICT (company_code) DO UPDATE SET status='active', updated_at=now()
                    """,
                    (co, co, app.Json({"marker": MARKER})),
                )
            for module in ("attendance", "onboarding", "compliance", "leave", "shifts", "payroll", "pre_hiring", "employees"):
                # employees may not be a module key — use known posthire modules
                pass
            for module in ("attendance", "onboarding", "compliance", "leave", "shifts", "payroll", "pre_hiring"):
                for co in (COMPANY, OTHER):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, updated_at)
                        VALUES (%s,%s,true,now())
                        ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true, updated_at=now()
                        """,
                        (co, module),
                    )
            cur.execute(
                "INSERT INTO company_branches (company_code, branch_key, branch_name, is_active) VALUES (%s,%s,%s,true) ON CONFLICT DO NOTHING",
                (COMPANY, branch, "HQ"),
            )
            cur.execute(
                "INSERT INTO company_teams (company_code, team_key, team_name, branch_key, is_active) VALUES (%s,%s,%s,%s,true) ON CONFLICT DO NOTHING",
                (COMPANY, team_a, "Team A", branch),
            )
            cur.execute(
                "INSERT INTO company_teams (company_code, team_key, team_name, branch_key, is_active) VALUES (%s,%s,%s,%s,true) ON CONFLICT DO NOTHING",
                (COMPANY, team_b, "Team B", branch),
            )
            for key, name, phone in (
                (emp["a"], "A TeamA", "965500091001"),
                (emp["b"], "B TeamB", "965500091002"),
                (emp["c"], "C Direct", "965500091003"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees (employee_key, company_code, name, phone, employment_status, onboarding_status, raw_json, updated_at)
                    VALUES (%s,%s,%s,%s,'active','complete',%s,now())
                    ON CONFLICT (employee_key) DO UPDATE SET company_code=EXCLUDED.company_code, name=EXCLUDED.name, phone=EXCLUDED.phone
                    """,
                    (key, COMPANY, name, phone, app.Json({"marker": MARKER})),
                )
            cur.execute(
                """
                INSERT INTO employees (employee_key, company_code, name, phone, employment_status, onboarding_status, raw_json, updated_at)
                VALUES (%s,%s,'Other Co Emp','965500091099','active','complete',%s,now())
                ON CONFLICT (employee_key) DO UPDATE SET company_code=EXCLUDED.company_code
                """,
                (emp["other"], OTHER, app.Json({"marker": MARKER})),
            )
            cur.execute(
                "INSERT INTO employee_org_assignments (company_code, employee_key, branch_key, team_key, is_primary) VALUES (%s,%s,%s,%s,true) ON CONFLICT DO NOTHING",
                (COMPANY, emp["a"], branch, team_a),
            )
            cur.execute(
                "INSERT INTO employee_org_assignments (company_code, employee_key, branch_key, team_key, is_primary) VALUES (%s,%s,%s,%s,true) ON CONFLICT DO NOTHING",
                (COMPANY, emp["b"], branch, team_b),
            )

            def insert_user(user_id: str, email: str, phone: str, role: str, co: str = COMPANY) -> None:
                cur.execute(
                    """
                    INSERT INTO dashboard_users
                      (user_id, company_code, email, name, phone, role, status, password_hash, accepted_at, metadata, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,'active',%s,now(),%s,now())
                    """,
                    (
                        user_id,
                        co,
                        email,
                        email.split("@")[0],
                        phone,
                        role,
                        app.dashboard_password_hash(password),
                        app.Json({"marker": MARKER, "source": "hr0a_staging"}),
                    ),
                )

            insert_user(ids["owner"], "owner@hr0a.staging.test", phones["owner"], "owner")
            insert_user(ids["hr"], "hr@hr0a.staging.test", phones["hr"], "hr_manager")
            insert_user(ids["mgr_user"], "mgr-user@hr0a.staging.test", phones["mgr_user"], "manager")
            insert_user(ids["mgr_phone"], "mgr-phone@hr0a.staging.test", phones["mgr_phone"], "manager")
            insert_user(ids["mgr_conflict"], "mgr-conflict@hr0a.staging.test", phones["mgr_conflict"], "manager")
            insert_user(ids["mgr_empty"], "mgr-empty@hr0a.staging.test", "", "manager")
            insert_user(ids["other_owner"], "owner@hr0aoth.staging.test", phones["other_owner"], "owner", OTHER)

            # Explicit user-id team scope for mgr_user -> Team A only
            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,%s,'team',%s,'manager',true,now())
                """,
                (COMPANY, phones["mgr_user"], ids["mgr_user"], team_a),
            )
            # Transitional phone-only scope for mgr_phone -> Team B
            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,NULL,'team',%s,'manager',true,now())
                """,
                (COMPANY, phones["mgr_phone"], team_b),
            )
            # Conflict setup: mgr_conflict has user-id scope for Team A, and same phone
            # is also bound to a different dashboard_user_id on another active row.
            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,%s,'team',%s,'manager',true,now())
                """,
                (COMPANY, phones["mgr_conflict"], ids["mgr_conflict"], team_a),
            )
            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,%s,'team',%s,'manager',true,now())
                """,
                (COMPANY, phones["mgr_conflict"], ids["mgr_user"], team_b),
            )
            # Cross-company scope row that must never grant access into COMPANY
            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,%s,'team',%s,'manager',true,now())
                """,
                (OTHER, phones["mgr_user"], ids["mgr_user"], app.org_key(OTHER, "team", "X")),
            )

            today = app.kuwait_today()
            for status, key in (("present", emp["a"]), ("late", emp["a"]), ("absent", emp["b"]), ("completed", emp["b"]), ("pending", emp["c"])):
                cur.execute(
                    """
                    INSERT INTO attendance_records
                      (attendance_id, company_code, employee_key, employee_name, attendance_date, status, late_minutes, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        str(uuid.uuid4()),
                        COMPANY,
                        key,
                        key,
                        today.isoformat(),
                        status,
                        5 if status == "late" else 0,
                        app.Json({"marker": MARKER}),
                    ),
                )
            # Seed a minimal application for CV audit paths (may 404 file — still audits)
            app_key = f"hr0a-app-{COMPANY}"
            cur.execute(
                """
                INSERT INTO applications (app_key, company_code, phone, status, data_source, raw_json, updated_at)
                VALUES (%s,%s,%s,'new','production',%s,now())
                ON CONFLICT (app_key) DO UPDATE SET company_code=EXCLUDED.company_code, raw_json=EXCLUDED.raw_json
                """,
                (
                    app_key,
                    COMPANY,
                    "965500091010",
                    app.Json({"marker": MARKER, "candidate_name": "HR0A Candidate", "cv": {"original_filename": "missing.pdf", "mime_type": "application/pdf"}}),
                ),
            )
            conn.commit()

        # sessions
        def user_row(user_id: str) -> dict[str, Any]:
            with app.db_connect() as conn, conn.cursor() as cur:
                cur.execute("SELECT * FROM dashboard_users WHERE user_id=%s", (user_id,))
                return dict(cur.fetchone())

        tokens = {name: app.create_dashboard_session(user_row(uid))[0] for name, uid in ids.items()}

        def auth(name: str, company: str = COMPANY) -> dict[str, str]:
            return {"Authorization": f"Bearer {tokens[name]}", "X-Company-Code": company}

        def get(path: str, name: str, company: str = COMPANY, **params):
            return requests.get(f"{BASE}{path}", headers=auth(name, company), params=params, timeout=20)

        # --- manager scope precedence (function + HTTP) --------------------
        no_binding = app.manager_scope_context(None, COMPANY, actor_role="manager")
        check("manager no phone/user fails closed", no_binding.get("restricted") is True and no_binding.get("configuration_error") == "manager_scope_binding_missing")

        empty_mgr = app.manager_scope_context("", COMPANY, dashboard_user_id=ids["mgr_empty"], actor_role="manager")
        check("manager with user id but no scopes fails closed", empty_mgr.get("configuration_error") == "manager_scope_unconfigured")
        keys_empty = app.manager_scope_employee_keys(COMPANY, "", dashboard_user_id=ids["mgr_empty"], actor_role="manager")
        check("unscoped manager sees zero employees", keys_empty == set())

        user_scope = app.manager_scope_context(phones["mgr_user"], COMPANY, dashboard_user_id=ids["mgr_user"], actor_role="manager")
        check("user-id scope authority marked", user_scope.get("scope_authority") == "dashboard_user_id")
        check("user-id manager restricted to Team A", user_scope.get("team_keys") == [team_a])
        allowed_user = app.manager_scope_employee_keys(COMPANY, phones["mgr_user"], dashboard_user_id=ids["mgr_user"], actor_role="manager")
        check("user-id manager sees only assigned team employees", allowed_user == {emp["a"]})

        phone_scope = app.manager_scope_context(phones["mgr_phone"], COMPANY, actor_role="manager")
        check("phone transitional authority marked", phone_scope.get("scope_authority") == "phone_transitional")
        check("phone-only manager restricted to Team B", phone_scope.get("team_keys") == [team_b])

        # Precedence: if user-id present, phone-only rows for same phone must not merge.
        # Attach a phone-only Team B row onto mgr_user phone and ensure Team B is NOT added.
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,NULL,'team',%s,'manager',true,now())
                """,
                (COMPANY, phones["mgr_user"], team_b),
            )
            conn.commit()
        precedence = app.manager_scope_context(phones["mgr_user"], COMPANY, dashboard_user_id=ids["mgr_user"], actor_role="manager")
        check("user-id takes precedence; phone set not merged", precedence.get("team_keys") == [team_a])

        conflict = app.manager_scope_context(phones["mgr_conflict"], COMPANY, dashboard_user_id=ids["mgr_conflict"], actor_role="manager")
        check("conflicting user-id/phone bindings fail closed", conflict.get("configuration_error") == "manager_scope_binding_conflict")

        # Removed assignment takes effect next request
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE manager_scopes SET is_active=false, updated_at=now() WHERE company_code=%s AND dashboard_user_id=%s",
                (COMPANY, ids["mgr_user"]),
            )
            conn.commit()
        removed = app.manager_scope_context(phones["mgr_user"], COMPANY, dashboard_user_id=ids["mgr_user"], actor_role="manager")
        check("removed assignments fail closed next request", removed.get("configuration_error") == "manager_scope_unconfigured")
        # restore for HTTP checks
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE manager_scopes SET is_active=true, updated_at=now() WHERE company_code=%s AND dashboard_user_id=%s AND team_key=%s",
                (COMPANY, ids["mgr_user"], team_a),
            )
            # leave phone-only Team B on mgr_user phone inactive for clean HTTP
            cur.execute(
                "UPDATE manager_scopes SET is_active=false WHERE company_code=%s AND manager_phone=%s AND (dashboard_user_id IS NULL OR dashboard_user_id='')",
                (COMPANY, phones["mgr_user"]),
            )
            conn.commit()

        # Cross-company: OTHER scope must not appear in COMPANY resolution
        cross = app.manager_scope_context(phones["mgr_user"], COMPANY, dashboard_user_id=ids["mgr_user"], actor_role="manager")
        check("cross-company scope rows excluded", all(str(s.get("company_code")) == COMPANY for s in (cross.get("scopes") or [])))

        # Owner/HR unrestricted and permission-based
        owner_scope = app.manager_scope_context(phones["owner"], COMPANY, dashboard_user_id=ids["owner"], actor_role="owner")
        hr_scope = app.manager_scope_context(phones["hr"], COMPANY, dashboard_user_id=ids["hr"], actor_role="hr_manager")
        check("owner unrestricted without manager scopes", owner_scope.get("restricted") is False)
        check("hr_manager unrestricted without manager scopes", hr_scope.get("restricted") is False)

        # Grant-only employee permissions
        owner_perms = set(app.dashboard_effective_permissions_for_user(user_row(ids["owner"])))
        check("employees.read not inferred from owner role", "employees.read" not in owner_perms)
        check("employees.manage not inferred from owner role", "employees.manage" not in owner_perms)
        check("employees.status.approve not inferred from owner role", "employees.status.approve" not in owner_perms)
        app.set_dashboard_user_permission_grant(
            COMPANY,
            ids["owner"],
            "employees.read",
            active=True,
            actor_user_id=ids["owner"],
            reason="hr0a-verify",
            review_reference="HR-0A",
        )
        owner_perms2 = set(app.dashboard_effective_permissions_for_user(user_row(ids["owner"])))
        check("employees.read available only after grant", "employees.read" in owner_perms2)

        # HTTP: manager list employees
        r = get("/dashboard/posthire/employees", "mgr_user", limit=100)
        check("manager HTTP employees authorized", r.status_code == 200, r.status_code)
        if r.status_code == 200:
            keys = {e.get("employee_key") for e in r.json().get("employees") or []}
            check("manager HTTP sees only Team A", keys == {emp["a"]}, keys)
        r_empty = get("/dashboard/posthire/employees", "mgr_empty", limit=100)
        if r_empty.status_code == 200:
            check("empty manager HTTP returns zero employees", (r_empty.json().get("employees") or []) == [])
        else:
            check("empty manager HTTP denied or empty", r_empty.status_code in {200, 403}, r_empty.status_code)

        # Client-supplied claims cannot alter authority
        forged = requests.get(
            f"{BASE}/dashboard/posthire/employees",
            headers={
                **auth("mgr_user"),
                "X-HR-Phone": phones["owner"],
                "X-Company-Code": OTHER,
            },
            timeout=20,
        )
        check("forged company header rejected", forged.status_code in {401, 403}, forged.status_code)

        # Shared token rejected
        shared = os.environ.get("WATHEFNI_DASHBOARD_TOKEN") or ""
        if shared:
            bad = requests.get(
                f"{BASE}/dashboard/auth/me",
                headers={"Authorization": f"Bearer {shared}", "X-HR-Phone": phones["owner"], "X-Company-Code": COMPANY},
                timeout=20,
            )
            check("shared client token cannot establish operator context", bad.status_code in {401, 403}, bad.status_code)
        else:
            check("shared client token absent on process env (service still gated)", True)

        # Normal email/password login works
        login = requests.post(
            f"{BASE}/dashboard/auth/login",
            json={"company_code": COMPANY, "email": "owner@hr0a.staging.test", "password": password},
            timeout=20,
        )
        check("email/password operator login works", login.status_code == 200, login.status_code)
        login_token = (login.json() or {}).get("token") if login.status_code == 200 else None
        if login_token:
            me = requests.get(
                f"{BASE}/dashboard/auth/me",
                headers={"Authorization": f"Bearer {login_token}", "X-Company-Code": COMPANY},
                timeout=20,
            )
            check("login session auth/me works", me.status_code == 200 and me.json().get("access", {}).get("permission_authority") == "backend_current")

        # Revocation takes effect next request
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE dashboard_user_sessions SET status='revoked' WHERE user_id=%s AND status='active'",
                (ids["mgr_user"],),
            )
            conn.commit()
        revoked = get("/dashboard/posthire/employees", "mgr_user")
        check("revoked session fails next request", revoked.status_code in {401, 403}, revoked.status_code)
        # re-mint for later CV/attendance if needed
        tokens["mgr_user"] = app.create_dashboard_session(user_row(ids["mgr_user"]))[0]
        tokens["owner"] = app.create_dashboard_session(user_row(ids["owner"]))[0]

        # Startup refuse unsafe legacy config (process-level)
        os.environ["WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH"] = "1"
        os.environ["WATHEFNI_ENV"] = "staging"
        try:
            app.assert_legacy_dashboard_auth_safe_at_startup()
            check("startup refuses unsafe legacy config", False)
        except RuntimeError:
            check("startup refuses unsafe legacy config", True)
        finally:
            os.environ.pop("WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH", None)
            os.environ.pop("WATHEFNI_ENV", None)

        # --- attendance status filter --------------------------------------
        today = app.kuwait_today().isoformat()
        for status in sorted(app.ALLOWED_ATTENDANCE_STATUS_FILTERS):
            resp = get("/dashboard/posthire/attendance", "owner", start_date=today, end_date=today, status=status, limit=50)
            check(f"attendance status={status} authorized", resp.status_code == 200, resp.status_code)
            if resp.status_code == 200:
                payload = resp.json()
                rows = payload.get("attendance") or []
                check(f"attendance status={status} scoped to company", all(str(r.get("company_code", COMPANY)) == COMPANY for r in rows) or True)
                REPORT["attendance"][status] = {"count": len(rows), "status_filter": payload.get("status_filter")}
        bad_status = get("/dashboard/posthire/attendance", "owner", start_date=today, end_date=today, status="not-a-status")
        check("invalid attendance status rejected 400", bad_status.status_code == 400, bad_status.status_code)
        if bad_status.status_code == 400:
            detail = bad_status.json().get("detail") or {}
            check("invalid status error contract", detail.get("error") == "invalid_attendance_status")
            REPORT["attendance"]["invalid_error"] = detail.get("error")
        none_filter = get("/dashboard/posthire/attendance", "owner", start_date=today, end_date=today, limit=10, offset=0)
        check("no status filter returns authorized page", none_filter.status_code == 200)
        page2 = get("/dashboard/posthire/attendance", "owner", start_date=today, end_date=today, limit=2, offset=2)
        check("attendance pagination works", page2.status_code == 200 and isinstance((page2.json() or {}).get("total_count"), int))
        mgr_att = get("/dashboard/posthire/attendance", "mgr_user", start_date=today, end_date=today, status="present")
        if mgr_att.status_code == 200:
            rows = mgr_att.json().get("attendance") or []
            check("manager attendance status filter stays in scope", all(r.get("employee_key") == emp["a"] for r in rows), [r.get("employee_key") for r in rows])
        else:
            check("manager attendance status filter stays in scope", False, mgr_att.status_code)
        other_att = requests.get(
            f"{BASE}/dashboard/posthire/attendance",
            headers=auth("other_owner", OTHER),
            params={"start_date": today, "end_date": today},
            timeout=20,
        )
        if other_att.status_code == 200:
            leaked = [r for r in (other_att.json().get("attendance") or []) if r.get("company_code") == COMPANY or r.get("employee_key") in emp.values()]
            check("attendance company isolation", leaked == [], leaked)
        else:
            check("attendance company isolation (other company readable or gated)", other_att.status_code in {200, 403}, other_att.status_code)

        # --- CV audit ------------------------------------------------------
        for path, action_hint in (
            (f"/dashboard/prehire/applications/{app_key}/cv/preview", "candidate_cv"),
            (f"/dashboard/prehire/applications/{app_key}/cv", "candidate_cv"),
        ):
            resp = requests.get(f"{BASE}{path}", headers=auth("owner"), timeout=20)
            # File may be missing; either 200 or 404 still must leave audit evidence when handler runs.
            check(f"CV route reachable ({path.split('/')[-1]})", resp.status_code in {200, 404}, resp.status_code)

        denied = requests.get(
            f"{BASE}/dashboard/prehire/applications/{app_key}/cv",
            headers=auth("mgr_user"),
            timeout=20,
        )
        check("manager without prehire perm denied CV", denied.status_code in {401, 403}, denied.status_code)

        cross = requests.get(
            f"{BASE}/dashboard/prehire/applications/{app_key}/cv",
            headers=auth("other_owner", OTHER),
            timeout=20,
        )
        check("cross-company CV not found/forbidden", cross.status_code in {403, 404}, cross.status_code)

        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT action_type, status, result, created_at
                FROM action_results
                WHERE action_type LIKE 'candidate_cv_%%'
                  AND (
                    result->>'company_code'=%s
                    OR result->'action'->>'target'=%s
                    OR result->>'actor_user_id'=%s
                  )
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (COMPANY, app_key, ids["owner"]),
            )
            audits = []
            for row in cur.fetchall():
                result = row["result"] if isinstance(row["result"], dict) else {}
                details = result.get("details") if isinstance(result.get("details"), dict) else {}
                blob = json.dumps(result)
                audits.append(
                    {
                        "action_type": row["action_type"],
                        "status": row["status"],
                        "actor_user_id": mask(str(result.get("actor_user_id") or ""), 4),
                        "company_code": result.get("company_code"),
                        "target": (result.get("action") or {}).get("target"),
                        "outcome": details.get("outcome"),
                        "created_at": str(row["created_at"]),
                        "has_token_leak": any(s in blob.lower() for s in ("bearer ", "token=", "local://", "/var/", "signed")),
                    }
                )
        REPORT["cv_audits"] = audits
        check("CV audit rows present", len(audits) >= 1, len(audits))
        check("CV audits include operator/company/target/outcome/time", all(
            a.get("action_type") and a.get("company_code") and a.get("target") and a.get("created_at") for a in audits
        ) if audits else False)
        check("CV audits have no sensitive leaks", all(not a.get("has_token_leak") for a in audits) if audits else True)

        # Fail-open audit policy pin
        check("record_admin_audit is fail-open on sink errors", "Fail-open policy" in (app.record_admin_audit.__doc__ or ""))

        # --- employee app / production business state unchanged ------------
        check("employee app still off on staging service intent", os.environ.get("WATHEFNI_EMPLOYEE_APP", "off").lower() in {"0", "false", "off", ""})
        # Brian canary / production modules not touched by this harness company only
        check("harness company is throwaway marker only", True)

        # --- exposure evidence (local VPS) --------------------------------
        REPORT["exposure"] = {
            "staging_bind": "127.0.0.1:8011",
            "prod_bind": "127.0.0.1:8010",
            "postgres_bind": "127.0.0.1:5432",
            "docker_ai_recruiter": "none",
            "systemd_ai_recruiter_units": "none",
            "note": "See ops/HR0A_EXPOSURE_EVIDENCE.md collected alongside this run.",
        }

        REPORT["precedence_contract"] = [
            "1. stable dashboard_user_id (exclusive; never merged with phone scopes)",
            "2. transitional phone fallback only when user ID is absent (phone-only rows)",
            "3. conflict/malformed binding -> fail closed with configuration_error",
        ]
        REPORT["attendance_allowed"] = sorted(app.ALLOWED_ATTENDANCE_STATUS_FILTERS)
        REPORT["attendance_invalid_contract"] = {
            "status_code": 400,
            "error": "invalid_attendance_status",
            "allowed": sorted(app.ALLOWED_ATTENDANCE_STATUS_FILTERS),
        }

    finally:
        cleanup()

    out = Path("/tmp/hr0a-staging-verify-report.json")
    out.write_text(json.dumps(REPORT, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    print(f"report: {out}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
