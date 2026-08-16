"""Phase 5 governed Candidate Knowledge tools (local shadow mode).

Thin adapters over CandidateKnowledgeAuthority + Phase 4 search. Never open SQL
connections, never choose source authority, never register into the live
production action registry.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from candidate_knowledge_authority import (
    CandidateKnowledgeAuthority,
    build_request_context,
)
from candidate_knowledge_errors import (
    ERROR_AUDIT_WRITE_FAILED,
    ERROR_CANONICAL_VERSION_CONFLICT,
    ERROR_INVALID_COMPARISON_CONTEXT,
    ERROR_SECTION_NOT_AUTHORIZED,
    ERROR_SHADOW_TOOLS_DISABLED,
    CandidateKnowledgeError,
)
from candidate_knowledge_search import CandidateKnowledgeSearchService
from candidate_knowledge_types import app_key_from_candidate_ref


PHASE5_VERSION = "candidate-knowledge-phase5-tools-v1"
POLICY_VERSION = "candidate-record-state-policy-v1"
MAX_COMPARE_REFS = 5
MIN_COMPARE_REFS = 2
MODEL_CV_CHUNK_BUDGET = 3
MODEL_SNIPPET_CHARS = 240
MODEL_FACT_KEYS = (
    "skills",
    "employment",
    "employment_history",
    "education",
    "certifications",
    "languages",
    "projects",
    "experience_years",
)
PROTECTED_TRAIT_MARKERS = (
    "religion",
    "race",
    "ethnicity",
    "national origin",
    "gender",
    "pregnancy",
    "disability",
    "age discrimination",
    "marital status",
    "political",
)
SHELL_SECTIONS = frozenset({"subject", "governance"})
READER_SECTIONS = frozenset(
    {
        "canonical_cv",
        "effective_facts",
        "classifications",
        "applications",
        "screening_evidence",
        "assessments",
        "interviews",
        "ranking_evaluations",
        "notes",
        "identity_state",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _request_id(explicit: str | None = None) -> str:
    if _norm(explicit):
        return _norm(explicit)
    return "ckreq_" + uuid.uuid4().hex[:20]


def _tokenize(text: str) -> set[str]:
    return {part.lower() for part in re.split(r"[^\w\u0600-\u06FF]+", text or "") if len(part) > 1}


@dataclass
class ShadowToolRuntime:
    """Local shadow runtime. Disabled unless explicitly enabled."""

    authority: CandidateKnowledgeAuthority
    search: CandidateKnowledgeSearchService
    audit_store: Any
    enabled: bool = False
    module_enabled: Callable[[str, str], bool] | None = None
    mutation_count: int = 0
    production_registry_writes: int = 0

    def assert_shadow_enabled(self) -> None:
        if not self.enabled:
            raise CandidateKnowledgeError(
                ERROR_SHADOW_TOOLS_DISABLED,
                "Candidate Knowledge shadow tools are disabled.",
            )


def write_access_audit_or_fail(
    audit_store: Any,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Fail closed if the dedicated access audit cannot be written."""

    try:
        written = audit_store.record_access_event(event)
    except Exception as exc:
        raise CandidateKnowledgeError(
            ERROR_AUDIT_WRITE_FAILED,
            "Candidate Knowledge access audit write failed closed.",
            reason_codes=(ERROR_AUDIT_WRITE_FAILED, "audit_exception"),
        ) from exc
    if not isinstance(written, dict) or not _norm(written.get("event_id")):
        raise CandidateKnowledgeError(
            ERROR_AUDIT_WRITE_FAILED,
            "Candidate Knowledge access audit write returned no event_id.",
            reason_codes=(ERROR_AUDIT_WRITE_FAILED, "audit_missing_event_id"),
        )
    # Content-free guarantee.
    for banned in ("chunk_text", "snippet", "email", "phone", "embedding", "query_text", "cv_text"):
        if banned in written:
            raise CandidateKnowledgeError(
                ERROR_AUDIT_WRITE_FAILED,
                "Access audit contained forbidden content fields.",
                reason_codes=(ERROR_AUDIT_WRITE_FAILED, f"forbidden_field:{banned}"),
            )
    return written


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    filt = dict(filters or {})
    if "statuses" in filt and "status" not in filt:
        filt["status"] = filt.get("statuses")
    return filt


