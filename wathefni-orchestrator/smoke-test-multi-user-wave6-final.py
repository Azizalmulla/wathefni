#!/usr/bin/env python3
"""Wave 6: team privacy, people pickers, notify routing, final qualification."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import candidate_collaboration as c2  # noqa: E402
import concurrency_safety as cs  # noqa: E402
import prehire_ownership as own  # noqa: E402
import prehire_personal_work as ppw  # noqa: E402
import prehire_team_directory as td  # noqa: E402
import prehire_visibility as pv  # noqa: E402


def check(label: str, cond: bool) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    # --- Privacy -------------------------------------------------------------
    collab = td.project_team_member(
        {
            "user_id": "u-peer",
            "name": "Peer",
            "email": "peer@example.com",
            "phone": "96550000000",
            "role": "recruiter",
            "status": "active",
            "permissions": ["users.manage", "candidates.read"],
        },
        view=td.VIEW_COLLABORATION,
        actor_user_id="u-viewer",
        include_permissions=True,
    )
    check("collaboration hides peer email", "email" not in collab)
    check("collaboration hides peer phone", "phone" not in collab)
    check("collaboration hides permissions", "permissions" not in collab)
    check("collaboration keeps name+role", collab.get("name") == "Peer" and collab.get("role") == "recruiter")

    admin = td.project_team_member(
        {
            "user_id": "u-peer",
            "name": "Peer",
            "email": "peer@example.com",
            "phone": "96550000000",
            "role": "recruiter",
            "status": "active",
            "_effective_permissions": ["candidates.read"],
        },
        view=td.VIEW_ADMIN,
        actor_user_id="u-owner",
        include_permissions=True,
    )
    check("admin sees email", admin.get("email") == "peer@example.com")
    check("admin with users.manage sees permissions", admin.get("permissions") == ["candidates.read"])

    check(
        "owner directory admin",
        td.resolve_directory_view(can_manage_users=True, can_manage_settings=True, actor_role="owner") == td.VIEW_ADMIN,
    )
    check(
        "hr_admin settings => admin view",
        td.resolve_directory_view(can_manage_users=False, can_manage_settings=True, actor_role="hr_admin") == td.VIEW_ADMIN,
    )
    check(
        "recruiter collaboration view",
        td.resolve_directory_view(can_manage_users=False, can_manage_settings=False, actor_role="recruiter")
        == td.VIEW_COLLABORATION,
    )

    # --- People pickers ------------------------------------------------------
    people = td.filter_users_for_picker(
        [
            {"user_id": "1", "name": "Alex Recruiter", "role": "recruiter", "status": "active", "email": "a@x.com"},
            {"user_id": "2", "name": "Sam Viewer", "role": "viewer", "status": "active", "email": "s@x.com"},
            {"user_id": "3", "name": "Pat Payroll", "role": "payroll_operator", "status": "active"},
            {"user_id": "4", "name": "Disabled", "role": "recruiter", "status": "disabled"},
            {"user_id": "5", "name": "Ivy Interviewer", "role": "interviewer", "status": "active"},
            {"user_id": "6", "name": "HR Admin", "role": "hr_admin", "status": "active"},
        ],
        purpose="recruiter",
        query="alex",
    )
    check("picker returns eligible recruiter", len(people) == 1 and people[0]["user_id"] == "1")
    check("picker label has name+role", "Alex Recruiter" in people[0]["label"] and "email" not in people[0])

    interviewers = td.filter_users_for_picker(
        [
            {"user_id": "5", "name": "Ivy Interviewer", "role": "interviewer", "status": "active"},
            {"user_id": "2", "name": "Sam Viewer", "role": "viewer", "status": "active"},
        ],
        purpose="interviewer",
    )
    check("interviewer purpose excludes viewer", [p["user_id"] for p in interviewers] == ["5"])
    check("hr_admin eligible as recruiter", td.role_eligible_for_purpose("hr_admin", "recruiter"))
    check("hr_admin in RECRUITING_ROLES", "hr_admin" in c2.RECRUITING_ROLES)

    # --- Notify routing ------------------------------------------------------
    personal = td.notification_audit_fields(audience="personal", source="task_assignment", kind="task_created")
    check("personal audit audience", personal["audience"] == "personal" and personal["source"] == "task_assignment")
    company = td.notification_audit_fields(audience="company")
    check("company audit source default", company["source"] == "company_ops")

    sig = inspect.signature(app.notify_hr_admins)
    check("notify accepts source", "source" in sig.parameters and "kind" in sig.parameters)
    check("personal helper present", callable(app.notify_prehire_personal_assignees))

    empty = app.notify_prehire_personal_assignees(
        company_code="WATHEFNI",
        assignee_user_ids=[],
        message="x",
        source="task_assignment",
        kind="task_created",
    )
    check("personal notify skips empty assignees", empty.get("skipped") is True and empty.get("audience") == "personal")
    check("personal never falls back to company", empty.get("notification_scope") == "personal")

    # --- Role qualification matrix ------------------------------------------
    roles = [
        "owner",
        "hr_admin",
        "hr_manager",
        "recruiter",
        "hiring_manager",
        "interviewer",
        "payroll_operator",
        "viewer",
    ]
    for role in roles:
        check(f"role known:{role}", role in app.ROLE_PERMISSIONS)

    check("owner has users.manage", "users.manage" in app.ROLE_PERMISSIONS["owner"])
    check("hr_admin no users.manage", "users.manage" not in app.ROLE_PERMISSIONS["hr_admin"])
    check("hr_admin has settings.manage", "settings.manage" in app.ROLE_PERMISSIONS["hr_admin"])
    check("payroll no prehire.read", "prehire.read" not in app.ROLE_PERMISSIONS["payroll_operator"])
    check("viewer has jobs.read", "jobs.read" in app.ROLE_PERMISSIONS["viewer"])
    check("interviewer assignment scoped", app.interview_role_is_assignment_scoped("interviewer"))
    check("recruiter company work forbidden", True)
    try:
        ppw.resolve_work_scope(requested="company", role="recruiter")
        check("recruiter company work forbidden", False)
    except ppw.PersonalWorkScopeError as exc:
        check("recruiter company work forbidden", exc.code == "company_work_forbidden")
    check("owner may company work", ppw.resolve_work_scope(requested="company", role="owner") == "company")
    check("shared visibility default", pv.normalize_prehire_visibility_policy(None) == "shared_company")
    check("wave3 ownership present", hasattr(own, "resolve_job_recruiter_on_create"))
    check("wave5 conflict message", "another user" in cs.CONFLICT_MESSAGE_EN.lower())
    check("people route registered", any(getattr(r, "path", "") == "/dashboard/team/people" for r in app.app.routes))
    check("calendar routes present for C1", "/dashboard/calendar/events" in {getattr(r, "path", "") for r in app.app.routes})
    check("interview routes preserved", "/dashboard/prehire/interviews" in {getattr(r, "path", "") for r in app.app.routes})
    check("owner has calendar.company", "calendar.company" in app.ROLE_PERMISSIONS["owner"])
    check("payroll has no calendar.read", "calendar.read" not in app.ROLE_PERMISSIONS["payroll_operator"])

    print("ALL WAVE6 FINAL QUALIFICATION CHECKS PASSED")


if __name__ == "__main__":
    main()
