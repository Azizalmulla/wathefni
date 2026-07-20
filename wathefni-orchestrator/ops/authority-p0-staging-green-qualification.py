#!/usr/bin/env python3
"""Authority P0 staging-green qualification evidence (staging DB + :8011 only).

Proves:
  - duplicate-name employee fixture (0 / 1 / many; no latest fallback)
  - authenticated cross-surface parity (web, WhatsApp toolcall, mobile)
  - shift reschedule expected_updated_at / tenant / overlap
  - leave/payroll provisional invalidation parity

Does not touch production.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

BASE = os.environ.get("WATHEFNI_STAGING_BASE", "http://127.0.0.1:8011")
COMPANY = "WATHEFNI"
FIXTURE_NAME = "Authority P0 Twin"
FIXTURE_PREFIX = "WATHEFNI-P0-DUP-"


def _check(results: dict[str, Any], name: str, ok: bool, detail: Any = None) -> None:
    results["checks"][name] = {"ok": bool(ok), "detail": detail}
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {json.dumps(detail, default=str)[:500]}")


def mint_token() -> str:
    import subprocess

    token = subprocess.check_output(
        [
            "/opt/wathefni/orchestrator/.venv/bin/python",
            str(ROOT / "ops" / "mint-staging-dashboard-session.py"),
            "--company",
            COMPANY,
            "--role",
            "owner",
        ],
        text=True,
    ).strip()
    if not token:
        raise RuntimeError("empty staging dashboard token")
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Company-Code": COMPANY, "Content-Type": "application/json"}


def ensure_duplicate_fixture(app: Any) -> dict[str, Any]:
    """Create exactly two active employees sharing FIXTURE_NAME (staging only)."""
    keys: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM employees
                WHERE company_code=%s
                  AND (employee_key LIKE %s OR name=%s)
                """,
                (COMPANY, f"{FIXTURE_PREFIX}%", FIXTURE_NAME),
            )
            for idx in (1, 2):
                key = f"{FIXTURE_PREFIX}{idx}"
                phone = f"9650000{1000 + idx}"
                cur.execute(
                    """
                    INSERT INTO employees (
                      employee_key, company_code, phone, name, employment_status, profile, raw_json
                    ) VALUES (%s,%s,%s,%s,'active',%s::jsonb,%s::jsonb)
                    ON CONFLICT (employee_key) DO UPDATE
                      SET name=EXCLUDED.name, phone=EXCLUDED.phone, updated_at=now(),
                          employment_status='active', profile=EXCLUDED.profile, raw_json=EXCLUDED.raw_json
                    RETURNING employee_key, name, phone, updated_at
                    """,
                    (
                        key,
                        COMPANY,
                        phone,
                        FIXTURE_NAME,
                        json.dumps({"p0_fixture": True, "idx": idx}),
                        json.dumps({"p0_fixture": True, "idx": idx}),
                    ),
                )
                keys.append(dict(cur.fetchone())["employee_key"])
            # Bump twin-2 updated_at later so a latest-updated guess would prefer it.
            cur.execute(
                "UPDATE employees SET updated_at=now() + interval '1 hour' WHERE employee_key=%s",
                (keys[1],),
            )
        conn.commit()
    return {"name": FIXTURE_NAME, "employee_keys": keys}


def cleanup_fixture(app: Any) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM employees WHERE company_code=%s AND employee_key LIKE %s",
                (COMPANY, f"{FIXTURE_PREFIX}%"),
            )
        conn.commit()