def _select_relevant_chunks(
    audit_store: Any,
    *,
    company_code: str,
    candidate_ref: str,
    focus_question: str,
    limit: int = MODEL_CV_CHUNK_BUDGET,
) -> list[dict[str, Any]]:
    chunks = audit_store.list_chunks(
        company_code=company_code,
        candidate_ref=candidate_ref,
        states=["current"],
    )
    if not chunks:
        app_key = app_key_from_candidate_ref(candidate_ref)
        if app_key:
            chunks = audit_store.list_chunks(
                company_code=company_code,
                app_key=app_key,
                states=["current"],
            )
    # Prefer canonical CV chunks.
    cv_chunks = [item for item in chunks if _norm(item.get("source_family")) == "canonical_cv"]
    pool = cv_chunks or chunks
    tokens = _tokenize(focus_question)
    ranked = []
    for chunk in pool:
        text = _norm(chunk.get("chunk_text"))
        overlap = len(tokens & _tokenize(text)) if tokens else 0
        ranked.append((overlap, _norm(chunk.get("chunk_id")), chunk))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected = []
    for overlap, _chunk_id, chunk in ranked[:limit]:
        text = _norm(chunk.get("chunk_text"))
        selected.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "section_type": chunk.get("section_type"),
                "document_version_id": chunk.get("document_version_id"),
                "source_family": chunk.get("source_family"),
                "snippet": text[:MODEL_SNIPPET_CHARS],
                "relevance": "focus_overlap" if overlap else "current_cv_window",
                "evidence_refs": chunk.get("evidence_refs") or [],
            }
        )
    return selected


def _facts_summary(effective_facts: dict[str, Any]) -> dict[str, Any]:
    payload = effective_facts if isinstance(effective_facts, dict) else {}
    effective = payload.get("effective") if isinstance(payload.get("effective"), dict) else payload
    out = {}
    for key in MODEL_FACT_KEYS:
        if key in effective and effective.get(key) is not None:
            out[key] = effective.get(key)
    return out


def _coverage_map(coverage_items: list[Any]) -> dict[str, Any]:
    out = {}
    for item in coverage_items or []:
        if hasattr(item, "to_dict"):
            row = item.to_dict()
        elif isinstance(item, dict):
            row = item
        else:
            continue
        out[str(row.get("section"))] = {
            "state": row.get("state"),
            "reason_codes": row.get("reason_codes") or [],
            "note": row.get("note"),
        }
    return out


