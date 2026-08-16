#!/usr/bin/env python3
"""Wave 4: personal work queues (My work / Company work) + assignee notifications."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import prehire_personal_work as ppw  # noqa: E402
import prehire_visibility as pv  # noqa: E402
import app  # noqa: E402


def check(label: str, cond: bool) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {label}")
    print(f"PASS: {label}")


def main() -> None:
    check("scopes include mine+company", ppw.WORK_SCOPES == frozenset({"mine", "company"}))
    check("normalize my_work -> mine", ppw.normalize_work_scope("my_work") == "mine")
    check("normalize company_work -> company", ppw.normalize_work_scope("company_work") == "company")
    check("default mine for recruiter", ppw.resolve_work_scope(requested=None, role="recruiter") == "mine")
    check("default mine for owner", ppw.resolve_work_scope(requested=None, role="owner") == "mine")
    check("owner can request company", ppw.resolve_work_scope(requested="company", role="owner") == "company")
    try:
        ppw.resolve_work_scope(requested="company", role="recruiter")
        check("recruiter company forbidden", False)
    except ppw.PersonalWorkScopeError as exc:
        check("recruiter company forbidden", exc.code == "company_work_forbidden")

    # Responsibility matching
    is_mine, owner, source = ppw.responsibility_for_actor(
        {"owner_user_id": "u-recruiter", "recruiter_user_id": "u-recruiter", "hiring_manager_user_id": None},
        actor_user_id="u-recruiter",
    )
    check("recruiter owns via application_owner", is_mine and source == ppw.SOURCE_APPLICATION_OWNER)

    is_mine, _, source = ppw.responsibility_for_actor(
        {"owner_user_id": "other", "recruiter_user_id": None, "hiring_manager_user_id": "u-hm"},
        actor_user_id="u-hm",
    )
    check("HM owns via hiring_manager", is_mine and source == ppw.SOURCE_JOB_HIRING_MANAGER)

    is_mine, _, source = ppw.responsibility_for_actor(
        {"owner_user_id": "other", "recruiter_user_id": None, "hiring_manager_user_id": None},
        actor_user_id="u-interviewer",
        interview_app_keys={"app-1"},
        app_key="app-1",
    )
    check("interviewer owns via interview assignment", is_mine and source == ppw.SOURCE_INTERVIEW_ASSIGNMENT)

    is_mine, _, _ = ppw.responsibility_for_actor(
        {"owner_user_id": "other", "recruiter_user_id": None, "hiring_manager_user_id": None},
        actor_user_id="u-unrelated",
        interview_app_keys=set(),
        app_key="app-1",
    )
    check("unrelated user not responsible", not is_mine)

    enriched = ppw.enrich_work_item(
        {
            "action_type": "ready_for_review",
            "app_key": "app-1",
            "person_key": "p-1",
            "reason": "Ready",
            "priority": 55,
        },
        audience=ppw.AUDIENCE_PERSONAL,
        owner_user_id="u-1",
        owner_label="Alex",
        source=ppw.SOURCE_APPLICATION_OWNER,
        due_state="overdue",
        entity_type="application",
        entity_id="app-1",
    )
    check("enriched has owner", enriched.get("owner") == "Alex")
    check("enriched has due_state", enriched.get("due_state") == "overdue")
    check("enriched has next_action", bool(enriched.get("next_action")))
    check("enriched has source", enriched.get("source") == ppw.SOURCE_APPLICATION_OWNER)
    check("enriched audience personal", enriched.get("audience") == "personal")

    # Dedup: personal + company same entity keep one
    items = ppw._dedupe_items(  # noqa: SLF001
        [
            {"action_type": "ready_for_review", "entity_id": "app-1", "priority": 40, "due_state": "open"},
            {"action_type": "ready_for_review", "entity_id": "app-1", "priority": 70, "due_state": "overdue"},
        ]
    )
    check("dedupe keeps higher priority", len(items) == 1 and items[0]["priority"] == 70)

    counts = ppw._count_breakdown(  # noqa: SLF001
        [
            {"action_type": "ready_for_review"},
            {"action_type": "follow_up_needed"},
            {"action_type": "interview_feedback"},
            {"action_type": "overdue_task"},
        ]
    )
    check("counts match rows total", counts["total"] == 4)
    check("counts ready", counts["ready_for_review"] == 1)
    check("counts follow_up", counts["follow_up"] == 1)
    check("counts interview_feedback", counts["interview_feedback"] == 1)
    check("counts overdue", counts["overdue_tasks"] == 1)

    # notify helper signature
    sig = inspect.signature(app.notify_hr_admins)
    check("notify accepts assignee_user_ids", "assignee_user_ids" in sig.parameters)
    check("notify accepts audience", "audience" in sig.parameters)

    # Routes
    paths = {getattr(r, "path", "") for r in app.app.routes}
    check("work-queue route", "/dashboard/prehire/overview/work-queue" in paths)
    check("next-action route", "/dashboard/prehire/overview/next-action" in paths)
    check("notifications route", "/dashboard/prehire/notifications" in paths)

    # Wave 1–3 preserved
    check("Wave1 interviewer scoped", app.interview_role_is_assignment_scoped("interviewer"))
    check("Wave2 oversight roles", pv.actor_has_prehire_oversight("hr_admin"))
    check("Wave2 default shared", pv.normalize_prehire_visibility_policy(None) == "shared_company")
    check("Wave3 ownership module", hasattr(__import__("prehire_ownership"), "resolve_job_recruiter_on_create"))
    check("calendar routes added in C1", "/dashboard/calendar/events" in paths)
    check("interview routes preserved", "/dashboard/prehire/interviews" in paths)

    # notification item audience
    item = app.dashboard_notification_item(
        kind="assessment_delivery_failed",
        title="Assessment delivery failed",
        count=2,
        severity="high",
        action="Fix",
        page="assessments",
        audience="company",
        metadata={"shared_alert": True},
    )
    check("company alert labeled", item and item.get("audience") == "company")

    print("ALL WAVE4 PERSONAL WORK CHECKS PASSED")


if __name__ == "__main__":
    main()
