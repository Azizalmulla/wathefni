"""Wave 4 Candidate Knowledge person:/subject: refs (additive).

Preserves app: exact reads and Wave 1 _anchor_actionability. person:/subject:
refs are searchable; provisional/held subjects remain non-actionable.
Identity correction invalidates old chunks before reindex.
"""

from __future__ import annotations

import os
from typing import Any

from candidate_knowledge_types import (
    Actionability,
    CANDIDATE_REF_PREFIX,
    app_key_from_candidate_ref,
    candidate_ref_from_app_key,
)

FEATURE_CK_PERSON_SUBJECT = "WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS"
PERSON_REF_PREFIX = "person:"
SUBJECT_REF_PREFIX = "subject:"
WAVE4_CK_VERSION = "candidate-knowledge-person-subject-v1"


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_CK_PERSON_SUBJECT))


def _norm(value: Any) -> str:
    return str(value or "").strip()


def candidate_ref_from_person_id(person_id: str) -> str:
    key = _norm(person_id)
    if not key:
        raise ValueError("person_id_required")
    if key.startswith(PERSON_REF_PREFIX):
        return key
    return f"{PERSON_REF_PREFIX}{key}"


def candidate_ref_from_subject_id(subject_id: str) -> str:
    key = _norm(subject_id)
    if not key:
        raise ValueError("subject_id_required")
    if key.startswith(SUBJECT_REF_PREFIX):
        return key
    return f"{SUBJECT_REF_PREFIX}{key}"


def person_id_from_candidate_ref(candidate_ref: str) -> str:
    value = _norm(candidate_ref)
    if not value.startswith(PERSON_REF_PREFIX):
        raise ValueError("invalid_person_ref")
    person_id = value[len(PERSON_REF_PREFIX) :].strip()
    if not person_id:
        raise ValueError("invalid_person_ref")
    return person_id


def subject_id_from_candidate_ref(candidate_ref: str) -> str:
    value = _norm(candidate_ref)
    if not value.startswith(SUBJECT_REF_PREFIX):
        raise ValueError("invalid_subject_ref")
    subject_id = value[len(SUBJECT_REF_PREFIX) :].strip()
    if not subject_id:
        raise ValueError("invalid_subject_ref")
    return subject_id


def classify_knowledge_ref(value: Any) -> tuple[str, str]:
    """Return (kind, normalized_ref) for app|person|subject."""

    raw = _norm(value)
    if not raw:
        raise ValueError("candidate_ref_required")
    if any(ch.isspace() for ch in raw):
        raise ValueError("candidate_ref_whitespace")
    if raw.startswith(CANDIDATE_REF_PREFIX):
        return "app", candidate_ref_from_app_key(app_key_from_candidate_ref(raw))
    if raw.startswith(PERSON_REF_PREFIX):
        return "person", candidate_ref_from_person_id(person_id_from_candidate_ref(raw))
    if raw.startswith(SUBJECT_REF_PREFIX):
        return "subject", candidate_ref_from_subject_id(subject_id_from_candidate_ref(raw))
    raise ValueError("unsupported_candidate_ref_kind")


def talent_pool_actionability(*, provisional: bool, held: bool, restricted: bool) -> Actionability:
    """Talent Pool / subject refs: searchable when not restricted; never Job-actionable."""

    if restricted:
        return Actionability(
            readable=False,
            contact_allowed=False,
            lifecycle_mutation_allowed=False,
            job_ranking_allowed=False,
            held_state="restricted",
            reason_codes=("candidate_restricted",),
        )
    held_state = "provisional" if provisional else ("held" if held else "talent_pool")
    return Actionability(
        readable=True,
        contact_allowed=False,
        lifecycle_mutation_allowed=False,
        job_ranking_allowed=False,
        held_state=held_state,
        reason_codes=("searchable_non_actionable", "requires_verified_job_binding"),
    )


def invalidate_before_identity_reindex(
    index_store: Any,
    *,
    company_code: str,
    old_candidate_refs: list[str],
    reason: str = "identity_correction",
) -> dict[str, Any]:
    """Invalidate chunks for prior refs before reindexing corrected identity."""

    invalidated = 0
    for ref in old_candidate_refs:
        ref_n = _norm(ref)
        if not ref_n:
            continue
        invalidated += int(
            index_store.invalidate_chunks(
                company_code=company_code,
                candidate_ref=ref_n,
                reason=reason,
            )
            or 0
        )
    return {
        "ok": True,
        "invalidated": invalidated,
        "refs": list(old_candidate_refs),
        "reason": reason,
        "reindex_required": True,
        "version": WAVE4_CK_VERSION,
    }


def index_meta_for_ref(
    *,
    candidate_ref: str,
    actionable: bool = False,
    provisional: bool = False,
) -> dict[str, Any]:
    kind, normalized = classify_knowledge_ref(candidate_ref)
    return {
        "candidate_ref": normalized,
        "ref_kind": kind,
        "searchable": True,
        "actionable": bool(actionable) and kind == "app",
        "provisional": provisional or kind == "subject",
        "job_ranking_allowed": False if kind != "app" else None,
        "version": WAVE4_CK_VERSION,
    }


__all__ = [
    "FEATURE_CK_PERSON_SUBJECT",
    "PERSON_REF_PREFIX",
    "SUBJECT_REF_PREFIX",
    "WAVE4_CK_VERSION",
    "enabled",
    "candidate_ref_from_person_id",
    "candidate_ref_from_subject_id",
    "person_id_from_candidate_ref",
    "subject_id_from_candidate_ref",
    "classify_knowledge_ref",
    "talent_pool_actionability",
    "invalidate_before_identity_reindex",
    "index_meta_for_ref",
]
