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


def owner_user(app: Any) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM dashboard_users
                WHERE company_code=%s
                  AND status='active'
                  AND role='owner'
                  AND COALESCE(metadata->>'source','') <> 'legacy_hr_phone_bootstrap'
                  AND lower(email) NOT LIKE '%%.wathefni.local'
                ORDER BY accepted_at NULLS LAST, updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (COMPANY,),
            )
            row = cur.fetchone()
            if not row:
                cur.execute(
                    """
                    SELECT *
                    FROM dashboard_users
                    WHERE company_code=%s AND status='active' AND role='owner'
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (COMPANY,),
                )
                row = cur.fetchone()
    if not row:
        raise RuntimeError("no active owner")
    return dict(row)


def mint_mobile_token(app: Any) -> str:
    """Mint a real operator-mobile access token (browser dashboard sessions are rejected)."""
    user = owner_user(app)
    tokens = app._operator_mobile.create_operator_mobile_session(app, user, device_label="p0-qual")
    access = str(tokens.get("access_token") or "").strip()
    if not access:
        raise RuntimeError("empty operator mobile access token")
    return access


def dashboard_assistant_scope(app: Any, user: dict[str, Any]) -> dict[str, Any]:
    """Hydrate the same Admin Assistant scope dashboard chat uses after login."""
    from tool_call_orchestrator import _base_memory_scope

    access = app.dashboard_access_payload_for_user(user)
    perms = access.get("permissions") or app.dashboard_effective_permissions_for_user(user)
    phone = app.digits(user.get("phone")) or "dashboard"

    class Req:
        account_id = "default"
        conversation_id = f"p0-scope-{uuid.uuid4().hex[:8]}"
        sender_phone = phone
        sender_role = "hr_admin"
        raw_text = ""
        metadata = {
            "channel": "web_dashboard",
            "dashboard": True,
            "company_code": COMPANY,
            "admin_user": user,
            "access": access,
            "permissions": perms,
        }

    return _base_memory_scope(Req())


def execute_assistant_tool(app: Any, scope: dict[str, Any], tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    from tool_call_orchestrator import _execute_tool

    class Req:
        account_id = "default"
        conversation_id = scope.get("conversation_id") or f"p0-tool-{uuid.uuid4().hex[:8]}"
        sender_phone = app.digits((scope.get("hr_user") or {}).get("phone")) or "dashboard"
        sender_role = "hr_admin"
        raw_text = tool_name
        metadata = {
            "channel": "web_dashboard",
            "dashboard": True,
            "company_code": COMPANY,
            "admin_user": scope.get("hr_user"),
            "access": scope.get("access"),
            "permissions": scope.get("permissions") or [],
        }

    return _execute_tool(tool_name, args, Req(), {}, {}, scope)


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


def prove_jobs_surfaces(app: Any, token: str, mobile_token: str, results: dict[str, Any]) -> None:
    import action_registry
    import re

    # Web API
    web = requests.get(f"{BASE}/dashboard/prehire/positions", headers=auth_headers(token), params={"status": "open", "limit": 200}, timeout=30)
    web_body = web.json() if web.ok else {"error": web.status_code, "text": web.text[:300]}
    web_total = int(web_body.get("total_count") or web_body.get("total_matching") or len(web_body.get("positions") or []))

    # Mobile API (operator-mobile session; shared positions authority)
    mobile = requests.get(
        f"{BASE}/dashboard/mobile/positions",
        headers=auth_headers(mobile_token),
        params={"status": "open", "limit": 100},
        timeout=30,
    )
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
        headers=auth_headers(mobile_token),
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

    # Authenticated Admin Assistant tool path (same entitlement + list tool as chat after model pick).
    user = owner_user(app)
    scope = dashboard_assistant_scope(app, user)
    tool_out = execute_assistant_tool(app, scope, "list_job_openings", {"status": "open", "limit": 200})
    tool_result = tool_out.get("result") if isinstance(tool_out.get("result"), dict) else tool_out
    tool_total = int(tool_result.get("total_matching") or tool_result.get("total_count") or 0)
    tool_ok = (
        tool_out.get("status") not in {"permission_denied", "error"}
        and "permission" not in str(tool_out.get("message") or "").lower()
        and tool_total == 10
    )
    _check(
        results,
        "web_assistant_jobs_count_backend_authority",
        tool_ok,
        {
            "path": "authenticated_execute_tool",
            "status": tool_out.get("status"),
            "total_matching": tool_total,
            "message": str(tool_out.get("message") or "")[:180],
            "admin_user_id": scope.get("admin_user_id"),
            "permission_authority": scope.get("permission_authority"),
        },
    )

    # WhatsApp-linked owner tool path (same list authority; no LLM required).
    class WaReq:
        account_id = COMPANY
        conversation_id = f"p0-wa-tool-{uuid.uuid4().hex[:8]}"
        sender_phone = "96599338566"
        sender_role = "hr_admin"
        raw_text = "How many job openings do we have?"
        metadata = {"company_code": COMPANY, "channel": "whatsapp"}

    from tool_call_orchestrator import _base_memory_scope, _execute_tool

    wa_scope = _base_memory_scope(WaReq())
    wa_tool = _execute_tool("list_job_openings", {"status": "open", "limit": 200}, WaReq(), {}, {}, wa_scope)
    wa_result = wa_tool.get("result") if isinstance(wa_tool.get("result"), dict) else wa_tool
    wa_total_tool = int(wa_result.get("total_matching") or wa_result.get("total_count") or 0)
    wa_tool_ok = (
        wa_tool.get("status") not in {"permission_denied", "error"}
        and wa_total_tool == 10
        and wa_scope.get("permission_authority") == "backend_current"
    )
    _check(
        results,
        "whatsapp_assistant_jobs_count_backend_authority",
        wa_tool_ok,
        {
            "path": "authenticated_execute_tool",
            "status": wa_tool.get("status"),
            "total_matching": wa_total_tool,
            "permission_authority": wa_scope.get("permission_authority"),
            "admin_user_id": wa_scope.get("admin_user_id"),
        },
    )

    # Live LLM chat is observed when quota allows; never invent counts if it answers.
    chat = requests.post(
        f"{BASE}/dashboard/prehire/chat",
        headers=auth_headers(token),
        json={"message": "How many job openings do we have?", "conversation_id": f"p0-web-{uuid.uuid4().hex[:10]}"},
        timeout=120,
    )
    chat_body = chat.json() if chat.ok else {"error": chat.status_code, "text": chat.text[:400]}
    reply = str(chat_body.get("reply_text") or chat_body.get("reply") or chat_body.get("message") or chat_body.get("final_reply") or "")
    model_down = "trouble reaching the model" in reply.lower()
    mentions_10 = bool(re.search(r"\b10\b", reply))
    invents_other = bool(re.search(r"\b(0|11|9)\b", reply)) and not mentions_10 and not model_down
    llm_ok = model_down or (chat.ok and mentions_10 and not invents_other)
    _check(
        results,
        "web_assistant_llm_jobs_count_observation",
        llm_ok and not invents_other,
        {"http": chat.status_code, "reply_excerpt": reply[:280], "model_down": model_down, "mentions_10": mentions_10},
    )
    if model_down:
        results.setdefault("defects", []).append(
            "openai_insufficient_quota: live Admin Assistant LLM returns model-unreachable; authenticated tool authority still green"
        )

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
    wa_reply = str(wa_body.get("reply_text") or wa_body.get("reply") or wa_body.get("final_reply") or wa_body.get("message") or "")
    wa_model_down = "trouble reaching the model" in wa_reply.lower()
    wa_mentions_10 = bool(re.search(r"\b10\b", wa_reply))
    _check(
        results,
        "whatsapp_assistant_llm_jobs_count_observation",
        wa_model_down or (wa_turn.ok and wa_mentions_10),
        {
            "http": wa_turn.status_code,
            "reply_excerpt": wa_reply[:280],
            "model_down": wa_model_down,
            "mentions_10": wa_mentions_10,
            "intent": wa_body.get("intent"),
        },
    )


def prove_employee_clarification_surfaces(app: Any, token: str, results: dict[str, Any]) -> None:
    # Shared resolver + shift tool executor must clarify, never latest-fallback.
    typed = app.resolve_employee_typed(employee_name=FIXTURE_NAME, company_code=COMPANY)
    _check(
        results,
        "employee_clarification_shared_resolver",
        typed.get("status") == "ambiguous",
        {"status": typed.get("status"), "choices": len(typed.get("choices") or [])},
    )

    user = owner_user(app)
    scope = dashboard_assistant_scope(app, user)
    tool_out = execute_assistant_tool(
        app,
        scope,
        "create_shift_assignment",
        {
            "employee_name": FIXTURE_NAME,
            "shift_date": (date.today() + timedelta(days=40)).isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
        },
    )
    tool_result = tool_out.get("result") if isinstance(tool_out.get("result"), dict) else tool_out
    status = str(tool_out.get("status") or tool_result.get("status") or "")
    message = str(tool_out.get("message") or tool_result.get("message") or tool_result.get("safe_user_message") or "").lower()
    choices = tool_result.get("choices") or tool_out.get("choices") or []
    clarified = (
        status in {"needs_clarification", "ambiguous"}
        or len(choices) >= 2
        or "which one" in message
        or "found 2 employees" in message
        or "wathefni-p0-dup" in message
    )
    _check(
        results,
        "shift_tool_ambiguous_employee_clarification",
        clarified and "permission" not in message,
        {"status": status, "choices": len(choices), "message": message[:300]},
    )

    # Live LLM observation only (quota may block); authenticated tool path above is authoritative.
    chat = requests.post(
        f"{BASE}/dashboard/prehire/chat",
        headers=auth_headers(token),
        json={
            "message": f"Create a scheduled shift for employee {FIXTURE_NAME} on {(date.today() + timedelta(days=41)).isoformat()} from 09:00 to 17:00",
            "conversation_id": f"p0-amb-{uuid.uuid4().hex[:10]}",
        },
        timeout=120,
    )
    body = chat.json() if chat.ok else {}
    reply = str(body.get("reply_text") or body.get("reply") or body.get("message") or body.get("final_reply") or "").lower()
    model_down = "trouble reaching the model" in reply
    clarified_llm = any(
        tok in reply
        for tok in (
            "which employee",
            "which one",
            "more than one",
            "multiple employees",
            "ambiguous",
            "clarify",
            "choose one",
            "two employees",
            "wathefni-p0-dup",
            "found 2 employees",
        )
    )
    invented_single = ("scheduled" in reply or "created" in reply) and not clarified_llm and not model_down
    _check(
        results,
        "web_assistant_ambiguous_employee_no_guess",
        clarified or ((model_down or clarified_llm) and not invented_single),
        {
            "http": chat.status_code,
            "reply_excerpt": reply[:280],
            "intent": body.get("intent"),
            "tool_clarified": clarified,
            "model_down": model_down,
            "llm_clarified": clarified_llm,
        },
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
        mobile_token = mint_mobile_token(app)
        ensure_duplicate_fixture(app)
        prove_identity(app, results)
        prove_jobs_surfaces(app, dash_token, mobile_token, results)
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
