"""Candidates stage-bucket contract — shared status sets for filter expansion proofs.

Mirrors apps/wathefni-dashboard/src/lib/candidatesStageContract.ts.

Axis separation:
* candidates.view.* — job/governance (Talent Pool = no job assigned).
* candidates.stage.* — application lifecycle only.

Talent Pool / needs_role / import_review are not Stage New.
Legacy offered / offer_sent belong to Shortlisted until Offer is a real stage.
"""

from __future__ import annotations

from typing import Any

STAGE_FILTER_NEW = "awaiting_cv"
STAGE_FILTER_READY = "ready_for_review"
STAGE_FILTER_SHORTLISTED = "shortlisted"
STAGE_FILTER_INTERVIEW = "interview"
STAGE_FILTER_HIRED = "hired"
STAGE_FILTER_REJECTED = "rejected"
STAGE_FILTER_WITHDRAWN = "withdrawn"

STAGE_BUCKET_NEW = "new"
STAGE_BUCKET_READY = "ready_for_review"
STAGE_BUCKET_SHORTLISTED = "shortlisted"
STAGE_BUCKET_INTERVIEW = "interview"
STAGE_BUCKET_HIRED = "hired"
STAGE_BUCKET_REJECTED = "rejected"
STAGE_BUCKET_WITHDRAWN = "withdrawn"
STAGE_BUCKET_ARCHIVED = "archived"
STAGE_BUCKET_NONE = "none"
STAGE_BUCKET_UNKNOWN = "unknown"

CANDIDATE_STAGE_FILTER_STATUSES: dict[str, tuple[str, ...]] = {
    STAGE_FILTER_NEW: (
        "awaiting_cv",
        "cv_processing",
        "cv_received",
        "screening",
        "cv_request",
        "cv_upload",
    ),
    STAGE_FILTER_READY: ("ready_for_review", "screening_complete", "review_pending"),
    STAGE_FILTER_SHORTLISTED: ("shortlisted", "offered", "offer_sent"),
    STAGE_FILTER_INTERVIEW: ("interview", "scheduled"),
    STAGE_FILTER_HIRED: ("hired",),
    STAGE_FILTER_REJECTED: ("rejected",),
    STAGE_FILTER_WITHDRAWN: ("withdrawn",),
}

HELD_ACTIVE_STATUSES = frozenset({"needs_role", "import_review"})


def expand_stage_filter_statuses(filter_value: str) -> list[str]:
    key = str(filter_value or "").strip().lower()
    if not key:
        return []
    direct = CANDIDATE_STAGE_FILTER_STATUSES.get(key)
    if direct:
        return list(direct)
    for statuses in CANDIDATE_STAGE_FILTER_STATUSES.values():
        if key in statuses:
            return list(statuses)
    return [key]


def lifecycle_bucket_for_status(status: Any) -> str | None:
    raw = str(status or "").strip().lower()
    if not raw:
        return None
    if raw in CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_NEW]:
        return STAGE_BUCKET_NEW
    if raw in CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_READY]:
        return STAGE_BUCKET_READY
    if raw in CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_SHORTLISTED]:
        return STAGE_BUCKET_SHORTLISTED
    if raw in CANDIDATE_STAGE_FILTER_STATUSES[STAGE_FILTER_INTERVIEW]:
        return STAGE_BUCKET_INTERVIEW
    if raw == STAGE_FILTER_HIRED:
        return STAGE_BUCKET_HIRED
    if raw == STAGE_FILTER_REJECTED:
        return STAGE_BUCKET_REJECTED
    if raw == STAGE_FILTER_WITHDRAWN:
        return STAGE_BUCKET_WITHDRAWN
    if raw == "archived":
        return STAGE_BUCKET_ARCHIVED
    return None


def is_talent_pool_stage_exempt(row: dict[str, Any] | None) -> bool:
    row = row or {}
    status = str(row.get("status") or "").strip().lower()
    return str(row.get("record_state") or "").strip().lower() == "talent_pool" or status in HELD_ACTIVE_STATUSES


def display_stage_bucket(row: dict[str, Any] | None) -> str:
    """Mirror of frontend candidateListStageBucket for live proofs."""
    row = row or {}
    status = str(row.get("status") or "").strip().lower()
    record_state = str(row.get("record_state") or "").strip().lower()
    if record_state == "archived" or status == "import_archived":
        return STAGE_BUCKET_ARCHIVED
    if is_talent_pool_stage_exempt(row):
        return STAGE_BUCKET_NONE
    for key in (status, str(row.get("canonical_stage") or "").strip().lower()):
        bucket = lifecycle_bucket_for_status(key)
        if bucket:
            return bucket
    return STAGE_BUCKET_UNKNOWN