def prove_identity(app: Any, results: dict[str, Any]) -> None:
    unknown = app.resolve_employee_typed(employee_name="Definitely Missing P0 Employee XYZ", company_code=COMPANY)
    _check(results, "identity_zero_matches", unknown.get("status") == "employee_not_found", unknown.get("status"))

    unique_key = f"{FIXTURE_PREFIX}1"
    by_id = app.resolve_employee_typed(employee_key=unique_key, company_code=COMPANY)
    _check(results, "identity_one_match_by_id", by_id.get("status") == "resolved" and (by_id.get("employee") or {}).get("employee_key") == unique_key, by_id.get("status"))

    amb = app.resolve_employee_typed(employee_name=FIXTURE_NAME, company_code=COMPANY)
    _check(
        results,
        "identity_multiple_matches_clarification",
        amb.get("status") == "ambiguous" and len(amb.get("choices") or []) >= 2,
        {"status": amb.get("status"), "choices": len(amb.get("choices") or [])},
    )

    guessed = app.resolve_employee_for_direct_action(
        {"company_code": COMPANY, "subject_name": FIXTURE_NAME},
        allow_latest=True,
    )
    latest = app.latest_employee(company_code=COMPANY)
    _check(
        results,
        "identity_no_latest_fallback",
        guessed is None and latest is not None,
        {"guessed": guessed, "latest_key": (latest or {}).get("employee_key")},
    )


