"""Shared CandidateRecordStatePolicy for Candidate Knowledge Phase 1.

This is a read/actionability projection only. Existing communication, lifecycle,
ranking, intake, and retention authorities remain the mutation gates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


POLICY_VERSION = "candidate-record-state-policy-v1"

INTAKE_HOLD_STATUSES = frozenset({"needs_role", "import_review", "import_archived"})
RETENTION_HELD_STATUSES = frozenset({"needs_role", "import_review", "import_archived", "review_pending"})
FINALIZED_STATUSES = frozenset({"hired", "rejected", "withdrawn"})
LIVE_PIPELINE_STATUSES = frozenset(
    {
        "review_pending",
        "screening",
        "screening_complete",
        "ready_for_review",
        "shortlisted",
        "interview",
        "offer",
        "awaiting_cv",
    }
)

DELETION_ACTIVE_STATES = frozenset({"requested", "in_progress", "pending", "completed"})
RESTRICTION_ACTIVE_STATES = frozenset({"restricted", "active", "true", "1"})
ARCHIVE_ACTIVE_STATES = frozenset({"archived", "active", "true", "1"})
LEGAL_HOLD_ACTIVE_STATES = frozenset({"active", "true", "1", "legal_hold", "hold"})

ReadProjection = Literal["full", "redacted", "metadata_only", "denied"]


@dataclass(frozen=True)
class CandidateRecordStateDecision:
    intake_hold_state: str | None
    communication_allowed: bool
    lifecycle_mutation_allowed: bool
    job_ranking_eligible: bool
    talent_pool_search_eligible: bool
    retention_blocked: bool
    read_projection: ReadProjection
    held_state: str | None
    reason_codes: tuple[str, ...]
    policy_version: str = POLICY_VERSION
    application_status: str | None = None
    governance_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason_codes"] = list(self.reason_codes)
        payload["governance_flags"] = list(self.governance_flags)
        return payload

    def to_actionability(self) -> dict[str, Any]:
        readable = self.read_projection in {"full", "redacted", "metadata_only"}
        contact_allowed = bool(
            readable
            and self.communication_allowed
            and self.read_projection == "full"
            and "restricted" not in self.governance_flags
            and "deletion_completed" not in self.governance_flags
        )
        return {
            "readable": readable,
            "contact_allowed": contact_allowed,
            "lifecycle_mutation_allowed": self.lifecycle_mutation_allowed,
            "job_ranking_allowed": self.job_ranking_eligible,
            "held_state": self.held_state,
            "reason_codes": list(self.reason_codes),
            "read_projection": self.read_projection,
            "policy_version": self.policy_version,
        }


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_lower(value: Any) -> str:
    return _norm(value).lower()


def _governance_flags(governance: dict[str, Any] | None, status: str) -> list[str]:
    gov = governance if isinstance(governance, dict) else {}
    flags: list[str] = []
    if status == "import_archived" or _norm_lower(gov.get("archive_state")) in ARCHIVE_ACTIVE_STATES:
        flags.append("archived")
    if _norm_lower(gov.get("restriction_state")) in RESTRICTION_ACTIVE_STATES:
        flags.append("restricted")
    if _norm_lower(gov.get("legal_hold_state") or gov.get("legal_hold")) in LEGAL_HOLD_ACTIVE_STATES:
        flags.append("legal_hold")
    deletion = _norm_lower(gov.get("deletion_request_state") or gov.get("deletion_state"))
    if deletion in DELETION_ACTIVE_STATES:
        flags.append(f"deletion_{deletion}" if deletion != "completed" else "deletion_completed")
        if deletion != "completed":
            flags.append("deletion_pending")
    return flags


def evaluate_candidate_record_state(
    application: dict[str, Any] | None,
    *,
    governance: dict[str, Any] | None = None,
) -> CandidateRecordStateDecision:
    """Return named domain decisions without collapsing review_pending."""

    row = application if isinstance(application, dict) else {}
    status = _norm_lower(row.get("status"))
    reasons: list[str] = []
    flags = _governance_flags(governance, status)

    intake_hold_state = status if status in INTAKE_HOLD_STATUSES else None
    if intake_hold_state:
        reasons.append(f"intake_hold:{intake_hold_state}")

    # Communication mirrors live communication authority held set (not review_pending).
    communication_allowed = status not in INTAKE_HOLD_STATUSES and "restricted" not in flags and "deletion_pending" not in flags and "deletion_completed" not in flags and "archived" not in flags
    if not communication_allowed:
        reasons.append("communication_blocked")

    # Production search / ranking eligibility exclude intake holds, not review_pending.
    talent_pool_search_eligible = status not in INTAKE_HOLD_STATUSES and status not in FINALIZED_STATUSES and "restricted" not in flags and "deletion_completed" not in flags and "archived" not in flags
    job_ranking_eligible = talent_pool_search_eligible
    if not talent_pool_search_eligible:
        reasons.append("talent_pool_search_ineligible")
    if not job_ranking_eligible:
        reasons.append("job_ranking_ineligible")

    # Retention treats review_pending as held intentionally.
    retention_blocked = status in RETENTION_HELD_STATUSES or "legal_hold" in flags or "deletion_pending" in flags or "deletion_completed" in flags
    if retention_blocked:
        reasons.append("retention_blocked")

    lifecycle_mutation_allowed = (
        status not in INTAKE_HOLD_STATUSES
        and status not in FINALIZED_STATUSES
        and "restricted" not in flags
        and "archived" not in flags
        and "deletion_pending" not in flags
        and "deletion_completed" not in flags
    )
    if not lifecycle_mutation_allowed:
        reasons.append("lifecycle_mutation_blocked")

    if "deletion_completed" in flags:
        read_projection: ReadProjection = "denied"
        reasons.append("deletion_completed")
    elif "restricted" in flags:
        read_projection = "metadata_only"
        reasons.append("restricted")
    elif "deletion_pending" in flags:
        read_projection = "redacted"
        reasons.append("deletion_pending")
    elif "archived" in flags or status == "import_archived":
        read_projection = "redacted"
        reasons.append("archived")
    elif intake_hold_state:
        read_projection = "full"
        reasons.append("held_readable_not_actionable")
    else:
        read_projection = "full"

    held_state = intake_hold_state
    if held_state is None and status == "review_pending":
        # review_pending is not a communication/search hold, but retention treats it as held.
        held_state = None
        reasons.append("review_pending_retention_held_only")
    if "restricted" in flags:
        held_state = held_state or "restricted"
    if "archived" in flags:
        held_state = held_state or "archived"

    if status in FINALIZED_STATUSES:
        reasons.append(f"finalized:{status}")
    elif status in LIVE_PIPELINE_STATUSES and status != "review_pending":
        reasons.append("live_pipeline")
    elif status == "review_pending":
        reasons.append("review_pending")

    # Deduplicate while preserving order.
    ordered_reasons: list[str] = []
    seen: set[str] = set()
    for item in reasons:
        if item not in seen:
            seen.add(item)
            ordered_reasons.append(item)

    return CandidateRecordStateDecision(
        intake_hold_state=intake_hold_state,
        communication_allowed=communication_allowed,
        lifecycle_mutation_allowed=lifecycle_mutation_allowed,
        job_ranking_eligible=job_ranking_eligible,
        talent_pool_search_eligible=talent_pool_search_eligible,
        retention_blocked=retention_blocked,
        read_projection=read_projection,
        held_state=held_state,
        reason_codes=tuple(ordered_reasons) or ("normal",),
        application_status=status or None,
        governance_flags=tuple(flags),
    )


# Public alias matching architecture naming.
CandidateRecordStatePolicy = evaluate_candidate_record_state
