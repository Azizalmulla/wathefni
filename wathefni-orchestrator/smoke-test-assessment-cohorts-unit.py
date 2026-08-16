"""Unit tests for shared assessment cohort contract (Wave 3)."""

from __future__ import annotations

import assessment_cohorts as ac


def test_classify_states_are_mutually_exclusive_actionable():
    assert ac.classify_attempt_state(assessment_status="", application_status="ready_for_review") == ac.COHORT_READY_TO_SEND
    assert ac.classify_attempt_state(assessment_status="pending", application_status="ready_for_review") == ac.COHORT_SENT_PENDING
    assert (
        ac.classify_attempt_state(
            assessment_status="pending",
            delivery_status="failed",
            application_status="ready_for_review",
        )
        == ac.COHORT_DELIVERY_FAILED
    )
    assert ac.classify_attempt_state(assessment_status="in_progress", application_status="ready_for_review") == ac.COHORT_IN_PROGRESS
    assert ac.classify_attempt_state(assessment_status="expired", application_status="ready_for_review") == ac.COHORT_RESEND_NEEDED
    assert ac.classify_attempt_state(assessment_status="completed", application_status="ready_for_review") == ac.COHORT_COMPLETED
    assert ac.classify_attempt_state(assessment_status="pending", application_status="hired") is None


def test_expired_is_not_ready_to_send_or_attention_send_label():
    defs = ac.cohort_definitions()
    assert "Send pending" not in str(defs[ac.COHORT_ATTENTION].get("label") or "")
    assert defs[ac.COHORT_ATTENTION]["note"]
    assert ac.PRIMARY_ACTION_BY_COHORT[ac.COHORT_RESEND_NEEDED] == "resend_assessment"
    assert ac.PRIMARY_ACTION_BY_COHORT[ac.COHORT_READY_TO_SEND] == "send_assessment"


def test_allowed_actions_and_destinations():
    assert ac.allowed_actions_for_cohort(ac.COHORT_READY_TO_SEND, can_manage=True) == ["send_assessment"]
    assert "resend_assessment" in ac.allowed_actions_for_cohort(ac.COHORT_RESEND_NEEDED, can_manage=True)
    failed = ac.allowed_actions_for_cohort(ac.COHORT_DELIVERY_FAILED, can_manage=True)
    assert "resend_assessment" in failed
    assert "review_assessment_delivery" in failed
    dest = ac.destination_assessments(ac.COHORT_RESEND_NEEDED)
    assert dest["page"] == "assessments"
    assert dest["filters"]["tab"] == "resend"
    assert dest["filters"]["assessment_cohort"] == ac.COHORT_RESEND_NEEDED


def test_pick_primary_prefers_delivery_failed_then_resend_then_send():
    cohorts = {
        ac.COHORT_READY_TO_SEND: {"people_count": 3, "application_count": 4, "destination": ac.destination_assessments(ac.COHORT_READY_TO_SEND)},
        ac.COHORT_RESEND_NEEDED: {"people_count": 2, "application_count": 2, "destination": ac.destination_assessments(ac.COHORT_RESEND_NEEDED)},
        ac.COHORT_DELIVERY_FAILED: {"people_count": 1, "application_count": 1, "destination": ac.destination_assessments(ac.COHORT_DELIVERY_FAILED)},
        ac.COHORT_IN_PROGRESS: {"people_count": 5, "application_count": 5},
        ac.COHORT_SENT_PENDING: {"people_count": 0, "application_count": 0},
    }
    primary = ac.pick_primary_assessment_action(cohorts)
    assert primary["action"] == ac.ACTION_DELIVERY_FAILED
    cohorts[ac.COHORT_DELIVERY_FAILED]["people_count"] = 0
    primary = ac.pick_primary_assessment_action(cohorts)
    assert primary["action"] == ac.ACTION_RESEND
    cohorts[ac.COHORT_RESEND_NEEDED]["people_count"] = 0
    primary = ac.pick_primary_assessment_action(cohorts)
    assert primary["action"] == ac.ACTION_READY_TO_SEND
    assert primary["label"] == "Send assessments"


def test_normalize_aliases():
    assert ac.normalize_cohort_key("expired") == ac.COHORT_EXPIRED
    assert ac.normalize_cohort_key("resend") == ac.COHORT_RESEND_NEEDED
    assert ac.normalize_cohort_key("assessment_pending") == ac.COHORT_ATTENTION
    assert ac.normalize_cohort_key("awaiting") == ac.COHORT_ATTENTION


if __name__ == "__main__":
    test_classify_states_are_mutually_exclusive_actionable()
    test_expired_is_not_ready_to_send_or_attention_send_label()
    test_allowed_actions_and_destinations()
    test_pick_primary_prefers_delivery_failed_then_resend_then_send()
    test_normalize_aliases()
    print("PASS assessment_cohorts unit")
