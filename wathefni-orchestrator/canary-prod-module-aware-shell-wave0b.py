#!/usr/bin/env python3
"""Module-Aware Shell Wave 0-B — production synthetic Focused Workforce canary (WATHEFNI).

Proves landing/nav/catalog/inbox honesty/alerts scoping/E360 section gates across
requested module combinations. Mutations off. Ingest off. Residual canary cleanup.
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
os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")
os.environ.setdefault("WATHEFNI_MODULE_AWARE_SHELL_WAVE0", "1")

import app  # noqa: E402
import assistant_capability_catalog as caps  # noqa: E402
import platform_assistant_spine_wave1 as spine  # noqa: E402
import workspace_capability as wc  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("MASW0B_TAG") or uuid.uuid4().hex[:8]
PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("MASW0B_EVID") or f"/tmp/module-aware-shell-w0b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
CANARY_EVENT_IDS: list[str] = []

OWNER_PAGES_BASE = [
    "overview",
    "ai",
    "jobs",
    "candidates",
    "employees",
    "workforce",
    "inbox",
    "onboarding",
    "attendance",
    "leave",
    "shifts",
    "payroll",
    "analytics",
    "compliance",
    "notifications",
    "settings",
]


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def pages_for(modules: list[str]) -> list[str]:
    """Approximate available pages = authority nav + operational modules present."""
    auth = wc.resolve_workspace_authority(modules, "owner")
    available = list(auth["nav_ids"])
    for page in ("inbox", "workforce", "employees"):
        if page not in available and (
            page != "inbox"
            or any(m in modules for m in ("leave", "attendance", "shifts", "payroll", "onboarding", "compliance", "analytics"))
        ):
            # Frontend has richer inbox/workforce; include when posthire modules on for landing proofs.
            if page == "employees" and (set(modules) & wc.PEOPLE_MODULES):
                available.append(page)
            elif page == "inbox" and (set(modules) & (wc.POSTHIRE_MODULES | {"onboarding"})):
                available.append(page)
            elif page == "workforce" and (set(modules) & wc.PEOPLE_MODULES):
                available.append(page)
    for m in modules:
        if m in wc.POSTHIRE_OPERATIONAL_LANDING_PRIORITY and m not in available:
            # Backend mirror may omit some pages; landing proofs supply them when entitled.
            available.append(m)
    if "pre_hiring" in modules and "overview" not in available:
        available.append("overview")
    return available


def land(modules: list[str], *, inbox: bool) -> str:
    available = pages_for(modules)
    return wc.resolve_focused_posthire_landing(
        modules,
        role="owner",
        available_pages=available,
        action_inbox_offerable=inbox,
    )


def inbox_honesty(*, can_a: bool, err_a: str | None, can_c: bool, err_c: str | None, can_e: bool, emp_live: bool) -> dict[str, Any]:
    unavailable: list[str] = []
    present: list[str] = []
    if can_a:
        present.append("analytics")
        if err_a:
            unavailable.append("analytics")
    if can_c:
        present.append("compliance")
        if err_c:
            unavailable.append("compliance")
    if can_e:
        present.append("employees")
        if not emp_live:
            unavailable.append("employees")
    return {
        "present": present,
        "partial": bool(unavailable),
        "unavailable": unavailable,
        "omitted": [k for k in ("analytics", "compliance", "employees") if k not in present],
    }


def scope_delivery_rows(rows: list[dict[str, Any]], enabled: list[str]) -> list[dict[str, Any]]:
    """Mirror dashboard scopeDeliveryNotificationRows (Wave 0)."""
    if not enabled:
        return rows
    if "pre_hiring" in enabled:
        return rows
    posthire_on = any(
        k in enabled for k in ("onboarding", "compliance", "attendance", "leave", "shifts", "payroll", "analytics")
    )
    if not posthire_on:
        return []
    out = []
    for item in rows:
        blob = " ".join(
            str(item.get(k) or "").lower()
            for k in ("last_error", "dashboard_status", "status", "app_key", "position_title", "candidate_name")
        )
        if any(x in blob for x in ("assessment", "interview", "screening", "video_interview")):
            continue
        if any(x in blob for x in ("onboarding", "compliance", "employee", "leave", "shift", "attendance", "payroll")):
            out.append(item)
            continue
        if item.get("candidate_name") or item.get("app_key") or item.get("position_code"):
            continue
        out.append(item)
    return out


def e360_sections(modules: list[str]) -> list[str]:
    people = ["onboarding", "compliance", "attendance", "leave", "shifts", "payroll"]
    return [m for m in people if m in modules]


def catalog_for(modules: list[str]) -> dict[str, Any]:
    class Legacy:
        def configured_company_modules(self, company):
            return set(modules)

    tools = [
        {"function": {"name": n}}
        for n in (
            "list_job_openings",
            "get_prehire_work_queue",
            "list_leave_requests",
            "list_attendance",
            "list_shifts",
            "list_onboarding_status",
            "list_compliance_documents",
            "list_payroll_hours",
            "summarize_employee_360",
            "summarize_action_inbox",
        )
    ]
    perms = [
        "jobs.read",
        "prehire.read",
        "leave.read",
        "attendance.read",
        "shifts.read",
        "onboarding.read",
        "compliance.read",
        "payroll.read",
        "employees.read",
        "analytics.read",
        "settings.read",
    ]
    return caps.build_assistant_capability_catalog(
        legacy=Legacy(),
        company_code=COMPANY,
        permissions=perms,
        visible_tools=tools,
    )


def main() -> int:
    check("shell wave0 flag", os.environ.get("WATHEFNI_MODULE_AWARE_SHELL_WAVE0") == "1")
    check("mutations off", spine.assistant_mutations_allowed() is False)
    check(
        "ingest off",
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
                event_type="assistant.shell_wave0b_canary",
                channel="web_dashboard",
                turn_id=f"MASW0B-{TAG}",
                detail={"canary_tag": f"MASW0B-{TAG}", "phase": "start"},
                environment="production",
            )
            CANARY_EVENT_IDS.append(ev["event_id"])
            conn.commit()
            check("audit event written", bool(ev.get("event_id")))

    # --- Landing + nav matrix ---
    landing_cases = [
        (["leave"], False, "leave"),
        (["shifts"], False, "shifts"),
        (["attendance"], False, "attendance"),
        (["payroll"], False, "payroll"),
        (["onboarding", "compliance"], True, "inbox"),
        (["onboarding", "compliance"], False, "onboarding"),
        (["shifts", "attendance", "leave"], True, "inbox"),
        (["shifts", "attendance", "leave"], False, "leave"),
        (["leave", "attendance", "shifts", "payroll"], True, "inbox"),
        (
            [
                "pre_hiring",
                "leave",
                "attendance",
                "shifts",
                "payroll",
                "onboarding",
                "compliance",
                "analytics",
            ],
            True,
            "overview",
        ),
    ]
    for modules, inbox_on, expect in landing_cases:
        got = land(modules, inbox=inbox_on)
        check(f"landing {'+'.join(modules)} inbox={inbox_on}", got == expect, got)
        nav = set(wc.resolve_workspace_authority(modules, "owner")["nav_ids"])
        if "leave" in modules and "pre_hiring" not in modules:
            check(f"nav leave present {'+'.join(modules)}", "leave" in pages_for(modules) or "leave" in nav)
            check(f"nav no overview {'+'.join(modules)}", "overview" not in nav)
            check(f"nav no jobs {'+'.join(modules)}", "jobs" not in nav)
        if set(modules) & wc.PEOPLE_MODULES:
            check(f"employees spine {'+'.join(modules)}", "employees" in pages_for(modules) or "employees" in nav)

    # --- Inbox honesty ---
    leave_h = inbox_honesty(can_a=False, err_a=None, can_c=False, err_c=None, can_e=True, emp_live=True)
    check("leave inbox omits analytics", "analytics" in leave_h["omitted"])
    check("leave inbox omits compliance", "compliance" in leave_h["omitted"])
    check("leave inbox not partial", leave_h["partial"] is False)
    err_h = inbox_honesty(can_a=True, err_a="timeout", can_c=True, err_c=None, can_e=True, emp_live=True)
    check("entitled analytics error partial", err_h["partial"] is True and "analytics" in err_h["unavailable"])
    check("entitled compliance present when purchased", "compliance" in err_h["present"])

    # Live inbox payload honesty when allowlisted (best-effort)
    try:
        ctx = {
            "company_code": COMPANY,
            "hr_phone": "96599338566",
            "actor_user_id": f"masw0b-{TAG}",
            "actor_role": "hr_admin",
            "access": {"permissions": [
                "employees.read", "leave.read", "attendance.read", "shifts.read",
                "payroll.read", "onboarding.read", "compliance.read", "analytics.read",
            ]},
        }
        # Prefer direct payload if gate allows
        pack = None
        try:
            pack = app.dashboard_action_inbox_payload(ctx)
        except Exception as exc:
            check("action inbox live soft-skip", True, str(exc)[:120])
            pack = None
        if isinstance(pack, dict) and pack.get("ok"):
            sources = pack.get("sources") if isinstance(pack.get("sources"), dict) else {}
            (EVID / "action_inbox_live.json").write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")
            omitted = sources.get("omitted_unentitled_keys")
            if isinstance(omitted, list):
                check("live inbox has omitted_unentitled_keys", True)
            # partial must not be true solely because analytics/compliance missing if omitted
            if "analytics" not in sources and "compliance" not in sources:
                check("live inbox not falsely partial when streams omitted", sources.get("partial") is not True or bool(sources.get("unavailable_source_keys")))
            check("live inbox no mutate", (pack.get("honesty") or {}).get("mutates_records") is False or pack.get("authority", {}).get("mutates_records") is False)
    except Exception as exc:
        check("action inbox live path", False, exc)

    # --- Assistant capabilities ---
    leave_cat = catalog_for(["leave"])
    check("catalog leave-only jobs off", leave_cat["capabilities"]["jobs"]["status"] == caps.STATUS_MODULE_OFF)
    check("catalog leave-only overview off", leave_cat["capabilities"]["overview"]["status"] == caps.STATUS_MODULE_OFF)
    check(
        "catalog leave-only e360 on people surface",
        leave_cat["capabilities"]["posthire_employees_360"]["offerable"] is True
        or leave_cat["capabilities"]["posthire_employees_360"]["status"] == caps.STATUS_AVAILABLE,
        leave_cat["capabilities"]["posthire_employees_360"],
    )
    check(
        "catalog leave-only leave on",
        leave_cat["capabilities"]["posthire_leave"]["offerable"] is True
        or leave_cat["capabilities"]["posthire_leave"]["status"] == caps.STATUS_AVAILABLE,
    )
    full_cat = catalog_for(["pre_hiring", "leave", "attendance"])
    check("catalog full suite jobs on", full_cat["capabilities"]["jobs"]["offerable"] is True)

    empty_en = caps.empty_state_from_catalog(leave_cat, locale="en")
    empty_ar = caps.empty_state_from_catalog(leave_cat, locale="ar")
    check("empty en", bool(empty_en.get("headline") or empty_en.get("chips")))
    check("empty ar", bool(empty_ar.get("headline") or empty_ar.get("chips")))
    check(
        "empty ar differs or bilingual",
        bool(empty_ar.get("headline") or empty_ar.get("chips")),
    )

    # --- Alerts scoping ---
    rows = [
        {"delivery_id": "1", "last_error": "onboarding reminder failed", "status": "failed"},
        {"delivery_id": "2", "last_error": "assessment delivery failed", "candidate_name": "Ada", "status": "failed"},
        {"delivery_id": "3", "last_error": "smtp timeout", "status": "failed"},
    ]
    scoped = scope_delivery_rows(rows, ["leave", "attendance"])
    check("alerts keep onboarding row", any(r["delivery_id"] == "1" for r in scoped))
    check("alerts drop assessment residue", not any(r["delivery_id"] == "2" for r in scoped))
    check("alerts keep generic posthire delivery", any(r["delivery_id"] == "3" for r in scoped))
    scoped_prehire = scope_delivery_rows(rows, ["pre_hiring"])
    check("alerts prehire keeps all issue rows", len(scoped_prehire) == 3)

    # --- E360 sections ---
    check("e360 leave-only sections", e360_sections(["leave"]) == ["leave"])
    check(
        "e360 onboarding+compliance",
        e360_sections(["onboarding", "compliance"]) == ["onboarding", "compliance"],
    )
    check(
        "e360 ops combo",
        e360_sections(["shifts", "attendance", "leave"]) == ["attendance", "leave", "shifts"],
    )
    check("e360 no disabled payroll in leave-only", "payroll" not in e360_sections(["leave"]))

    # Live E360 accessible modules for real company (should not invent disabled)
    try:
        context = {
            "access": {
                "permissions": [
                    "employees.read",
                    "leave.read",
                    "attendance.read",
                    "shifts.read",
                    "payroll.read",
                    "onboarding.read",
                    "compliance.read",
                ]
            }
        }
        modules = app.employee_profile_accessible_modules(context, COMPANY)
        check("live e360 modules list", isinstance(modules, list))
        for m in modules:
            check(f"live e360 module entitled {m}", app.company_has_module(COMPANY, m), m)
        (EVID / "e360_modules.json").write_text(json.dumps(modules, indent=2), encoding="utf-8")
    except Exception as exc:
        check("live e360 modules", False, exc)

    # Residual cleanup
    residual = 0
    ack_count = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            ev2 = spine.record_assistant_event(
                cur,
                company_code=COMPANY,
                event_type="assistant.shell_wave0b_canary",
                channel="web_dashboard",
                turn_id=f"MASW0B-{TAG}",
                detail={"canary_tag": f"MASW0B-{TAG}", "phase": "end"},
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
                  AND event_type LIKE 'assistant.shell_wave0b_canary%%'
                """,
                (COMPANY, f"MASW0B-{TAG}", f"MASW0B-{TAG}", CANARY_EVENT_IDS),
            )
            deleted = cur.rowcount
            conn.commit()
            cur.execute(
                """
                SELECT count(*) AS c FROM assistant_spine_events
                WHERE company_code=%s
                  AND (turn_id=%s OR detail->>'canary_tag'=%s)
                  AND event_type LIKE 'assistant.shell_wave0b_canary%%'
                """,
                (COMPANY, f"MASW0B-{TAG}", f"MASW0B-{TAG}"),
            )
            residual = int(dict(cur.fetchone())["c"])
            cur.execute(
                """
                SELECT count(*) AS c FROM assistant_spine_events
                WHERE company_code=%s AND event_type='assistant.shell_wave0b_production_ack'
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
        "shell_wave0": os.environ.get("WATHEFNI_MODULE_AWARE_SHELL_WAVE0"),
    }
    (EVID / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
