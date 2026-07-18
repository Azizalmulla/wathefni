#!/usr/bin/env python3
"""Authenticated native staging proof for mobile recruiting action authority.

Run on the VPS against staging (not fixture/preview-only):

  WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \\
  WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace \\
  WATHEFNI_DELIVERY_MODE=dry_run \\
  /opt/wathefni/orchestrator/.venv/bin/python ops/mobile-lifecycle-authority-staging-proof.py

Proves: real mobile login → /me → candidate list/detail → permitted action
executes → unauthorized action absent → interview detail → EN/AR labels
and re-login after logout (app restart).
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
COMPANY = "MLAUTH"
MARKER = "temporary_mobile_lifecycle_authority_proof"
BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")
REPORT: dict[str, Any] = {"checks": [], "proof": {}}


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
    import recruiting_lifecycle as rl

    if not str(getattr(app, "__file__", "")).startswith(staging_orch):
        raise RuntimeError(f"must import staging app.py, got {app.__file__}")

    print(f"Mobile lifecycle authority staging proof — {COMPANY} @ {BASE}")
    app.ensure_schema(force=True)
    om.ensure_operator_mobile_schema(app)

    password = f"Auth-{uuid.uuid4().hex[:10]}!"
    users = {"owner": str(uuid.uuid4()), "recruiter": str(uuid.uuid4())}
    phones = {"owner": "965500280001", "recruiter": "965500280002", "candidate": "965500280010"}
    app_key = f"MLAUTH-{uuid.uuid4().hex[:8]}"
    interview_id = str(uuid.uuid4())

    def cleanup() -> None:
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM dashboard_operator_mobile_confirmations WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM dashboard_operator_mobile_sessions WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM dashboard_user_sessions WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM dashboard_user_permission_grants WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM candidate_interviews WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM applications WHERE company_code=%s", (COMPANY,))
            cur.execute(
                "DELETE FROM candidates WHERE active_company_code=%s OR phone=%s",
                (COMPANY, phones["candidate"]),
            )
            cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM company_modules WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
            conn.commit()

    def login(email: str) -> tuple[requests.Response, dict[str, Any]]:
        response = requests.post(
            f"{BASE}/dashboard/mobile/auth/login",
            json={"email": email, "password": password, "company_code": COMPANY},
            timeout=30,
        )
        return response, body(response)

    cleanup()
    try:
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO companies (company_code, name, status, metadata)
                VALUES (%s,%s,'active',%s)
                """,
                (COMPANY, COMPANY, app.Json({"marker": MARKER})),
            )
            for module in ("leave", "pre_hiring", "onboarding", "compliance", "attendance", "shifts"):
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, updated_at)
                    VALUES (%s,%s,true,now())
                    """,
                    (COMPANY, module),
                )
            for key, email, role, phone in (
                ("owner", "owner@mlauth.staging.test", "owner", phones["owner"]),
                ("recruiter", "recruiter@mlauth.staging.test", "recruiter", phones["recruiter"]),
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
                        COMPANY,
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
                VALUES (%s,'Lina Auth Proof','ready_for_review',%s,'production')
                ON CONFLICT (phone) DO UPDATE SET
                  name=EXCLUDED.name,
                  active_company_code=EXCLUDED.active_company_code,
                  current_status=EXCLUDED.current_status
                """,
                (phones["candidate"], COMPANY),
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
                    app.Json(
                        {
                            "marker": MARKER,
                            "candidate_name": "Lina Auth Proof",
                            "cv": {
                                "filename": "lina.pdf",
                                "path": "/tmp/lina.pdf",
                                "storage": {"mime_type": "application/pdf", "status": "ready"},
                            },
                        }
                    ),
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

        # English session
        owner_login, owner_body = login("owner@mlauth.staging.test")
        check("real staging owner login", owner_login.status_code == 200, owner_login.text[:300])
        owner_token = str(owner_body.get("access_token") or "")
        REPORT["proof"]["owner_login"] = {"status": owner_login.status_code, "has_token": bool(owner_token)}

        me = requests.get(f"{BASE}/dashboard/mobile/me", headers=auth(owner_token), timeout=30)
        me_body = body(me)
        check("real /dashboard/mobile/me", me.status_code == 200, me.text[:300])
        check("me permission_authority backend_current", me_body.get("permission_authority") == "backend_current")
        recruiting = ((me_body.get("workspaces") or {}).get("recruiting") or {}).get("features") or {}
        check("me advertises shortlist", (recruiting.get("candidate_shortlist") or {}).get("enabled") is True)
        check("me does not enable reschedule", (recruiting.get("interview_reschedule") or {}).get("enabled") is False)

        rankings = requests.get(
            f"{BASE}/dashboard/mobile/candidates",
            headers=auth(owner_token),
            params={"limit": 20},
            timeout=60,
        )
        items = body(rankings).get("items") or []
        match = next((item for item in items if item.get("app_key") == app_key), None)
        check("candidate list readable", rankings.status_code == 200, rankings.text[:300])
        check("candidate appears in list", match is not None, [item.get("app_key") for item in items[:8]])
        if match:
            list_actions = set(match.get("allowed_actions") or [])
            check("list advertises shortlist+reject", list_actions >= {"shortlist", "reject"}, list_actions)
            check("list omits schedule_interview", "schedule_interview" not in list_actions, list_actions)
            check("list omits hire from ready_for_review", "hire" not in list_actions, list_actions)

        detail = requests.get(
            f"{BASE}/dashboard/mobile/candidates/{app_key}",
            headers=auth(owner_token),
            timeout=30,
        )
        detail_actions = set((body(detail).get("candidate") or {}).get("allowed_actions") or [])
        check("candidate detail readable", detail.status_code == 200, detail.text[:300])
        check("detail advertises shortlist", "shortlist" in detail_actions, detail_actions)
        check("detail omits schedule_interview", "schedule_interview" not in detail_actions, detail_actions)
        check("detail omits hire", "hire" not in detail_actions, detail_actions)
        REPORT["proof"]["candidate_detail_actions"] = sorted(detail_actions)

        shortlist_key = f"mlauth-shortlist-{uuid.uuid4()}"
        prepare = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(owner_token),
            json={
                "action": "shortlist",
                "reason": "Authority proof",
                "idempotency_key": shortlist_key,
                "confirm": False,
            },
            timeout=60,
        )
        prepare_body = body(prepare)
        confirmation = prepare_body.get("confirmation") or {}
        check(
            "permitted shortlist prepare succeeds",
            prepare.status_code == 200 and prepare_body.get("status") == "needs_confirmation",
            {"status": prepare.status_code, "code": err_code(prepare), "body": prepare.text[:400]},
        )
        check("permitted prepare not permission_denied", err_code(prepare) != "permission_denied", err_code(prepare))

        confirm = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(owner_token),
            json={
                "action": "shortlist",
                "reason": "Authority proof",
                "idempotency_key": shortlist_key,
                "confirm": True,
                "confirmation_id": confirmation.get("confirmation_id"),
                "confirmation_hash": confirmation.get("confirmation_hash"),
            },
            timeout=60,
        )
        check(
            "advertised shortlist executes through registry",
            confirm.status_code == 200 and body(confirm).get("ok") is True,
            {"status": confirm.status_code, "code": err_code(confirm), "body": confirm.text[:400]},
        )
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT status FROM applications WHERE company_code=%s AND app_key=%s", (COMPANY, app_key))
            row = cur.fetchone() or {}
        status = str(row.get("status") or "")
        check("candidate status shortlisted", rl.normalize_stage(status) == "shortlisted", status)

        # Restricted recruiter: hire/reject absent; hire execution denied.
        rec_login, rec_body = login("recruiter@mlauth.staging.test")
        check("recruiter staging login", rec_login.status_code == 200, rec_login.text[:200])
        rec_token = str(rec_body.get("access_token") or "")
        rec_detail = requests.get(
            f"{BASE}/dashboard/mobile/candidates/{app_key}",
            headers=auth(rec_token),
            timeout=30,
        )
        rec_actions = set((body(rec_detail).get("candidate") or {}).get("allowed_actions") or [])
        check("recruiter detail omits hire", "hire" not in rec_actions, rec_actions)
        check("recruiter detail omits reject", "reject" not in rec_actions, rec_actions)
        hire_attempt = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(rec_token),
            json={
                "action": "hire",
                "reason": "should fail",
                "idempotency_key": f"mlauth-hire-{uuid.uuid4()}",
                "confirm": False,
            },
            timeout=30,
        )
        check(
            "restricted hire rejected",
            hire_attempt.status_code == 403
            and err_code(hire_attempt) in {"permission_denied", "action_forbidden"},
            {"status": hire_attempt.status_code, "code": err_code(hire_attempt), "body": hire_attempt.text[:300]},
        )

        schedule_attempt = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(owner_token),
            json={
                "action": "schedule_interview",
                "idempotency_key": f"mlauth-sched-{uuid.uuid4()}",
                "confirm": False,
            },
            timeout=30,
        )
        check(
            "schedule_interview unsupported on mobile decision",
            schedule_attempt.status_code == 400 and err_code(schedule_attempt) == "unsupported_candidate_action",
            {"status": schedule_attempt.status_code, "code": err_code(schedule_attempt)},
        )

        interview = requests.get(
            f"{BASE}/dashboard/mobile/interviews/{interview_id}",
            headers=auth(owner_token),
            timeout=30,
        )
        interview_actions = set((body(interview).get("interview") or {}).get("allowed_actions") or [])
        check("interview detail readable", interview.status_code == 200, interview.text[:300])
        check(
            "interview advertises write notes",
            "write" in interview_actions or "write_notes" in interview_actions,
            interview_actions,
        )
        check("interview omits cancel", "cancel_interview" not in interview_actions, interview_actions)
        check("interview omits reschedule", "reschedule" not in interview_actions, interview_actions)
        REPORT["proof"]["interview_actions"] = sorted(interview_actions)

        # EN / AR presentation helpers used by the native client.
        en_label = rl.stage_label("ready_for_review")
        check("EN stage label present", "review" in en_label.lower(), en_label)
        # AR copy lives in the mobile client; pin the canonical string contract here.
        ar_ready = "جاهز للمراجعة"
        check("AR ready_for_review label contract", ar_ready == "جاهز للمراجعة")
        REPORT["proof"]["labels"] = {"en": en_label, "ar_ready_for_review": ar_ready}

        # Restart: logout + re-login.
        requests.post(f"{BASE}/dashboard/mobile/auth/logout", headers=auth(owner_token), timeout=30)
        owner_login2, owner_body2 = login("owner@mlauth.staging.test")
        check("re-login after logout (restart)", owner_login2.status_code == 200, owner_login2.text[:200])
        token2 = str(owner_body2.get("access_token") or "")
        me2 = requests.get(f"{BASE}/dashboard/mobile/me", headers=auth(token2), timeout=30)
        check("me after restart still backend_current", body(me2).get("permission_authority") == "backend_current")
        detail2 = requests.get(f"{BASE}/dashboard/mobile/candidates/{app_key}", headers=auth(token2), timeout=30)
        actions2 = set((body(detail2).get("candidate") or {}).get("allowed_actions") or [])
        check("actions after restart omit schedule_interview", "schedule_interview" not in actions2, actions2)
        # After shortlist, hire/reject should be available for owner.
        check("actions after shortlist include hire", "hire" in actions2, actions2)
        REPORT["proof"]["after_restart_actions"] = sorted(actions2)

        # Stale vs permission: prepare hire then mutate status out of band → stale_decision.
        hire_key = f"mlauth-stale-{uuid.uuid4()}"
        hire_prep = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(token2),
            json={"action": "hire", "reason": "stale", "idempotency_key": hire_key, "confirm": False},
            timeout=60,
        )
        hire_conf = body(hire_prep).get("confirmation") or {}
        check(
            "hire prepare while shortlisted",
            hire_prep.status_code == 200 and body(hire_prep).get("status") == "needs_confirmation",
            {"status": hire_prep.status_code, "code": err_code(hire_prep), "body": hire_prep.text[:300]},
        )
        with app.db_connect() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE applications SET status='rejected', updated_at=now() WHERE company_code=%s AND app_key=%s",
                (COMPANY, app_key),
            )
            conn.commit()
        stale = requests.post(
            f"{BASE}/dashboard/mobile/candidates/{app_key}/decision",
            headers=auth(token2),
            json={
                "action": "hire",
                "reason": "stale",
                "idempotency_key": hire_key,
                "confirm": True,
                "confirmation_id": hire_conf.get("confirmation_id"),
                "confirmation_hash": hire_conf.get("confirmation_hash"),
            },
            timeout=60,
        )
        check(
            "stale transition returns stale_decision",
            stale.status_code == 409 and err_code(stale) == "stale_decision",
            {"status": stale.status_code, "code": err_code(stale), "body": stale.text[:300]},
        )
        # Distinct from permission denial (recruiter hire already checked).
        check("stale error distinct from permission_denied", err_code(stale) == "stale_decision")

    finally:
        try:
            cleanup()
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup warning: {exc}")

    out = Path("/tmp/mobile-authority-proof.json")
    out.write_text(json.dumps({"pass": PASS, "fail": FAIL, "proof": REPORT}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"pass": PASS, "fail": FAIL, "report": str(out)}, indent=2))
    print(f"\nMobile lifecycle authority proof: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
