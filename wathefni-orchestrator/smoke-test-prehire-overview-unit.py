#!/usr/bin/env python3
"""Local/unit smoke for prehire_overview SQL predicates and Wave 1 units."""

from __future__ import annotations

from datetime import datetime, timezone

import prehire_overview as po


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {msg}")


def main() -> None:
    ready = po.ready_for_review_predicate("a")
    assert_true("ready_for_review" in ready, "ready predicate includes canonical status")
    assert_true("screening_complete" in ready, "ready predicate includes legacy status")

    assess = po.assessment_pending_predicate("a")
    assert_true("shortlisted" in assess, "assessment eligible includes shortlisted")
    assert_true("pending" in assess, "assessment pending includes pending")
    assert_true("expired" in assess, "assessment pending includes expired (prod sync)")

    follow = po.follow_up_needed_exists("a")
    assert_true("outbound_delivery_events" in follow, "follow-up uses delivery events")
    assert_true("recovered_at IS NULL" in follow, "follow-up excludes recovered")
    follow_compact = follow.replace(" ", "")
    assert_true(
        "ode.company_code=a.company_code" in follow_compact,
        "follow-up requires strict company_code equality",
    )
    assert_true(
        "COALESCE(ode.company_code" not in follow,
        "follow-up must not COALESCE company_code",
    )
    assert_true(
        "ode.subject_key=a.app_key" in follow_compact,
        "follow-up requires subject_key = app_key",
    )
    assert_true("NOT IN ('sent','recovered')" in follow, "follow-up excludes sent/recovered")

    person = po.person_identity_sql("a", "c")
    assert_true("email:" in person, "person identity prefers email")
    assert_true("phone:" in person, "person identity falls back to phone")
    assert_true("singleton:" in person, "person identity singleton app_key")

    sla = po.resolve_sla_hours({"prehire_overview_sla": {"follow_up_hours": 12}})
    assert_true(sla["follow_up_hours"] == 12, "tenant SLA override")
    assert_true(sla["ready_for_review_hours"] == 48, "default SLA retained")

    assert_true(po.ACTION_FOLLOW_UP == "follow_up_failed_delivery", "follow-up action key")
    assert_true(po.ACTION_READY_FOR_REVIEW == "ready_for_review", "ready action key")
    assert_true(po.UNIT_PEOPLE == "people", "people unit")
    assert_true(po.UNIT_APPLICATIONS == "applications", "applications unit")

    metric = po._metric_block(key="follow_up_needed", people=2, applications=4)
    assert_true(metric["unit"] == "people", "metric unit is people")
    assert_true(metric["display"] == 2, "display is people")
    assert_true(metric["applications"] == 4, "applications published beside people")

    now = datetime.now(timezone.utc)
    grouped = po._group_work_queue_by_person(
        [
            {
                "action_type": po.ACTION_FOLLOW_UP,
                "app_key": "A1",
                "person_key": "phone:96597485758",
                "candidate_name": "Hamad Almulla",
                "position_code": "ACCOUNTING_EXCEL",
                "position_title": "Accounting Excel",
                "status": "screening_complete",
                "reason": "follow",
                "priority": 99,
                "age_hours": 10,
                "destination": {},
                "authority_source": "t",
            },
            {
                "action_type": po.ACTION_READY_FOR_REVIEW,
                "app_key": "A1",
                "person_key": "phone:96597485758",
                "candidate_name": "Hamad Almulla",
                "position_code": "ACCOUNTING_EXCEL",
                "position_title": "Accounting Excel",
                "status": "screening_complete",
                "reason": "ready",
                "priority": 80,
                "age_hours": 8,
                "destination": {},
                "authority_source": "t",
            },
            {
                "action_type": po.ACTION_FOLLOW_UP,
                "app_key": "A2",
                "person_key": "phone:96597485758",
                "candidate_name": "Hamad Almulla",
                "position_code": "HR",
                "position_title": "HR",
                "status": "shortlisted",
                "reason": "follow2",
                "priority": 90,
                "age_hours": 9,
                "destination": {},
                "authority_source": "t",
            },
        ],
        now=now,
    )
    assert_true(len(grouped) == 1, "one person row for Hamad")
    assert_true(grouped[0]["application_count"] == 2, "two applications nested")
    assert_true(grouped[0]["action_count"] == 3, "three actions nested")

    follow_dest = po._destination_candidates(cohort_key=po.COHORT_FOLLOW_UP, follow_up="needed")
    assert_true(follow_dest["cohort_key"] == po.COHORT_FOLLOW_UP, "follow-up cohort_key")
    assert_true(follow_dest["filters"]["overview_cohort"] == po.COHORT_FOLLOW_UP, "follow-up overview_cohort")
    assert_true(follow_dest["filters"]["follow_up"] == "needed", "follow-up filter")

    interview_dest = po._destination_interview_scheduling_debt()
    assert_true(interview_dest["page"] == "candidates", "interview debt opens candidates")
    assert_true(interview_dest["filters"]["overview_cohort"] == po.COHORT_INTERVIEW_SCHEDULING, "interview cohort")
    assert_true(interview_dest["filters"]["interview_status"] == "none", "interview none filter")

    role_dest = po._destination_role_active("ACCOUNTING_EXCEL")
    assert_true(role_dest["page"] == "candidates", "role opens candidates")
    assert_true(role_dest["cohort_key"] == "role_active:ACCOUNTING_EXCEL", "role cohort_key")
    assert_true(role_dest["filters"]["position"] == "ACCOUNTING_EXCEL", "role position")
    ranking = po._destination_ranking("ACCOUNTING_EXCEL")
    assert_true(ranking["page"] == "ranking", "ranking destination separate")

    debt_pred = po.interview_scheduling_debt_predicate("a")
    assert_true("shortlisted" in debt_pred, "interview debt statuses")
    assert_true("IS NULL" in debt_pred, "interview debt requires null interview")

    print("PASS: prehire_overview unit invariants (wave1+wave2)")


if __name__ == "__main__":
    main()