def _omission_reasons(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    omitted = []
    for section, row in coverage.items():
        state = _norm(row.get("state"))
        if state in {"not_recorded", "not_authorized", "module_disabled", "restricted", "conflict", "source_pipeline_incomplete"}:
            omitted.append(
                {
                    "section": section,
                    "state": state,
                    "reason_codes": row.get("reason_codes") or [],
                }
            )
    return omitted


def search_candidates(
    runtime: ShadowToolRuntime,
    *,
    company_code: str,
    actor_user_id: str,
    permission_authority: str,
    permission_subject_user_id: str,
    permission_subject_company: str,
    permissions: list[str] | tuple[str, ...],
    modules_enabled: list[str] | tuple[str, ...] | None = None,
    query: str,
    scope: str = "talent_pool",
    filters: dict[str, Any] | None = None,
    limit: int = 20,
    cursor: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Governed discovery tool. Shadow mode only."""

    runtime.assert_shadow_enabled()
    assert_owner_canary_actor(actor_user_id)
    started = time.perf_counter()
    req_id = _request_id(request_id)
    context = build_request_context(
        company_code=company_code,
        actor_user_id=actor_user_id,
        permission_authority=permission_authority,
        permission_subject_user_id=permission_subject_user_id,
        permission_subject_company=permission_subject_company,
        permissions=permissions,
        modules_enabled=modules_enabled,
        request_id=req_id,
    )
    # Fail closed via authority authorization (tenant/actor/backend_current/prehire/module).
    runtime.authority.authorize(context)

    filt = _normalize_filters(filters)
    raw = runtime.search.search(
        company_code=context.company_code,
        actor_user_id=context.actor_user_id,
        permission_authority=context.permission_authority,
        permissions=context.permissions,
        query=query,
        scope=scope,  # type: ignore[arg-type]
        filters=filt,
        limit=limit,
        cursor=cursor,
    )

    # Dedicated audit must succeed before evidence is returned to the caller.
    write_access_audit_or_fail(
        runtime.audit_store,
        {
            "company_code": context.company_code,
            "actor_user_id": context.actor_user_id,
            "request_id": req_id,
            "operation": "search_candidates",
            "tool": "search_candidates",
            "scope": scope,
            "retrieval_mode": raw.get("retrieval_mode"),
            "result_count": len(raw.get("items") or []),
            "candidate_refs": [item.get("candidate_ref") for item in (raw.get("items") or [])],
            "policy_version": POLICY_VERSION,
            "reason_codes": ["shadow_mode", str(raw.get("retrieval_mode") or "")],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "result_status": "ok",
        },
    )

    items = []
    for item in raw.get("items") or []:
        evidence_refs = []
        for match in item.get("matching_sections") or []:
            for ref in match.get("evidence_refs") or []:
                if isinstance(ref, dict):
                    evidence_refs.append(
                        {
                            "source_family": ref.get("source_family"),
                            "source_record_id": ref.get("source_record_id"),
                            "document_version_id": ref.get("document_version_id"),
                        }
                    )
            evidence_refs.append(
                {
                    "chunk_id": match.get("chunk_id"),
                    "section_type": match.get("section_type"),
                    "document_version_id": match.get("document_version_id"),
                }
            )
        items.append(
            {
                "candidate_ref": item.get("candidate_ref"),
                "display_name": item.get("display_name"),
                "anchor_app_key": item.get("app_key"),
                "application_count": 1,
                "held_state": item.get("held_state"),
                "lifecycle_status": item.get("lifecycle_status"),
                "classifications": item.get("classifications") or {},
                "match_reasons": item.get("match_reasons") or [],
                "matching_sections": item.get("matching_sections") or [],
                "search_relevance": item.get("search_relevance"),
                "coverage": item.get("coverage"),
                "actionability": item.get("actionability"),
                "evidence_refs": evidence_refs,
                "index_version": item.get("index_version"),
            }
        )

    return {
        "ok": True,
        "tool": "search_candidates",
        "mode": "shadow",
        "request_id": req_id,
        "as_of": _now(),
        "knowledge_version": PHASE5_VERSION,
        "retrieval_mode": raw.get("retrieval_mode"),
        "items": items,
        "next_cursor": raw.get("next_cursor"),
        "total": raw.get("total"),
        "scanned_entire_pool": raw.get("scanned_entire_pool"),
        "index_freshness": raw.get("index_freshness"),
        "embedding": raw.get("embedding"),
        "coverage": {
            "result_count": len(items),
            "index_state": raw.get("retrieval_mode"),
        },
        "redactions": {
            "contacts_redacted": True,
            "reason_codes": ["default_contact_redaction"],
        },
        "omission_reasons": [],
        "actionability_note": "Held Talent Pool hits remain non-actionable for communication/lifecycle/ranking.",
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "name_merge_forbidden": True,
    }


def get_candidate_knowledge(
    runtime: ShadowToolRuntime,
    *,
    company_code: str,
    actor_user_id: str,
    permission_authority: str,
    permission_subject_user_id: str,
    permission_subject_company: str,
    permissions: list[str] | tuple[str, ...],
    modules_enabled: list[str] | tuple[str, ...] | None = None,
    candidate_ref: str,
    focus_question: str | None = None,
    sections: list[str] | tuple[str, ...] | None = None,
    application_cursor: str | None = None,
    evidence_cursor: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Exact candidate knowledge tool through CandidateKnowledgeAuthority."""

    runtime.assert_shadow_enabled()
    assert_owner_canary_actor(actor_user_id)
    started = time.perf_counter()
    req_id = _request_id(request_id)
    context = build_request_context(
        company_code=company_code,
        actor_user_id=actor_user_id,
        permission_authority=permission_authority,
        permission_subject_user_id=permission_subject_user_id,
        permission_subject_company=permission_subject_company,
        permissions=permissions,
        modules_enabled=modules_enabled,
        request_id=req_id,
    )

    requested = list(sections or [
        "subject",
        "canonical_cv",
        "effective_facts",
        "classifications",
        "applications",
        "screening_evidence",
        "assessments",
        "interviews",
        "ranking_evaluations",
        "notes",
        "identity_state",
    ])
    denied_sections = []
    reader_sections = []
    for name in requested:
        if name in SHELL_SECTIONS:
            continue
        if name not in READER_SECTIONS:
            denied_sections.append(name)
            continue
        reader_sections.append(name)
    if denied_sections and not reader_sections and "subject" not in requested:
        raise CandidateKnowledgeError(
            ERROR_SECTION_NOT_AUTHORIZED,
            "Requested sections are not authorized.",
            reason_codes=(ERROR_SECTION_NOT_AUTHORIZED, *denied_sections),
        )

    app_offset = 0
    if application_cursor:
        try:
            app_offset = max(0, int(application_cursor))
        except Exception:
            app_offset = 0

    record = runtime.authority.assemble_phase3(
        context,
        candidate_ref,
        sections=tuple(reader_sections) if reader_sections else ("applications",),
        application_limit=20,
        application_offset=app_offset,
        include_phase2=True,
    )

    # Map canonical CV conflicts/unavailable into typed tool errors when CV was requested.
    if "canonical_cv" in reader_sections:
        cv_cov = next((item for item in record.coverage if getattr(item, "section", None) == "canonical_cv"), None)
        if cv_cov is not None:
            if cv_cov.state == "conflict":
                raise CandidateKnowledgeError(
                    ERROR_CANONICAL_VERSION_CONFLICT,
                    "Canonical CV version conflict.",
                )
            if cv_cov.state in {"not_recorded", "not_extracted", "source_pipeline_incomplete"} and not record.canonical_cv:
                # Soft: include coverage rather than hard-fail unless section was exclusive.
                pass

    focus = _norm(focus_question) or "summarize current candidate evidence"
    relevant_chunks = _select_relevant_chunks(
        runtime.audit_store,
        company_code=context.company_code,
        candidate_ref=record.candidate_ref,
        focus_question=focus,
    )

    coverage = _coverage_map(record.coverage)
    for name in denied_sections:
        coverage[name] = {
            "state": "not_authorized",
            "reason_codes": [ERROR_SECTION_NOT_AUTHORIZED],
            "note": "Section not in Candidate Knowledge Phase 5 contract.",
        }
    omissions = _omission_reasons(coverage)

    evidence_manifest = []
    for item in record.evidence_manifest:
        evidence_manifest.append(item.to_dict() if hasattr(item, "to_dict") else dict(item))
    for chunk in relevant_chunks:
        evidence_manifest.append(
            {
                "evidence_id": f"chunk:{chunk.get('chunk_id')}",
                "source_kind": chunk.get("source_family") or "candidate_knowledge_chunks",
                "source_record_id": chunk.get("chunk_id"),
                "company_code": context.company_code,
                "app_key": app_key_from_candidate_ref(record.candidate_ref),
                "document_version_id": chunk.get("document_version_id"),
            }
        )

    # Audit before returning evidence.
    write_access_audit_or_fail(
        runtime.audit_store,
        {
            "company_code": context.company_code,
            "actor_user_id": context.actor_user_id,
            "request_id": req_id,
            "operation": "get_candidate_knowledge",
            "tool": "get_candidate_knowledge",
            "candidate_ref": record.candidate_ref,
            "requested_sections": requested,
            "returned_sections": reader_sections,
            "retrieval_mode": "authority_exact",
            "evidence_count": len(evidence_manifest),
            "policy_version": POLICY_VERSION,
            "reason_codes": ["shadow_mode"] + [item["state"] for item in omissions],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "result_status": "ok",
        },
    )

    # Model-facing projection: never dump entire CV text.
    canonical_cv = dict(record.canonical_cv or {})
    if "text" in canonical_cv:
        canonical_cv = {
            "version_id": canonical_cv.get("version_id"),
            "channel": canonical_cv.get("channel"),
            "content_hash": canonical_cv.get("content_hash") or canonical_cv.get("extracted_text_hash"),
            "text_omitted": True,
            "omission_reason": "returned_via_relevant_chunks_only",
        }

    next_app_cursor = None
    if len(record.applications) >= 20:
        next_app_cursor = str(app_offset + 20)
    next_evidence_cursor = None
    if evidence_cursor is None and len(relevant_chunks) >= MODEL_CV_CHUNK_BUDGET:
        next_evidence_cursor = "1"

    return {
        "ok": True,
        "tool": "get_candidate_knowledge",
        "mode": "shadow",
        "request_id": req_id,
        "as_of": record.as_of or _now(),
        "knowledge_version": record.knowledge_version,
        "retrieval_mode": "authority_exact",
        "candidate_ref": record.candidate_ref,
        "subject": record.subject.to_dict(),
        "governance": record.governance,
        "identity_state": record.identity_state,
        "effective_facts": _facts_summary(record.effective_facts),
        "classifications": record.classifications,
        "applications": record.applications,
        "screening_evidence": record.screening_evidence,
        "assessments": record.assessments,
        "interviews": record.interviews,
        "ranking_evaluations": record.ranking_evaluations,
        "notes": record.notes if "notes" in reader_sections else [],
        "canonical_cv": canonical_cv if "canonical_cv" in reader_sections else {},
        "relevant_cv_chunks": relevant_chunks,
        "evidence_manifest": evidence_manifest,
        "coverage": coverage,
        "omission_reasons": omissions,
        "redactions": {
            "contacts_redacted": True,
            "full_cv_text_omitted": True,
            "reason_codes": ["default_contact_redaction", "cv_chunk_budget"],
        },
        "actionability": record.actionability.to_dict(),
        "application_cursor": {"next": next_app_cursor},
        "evidence_cursor": {"next": next_evidence_cursor},
        "focus_question": focus,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def compare_candidates(
    runtime: ShadowToolRuntime,
    *,
    company_code: str,
    actor_user_id: str,
    permission_authority: str,
    permission_subject_user_id: str,
    permission_subject_company: str,
    permissions: list[str] | tuple[str, ...],
    modules_enabled: list[str] | tuple[str, ...] | None = None,
    candidate_refs: list[str] | tuple[str, ...],
    question: str | None = None,
    dimensions: list[str] | tuple[str, ...] | None = None,
    job_context: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Compare 2–5 exact candidate refs on the same authority contract."""

    runtime.assert_shadow_enabled()
    assert_owner_canary_actor(actor_user_id)
    started = time.perf_counter()
    req_id = _request_id(request_id)
    refs = [_norm(item) for item in (candidate_refs or []) if _norm(item)]
    if len(refs) < MIN_COMPARE_REFS or len(refs) > MAX_COMPARE_REFS:
        raise CandidateKnowledgeError(
            ERROR_INVALID_COMPARISON_CONTEXT,
            f"compare_candidates requires {MIN_COMPARE_REFS} to {MAX_COMPARE_REFS} exact candidate refs.",
        )
    if len(set(refs)) != len(refs):
        raise CandidateKnowledgeError(
            ERROR_INVALID_COMPARISON_CONTEXT,
            "Duplicate candidate_refs are not allowed.",
        )

    q = _norm(question).lower()
    if any(marker in q for marker in PROTECTED_TRAIT_MARKERS):
        raise CandidateKnowledgeError(
            ERROR_INVALID_COMPARISON_CONTEXT,
            "Comparison on protected traits is not allowed.",
            reason_codes=(ERROR_INVALID_COMPARISON_CONTEXT, "protected_trait"),
        )

    dims = [ _norm(item) for item in (dimensions or ["skills", "employment", "languages", "assessments"]) if _norm(item) ]
    context = build_request_context(
        company_code=company_code,
        actor_user_id=actor_user_id,
        permission_authority=permission_authority,
        permission_subject_user_id=permission_subject_user_id,
        permission_subject_company=permission_subject_company,
        permissions=permissions,
        modules_enabled=modules_enabled,
        request_id=req_id,
    )

    as_of = _now()
    candidates = []
    for ref in refs:
        record = runtime.authority.assemble_phase3(
            context,
            ref,
            sections=("canonical_cv", "effective_facts", "classifications", "assessments", "interviews", "ranking_evaluations", "applications"),
            include_phase2=True,
        )
        facts = _facts_summary(record.effective_facts)
        dim_payload = {}
        for dim in dims:
            if dim in {"skills", "employment", "languages", "education", "certifications", "projects"}:
                key = "employment_history" if dim == "employment" and "employment_history" in facts else dim
                value = facts.get(key)
                dim_payload[dim] = {
                    "value": value,
                    "state": "available" if value not in (None, "", [], {}) else "unknown",
                    "evidence_refs": [
                        item.to_dict() if hasattr(item, "to_dict") else item
                        for item in record.evidence_manifest
                        if getattr(item, "source_kind", None) in {"application_cv_fact_snapshots", "candidate_fact_review_events"}
                        or (isinstance(item, dict) and item.get("source_kind") in {"application_cv_fact_snapshots", "candidate_fact_review_events"})
                    ][:5],
                }
            elif dim == "assessments":
                dim_payload[dim] = {
                    "value": record.assessments,
                    "state": "available" if record.assessments else "unknown",
                    "evidence_refs": [],
                }
            else:
                dim_payload[dim] = {"value": None, "state": "unknown", "evidence_refs": []}
        candidates.append(
            {
                "candidate_ref": record.candidate_ref,
                "display_name": record.subject.display_name,
                "dimensions": dim_payload,
                "actionability": record.actionability.to_dict(),
                "coverage": _coverage_map(record.coverage),
                "knowledge_version": record.knowledge_version,
            }
        )

    recommendation = None
    ranking_context = None
    if isinstance(job_context, dict) and job_context:
        # Read stored ranking only; never silently rescore.
        position_code = _norm(job_context.get("position_code"))
        if not position_code:
            raise CandidateKnowledgeError(
                ERROR_INVALID_COMPARISON_CONTEXT,
                "job_context.position_code is required when job_context is provided.",
            )
        ranking_context = {
            "position_code": position_code,
            "used_stored_ranking_only": True,
            "rescored": False,
        }
        stored = []
        for item in candidates:
            evals = []
            # Pull from assembled ranking_evaluations via re-read would be heavy; use authority store through get tool style.
            # Re-assemble already included ranking_evaluations in record above — recover from candidates dims only.
            stored.append({"candidate_ref": item["candidate_ref"], "stored_score": None})
        # Load ranking evaluations explicitly from a fresh assemble for ranking section.
        for ref in refs:
            record = runtime.authority.assemble_phase3(
                context,
                ref,
                sections=("ranking_evaluations",),
                include_phase2=False,
            )
            matched = [
                row
                for row in record.ranking_evaluations
                if _norm((row.get("job_context") or {}).get("position_code")) == position_code
                or _norm(row.get("position_code")) == position_code
            ]
            stored_score = matched[0].get("score") if matched else None
            for item in candidates:
                if item["candidate_ref"] == record.candidate_ref:
                    item["stored_job_ranking"] = {
                        "position_code": position_code,
                        "score": stored_score,
                        "state": "available" if stored_score is not None else "unknown",
                    }
        # Still do not recommend a best candidate automatically even with job context unless explicitly asked later.
        recommendation = {
            "best_candidate": None,
            "reason": "No automatic best-candidate recommendation; stored job ranking scores are attached when available.",
        }
    else:
        recommendation = {
            "best_candidate": None,
            "reason": "Factual comparison only; no Job Ranking context provided.",
        }

    write_access_audit_or_fail(
        runtime.audit_store,
        {
            "company_code": context.company_code,
            "actor_user_id": context.actor_user_id,
            "request_id": req_id,
            "operation": "compare_candidates",
            "tool": "compare_candidates",
            "candidate_refs": refs,
            "dimensions": dims,
            "retrieval_mode": "authority_compare",
            "policy_version": POLICY_VERSION,
            "reason_codes": ["shadow_mode", "no_best_recommendation"],
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "result_status": "ok",
        },
    )

    return {
        "ok": True,
        "tool": "compare_candidates",
        "mode": "shadow",
        "request_id": req_id,
        "as_of": as_of,
        "knowledge_version": PHASE5_VERSION,
        "retrieval_mode": "authority_compare",
        "question": _norm(question) or None,
        "dimensions": dims,
        "candidates": candidates,
        "recommendation": recommendation,
        "job_context": ranking_context,
        "coverage": {"candidate_count": len(candidates)},
        "redactions": {"contacts_redacted": True, "reason_codes": ["default_contact_redaction"]},
        "omission_reasons": [],
        "actionability": {"side_effects": False},
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


# --- Shadow registry (never touches production action_registry) ---

SHADOW_TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "search_candidates": search_candidates,
    "get_candidate_knowledge": get_candidate_knowledge,
    "compare_candidates": compare_candidates,
}


def shadow_tools_enabled(environ: dict[str, str] | None = None) -> bool:
    import os

    env = environ if environ is not None else dict(os.environ)
    return str(env.get("WATHEFNI_CK_SHADOW_TOOLS_ENABLED") or "").strip().lower() in {"1", "true", "yes"}


def owner_canary_actors(environ: dict[str, str] | None = None) -> set[str]:
    """Optional allowlist for owner/admin canary actors (comma-separated user ids)."""

    import os

    env = environ if environ is not None else dict(os.environ)
    raw = str(env.get("WATHEFNI_CK_OWNER_CANARY_ACTORS") or "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def assert_owner_canary_actor(actor_user_id: str, environ: dict[str, str] | None = None) -> None:
    """When an owner allowlist is configured, reject non-listed actors.

    Normal-user live tools remain off via WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
    and absence from action_registry. This gate further constrains the shadow path.
    Live allowlisted actors (WATHEFNI_CK_LIVE_TOOL_ACTORS) bypass the owner-canary
    list when live tools are enabled.
    """

    import os

    env = environ if environ is not None else dict(os.environ)
    actor = _norm(actor_user_id)
    live_on = str(env.get("WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS") or "").strip().lower() in {"1", "true", "yes", "on"}
    if live_on:
        live_raw = str(env.get("WATHEFNI_CK_LIVE_TOOL_ACTORS") or "").strip()
        live_allowed = {part.strip() for part in live_raw.split(",") if part.strip()}
        if live_allowed and actor in live_allowed:
            return
    allowed = owner_canary_actors(env)
    if not allowed:
        return
    if actor not in allowed:
        raise CandidateKnowledgeError(
            ERROR_SECTION_NOT_AUTHORIZED,
            "Candidate Knowledge owner-canary tools are restricted to allowlisted actors.",
            reason_codes=("owner_canary_actor_denied", actor[:64] or "missing_actor"),
        )


def build_shadow_registry(runtime: ShadowToolRuntime) -> dict[str, Callable[..., dict[str, Any]]]:
    """Return local shadow tool callables. Does not register into action_registry."""

    if not runtime.enabled:
        return {}
    return {
        name: (lambda handler=handler: (lambda **kwargs: handler(runtime, **kwargs)))()
        for name, handler in SHADOW_TOOL_HANDLERS.items()
    }


def invoke_shadow_tool(runtime: ShadowToolRuntime, tool_name: str, **kwargs: Any) -> dict[str, Any]:
    runtime.assert_shadow_enabled()
    handler = SHADOW_TOOL_HANDLERS.get(tool_name)
    if handler is None:
        raise CandidateKnowledgeError(
            ERROR_SECTION_NOT_AUTHORIZED,
            f"Unknown shadow tool {tool_name}",
        )
    # Hard guarantee: never write production registry.
    if runtime.production_registry_writes:
        raise CandidateKnowledgeError(
            ERROR_SHADOW_TOOLS_DISABLED,
            "Production registry writes are forbidden in shadow mode.",
        )
    return handler(runtime, **kwargs)


__all__ = [
    "PHASE5_VERSION",
    "ShadowToolRuntime",
    "search_candidates",
    "get_candidate_knowledge",
    "compare_candidates",
    "write_access_audit_or_fail",
    "shadow_tools_enabled",
    "owner_canary_actors",
    "assert_owner_canary_actor",
    "build_shadow_registry",
    "invoke_shadow_tool",
    "SHADOW_TOOL_HANDLERS",
]
