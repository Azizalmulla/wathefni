#!/usr/bin/env python3
"""Wave 2: pre-hiring visibility policy (shared_company / assigned_only / hybrid)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import prehire_visibility as pv  # noqa: E402
import app  # noqa: E402


def check(label: str, cond: bool) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    check("default policy is shared_company", pv.normalize_prehire_visibility_policy(None) == "shared_company")
    check("unknown falls back to shared_company", pv.normalize_prehire_visibility_policy("nope") == "shared_company")
    check("empty settings default shared", pv.prehire_visibility_policy_from_settings({}) == "shared_company")
    check("setting key preserved", pv.SETTING_KEY == "prehire_visibility_policy")
    check("operator managed includes policy", "prehire_visibility_policy" in app.OPERATOR_MANAGED_SETTING_KEYS)

    for role in ("owner", "hr_admin", "hr_manager"):
        check(f"{role} has oversight", pv.actor_has_prehire_oversight(role))
    for role in ("recruiter", "hiring_manager", "interviewer", "viewer", "payroll_operator"):
        check(f"{role} not oversight", not pv.actor_has_prehire_oversight(role))

    # shared_company: never apply assignment scope for recruiter detail
    plan = pv.resolve_visibility_plan(policy="shared_company", role="recruiter", surface="detail")
    check("shared recruiter detail unscoped", plan["apply_assignment_scope"] is False)

    # assigned_only: recruiter/HM scoped on detail + summary
    for surface in ("detail", "summary"):
        plan = pv.resolve_visibility_plan(policy="assigned_only", role="recruiter", surface=surface)
        check(f"assigned_only recruiter {surface} scoped", plan["apply_assignment_scope"] is True)
        plan = pv.resolve_visibility_plan(policy="assigned_only", role="hiring_manager", surface=surface)
        check(f"assigned_only HM {surface} scoped", plan["apply_assignment_scope"] is True)
        plan = pv.resolve_visibility_plan(policy="assigned_only", role="owner", surface=surface)
        check(f"assigned_only owner {surface} unscoped", plan["apply_assignment_scope"] is False)

    # hybrid: summary company-wide for recruiter; detail scoped
    plan = pv.resolve_visibility_plan(policy="hybrid", role="recruiter", surface="summary")
    check("hybrid recruiter summary unscoped", plan["apply_assignment_scope"] is False and plan["summary_company_wide"] is True)
    plan = pv.resolve_visibility_plan(policy="hybrid", role="recruiter", surface="detail")
    check("hybrid recruiter detail scoped", plan["apply_assignment_scope"] is True)
    plan = pv.resolve_visibility_plan(policy="hybrid", role="hr_manager", surface="detail")
    check("hybrid HR Manager detail unscoped", plan["apply_assignment_scope"] is False)

    # SQL predicates bind actor placeholders
    sql, ph = pv.jobs_assignment_sql("recruiter", alias="")
    check("recruiter jobs sql mentions recruiter_user_id", "recruiter_user_id" in sql and "created_by_user_id" in sql)
    bound = pv.bind_actor_params(ph, "user-1")
    check("recruiter jobs binds actor twice", bound == ["user-1", "user-1"])
    sql, ph = pv.jobs_assignment_sql("hiring_manager", alias="p")
    check("HM jobs sql uses hiring_manager_user_id", "hiring_manager_user_id" in sql)
    sql, ph = pv.applications_assignment_sql("recruiter")
    check("recruiter apps sql includes owner + positions", "owner_user_id" in sql and "positions" in sql)
    sql, ph = pv.applications_assignment_sql("hiring_manager")
    check("HM apps sql uses hiring_manager on positions", "hiring_manager_user_id" in sql)

    # Wave 1 interviewer unchanged: assignment-scoped role still present
    check("interviewer still assignment scoped role", app.interview_role_is_assignment_scoped("interviewer"))
    check("Wave1 roles still present", "hr_admin" in app.ROLE_PERMISSIONS and "payroll_operator" in app.ROLE_PERMISSIONS)

    # Routes registered
    paths = {getattr(r, "path", "") for r in app.app.routes}
    check("GET visibility-policy route", "/dashboard/prehire/visibility-policy" in paths)
    check("bootstrap still present", "/dashboard/bootstrap" in paths)

    print("ALL WAVE2 VISIBILITY CHECKS PASSED")


if __name__ == "__main__":
    main()
