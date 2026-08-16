#!/usr/bin/env python3
"""Smoke: Calendar Wave 2 post-hire read-only projections (flag-gated)."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ORCH = os.path.join(ROOT, "wathefni-orchestrator")
if ORCH not in sys.path:
    sys.path.insert(0, ORCH)

import calendar_posthire_projections as cpp  # noqa: E402


def check(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")
    print(f"PASS  {msg}")


def main() -> None:
    for source, meta in cpp.SOURCE_FLAGS.items():
        os.environ.pop(meta["flag"], None)
        check(not cpp.source_enabled_for_company(source, "WATHEFNI"), f"{source} off by default")

    os.environ[cpp.SOURCE_FLAGS["employee_start"]["flag"]] = "on"
    os.environ[cpp.SOURCE_FLAGS["employee_start"]["companies"]] = "WATHEFNI"
    check(cpp.source_enabled_for_company("employee_start", "WATHEFNI"), "employee_start on for WATHEFNI")
    check(not cpp.source_enabled_for_company("employee_start", "ACME"), "employee_start denied for ACME")
    check(cpp.is_projection_event_id("calproj-employee-start-x"), "calproj id detect")
    check(not cpp.is_projection_event_id("calprev-x"), "preview id not projection")

    # Permissions gate
    check(
        cpp.actor_has_permission(["employees.read", "calendar.read"], "employees.read"),
        "permission allow",
    )
    check(
        not cpp.actor_has_permission(["calendar.read"], "employees.read"),
        "permission deny",
    )

    # Status filter constants
    check("approved" in cpp.LEAVE_STATUS_USE, "leave approved only")
    check("cancelled" in cpp.ONBOARDING_ASSIGNMENT_EXCLUDE, "onboarding terminal excluded")
    check("rejected" in cpp.HOLIDAY_REVIEW_EXCLUDE, "holiday rejected excluded")

    print("CALENDAR_POSTHIRE_PROJECTIONS_SMOKE_OK")


if __name__ == "__main__":
    main()
