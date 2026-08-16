"""Dual-path Ranking shadow parity harness (Phase 6).

Runs the existing scorer path and the Candidate Knowledge adapter path separately.
Does not mix inputs/outputs, does not write ranking runs, does not cut over live Ranking.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import candidate_ranking as cr
from ranking_evidence_adapter import (
    RankingEvidenceAdapter,
    RankingEvidenceBundle,
    RankingJobContext,
    is_evaluation_stale,
)


DIFFERENCE_CLASSES = (
    "expected_evidence_improvement",
    "expected_authority_difference",
    "bug",
    "unexplained",
    "blocked_by_missing_canonical_evidence",
)


def _norm(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class ShadowParityResult:
    ok: bool
    eligibility_match: bool
    tenant_isolation_ok: bool
    held_exclusion_match: bool
    existing_path: dict[str, Any]
    adapter_path: dict[str, Any]
    differences: list[dict[str, Any]] = field(default_factory=list)
    unexplained_score_differences: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: dict[str, float] = field(default_factory=dict)
    side_effects: dict[str, int] = field(default_factory=dict)
    qualification_pass: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "eligibility_match": self.eligibility_match,
            "tenant_isolation_ok": self.tenant_isolation_ok,
            "held_exclusion_match": self.held_exclusion_match,
            "existing_path": self.existing_path,
            "adapter_path": self.adapter_path,
            "differences": self.differences,
            "unexplained_score_differences": self.unexplained_score_differences,
            "latency_ms": self.latency_ms,
            "side_effects": self.side_effects,
            "qualification_pass": self.qualification_pass,
            "paths_mixed": False,
        }


def build_legacy_ranking_row(
    *,
    company_code: str,
    app_key: str,
    position_code: str,
    status: str,
    raw_json: dict[str, Any] | None = None,
    candidate_profile: dict[str, Any] | None = None,
    cv_ready_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Simulate existing Ranking pool row using legacy mirrors (shadow only)."""

    row = {
        "company_code": company_code,
        "app_key": app_key,
        "position_code": position_code,
        "status": status,
        "raw_json": raw_json or {},
        "candidate_profile": candidate_profile or {},
        "application_cv_facts": None,
        "cv_facts_id": None,
        "cv_facts_status": "missing",
        "screening_status": None,
        "assessment_status": None,
        "assessment_percent": None,
    }
    row.update(cv_ready_fields or {})
    return row


def score_row(
    row: dict[str, Any],
    *,
    job: dict[str, Any],
    hard_criteria: list[dict[str, Any]],
    soft_criteria: list[dict[str, Any]],
    evidence_policy: dict[str, Any] | None = None,
    semantic_similarity: float | None = None,
) -> dict[str, Any]:
    """Existing Ranking scorer path for one row (no persistence)."""

    eligibility = cr.evaluate_application_eligibility(
        hard_criteria,
        row,
        evidence_policy=evidence_policy,
    )
    soft = cr.soft_component_scores(
        row=row,
        job=job,
        soft_criteria=soft_criteria,
        semantic_similarity=semantic_similarity,
        evidence_policy=evidence_policy,
    )
    return {
        "eligibility_bucket": eligibility.get("eligibility_bucket"),
        "required_missing": eligibility.get("required_missing") or [],
        "requirement_results": eligibility.get("requirement_results") or [],
        "advisory_score": soft.get("advisory_score"),
        "component_scores": soft.get("component_scores") or {},
        "missing_data": soft.get("missing_data") or [],
        "evidence_coverage": soft.get("evidence_coverage"),
        "confidence": soft.get("confidence"),
        "ranking_result_kind": soft.get("ranking_result_kind"),
        "legacy_fallback": bool(
            (cr._structured_cv_fields(row) or {}).get("legacy_candidate_profile_fallback")
        ),
    }


def classify_difference(
    *,
    field: str,
    existing_value: Any,
    adapter_value: Any,
    adapter_bundle: RankingEvidenceBundle,
    existing_used_legacy_fallback: bool,
) -> str:
    if existing_value == adapter_value:
        return "expected_authority_difference"  # unused when equal
    if field == "advisory_score" and existing_used_legacy_fallback and not adapter_bundle.row.get("raw_json"):
        return "expected_evidence_improvement"
    if field in {"evidence_coverage", "missing_data"} and adapter_bundle.unavailable_sections:
        return "blocked_by_missing_canonical_evidence"
    if field == "eligibility_bucket" and adapter_bundle.denial_reason == "held_or_job_ranking_ineligible":
        return "expected_authority_difference"
    if field == "legacy_fallback":
        return "expected_authority_difference"
    # Score moved with richer canonical facts and no legacy fallback.
    if field in {"advisory_score", "component_scores"} and not existing_used_legacy_fallback:
        # Same authority family but values differ without classification → unexplained until reviewed.
        if adapter_bundle.unavailable_sections:
            return "blocked_by_missing_canonical_evidence"
        return "unexplained"
    if existing_used_legacy_fallback:
        return "expected_evidence_improvement"
    return "unexplained"


