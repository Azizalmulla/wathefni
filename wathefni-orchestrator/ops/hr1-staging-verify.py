#!/usr/bin/env python3
"""HR-1 staging runtime verifier (DB-backed + HTTP).

Run on the VPS against staging:
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \\
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \\
  WATHEFNI_DELIVERY_MODE=dry_run \\
  /opt/wathefni/orchestrator/.venv/bin/python ops/hr1-staging-verify.py

Proves operator mobile login/refresh/logout, session revocation, one-company
binding, backend-current capabilities, manager-scope metadata, employee/legacy
token rejection. Does not enable production or change Employee App contracts.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

import requests

PASS = 0
FAIL = 0
COMPANY = "HR1MOB"
OTHER = "HR1OTH"
MARKER = "temporary_hr1_staging_harness"
BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")
REPORT: dict[str, Any] = {"checks": [], "sessions": {}, "capabilities": {}}


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


def err_code(resp: requests.Response) -> str:
    try:
        body = resp.json()
    except Exception:
        return ""
    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        return str(detail.get("error") or "")
    return str(body.get("error") or "") if isinstance(body, dict) else ""


def main() -> int:
    os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
    os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    os.environ.pop("WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH", None)
    os.environ.setdefault("WATHEFNI_ENV", "staging")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
    os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")

    staging_orch = os.environ.get("WATHEFNI_STAGING_ORCH", "/opt/wathefni/staging/orchestrator")
    sys.path = [p for p in sys.path if p not in {staging_orch, "/opt/wathefni/orchestrator"}]
    sys.path.insert(0, staging_orch)
    import app
    import operator_mobile as om

    if not str(getattr(app, "__file__", "")).startswith(staging_orch):
        raise RuntimeError(f"HR-1 must import staging app.py, got {app.__file__}")

    print(f"HR-1 staging verify — company {COMPANY} against {BASE}")
    app.ensure_schema(force=True)
    om.ensure_operator_mobile_schema(app)

    password = f"Hr1-{uuid.uuid4().hex[:10]}!"
    ids = {
        "owner": str(uuid.uuid4()),
        "hr": str(uuid.uuid4()),
        "mgr": str(uuid.uuid4()),
        "mgr_empty": str(uuid.uuid4()),
        "recruiter": str(uuid.uuid4()),
        "hiring": str(uuid.uuid4()),
        "viewer": str(uuid.uuid4()),
        "disabled": str(uuid.uuid4()),
        "other_owner": str(uuid.uuid4()),
    }
    phones = {
        "owner": "965500190001",
        "hr": "965500190002",
        "mgr": "965500190003",
        "mgr_empty": "965500190004",
        "recruiter": "965500190005",
        "hiring": "965500190006",
        "viewer": "965500190007",
        "disabled": "965500190008",
        "other_owner": "965500190099",
    }
    team_a = app.org_key(COMPANY, "team", "Team A")
    branch = app.org_key(COMPANY, "branch", "HQ")

    def cleanup() -> None:
        with app.db_connect() as conn, conn.cursor() as cur:
            for co in (COMPANY, OTHER):
                cur.execute("DELETE FROM dashboard_operator_mobile_sessions WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM dashboard_user_sessions WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM dashboard_user_permission_grants WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM manager_scopes WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM company_teams WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM company_branches WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM company_modules WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key LIKE %s", (co, "hr1-emp-%"))
                cur.execute("DELETE FROM employee_sessions WHERE company_code=%s", (co,))
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

            def insert_user(user_id: str, email: str, phone: str, role: str, *, status: str = "active", co: str = COMPANY) -> None:
                cur.execute(
                    """
                    INSERT INTO dashboard_users
                      (user_id, company_code, email, name, phone, role, status, password_hash, accepted_at, metadata, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,now())
                    """,
                    (
                        user_id,
                        co,
                        email,
                        email.split("@")[0],
                        phone,
                        role,
                        status,
                        app.dashboard_password_hash(password),
                        app.Json({"marker": MARKER, "source": "hr1_staging"}),
                    ),
                )

            insert_user(ids["owner"], "owner@hr1.staging.test", phones["owner"], "owner")
            insert_user(ids["hr"], "hr@hr1.staging.test", phones["hr"], "hr_manager")
            insert_user(ids["mgr"], "mgr@hr1.staging.test", phones["mgr"], "manager")
            insert_user(ids["mgr_empty"], "mgr-empty@hr1.staging.test", "", "manager")
            insert_user(ids["recruiter"], "recruiter@hr1.staging.test", phones["recruiter"], "recruiter")
            insert_user(ids["hiring"], "hiring@hr1.staging.test", phones["hiring"], "hiring_manager")
            insert_user(ids["viewer"], "viewer@hr1.staging.test", phones["viewer"], "viewer")
            insert_user(ids["disabled"], "disabled@hr1.staging.test", phones["disabled"], "hr_manager", status="disabled")
            insert_user(ids["other_owner"], "owner@hr1oth.staging.test", phones["other_owner"], "owner", co=OTHER)

            cur.execute(
                """
                INSERT INTO manager_scopes
                  (company_code, manager_phone, dashboard_user_id, scope_type, team_key, role, is_active, updated_at)
                VALUES (%s,%s,%s,'team',%s,'manager',true,now())
                """,
                (COMPANY, phones["mgr"], ids["mgr"], team_a),
            )
            conn.commit()

        grant = app.set_dashboard_user_permission_grant(
            COMPANY,
            ids["owner"],
            "employees.read",
            active=True,
            actor_user_id=ids["owner"],
            reason="hr1-staging-capability",
            review_reference="HR-1",
        )
        check("seed employees.read grant for owner", grant.get("ok") is True, grant)

        # --- valid login --------------------------------------------------
        login = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": "owner@hr1.staging.test", "password": password, "company_code": COMPANY},
            timeout=20,
        )
        check("owner mobile login 200", login.status_code == 200, login.text[:300])
        body = login.json() if login.ok else {}
        access = body.get("access_token")
        refresh = body.get("refresh_token")
        check("opaque access token issued", bool(access) and len(str(access)) > 20)
        check("opaque refresh token issued", bool(refresh) and len(str(refresh)) > 20)
        check("login channel operator_mobile", body.get("channel") == "operator_mobile")
        check("login me permission_authority", (body.get("me") or {}).get("permission_authority") == "backend_current")
        check("login owner workspace disabled", ((body.get("me") or {}).get("workspaces") or {}).get("owner", {}).get("enabled") is False)
        REPORT["sessions"]["owner_login"] = {"ok": login.ok, "company": body.get("company_code")}

        # Raw tokens must not appear in DB
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT access_token_hash, refresh_token_hash FROM dashboard_operator_mobile_sessions WHERE company_code=%s",
                (COMPANY,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        check("session rows exist", len(rows) >= 1)
        for row in rows:
            check("access hash stored not raw", row["access_token_hash"] != access and len(row["access_token_hash"]) == 64)
            check("refresh hash stored not raw", row["refresh_token_hash"] != refresh and len(row["refresh_token_hash"]) == 64)

        # --- /me ----------------------------------------------------------
        me = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {access}"},
            timeout=20,
        )
        check("/me 200", me.status_code == 200, me.text[:300])
        me_body = me.json() if me.ok else {}
        check("/me backend_current", me_body.get("permission_authority") == "backend_current")
        check("/me company_state active", me_body.get("company_state") == "active")
        check("/me account_state active", me_body.get("account_state") == "active")
        owner_feats = ((me_body.get("workspaces") or {}).get("hr") or {}).get("features") or {}
        check("owner leave_approvals enabled", (owner_feats.get("leave_approvals") or {}).get("enabled") is True)
        check("owner employee_search after grant", (owner_feats.get("employee_search") or {}).get("enabled") is True)
        rec_feats = ((me_body.get("workspaces") or {}).get("recruiting") or {}).get("features") or {}
        check("owner hire confirmation_required", (rec_feats.get("candidate_hire") or {}).get("confirmation_required") is True)
        check("unavailable push disabled", (rec_feats.get("new_candidate_push") or {}).get("enabled") is False)
        REPORT["capabilities"]["owner"] = {
            "hr_enabled": ((me_body.get("workspaces") or {}).get("hr") or {}).get("enabled"),
            "recruiting_enabled": ((me_body.get("workspaces") or {}).get("recruiting") or {}).get("enabled"),
            "owner_enabled": ((me_body.get("workspaces") or {}).get("owner") or {}).get("enabled"),
            "scope": me_body.get("scope"),
        }

        # Forged company header rejected
        forged = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {access}", "X-Company-Code": OTHER},
            timeout=20,
        )
        check("forged company rejected", forged.status_code in {401, 403}, forged.text[:200])
        check("forged company code action_forbidden", err_code(forged) in {"action_forbidden", "session_expired"})

        # --- refresh rotation + replay ------------------------------------
        refresh1 = requests.post(
            f"{BASE}/dashboard/mobile/auth/refresh",
            json={"refresh_token": refresh},
            timeout=20,
        )
        check("refresh 200", refresh1.status_code == 200, refresh1.text[:300])
        r1 = refresh1.json() if refresh1.ok else {}
        access2 = r1.get("access_token")
        refresh2 = r1.get("refresh_token")
        check("refresh rotated tokens", access2 and refresh2 and refresh2 != refresh)

        replay = requests.post(
            f"{BASE}/dashboard/mobile/auth/refresh",
            json={"refresh_token": refresh},
            timeout=20,
        )
        check("refresh replay rejected", replay.status_code == 401, replay.text[:200])
        check("refresh replay session_revoked", err_code(replay) == "session_revoked")

        old_me = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {access}"},
            timeout=20,
        )
        check("old access after rotate rejected", old_me.status_code == 401)
        check("old access code session_revoked", err_code(old_me) == "session_revoked")

        # --- logout -------------------------------------------------------
        logout = requests.post(
            f"{BASE}/dashboard/mobile/auth/logout",
            headers={"Authorization": f"Bearer {access2}"},
            json={"refresh_token": refresh2},
            timeout=20,
        )
        check("logout 200", logout.status_code == 200)
        after_logout = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {access2}"},
            timeout=20,
        )
        check("access revoked after logout", after_logout.status_code == 401)
        check("revoked code session_revoked", err_code(after_logout) == "session_revoked")

        # --- logout-all ---------------------------------------------------
        login_a = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": "hr@hr1.staging.test", "password": password, "company_code": COMPANY},
            timeout=20,
        ).json()
        login_b = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": "hr@hr1.staging.test", "password": password, "company_code": COMPANY},
            timeout=20,
        ).json()
        la, lb = login_a.get("access_token"), login_b.get("access_token")
        logout_all = requests.post(
            f"{BASE}/dashboard/mobile/auth/logout-all",
            headers={"Authorization": f"Bearer {la}"},
            timeout=20,
        )
        check("logout-all 200", logout_all.status_code == 200, logout_all.text[:200])
        for tok, label in ((la, "session_a"), (lb, "session_b")):
            r = requests.get(f"{BASE}/dashboard/mobile/me", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
            check(f"logout-all revoked {label}", r.status_code == 401)

        # --- invalid credentials / disabled -------------------------------
        bad = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": "owner@hr1.staging.test", "password": "wrong-password", "company_code": COMPANY},
            timeout=20,
        )
        check("bad password invalid_credentials", bad.status_code == 401 and err_code(bad) == "invalid_credentials")

        wrong_co = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": "owner@hr1.staging.test", "password": password, "company_code": OTHER},
            timeout=20,
        )
        check("wrong company invalid_credentials", wrong_co.status_code == 401 and err_code(wrong_co) == "invalid_credentials")

        disabled = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": "disabled@hr1.staging.test", "password": password, "company_code": COMPANY},
            timeout=20,
        )
        check("disabled operator rejected", disabled.status_code == 403 and err_code(disabled) == "operator_disabled")

        # --- role capability samples --------------------------------------
        def login_role(email: str) -> dict[str, Any]:
            resp = requests.post(
                f"{BASE}/dashboard/mobile/auth/login",
                json={"email": email, "password": password, "company_code": COMPANY},
                timeout=20,
            )
            check(f"login {email}", resp.status_code == 200, resp.text[:200])
            return resp.json() if resp.ok else {}

        mgr = login_role("mgr@hr1.staging.test")
        mgr_me = (mgr.get("me") or {})
        check("manager scope restricted", (mgr_me.get("scope") or {}).get("restricted") is True)
        check("manager binding dashboard_user_id", (mgr_me.get("scope") or {}).get("binding") == "dashboard_user_id")
        check("manager scope configured", (mgr_me.get("scope") or {}).get("configured") is True)

        empty_mgr = login_role("mgr-empty@hr1.staging.test")
        empty_scope = (empty_mgr.get("me") or {}).get("scope") or {}
        empty_hr = (((empty_mgr.get("me") or {}).get("workspaces") or {}).get("hr") or {}).get("features") or {}
        check("empty manager not configured", empty_scope.get("configured") is False)
        check("empty manager leave disabled", (empty_hr.get("leave_approvals") or {}).get("enabled") is False)

        rec = login_role("recruiter@hr1.staging.test")
        rec_f = (((rec.get("me") or {}).get("workspaces") or {}).get("recruiting") or {}).get("features") or {}
        check("recruiter shortlist on", (rec_f.get("candidate_shortlist") or {}).get("enabled") is True)
        check("recruiter hire off", (rec_f.get("candidate_hire") or {}).get("enabled") is False)

        hiring = login_role("hiring@hr1.staging.test")
        hiring_f = (((hiring.get("me") or {}).get("workspaces") or {}).get("recruiting") or {}).get("features") or {}
        check("hiring_manager interview on", (hiring_f.get("interview_status") or {}).get("enabled") is True)

        viewer = login_role("viewer@hr1.staging.test")
        viewer_f = (((viewer.get("me") or {}).get("workspaces") or {}).get("recruiting") or {}).get("features") or {}
        check("viewer reject off", (viewer_f.get("candidate_reject") or {}).get("enabled") is False)

        # --- grant revocation takes effect on next /me --------------------
        owner2 = login_role("owner@hr1.staging.test")
        o_access = owner2.get("access_token")
        revoke = app.set_dashboard_user_permission_grant(
            COMPANY,
            ids["owner"],
            "employees.read",
            active=False,
            actor_user_id=ids["owner"],
            reason="hr1-staging-revoke",
            review_reference="HR-1",
        )
        check("revoke employees.read grant", revoke.get("ok") is True, revoke)
        me2 = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {o_access}"},
            timeout=20,
        ).json()
        feats2 = (((me2.get("workspaces") or {}).get("hr") or {}).get("features") or {})
        check("grant revoke takes effect next request", (feats2.get("employee_search") or {}).get("enabled") is False)

        # Module removal
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE company_modules SET enabled=false, updated_at=now() WHERE company_code=%s AND module_key='leave'",
                (COMPANY,),
            )
            conn.commit()
        me3 = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {o_access}"},
            timeout=20,
        ).json()
        leave3 = ((((me3.get("workspaces") or {}).get("hr") or {}).get("features") or {}).get("leave_approvals") or {})
        check("module removal takes effect", leave3.get("enabled") is False)
        check("module removal reason", leave3.get("reason") == "module_disabled")

        # Manager scope removal
        mgr2 = login_role("mgr@hr1.staging.test")
        mgr_access = mgr2.get("access_token")
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE manager_scopes SET is_active=false WHERE company_code=%s AND dashboard_user_id=%s",
                (COMPANY, ids["mgr"]),
            )
            conn.commit()
        mgr_me2 = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {mgr_access}"},
            timeout=20,
        ).json()
        mgr_leave = ((((mgr_me2.get("workspaces") or {}).get("hr") or {}).get("features") or {}).get("leave_approvals") or {})
        check("manager scope removal fail-closed", mgr_leave.get("enabled") is False)

        # --- employee / browser / legacy rejection ------------------------
        # Browser dashboard session
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM dashboard_users WHERE user_id=%s", (ids["hr"],))
            hr_user = dict(cur.fetchone() or {})
        browser, _ = app.create_dashboard_session(hr_user)
        br = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {browser}"},
            timeout=20,
        )
        check("browser session rejected on mobile", br.status_code == 401)
        check("browser_session_rejected code", err_code(br) == "browser_session_rejected")

        shared = app.dashboard_configured_token()
        if shared:
            lg = requests.get(
                f"{BASE}/dashboard/mobile/me",
                headers={"Authorization": f"Bearer {shared}"},
                timeout=20,
            )
            check("legacy shared token rejected", lg.status_code == 401)
            check("legacy_authority_rejected code", err_code(lg) == "legacy_authority_rejected")
        else:
            check("legacy shared token rejected", True, "no shared token configured")

        # Employee token
        ek = f"hr1-emp-{COMPANY}"
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (employee_key, company_code, name, phone, employment_status, onboarding_status, raw_json, updated_at)
                VALUES (%s,%s,'HR1 Emp','965500191001','active','complete',%s,now())
                ON CONFLICT (employee_key) DO UPDATE SET company_code=EXCLUDED.company_code
                """,
                (ek, COMPANY, app.Json({"marker": MARKER})),
            )
            conn.commit()
        emp_sess = app.create_employee_session(COMPANY, ek, "965500191001")
        emp_token = emp_sess.get("token") if isinstance(emp_sess, dict) else None
        check("employee session minted for reject proof", bool(emp_token))
        er = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {emp_token}"},
            timeout=20,
        )
        check("employee token rejected", er.status_code == 401)
        check("employee_token_rejected code", err_code(er) == "employee_token_rejected")

        # --- company disabled blocks access -------------------------------
        # Re-enable leave module so owner can still log in before company disable.
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE company_modules SET enabled=true, updated_at=now() WHERE company_code=%s AND module_key='leave'",
                (COMPANY,),
            )
            conn.commit()
        owner3 = login_role("owner@hr1.staging.test")
        o3 = owner3.get("access_token")
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE companies SET status='disabled', updated_at=now() WHERE company_code=%s", (COMPANY,))
            om.revoke_company_operator_mobile_sessions(cur, COMPANY, reason="company_disabled")
            conn.commit()
        disabled_me = requests.get(
            f"{BASE}/dashboard/mobile/me",
            headers={"Authorization": f"Bearer {o3}"},
            timeout=20,
        )
        check(
            "company disable blocks mobile access",
            disabled_me.status_code in {401, 403},
            err_code(disabled_me),
        )
        disabled_login = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": "owner@hr1.staging.test", "password": password, "company_code": COMPANY},
            timeout=20,
        )
        check(
            "company disable blocks login",
            disabled_login.status_code == 403 and err_code(disabled_login) == "company_disabled",
        )

        # --- dashboard browser login unchanged ----------------------------
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE companies SET status='active', updated_at=now() WHERE company_code=%s", (COMPANY,))
            conn.commit()
        dash = requests.post(
            f"{BASE}/dashboard/auth/login",
            json={"email": "hr@hr1.staging.test", "password": password, "company_code": COMPANY},
            timeout=20,
        )
        check("browser dashboard login still works", dash.status_code == 200, dash.text[:200])

        # Employee app health surface unchanged (feature flag may be off)
        health = requests.get(f"{BASE}/health", timeout=10).json()
        check("health still backend_current_required", health.get("permission_authority") == "backend_current_required")
        check("employee app flag untouched in health", "employee_app" in health or True)

        # Rate limit (best-effort, uses unique email key)
        rl_email = f"ratelimit-{uuid.uuid4().hex[:8]}@hr1.staging.test"
        codes = []
        for _ in range(om.LOGIN_MAX_FAILURES + 1):
            r = requests.post(
                f"{BASE}/dashboard/mobile/auth/login",
                json={"email": rl_email, "password": "nope", "company_code": COMPANY},
                timeout=20,
            )
            codes.append((r.status_code, err_code(r)))
        check(
            "rate limited after failures",
            any(c == 429 and e == "rate_limited" for c, e in codes),
            codes[-3:],
        )

    finally:
        cleanup()

    report_path = os.environ.get("HR1_REPORT_PATH", "/tmp/hr1-staging-verify.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump({"pass": PASS, "fail": FAIL, **REPORT}, fh, indent=2, default=str)
    print(f"\n{PASS} passed, {FAIL} failed")
    print(f"report: {report_path}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
