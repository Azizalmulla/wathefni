"""Postgres Candidate Knowledge index store (staging/production projection).

Additive search projection only. Never mutates lifecycle/communication/ranking/
identity or production. All SQL is company_code-scoped.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from candidate_knowledge_index_schema import PHASE4_LOCAL_SCHEMA_DDL
from candidate_knowledge_index_store import stable_chunk_id


CursorFactory = Callable[[], Any]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_upper(value: Any) -> str:
    return _norm(value).upper()


def _vec_literal(vector: list[float] | None) -> str | None:
    if not vector:
        return None
    return "[" + ",".join(f"{float(v):.8f}" for v in vector) + "]"


@dataclass
class PostgresCandidateKnowledgeIndexStore:
    connect: CursorFactory
    access_events: list[dict[str, Any]] = field(default_factory=list)
    write_attempts: int = 0
    lifecycle_mutations: int = 0
    communication_mutations: int = 0
    ranking_mutations: int = 0
    identity_mutations: int = 0
    production_access_attempts: int = 0

    def ensure_schema(self) -> None:
        with self.connect() as cur:
            cur.execute(PHASE4_LOCAL_SCHEMA_DDL)

    def upsert_chunk(self, chunk: dict[str, Any]) -> dict[str, Any]:
        company = _norm_upper(chunk.get("company_code"))
        chunk_id = _norm(chunk.get("chunk_id")) or stable_chunk_id(
            company_code=company,
            source_family=_norm(chunk.get("source_family")),
            source_record_id=_norm(chunk.get("source_record_id")),
            chunker_version=_norm(chunk.get("chunker_version")) or "ck-chunker-v1",
            ordinal=int(chunk.get("chunk_ordinal") or 0),
            text_hash=_norm(chunk.get("text_hash")),
        )
        embedding = chunk.get("embedding")
        vec = _vec_literal(embedding if isinstance(embedding, list) else None)
        meta = chunk.get("searchable_metadata") if isinstance(chunk.get("searchable_metadata"), dict) else {}
        refs = chunk.get("evidence_refs") if isinstance(chunk.get("evidence_refs"), list) else []
        with self.connect() as cur:
            if vec is None:
                cur.execute(
                    """
                    INSERT INTO candidate_knowledge_chunks (
                      chunk_id, company_code, candidate_ref, app_key, candidate_key,
                      document_version_id, source_channel, source_family, source_record_id,
                      section_type, chunk_ordinal, chunk_text, text_hash, language,
                      char_start, char_end, token_start, token_end, evidence_refs,
                      state, chunker_version, embedding_provider, embedding_model,
                      embedding_dimensions, embedding_index_version, embedding,
                      display_name, searchable_metadata, indexed_at
                    ) VALUES (
                      %s,%s,%s,%s,%s,
                      %s,%s,%s,%s,
                      %s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s::jsonb,
                      %s,%s,%s,%s,
                      %s,%s,NULL,
                      %s,%s::jsonb, now()
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      chunk_text = EXCLUDED.chunk_text,
                      state = EXCLUDED.state,
                      searchable_metadata = EXCLUDED.searchable_metadata,
                      embedding = NULL,
                      embedding_provider = EXCLUDED.embedding_provider,
                      embedding_model = EXCLUDED.embedding_model,
                      embedding_dimensions = EXCLUDED.embedding_dimensions,
                      embedding_index_version = EXCLUDED.embedding_index_version,
                      indexed_at = now()
                    """,
                    (
                        chunk_id,
                        company,
                        _norm(chunk.get("candidate_ref")),
                        _norm(chunk.get("app_key")),
                        _norm(chunk.get("candidate_key")) or None,
                        _norm(chunk.get("document_version_id")) or None,
                        _norm(chunk.get("source_channel")) or None,
                        _norm(chunk.get("source_family")),
                        _norm(chunk.get("source_record_id")),
                        _norm(chunk.get("section_type")),
                        int(chunk.get("chunk_ordinal") or 0),
                        _norm(chunk.get("chunk_text")),
                        _norm(chunk.get("text_hash")),
                        _norm(chunk.get("language")) or None,
                        chunk.get("char_start"),
                        chunk.get("char_end"),
                        chunk.get("token_start"),
                        chunk.get("token_end"),
                        json.dumps(refs),
                        _norm(chunk.get("state")) or "current",
                        _norm(chunk.get("chunker_version")) or "ck-chunker-v1",
                        _norm(chunk.get("embedding_provider")) or None,
                        _norm(chunk.get("embedding_model")) or None,
                        chunk.get("embedding_dimensions"),
                        _norm(chunk.get("embedding_index_version")) or None,
                        _norm(chunk.get("display_name")) or None,
                        json.dumps(meta),
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO candidate_knowledge_chunks (
                      chunk_id, company_code, candidate_ref, app_key, candidate_key,
                      document_version_id, source_channel, source_family, source_record_id,
                      section_type, chunk_ordinal, chunk_text, text_hash, language,
                      char_start, char_end, token_start, token_end, evidence_refs,
                      state, chunker_version, embedding_provider, embedding_model,
                      embedding_dimensions, embedding_index_version, embedding,
                      display_name, searchable_metadata, indexed_at
                    ) VALUES (
                      %s,%s,%s,%s,%s,
                      %s,%s,%s,%s,
                      %s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s::jsonb,
                      %s,%s,%s,%s,
                      %s,%s,%s::vector,
                      %s,%s::jsonb, now()
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      chunk_text = EXCLUDED.chunk_text,
                      state = EXCLUDED.state,
                      embedding = EXCLUDED.embedding,
                      embedding_provider = EXCLUDED.embedding_provider,
                      embedding_model = EXCLUDED.embedding_model,
                      embedding_dimensions = EXCLUDED.embedding_dimensions,
                      embedding_index_version = EXCLUDED.embedding_index_version,
                      searchable_metadata = EXCLUDED.searchable_metadata,
                      indexed_at = now()
                    """,
                    (
                        chunk_id,
                        company,
                        _norm(chunk.get("candidate_ref")),
                        _norm(chunk.get("app_key")),
                        _norm(chunk.get("candidate_key")) or None,
                        _norm(chunk.get("document_version_id")) or None,
                        _norm(chunk.get("source_channel")) or None,
                        _norm(chunk.get("source_family")),
                        _norm(chunk.get("source_record_id")),
                        _norm(chunk.get("section_type")),
                        int(chunk.get("chunk_ordinal") or 0),
                        _norm(chunk.get("chunk_text")),
                        _norm(chunk.get("text_hash")),
                        _norm(chunk.get("language")) or None,
                        chunk.get("char_start"),
                        chunk.get("char_end"),
                        chunk.get("token_start"),
                        chunk.get("token_end"),
                        json.dumps(refs),
                        _norm(chunk.get("state")) or "current",
                        _norm(chunk.get("chunker_version")) or "ck-chunker-v1",
                        _norm(chunk.get("embedding_provider")) or None,
                        _norm(chunk.get("embedding_model")) or None,
                        chunk.get("embedding_dimensions"),
                        _norm(chunk.get("embedding_index_version")) or None,
                        vec,
                        _norm(chunk.get("display_name")) or None,
                        json.dumps(meta),
                    ),
                )
        payload = dict(chunk)
        payload["chunk_id"] = chunk_id
        payload["company_code"] = company
        return payload

    def list_chunks(
        self,
        *,
        company_code: str,
        states: list[str] | tuple[str, ...] | None = None,
        candidate_ref: str | None = None,
        app_key: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        clauses = ["company_code = %s"]
        params: list[Any] = [company]
        if states:
            clauses.append("state = ANY(%s)")
            params.append(list(states))
        if candidate_ref:
            clauses.append("candidate_ref = %s")
            params.append(_norm(candidate_ref))
        if app_key:
            clauses.append("app_key = %s")
            params.append(_norm(app_key))
        sql = f"""
            SELECT chunk_id, company_code, candidate_ref, app_key, candidate_key,
                   document_version_id, source_channel, source_family, source_record_id,
                   section_type, chunk_ordinal, chunk_text, text_hash, language,
                   char_start, char_end, token_start, token_end, evidence_refs,
                   state, chunker_version, embedding_provider, embedding_model,
                   embedding_dimensions, embedding_index_version,
                   CASE WHEN embedding IS NULL THEN NULL ELSE embedding::text END AS embedding,
                   display_name, searchable_metadata, indexed_at
            FROM candidate_knowledge_chunks
            WHERE {' AND '.join(clauses)}
            ORDER BY app_key, chunk_ordinal
        """
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        with self.connect() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        out = []
        for row in rows:
            item = dict(row)
            emb = item.get("embedding")
            if isinstance(emb, str) and emb.startswith("["):
                try:
                    item["embedding"] = [float(x) for x in emb.strip("[]").split(",") if x.strip()]
                except Exception:
                    item["embedding"] = None
            if isinstance(item.get("evidence_refs"), str):
                item["evidence_refs"] = json.loads(item["evidence_refs"])
            if isinstance(item.get("searchable_metadata"), str):
                item["searchable_metadata"] = json.loads(item["searchable_metadata"])
            out.append(item)
        return out

    def lexical_search(
        self,
        *,
        company_code: str,
        query: str,
        limit: int = 20,
        states: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        states = states or ["current"]
        with self.connect() as cur:
            cur.execute(
                """
                SELECT candidate_ref, app_key, company_code, chunk_id, chunk_text, state,
                       ts_rank(
                         to_tsvector('simple', coalesce(chunk_text, '')),
                         plainto_tsquery('simple', %s)
                       ) AS rank
                FROM candidate_knowledge_chunks
                WHERE company_code = %s
                  AND state = ANY(%s)
                  AND to_tsvector('simple', coalesce(chunk_text, ''))
                      @@ plainto_tsquery('simple', %s)
                ORDER BY rank DESC, candidate_ref
                LIMIT %s
                """,
                (query, company, states, query, int(limit)),
            )
            return [dict(row) for row in cur.fetchall()]

    def invalidate_chunks(
        self,
        *,
        company_code: str,
        app_key: str | None = None,
        document_version_id: str | None = None,
        candidate_ref: str | None = None,
        reason: str = "invalidated",
    ) -> int:
        company = _norm_upper(company_code)
        clauses = ["company_code = %s", "state <> 'invalidated'"]
        params: list[Any] = [company]
        if app_key:
            clauses.append("app_key = %s")
            params.append(_norm(app_key))
        if document_version_id:
            clauses.append("document_version_id = %s")
            params.append(_norm(document_version_id))
        if candidate_ref:
            clauses.append("candidate_ref = %s")
            params.append(_norm(candidate_ref))
        with self.connect() as cur:
            cur.execute(
                f"""
                UPDATE candidate_knowledge_chunks
                SET state = 'invalidated', indexed_at = now()
                WHERE {' AND '.join(clauses)}
                """,
                params,
            )
            return int(cur.rowcount or 0)

    def mark_chunks_state(
        self,
        *,
        company_code: str,
        document_version_id: str,
        state: str,
    ) -> int:
        with self.connect() as cur:
            cur.execute(
                """
                UPDATE candidate_knowledge_chunks
                SET state = %s, indexed_at = now()
                WHERE company_code = %s AND document_version_id = %s
                """,
                (_norm(state), _norm_upper(company_code), _norm(document_version_id)),
            )
            return int(cur.rowcount or 0)

    def enqueue_job(self, job: dict[str, Any]) -> dict[str, Any]:
        company = _norm_upper(job.get("company_code"))
        idem = _norm(job.get("idempotency_key"))
        with self.connect() as cur:
            cur.execute(
                """
                SELECT * FROM candidate_knowledge_index_jobs
                WHERE company_code = %s AND idempotency_key = %s
                """,
                (company, idem),
            )
            existing = cur.fetchone()
            if existing:
                return dict(existing)
            job_id = _norm(job.get("job_id")) or str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO candidate_knowledge_index_jobs (
                  job_id, company_code, app_key, candidate_ref, document_version_id,
                  source_key, reason, idempotency_key, status, attempts, dead_letter
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,'pending',0,false
                )
                RETURNING *
                """,
                (
                    job_id,
                    company,
                    _norm(job.get("app_key")),
                    _norm(job.get("candidate_ref")) or None,
                    _norm(job.get("document_version_id")) or None,
                    _norm(job.get("source_key")),
                    _norm(job.get("reason")) or "index",
                    idem,
                ),
            )
            return dict(cur.fetchone())

    def claim_job(self, *, company_code: str, owner: str, lease_seconds: int = 60) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        with self.connect() as cur:
            cur.execute(
                """
                UPDATE candidate_knowledge_index_jobs
                SET status = 'claimed',
                    claim_owner = %s,
                    claim_lease_until = now() + (%s || ' seconds')::interval,
                    attempts = attempts + 1,
                    updated_at = now()
                WHERE job_id = (
                  SELECT job_id FROM candidate_knowledge_index_jobs
                  WHERE company_code = %s
                    AND dead_letter = false
                    AND status IN ('pending', 'failed')
                    AND available_at <= now()
                  ORDER BY available_at
                  FOR UPDATE SKIP LOCKED
                  LIMIT 1
                )
                RETURNING *
                """,
                (owner, str(int(lease_seconds)), company),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def complete_job(self, *, company_code: str, job_id: str, error: str | None = None) -> None:
        with self.connect() as cur:
            if error:
                cur.execute(
                    """
                    UPDATE candidate_knowledge_index_jobs
                    SET status = 'failed',
                        last_error = %s,
                        dead_letter = CASE WHEN attempts >= 5 THEN true ELSE dead_letter END,
                        updated_at = now()
                    WHERE company_code = %s AND job_id = %s::uuid
                    """,
                    (error[:2000], _norm_upper(company_code), job_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE candidate_knowledge_index_jobs
                    SET status = 'completed',
                        last_error = NULL,
                        completed_at = now(),
                        updated_at = now()
                    WHERE company_code = %s AND job_id = %s::uuid
                    """,
                    (_norm_upper(company_code), job_id),
                )

    def record_access_event(self, event: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"chunk_text", "snippet", "email", "phone", "embedding", "query_text", "cv_text"}
        payload = {key: value for key, value in event.items() if key not in forbidden}
        event_id = _norm(payload.get("event_id")) or str(uuid.uuid4())
        reason_codes = payload.get("reason_codes") if isinstance(payload.get("reason_codes"), list) else []
        with self.connect() as cur:
            cur.execute(
                """
                INSERT INTO candidate_knowledge_access_events (
                  event_id, company_code, actor_user_id, request_id, operation,
                  scope, candidate_ref, retrieval_mode, result_count, reason_codes
                ) VALUES (
                  %s::uuid, %s, %s, %s, %s,
                  %s, %s, %s, %s, %s::jsonb
                )
                RETURNING event_id::text AS event_id, company_code, actor_user_id, operation, reason_codes
                """,
                (
                    event_id,
                    _norm_upper(payload.get("company_code")),
                    _norm(payload.get("actor_user_id")),
                    _norm(payload.get("request_id")) or None,
                    _norm(payload.get("operation")) or "unknown",
                    _norm(payload.get("scope")) or None,
                    _norm(payload.get("candidate_ref")) or None,
                    _norm(payload.get("retrieval_mode")) or None,
                    payload.get("result_count"),
                    json.dumps([str(x) for x in reason_codes]),
                ),
            )
            written = dict(cur.fetchone())
        self.access_events.append(written)
        return written

    def count_chunks(self, *, company_code: str, state: str = "current") -> int:
        with self.connect() as cur:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM candidate_knowledge_chunks
                WHERE company_code = %s AND state = %s
                """,
                (_norm_upper(company_code), state),
            )
            return int(cur.fetchone()["n"])

    def mutate_lifecycle(self, *_args: Any, **_kwargs: Any) -> None:
        self.lifecycle_mutations += 1
        self.write_attempts += 1
        raise RuntimeError("Candidate Knowledge index must not mutate lifecycle")

    def mutate_communication(self, *_args: Any, **_kwargs: Any) -> None:
        self.communication_mutations += 1
        self.write_attempts += 1
        raise RuntimeError("Candidate Knowledge index must not mutate communication")

    def mutate_ranking(self, *_args: Any, **_kwargs: Any) -> None:
        self.ranking_mutations += 1
        self.write_attempts += 1
        raise RuntimeError("Candidate Knowledge index must not mutate ranking")

    def mutate_identity(self, *_args: Any, **_kwargs: Any) -> None:
        self.identity_mutations += 1
        self.write_attempts += 1
        raise RuntimeError("Candidate Knowledge index must not mutate identity")

    def access_production(self, *_args: Any, **_kwargs: Any) -> None:
        self.production_access_attempts += 1
        raise RuntimeError("Candidate Knowledge must not access production")


__all__ = ["PostgresCandidateKnowledgeIndexStore"]
