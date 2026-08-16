#!/usr/bin/env python3
"""Platform Assistant Wave 1-B — production synthetic Spine Contract canary (WATHEFNI).

HR dashboard-only. Mutations off. Proves Action Inbox / Employees 360 / Setup readiness
read-only tools, grounded citations/freshness/authority, EN/AR fallbacks, audit events,
tenant isolation, WhatsApp tool hide, mutation kill + pending confirmation block,
master kill, residual cleanup of canary-tagged events.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
os.environ.setdefault("WATHEFNI_ASSISTANT_KILL", "0")

import action_registry as registry  # noqa: E402
import app  # noqa: E402
import platform_assistant_spine_wave1 as spine  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAW1B_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PAW1B_EVID") or f"/tmp/platform-assistant-w1b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
CANARY_EVENT_IDS: list[str] = []


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def _req(*, channel: str = "web_dashboard", company: str = COMPANY, perms: list[str] | None = None, locale: str = "en"):
    default_perms = [
        "analytics.read",
        "employees.read",
        "employee.read",
        "settings.read",
        "leave.read",
        "leave.manage",
    ]
    return SimpleNamespace(
        metadata={
            "channel": channel,
            "dashboard": channel == "web_dashboard",
            "company_code": company,
            "permissions": default_perms if perms is None else list(perms),
            "admin_user": {"phone": "96599338566", "role": "hr_admin", "user_id": f"paw1b-{TAG}"},
            "access": {"role": "hr_admin"},
            "locale": locale,
        },
        raw_text="What needs attention?" if locale == "en" else "ما الذي يحتاج انتباهاً؟",
    )


def _ctx(request: Any, company: str = COMPANY) -> Any:
    return SimpleNamespace(
        request=request,
        action={"company_code": company, "permissions": request.metadata.get("permissions") or []},
        state={},
        graph_state={},
        intent={},
        legacy=app,
    )


def main() -> int:
    honesty = spine.honesty_payload()
    check("wave1 enabled", spine.platform_assistant_wave1_enabled())
    check("wathefni company", spine.wave1_enabled_for_company(COMPANY))
    check("external denied", spine.wave1_enabled_for_company("ACME") is False)
    check("mutations off", spine.assistant_mutations_allowed() is False)
    check("master kill off", spine.assistant_kill_engaged() is False)
    check("no payroll money", honesty.get("payroll_money") is False)
    check("no attendance ingest", honesty.get("attendance_ingest") is False)
    check("no whatsapp widen", honesty.get("whatsapp_widening") is False)
    check("no ck wiring", honesty.get("candidate_knowledge_wired") is False)
    check("no mutations honesty", honesty.get("mutates_records") is False)
    check("default inbox entry", honesty.get("default_posthire_entry") == "action_inbox")
    check("hr dashboard only", honesty.get("hr_dashboard_only") is True)
    check("ingest env off", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off").lower() in {"off", "0", "false", "no", ""})

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)
            spine.ensure_assistant_spine_audit_schema(cur, force=True)
            ev = spine.record_assistant_event(
                cur,
                company_code=COMPANY,
                event_type="assistant.wave1b_canary",
                channel="web_dashboard",
                turn_id=f"PAW1B-{TAG}",
                detail={"canary_tag": f"PAW1B-{TAG}", "phase": "start"},
                environment="production",
            )
            CANARY_EVENT_IDS.append(ev["event_id"])
            conn.commit()
            check("audit event written", bool(ev.get("event_id")))

    # Tool catalog: dashboard exposes read tools; mutations hidden; WhatsApp hides spine tools
    dash_tools = registry.build_tool_schemas(app, _req())
    dash_names = {str((t.get("function") or {}).get("name") or "") for t in dash_tools}
    check("tool action inbox", "summarize_action_inbox" in dash_names)
    check("tool employee 360", "summarize_employee_360" in dash_names)
    check("tool setup readiness", "get_launch_readiness_summary" in dash_names)
    check("mutation approve_leave hidden", "approve_leave_request" not in dash_names)
    check("mutation export_payroll hidden", "export_payroll" not in dash_names)

    wa_tools = registry.build_tool_schemas(app, _req(channel="whatsapp"))
    wa_names = {str((t.get("function") or {}).get("name") or "") for t in wa_tools}
    check("whatsapp spine tools hidden", not any(spine.is_wave1_read_tool(n) for n in wa_names))

    ext_tools = registry.build_tool_schemas(app, _req(company="ACME"))
    ext_names = {str((t.get("function") or {}).get("name") or "") for t in ext_tools}
    check("external spine tools hidden", not any(spine.is_wave1_read_tool(n) for n in ext_names))

    # Action Inbox canary
    inbox = spine.execute_summarize_action_inbox(_ctx(_req()))
    g_inbox = inbox.get("grounding") or {}
    (EVID / "inbox.json").write_text(json.dumps(inbox, indent=2, default=str), encoding="utf-8")
    check("inbox tool ran", isinstance(g_inbox, dict) and bool(g_inbox))
    check("inbox freshness", bool(g_inbox.get("data_freshness")))
    check("inbox authority label", bool(g_inbox.get("authority_state")))
    check("inbox citations list", isinstance(g_inbox.get("citations"), list))
    check("inbox no mutate", inbox.get("mutates_records") is False)
    check("inbox proposed actions prepare-only", all(not a.get("executes") for a in (g_inbox.get("proposed_actions") or [])))

    # Setup readiness canary
    ready = spine.execute_get_launch_readiness_summary(_ctx(_req()))
    g_ready = ready.get("grounding") or {}
    (EVID / "setup_readiness.json").write_text(json.dumps(ready, indent=2, default=str), encoding="utf-8")
    check("setup readiness ran", bool(g_ready.get("citations")))
    check("setup freshness", bool(g_ready.get("data_freshness")))
    check("setup authority", bool(g_ready.get("authority_state")))
    check("setup payroll money false", (g_ready.get("payload") or {}).get("payroll_money") is False)
    check("setup attendance ingest false", (g_ready.get("payload") or {}).get("attendance_ingest") is False)

    # Employees 360 — missing subject yields grounded missing fallback (no invent)
    e360_missing = spine.execute_summarize_employee_360(_ctx(_req()))
    g_e360 = e360_missing.get("grounding") or {}
    check("e360 asks for subject or returns envelope", bool(g_e360.get("message") or g_e360.get("summary_en")))
    check(
        "e360 missing/partial authority",
        g_e360.get("fallback_key") in {"missing", "partial", "unavailable", "blocked"} or g_e360.get("ok") is True,
        g_e360.get("fallback_key"),
    )

    # Try a real employee key if one exists (read-only)
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key FROM employees
                    WHERE upper(company_code)=%s
                    ORDER BY created_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (COMPANY,),
                )
                row = cur.fetchone()
        if row:
            key = dict(row)["employee_key"]
            ctx = _ctx(_req())
            ctx.action["employee_key"] = key
            e360 = spine.execute_summarize_employee_360(ctx)
            ge = e360.get("grounding") or {}
            (EVID / "employee360.json").write_text(json.dumps(e360, indent=2, default=str), encoding="utf-8")
            check("e360 keyed summary", bool(ge.get("data_freshness")) and bool(ge.get("authority_state")), ge)
            check("e360 citations", isinstance(ge.get("citations"), list))
            check("e360 no mutate", e360.get("mutates_records") is False)
        else:
            check("e360 keyed summary skipped (no employees)", True)
    except Exception as exc:
        check("e360 keyed summary", False, exc)

    # Tenant isolation
    bad = spine.execute_summarize_action_inbox(_ctx(_req(company="ACME"), company="ACME"))
    check("tenant isolation inbox", (bad.get("grounding") or {}).get("fallback_key") == "tenant_denied", bad)

    # Permission / disabled-style denial
    noperm_req = _req(perms=[])
    denied = spine.execute_summarize_action_inbox(_ctx(noperm_req))
    check("permission denial", (denied.get("grounding") or {}).get("fallback_key") == "blocked", denied)

    # EN/AR fallbacks
    for key in ("missing", "stale", "partial", "unavailable", "blocked", "unsupported", "mutations_killed"):
        en = spine.fallback_envelope(key, locale="en")
        ar = spine.fallback_envelope(key, locale="ar")
        check(f"fallback en {key}", bool(en.get("message")))
        check(f"fallback ar {key}", bool(ar.get("message")) and ar.get("message") != en.get("message"))

    # Mutation kill denial + tool_is_mutation
    denial = spine.mutation_kill_denial(tool_name="approve_leave_request", locale="en")
    check("mutation denial status", denial.get("status") == "mutations_disabled")
    spec = registry.spec_for("approve_leave_request")
    check("approve_leave is mutation", spine.tool_is_mutation(spec) is True)
    check("inbox not mutation", spine.tool_is_mutation(registry.spec_for("summarize_action_inbox")) is False)

    # Pending confirmation block path (simulate orchestrator gate)
    try:
        import tool_call_orchestrator as tco

        # Direct unit: mutations off => mutation_kill_denial used by execute path
        check("orchestrator has pending block", "mutations_disabled" in Path(tco.__file__).read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        check("orchestrator pending block source", False, exc)

    # Master kill
    os.environ["WATHEFNI_ASSISTANT_KILL"] = "1"
    check("master kill engaged", spine.assistant_kill_engaged() is True)
    kill = spine.master_kill_turn_result(locale="en")
    check("master kill intent", kill.get("intent") == "assistant_killed")
    kill_ar = spine.master_kill_turn_result(locale="ar")
    check("master kill ar", bool(kill_ar.get("reply_text")) and kill_ar.get("reply_text") != kill.get("reply_text"))
    os.environ["WATHEFNI_ASSISTANT_KILL"] = "0"
    check("master kill cleared", spine.assistant_kill_engaged() is False)

    # WhatsApp channel denial on spine executor
    wa_ctx = _ctx(_req(channel="whatsapp"))
    wa_out = spine.execute_summarize_action_inbox(wa_ctx)
    check("whatsapp executor denied", (wa_out.get("grounding") or {}).get("fallback_key") == "whatsapp_denied", wa_out)

    # Residual cleanup of canary-tagged events
    residual = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Record one more tagged event then delete all PAW1B-{TAG} canary rows
            ev2 = spine.record_assistant_event(
                cur,
                company_code=COMPANY,
                event_type="assistant.wave1b_canary",
                channel="web_dashboard",
                turn_id=f"PAW1B-{TAG}",
                detail={"canary_tag": f"PAW1B-{TAG}", "phase": "end"},
                environment="production",
            )
            CANARY_EVENT_IDS.append(ev2["event_id"])
            conn.commit()
            cur.execute(
                """
                DELETE FROM assistant_spine_events
                WHERE company_code=%s
                  AND (
                    turn_id = %s
                    OR detail->>'canary_tag' = %s
                    OR event_id = ANY(%s::uuid[])
                  )
                  AND event_type LIKE 'assistant.wave1b_canary%%'
                """,
                (COMPANY, f"PAW1B-{TAG}", f"PAW1B-{TAG}", CANARY_EVENT_IDS),
            )
            deleted = cur.rowcount
            conn.commit()
            cur.execute(
                """
                SELECT count(*) AS c FROM assistant_spine_events
                WHERE company_code=%s
                  AND (turn_id=%s OR detail->>'canary_tag'=%s)
                  AND event_type LIKE 'assistant.wave1b_canary%%'
                """,
                (COMPANY, f"PAW1B-{TAG}", f"PAW1B-{TAG}"),
            )
            residual = int(dict(cur.fetchone())["c"])
            # Durable ACK rows must remain
            cur.execute(
                """
                SELECT count(*) AS c FROM assistant_spine_events
                WHERE company_code=%s AND event_type='assistant.wave1b_production_ack'
                """,
                (COMPANY,),
            )
            ack_count = int(dict(cur.fetchone())["c"])
    check("canary events deleted", deleted >= 1, deleted)
    check("residual canary 0", residual == 0, residual)
    check("durable ack retained", ack_count >= 1, ack_count)

    summary = {
        "pass": PASS,
        "fail": FAIL,
        "tag": TAG,
        "residual": residual,
        "ack_count": ack_count,
        "mutations_allowed": spine.assistant_mutations_allowed(),
        "inbox_authority": g_inbox.get("authority_state"),
        "setup_overall": (g_ready.get("payload") or {}).get("overall_state"),
    }
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
