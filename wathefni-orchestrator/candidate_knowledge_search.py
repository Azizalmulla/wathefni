"""Hybrid Candidate Knowledge search (Phase 4).

Combines structured filters, lexical retrieval, vector nearest-neighbor, and
classification filters with reciprocal-rank fusion and candidate-level aggregation.
"""

from __future__ import annotations

import base64
import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from candidate_knowledge_embeddings import (
    QueryEmbeddingCache,
    cosine_similarity,
    build_embedding_provider,
)
from candidate_knowledge_errors import (
    ERROR_BACKEND_CURRENT_REQUIRED,
    ERROR_INDEX_NOT_READY,
    ERROR_PERMISSION_DENIED,
    ERROR_RETRIEVAL_DEGRADED,
    ERROR_TENANT_SCOPE_REQUIRED,
    CandidateKnowledgeError,
)
from candidate_knowledge_index_store import InMemoryCandidateKnowledgeIndexStore
from candidate_record_state_policy import (
    FINALIZED_STATUSES,
    INTAKE_HOLD_STATUSES,
    LIVE_PIPELINE_STATUSES,
)


RetrievalMode = Literal[
    "hybrid",
    "lexical_only",
    "structured_only",
    "index_not_ready",
    "retrieval_degraded",
]

SearchScope = Literal["talent_pool", "active_applications", "all_authorized"]

