#!/usr/bin/env python3
"""Platform Assistant Wave 2-B — production synthetic Safe Ops Queue Reads canary (WATHEFNI).

HR dashboard-only. Mutations off. Proves Leave queue + Attendance exception
read-only tools, grounded citations/freshness/authority, grouping, EN/AR,
prepare-only deep links, ingest-off honesty, audit events, tenant/permission/
manager-scope isolation, kill switches, residual cleanup of canary-tagged events.
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

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE2", "1")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE2_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
os.environ.setdefault("WATHEFNI_ASSISTANT_KILL", "0")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")

import action_registry as registry  # noqa: E402
import app  # noqa: E402
import platform_assistant_spine_wave1 as spine  # noqa: E402
import platform_assistant_wave2_safe_ops_reads as wave2  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAW2B_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PAW2B_EVID") or f"/tmp/platform-assistant-w2b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
CANARY_EVENT_IDS: list[str] = []
PHONE = "96599338566"


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def _req(
    *,
    channel: str = "web_dashboard",
    company: str = COMPANY,
    perms: list[str] | None = None,
    locale: str = "en",
    phone: str = PHONE,
    role: str = "hr_admin",
):
    default_perms = [
        "leave.read",
        "leave.manage",
        "attendance.read",
        "attendance.manage",
        "analytics.read",
        "employees.read",
    ]
    return SimpleNamespace(
        metadata={
            "channel": channel,
            "dashboard": channel == "web_dashboard",
            "company_code": company,
            "permissions": default_perms if perms is None else list(perms),
            "admin_user": {"phone": phone, "role": role, "user_id": f"paw2b-{TAG}"},
            "access": {"role": role, "phone": phone},
            "locale": locale,
        },
        raw_text="pending leave and late attendance" if locale == "en" else "إجازات معلّقة وحضور متأخر",
        sender_phone=phone,
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
    honesty = wave2.honesty_payload()
    check("wave1 enabled", spine.platform_assistant_wave1_enabled())
    check("wave2 enabled", wave2.platform_assistant_wave2_enabled())
    check("wathefni company", wave2.wave2_enabled_for_company(COMPANY))
    check("external denied", wave2.wave2_enabled_for_company("ACME") is False)
    check("mutations off", spine.assistant_mutations_allowed() is False)
    check("master kill off", spine.assistant_kill_engaged() is False)
    check("no payroll", honesty.get("payroll") is False)
    check("no shifts", honesty.get("shifts") is False)
    check("no onboarding surface", honesty.get("onboarding_assistant_surface") is False)
    check("no attendance ingest", honesty.get("attendance_ingest") is False)
    check("capture ingest off", honesty.get("capture_ingest") == "off")
    check("existing records basis", honesty.get("attendance_records_basis") == "existing_records_only")
    check("no whatsapp widen", honesty.get("whatsapp_widening") is False)
    check("no mutations honesty", honesty.get("mutations") is False)
    check("hr dashboard only", honesty.get("hr_dashboard_only") is True)
    check(
        "ingest env off",
        os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off").lower() in {"off", "0", "false", "no", ""},
    )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("production db", db == "wathefni", db)
            spine.ensure_assistant_spine_audit_schema(cur, force=True)
            ev = spine.record_assistant_event(
                cur,
                company_code=COMPANY,
                event_type="assistant.wave2b_canary",
                channel="web_dashboard",
                turn_id=f"PAW2B-{TAG}",
                detail={"canary_tag": f"PAW2B-{TAG}", "phase": "start"},
                environment="production",
            )
            CANARY_EVENT_IDS.append(ev["event_id"])
            conn.commit()
            check("audit event written", bool(ev.get("event_id")))

    dash_tools = registry.build_tool_schemas(app, _req())
    dash_names = {str((t.get("function") or {}).get("name") or "") for t in dash_tools}
    check("tool leave queue", "summarize_leave_queue" in dash_names)
    check("tool attendance exceptions", "summarize_attendance_exceptions" in dash_names)
    check("wave1 inbox still present", "summarize_action_inbox" in dash_names)
    check("mutation approve_leave hidden", "approve_leave_request" not in dash_names)
    check("mutation mark_absent hidden", "mark_attendance_absent" not in dash_names)
    check("mutation export_payroll hidden", "export_payroll" not in dash_names)

    wa_tools = registry.build_tool_schemas(app, _req(channel="whatsapp"))
    wa_names = {str((t.get("function") or {}).get("name") or "") for t in wa_tools}
    check("whatsapp wave2 tools hidden", not any(wave2.is_wave2_read_tool(n) for n in wa_names))

    ext_tools = registry.build_tool_schemas(app, _req(company="ACME"))
    ext_names = {str((t.get("function") or {}).get("name") or "") for t in ext_tools}
    check("external wave2 tools hidden", not any(wave2.is_wave2_read_tool(n) for n in ext_names))

    # --- Leave queue canary ---
    captured_leave: dict[str, Any] = {}
    orig_leave = app.list_leave_requests

    def _wrap_leave(action, company_code=None):
        captured_leave["viewer_phone"] = (action or {}).get("viewer_phone")
        captured_leave["company_code"] = company_code or (action or {}).get("company_code")
        return orig_leave(action, company_code=company_code)

    app.list_leave_requests = _wrap_leave  # type: ignore[method-assign]
    try:
        leave = wave2.execute_summarize_leave_queue(_ctx(_req()))
    finally:
        app.list_leave_requests = orig_leave  # type: ignore[method-assign]

    g_leave = leave.get("grounding") or {}
    (EVID / "leave_queue.json").write_text(json.dumps(leave, indent=2, default=str), encoding="utf-8")
    check("leave tool ran", isinstance(g_leave, dict) and bool(g_leave))
    check("leave freshness", bool(g_leave.get("data_freshness")))
    check("leave authority label", bool(g_leave.get("authority_state")))
    check("leave citations list", isinstance(g_leave.get("citations"), list))
    check("leave no mutate", leave.get("mutates_records") is False)
    check(
        "leave proposed actions prepare-only",
        all(not a.get("executes") for a in (g_leave.get("proposed_actions") or [])),
    )
    check(
        "leave deep links present",
        bool(g_leave.get("deep_links")) or bool(g_leave.get("proposed_actions")),
    )
    payload_leave = g_leave.get("payload") or {}
    groups_leave = payload_leave.get("groups") or {}
    check(
        "leave groups present",
        isinstance(groups_leave, dict)
        and ("by_employee" in groups_leave or "by_status" in groups_leave or payload_leave.get("total") == 0),
        groups_leave,
    )
    check("leave viewer_phone injected", captured_leave.get("viewer_phone") == PHONE, captured_leave)
    check("leave summary en", bool(g_leave.get("summary_en") or g_leave.get("message")))
    check("leave summary ar", bool(g_leave.get("summary_ar") or g_leave.get("message")))
    check("leave soa leave", payload_leave.get("soa") == "leave" or g_leave.get("fallback_key"))

    leave_ar = wave2.execute_summarize_leave_queue(_ctx(_req(locale="ar")))
    g_leave_ar = leave_ar.get("grounding") or {}
    check("leave ar locale", bool(g_leave_ar.get("summary_ar") or g_leave_ar.get("message")))

    # --- Attendance exceptions canary ---
    captured_att: dict[str, Any] = {}
    orig_att = app.list_attendance

    def _wrap_att(action, company_code=None):
        captured_att["viewer_phone"] = (action or {}).get("viewer_phone")
        return orig_att(action, company_code=company_code)

    app.list_attendance = _wrap_att  # type: ignore[method-assign]
    try:
        att = wave2.execute_summarize_attendance_exceptions(_ctx(_req()))
    finally:
        app.list_attendance = orig_att  # type: ignore[method-assign]

    g_att = att.get("grounding") or {}
    (EVID / "attendance_exceptions.json").write_text(json.dumps(att, indent=2, default=str), encoding="utf-8")
    check("attendance tool ran", isinstance(g_att, dict) and bool(g_att))
    check("attendance freshness", bool(g_att.get("data_freshness")))
    check("attendance authority label", bool(g_att.get("authority_state")))
    check("attendance citations list", isinstance(g_att.get("citations"), list))
    check("attendance no mutate", att.get("mutates_records") is False)
    check(
        "attendance proposed actions prepare-only",
        all(not a.get("executes") for a in (g_att.get("proposed_actions") or [])),
    )
    payload_att = g_att.get("payload") or {}
    check("attendance capture_ingest off", payload_att.get("capture_ingest") == "off" or "ingest" in (g_att.get("summary_en") or "").lower())
    check("attendance existing records", payload_att.get("records_basis") == "existing_records_only" or "existing" in (g_att.get("summary_en") or "").lower())
    check(
        "attendance ingest-off in summary",
        "ingest" in (g_att.get("summary_en") or "").lower() or "device" in (g_att.get("summary_en") or "").lower(),
        g_att.get("summary_en"),
    )
    groups_att = payload_att.get("groups") or {}
    check(
        "attendance groups present",
        isinstance(groups_att, dict)
        and ("by_employee" in groups_att or "by_status" in groups_att or payload_att.get("total") == 0),
        groups_att,
    )
    check("attendance viewer_phone injected", captured_att.get("viewer_phone") == PHONE, captured_att)
    check("attendance authority synthetic-or-partial", g_att.get("authority_state") in {"synthetic", "partial", "live_controlled", "unavailable", "blocked"} or bool(g_att.get("fallback_key")))

    att_ar = wave2.execute_summarize_attendance_exceptions(_ctx(_req(locale="ar")))
    g_att_ar = att_ar.get("grounding") or {}
    check("attendance ar locale", bool(g_att_ar.get("summary_ar") or g_att_ar.get("message")))
    check(
        "attendance ar differs or bilingual",
        bool(g_att_ar.get("summary_ar")) and (
            g_att_ar.get("summary_ar") != g_att.get("summary_en")
            or bool(g_att_ar.get("summary_en"))
        ),
    )

    # Tenant isolation
    bad_leave = wave2.execute_summarize_leave_queue(_ctx(_req(company="ACME"), company="ACME"))
    check("tenant isolation leave", (bad_leave.get("grounding") or {}).get("fallback_key") == "tenant_denied", bad_leave)
    bad_att = wave2.execute_summarize_attendance_exceptions(_ctx(_req(company="ACME"), company="ACME"))
    check("tenant isolation attendance", (bad_att.get("grounding") or {}).get("fallback_key") == "tenant_denied", bad_att)

    # Permission denial
    noperm = _req(perms=[])
    denied_leave = wave2.execute_summarize_leave_queue(_ctx(noperm))
    check("permission denial leave", (denied_leave.get("grounding") or {}).get("fallback_key") == "blocked", denied_leave)
    denied_att = wave2.execute_summarize_attendance_exceptions(_ctx(noperm))
    check("permission denial attendance", (denied_att.get("grounding") or {}).get("fallback_key") == "blocked", denied_att)

    # Manager-scope isolation: scope-denied surface + viewer_phone wiring (already checked)
    orig_leave2 = app.list_leave_requests

    def _deny_scope(action, company_code=None):
        return {"ok": False, "error": "employee_outside_manager_scope"}

    app.list_leave_requests = _deny_scope  # type: ignore[method-assign]
    try:
        scoped = wave2.execute_summarize_leave_queue(_ctx(_req(role="manager")))
    finally:
        app.list_leave_requests = orig_leave2  # type: ignore[method-assign]
    check(
        "manager scope denial surfaced",
        (scoped.get("grounding") or {}).get("fallback_key") in {"blocked", "unavailable"},
        scoped,
    )

    orig_att2 = app.list_attendance

    def _deny_att_scope(action, company_code=None):
        return {"ok": False, "error": "scope_denied"}

    app.list_attendance = _deny_att_scope  # type: ignore[method-assign]
    try:
        scoped_att = wave2.execute_summarize_attendance_exceptions(_ctx(_req(role="manager")))
    finally:
        app.list_attendance = orig_att2  # type: ignore[method-assign]
    check(
        "manager scope denial attendance",
        (scoped_att.get("grounding") or {}).get("fallback_key") in {"blocked", "unavailable"},
        scoped_att,
    )

    # Honest stale/partial/unavailable/blocked EN/AR
    for key in ("missing", "stale", "partial", "unavailable", "blocked", "unsupported", "mutations_killed"):
        en = spine.fallback_envelope(key, locale="en")
        ar = spine.fallback_envelope(key, locale="ar")
        check(f"fallback en {key}", bool(en.get("message")))
        check(f"fallback ar {key}", bool(ar.get("message")) and ar.get("message") != en.get("message"))

    # Mutation kill + tool classification
    denial = spine.mutation_kill_denial(tool_name="approve_leave_request", locale="en")
    check("mutation denial status", denial.get("status") == "mutations_disabled")
    check("approve_leave is mutation", spine.tool_is_mutation(registry.spec_for("approve_leave_request")) is True)
    check("leave queue not mutation", spine.tool_is_mutation(registry.spec_for("summarize_leave_queue")) is False)
    check(
        "attendance exceptions not mutation",
        spine.tool_is_mutation(registry.spec_for("summarize_attendance_exceptions")) is False,
    )

    # Master kill
    os.environ["WATHEFNI_ASSISTANT_KILL"] = "1"
    check("master kill engaged", spine.assistant_kill_engaged() is True)
    kill_leave = wave2.execute_summarize_leave_queue(_ctx(_req()))
    check("master kill leave", (kill_leave.get("grounding") or {}).get("fallback_key") == "killed", kill_leave)
    os.environ["WATHEFNI_ASSISTANT_KILL"] = "0"
    check("master kill cleared", spine.assistant_kill_engaged() is False)

    # WhatsApp channel denial on wave2 executors
    wa_out = wave2.execute_summarize_leave_queue(_ctx(_req(channel="whatsapp")))
    check("whatsapp leave denied", (wa_out.get("grounding") or {}).get("fallback_key") == "whatsapp_denied", wa_out)
    wa_att = wave2.execute_summarize_attendance_exceptions(_ctx(_req(channel="whatsapp")))
    check("whatsapp attendance denied", (wa_att.get("grounding") or {}).get("fallback_key") == "whatsapp_denied", wa_att)

    # Residual cleanup of canary-tagged events
    residual = 0
    ack_count = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            ev2 = spine.record_assistant_event(
                cur,
                company_code=COMPANY,
                event_type="assistant.wave2b_canary",
                channel="web_dashboard",
                turn_id=f"PAW2B-{TAG}",
                detail={"canary_tag": f"PAW2B-{TAG}", "phase": "end"},
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
                  AND event_type LIKE 'assistant.wave2b_canary%%'
                """,
                (COMPANY, f"PAW2B-{TAG}", f"PAW2B-{TAG}", CANARY_EVENT_IDS),
            )
            deleted = cur.rowcount
            conn.commit()
            cur.execute(
                """
                SELECT count(*) AS c FROM assistant_spine_events
                WHERE company_code=%s
                  AND (turn_id=%s OR detail->>'canary_tag'=%s)
                  AND event_type LIKE 'assistant.wave2b_canary%%'
                """,
                (COMPANY, f"PAW2B-{TAG}", f"PAW2B-{TAG}"),
            )
            residual = int(dict(cur.fetchone())["c"])
            cur.execute(
                """
                SELECT count(*) AS c FROM assistant_spine_events
                WHERE company_code=%s AND event_type='assistant.wave2b_production_ack'
                """,
                (COMPANY,),
            )
            ack_count = int(dict(cur.fetchone())["c"])
            # Wave 1 durable ACK must remain
            cur.execute(
                """
                SELECT count(*) AS c FROM assistant_spine_events
                WHERE company_code=%s AND event_type='assistant.wave1b_production_ack'
                """,
                (COMPANY,),
            )
            w1_ack = int(dict(cur.fetchone())["c"])
    check("canary events deleted", deleted >= 1, deleted)
    check("residual canary 0", residual == 0, residual)
    check("durable wave2 ack retained", ack_count >= 1, ack_count)
    check("durable wave1 ack retained", w1_ack >= 1, w1_ack)

    summary = {
        "pass": PASS,
        "fail": FAIL,
        "tag": TAG,
        "residual": residual,
        "ack_count": ack_count,
        "mutations_allowed": spine.assistant_mutations_allowed(),
        "leave_authority": g_leave.get("authority_state"),
        "leave_total": payload_leave.get("total"),
        "attendance_authority": g_att.get("authority_state"),
        "attendance_total": payload_att.get("total"),
        "attendance_capture_ingest": payload_att.get("capture_ingest"),
    }
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
