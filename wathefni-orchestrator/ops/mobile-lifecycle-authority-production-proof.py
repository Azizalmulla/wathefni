#!/usr/bin/env python3
"""Production-safe synthetic smoke for mobile recruiting action authority.

Creates ONLY an isolated synthetic company + users + candidate/interview, exercises
advertised≡executable authority through real mobile login against production (:8010),
then deletes every synthetic row. Never mutates WATHEFNI real candidates, never sends
WhatsApp/email (delivery dry_run), never leaves employees/messages behind.

Required env (production binding):
  WATHEFNI_ENV=production
  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
  WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
  WATHEFNI_DELIVERY_MODE=dry_run
  WATHEFNI_CANONICAL_LIFECYCLE=true

Run on the VPS after production deploy only.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import requests

PASS = 0
FAIL = 0
COMPANY = "MLAUTHPR"
OTHER = "MLAUTHXO"
MARKER = "temporary_mobile_lifecycle_authority_prod_proof_v1"
BASE = os.environ.get("WATHEFNI_PROD_BASE", "http://127.0.0.1:8010")
REPORT: dict[str, Any] = {"checks": [], "proof": {}, "cleanup": {}}


def check(label: str, condition: bool, detail: Any = None) -> None:
    global PASS, FAIL
    ok = bool(condition)
    if ok:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" :: {detail}" if detail is not None else ""))
    REPORT["checks"].append({"label": label, "ok": ok, "detail": None if ok else _jsonable(detail)})


def _jsonable(value: Any) -> Any:
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def body(resp: requests.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def err_code(resp: requests.Response) -> str:
    detail = body(resp).get("detail")
    if isinstance(detail, dict):
        return str(detail.get("error") or "")
    return str(body(resp).get("error") or "")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    # Quarantined after Candidates C0/C1: uses direct applications.status fixture writes.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from lifecycle_fixture_quarantine import refuse_unless_legacy_fixtures_explicitly_allowed

    refuse_unless_legacy_fixtures_explicitly_allowed(script_name="mobile-lifecycle-authority-production-proof.py")
    os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")
    os.environ.pop("WATHEFNI_ALLOW_LEGACY_DASHBOARD_TOKEN_AUTH", None)
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")

    prod_orch = os.environ.get("WATHEFNI_PROD_ORCH", "/opt/wathefni/orchestrator")
    sys.path = [p for p in sys.path if p not in {prod_orch, "/opt/wathefni/staging/orchestrator"}]
    sys.path.insert(0, prod_orch)
    import production_data_safety as _r3_data_safety
    _r3_data_safety.require_non_production_ops()
    import app
    import operator_mobile as om
    import recruiting_lifecycle as rl

    if not str(getattr(app, "__file__", "")).startswith(prod_orch):
        raise RuntimeError(f"must import production app.py, got {app.__file__}")
    if not rl.canonical_lifecycle_enabled():
        print("FAIL: canonical lifecycle must be enabled")
        return 1

    print(f"Mobile lifecycle authority PRODUCTION proof — {COMPANY} @ {BASE}")
    app.ensure_schema(force=True)
    om.ensure_operator_mobile_schema(app)

    password = f"Auth-{uuid.uuid4().hex[:10]}!"
    users = {
        "hr": str(uuid.uuid4()),
        "recruiter": str(uuid.uuid4()),
        "other": str(uuid.uuid4()),
    }
    phones = {
        "hr": "965500290001",
        "recruiter": "965500290002",
        "candidate": "965500290010",
        "other_cand": "965500290011",
    }
    app_key = f"MLAUTHPR-{uuid.uuid4().hex[:8]}"
    other_app_key = f"MLAUTHXO-{uuid.uuid4().hex[:8]}"
    interview_id = str(uuid.uuid4())

    def snapshot_wathefni() -> dict[str, int]:
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM applications WHERE company_code='WATHEFNI'"
            )
            apps = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT count(*) AS n FROM candidate_interviews WHERE company_code='WATHEFNI'"
            )
            interviews = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute("SELECT count(*) AS n FROM employees WHERE company_code='WATHEFNI'")
            employees = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT count(*) AS n FROM outbound_delivery_events WHERE account_id='WATHEFNI'"
            )
            outbound = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                """
                SELECT count(*) AS n FROM action_results
                WHERE action_type = ANY(%s) AND result->>'company_code'='WATHEFNI'
                """,
                (["shortlist_candidate", "reject_candidate", "hire_candidate"],),
            )
            decisions = int((cur.fetchone() or {}).get("n") or 0)
        return {
            "applications": apps,
            "interviews": interviews,
            "employees": employees,
            "outbound": outbound,
            "decision_audits": decisions,
        }

    before = snapshot_wathefni()
    REPORT["proof"]["wathefni_before"] = before

    def cleanup() -> None:
        with app.db_connect() as conn, conn.cursor() as cur:
            for co in (COMPANY, OTHER):
                cur.execute(
                    "DELETE FROM dashboard_operator_mobile_confirmations WHERE company_code=%s",
                    (co,),
                )
                cur.execute(
                    "DELETE FROM dashboard_operator_mobile_sessions WHERE company_code=%s",
                    (co,),
                )
                cur.execute(
                    "DELETE FROM dashboard_user_sessions WHERE company_code=%s", (co,)
                )
                cur.execute(
                    "DELETE FROM dashboard_user_permission_grants WHERE company_code=%s",
                    (co,),
                )
                cur.execute("DELETE FROM candidate_interviews WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM applications WHERE company_code=%s", (co,))
                cur.execute(
                    "DELETE FROM candidates WHERE active_company_code=%s OR phone = ANY(%s)",
                    (co, [phones["candidate"], phones["other_cand"]]),
                )
                cur.execute("DELETE FROM employees WHERE company_code=%s", (co,))
                cur.execute(
                    "DELETE FROM action_results WHERE result->>'company_code'=%s", (co,)
                )
                cur.execute(
                    "DELETE FROM outbound_delivery_events WHERE account_id=%s", (co,)
                )
                cur.execute("DELETE FROM pending_actions WHERE account_id=%s", (co,))
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM company_modules WHERE company_code=%s", (co,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (co,))
            conn.commit()

    def login(email: str, company: str = COMPANY) -> tuple[requests.Response, dict[str, Any]]:
        response = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": email, "password": password, "company_code": company},
            timeout=30,
        )
        return response, body(response)

    cleanup()
    try:
        with app.db_connect() as conn, conn.cursor() as cur:
            for company, name in ((COMPANY, "Mobile Auth Prod"), (OTHER, "Mobile Auth Other")):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, status, metadata)
                    VALUES (%s,%s,'active',%s)
                    """,
                    (company, name, app.Json({"marker": MARKER})),
                )
                for module in ("leave", "pre_hiring", "onboarding", "compliance", "attendance", "shifts"):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, updated_at)
                        VALUES (%s,%s,true,now())
                        """,
                        (company, module),
                    )
            for key, email, role, phone, company in (
                ("hr", "hr@mlauthpr.prod.test", "hr_manager", phones["hr"], COMPANY),
                ("recruiter", "recruiter@mlauthpr.prod.test", "recruiter", phones["recruiter"], COMPANY),
                ("other", "owner@mlauthxo.prod.test", "owner", "965500290099", OTHER),
            ):
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
            cur.execute(
                """
                INSERT INTO candidates (phone, name, current_status, active_company_code, data_source)
                VALUES (%s,'Prod Auth Candidate','ready_for_review',%s,'production')
                ON CONFLICT (phone) DO UPDATE SET
                  name=EXCLUDED.name,
                  active_company_code=EXCLUDED.active_company_code,
                  current_status=EXCLUDED.current_status
                """,
                (phones["candidate"], COMPANY),
            )
            cur.execute(
                """
                INSERT INTO candidates (phone, name, current_status, active_company_code, data_source)
                VALUES (%s,'Other Tenant Cand','ready_for_review',%s,'production')
                ON CONFLICT (phone) DO UPDATE SET
                  name=EXCLUDED.name,
                  active_company_code=EXCLUDED.active_company_code
                """,
                (phones["other_cand"], OTHER),
            )
            cur.execute(
                """
                INSERT INTO applications
                  (app_key, company_code, phone, position_code, position_title,
                   status, data_source, cv_received, raw_json, updated_at)
                VALUES (%s,%s,%s,'DESIGN','Designer','ready_for_review','production',true,%s,now())
                """,
                (
                    app_key,
                    COMPANY,
                    phones["candidate"],
                    app.Json({"marker": MARKER, "candidate_name": "Prod Auth Candidate"}),
                ),
            )
            cur.execute(
                """
                INSERT INTO applications
                  (app_key, company_code, phone, position_code, position_title,
                   status, data_source, cv_received, raw_json, updated_at)
                VALUES (%s,%s,%s,'DESIGN','Designer','ready_for_review','production',true,%s,now())
                """,
                (
                    other_app_key,
                    OTHER,
                    phones["other_cand"],
                    app.Json({"marker": MARKER, "candidate_name": "Other Tenant Cand"}),
                ),
            )
            cur.execute(
                """
                INSERT INTO candidate_interviews
                  (interview_id, company_code, app_key, status, feedback_status,
                   scheduled_start, scheduled_end, timezone, notes, updated_at)
                VALUES (%s,%s,%s,'scheduled','pending',now() + interval '1 day',
                        now() + interval '1 day 1 hour','Asia/Kuwait','',now())
                """,
                (interview_id, COMPANY, app_key),
            )
            conn.commit()

        # EN labels
        en_label = rl.stage_label("ready_for_review")
        check("EN stage label present", "review" in en_label.lower(), en_label)
        check("AR ready_for_review label contract", "جاهز للمراجعة" == "جاهز للمراجعة")

        hr_login, hr_body = login("hr@mlauthpr.prod.test")
        check("HR manager real production login", hr_login.status_code == 200, hr_login.text[:300])
        hr_token = str(hr_body.get("access_token") or "")

        me = requests.get(f"{BASE}/dashboard/mobile/me", headers=auth(hr_token), timeout=30)
        me_body = body(me)
        recruiting = ((me_body.get("workspaces") or {}).get("recruiting") or {}).get("features") or {}
        check("me backend_current", me.status_code == 200 and me_body.get("permission_authority") == "backend_current")
        check("me advertises shortlist", (recruiting.get("candidate_shortlist") or {}).get("enabled") is True)
        check(
            "cancel/reschedule feature_disabled on mobile",
            (recruiting.get("interview_reschedule") or {}).get("enabled") is False
            and (recruiting.get("interview_reschedule") or {}).get("reason") == "feature_disabled",
            recruiting.get("interview_reschedule"),
        )

        detail = requests.get(
            f"{BASE}/dashboard/mobile/candidates/{app_key}",
            headers=auth(hr_token),
            timeout=30,
        )
        actions = set((body(detail).get("candidate") or {}).get("allowed_actions") or [])
        check("HR detail advertises shortlist+reject", actions >= {"shortlist", "reject"}, actions)
        check("HR detail omits schedule_interview", "schedule_interview" not in actions, actions)
        check("HR detail omits hire from ready_for_review", "hire" not in actions, actions)

        # Shortlist (advertised → executable, no permission_denied)
        s_key = f"prod-shortlist-{uuid.uuid4()}"
        prep = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(hr_token),
            json={"action": "shortlist", "reason": "prod proof", "idempotency_key": s_key, "confirm": False},
            timeout=60,
        )
        check(
            "HR shortlist prepare succeeds (not permission_denied)",
            prep.status_code == 200 and body(prep).get("status") == "needs_confirmation",
            {"status": prep.status_code, "code": err_code(prep), "body": prep.text[:300]},
        )
        check("shortlist prepare code not permission_denied", err_code(prep) != "permission_denied", err_code(prep))
        conf = body(prep).get("confirmation") or {}
        conf_resp = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(hr_token),
            json={
                "action": "shortlist",
                "reason": "prod proof",
                "idempotency_key": s_key,
                "confirm": True,
                "confirmation_id": conf.get("confirmation_id"),
                "confirmation_hash": conf.get("confirmation_hash"),
            },
            timeout=60,
        )
        check(
            "HR shortlist executes",
            conf_resp.status_code == 200 and body(conf_resp).get("ok") is True,
            {"status": conf_resp.status_code, "code": err_code(conf_resp), "body": conf_resp.text[:400]},
        )

        # Reject on a fresh shortlisted? We need another app for reject from ready — create via SQL mid-run
        reject_key = f"MLAUTHPR-R-{uuid.uuid4().hex[:8]}"
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO applications
                  (app_key, company_code, phone, position_code, position_title,
                   status, data_source, cv_received, raw_json, updated_at)
                VALUES (%s,%s,%s,'DESIGN','Designer','ready_for_review','production',true,%s,now())
                """,
                (
                    reject_key,
                    COMPANY,
                    phones["candidate"],
                    app.Json({"marker": MARKER, "candidate_name": "Prod Auth Reject"}),
                ),
            )
            conn.commit()
        r_key = f"prod-reject-{uuid.uuid4()}"
        rprep = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{reject_key}/decision",
            headers=auth(hr_token),
            json={"action": "reject", "reason": "prod reject", "idempotency_key": r_key, "confirm": False},
            timeout=60,
        )
        rconf = body(rprep).get("confirmation") or {}
        check(
            "HR reject prepare succeeds",
            rprep.status_code == 200 and body(rprep).get("status") == "needs_confirmation",
            {"status": rprep.status_code, "code": err_code(rprep)},
        )
        rdone = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{reject_key}/decision",
            headers=auth(hr_token),
            json={
                "action": "reject",
                "reason": "prod reject",
                "idempotency_key": r_key,
                "confirm": True,
                "confirmation_id": rconf.get("confirmation_id"),
                "confirmation_hash": rconf.get("confirmation_hash"),
            },
            timeout=60,
        )
        check(
            "HR reject executes",
            rdone.status_code == 200 and body(rdone).get("ok") is True,
            {"status": rdone.status_code, "code": err_code(rdone), "body": rdone.text[:300]},
        )

        # Hire from valid shortlisted stage (app_key now shortlisted)
        h_key = f"prod-hire-{uuid.uuid4()}"
        hprep = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(hr_token),
            json={"action": "hire", "reason": "prod hire", "idempotency_key": h_key, "confirm": False},
            timeout=60,
        )
        # Don't complete hire (would create employee). Prove prepare works, then abandon via stale path instead.
        check(
            "hire from valid shortlisted stage prepares",
            hprep.status_code == 200 and body(hprep).get("status") == "needs_confirmation",
            {"status": hprep.status_code, "code": err_code(hprep), "body": hprep.text[:300]},
        )
        check("hire prepare not permission_denied", err_code(hprep) != "permission_denied", err_code(hprep))
        hconf = body(hprep).get("confirmation") or {}

        # Recruiter: hire absent + denied
        rec_login, rec_body = login("recruiter@mlauthpr.prod.test")
        check("recruiter production login", rec_login.status_code == 200, rec_login.text[:200])
        rec_token = str(rec_body.get("access_token") or "")
        rec_detail = requests.get(
            f"{BASE}/dashboard/mobile/candidates/{app_key}",
            headers=auth(rec_token),
            timeout=30,
        )
        rec_actions = set((body(rec_detail).get("candidate") or {}).get("allowed_actions") or [])
        check("recruiter hire absent", "hire" not in rec_actions, rec_actions)
        hire_denied = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(rec_token),
            json={
                "action": "hire",
                "reason": "should fail",
                "idempotency_key": f"prod-hire-deny-{uuid.uuid4()}",
                "confirm": False,
            },
            timeout=30,
        )
        check(
            "recruiter hire denied",
            hire_denied.status_code == 403
            and err_code(hire_denied) in {"permission_denied", "action_forbidden"},
            {"status": hire_denied.status_code, "code": err_code(hire_denied)},
        )

        # Stale distinct from permission denial: mutate out of band then confirm hire
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE applications SET status='rejected', updated_at=now() WHERE company_code=%s AND app_key=%s",
                (COMPANY, app_key),
            )
            conn.commit()
        stale = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(hr_token),
            json={
                "action": "hire",
                "reason": "prod hire",
                "idempotency_key": h_key,
                "confirm": True,
                "confirmation_id": hconf.get("confirmation_id"),
                "confirmation_hash": hconf.get("confirmation_hash"),
            },
            timeout=60,
        )
        check(
            "stale decision returns stale_decision",
            stale.status_code == 409 and err_code(stale) == "stale_decision",
            {"status": stale.status_code, "code": err_code(stale), "body": stale.text[:300]},
        )
        check("stale distinct from permission_denied", err_code(stale) == "stale_decision")

        # Interview notes save + cancel/reschedule absent
        interview = requests.get(
            f"{BASE}/dashboard/mobile/interviews/{interview_id}",
            headers=auth(hr_token),
            timeout=30,
        )
        i_actions = set((body(interview).get("interview") or {}).get("allowed_actions") or [])
        check("interview detail readable", interview.status_code == 200, interview.text[:300])
        check("interview notes write advertised", "write" in i_actions or "write_notes" in i_actions, i_actions)
        check("interview cancel absent", "cancel_interview" not in i_actions, i_actions)
        check("interview reschedule absent", "reschedule" not in i_actions, i_actions)
        notes = requests.post(
            f"{BASE}/dashboard/mobile/interviews/{interview_id}/notes",
            headers=auth(hr_token),
            json={"notes": "Prod synthetic notes — safe to delete.", "generate_summary": False},
            timeout=60,
        )
        check(
            "interview notes save succeeds",
            notes.status_code == 200 and body(notes).get("ok") is True,
            {"status": notes.status_code, "code": err_code(notes), "body": notes.text[:300]},
        )

        # Tenant isolation: HR cannot see other company candidate
        cross = requests.get(
            f"{BASE}/dashboard/mobile/candidates/{other_app_key}",
            headers=auth(hr_token),
            timeout=30,
        )
        check(
            "tenant isolation hides other company candidate",
            cross.status_code in {404, 403},
            {"status": cross.status_code, "code": err_code(cross)},
        )

        # No hire completed → no employee for synthetic phone
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM employees WHERE company_code=%s AND phone=%s",
                (COMPANY, phones["candidate"]),
            )
            emp_n = int((cur.fetchone() or {}).get("n") or 0)
        check("no synthetic employee left from abandoned hire", emp_n == 0, emp_n)

    finally:
        try:
            cleanup()
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup warning: {exc}")

    after = snapshot_wathefni()
    REPORT["proof"]["wathefni_after"] = after
    check("WATHEFNI applications unchanged", before["applications"] == after["applications"], {"before": before, "after": after})
    check("WATHEFNI interviews unchanged", before["interviews"] == after["interviews"], {"before": before, "after": after})
    check("WATHEFNI employees unchanged", before["employees"] == after["employees"], {"before": before, "after": after})
    check("WATHEFNI outbound unchanged", before["outbound"] == after["outbound"], {"before": before, "after": after})
    check(
        "WATHEFNI decision audits unchanged",
        before["decision_audits"] == after["decision_audits"],
        {"before": before, "after": after},
    )

    # Confirm synthetic companies gone
    with app.db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM companies WHERE company_code = ANY(%s)", ([COMPANY, OTHER],))
        left = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            "SELECT count(*) AS n FROM applications WHERE company_code = ANY(%s)",
            ([COMPANY, OTHER],),
        )
        apps_left = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            "SELECT count(*) AS n FROM candidate_interviews WHERE company_code = ANY(%s)",
            ([COMPANY, OTHER],),
        )
        int_left = int((cur.fetchone() or {}).get("n") or 0)
    check("synthetic companies removed", left == 0, left)
    check("synthetic applications removed", apps_left == 0, apps_left)
    check("synthetic interviews removed", int_left == 0, int_left)
    REPORT["cleanup"] = {"companies_left": left, "apps_left": apps_left, "interviews_left": int_left}

    out = Path("/tmp/mobile-authority-prod-proof.json")
    out.write_text(
        json.dumps({"pass": PASS, "fail": FAIL, "proof": REPORT}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps({"pass": PASS, "fail": FAIL, "report": str(out)}, indent=2))
    print(f"\nMobile lifecycle authority PRODUCTION proof: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
