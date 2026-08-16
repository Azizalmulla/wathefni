"""Candidate Knowledge indexer (Phase 4).

Indexes only authorized canonical sources assembled by CandidateKnowledgeAuthority.
Never indexes PII contacts, private notes, transcripts, secrets, or identity alternatives.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from candidate_knowledge_chunker import (
    CHUNKER_VERSION,
    ChunkerConfig,
    chunk_classification_labels,
    chunk_cv_text,
    chunk_structured_facts,
)
from candidate_knowledge_embeddings import (
    EMBEDDING_INDEX_VERSION,
    EmbeddingProvider,
    MockEmbeddingProvider,
    build_embedding_provider,
)
from candidate_knowledge_index_store import InMemoryCandidateKnowledgeIndexStore, stable_chunk_id
from candidate_record_state_policy import evaluate_candidate_record_state


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(\+?\d[\d\s\-()]{7,}\d)")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def redact_pii_for_index(text: str) -> str:
    cleaned = EMAIL_RE.sub("[REDACTED_EMAIL]", str(text or ""))
    cleaned = PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
    return cleaned


def versioned_source_key(
    *,
    company_code: str,
    app_key: str,
    document_version_id: str,
    source_record_id: str,
    source_content_hash: str,
    chunker_version: str,
    embedding_model: str,
    policy_version: str,
) -> str:
    raw = "|".join(
        [
            _norm(company_code).upper(),
            _norm(app_key),
            _norm(document_version_id),
            _norm(source_record_id),
            _norm(source_content_hash),
            _norm(chunker_version),
            _norm(embedding_model),
            _norm(policy_version),
        ]
    )
    return "src_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


@dataclass
class CandidateKnowledgeIndexer:
    index_store: InMemoryCandidateKnowledgeIndexStore
    embedder: EmbeddingProvider | None = None
    chunker_config: ChunkerConfig | None = None
    policy_version: str = "candidate-record-state-policy-v1"

    def __post_init__(self) -> None:
        if self.embedder is None:
            self.embedder = MockEmbeddingProvider()
        if self.chunker_config is None:
            self.chunker_config = ChunkerConfig()

    def enqueue(
        self,
        *,
        company_code: str,
        app_key: str,
        candidate_ref: str,
        document_version_id: str | None,
        reason: str,
        source_content_hash: str = "",
    ) -> dict[str, Any]:
        embedder = self.embedder or MockEmbeddingProvider()
        source_key = versioned_source_key(
            company_code=company_code,
            app_key=app_key,
            document_version_id=document_version_id or "",
            source_record_id=document_version_id or app_key,
            source_content_hash=source_content_hash or "none",
            chunker_version=self.chunker_config.version if self.chunker_config else CHUNKER_VERSION,
            embedding_model=getattr(embedder, "model", "unknown"),
            policy_version=self.policy_version,
        )
        return self.index_store.enqueue_job(
            {
                "company_code": company_code,
                "app_key": app_key,
                "candidate_ref": candidate_ref,
                "document_version_id": document_version_id,
                "source_key": source_key,
                "reason": reason,
                "idempotency_key": f"{reason}:{source_key}",
            }
        )

    def invalidate_for_identity_correction(
        self,
        *,
        company_code: str,
        old_app_key: str,
        old_candidate_ref: str | None = None,
    ) -> int:
        """Step 1–2: invalidate old-owner chunks immediately."""

        return self.index_store.invalidate_chunks(
            company_code=company_code,
            app_key=old_app_key,
            candidate_ref=old_candidate_ref,
            reason="identity_ownership_correction",
        )

    def index_from_knowledge_record(
        self,
        record: Any,
        *,
        application: dict[str, Any] | None = None,
        governance: dict[str, Any] | None = None,
        force_state: str | None = None,
    ) -> dict[str, Any]:
        """Build searchable chunks from an authorized CandidateKnowledgeRecord."""

        embedder = self.embedder or MockEmbeddingProvider()
        cfg = self.chunker_config or ChunkerConfig()
        company = _norm(getattr(record, "company_code", None) or record.get("company_code")).upper()
        candidate_ref = _norm(getattr(record, "candidate_ref", None) or record.get("candidate_ref"))
        app_key = candidate_ref.split("app:", 1)[-1] if candidate_ref.startswith("app:") else candidate_ref

        app = application if isinstance(application, dict) else {}
        decision = evaluate_candidate_record_state(app or {"status": "review_pending"}, governance=governance)
        if decision.read_projection == "denied" or "deletion_completed" in decision.governance_flags:
            invalidated = self.index_store.invalidate_chunks(company_code=company, app_key=app_key, reason="deletion_or_denied")
            return {"indexed": 0, "invalidated": invalidated, "state": "denied"}
        if "restricted" in decision.governance_flags or decision.read_projection == "metadata_only":
            # Restricted candidates: mark any existing chunks restricted and do not embed bodies.
            marked = self.index_store.mark_chunks_state(
                company_code=company,
                document_version_id=_norm((getattr(record, "canonical_cv", {}) or {}).get("version_id")),
                state="restricted",
            ) if _norm((getattr(record, "canonical_cv", {}) or {}).get("version_id")) else self.index_store.invalidate_chunks(
                company_code=company, app_key=app_key, reason="restricted"
            )
            return {"indexed": 0, "restricted": marked, "state": "restricted"}

        canonical_cv = getattr(record, "canonical_cv", None) or (record.get("canonical_cv") if isinstance(record, dict) else {}) or {}
        effective_facts = getattr(record, "effective_facts", None) or (record.get("effective_facts") if isinstance(record, dict) else {}) or {}
        classifications = getattr(record, "classifications", None) or (record.get("classifications") if isinstance(record, dict) else {}) or {}
        subject = getattr(record, "subject", None)
        display_name = None
        if subject is not None:
            display_name = getattr(subject, "display_name", None) if not isinstance(subject, dict) else subject.get("display_name")

        state = force_state or "current"
        version_id = _norm(canonical_cv.get("version_id"))
        channel = _norm(canonical_cv.get("channel") or app.get("data_source") or "unknown")
        cv_text = redact_pii_for_index(_norm(canonical_cv.get("text")))

        built = []
        if cv_text:
            built.extend(
                ("canonical_cv", version_id or app_key, chunk)
                for chunk in chunk_cv_text(cv_text, config=cfg)
            )

        facts_payload = effective_facts.get("effective") if isinstance(effective_facts.get("effective"), dict) else effective_facts
        # Never index private notes.
        safe_facts = {
            key: value
            for key, value in (facts_payload or {}).items()
            if key
            in {
                "skills",
                "employment",
                "employment_history",
                "education",
                "certifications",
                "languages",
                "projects",
                "experience_years",
            }
        }
        for chunk in chunk_structured_facts(safe_facts, config=cfg):
            built.append(("effective_facts", f"facts:{app_key}", chunk))

        for chunk in chunk_classification_labels(classifications):
            built.append(("classifications", f"class:{app_key}", chunk))

        # Authorized searchable application metadata (no contacts).
        meta_parts = []
        if app.get("position_code"):
            meta_parts.append(f"position_code:{app.get('position_code')}")
        if app.get("position_title"):
            meta_parts.append(f"position_title:{app.get('position_title')}")
        if app.get("status"):
            meta_parts.append(f"status:{app.get('status')}")
        if meta_parts:
            from candidate_knowledge_chunker import TextChunk, approximate_tokens, detect_language, text_hash

            meta_text = "\n".join(meta_parts)
            built.append(
                (
                    "application_metadata",
                    f"appmeta:{app_key}",
                    TextChunk(
                        section_type="application_metadata",
                        ordinal=0,
                        text=meta_text,
                        text_hash=text_hash(meta_text),
                        char_start=0,
                        char_end=len(meta_text),
                        token_start=0,
                        token_end=len(approximate_tokens(meta_text)),
                        language=detect_language(meta_text),
                        heading="application_metadata",
                    ),
                )
            )

        # Mark previous current chunks for this app superseded when indexing a new current version.
        if state == "current" and version_id:
            for existing in self.index_store.list_chunks(company_code=company, app_key=app_key, states=["current"]):
                old_version = _norm(existing.get("document_version_id"))
                if old_version and old_version != version_id:
                    if hasattr(self.index_store, "mark_chunks_state"):
                        self.index_store.mark_chunks_state(
                            company_code=company,
                            document_version_id=old_version,
                            state="superseded",
                        )
                    else:
                        existing["state"] = "superseded"

        texts = [item[2].text for item in built]
        vectors: list[list[float]] = []
        if texts:
            vectors = embedder.embed_documents(texts)

        indexed = 0
        for idx, (source_family, source_record_id, chunk) in enumerate(built):
            if EMAIL_RE.search(chunk.text):
                # Never embed email addresses.
                continue
            chunk_id = stable_chunk_id(
                company_code=company,
                source_family=source_family,
                source_record_id=source_record_id,
                chunker_version=cfg.version,
                ordinal=chunk.ordinal,
                text_hash=chunk.text_hash,
            )
            vector = vectors[idx] if idx < len(vectors) else None
            payload = {
                "chunk_id": chunk_id,
                "company_code": company,
                "candidate_ref": candidate_ref,
                "app_key": app_key,
                "candidate_key": _norm(app.get("phone")),
                "document_version_id": version_id or None,
                "source_channel": channel,
                "source_family": source_family,
                "source_record_id": source_record_id,
                "section_type": chunk.section_type,
                "chunk_ordinal": chunk.ordinal,
                "chunk_text": chunk.text,
                "text_hash": chunk.text_hash,
                "language": chunk.language,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "token_start": chunk.token_start,
                "token_end": chunk.token_end,
                "evidence_refs": [
                    {
                        "source_family": source_family,
                        "source_record_id": source_record_id,
                        "document_version_id": version_id or None,
                    }
                ],
                "state": state,
                "chunker_version": cfg.version,
                "embedding_provider": getattr(embedder, "provider", None),
                "embedding_model": getattr(embedder, "model", None),
                "embedding_dimensions": getattr(embedder, "dimensions", None),
                "embedding_index_version": EMBEDDING_INDEX_VERSION,
                "embedding": vector,
                "display_name": display_name,
                "searchable_metadata": {
                    "position_code": app.get("position_code"),
                    "status": app.get("status"),
                    "source_channel": channel,
                    "held_state": decision.held_state,
                    "lifecycle_status": app.get("status"),
                    "hr_confirmed_labels": [
                        item.get("node_id") or item.get("label")
                        for item in (classifications.get("hr_confirmed") or [])
                        if isinstance(item, dict)
                    ],
                    "ai_suggested_labels": [
                        item.get("node_id") or item.get("label")
                        for item in (classifications.get("ai_suggested") or [])
                        if isinstance(item, dict)
                    ],
                },
                "created_at": _now(),
                "indexed_at": _now(),
                "actionability": decision.to_actionability(),
            }
            self.index_store.upsert_chunk(payload)
            indexed += 1

        self.enqueue(
            company_code=company,
            app_key=app_key,
            candidate_ref=candidate_ref,
            document_version_id=version_id or None,
            reason="indexed",
            source_content_hash=_norm(canonical_cv.get("content_hash") or canonical_cv.get("extracted_text_hash")),
        )
        return {
            "indexed": indexed,
            "state": state,
            "document_version_id": version_id or None,
            "chunker_version": cfg.version,
            "embedding_model": getattr(embedder, "model", None),
        }

    def process_identity_correction(
        self,
        *,
        company_code: str,
        old_app_key: str,
        new_record: Any,
        new_application: dict[str, Any],
        governance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Identity correction order: invalidate old → index new → restore visibility."""

        invalidated = self.invalidate_for_identity_correction(
            company_code=company_code,
            old_app_key=old_app_key,
        )
        # Search excludes invalidated immediately (no wait for reindex).
        indexed = self.index_from_knowledge_record(
            new_record,
            application=new_application,
            governance=governance,
            force_state="current",
        )
        return {"invalidated": invalidated, "indexed": indexed}


__all__ = [
    "CandidateKnowledgeIndexer",
    "redact_pii_for_index",
    "versioned_source_key",
]
