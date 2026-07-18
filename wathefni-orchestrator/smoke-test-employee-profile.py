"""Smoke test: Employee 360 profile (read-only, tenant + entitlement scoped).

The unified employee profile composes per-module reads around one person. It must
never leak across tenants and must only surface modules the company has and the
user can read. This test pins:

  - the profile resolves an employee within the session company and returns a
    structured, JSON-safe payload (employee + sections + next_actions)
  - tenant isolation: the same employee_key under a different company does not
    resolve (404)
  - entitlement gating: a section only appears when the user can read that module
  - an empty/unknown key is a clean 404

Run against a DB (staging): python3 smoke-test-employee-profile.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    employee 360 — read-only profile, tenant + entitlement scoped")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    def ctx(company: str, permissions: list[str]):
        return {
            "company_code": company,
            "permissions": permissions,
            "access": {"role": "owner", "permissions": permissions},
            "actor_user_id": "smoke-owner",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-owner",
            "permission_subject_company": company,
            "actor_role": "owner",
            "hr_user": {"role": "owner", "status": "active", "company_code": company},
        }

    owner_perms = sorted(app.hr_role_permissions("owner"))
    valid_section_keys = {"onboarding", "compliance", "attendance", "shifts", "leave", "payroll"}
    # Composite sections are derived from one or more modules' read access rather
    # than being a module themselves (e.g. the Document Hub surfaces files when the
    # user can read onboarding OR compliance). They are not in available_modules.
    composite_sections = {"documents"}

    # locate a real employee to profile
    real_emp = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code, employee_key, name FROM employees WHERE employee_key <> '' LIMIT 1")
            row = cur.fetchone()
            if row:
                real_emp = dict(row)

    if not real_emp:
        print("    (no employees on this DB — running structural checks only)")
        # Empty key still 404s regardless of data.
        try:
            app.dashboard_employee_profile(ctx("WATHEFNI", owner_perms), "")
            check("empty key raises 404", False)
        except app.HTTPException as exc:
            check("empty key raises 404", exc.status_code == 404)
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 0 if FAIL == 0 else 1

    company = str(real_emp["company_code"])
    key = str(real_emp["employee_key"])

    # 1) resolves within the session company with a structured payload
    profile = app.dashboard_employee_profile(ctx(company, owner_perms), key)
    check("profile resolves the requested employee", (profile.get("employee") or {}).get("employee_key") == key)
    check("profile carries the session company", profile.get("company_code") == company)
    sections = profile.get("sections") or {}
    check("sections is a dict", isinstance(sections, dict))
    check("next_actions is a list", isinstance(profile.get("next_actions"), list))
    available = set(profile.get("available_modules") or [])
    check("available_modules is a subset of the post-hire modules", available <= valid_section_keys)
    check("every rendered section is an available module", (set(sections.keys()) - composite_sections) <= available)
    # The documents composite, when present, must be backed by an available module.
    check("documents section implies onboarding/compliance access", "documents" not in sections or bool(available & {"onboarding", "compliance"}))

    # 1b) quick-slice payload contract — the fields the Employee 360 inline
    # actions and "why" context need. Gates mirror the module pages; row ids
    # let the page run registry actions without a second lookup.
    check("payload carries hr_mutate_enabled gate", isinstance(profile.get("hr_mutate_enabled"), bool))
    check("payload carries doc_upload_enabled gate", isinstance(profile.get("doc_upload_enabled"), bool))
    onboarding = sections.get("onboarding")
    if isinstance(onboarding, dict):
        check(
            "onboarding outstanding rows carry item_id",
            all("item_id" in it for it in onboarding.get("outstanding") or []),
        )
    compliance = sections.get("compliance")
    if isinstance(compliance, dict):
        check(
            "compliance rows carry why-context (days/reminded/count)",
            all(
                {"days_until_expiry", "last_reminded_at", "reminder_count"} <= set(d.keys())
                for d in compliance.get("documents") or []
            ),
        )
    payroll = sections.get("payroll")
    if isinstance(payroll, dict):
        check(
            "payroll timesheet rows carry timesheet_id",
            all("timesheet_id" in it for it in payroll.get("items") or []),
        )

    # 2) tenant isolation — same key under a different company does not resolve
    try:
        app.dashboard_employee_profile(ctx("ZZ_NOT_A_TENANT", owner_perms), key)
        check("cross-tenant lookup is blocked (404)", False)
    except app.HTTPException as exc:
        check("cross-tenant lookup is blocked (404)", exc.status_code == 404)

    # 3) entitlement gating — only onboarding.read present -> no payroll/attendance section
    limited = app.employee_profile_accessible_modules(ctx(company, ["onboarding.read"]), company)
    check("limited perms exclude payroll", "payroll" not in limited)
    check("limited perms exclude attendance", "attendance" not in limited)
    check("limited perms cannot exceed onboarding", set(limited) <= {"onboarding"})

    # 4) empty key -> clean 404
    try:
        app.dashboard_employee_profile(ctx(company, owner_perms), "")
        check("empty key raises 404", False)
    except app.HTTPException as exc:
        check("empty key raises 404", exc.status_code == 404)

    # 5) Next Actions engine — test the pure builder directly with synthetic,
    # fully-populated sections so ranking/contract/no-leak are deterministic
    # regardless of this DB's data or the live flag state.
    card = {"employee_key": "emp-x", "name": "Aziz Tester", "phone": "+96599999999"}
    synth_sections = {
        "compliance": {"documents": [
            {"document_type": "civil_id", "document_label": "Civil ID", "status": "expired", "days_until_expiry": -12, "expiry_date": "2026-05-29"},
            {"document_type": "passport", "document_label": "Passport", "status": "missing", "days_until_expiry": None},
            {"document_type": "health_card", "document_label": "Health Card", "status": "expiring_soon", "days_until_expiry": 5, "expiry_date": "2026-06-15"},
            {"document_type": "contract", "document_label": "Contract", "status": "expiring_soon", "days_until_expiry": 20, "expiry_date": "2026-06-30"},
            {"document_type": "visa", "document_label": "Visa", "status": "needs_review", "days_until_expiry": None},
        ]},
        "onboarding": {"outstanding_count": 2, "outstanding": [
            {"item_id": "i1", "label": "Bank details", "status": "pending"},
            {"item_id": "i2", "label": "Signed contract", "status": "pending"},
        ]},
        "leave": {
            "items": [{"leave_type": "annual", "start_date": "2026-06-20", "end_date": "2026-06-25", "status": "requested"}],
            "balances": [{"leave_type": "annual", "current_balance": -3.0}],
        },
        "payroll": {"items": [{"timesheet_id": "ts-1", "period_start": "2026-05-01", "period_end": "2026-05-31", "status": "draft"}]},
        "attendance": {"window_days": 14, "present": 5, "late": 4, "absent": 3},
    }
    actions, summary = app.build_employee_next_actions(card, synth_sections)
    sev_set = {"critical", "high", "medium", "low"}
    module_set = {"onboarding", "compliance", "attendance", "leave", "payroll", "shifts"}
    by_id = {a["id"]: a for a in actions}

    check("engine returns a non-empty ranked list", isinstance(actions, list) and len(actions) > 0)
    check("every action has a valid severity", all(a.get("severity") in sev_set for a in actions))
    check("every action has a valid module", all(a.get("module") in module_set for a in actions))
    check("every action has title + reason + target", all(a.get("title") and a.get("reason") and isinstance(a.get("target"), dict) for a in actions))
    check(
        "executable rows carry action_type+args; nav rows omit action_type",
        all(
            ((isinstance(a.get("action_type"), str) and bool(a["action_type"]) and isinstance(a.get("args"), dict))
             if a.get("executable") else ("action_type" not in a))
            for a in actions
        ),
    )

    weight = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sev_seq = [weight[a["severity"]] for a in actions]
    check("list is ordered severity-first (critical -> low)", sev_seq == sorted(sev_seq))
    check("the critical item is ranked first", actions and actions[0]["severity"] == "critical")

    check("expired document is critical", by_id.get("compliance:expired:civil_id", {}).get("severity") == "critical")
    check("missing required document is high", by_id.get("compliance:missing:passport", {}).get("severity") == "high")
    check("expiring <=7d is high", by_id.get("compliance:expiring:health_card", {}).get("severity") == "high")
    check("expiring 8-30d is medium", by_id.get("compliance:expiring:contract", {}).get("severity") == "medium")
    check("needs_review is high", by_id.get("compliance:review:visa", {}).get("severity") == "high")
    check("pending leave is high", any(a["module"] == "leave" and a["severity"] == "high" for a in actions))
    check("draft timesheet is high", by_id.get("payroll:review:ts-1", {}).get("severity") == "high")
    check("incomplete onboarding is medium", by_id.get("onboarding:incomplete", {}).get("severity") == "medium")
    check("attendance pattern surfaces", any(a["module"] == "attendance" for a in actions))
    check("negative leave balance is observe-only low", by_id.get("leave:balance:annual", {}).get("severity") == "low")

    comp_ids = [a["id"] for a in actions if a["module"] == "compliance"]
    check(
        "expired ranks before expiring within compliance",
        "compliance:expired:civil_id" in comp_ids and "compliance:expiring:health_card" in comp_ids
        and comp_ids.index("compliance:expired:civil_id") < comp_ids.index("compliance:expiring:health_card"),
    )

    # executable actions reuse ONLY whitelisted actions, with the expected permission
    import tool_call_orchestrator as tco
    expected_perm = {
        "compliance_send_reminder": "compliance.manage",
        "compliance_mark_reviewed": "compliance.manage",
        "send_onboarding_reminder": "onboarding.manage",
    }
    exec_types = {a["action_type"] for a in actions if a.get("executable")}
    check("executable action_types are all whitelisted", all(t in tco.TOOL_PERMISSION_MAP for t in exec_types))
    check("executable action_types map to the expected permission", all(tco.TOOL_PERMISSION_MAP.get(t) == expected_perm.get(t) for t in exec_types))
    check("leave decisions are navigation-only", all(not a.get("executable") for a in actions if a["module"] == "leave"))
    check("payroll decisions are navigation-only", all(not a.get("executable") for a in actions if a["module"] == "payroll"))
    check("attendance items are navigation-only", all(not a.get("executable") for a in actions if a["module"] == "attendance"))

    # no raw document data / storage details may leak into the engine output
    import json as _json
    blob = _json.dumps(actions)
    leak_markers = ("file_registry", "file_id", "storage", "http://", "https://", "/files/", "s3://")
    check("no file ids / urls / storage paths leak", not any(m in blob for m in leak_markers))

    check("summary total equals action count", summary.get("total") == len(actions))
    check("summary severity counts sum to total", sum(summary.get("by_severity", {}).values()) == len(actions))
    check("summary advertises the visible cap (5)", summary.get("visible_cap") == 5)

    # 6) flag gate — the profile only emits the enriched engine when the flag is on
    import os as _os
    prev_flag = _os.environ.get("WATHEFNI_EMPLOYEE_NEXT_ACTIONS")
    try:
        _os.environ["WATHEFNI_EMPLOYEE_NEXT_ACTIONS"] = "off"
        check("flag OFF -> engine disabled", app.employee_next_actions_enabled() is False)
        off_profile = app.dashboard_employee_profile(ctx(company, owner_perms), key)
        check("flag OFF -> profile reports next_actions_enabled false", off_profile.get("next_actions_enabled") is False)
        check("flag OFF -> no next_actions_summary", off_profile.get("next_actions_summary") is None)
        _os.environ["WATHEFNI_EMPLOYEE_NEXT_ACTIONS"] = "on"
        check("flag ON -> engine enabled", app.employee_next_actions_enabled() is True)
        on_profile = app.dashboard_employee_profile(ctx(company, owner_perms), key)
        check("flag ON -> profile reports next_actions_enabled true", on_profile.get("next_actions_enabled") is True)
        check("flag ON -> next_actions_summary present", isinstance(on_profile.get("next_actions_summary"), dict))
    finally:
        if prev_flag is None:
            _os.environ.pop("WATHEFNI_EMPLOYEE_NEXT_ACTIONS", None)
        else:
            _os.environ["WATHEFNI_EMPLOYEE_NEXT_ACTIONS"] = prev_flag

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    EMPLOYEE 360: FAILURES")
        return 1
    print("    EMPLOYEE 360: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