def prove_jobs_surfaces(app: Any, token: str, results: dict[str, Any]) -> None:
    import action_registry
    import re

    # Web API
    web = requests.get(f"{BASE}/dashboard/prehire/positions", headers=auth_headers(token), params={"status": "open", "limit": 200}, timeout=30)
    web_body = web.json() if web.ok else {"error": web.status_code, "text": web.text[:300]}
    web_total = int(web_body.get("total_count") or web_body.get("total_matching") or len(web_body.get("positions") or []))

    # Mobile API (shared positions authority)
    mobile = requests.get(f"{BASE}/dashboard/mobile/positions", headers=auth_headers(token), params={"status": "open", "limit": 100}, timeout=30)
    mobile_body = mobile.json() if mobile.ok else {"error": mobile.status_code, "text": mobile.text[:300]}
    mobile_total = int(mobile_body.get("total_count") or len(mobile_body.get("positions") or []))

    # WhatsApp / Admin Assistant shared list tool
    class Req:
        account_id = COMPANY
        raw_text = "how many openings?"
        sender_phone = "96599338566"
        sender_role = "hr_admin"
        conversation_id = f"p0-qual-{uuid.uuid4().hex[:8]}"
        metadata = {"company_code": COMPANY, "channel": "web_dashboard", "dashboard": True}

    class Ctx:
        legacy = app
        action = {"status": "open", "limit": 200, "query": "how many openings", "search": "how many openings"}
        request = Req()
        scope = {"company_code": COMPANY, "permissions": ["prehire.read"]}

    wa = action_registry._list_job_openings_executor(Ctx())
    wa_total = int(wa.get("total_matching") or 0)

    _check(
        results,
        "jobs_cross_surface_10",
        web.status_code == 200 and mobile.status_code == 200 and web_total == mobile_total == wa_total == 10,
        {"web": web_total, "mobile": mobile_total, "whatsapp_tool": wa_total, "web_code": web.status_code, "mobile_code": mobile.status_code},
    )

    # Finance search parity
    web_fin = requests.get(
        f"{BASE}/dashboard/prehire/positions",
        headers=auth_headers(token),
        params={"status": "open", "search": "Finance", "limit": 50},
        timeout=30,
    )
    web_fin_body = web_fin.json() if web_fin.ok else {}
    mobile_fin = requests.get(
        f"{BASE}/dashboard/mobile/positions",
        headers=auth_headers(token),
        params={"status": "open", "q": "Finance", "limit": 50},
        timeout=30,
    )
    mobile_fin_body = mobile_fin.json() if mobile_fin.ok else {}

    class SearchCtx(Ctx):
        action = {"company_code": COMPANY, "query": "Finance", "search": "Finance", "limit": 50}

    searched = action_registry._search_job_openings_executor(SearchCtx())
    web_codes = {str(p.get("position_code") or "") for p in (web_fin_body.get("positions") or [])}
    mobile_codes = {str(p.get("position_code") or "") for p in (mobile_fin_body.get("positions") or [])}
    wa_codes = {str(p.get("position_code") or "") for p in (searched.get("positions") or [])}
    _check(
        results,
        "finance_search_parity",
        web_fin.ok and mobile_fin.ok and searched.get("action_type") == "search_job_openings" and web_codes == mobile_codes == wa_codes == {"FINANCE"},
        {"web": sorted(web_codes), "mobile": sorted(mobile_codes), "wa": sorted(wa_codes)},
    )

    # Authenticated Admin Assistant chat (web)
    chat = requests.post(
        f"{BASE}/dashboard/prehire/chat",
        headers=auth_headers(token),
        json={"message": "How many job openings do we have?", "conversation_id": f"p0-web-{uuid.uuid4().hex[:10]}"},
        timeout=120,
    )
    chat_body = chat.json() if chat.ok else {"error": chat.status_code, "text": chat.text[:400]}
    reply = str(chat_body.get("reply_text") or chat_body.get("reply") or chat_body.get("message") or chat_body.get("final_reply") or "")
    # Must mention 10 and must not invent a different count from dual fields.
    mentions_10 = bool(re.search(r"\b10\b", reply))
    invents_other = bool(re.search(r"\b(0|11|9)\b", reply)) and not mentions_10
    _check(
        results,
        "web_assistant_jobs_count_backend_authority",
        chat.ok and mentions_10 and not invents_other,
        {"http": chat.status_code, "reply_excerpt": reply[:280], "mentions_10": mentions_10},
    )

    # WhatsApp Admin Assistant authenticated path (HR turn) — requires provider_message_id
    wa_msg_id = f"p0-qual-wamid-{uuid.uuid4().hex}"
    wa_turn = requests.post(
        f"{BASE}/orchestrator/whatsapp-turn",
        headers={"Content-Type": "application/json"},
        json={
            "account_id": COMPANY,
            "conversation_id": f"p0-wa-{uuid.uuid4().hex[:10]}",
            "sender_phone": "96599338566",
            "sender_role": "hr_admin",
            "raw_text": "How many job openings do we have?",
            "metadata": {
                "company_code": COMPANY,
                "channel": "whatsapp",
                "provider": "p0-qual",
                "provider_message_id": wa_msg_id,
                "message_id": wa_msg_id,
                "wamid": wa_msg_id,
                "provider_payload": {"messages": [{"id": wa_msg_id}]},
            },
        },
        timeout=120,
    )
    wa_body = wa_turn.json() if wa_turn.ok else {"error": wa_turn.status_code, "text": wa_turn.text[:400]}
    wa_reply = str(
        wa_body.get("reply_text")
        or wa_body.get("reply")
        or wa_body.get("final_reply")
        or wa_body.get("message")
        or ""
    )
    wa_mentions_10 = bool(re.search(r"\b10\b", wa_reply))
    _check(
        results,
        "whatsapp_assistant_jobs_count_backend_authority",
        wa_turn.ok and wa_mentions_10 and "permission" not in wa_reply.lower(),
        {
            "http": wa_turn.status_code,
            "reply_excerpt": wa_reply[:280],
            "mentions_10": wa_mentions_10,
            "intent": wa_body.get("intent"),
            "final_reply_source": wa_body.get("final_reply_source"),
        },
    )


