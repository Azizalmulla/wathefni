#!/usr/bin/env python3
"""Wave 1: role taxonomy + least-privilege authority (no Calendar).

Pins:
  - hr_admin does not alias to owner
  - Company Admin (owner) ≠ HR Admin
  - HR Admin cannot users.manage
  - Payroll Operator has no candidate/prehire scopes
  - Interviewer is assignment-scoped and action-narrowed
  - existing owner permission set is preserved (no escalation)
  - Team Manager (manager) remains for manager_scopes
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


def check(label: str, cond: bool) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    # --- Alias / key clarity -------------------------------------------------
    check("hr_admin normalizes to itself", app.normalize_hr_role("hr_admin") == "hr_admin")
    check("hr admin spaced normalizes to hr_admin", app.normalize_hr_role("hr admin") == "hr_admin")
    check("company_admin aliases to owner", app.normalize_hr_role("company_admin") == "owner")
    check("owner stays owner", app.normalize_hr_role("owner") == "owner")
    check("interviewer is a real role", app.normalize_hr_role("interviewer") == "interviewer")
    check("payroll_operator is a real role", app.normalize_hr_role("payroll_operator") == "payroll_operator")
    check("hr_admin is in ROLE_PERMISSIONS", "hr_admin" in app.ROLE_PERMISSIONS)
    check("interviewer is in ROLE_PERMISSIONS", "interviewer" in app.ROLE_PERMISSIONS)
    check("payroll_operator is in ROLE_PERMISSIONS", "payroll_operator" in app.ROLE_PERMISSIONS)
    check("manager remains for Team Manager", "manager" in app.ROLE_PERMISSIONS)

    # --- Labels --------------------------------------------------------------
    check("owner labeled Company Admin", app.ROLE_LABELS.get("owner") == "Company Admin")
    check("hr_admin labeled HR Admin", app.ROLE_LABELS.get("hr_admin") == "HR Admin")
    check("interviewer labeled Interviewer", app.ROLE_LABELS.get("interviewer") == "Interviewer")
    check("payroll labeled Payroll Operator", app.ROLE_LABELS.get("payroll_operator") == "Payroll Operator")

    owner = set(app.hr_role_permissions("owner"))
    hr_admin = set(app.hr_role_permissions("hr_admin"))
    hr_manager = set(app.hr_role_permissions("hr_manager"))
    interviewer = set(app.hr_role_permissions("interviewer"))
    payroll = set(app.hr_role_permissions("payroll_operator"))

    # --- Company Admin ≠ HR Admin -------------------------------------------
    check("Company Admin has users.manage", "users.manage" in owner)
    check("HR Admin lacks users.manage", "users.manage" not in hr_admin)
    check("Company Admin has settings.manage", "settings.manage" in owner)
    check("HR Admin has settings.manage", "settings.manage" in hr_admin)
    check("HR Manager lacks settings.manage", "settings.manage" not in hr_manager)
    check("HR Manager lacks users.manage", "users.manage" not in hr_manager)
    check("HR Manager lacks audit.read", "audit.read" not in hr_manager)
    check("HR Admin has audit.read", "audit.read" in hr_admin)
    check("HR Admin lacks calendar.sync", "calendar.sync" not in hr_admin)
    check("owner has calendar.sync", "calendar.sync" in owner)
    check("owner perms are a strict superset of hr_admin", owner > hr_admin)
    check("hr_admin perms are a strict superset of hr_manager", hr_admin > hr_manager)

    # --- Owner preserved (no accidental loss of Company Admin powers) -------
    for perm in (
        "users.manage",
        "settings.manage",
        "audit.read",
        "candidate.decide",
        "jobs.publish",
        "payroll.export",
        "assessment.manage",
    ):
        check(f"owner keeps {perm}", perm in owner)

    # --- Payroll Operator least privilege -----------------------------------
    check("payroll_operator has payroll.read", "payroll.read" in payroll)
    check("payroll_operator has payroll.manage", "payroll.manage" in payroll)
    check("payroll_operator has payroll.approve", "payroll.approve" in payroll)
    check("payroll_operator lacks payroll.export (SOD)", "payroll.export" not in payroll)
    for forbidden in (
        "prehire.read",
        "candidates.read",
        "candidate.manage",
        "interview.manage",
        "assessment.manage",
        "jobs.read",
        "users.manage",
        "settings.manage",
        "audit.read",
    ):
        check(f"payroll_operator lacks {forbidden}", forbidden not in payroll)

    # --- Interviewer least privilege + scoping hooks ------------------------
    check("interviewer has prehire.read", "prehire.read" in interviewer)
    check("interviewer has interview.manage", "interview.manage" in interviewer)
    for forbidden in (
        "candidates.read",
        "candidate.manage",
        "jobs.create",
        "jobs.publish",
        "assessment.manage",
        "offer.send",
        "users.manage",
        "settings.manage",
        "payroll.read",
        "report.export",
    ):
        check(f"interviewer lacks {forbidden}", forbidden not in interviewer)
    check("interviewer is assignment-scoped role", app.interview_role_is_assignment_scoped("interviewer"))
    check("recruiter is not assignment-scoped", not app.interview_role_is_assignment_scoped("recruiter"))
    narrowed = app.narrow_interview_allowed_actions_for_role(
        "interviewer",
        ["write_notes", "cancel_interview", "schedule_interview", "assign_interviewer", "view_feedback", "review_video"],
    )
    check("interviewer actions exclude cancel/schedule/assign", narrowed == ["write_notes", "view_feedback", "review_video"])

    # --- Grant-only scopes never on role defaults ---------------------------
    for role in app.ROLE_PERMISSIONS:
        perms = set(app.ROLE_PERMISSIONS[role])
        check(f"{role} has no assessment.publish default", "assessment.publish" not in perms)
        check(f"{role} has no offer.hire_override default", "offer.hire_override" not in perms)
        check(f"{role} has no employees.manage default", "employees.manage" not in perms)

    # --- No escalation via alias traps --------------------------------------
    check("admin still maps to Company Admin/owner", app.normalize_hr_role("admin") == "owner")
    check("hr_admin does NOT map to owner", app.normalize_hr_role("hr_admin") != "owner")

    print("ALL WAVE1 ROLE CHECKS PASSED")


if __name__ == "__main__":
    main()