REQUIRED_PERMISSION = "prehire.read"
REQUIRED_PERMISSION_AUTHORITY = "backend_current"


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_upper(value: Any) -> str:
    return _norm(value).upper()


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[str]],
    *,
    k: int = 60,
) -> dict[str, float]:
    scores: dict[str, float] = {}
    for _channel, ordered_ids in ranked_lists.items():
        for rank, item_id in enumerate(ordered_ids, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def _tokenize(text: str) -> set[str]:
    return {part.lower() for part in re.split(r"[^\w\u0600-\u06FF]+", text or "") if part}


def _encode_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {"offset": 0}
    try:
        raw = base64.urlsafe_b64decode(str(cursor).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return {"offset": 0}
        return payload
    except Exception:
        return {"offset": 0}


def scope_allows_chunk(scope: SearchScope, chunk: dict[str, Any], *, include_finalized: bool, include_archived: bool) -> bool:
    meta = chunk.get("searchable_metadata") if isinstance(chunk.get("searchable_metadata"), dict) else {}
    status = _norm(meta.get("lifecycle_status") or meta.get("status")).lower()
    held = _norm(meta.get("held_state")).lower()
    actionability = chunk.get("actionability") if isinstance(chunk.get("actionability"), dict) else {}

    if _norm(chunk.get("state")) != "current":
        return False

    if status == "import_archived" and not include_archived:
        return False
    if status in FINALIZED_STATUSES and not include_finalized:
        if scope != "all_authorized":
            return False

    if scope == "talent_pool":
        # Held Talent Pool candidates may be searchable when authorized.
        return status in INTAKE_HOLD_STATUSES or held in INTAKE_HOLD_STATUSES or status == "needs_role" or status == "import_review"
    if scope == "active_applications":
        return status in LIVE_PIPELINE_STATUSES and status not in INTAKE_HOLD_STATUSES
    # all_authorized
    return True


@dataclass
class CandidateKnowledgeSearchService:
    index_store: InMemoryCandidateKnowledgeIndexStore
    embedder: Any = None
    query_cache: QueryEmbeddingCache = field(default_factory=QueryEmbeddingCache)
    force_lexical_only: bool = False

    def __post_init__(self) -> None:
        if self.embedder is None:
            self.embedder = build_embedding_provider(force_mock=True)

    def search(
        self,
        *,
        company_code: str,
        actor_user_id: str,
        permission_authority: str,
        permissions: list[str] | tuple[str, ...],
        query: str,
        scope: SearchScope = "talent_pool",
        filters: dict[str, Any] | None = None,
        limit: int = 20,
        cursor: str | None = None,
        oversample: int = 5,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        company = _norm_upper(company_code)
        if not company:
            raise CandidateKnowledgeError(ERROR_TENANT_SCOPE_REQUIRED, "company_code required")
        if permission_authority != REQUIRED_PERMISSION_AUTHORITY:
            raise CandidateKnowledgeError(ERROR_BACKEND_CURRENT_REQUIRED, "backend_current required")
        if REQUIRED_PERMISSION not in {_norm(item) for item in permissions}:
            raise CandidateKnowledgeError(ERROR_PERMISSION_DENIED, "prehire.read required")

        filt = filters if isinstance(filters, dict) else {}
        include_finalized = bool(filt.get("include_finalized"))
        include_archived = bool(filt.get("include_archived"))
        status_filter = {
            _norm(item).lower()
            for item in (filt.get("status") or filt.get("statuses") or [])
            if _norm(item)
        }
        skill_filter = {_norm(item).lower() for item in (filt.get("skills") or []) if _norm(item)}
        channel_filter = {_norm(item).lower() for item in (filt.get("source_channels") or []) if _norm(item)}
        class_filter = {_norm(item) for item in (filt.get("classification_node_ids") or []) if _norm(item)}
        language_filter = {_norm(item).lower() for item in (filt.get("languages") or []) if _norm(item)}
        page_limit = max(1, min(int(limit or 20), 100))
        cursor_payload = _decode_cursor(cursor)
        offset = max(0, int(cursor_payload.get("offset") or 0))

        chunks = self.index_store.list_chunks(company_code=company, states=["current"])
        if not chunks:
            self.index_store.record_access_event(
                {
                    "company_code": company,
                    "actor_user_id": actor_user_id,
                    "operation": "search",
                    "scope": scope,
                    "retrieval_mode": "index_not_ready",
                    "result_count": 0,
                    "reason_codes": [ERROR_INDEX_NOT_READY],
                }
            )
            return {
                "ok": True,
                "items": [],
                "next_cursor": None,
                "retrieval_mode": "index_not_ready",
                "index_freshness": {"chunk_count": 0},
                "scanned_entire_pool": True,
                "total": 0,
                "match_reasons_legend": {},
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }

        # Structured prefilter.
        structured_hits: list[dict[str, Any]] = []
        for chunk in chunks:
            if not scope_allows_chunk(scope, chunk, include_finalized=include_finalized, include_archived=include_archived):
                continue
            meta = chunk.get("searchable_metadata") if isinstance(chunk.get("searchable_metadata"), dict) else {}
            status = _norm(meta.get("lifecycle_status") or meta.get("status")).lower()
            if status_filter and status not in status_filter:
                continue
            channel = _norm(chunk.get("source_channel") or meta.get("source_channel")).lower()
            if channel_filter and channel not in channel_filter:
                continue
            labels = {
                _norm(item)
                for item in (meta.get("hr_confirmed_labels") or []) + (meta.get("ai_suggested_labels") or [])
                if _norm(item)
            }
            if class_filter and not (labels & class_filter):
                continue
            if skill_filter:
                text_l = _norm(chunk.get("chunk_text")).lower()
                if not any(skill in text_l for skill in skill_filter):
                    continue
            if language_filter:
                lang = _norm(chunk.get("language")).lower()
                text_l = _norm(chunk.get("chunk_text")).lower()
                if not any(item in lang or item in text_l for item in language_filter):
                    continue
            structured_hits.append(chunk)

        if not query.strip() and (status_filter or skill_filter or channel_filter or class_filter or language_filter):
            retrieval_mode: RetrievalMode = "structured_only"
        else:
            retrieval_mode = "hybrid"

        query_tokens = _tokenize(query)
        lexical_scores: dict[str, float] = {}
        for chunk in structured_hits:
            text_tokens = _tokenize(_norm(chunk.get("chunk_text")))
            overlap = len(query_tokens & text_tokens) if query_tokens else 0
            if overlap or not query_tokens:
                # Structured-only path ranks all structured hits equally by candidate_ref tie-break later.
                score = float(overlap) / float(max(1, len(query_tokens))) if query_tokens else 1.0
                lexical_scores[chunk["chunk_id"]] = score

        semantic_scores: dict[str, float] = {}
        embedding_error = None
        semantic_top_n = 100
        semantic_min_score = 0.2
        if retrieval_mode == "hybrid" and query_tokens and not self.force_lexical_only:
            try:
                cached = self.query_cache.get(
                    company_code=company,
                    model=getattr(self.embedder, "model", "unknown"),
                    query=query,
                    policy_scope=scope,
                )
                if cached is None:
                    cached = self.embedder.embed_query(query)
                    self.query_cache.put(
                        company_code=company,
                        model=getattr(self.embedder, "model", "unknown"),
                        query=query,
                        policy_scope=scope,
                        vector=cached,
                    )
                scored: list[tuple[str, float]] = []
                for chunk in structured_hits:
                    vector = chunk.get("embedding")
                    if not isinstance(vector, list) or not vector:
                        continue
                    score = cosine_similarity(cached, vector)
                    if score >= semantic_min_score:
                        scored.append((chunk["chunk_id"], score))
                scored.sort(key=lambda item: (-item[1], item[0]))
                for chunk_id, score in scored[:semantic_top_n]:
                    semantic_scores[chunk_id] = score
            except Exception as exc:
                embedding_error = str(exc)
                retrieval_mode = "retrieval_degraded"

        if retrieval_mode == "hybrid" and not semantic_scores and query_tokens:
            retrieval_mode = "lexical_only" if lexical_scores else "structured_only"
        if self.force_lexical_only and query_tokens:
            retrieval_mode = "lexical_only"
            semantic_scores = {}

        # Rank channels for RRF (candidate-level via best chunk later).
        def _sorted_ids(score_map: dict[str, float]) -> list[str]:
            return [
                chunk_id
                for chunk_id, _score in sorted(
                    score_map.items(),
                    key=lambda item: (-item[1], item[0]),
                )
                if _score > 0 or retrieval_mode == "structured_only"
            ]

        ranked_lists: dict[str, list[str]] = {}
        if lexical_scores:
            ranked_lists["lexical"] = _sorted_ids(lexical_scores)
        if semantic_scores:
            ranked_lists["semantic"] = _sorted_ids(semantic_scores)
        if not ranked_lists:
            ranked_lists["structured"] = [chunk["chunk_id"] for chunk in structured_hits]

        fused = reciprocal_rank_fusion(ranked_lists)
        chunk_by_id = {chunk["chunk_id"]: chunk for chunk in structured_hits}

        # Candidate-level aggregation: one result per candidate_ref using best fused chunk.
        best_by_candidate: dict[str, tuple[float, dict[str, Any], list[dict[str, Any]]]] = {}
        for chunk_id, score in fused.items():
            chunk = chunk_by_id.get(chunk_id)
            if not chunk:
                continue
            candidate_ref = _norm(chunk.get("candidate_ref"))
            current = best_by_candidate.get(candidate_ref)
            match_chunk = {
                "chunk_id": chunk_id,
                "section_type": chunk.get("section_type"),
                "snippet": _snippet(chunk.get("chunk_text"), query),
                "document_version_id": chunk.get("document_version_id"),
                "source_family": chunk.get("source_family"),
                "evidence_refs": chunk.get("evidence_refs") or [],
                "language": chunk.get("language"),
            }
            if current is None:
                best_by_candidate[candidate_ref] = (score, chunk, [match_chunk])
            else:
                best_score, best_chunk, matches = current
                matches.append(match_chunk)
                # Cap per-candidate match fanout so long CVs cannot dominate listing.
                matches = sorted(matches, key=lambda item: item["chunk_id"])[:3]
                if score > best_score or (math.isclose(score, best_score) and chunk_id < best_chunk["chunk_id"]):
                    best_by_candidate[candidate_ref] = (score, chunk, matches)
                else:
                    best_by_candidate[candidate_ref] = (best_score, best_chunk, matches)

        ordered_candidates = sorted(
            best_by_candidate.items(),
            key=lambda item: (-item[1][0], item[0]),
        )
        total = len(ordered_candidates)
        # Oversample then slice for stable pagination.
        window = ordered_candidates[offset : offset + page_limit * max(1, oversample)]
        page = window[:page_limit]

        items = []
        for candidate_ref, (score, chunk, matches) in page:
            meta = chunk.get("searchable_metadata") if isinstance(chunk.get("searchable_metadata"), dict) else {}
            actionability = chunk.get("actionability") if isinstance(chunk.get("actionability"), dict) else {}
            reasons = []
            if chunk["chunk_id"] in lexical_scores and lexical_scores[chunk["chunk_id"]] > 0:
                reasons.append("lexical_match")
            if chunk["chunk_id"] in semantic_scores and semantic_scores[chunk["chunk_id"]] > 0:
                reasons.append("semantic_match")
            if status_filter or skill_filter or channel_filter:
                reasons.append("structured_match")
            hr_labels = meta.get("hr_confirmed_labels") or []
            ai_labels = meta.get("ai_suggested_labels") or []
            if class_filter and ({_norm(x) for x in hr_labels + ai_labels} & class_filter):
                reasons.append("classification_match")
            if not reasons:
                reasons.append("structured_match")

            items.append(
                {
                    "candidate_ref": candidate_ref,
                    "display_name": chunk.get("display_name"),
                    "app_key": chunk.get("app_key"),
                    "held_state": meta.get("held_state"),
                    "lifecycle_status": meta.get("lifecycle_status") or meta.get("status"),
                    "classifications": {
                        "hr_confirmed": hr_labels,
                        "ai_suggested": ai_labels,
                    },
                    "matching_sections": matches,
                    "search_relevance": {
                        "score": round(score, 6),
                        "label": "search_relevance_not_hiring_score",
                        "components": {
                            "lexical": round(lexical_scores.get(chunk["chunk_id"], 0.0), 6),
                            "semantic": round(semantic_scores.get(chunk["chunk_id"], 0.0), 6),
                        },
                    },
                    "match_reasons": reasons,
                    "coverage": {
                        "indexed_sections": sorted({item.get("section_type") for item in matches}),
                        "index_state": chunk.get("state"),
                    },
                    "actionability": {
                        "readable": actionability.get("readable", True),
                        "contact_allowed": actionability.get("contact_allowed", False),
                        "lifecycle_mutation_allowed": actionability.get("lifecycle_mutation_allowed", False),
                        "job_ranking_allowed": actionability.get("job_ranking_allowed", False),
                        "held_state": actionability.get("held_state") or meta.get("held_state"),
                    },
                    "index_version": {
                        "chunker_version": chunk.get("chunker_version"),
                        "embedding_model": chunk.get("embedding_model"),
                        "embedding_index_version": chunk.get("embedding_index_version"),
                        "document_version_id": chunk.get("document_version_id"),
                    },
                }
            )

        next_offset = offset + len(items)
        next_cursor = _encode_cursor({"offset": next_offset, "scope": scope, "query": query}) if next_offset < total else None

        mode = retrieval_mode
        if embedding_error and mode == "retrieval_degraded":
            # Disclosed degradation — lexical results may still be present.
            pass

        self.index_store.record_access_event(
            {
                "company_code": company,
                "actor_user_id": actor_user_id,
                "operation": "search",
                "scope": scope,
                "retrieval_mode": mode,
                "result_count": len(items),
                "reason_codes": [mode] + ([ERROR_RETRIEVAL_DEGRADED] if embedding_error else []),
            }
        )

        return {
            "ok": True,
            "items": items,
            "next_cursor": next_cursor,
            "retrieval_mode": mode,
            "embedding": {
                "provider": getattr(self.embedder, "provider", None),
                "model": getattr(self.embedder, "model", None),
                "used": mode == "hybrid",
                "error": embedding_error,
            },
            "index_freshness": {
                "chunk_count": len(chunks),
                "eligible_chunk_count": len(structured_hits),
                "candidate_count": total,
            },
            "scanned_entire_pool": True,
            "total": total,
            "limit": page_limit,
            "offset": offset,
            "match_reasons_legend": {
                "structured_match": "Matched exact filters",
                "lexical_match": "Matched CV/fact lexical tokens",
                "semantic_match": "Matched vector similarity (search relevance, not hiring score)",
                "classification_match": "Matched classification labels",
            },
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "name_merge_forbidden": True,
        }


def _snippet(text: Any, query: str, *, radius: int = 80) -> str:
    body = _norm(text)
    if not body:
        return ""
    tokens = [token for token in _tokenize(query) if token]
    lower = body.lower()
    idx = -1
    for token in tokens:
        idx = lower.find(token)
        if idx >= 0:
            break
    if idx < 0:
        return body[: min(len(body), radius * 2)]
    start = max(0, idx - radius)
    end = min(len(body), idx + radius)
    return body[start:end]


__all__ = [
    "CandidateKnowledgeSearchService",
    "reciprocal_rank_fusion",
    "scope_allows_chunk",
    "RetrievalMode",
    "SearchScope",
]