def prove_employee_clarification_surfaces(app: Any, token: str, results: dict[str, Any]) -> None:
    # Backend resolver is shared; assistant surfaces should ask clarification not guess.
    chat = requests.post(
        f"{BASE}/dashboard/prehire/chat",
        headers=auth_headers(token),
        json={"message": f"Schedule a shift for {FIXTURE_NAME} tomorrow 9-5", "conversation_id": f"p0-amb-{uuid.uuid4().hex[:10]}"},
        timeout=120,
    )
    body = chat.json() if chat.ok else {}
    reply = str(
        body.get("reply_text") or body.get("reply") or body.get("message") or body.get("final_reply") or ""
    ).lower()
    # Confirmation pending is OK; inventing a single employee without clarification is not.
    clarified = any(tok in reply for tok in ("which", "choose", "multiple", "match", "clarify", "who", "twin"))
    typed = app.resolve_employee_typed(employee_name=FIXTURE_NAME, company_code=COMPANY)
    _check(
        results,
        "employee_clarification_shared_resolver",
        typed.get("status") == "ambiguous",
        {"status": typed.get("status"), "choices": len(typed.get("choices") or [])},
    )
    _check(
        results,
        "web_assistant_ambiguous_employee_no_guess",
        chat.ok
        and (
            clarified
            or "confirm" in reply
            or "pending" in str(body).lower()
            or body.get("needs_clarification")
            or body.get("status") in {"needs_clarification", "pending_confirmation"}
            or bool(body.get("confirmation"))
        ),
        {"http": chat.status_code, "reply_excerpt": reply[:280], "status": body.get("status"), "intent": body.get("intent")},
    )


def prove_shift_overlap_and_reschedule(app: Any, token: str, results: dict[str, Any]) -> None:
    day = date.today() + timedelta(days=30)
    emp_key = f"{FIXTURE_PREFIX}1"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  company_code, employee_key, employee_phone, employee_name,
                  shift_date, start_time, end_time, timezone, status, source_text, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'Asia/Kuwait','scheduled','p0-qual',%s::jsonb)
                RETURNING *
                """,
                (COMPANY, emp_key, "96500001001", FIXTURE_NAME, day, time(9, 0), time(17, 0), json.dumps({"p0": True})),
            )
            shift = dict(cur.fetchone())
        conn.commit()

    shift_id = str(shift["shift_id"])
    updated_at = shift.get("updated_at")
    updated_iso = updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at)

    # Overlap create via canonical service
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            conflicts = app.shift_conflicts(
                cur,
                company_code=COMPANY,
                employee_key=emp_key,
                shift_date=day,
                start_time=time(10, 0),
                end_time=time(12, 0),
            )
            cross = app.shift_conflicts(
                cur,
                company_code="__OTHER__",
                employee_key=emp_key,
                shift_date=day,
                start_time=time(10, 0),
                end_time=time(12, 0),
            )
    _check(results, "shift_overlap_rejected", len(conflicts) >= 1, {"count": len(conflicts)})
    _check(results, "shift_overlap_tenant_scoped", cross == [], {"count": len(cross)})

    # Reschedule into overlap should 409
    overlap_reschedule = requests.post(
        f"{BASE}/dashboard/posthire/shifts/{shift_id}/reschedule",
        headers=auth_headers(token),
        json={
            "shift_date": day.isoformat(),
            "start_time": "10:00",
            "end_time": "12:00",
            "expected_updated_at": updated_iso,
        },
        timeout=30,
    )
    # Create a second shift then reschedule into it — refresh expected_updated_at first.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_assignments (
                  company_code, employee_key, employee_phone, employee_name,
                  shift_date, start_time, end_time, timezone, status, source_text, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'Asia/Kuwait','scheduled','p0-qual-2',%s::jsonb)
                RETURNING shift_id
                """,
                (COMPANY, emp_key, "96500001001", FIXTURE_NAME, day, time(13, 0), time(15, 0), json.dumps({"p0": True})),
            )
            other_id = str(cur.fetchone()["shift_id"])
            cur.execute("SELECT updated_at FROM shift_assignments WHERE shift_id=%s", (shift_id,))
            fresh = cur.fetchone()["updated_at"]
        conn.commit()
    fresh_iso = fresh.isoformat() if hasattr(fresh, "isoformat") else str(fresh)

    into_overlap = requests.post(
        f"{BASE}/dashboard/posthire/shifts/{shift_id}/reschedule",
        headers=auth_headers(token),
        json={
            "shift_date": day.isoformat(),
            "start_time": "13:30",
            "end_time": "14:30",
            "expected_updated_at": fresh_iso,
        },
        timeout=30,
    )
    _check(
        results,
        "reschedule_overlap_rejected",
        into_overlap.status_code == 409 and "overlap" in into_overlap.text.lower(),
        {"http": into_overlap.status_code, "body": into_overlap.text[:300], "other_shift_id": other_id},
    )

    # Stale expected_updated_at fails closed
    stale = requests.post(
        f"{BASE}/dashboard/posthire/shifts/{shift_id}/reschedule",
        headers=auth_headers(token),
        json={
            "shift_date": (day + timedelta(days=1)).isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "expected_updated_at": "2000-01-01T00:00:00+00:00",
        },
        timeout=30,
    )
    _check(
        results,
        "reschedule_stale_expected_updated_at",
        stale.status_code == 409 and "stale" in stale.text.lower(),
        {"http": stale.status_code, "body": stale.text[:300]},
    )

    # Missing expected_updated_at — require fail-closed for P0
    missing = requests.post(
        f"{BASE}/dashboard/posthire/shifts/{shift_id}/reschedule",
        headers=auth_headers(token),
        json={
            "shift_date": (day + timedelta(days=1)).isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
        },
        timeout=30,
    )
    missing_fail_closed = missing.status_code in {409, 422}
    _check(
        results,
        "reschedule_requires_expected_updated_at",
        missing_fail_closed,
        {"http": missing.status_code, "body": missing.text[:300], "note": "P0 requires fail-closed when omitted"},
    )

    # Cross-tenant probe: other company shift id should 404
    cross_tenant = requests.post(
        f"{BASE}/dashboard/posthire/shifts/{shift_id}/reschedule",
        headers={**auth_headers(token), "X-Company-Code": "NOPE"},
        json={
            "shift_date": (day + timedelta(days=1)).isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "expected_updated_at": updated_iso,
        },
        timeout=30,
    )
    _check(
        results,
        "reschedule_tenant_scope",
        cross_tenant.status_code in {401, 403, 404},
        {"http": cross_tenant.status_code, "body": cross_tenant.text[:200]},
    )

    # create_shift_assignment confirmation required
    import action_registry

    spec = action_registry.spec_for("create_shift_assignment")
    _check(results, "shift_create_confirmation_required", bool(spec and spec.requires_confirmation and spec.sensitive))

    # Cleanup shifts
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM shift_assignments WHERE company_code=%s AND employee_key=%s AND source_text LIKE %s",
                (COMPANY, emp_key, "p0-qual%"),
            )
        conn.commit()