def run_shadow_parity(
    *,
    adapter: RankingEvidenceAdapter,
    record: Any,
    job_context: RankingJobContext,
    application: dict[str, Any],
    legacy_row: dict[str, Any],
    job: dict[str, Any],
    hard_criteria: list[dict[str, Any]],
    soft_criteria: list[dict[str, Any]],
    governance: dict[str, Any] | None = None,
    prior_pins: dict[str, Any] | None = None,
) -> ShadowParityResult:
    started = time.perf_counter()
    t0 = time.perf_counter()
    existing = score_row(
        legacy_row,
        job=job,
        hard_criteria=hard_criteria,
        soft_criteria=soft_criteria,
        evidence_policy=job_context.evidence_policy,
    )
    existing_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    bundle = adapter.adapt(
        record,
        job_context=job_context,
        application=application,
        governance=governance,
    )
    adapted_score = None
    if bundle.eligible:
        adapted_score = score_row(
            bundle.row,
            job=job,
            hard_criteria=hard_criteria,
            soft_criteria=soft_criteria,
            evidence_policy=bundle.evidence_policy,
        )
    else:
        adapted_score = {
            "eligibility_bucket": "not_applicable",
            "required_missing": [bundle.denial_reason],
            "advisory_score": None,
            "component_scores": {},
            "missing_data": [],
            "evidence_coverage": 0,
            "confidence": "low",
            "legacy_fallback": False,
        }
    adapter_ms = (time.perf_counter() - t1) * 1000

    held_statuses = {"needs_role", "import_review", "import_archived"}
    legacy_held = _norm(legacy_row.get("status")).lower() in held_statuses
    adapter_held_denied = bundle.denial_reason == "held_or_job_ranking_ineligible" or not bundle.eligible and legacy_held
    held_exclusion_match = (legacy_held and not bundle.eligible) or (not legacy_held)

    # Existing path typically still scores held rows if the caller passes them;
    # production SQL excludes them. Shadow compares adapter gate vs production policy.
    production_style_existing_eligible = not legacy_held
    eligibility_match = production_style_existing_eligible == bundle.eligible

    differences: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []
    for field in ("eligibility_bucket", "advisory_score", "evidence_coverage", "legacy_fallback"):
        left = existing.get(field)
        right = adapted_score.get(field)
        if left == right:
            continue
        klass = classify_difference(
            field=field,
            existing_value=left,
            adapter_value=right,
            adapter_bundle=bundle,
            existing_used_legacy_fallback=bool(existing.get("legacy_fallback")),
        )
        item = {
            "field": field,
            "existing": left,
            "adapter": right,
            "class": klass,
        }
        differences.append(item)
        if klass in {"unexplained", "bug"}:
            unexplained.append(item)

    stale = None
    if prior_pins:
        stale = is_evaluation_stale(
            prior_pins,
            current_knowledge_version=bundle.pins.knowledge_version,
            current_cv_version_id=bundle.pins.canonical_cv_version_id,
            current_fact_snapshot_id=bundle.pins.fact_snapshot_id,
            current_criteria_version=bundle.pins.criteria_version,
        )

    tenant_ok = _norm(bundle.row.get("company_code")).upper() == _norm(job_context.company_code).upper()
    qualification_pass = (
        tenant_ok
        and held_exclusion_match
        and not unexplained
        and bundle.side_effects.get("ranking_writes", 0) == 0
    )

    return ShadowParityResult(
        ok=True,
        eligibility_match=eligibility_match,
        tenant_isolation_ok=tenant_ok,
        held_exclusion_match=held_exclusion_match,
        existing_path={
            "score": existing,
            "uses_raw_json": bool(legacy_row.get("raw_json")),
            "uses_candidate_profile": bool(legacy_row.get("candidate_profile")),
        },
        adapter_path={
            "eligible": bundle.eligible,
            "denial_reason": bundle.denial_reason,
            "score": adapted_score,
            "pins": bundle.pins.to_dict(),
            "coverage": bundle.coverage,
            "unavailable_sections": bundle.unavailable_sections,
            "stale_vs_prior": stale,
            "raw_json_present": bundle.row.get("raw_json") not in (None, {}),
            "profile_present": bundle.row.get("candidate_profile") not in (None, {}),
        },
        differences=differences,
        unexplained_score_differences=unexplained,
        latency_ms={
            "existing_ms": round(existing_ms, 3),
            "adapter_ms": round(adapter_ms, 3),
            "total_ms": round((time.perf_counter() - started) * 1000, 3),
        },
        side_effects=dict(bundle.side_effects),
        qualification_pass=qualification_pass,
    )


__all__ = [
    "DIFFERENCE_CLASSES",
    "ShadowParityResult",
    "build_legacy_ranking_row",
    "score_row",
    "classify_difference",
    "run_shadow_parity",
]
