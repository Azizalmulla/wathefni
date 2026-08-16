"""Phase 0 typed contracts for candidate-knowledge-v1.

These DTOs define the future Candidate Knowledge authority surface. They do not
implement retrieval, indexing, Voyage calls, or database schema changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


CANDIDATE_KNOWLEDGE_SCHEMA = "candidate-knowledge-v1"
CANDIDATE_REF_PREFIX = "app:"
PERSON_REF_PREFIX = "person:"
SUBJECT_REF_PREFIX = "subject:"

AuthorityLevel = Literal[
    "canonical",
    "hr_confirmed",
    "ai_suggested",
    "candidate_reply",
    "cv_prefill",
    "profile_projection_legacy",
    "operational_mirror",
]

CoverageState = Literal[
    "available",
    "partial",
    "not_recorded",
    "not_extracted",
    "not_indexed",
    "not_authorized",
    "module_disabled",
    "restricted",
    "stale",
    "invalidated",
    "conflict",
    "source_pipeline_incomplete",
]

ReviewState = Literal[
    "extracted",
    "hr_confirmed",
    "hr_corrected",
    "rejected",
    "unreviewed",
    "not_applicable",
]


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_kind: str
    source_record_id: str
    company_code: str
    app_key: str | None = None
    document_version_id: str | None = None
    extraction_version_id: str | None = None
    authority_level: AuthorityLevel = "canonical"
    review_state: ReviewState = "unreviewed"
    observed_at: str | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CoverageItem:
    section: str
    state: CoverageState
    reason_codes: tuple[str, ...] = ()
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "note": self.note,
        }


@dataclass(frozen=True)
class Actionability:
    readable: bool
    contact_allowed: bool
    lifecycle_mutation_allowed: bool
    job_ranking_allowed: bool
    held_state: str | None = None
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "readable": self.readable,
            "contact_allowed": self.contact_allowed,
            "lifecycle_mutation_allowed": self.lifecycle_mutation_allowed,
            "job_ranking_allowed": self.job_ranking_allowed,
            "held_state": self.held_state,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class CandidateKnowledgeSubject:
    display_name: str | None
    contact_email_present: bool = False
    contact_phone_present: bool = False
    contact_email: str | None = None
    contact_phone: str | None = None
    source: str = "candidates"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateKnowledgeRecord:
    """Internal typed record for candidate-knowledge-v1."""

    candidate_ref: str
    company_code: str
    as_of: str
    knowledge_version: str
    subject: CandidateKnowledgeSubject
    governance: dict[str, Any] = field(default_factory=dict)
    identity_state: dict[str, Any] = field(default_factory=dict)
    canonical_cv: dict[str, Any] = field(default_factory=dict)
    effective_facts: dict[str, Any] = field(default_factory=dict)
    classifications: dict[str, Any] = field(default_factory=dict)
    applications: list[dict[str, Any]] = field(default_factory=list)
    screening_evidence: list[dict[str, Any]] = field(default_factory=list)
    assessments: list[dict[str, Any]] = field(default_factory=list)
    interviews: list[dict[str, Any]] = field(default_factory=list)
    ranking_evaluations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    evidence_manifest: list[EvidenceRef] = field(default_factory=list)
    coverage: list[CoverageItem] = field(default_factory=list)
    actionability: Actionability = field(
        default_factory=lambda: Actionability(
            readable=False,
            contact_allowed=False,
            lifecycle_mutation_allowed=False,
            job_ranking_allowed=False,
            reason_codes=("not_assembled",),
        )
    )
    schema: str = CANDIDATE_KNOWLEDGE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_ref": self.candidate_ref,
            "company_code": self.company_code,
            "as_of": self.as_of,
            "knowledge_version": self.knowledge_version,
            "subject": self.subject.to_dict(),
            "governance": self.governance,
            "identity_state": self.identity_state,
            "canonical_cv": self.canonical_cv,
            "effective_facts": self.effective_facts,
            "classifications": self.classifications,
            "applications": list(self.applications),
            "screening_evidence": list(self.screening_evidence),
            "assessments": list(self.assessments),
            "interviews": list(self.interviews),
            "ranking_evaluations": list(self.ranking_evaluations),
            "notes": list(self.notes),
            "evidence_manifest": [item.to_dict() for item in self.evidence_manifest],
            "coverage": [item.to_dict() for item in self.coverage],
            "actionability": self.actionability.to_dict(),
        }


def candidate_ref_from_app_key(app_key: str) -> str:
    key = str(app_key or "").strip()
    if not key:
        raise ValueError("app_key_required")
    if key.startswith(CANDIDATE_REF_PREFIX):
        return key
    return f"{CANDIDATE_REF_PREFIX}{key}"


def app_key_from_candidate_ref(candidate_ref: str) -> str:
    value = str(candidate_ref or "").strip()
    if not value.startswith(CANDIDATE_REF_PREFIX):
        raise ValueError("invalid_candidate_ref")
    app_key = value[len(CANDIDATE_REF_PREFIX) :].strip()
    if not app_key:
        raise ValueError("invalid_candidate_ref")
    return app_key


SECTION_NAMES: tuple[str, ...] = (
    "subject",
    "governance",
    "identity_state",
    "canonical_cv",
    "effective_facts",
    "classifications",
    "applications",
    "screening_evidence",
    "assessments",
    "interviews",
    "ranking_evaluations",
    "notes",
)