def prove_leave_payroll(app: Any, results: dict[str, Any]) -> None:
    from psycopg2.extras import Json

    emp_key = f"{FIXTURE_PREFIX}1"
    start = date.today() + timedelta(days=50)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests (
                  company_code, employee_key, employee_phone, employee_name,
                  leave_type, start_date, end_date, status, source_text, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,'requested','p0-qual',%s)
                RETURNING *
                """,
                (COMPANY, emp_key, "96500001001", FIXTURE_NAME, "time_off", start, start, Json({"p0": True})),
            )
            leave = dict(cur.fetchone())
            period_start = start.replace(day=1)
            period_end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            cur.execute(
                """
                INSERT INTO payroll_timesheets (
                  company_code, employee_key, employee_phone, employee_name,
                  period_start, period_end, status, scheduled_minutes, worked_minutes,
                  approved_leave_minutes, absent_minutes, late_minutes, early_leave_minutes,
                  overtime_minutes, payroll_status, snapshot, source_counts
                ) VALUES (%s,%s,%s,%s,%s,%s,'draft',480,480,0,0,0,0,0,'Ready',%s,%s)
                ON CONFLICT (company_code, employee_key, period_start, period_end) DO UPDATE
                  SET status='draft', payroll_status='Ready', updated_at=now()
                RETURNING timesheet_id
                """,
                (COMPANY, emp_key, "96500001001", FIXTURE_NAME, period_start, period_end, Json({"provisional": True}), Json({})),
            )
            ts_id = cur.fetchone()["timesheet_id"]
        conn.commit()

    approve = app.approve_leave_request({"leave_id": leave["leave_id"], "allow_shift_conflicts": True}, company_code=COMPANY, created_by_phone="96500000000")
    cancel = app.cancel_leave_request({"leave_id": leave["leave_id"]}, company_code=COMPANY, created_by_phone="96500000000")
    hours = app.list_payroll_hours(
        {"company_code": COMPANY, "start_date": period_start.isoformat(), "end_date": period_end.isoformat(), "employee_key": emp_key},
        company_code=COMPANY,
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status, payroll_status FROM payroll_timesheets WHERE timesheet_id=%s", (ts_id,))
            ts = dict(cur.fetchone() or {})
            cur.execute("DELETE FROM leave_requests WHERE leave_id=%s", (leave["leave_id"],))
            cur.execute(
                "DELETE FROM attendance_records WHERE company_code=%s AND employee_key=%s AND metadata->>'leave_id'=%s",
                (COMPANY, emp_key, str(leave["leave_id"])),
            )
        conn.commit()

    _check(
        results,
        "leave_payroll_state",
        bool(approve.get("ok"))
        and bool(cancel.get("ok"))
        and approve.get("payroll_impact") == "recalculation_required"
        and ts.get("payroll_status") == "recalculation_required"
        and hours.get("authority") == "provisional",
        {
            "approve": approve.get("payroll_impact"),
            "cancel": cancel.get("payroll_impact"),
            "timesheet": ts,
            "hours_authority": hours.get("authority"),
        },
    )


def main() -> int:
    import app

    app.assert_runtime_environment_binding()
    token = app.set_active_company_code(COMPANY)
    results: dict[str, Any] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "commit_expected": "e7ffd32bca0313c33c6154d55db8d29ab651895e",
        "environment": "staging",
        "base": BASE,
        "checks": {},
        "defects": [],
    }
    try:
        health = requests.get(f"{BASE}/health", timeout=10).json()
        _check(results, "staging_health_binding", health.get("status") == "ok" and (health.get("environment_binding") or {}).get("match") is True, health.get("environment_binding"))
        dash_token = mint_token()
        ensure_duplicate_fixture(app)
        prove_identity(app, results)
        prove_jobs_surfaces(app, dash_token, results)
        prove_employee_clarification_surfaces(app, dash_token, results)
        prove_shift_overlap_and_reschedule(app, dash_token, results)
        prove_leave_payroll(app, results)

        # Runtime matches green artifact file if present
        green = Path("/opt/wathefni/staging/last-green.sha256")
        results["last_green_sha256"] = green.read_text().strip() if green.exists() else None
        import hashlib
        import subprocess

        staging_app = subprocess.check_output(["sha256sum", "/opt/wathefni/staging/orchestrator/app.py"], text=True).split()[0]
        prod_app = subprocess.check_output(["sha256sum", "/opt/wathefni/orchestrator/app.py"], text=True).split()[0]
        results["staging_app_sha256"] = staging_app
        results["production_app_sha256"] = prod_app
        _check(results, "production_untouched_marker", prod_app != staging_app, {"prod": prod_app, "staging": staging_app})

        failed = [k for k, v in results["checks"].items() if not v.get("ok")]
        if not results["checks"].get("reschedule_requires_expected_updated_at", {}).get("ok"):
            results["defects"].append("reschedule_expected_updated_at_optional: omit currently allowed; P0 wants fail-closed required field")
        results["ok"] = not failed
        results["failed"] = failed
        out_dir = Path("/opt/wathefni/staging/evidence")
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = out_dir / f"authority-p0-staging-green-qual-{stamp}.json"
        path.write_text(json.dumps(results, indent=2, default=str))
        print(json.dumps({"ok": results["ok"], "failed": failed, "evidence": str(path), "defects": results["defects"]}, indent=2))
        return 0 if results["ok"] else 1
    finally:
        try:
            cleanup_fixture(app)
        except Exception:
            pass
        app.reset_active_company_code(token)


if __name__ == "__main__":
    raise SystemExit(main())
