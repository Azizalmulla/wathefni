#!/usr/bin/env python3
"""Platform Assistant Wave 2 — Safe Ops Queue Reads smoke (static + optional DB)."""
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
    os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE2"] = "1"
    os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE2_COMPANIES"] = "WATHEFNI"
    os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "0"
    os.environ["WATHEFNI_ASSISTANT_KILL"] = "0"
    os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")

    import platform_assistant_spine_wave1 as spine
    import platform_assistant_wave2_safe_ops_reads as wave2
    import action_registry as registry
    import assistant_capability_catalog as caps

    check("wave2 requires wave1", wave2.platform_assistant_wave2_enabled())
    check("wave2 company", wave2.wave2_enabled_for_company("WATHEFNI"))
    check("wave2 external denied", wave2.wave2_enabled_for_company("ACME") is False)
    check("mutations off", spine.assistant_mutations_allowed() is False)
    h = wave2.honesty_payload()
    check("honesty no payroll", h.get("payroll") is False or h.get("payroll_money") is False)
    check("honesty ingest off", h.get("attendance_ingest") is False)
    check("honesty existing records", h.get("attendance_records_basis") == "existing_records_only")
    check("contracts leave+attendance", bool(spine.get_module_contract("leave_queue")) and bool(spine.get_module_contract("attendance_exceptions")))

    class _Req:
        def __init__(self, *, channel="web_dashboard", company="WATHEFNI", perms=None, locale="en"):
            self.metadata = {
                "channel": channel,
                "dashboard": channel == "web_dashboard",
                "company_code": company,
                "permissions": ["leave.read", "attendance.read", "analytics.read"] if perms is None else list(perms),
                "admin_user": {"phone": "96599338566", "role": "hr_admin"},
                "access": {"role": "hr_admin"},
                "locale": locale,
            }
            self.raw_text = "pending leave"

    class _Legacy:
        def platform_assistant_wave1_tools_enabled(self):
            return True

        def platform_assistant_wave2_tools_enabled(self):
            return True

        def configured_company_modules(self, company):
            return {"leave", "attendance", "analytics", "pre_hiring", "onboarding"}

        def company_has_module(self, company, module):
            return module in self.configured_company_modules(company)

        def list_leave_requests(self, action, company_code=None):
            return {
                "ok": True,
                "leave_requests": [
                    {
                        "leave_id": "L1",
                        "employee_key": "WATHEFNI-1",
                        "employee_name": "Ada",
                        "status": "requested",
                        "start_date": "2026-08-10",
                        "end_date": "2026-08-12",
                        "shift_conflict_count": 1,
                        "team": "Ops",
                    }
                ],
                "count": 1,
                "total_count": 1,
                "has_more": False,
            }

        def list_attendance(self, action, company_code=None):
            return {
                "ok": True,
                "attendance": [
                    {
                        "employee_key": "WATHEFNI-1",
                        "employee_name": "Ada",
                        "status": "late",
                        "late_minutes": 25,
                        "attendance_date": "2026-08-03",
                        "team": "Ops",
                    },
                    {
                        "employee_key": "WATHEFNI-2",
                        "employee_name": "Bob",
                        "status": "absent",
                        "late_minutes": 0,
                        "attendance_date": "2026-08-03",
                        "team": "Ops",
                    },
                ],
                "count": 2,
                "total_count": 2,
                "has_more": False,
                "start_date": "2026-08-01",
                "end_date": "2026-08-03",
            }

    legacy = _Legacy()
    tools = registry.build_tool_schemas(legacy, _Req())
    names = {str((t.get("function") or {}).get("name") or "") for t in tools}
    check("tool leave queue", "summarize_leave_queue" in names)
    check("tool attendance exceptions", "summarize_attendance_exceptions" in names)
    check("mutations hidden", "approve_leave_request" not in names)
    check("whatsapp hide wave2", not any(
        wave2.is_wave2_read_tool(n)
        for n in {str((t.get("function") or {}).get("name") or "") for t in registry.build_tool_schemas(legacy, _Req(channel="whatsapp"))}
    ))

    catalog = caps.build_assistant_capability_catalog(
        legacy=legacy,
        company_code="WATHEFNI",
        permissions=["leave.read", "attendance.read"],
        visible_tools=tools,
    )
    offerable = set(catalog.get("offerable") or [])
    check("catalog leave queue", "posthire_leave_queue" in offerable)
    check("catalog attendance exceptions", "posthire_attendance_exceptions" in offerable)
    empty = caps.empty_state_from_catalog(catalog, locale="en")
    check("chips leave", any("leave" in c.lower() for c in (empty.get("chips") or [])))
    empty_ar = caps.empty_state_from_catalog(catalog, locale="ar")
    check("chips ar", any("إجاز" in c or "حضور" in c for c in (empty_ar.get("chips") or [])))

    ctx = SimpleNamespace(
        request=_Req(),
        action={"company_code": "WATHEFNI", "permissions": ["leave.read", "attendance.read"]},
        state={},
        graph_state={},
        intent={},
        legacy=legacy,
    )
    leave = wave2.execute_summarize_leave_queue(ctx)
    g = leave.get("grounding") or {}
    check("leave grounding", bool(g.get("data_freshness")) and bool(g.get("authority_state")))
    check("leave citations", len(g.get("citations") or []) >= 1)
    check("leave groups", bool((g.get("payload") or {}).get("groups")))
    check("leave deep links prepare-only", all(not a.get("executes") for a in (g.get("proposed_actions") or [])))
    check("leave no mutate", leave.get("mutates_records") is False)

    att = wave2.execute_summarize_attendance_exceptions(ctx)
    ga = att.get("grounding") or {}
    check("attendance grounding", bool(ga.get("data_freshness")))
    check("attendance ingest-off label", "ingest" in (ga.get("summary_en") or "").lower() or (ga.get("payload") or {}).get("capture_ingest") == "off")
    check("attendance citations", len(ga.get("citations") or []) >= 1)
    check("attendance no mutate", att.get("mutates_records") is False)

    # Isolation
    bad = wave2.execute_summarize_leave_queue(
        SimpleNamespace(
            request=_Req(company="ACME"),
            action={"company_code": "ACME", "permissions": ["leave.read"]},
            state={},
            graph_state={},
            intent={},
            legacy=legacy,
        )
    )
    check("tenant isolation", (bad.get("grounding") or {}).get("fallback_key") == "tenant_denied")

    denied = wave2.execute_summarize_leave_queue(
        SimpleNamespace(
            request=_Req(perms=[]),
            action={"company_code": "WATHEFNI", "permissions": []},
            state={},
            graph_state={},
            intent={},
            legacy=legacy,
        )
    )
    check("permission denial", (denied.get("grounding") or {}).get("fallback_key") == "blocked")

    # Module disabled
    class _NoLeave(_Legacy):
        def company_has_module(self, company, module):
            return module != "leave"

    mod = wave2.execute_summarize_leave_queue(
        SimpleNamespace(
            request=_Req(),
            action={"company_code": "WATHEFNI", "permissions": ["leave.read"]},
            state={},
            graph_state={},
            intent={},
            legacy=_NoLeave(),
        )
    )
    check("disabled module denial", (mod.get("grounding") or {}).get("fallback_key") == "blocked")

    # EN/AR fallbacks still via spine
    for key in ("missing", "stale", "partial", "unavailable", "blocked"):
        en = spine.fallback_envelope(key, locale="en")
        ar = spine.fallback_envelope(key, locale="ar")
        check(f"fallback {key} en/ar", en.get("message") and ar.get("message") and en.get("message") != ar.get("message"))

    # Optional DB path
    if os.environ.get("WATHEFNI_POSTGRES_ENV") and os.environ.get("WATHEFNI_ENV"):
        try:
            import app as orch

            ctx_db = SimpleNamespace(
                request=_Req(),
                action={"company_code": "WATHEFNI", "permissions": ["leave.read", "attendance.read"], "status": "requested"},
                state={},
                graph_state={},
                intent={},
                legacy=orch,
            )
            leave_db = wave2.execute_summarize_leave_queue(ctx_db)
            check("db leave envelope", isinstance(leave_db.get("grounding"), dict))
            att_db = wave2.execute_summarize_attendance_exceptions(ctx_db)
            check("db attendance envelope", isinstance(att_db.get("grounding"), dict))
            check(
                "db attendance ingest off",
                (att_db.get("grounding") or {}).get("payload", {}).get("capture_ingest") == "off"
                or "ingest" in ((att_db.get("grounding") or {}).get("summary_en") or "").lower(),
            )
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    spine.ensure_assistant_spine_audit_schema(cur)
                    ev = spine.record_assistant_event(
                        cur,
                        company_code="WATHEFNI",
                        event_type="assistant.wave2_smoke",
                        channel="web_dashboard",
                        detail={"wave2": True},
                    )
                    conn.commit()
            check("audit event", bool(ev.get("event_id")))
        except Exception as exc:
            check("db path", False, exc)
    else:
        print("db path skipped (no postgres env)")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
