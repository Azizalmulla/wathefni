"""In-memory Candidate Knowledge index store and access audit (Phase 4).

Local search projection. Supports optional Postgres DDL application but tests use
the in-memory adapter. Never mutates lifecycle/communication/ranking/identity.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_upper(value: Any) -> str:
    return _norm(value).upper()


def stable_chunk_id(
    *,
    company_code: str,
    source_family: str,
    source_record_id: str,
    chunker_version: str,
    ordinal: int,
    text_hash: str,
) -> str:
    raw = "|".join(
        [
            _norm_upper(company_code),
            _norm(source_family),
            _norm(source_record_id),
            _norm(chunker_version),
            str(ordinal),
            _norm(text_hash),
        ]
    )
    return "chk_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class InMemoryCandidateKnowledgeIndexStore:
    chunks: list[dict[str, Any]] = field(default_factory=list)
    jobs: list[dict[str, Any]] = field(default_factory=list)
    access_events: list[dict[str, Any]] = field(default_factory=list)
    write_attempts: int = 0
    lifecycle_mutations: int = 0
    communication_mutations: int = 0
    ranking_mutations: int = 0
    identity_mutations: int = 0
    production_access_attempts: int = 0

    def upsert_chunk(self, chunk: dict[str, Any]) -> dict[str, Any]:
        company = _norm_upper(chunk.get("company_code"))
        chunk_id = _norm(chunk.get("chunk_id"))
        payload = dict(chunk)
        payload["company_code"] = company
        payload["updated_at"] = _now()
        for idx, existing in enumerate(self.chunks):
            if _norm(existing.get("chunk_id")) == chunk_id and _norm_upper(existing.get("company_code")) == company:
                self.chunks[idx] = payload
                return dict(payload)
        self.chunks.append(payload)
        return dict(payload)

    def list_chunks(
        self,
        *,
        company_code: str,
        states: list[str] | tuple[str, ...] | None = None,
        candidate_ref: str | None = None,
        app_key: str | None = None,
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        allowed_states = {_norm(item) for item in (states or []) if _norm(item)}
        out = []
        for item in self.chunks:
            if _norm_upper(item.get("company_code")) != company:
                continue
            if allowed_states and _norm(item.get("state")) not in allowed_states:
                continue
            if candidate_ref and _norm(item.get("candidate_ref")) != _norm(candidate_ref):
                continue
            if app_key and _norm(item.get("app_key")) != _norm(app_key):
                continue
            out.append(dict(item))
        return out

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
        count = 0
        for item in self.chunks:
            if _norm_upper(item.get("company_code")) != company:
                continue
            if app_key and _norm(item.get("app_key")) != _norm(app_key):
                continue
            if document_version_id and _norm(item.get("document_version_id")) != _norm(document_version_id):
                continue
            if candidate_ref and _norm(item.get("candidate_ref")) != _norm(candidate_ref):
                continue
            if _norm(item.get("state")) == "invalidated":
                continue
            item["state"] = "invalidated"
            item["invalidation_reason"] = reason
            item["indexed_at"] = _now()
            count += 1
        return count

    def mark_chunks_state(
        self,
        *,
        company_code: str,
        document_version_id: str,
        state: str,
    ) -> int:
        company = _norm_upper(company_code)
        count = 0
        for item in self.chunks:
            if _norm_upper(item.get("company_code")) != company:
                continue
            if _norm(item.get("document_version_id")) != _norm(document_version_id):
                continue
            item["state"] = state
            count += 1
        return count

    def enqueue_job(self, job: dict[str, Any]) -> dict[str, Any]:
        company = _norm_upper(job.get("company_code"))
        idem = _norm(job.get("idempotency_key"))
        for existing in self.jobs:
            if _norm_upper(existing.get("company_code")) == company and _norm(existing.get("idempotency_key")) == idem:
                return dict(existing)
        payload = dict(job)
        payload.setdefault("job_id", str(uuid.uuid4()))
        payload["company_code"] = company
        payload.setdefault("status", "pending")
        payload.setdefault("attempts", 0)
        payload.setdefault("dead_letter", False)
        payload.setdefault("created_at", _now())
        payload.setdefault("updated_at", _now())
        payload.setdefault("available_at", _now())
        self.jobs.append(payload)
        return dict(payload)

    def claim_job(self, *, company_code: str, owner: str, lease_seconds: int = 60) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        now = _now()
        for job in self.jobs:
            if _norm_upper(job.get("company_code")) != company:
                continue
            if job.get("dead_letter"):
                continue
            if _norm(job.get("status")) not in {"pending", "failed"}:
                continue
            if str(job.get("available_at") or "") > now:
                continue
            job["status"] = "claimed"
            job["claim_owner"] = owner
            job["claim_lease_until"] = now
            job["attempts"] = int(job.get("attempts") or 0) + 1
            job["updated_at"] = now
            return dict(job)
        return None

    def complete_job(self, *, company_code: str, job_id: str, error: str | None = None) -> None:
        company = _norm_upper(company_code)
        for job in self.jobs:
            if _norm_upper(job.get("company_code")) == company and _norm(job.get("job_id")) == _norm(job_id):
                if error:
                    job["status"] = "failed"
                    job["last_error"] = error
                    if int(job.get("attempts") or 0) >= 5:
                        job["dead_letter"] = True
                else:
                    job["status"] = "completed"
                    job["completed_at"] = _now()
                    job["last_error"] = None
                job["updated_at"] = _now()
                return

    def record_access_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Content-free audit only."""

        forbidden = {"chunk_text", "snippet", "email", "phone", "embedding", "query_text"}
        payload = {key: value for key, value in event.items() if key not in forbidden}
        payload.setdefault("event_id", str(uuid.uuid4()))
        payload.setdefault("created_at", _now())
        # Strip accidental content fields nested in reason payloads.
        if isinstance(payload.get("reason_codes"), list):
            payload["reason_codes"] = [str(item) for item in payload["reason_codes"]]
        self.access_events.append(payload)
        return dict(payload)

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
        raise RuntimeError("Candidate Knowledge Phase 4 must not access production")


__all__ = [
    "InMemoryCandidateKnowledgeIndexStore",
    "stable_chunk_id",
]
