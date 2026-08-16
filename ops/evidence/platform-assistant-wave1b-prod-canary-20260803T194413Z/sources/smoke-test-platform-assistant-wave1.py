#!/usr/bin/env python3
"""Platform Assistant Wave 1 — Spine Contract smoke (static + optional staging DB)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

PASS = FAIL = 0
ROOT = Path(__file__).resolve().parent


def check(name: str, ok: bool, detail=None) -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS  {name}")
    else:
        FAIL += 1
        print(f"FAIL  {name} :: {detail}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE1"] = "1"
    os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES"] = "WATHEFNI"
    os.environ.pop("WATHEFNI_ASSISTANT_KILL", None)
    os.environ.pop("WATHEFNI_ASSISTANT_MUTATIONS", None)  # default mutations OFF under wave1

    import platform_assistant_spine_wave1 as spine
    import action_registry as registry
    import assistant_capability_catalog as caps

    check("wave1 version", bool(spine.WAVE1_VERSION))
    check("wathefni only", spine.ALLOWED_COMPANY == "WATHEFNI")
    check("wave1 enabled", spine.platform_assistant_wave1_enabled())
    check("company ok", spine.wave1_enabled_for_company("WATHEFNI"))
    check("external company denied", spine.wave1_enabled_for_company("ACME") is False)
    check("mutations default off", spine.assistant_mutations_allowed() is False)
    check("master kill default off", spine.assistant_kill_engaged() is False)

    honesty = spine.honesty_payload()
    check("honesty no money", honesty.get("payroll_money") is False)
    check("honesty no ingest", honesty.get("attendance_ingest") is False)
    check("honesty no mutations", honesty.get("mutates_records") is False)
    check("honesty no legal auth", honesty.get("legal_government_authority") is False)
    check("default posthire inbox", honesty.get("default_posthire_entry") == "action_inbox")
    check("hr dashboard only", honesty.get("hr_dashboard_only") is True)

    contracts = spine.list_module_contracts()
    keys = {c["module_key"] for c in contracts}
    check("contract action_inbox", "action_inbox" in keys)
    check("contract employees_360", "employees_360" in keys)
    check("contract setup_console", "setup_console" in keys)
    check("contracts read-only", all(c["honesty"]["read_only"] for c in contracts))
    check("contracts no mutations", all(not c["honesty"]["mutates_records"] for c in contracts))

    env = spine.grounded_envelope(
        ok=True,
        summary_en="ok",
        summary_ar="حسناً",
        citations=[{"kind": "t", "id": "1", "module": "action_inbox", "as_of": spine.kuwait_now_iso()}],
        authority_state="read_only_compose",
        confidence="grounded",
    )
    check("grounding has freshness", bool(env.get("data_freshness")))
    check("grounding has authority", env.get("authority_state") == "read_only_compose")
    check("grounding has citations", len(env.get("citations") or []) == 1)

    for key in ("missing", "stale", "partial", "unavailable", "blocked", "unsupported"):
        fb = spine.fallback_envelope(key, locale="en")
        fb_ar = spine.fallback_envelope(key, locale="ar")
        check(f"fallback en {key}", bool(fb.get("message")))
        check(f"fallback ar {key}", bool(fb_ar.get("message")) and fb_ar.get("message") != fb.get("message"))

    # Master kill
    os.environ["WATHEFNI_ASSISTANT_KILL"] = "1"
    check("master kill on", spine.assistant_kill_engaged() is True)
    kill = spine.master_kill_turn_result(locale="en")
    check("master kill reply", "kill" in (kill.get("reply_text") or "").lower() or "unavailable" in (kill.get("reply_text") or "").lower())
    os.environ["WATHEFNI_ASSISTANT_KILL"] = "0"
    check("master kill off", spine.assistant_kill_engaged() is False)

    # Mutation kill denial
    denial = spine.mutation_kill_denial(tool_name="approve_leave_request", locale="en")
    check("mutation denial status", denial.get("status") == "mutations_disabled")

    # Registry tools present + mutation tools filtered when mutations off
    class _Req:
        metadata = {
            "channel": "web_dashboard",
            "dashboard": True,
            "company_code": "WATHEFNI",
            "permissions": [
                "analytics.read",
                "employees.read",
                "employee.read",
                "settings.read",
                "leave.read",
                "leave.manage",
            ],
            "admin_user": {"phone": "96599338566", "role": "hr_admin"},
            "access": {"role": "hr_admin"},
            "locale": "en",
        }
        raw_text = "What needs attention?"

    class _Legacy:
        def platform_assistant_wave1_tools_enabled(self):
            return True

        def configured_company_modules(self, company):
            return {
                "pre_hiring",
                "analytics",
                "onboarding",
                "attendance",
                "leave",
                "shifts",
                "payroll",
                "compliance",
            }

    legacy = _Legacy()
    tools = registry.build_tool_schemas(legacy, _Req())
    names = set()
    for t in tools:
        fn = t.get("function") or {}
        names.add(str(fn.get("name") or ""))
    check("tool summarize_action_inbox", "summarize_action_inbox" in names)
    check("tool summarize_employee_360", "summarize_employee_360" in names)
    check("tool get_launch_readiness_summary", "get_launch_readiness_summary" in names)
    check("mutation tools hidden", "approve_leave_request" not in names and "export_payroll" not in names)

    # WhatsApp channel must not expose wave1 tools
    class _Wa:
        metadata = {"channel": "whatsapp", "company_code": "WATHEFNI", "permissions": ["analytics.read", "employees.read", "settings.read"]}
        raw_text = "hi"

    wa_tools = registry.build_tool_schemas(legacy, _Wa())
    wa_names = {str((t.get("function") or {}).get("name") or "") for t in wa_tools}
    check("whatsapp no spine tools", not any(spine.is_wave1_read_tool(n) for n in wa_names))

    # External company schemas drop spine tools
    class _Ext:
        metadata = {
            "channel": "web_dashboard",
            "dashboard": True,
            "company_code": "ACME",
            "permissions": ["analytics.read", "employees.read", "settings.read"],
        }
        raw_text = ""

    ext_tools = registry.build_tool_schemas(legacy, _Ext())
    ext_names = {str((t.get("function") or {}).get("name") or "") for t in ext_tools}
    check("external no spine tools", not any(spine.is_wave1_read_tool(n) for n in ext_names))

    catalog = caps.build_assistant_capability_catalog(
        legacy=legacy,
        company_code="WATHEFNI",
        permissions=["analytics.read", "employees.read", "settings.read", "leave.read"],
        visible_tools=tools,
    )
    offerable = set(catalog.get("offerable") or [])
    check("catalog action inbox", "posthire_action_inbox" in offerable)
    check("catalog e360", "posthire_employees_360" in offerable)
    check("catalog setup", "posthire_setup_readiness" in offerable)
    empty_en = caps.empty_state_from_catalog(catalog, locale="en")
    empty_ar = caps.empty_state_from_catalog(catalog, locale="ar")
    check("empty chips en inbox", any("Action Inbox" in c or "attention" in c.lower() for c in (empty_en.get("chips") or [])))
    check("empty chips ar", any("صندوق" in c or "الإجراءات" in c for c in (empty_ar.get("chips") or [])))

    # Executor: tenant deny / permission deny / grounding without DB
    ctx = SimpleNamespace(
        request=_Req(),
        action={"company_code": "WATHEFNI", "permissions": ["analytics.read"]},
        state={},
        graph_state={},
        intent={},
        legacy=legacy,
    )
    # Provide minimal inbox compose without dashboard payload
    out = spine.execute_summarize_action_inbox(ctx)
    check("inbox tool returns grounding", isinstance(out.get("grounding"), dict))
    g = out.get("grounding") or {}
    check("inbox freshness", bool(g.get("data_freshness")))
    check("inbox authority label", bool(g.get("authority_state")))
    check("inbox no mutate", out.get("mutates_records") is False)

    ctx_bad = SimpleNamespace(
        request=_Req(),
        action={"company_code": "ACME"},
        state={},
        graph_state={},
        intent={},
        legacy=legacy,
    )
    bad = spine.execute_summarize_action_inbox(ctx_bad)
    check("tenant isolation on tool", (bad.get("grounding") or {}).get("fallback_key") == "tenant_denied")

    ctx_noperm = SimpleNamespace(
        request=SimpleNamespace(
            metadata={"channel": "web_dashboard", "dashboard": True, "company_code": "WATHEFNI", "permissions": [], "locale": "en"},
            raw_text="",
        ),
        action={"company_code": "WATHEFNI"},
        state={},
        graph_state={},
        intent={},
        legacy=legacy,
    )
    denied = spine.execute_summarize_action_inbox(ctx_noperm)
    check("permission denial", (denied.get("grounding") or {}).get("fallback_key") == "blocked")

    # Optional staging DB path
    if os.environ.get("WATHEFNI_POSTGRES_ENV") and os.environ.get("WATHEFNI_ENV"):
        try:
            import app as orch

            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    spine.ensure_assistant_spine_audit_schema(cur)
                    ev = spine.record_assistant_event(
                        cur,
                        company_code="WATHEFNI",
                        event_type="assistant.wave1_smoke",
                        channel="web_dashboard",
                        detail={"smoke": True},
                    )
                    conn.commit()
                    cur.execute(
                        "SELECT count(*) AS c FROM assistant_spine_events WHERE event_id=%s::uuid",
                        (ev["event_id"],),
                    )
                    c = int(dict(cur.fetchone())["c"])
            check("audit event persisted", c == 1)

            # Launch readiness read
            ctx2 = SimpleNamespace(
                request=_Req(),
                action={"company_code": "WATHEFNI", "permissions": ["settings.read", "analytics.read", "employees.read"]},
                state={},
                graph_state={},
                intent={},
                legacy=orch,
            )
            ready = spine.execute_get_launch_readiness_summary(ctx2)
            check("setup readiness tool", isinstance(ready.get("grounding"), dict))
            check("setup readiness citations", len((ready.get("grounding") or {}).get("citations") or []) >= 1)
        except Exception as exc:
            check("db path", False, exc)
    else:
        print("db path skipped (no postgres env)")

    # Mutations can be explicitly re-enabled
    os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "1"
    check("mutations explicit on", spine.assistant_mutations_allowed() is True)
    os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "0"
    check("mutations explicit off", spine.assistant_mutations_allowed() is False)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
