"""Pure RankingEvidenceAdapter (Phase 6).

Converts an authorized CandidateKnowledgeRecord into the scorer-compatible row
contract used by candidate_ranking.evaluate_application_eligibility /
soft_component_scores.

Read-only. No DB writes, no Voyage, no Ranking run creation, no Job admission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import candidate_cv_evidence as _cv_evidence
import candidate_cv_facts as _cv_facts
from candidate_knowledge_errors import (
    ERROR_CANDIDATE_RESTRICTED,
    ERROR_INVALID_COMPARISON_CONTEXT,
    ERROR_PERMISSION_DENIED,
    ERROR_TENANT_SCOPE_REQUIRED,
    CandidateKnowledgeError,
)
from candidate_knowledge_types import Actionability, CandidateKnowledgeRecord, CoverageItem
from candidate_record_state_policy import (
    INTAKE_HOLD_STATUSES,
    evaluate_candidate_record_state,
)


ADAPTER_VERSION = "ranking-evidence-adapter-v1"
EVIDENCE_POLICY_VERSION = "ranking-evidence-policy-v1"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _stable_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return "evd_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _as_value_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for item in value:
            if isinstance(item, dict):
                if "value" in item:
                    out.append(dict(item))
                else:
                    # employment-style dicts pass through
                    out.append(item)
            elif str(item).strip():
                out.append({"value": str(item).strip()})
        return out
    if isinstance(value, dict):
        if "value" in value:
            return [dict(value)]
        return [value]
    if str(value).strip():
        return [{"value": str(value).strip()}]
    return []


def _as_years(value: Any) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict) and "value" in value:
        return dict(value)
    try:
        return {"value": float(value)}
    except Exception:
        return {"value": value}


def normalize_facts_for_ranking(effective_facts: dict[str, Any] | None) -> dict[str, Any]:
    """Map CK effective facts into application_cv_facts snapshot shape."""

    payload = effective_facts if isinstance(effective_facts, dict) else {}
    effective = payload.get("effective") if isinstance(payload.get("effective"), dict) else payload
    facts = {
        "skills": _as_value_list(effective.get("skills") or payload.get("skills")),
        "employment": [
            item
            for item in _as_value_list(effective.get("employment") or effective.get("employment_history") or payload.get("employment"))
            if isinstance(item, dict)
        ],
        "education": _as_value_list(effective.get("education") or payload.get("education")),
        "certifications": _as_value_list(effective.get("certifications") or payload.get("certifications")),
        "languages": _as_value_list(effective.get("languages") or payload.get("languages")),
        "projects": _as_value_list(effective.get("projects") or payload.get("projects")),
        "status": _norm(payload.get("status") or "ready") or "ready",
    }
    years = _as_years(effective.get("experience_years") or payload.get("experience_years"))
    if years is not None:
        facts["experience_years"] = years
    return facts


@dataclass(frozen=True)
class RankingJobContext:
    company_code: str
    position_code: str
    job_id: str | None = None
    job_version: int | None = None
    criteria_set_id: str | None = None
    criteria_version: int | None = None
    scorer_model_version: str | None = "ranking-soft-v2"
    evidence_policy_version: str = EVIDENCE_POLICY_VERSION
    evidence_policy: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RankingEvidencePins:
    candidate_ref: str
    app_key: str
    knowledge_version: str
    canonical_cv_version_id: str | None
    fact_snapshot_id: str | None
    fact_review_fingerprint: str | None
    classification_run_id: str | None
    classification_review_fingerprint: str | None
    assessment_attempt_ids: tuple[str, ...]
    interview_ids: tuple[str, ...]
    criteria_version: int | None
    scorer_model_version: str | None
    evidence_digest: str
    retrieved_at: str
    adapter_version: str = ADAPTER_VERSION

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["assessment_attempt_ids"] = list(self.assessment_attempt_ids)
        payload["interview_ids"] = list(self.interview_ids)
        return payload


@dataclass
class RankingEvidenceBundle:
    ok: bool
    eligible: bool
    denial_reason: str | None
    row: dict[str, Any]
    pins: RankingEvidencePins
    coverage: dict[str, Any]
    unavailable_sections: list[dict[str, Any]]
    classifications: dict[str, Any]
    screening_claims: list[dict[str, Any]]
    assessment_summaries: list[dict[str, Any]]
    interview_summaries: list[dict[str, Any]]
    actionability: dict[str, Any]
    evidence_policy: dict[str, Any]
    side_effects: dict[str, Any] = field(
        default_factory=lambda: {
            "ranking_writes": 0,
            "lifecycle_writes": 0,
            "communication_writes": 0,
            "identity_writes": 0,
            "extraction_triggers": 0,
            "indexing_writes": 0,
            "external_calls": 0,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "eligible": self.eligible,
            "denial_reason": self.denial_reason,
            "row": dict(self.row),
            "pins": self.pins.to_dict(),
            "coverage": dict(self.coverage),
            "unavailable_sections": list(self.unavailable_sections),
            "classifications": dict(self.classifications),
            "screening_claims": list(self.screening_claims),
            "assessment_summaries": list(self.assessment_summaries),
            "interview_summaries": list(self.interview_summaries),
            "actionability": dict(self.actionability),
            "evidence_policy": dict(self.evidence_policy),
            "side_effects": dict(self.side_effects),
            "adapter_version": ADAPTER_VERSION,
        }


def _coverage_map(record: CandidateKnowledgeRecord) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in record.coverage or []:
        if isinstance(item, CoverageItem):
            out[item.section] = {
                "state": item.state,
                "reason_codes": list(item.reason_codes),
                "note": item.note,
            }
        elif isinstance(item, dict):
            out[str(item.get("section"))] = {
                "state": item.get("state"),
                "reason_codes": list(item.get("reason_codes") or []),
                "note": item.get("note"),
            }
    return out


def _unavailable(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    unavailable = []
    for section, row in coverage.items():
        state = _norm(row.get("state"))
        if state in {
            "not_recorded",
            "not_extracted",
            "source_pipeline_incomplete",
            "module_disabled",
            "not_authorized",
            "restricted",
            "conflict",
            "not_indexed",
        }:
            unavailable.append(
                {
                    "section": section,
                    "state": state,
                    "reason_codes": row.get("reason_codes") or [],
                    "unknown_not_negative": True,
                }
            )
    return unavailable


def _fingerprint(items: list[Any]) -> str | None:
    if not items:
        return None
    return _stable_digest({"items": items})


class RankingEvidenceAdapter:
    """Pure adapter. Never mutates Ranking/Job/lifecycle/communication/identity."""

    def __init__(self) -> None:
        self.ranking_writes = 0
        self.lifecycle_writes = 0
        self.communication_writes = 0
        self.identity_writes = 0
        self.extraction_triggers = 0
        self.indexing_writes = 0
        self.external_calls = 0

    def adapt(
        self,
        record: CandidateKnowledgeRecord,
        *,
        job_context: RankingJobContext | dict[str, Any],
        application: dict[str, Any] | None = None,
        governance: dict[str, Any] | None = None,
        include_interview_summaries: bool = False,
        assessments_module_enabled: bool = True,
    ) -> RankingEvidenceBundle:
        job = job_context if isinstance(job_context, RankingJobContext) else RankingJobContext(
            company_code=_norm(job_context.get("company_code")).upper(),
            position_code=_norm(job_context.get("position_code")).upper(),
            job_id=_norm(job_context.get("job_id")) or None,
            job_version=job_context.get("job_version"),
            criteria_set_id=_norm(job_context.get("criteria_set_id")) or None,
            criteria_version=job_context.get("criteria_version"),
            scorer_model_version=_norm(job_context.get("scorer_model_version")) or "ranking-soft-v2",
            evidence_policy_version=_norm(job_context.get("evidence_policy_version")) or EVIDENCE_POLICY_VERSION,
            evidence_policy=job_context.get("evidence_policy") if isinstance(job_context.get("evidence_policy"), dict) else None,
        )

        if not job.company_code:
            raise CandidateKnowledgeError(ERROR_TENANT_SCOPE_REQUIRED, "Job context requires company_code.")
        if not job.position_code:
            raise CandidateKnowledgeError(
                ERROR_INVALID_COMPARISON_CONTEXT,
                "Job context requires position_code.",
                reason_codes=(ERROR_INVALID_COMPARISON_CONTEXT, "missing_position_code"),
            )
        if job.criteria_version is None:
            raise CandidateKnowledgeError(
                ERROR_INVALID_COMPARISON_CONTEXT,
                "Job context requires criteria_version.",
                reason_codes=(ERROR_INVALID_COMPARISON_CONTEXT, "missing_criteria_version"),
            )
        if _norm(record.company_code).upper() != job.company_code:
            raise CandidateKnowledgeError(
                ERROR_PERMISSION_DENIED,
                "Candidate Knowledge record tenant does not match Job context.",
                reason_codes=(ERROR_PERMISSION_DENIED, "cross_tenant"),
            )

        app = dict(application or {})
        status = _norm(app.get("status") or "").lower()
        if not status and record.applications:
            # Prefer anchor application status from assembled history when available.
            for item in record.applications:
                if _norm(item.get("app_key")) == _norm(record.candidate_ref).removeprefix("app:"):
                    status = _norm(item.get("lifecycle_status") or item.get("status")).lower()
                    app.setdefault("app_key", item.get("app_key"))
                    app.setdefault("position_code", item.get("position_code"))
                    break
            if not status and record.applications:
                status = _norm(record.applications[0].get("lifecycle_status") or record.applications[0].get("status")).lower()

        decision = evaluate_candidate_record_state(
            {"status": status or "review_pending", **{k: v for k, v in app.items() if k != "status"}},
            governance=governance,
        )
        actionability = (
            record.actionability.to_dict()
            if isinstance(record.actionability, Actionability)
            else dict(record.actionability or {})
        )

        coverage = _coverage_map(record)
        unavailable = _unavailable(coverage)
        denial = None
        eligible = True
        if decision.read_projection == "denied" or "deletion_completed" in decision.governance_flags:
            eligible = False
            denial = "deleted_or_denied"
        elif "restricted" in decision.governance_flags or decision.read_projection == "metadata_only":
            eligible = False
            denial = "restricted"
        elif "archived" in decision.governance_flags or status == "import_archived":
            eligible = False
            denial = "archived"
        elif status in INTAKE_HOLD_STATUSES or not decision.job_ranking_eligible:
            eligible = False
            denial = "held_or_job_ranking_ineligible"
        elif not actionability.get("job_ranking_allowed", decision.job_ranking_eligible):
            eligible = False
            denial = "actionability_job_ranking_denied"

        if not eligible and denial in {"deleted_or_denied", "restricted"}:
            # Hard deny as restricted for these states.
            raise CandidateKnowledgeError(
                ERROR_CANDIDATE_RESTRICTED,
                "Candidate is not eligible for Job Ranking evidence adaptation.",
                reason_codes=(ERROR_CANDIDATE_RESTRICTED, denial),
            )

        app_key = _norm(app.get("app_key")) or _norm(record.candidate_ref).removeprefix("app:")
        canonical_cv = dict(record.canonical_cv or {})
        version_id = _norm(canonical_cv.get("version_id")) or None
        content_hash = _norm(
            canonical_cv.get("content_hash")
            or canonical_cv.get("extracted_text_hash")
            or canonical_cv.get("source_content_sha256")
        )
        facts_payload = normalize_facts_for_ranking(record.effective_facts)
        facts_id = _norm((record.effective_facts or {}).get("facts_id")) or None
        if facts_id is None and any(facts_payload.get(key) for key in ("skills", "employment", "education", "languages")):
            facts_id = "ck-facts-" + _stable_digest({"app": app_key, "facts": facts_payload})[4:20]

        # Bounded semantic projection from facts only — never unrestricted CV body.
        from candidate_ranking import ranking_feature_text, sanitize_ranking_payload

        structured_for_text = sanitize_ranking_payload(_cv_facts.ranking_fields(facts_payload))
        semantic_content = ranking_feature_text(
            semantic_content="",
            structured=structured_for_text if isinstance(structured_for_text, dict) else {},
        )
        if not semantic_content and version_id:
            semantic_content = f"canonical_cv_version:{version_id}"
        semantic_hash = content_hash or (
            hashlib.sha256(semantic_content.encode("utf-8")).hexdigest() if semantic_content else ""
        )
        if content_hash and not semantic_content:
            semantic_content = f"canonical_cv_hash:{content_hash}"

        # CV evidence readiness fields: mark ready only when canonical version exists.
        cv_ready = bool(version_id and semantic_hash and semantic_content)
        file_id = _norm(canonical_cv.get("document_id") or version_id or "")
        row: dict[str, Any] = {
            "company_code": job.company_code,
            "app_key": app_key,
            "position_code": job.position_code,
            "status": status or "review_pending",
            "candidate_ref": record.candidate_ref,
            # Explicitly exclude raw mirrors.
            "raw_json": None,
            "candidate_profile": None,
            # Facts authority
            "application_cv_facts": facts_payload,
            "cv_facts_id": facts_id,
            "facts_id": facts_id,
            "cv_facts_status": "ready" if facts_id else "missing",
            "cv_facts_contract_version": _cv_facts.CV_FACTS_CONTRACT_VERSION,
            "cv_facts_extractor_version": _norm((record.effective_facts or {}).get("extractor_version")) or None,
            "cv_facts_hash": _stable_digest(facts_payload) if facts_id else None,
            # CV evidence readiness
            "cv_evidence_status": "ready" if cv_ready else "missing",
            "cv_evidence_file_id": file_id if cv_ready else "",
            "cv_evidence_source_sha256": semantic_hash if cv_ready else "",
            "cv_extraction_finalization_id": _norm(canonical_cv.get("extraction_finalization_id") or version_id),
            "cv_extraction_quality_ok": True if cv_ready else False,
            "cv_extracted_text_hash": semantic_hash if cv_ready else "",
            "cv_evidence_semantic_content_hash": semantic_hash if cv_ready else "",
            "semantic_content_hash": semantic_hash if cv_ready else "",
            "semantic_content": semantic_content if cv_ready else "",
            "cv_evidence_contract_version": _cv_evidence.CV_EVIDENCE_CONTRACT_VERSION if cv_ready else "",
            "cv_evidence_embedding_status": "not_required",
            "cv_file_id": file_id or None,
            "cv_evidence_id": version_id,
            # Screening
            "screening_status": _screening_status(record.screening_evidence),
            # Assessment flat fields (latest completed if present)
            **_assessment_flat(record.assessments if assessments_module_enabled else []),
        }

        # Validate readiness helpers do not see forbidden raw payloads.
        assert row.get("raw_json") in (None, {})
        assert row.get("candidate_profile") in (None, {})

        classifications = {
            "hr_confirmed": list((record.classifications or {}).get("hr_confirmed") or []),
            "ai_suggested": list((record.classifications or {}).get("ai_suggested") or []),
            "rejected": list((record.classifications or {}).get("rejected") or []),
            "run_id": (record.classifications or {}).get("run_id"),
            "taxonomy_version": (record.classifications or {}).get("taxonomy_version"),
        }
        screening_claims = [
            {
                "question_key": item.get("question_key"),
                "answer_value": item.get("answer_value"),
                "source": item.get("source"),
                "captured_at": item.get("captured_at"),
                "stale": item.get("stale"),
            }
            for item in (record.screening_evidence or [])
            if isinstance(item, dict)
        ]
        assessment_summaries = [
            {
                "attempt_id": item.get("attempt_id"),
                "status": item.get("status"),
                "completed_score": item.get("completed_score"),
                "score_band": item.get("score_band"),
                "approved_report_summary": item.get("approved_report_summary"),
            }
            for item in (record.assessments or [])
            if isinstance(item, dict)
        ]
        interview_summaries = []
        if include_interview_summaries:
            for item in record.interviews or []:
                if not isinstance(item, dict):
                    continue
                interview_summaries.append(
                    {
                        "interview_id": item.get("interview_id"),
                        "status": item.get("status"),
                        "feedback_status": item.get("feedback_status"),
                        "ai_summary_labeled": (item.get("ai_summary") or {}).get("labeled_as")
                        if isinstance(item.get("ai_summary"), dict)
                        else None,
                        "transcript_available": item.get("transcript_available"),
                        # Never include transcript body / meet links.
                    }
                )

        pins = RankingEvidencePins(
            candidate_ref=record.candidate_ref,
            app_key=app_key,
            knowledge_version=_norm(record.knowledge_version) or "unknown",
            canonical_cv_version_id=version_id,
            fact_snapshot_id=facts_id,
            fact_review_fingerprint=_fingerprint(
                list(((record.effective_facts or {}).get("reviews_by_path") or {}).items())
            ),
            classification_run_id=_norm(classifications.get("run_id")) or None,
            classification_review_fingerprint=_fingerprint(classifications.get("hr_confirmed") or []),
            assessment_attempt_ids=tuple(
                _norm(item.get("attempt_id")) for item in assessment_summaries if _norm(item.get("attempt_id"))
            ),
            interview_ids=tuple(
                _norm(item.get("interview_id")) for item in interview_summaries if _norm(item.get("interview_id"))
            ),
            criteria_version=int(job.criteria_version) if job.criteria_version is not None else None,
            scorer_model_version=job.scorer_model_version,
            evidence_digest="",
            retrieved_at=_now(),
        )
        digest = _stable_digest(
            {
                "pins": {k: v for k, v in pins.to_dict().items() if k != "evidence_digest"},
                "facts_hash": row.get("cv_facts_hash"),
                "cv_version": version_id,
                "criteria_version": job.criteria_version,
            }
        )
        pins = RankingEvidencePins(**{**pins.to_dict(), "evidence_digest": digest})

        policy = dict(job.evidence_policy or {})
        if not policy:
            from candidate_ranking import DEFAULT_EVIDENCE_POLICY, normalize_evidence_policy

            policy = normalize_evidence_policy(DEFAULT_EVIDENCE_POLICY)

        return RankingEvidenceBundle(
            ok=True,
            eligible=eligible,
            denial_reason=denial,
            row=row,
            pins=pins,
            coverage=coverage,
            unavailable_sections=unavailable,
            classifications=classifications,
            screening_claims=screening_claims,
            assessment_summaries=assessment_summaries if assessments_module_enabled else [],
            interview_summaries=interview_summaries,
            actionability={
                **actionability,
                "job_ranking_allowed": bool(eligible and decision.job_ranking_eligible),
                "held_state": decision.held_state,
            },
            evidence_policy=policy,
            side_effects={
                "ranking_writes": self.ranking_writes,
                "lifecycle_writes": self.lifecycle_writes,
                "communication_writes": self.communication_writes,
                "identity_writes": self.identity_writes,
                "extraction_triggers": self.extraction_triggers,
                "indexing_writes": self.indexing_writes,
                "external_calls": self.external_calls,
            },
        )


def _screening_status(screening_evidence: list[dict[str, Any]] | None) -> str:
    rows = screening_evidence if isinstance(screening_evidence, list) else []
    if not rows:
        return "missing"
    if any(item.get("stale") for item in rows if isinstance(item, dict)):
        return "in_progress"
    # Presence of typed answers is treated as complete for optional screening policy.
    return "completed"


def _assessment_flat(assessments: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = [item for item in (assessments or []) if isinstance(item, dict)]
    completed = [item for item in rows if _norm(item.get("status")).lower() == "completed"]
    chosen = completed[0] if completed else (rows[0] if rows else None)
    if not chosen:
        return {
            "assessment_status": None,
            "assessment_percent": None,
            "assessment_attempt_id": None,
            "assessment_position_code": None,
            "assessment_battery_key": None,
            "assessment_version_id": None,
            "assessment_norm_version": None,
        }
    return {
        "assessment_status": chosen.get("status"),
        "assessment_percent": chosen.get("completed_score"),
        "assessment_attempt_id": chosen.get("attempt_id"),
        "assessment_position_code": None,
        "assessment_battery_key": chosen.get("battery_key"),
        "assessment_version_id": chosen.get("assessment_version_id"),
        "assessment_norm_version": None,
    }


def is_evaluation_stale(
    pins: RankingEvidencePins | dict[str, Any],
    *,
    current_knowledge_version: str | None = None,
    current_cv_version_id: str | None = None,
    current_fact_snapshot_id: str | None = None,
    current_fact_review_fingerprint: str | None = None,
    current_classification_run_id: str | None = None,
    current_classification_review_fingerprint: str | None = None,
    current_criteria_version: int | None = None,
) -> dict[str, Any]:
    """Report staleness without rewriting historical evaluations."""

    payload = pins.to_dict() if isinstance(pins, RankingEvidencePins) else dict(pins)
    reasons = []
    checks = [
        ("knowledge_version", current_knowledge_version, payload.get("knowledge_version")),
        ("canonical_cv_version_id", current_cv_version_id, payload.get("canonical_cv_version_id")),
        ("fact_snapshot_id", current_fact_snapshot_id, payload.get("fact_snapshot_id")),
        ("fact_review_fingerprint", current_fact_review_fingerprint, payload.get("fact_review_fingerprint")),
        ("classification_run_id", current_classification_run_id, payload.get("classification_run_id")),
        (
            "classification_review_fingerprint",
            current_classification_review_fingerprint,
            payload.get("classification_review_fingerprint"),
        ),
        ("criteria_version", current_criteria_version, payload.get("criteria_version")),
    ]
    for name, current, pinned in checks:
        if current is None:
            continue
        if str(current) != str(pinned):
            reasons.append(name)
    return {
        "stale": bool(reasons),
        "reasons": reasons,
        "rewrites_historical": False,
        "pinned_evidence_digest": payload.get("evidence_digest"),
    }


__all__ = [
    "ADAPTER_VERSION",
    "RankingJobContext",
    "RankingEvidencePins",
    "RankingEvidenceBundle",
    "RankingEvidenceAdapter",
    "normalize_facts_for_ranking",
    "is_evaluation_stale",
]
