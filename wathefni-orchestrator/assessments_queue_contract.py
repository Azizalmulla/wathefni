"""Assessments queue contract — three authorities (approved).

* assessments.cohort.*  — applications, latest attempt; Send operational queues
* assessments.attempt.* — every historical attempt; Attempts totals / status_counts
* assessments.review.*  — completed attempts; Needs review + Reports

Cancelled latest attempts are Attempts-history only (not Send / not attention).
Delivery failed is a facet of pending/in_progress, not a separate lifecycle status.
"""

from __future__ import annotations

from typing import Any

# Re-export cohort keys / predicates from the cohort authority module.
from assessment_cohorts import (  # noqa: F401
    ASSESSMENT_ELIGIBLE_STATUSES,
    COHORT_ATTENTION,
    COHORT_COMPLETED,
    COHORT_DELIVERY_FAILED,
    COHORT_EXPIRED,
    COHORT_IN_PROGRESS,
    COHORT_READY_TO_SEND,
    COHORT_RESEND_NEEDED,
    COHORT_SENT_PENDING,
    DELIVERY_FAILED_STATUSES,
    classify_attempt_state,
    cohort_predicate,
    compute_assessment_cohorts,
    normalize_cohort_key,
)

ATTEMPT_STATUSES = ("pending", "in_progress", "completed", "cancelled", "expired")
TERMINAL_ATTEMPT_STATUSES = frozenset({"completed", "cancelled", "expired"})
CANCELLED_STATUS = "cancelled"

# Operational cohort metrics always use application_count (never attempt status_counts).
OPERATIONAL_COHORT_KEYS = (
    COHORT_READY_TO_SEND,
    COHORT_RESEND_NEEDED,
    COHORT_EXPIRED,
    COHORT_DELIVERY_FAILED,
    COHORT_SENT_PENDING,
    COHORT_IN_PROGRESS,
    COHORT_COMPLETED,
)


def needs_review_predicate(alias: str = "aa") -> str:
    """Completed attempt awaiting HR review (assessments.review.needs_review)."""
    return (
        f"{alias}.status = 'completed' "
        f"AND COALESCE(NULLIF(TRIM({alias}.review_status), ''), 'unreviewed') <> 'reviewed'"
    )


def report_ready_predicate(alias: str = "aa") -> str:
    """Completed attempt with a score/report available for the Reports queue."""
    return f"{alias}.status = 'completed'"


def is_cancelled_status(status: Any) -> bool:
    return str(status or "").strip().lower() == CANCELLED_STATUS


def cohort_for_attempt_presentation(
    *,
    attempt_status: Any,
    delivery_status: Any = None,
    application_status: Any = None,
) -> str | None:
    """Cohort key for presentation; cancelled never maps to attention/Send."""
    if is_cancelled_status(attempt_status):
        return None
    return classify_attempt_state(
        assessment_status=attempt_status,
        delivery_status=delivery_status,
        application_status=application_status,
    )


def application_count_only(block: dict[str, Any] | None) -> int:
    block = block or {}
    return int(block.get("application_count") or block.get("applications") or 0)
