#!/usr/bin/env python3
"""Module-Aware Shell Wave 0 — Focused Workforce Experience smoke."""
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
    os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
    os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")

    import assistant_capability_catalog as caps
    import workspace_capability as wc

    # Landing matrix
    cases = [
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
    for modules, inbox_on, expect in cases:
        available = list(wc.resolve_workspace_authority(modules, "owner")["nav_ids"])
        if inbox_on and "inbox" not in available:
            available.append("inbox")
        got = wc.resolve_focused_posthire_landing(
            modules, role="owner", available_pages=available, action_inbox_offerable=inbox_on
        )
        check(f"landing {'+'.join(modules) or 'none'} inbox={inbox_on}", got == expect, got)

    # Nav: leave-only keeps employees, hides overview/jobs
    leave_nav = set(wc.resolve_workspace_authority(["leave"], "owner")["nav_ids"])
    check("leave nav has employees", "employees" in leave_nav)
    check("leave nav has leave", "leave" in leave_nav)
    check("leave nav no overview", "overview" not in leave_nav)
    check("leave nav no jobs", "jobs" not in leave_nav)

    # Assistant catalog module truth
    class Legacy:
        def configured_company_modules(self, company):
            return set(self.enabled)

        def company_has_module(self, company, module):
            return module in self.enabled

    legacy = Legacy()
    legacy.enabled = {"leave"}
    tools = [
        {"function": {"name": "list_leave_requests"}},
        {"function": {"name": "summarize_employee_360"}},
        {"function": {"name": "list_job_openings"}},
        {"function": {"name": "get_prehire_work_queue"}},
    ]
    catalog = caps.build_assistant_capability_catalog(
        legacy=legacy,
        company_code="WATHEFNI",
        permissions=["leave.read", "employees.read", "jobs.read", "prehire.read", "settings.read"],
        visible_tools=tools,
    )
    caps_map = catalog["capabilities"]
    check("catalog leave on", caps_map["posthire_leave"]["offerable"] is True)
    check(
        "catalog prehire jobs off without module",
        caps_map["jobs"]["status"] == caps.STATUS_MODULE_OFF,
        caps_map["jobs"],
    )
    check(
        "catalog overview off without pre_hiring",
        caps_map["overview"]["status"] == caps.STATUS_MODULE_OFF,
        caps_map["overview"],
    )
    check(
        "catalog e360 follows people surface",
        caps_map["posthire_employees_360"]["offerable"] is True
        or caps_map["posthire_employees_360"]["status"] == caps.STATUS_AVAILABLE,
        caps_map["posthire_employees_360"],
    )

    legacy.enabled = {"pre_hiring", "leave"}
    catalog2 = caps.build_assistant_capability_catalog(
        legacy=legacy,
        company_code="WATHEFNI",
        permissions=["leave.read", "employees.read", "jobs.read", "prehire.read"],
        visible_tools=tools,
    )
    check("catalog jobs on with pre_hiring", catalog2["capabilities"]["jobs"]["offerable"] is True)

    # Inbox source honesty helper (mirrors Wave 0 rule)
    def honesty(*, can_a, err_a, can_c, err_c, can_e, emp_live):
        unavailable = []
        present = []
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

    leave_only = honesty(can_a=False, err_a=None, can_c=False, err_c=None, can_e=True, emp_live=True)
    check("leave inbox omits analytics", "analytics" in leave_only["omitted"])
    check("leave inbox omits compliance", "compliance" in leave_only["omitted"])
    check("leave inbox not partial when employees live", leave_only["partial"] is False)
    broken = honesty(can_a=True, err_a="boom", can_c=False, err_c=None, can_e=True, emp_live=True)
    check("entitled analytics error is partial", broken["partial"] is True and "analytics" in broken["unavailable"])

    # EN/AR empty state still builds
    empty_en = caps.empty_state_from_catalog(catalog, locale="en")
    empty_ar = caps.empty_state_from_catalog(catalog, locale="ar")
    check("empty en", bool(empty_en.get("headline") or empty_en.get("chips")))
    check("empty ar", bool(empty_ar.get("headline") or empty_ar.get("chips")))

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
