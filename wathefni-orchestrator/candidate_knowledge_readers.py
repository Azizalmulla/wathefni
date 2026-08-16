"""Phase 2 canonical source readers for Candidate Knowledge.

Reads only governed CV text versions, fact snapshots + review events, and
classification runs/suggestions/reviews. Never falls back to profile, raw JSON,
or semantic_documents. Never triggers OCR/extraction/Voyage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from candidate_knowledge_types import CoverageItem, CoverageState, EvidenceRef, ReviewState
from unified_candidates import effective_facts_from_events
from talent_pool_classification import effective_classification


PHASE2_READER_VERSION = "candidate-knowledge-phase2-readers-v1"


@dataclass
class SectionRead:
    section: str
    payload: dict[str, Any]
    coverage: CoverageItem
    evidence: list[EvidenceRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "payload": self.payload,
            "coverage": self.coverage.to_dict(),
            "evidence": [item.to_dict() for item in self.evidence],
        }


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _truthy_current(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "t", "yes"}


def _evidence_id(*parts: Any) -> str:
    digest = hashlib.sha256("|".join(_norm(part) for part in parts).encode("utf-8")).hexdigest()
    return f"ev_{digest[:24]}"


def _coverage(
    section: str,
    state: CoverageState,
    *reason_codes: str,
    note: str | None = None,
) -> CoverageItem:
    return CoverageItem(section=section, state=state, reason_codes=tuple(reason_codes), note=note)


def _channel_from_provenance(provenance: Any, document: dict[str, Any] | None = None) -> str:
    if isinstance(provenance, dict):
        channel = _norm(provenance.get("channel") or provenance.get("source") or provenance.get("intake_channel"))
        if channel:
            return channel.lower()
    doc = document or {}
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    channel = _norm(doc.get("source") or meta.get("channel") or meta.get("intake_channel"))
    return channel.lower() if channel else "unknown"


def read_canonical_cv(
    store: Any,
    *,
    company_code: str,
    app_key: str,
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    key = _norm(app_key)
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="canonical_cv",
            payload={},
            coverage=_coverage("canonical_cv", "not_authorized", "read_projection_denied"),
        )
    if read_projection == "restricted" or read_projection == "metadata_only":
        # Still disclose presence metadata without body text when restricted.
        versions = store.list_cv_text_versions(company_code=company, app_key=key)
        current = [item for item in versions if _truthy_current(item.get("is_current"))]
        return SectionRead(
            section="canonical_cv",
            payload={
                "text": None,
                "suppressed": True,
                "current_version_count": len(current),
            },
            coverage=_coverage("canonical_cv", "restricted", "metadata_only"),
        )

    versions = store.list_cv_text_versions(company_code=company, app_key=key)
    if not versions:
        return SectionRead(
            section="canonical_cv",
            payload={},
            coverage=_coverage(
                "canonical_cv",
                "not_recorded",
                "no_cv_text_versions",
                note="No immutable CV text versions recorded for this application.",
            ),
        )

    current_rows = [item for item in versions if _truthy_current(item.get("is_current"))]
    if len(current_rows) > 1:
        evidence = [
            EvidenceRef(
                evidence_id=_evidence_id(company, key, item.get("version_id"), "conflict"),
                source_kind="candidate_cv_text_versions",
                source_record_id=_norm(item.get("version_id")),
                company_code=company,
                app_key=key,
                document_version_id=_norm(item.get("version_id")) or None,
                authority_level="canonical",
                review_state="unreviewed",
                observed_at=_norm(item.get("created_at")) or None,
                content_hash=_norm(item.get("extracted_text_hash") or item.get("source_content_sha256")) or None,
            )
            for item in current_rows
        ]
        return SectionRead(
            section="canonical_cv",
            payload={"conflict_version_ids": [_norm(item.get("version_id")) for item in current_rows]},
            coverage=_coverage(
                "canonical_cv",
                "conflict",
                "multiple_current_cv_versions",
                note="Conflicting current CV versions; no silent selection.",
            ),
            evidence=evidence,
        )

    if not current_rows:
        invalidated = [
            item
            for item in versions
            if _norm(item.get("status")).lower() in {"invalidated", "superseded", "failed"}
        ]
        if invalidated and all(_norm(item.get("status")).lower() in {"invalidated", "superseded"} for item in versions):
            state: CoverageState = "invalidated"
            reason = "all_versions_invalidated_or_superseded"
        else:
            state = "not_extracted"
            reason = "no_current_cv_version"
        return SectionRead(
            section="canonical_cv",
            payload={"version_count": len(versions)},
            coverage=_coverage("canonical_cv", state, reason),
        )

    current = current_rows[0]
    status = _norm(current.get("status")).lower()
    if status == "invalidated":
        return SectionRead(
            section="canonical_cv",
            payload={"version_id": _norm(current.get("version_id"))},
            coverage=_coverage("canonical_cv", "invalidated", "current_version_invalidated"),
        )
    if status and status not in {"ready", "completed", "current", ""}:
        return SectionRead(
            section="canonical_cv",
            payload={"version_id": _norm(current.get("version_id")), "status": status},
            coverage=_coverage(
                "canonical_cv",
                "source_pipeline_incomplete",
                f"current_status:{status or 'unknown'}",
            ),
        )

    text = current.get("text_content")
    if text is None or str(text).strip() == "":
        return SectionRead(
            section="canonical_cv",
            payload={"version_id": _norm(current.get("version_id"))},
            coverage=_coverage("canonical_cv", "not_extracted", "current_version_empty_text"),
        )

    document = None
    document_id = _norm(current.get("document_id"))
    if document_id and hasattr(store, "get_candidate_document"):
        document = store.get_candidate_document(company_code=company, document_id=document_id)

    provenance = current.get("provenance") if isinstance(current.get("provenance"), dict) else {}
    channel = _channel_from_provenance(provenance, document)
    payload = {
        "version_id": _norm(current.get("version_id")),
        "document_id": document_id or None,
        "text": str(text),
        "extraction_method": current.get("extraction_method"),
        "extraction_finalization_id": current.get("extraction_finalization_id"),
        "content_hash": current.get("extracted_text_hash") or current.get("source_content_sha256"),
        "source_content_sha256": current.get("source_content_sha256"),
        "status": status or "ready",
        "is_current": True,
        "channel": channel,
        "provenance": {
            "channel": channel,
            "evidence_id": current.get("evidence_id"),
            "facts_id": current.get("facts_id"),
        },
        "observed_at": current.get("created_at"),
        "created_at": current.get("created_at"),
        "superseded_at": current.get("superseded_at"),
        "reader_version": PHASE2_READER_VERSION,
    }
    evidence = [
        EvidenceRef(
            evidence_id=_evidence_id(company, key, current.get("version_id"), "canonical_cv"),
            source_kind="candidate_cv_text_versions",
            source_record_id=_norm(current.get("version_id")),
            company_code=company,
            app_key=key,
            document_version_id=_norm(current.get("version_id")) or None,
            extraction_version_id=_norm(current.get("extraction_finalization_id")) or None,
            authority_level="canonical",
            review_state="extracted",
            observed_at=_norm(current.get("created_at")) or None,
            content_hash=_norm(payload.get("content_hash")) or None,
        )
    ]
    return SectionRead(
        section="canonical_cv",
        payload=payload,
        coverage=_coverage("canonical_cv", "available", "current_ready_version"),
        evidence=evidence,
    )


def _snapshot_as_projection_input(snapshot_row: dict[str, Any]) -> dict[str, Any]:
    facts = snapshot_row.get("facts")
    if isinstance(facts, dict) and "snapshot" in facts:
        body = facts
    elif isinstance(facts, dict):
        body = {
            "schema": snapshot_row.get("contract_version") or "application-cv-facts-v1",
            "snapshot": facts,
            "source": "application_cv_fact_snapshots",
        }
    else:
        body = {
            "schema": snapshot_row.get("contract_version") or "application-cv-facts-v1",
            "snapshot": {},
            "source": "application_cv_fact_snapshots",
        }
    body = dict(body)
    body["source"] = "application_cv_fact_snapshots"
    body["facts_id"] = snapshot_row.get("facts_id")
    body["contract_version"] = snapshot_row.get("contract_version")
    body["extractor_version"] = snapshot_row.get("extractor_version")
    body["confidence"] = snapshot_row.get("confidence")
    body["status"] = snapshot_row.get("status")
    return body


def read_effective_facts(
    store: Any,
    *,
    company_code: str,
    app_key: str,
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    key = _norm(app_key)
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="effective_facts",
            payload={},
            coverage=_coverage("effective_facts", "not_authorized", "read_projection_denied"),
        )
    if read_projection == "metadata_only":
        return SectionRead(
            section="effective_facts",
            payload={"suppressed": True},
            coverage=_coverage("effective_facts", "restricted", "metadata_only"),
        )

    snapshots = store.list_fact_snapshots(company_code=company, app_key=key)
    if not snapshots:
        return SectionRead(
            section="effective_facts",
            payload={"missing_policy": "Not extracted or Unknown — never a negative fact"},
            coverage=_coverage(
                "effective_facts",
                "not_recorded",
                "no_fact_snapshots",
                note="No application_cv_fact_snapshots rows for this application.",
            ),
        )

    current_rows = [item for item in snapshots if _truthy_current(item.get("is_current"))]
    if len(current_rows) > 1:
        return SectionRead(
            section="effective_facts",
            payload={"conflict_facts_ids": [_norm(item.get("facts_id")) for item in current_rows]},
            coverage=_coverage("effective_facts", "conflict", "multiple_current_fact_snapshots"),
        )
    if not current_rows:
        invalidated = [item for item in snapshots if _norm(item.get("status")).lower() == "invalidated"]
        state: CoverageState = "invalidated" if invalidated else "stale"
        return SectionRead(
            section="effective_facts",
            payload={"snapshot_count": len(snapshots)},
            coverage=_coverage("effective_facts", state, "no_current_fact_snapshot"),
        )

    current = current_rows[0]
    status = _norm(current.get("status")).lower()
    if status == "invalidated":
        return SectionRead(
            section="effective_facts",
            payload={"facts_id": _norm(current.get("facts_id"))},
            coverage=_coverage("effective_facts", "invalidated", "current_snapshot_invalidated"),
        )
    if status and status not in {"ready", "completed", ""}:
        return SectionRead(
            section="effective_facts",
            payload={"facts_id": _norm(current.get("facts_id")), "status": status},
            coverage=_coverage(
                "effective_facts",
                "source_pipeline_incomplete",
                f"snapshot_status:{status}",
            ),
        )

    events = store.list_fact_review_events(company_code=company, app_key=key)
    snapshot = _snapshot_as_projection_input(current)
    projected = effective_facts_from_events(snapshot, events)
    effective = projected.get("effective") if isinstance(projected.get("effective"), dict) else {}
    reviews = projected.get("reviews_by_path") if isinstance(projected.get("reviews_by_path"), dict) else {}

    # Map review states for evidence without copying sensitive values into digests.
    evidence: list[EvidenceRef] = [
        EvidenceRef(
            evidence_id=_evidence_id(company, key, current.get("facts_id"), "facts_snapshot"),
            source_kind="application_cv_fact_snapshots",
            source_record_id=_norm(current.get("facts_id")),
            company_code=company,
            app_key=key,
            document_version_id=_norm(current.get("document_id")) or None,
            authority_level="canonical",
            review_state="extracted",
            observed_at=_norm(current.get("materialized_at") or current.get("created_at")) or None,
            content_hash=_norm(current.get("facts_hash") or current.get("extracted_text_hash")) or None,
        )
    ]
    for path, event in reviews.items():
        display = _norm(event.get("display_state")).lower()
        review_state: ReviewState = "hr_confirmed"
        if display == "rejected":
            review_state = "rejected"
        elif _norm(event.get("action")).lower() == "correct":
            review_state = "hr_corrected"
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, key, event.get("event_id") or path, "fact_review"),
                source_kind="candidate_fact_review_events",
                source_record_id=_norm(event.get("event_id") or path),
                company_code=company,
                app_key=key,
                authority_level="hr_confirmed",
                review_state=review_state,
                observed_at=_norm(event.get("created_at")) or None,
            )
        )

    payload = {
        "facts_id": current.get("facts_id"),
        "evidence_id": current.get("evidence_id"),
        "document_id": current.get("document_id"),
        "contract_version": current.get("contract_version"),
        "extractor_version": current.get("extractor_version"),
        "confidence": current.get("confidence"),
        "status": status or "ready",
        "extraction_snapshot": snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else {},
        "effective": effective,
        "reviews_by_path": {
            path: {
                "action": event.get("action"),
                "display_state": event.get("display_state"),
                "event_id": event.get("event_id"),
                "fact_path": path,
            }
            for path, event in reviews.items()
        },
        "skills": effective.get("skills"),
        "employment": effective.get("employment") or effective.get("experience"),
        "experience_years": effective.get("experience_years"),
        "education": effective.get("education"),
        "certifications": effective.get("certifications"),
        "languages": effective.get("languages"),
        "projects": effective.get("projects"),
        "missing_policy": projected.get("missing_policy"),
        "completeness": {
            "review_event_count": len(events),
            "reviewed_path_count": len(reviews),
        },
        "reader_version": PHASE2_READER_VERSION,
    }
    coverage_state: CoverageState = "available"
    reasons = ["current_ready_snapshot"]
    if reviews:
        reasons.append("hr_review_events_applied")
    if not any(effective.get(field) not in (None, "", [], {}) for field in ("skills", "employment", "education", "languages", "projects", "experience_years")):
        coverage_state = "partial"
        reasons.append("effective_values_sparse")
    return SectionRead(
        section="effective_facts",
        payload=payload,
        coverage=_coverage("effective_facts", coverage_state, *reasons),
        evidence=evidence,
    )


def read_effective_classification(
    store: Any,
    *,
    company_code: str,
    app_key: str,
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    key = _norm(app_key)
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="classifications",
            payload={},
            coverage=_coverage("classifications", "not_authorized", "read_projection_denied"),
        )
    if read_projection == "metadata_only":
        return SectionRead(
            section="classifications",
            payload={"suppressed": True},
            coverage=_coverage("classifications", "restricted", "metadata_only"),
        )

    runs = store.list_classification_runs(company_code=company, app_key=key)
    if not runs:
        return SectionRead(
            section="classifications",
            payload={
                "hr_confirmed": [],
                "ai_suggested": [],
                "rejected": [],
            },
            coverage=_coverage(
                "classifications",
                "not_recorded",
                "no_classification_runs",
                note="Missing classification is coverage, not candidate weakness.",
            ),
        )

    invalidations = store.list_classification_invalidations(company_code=company, app_key=key)
    invalidated_run_ids = {_norm(item.get("run_id")) for item in invalidations}
    eligible_runs = [item for item in runs if _norm(item.get("run_id")) not in invalidated_run_ids]
    if not eligible_runs:
        return SectionRead(
            section="classifications",
            payload={"invalidated_run_ids": sorted(invalidated_run_ids)},
            coverage=_coverage("classifications", "invalidated", "all_runs_invalidated"),
        )

    eligible_runs.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    current_run = eligible_runs[0]
    run_id = _norm(current_run.get("run_id"))
    suggestions = [
        item
        for item in store.list_classification_suggestions(company_code=company, app_key=key)
        if _norm(item.get("run_id")) == run_id or (_norm(item.get("state")).lower() == "active" and _norm(item.get("run_id")) not in invalidated_run_ids)
    ]
    # Prefer suggestions bound to current eligible run.
    run_suggestions = [item for item in suggestions if _norm(item.get("run_id")) == run_id]
    if run_suggestions:
        suggestions = run_suggestions

    review_events = store.list_classification_review_events(company_code=company, app_key=key)
    projected = effective_classification(suggestions=suggestions, review_events=review_events, include_medium_ai=False)

    taxonomy_version = _norm(current_run.get("taxonomy_version"))
    taxonomy_release = store.get_taxonomy_release(taxonomy_version=taxonomy_version) if taxonomy_version else None
    taxonomy_nodes = store.list_taxonomy_nodes(taxonomy_version=taxonomy_version) if taxonomy_version else []
    nodes_by_id = {_norm(item.get("node_id")): item for item in taxonomy_nodes}

    def enrich(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for item in items:
            node = nodes_by_id.get(_norm(item.get("node_id")), {})
            out.append(
                {
                    "node_id": item.get("node_id"),
                    "node_type": item.get("node_type") or node.get("node_type"),
                    "label_en": item.get("label_en") or node.get("label_en"),
                    "label_ar": item.get("label_ar") or node.get("label_ar"),
                    "authority": item.get("authority"),
                    "confidence_band": item.get("confidence_band"),
                    "confidence_score": item.get("confidence_score"),
                    "suggestion_id": item.get("suggestion_id"),
                    "event_id": item.get("event_id"),
                }
            )
        return out

    hr_confirmed = enrich(list(projected.get("confirmed") or []))
    ai_suggested = enrich(list(projected.get("ai_suggested") or []))
    rejected = [
        {"node_id": node_id, "authority": "rejected"}
        for node_id in (projected.get("rejected_node_ids") or [])
    ]

    def by_type(rows: list[dict[str, Any]], node_type: str) -> list[dict[str, Any]]:
        return [item for item in rows if _norm(item.get("node_type")).lower() == node_type.lower()]

    payload = {
        "run_id": run_id,
        "run_status": current_run.get("status"),
        "taxonomy_version": taxonomy_version or None,
        "classifier_version": current_run.get("classifier_version"),
        "taxonomy_release": {
            "taxonomy_version": taxonomy_release.get("taxonomy_version"),
            "label_en": taxonomy_release.get("label_en"),
            "immutable": taxonomy_release.get("immutable"),
        }
        if isinstance(taxonomy_release, dict)
        else None,
        "hr_confirmed": hr_confirmed,
        "ai_suggested": ai_suggested,
        "rejected": rejected,
        "job_families": by_type(hr_confirmed + ai_suggested, "job_family")
        or by_type(hr_confirmed + ai_suggested, "family"),
        "suggested_roles": by_type(hr_confirmed + ai_suggested, "role")
        or by_type(hr_confirmed + ai_suggested, "likely_role"),
        "seniority": by_type(hr_confirmed + ai_suggested, "seniority"),
        "career_functions": by_type(hr_confirmed + ai_suggested, "career_function")
        or by_type(hr_confirmed + ai_suggested, "career_area"),
        "skills": by_type(hr_confirmed + ai_suggested, "skill"),
        "industries": by_type(hr_confirmed + ai_suggested, "industry"),
        "invalidated_run_ids": sorted(invalidated_run_ids),
        "reader_version": PHASE2_READER_VERSION,
    }

    evidence = [
        EvidenceRef(
            evidence_id=_evidence_id(company, key, run_id, "classification_run"),
            source_kind="candidate_classification_runs",
            source_record_id=run_id,
            company_code=company,
            app_key=key,
            authority_level="canonical",
            review_state="unreviewed",
            observed_at=_norm(current_run.get("created_at")) or None,
            content_hash=_norm(current_run.get("input_bundle_hash")) or None,
        )
    ]
    for item in hr_confirmed:
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, key, item.get("event_id") or item.get("node_id"), "hr_class"),
                source_kind="candidate_classification_review_events",
                source_record_id=_norm(item.get("event_id") or item.get("node_id")),
                company_code=company,
                app_key=key,
                authority_level="hr_confirmed",
                review_state="hr_confirmed",
            )
        )
    for item in ai_suggested:
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, key, item.get("suggestion_id") or item.get("node_id"), "ai_class"),
                source_kind="candidate_classification_suggestions",
                source_record_id=_norm(item.get("suggestion_id") or item.get("node_id")),
                company_code=company,
                app_key=key,
                authority_level="ai_suggested",
                review_state="unreviewed",
            )
        )

    if hr_confirmed or ai_suggested:
        coverage_state: CoverageState = "available"
        reasons = ["eligible_non_invalidated_run"]
    else:
        coverage_state = "partial"
        reasons = ["run_present_without_active_labels"]

    return SectionRead(
        section="classifications",
        payload=payload,
        coverage=_coverage("classifications", coverage_state, *reasons),
        evidence=evidence,
    )
