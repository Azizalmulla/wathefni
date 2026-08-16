"""Wave 4 org authority — pure unit tests (no DB)."""

from __future__ import annotations

import os

import employee_org_wave4 as w4

PASS = 0
FAIL = 0


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label} :: {detail}")


def main() -> int:
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES"] = "WATHEFNI"
    os.environ["WATHEFNI_EMPLOYEE_ORG_V4"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES"] = "WATHEFNI"

    check("enabled WATHEFNI", w4.org_v4_enabled("WATHEFNI") is True)
    check("disabled OTHERCO", w4.org_v4_enabled("OTHERCO") is False)

    os.environ["WATHEFNI_EMPLOYEE_ORG_V4"] = "off"
    check("flag off", w4.org_v4_enabled("WATHEFNI") is False)
    os.environ["WATHEFNI_EMPLOYEE_ORG_V4"] = "on"

    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "off"
    check("requires wave2", w4.org_v4_enabled("WATHEFNI") is False)
    os.environ["WATHEFNI_EMPLOYEE_AUTHORITY_V2"] = "on"

    for t in ("legal_employer", "branch", "department", "team", "location", "position", "cost_center"):
        check(f"unit type {t}", t in w4.UNIT_TYPES)

    for t in ("transfer", "manager_change", "job_change", "department_change", "location_change", "bulk_assign", "migration", "initial"):
        check(f"change type {t}", t in w4.CHANGE_TYPES)

    for tier in ("small", "medium", "enterprise"):
        p = w4._policy_defaults_for_tier(tier)
        check(f"tier {tier}", p["tier"] == tier)
    check("small subset", "department" in w4._policy_defaults_for_tier("small")["simple_org_types"])
    check("enterprise dual approval", w4._policy_defaults_for_tier("enterprise")["require_dual_approval"] is True)
    check("small no dual approval", w4._policy_defaults_for_tier("small")["require_dual_approval"] is False)
    check("ambiguous never auto-merge", w4.DEFAULT_POLICY["migration_ambiguous_people"] == "needs_review")

    mapping = w4.suggest_column_mapping(["Full Name", "Mobile", "Department", "Title", "Team"])
    check("map name", mapping.get("Full Name") == "name", mapping)
    check("map phone", mapping.get("Mobile") == "phone", mapping)
    check("map department", mapping.get("Department") == "department", mapping)
    check("map title", mapping.get("Title") == "position_title", mapping)
    check("map team", mapping.get("Team") == "team", mapping)

    check("slug", w4._slug_key("HR Ops!") == "hr-ops")
    check("schema version", w4.SCHEMA_VERSION == "employees360-wave4-org-authority-v1")

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
