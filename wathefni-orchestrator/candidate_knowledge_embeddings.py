"""Voyage and deterministic mock embedding providers for Candidate Knowledge Phase 4.

Local-only. No silent model switching. Provider failure must degrade explicitly.
"""

from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol


DOCUMENT_MODEL = "voyage-4-large"
QUERY_MODEL = "voyage-4-large"
DEFAULT_DIMENSIONS = 1024
EMBEDDING_INDEX_VERSION = "ck-embed-v1"
PROVIDER_VOYAGE = "voyage"
PROVIDER_MOCK = "mock"


class EmbeddingProvider(Protocol):
    provider: str
    model: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def deterministic_mock_embedding(text: str, *, dimensions: int = DEFAULT_DIMENSIONS) -> list[float]:
    """Stable hash embedding for unit tests (not semantically meaningful)."""

    digest = hashlib.sha256(str(text or "").encode("utf-8")).digest()
    values: list[float] = []
    seed = digest
    while len(values) < dimensions:
        for byte in seed:
            values.append(((byte / 255.0) * 2.0) - 1.0)
            if len(values) >= dimensions:
                break
        seed = hashlib.sha256(seed).digest()
    return _l2_normalize(values[:dimensions])


@dataclass
class MockEmbeddingProvider:
    provider: str = PROVIDER_MOCK
    model: str = "mock-ck-embed-v1"
    dimensions: int = DEFAULT_DIMENSIONS
    document_calls: int = 0
    query_calls: int = 0
    fail: bool = False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("mock_embedding_provider_failed")
        self.document_calls += 1
        return [deterministic_mock_embedding(text, dimensions=self.dimensions) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        if self.fail:
            raise RuntimeError("mock_embedding_provider_failed")
        self.query_calls += 1
        return deterministic_mock_embedding(text, dimensions=self.dimensions)


@dataclass
class VoyageEmbeddingProvider:
    """Real Voyage client. Instantiated only when explicitly enabled + credentialed."""

    api_key: str
    provider: str = PROVIDER_VOYAGE
    model: str = DOCUMENT_MODEL
    query_model: str = QUERY_MODEL
    dimensions: int = DEFAULT_DIMENSIONS
    document_calls: int = 0
    query_calls: int = 0

    def __post_init__(self) -> None:
        if self.model != DOCUMENT_MODEL or self.query_model != QUERY_MODEL:
            raise RuntimeError("silent_model_switching_forbidden")

    def _client(self) -> Any:
        try:
            import voyageai  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("voyageai_sdk_unavailable") from exc
        return voyageai.Client(api_key=self.api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        client = self._client()
        self.document_calls += 1
        result = client.embed(
            texts,
            model=self.model,
            input_type="document",
        )
        vectors = list(result.embeddings)
        if not vectors:
            raise RuntimeError("voyage_empty_document_embeddings")
        return [_l2_normalize([float(v) for v in row]) for row in vectors]

    def embed_query(self, text: str) -> list[float]:
        client = self._client()
        self.query_calls += 1
        result = client.embed(
            [text],
            model=self.query_model,
            input_type="query",
        )
        vectors = list(result.embeddings)
        if not vectors:
            raise RuntimeError("voyage_empty_query_embedding")
        return _l2_normalize([float(v) for v in vectors[0]])


@dataclass
class QueryEmbeddingCache:
    ttl_seconds: int = 300
    max_entries: int = 512
    _entries: dict[str, tuple[float, list[float]]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def _key(self, *, company_code: str, model: str, query: str, policy_scope: str) -> str:
        raw = "|".join(
            [
                str(company_code or "").upper(),
                str(model or ""),
                str(policy_scope or ""),
                " ".join(str(query or "").lower().split()),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(
        self,
        *,
        company_code: str,
        model: str,
        query: str,
        policy_scope: str,
    ) -> list[float] | None:
        key = self._key(company_code=company_code, model=model, query=query, policy_scope=policy_scope)
        item = self._entries.get(key)
        if not item:
            self.misses += 1
            return None
        expires_at, vector = item
        if time.time() > expires_at:
            self._entries.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        return list(vector)

    def put(
        self,
        *,
        company_code: str,
        model: str,
        query: str,
        policy_scope: str,
        vector: list[float],
    ) -> None:
        if len(self._entries) >= self.max_entries:
            # Drop oldest.
            oldest = sorted(self._entries.items(), key=lambda item: item[1][0])[: max(1, self.max_entries // 10)]
            for key, _ in oldest:
                self._entries.pop(key, None)
        key = self._key(company_code=company_code, model=model, query=query, policy_scope=policy_scope)
        self._entries[key] = (time.time() + self.ttl_seconds, list(vector))


@dataclass(frozen=True)
class EmbeddingRuntimeConfig:
    enabled: bool
    allow_real_voyage: bool
    api_key_present: bool
    document_model: str = DOCUMENT_MODEL
    query_model: str = QUERY_MODEL
    dimensions: int = DEFAULT_DIMENSIONS
    index_version: str = EMBEDDING_INDEX_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "allow_real_voyage": self.allow_real_voyage,
            "api_key_present": self.api_key_present,
            "document_model": self.document_model,
            "query_model": self.query_model,
            "dimensions": self.dimensions,
            "index_version": self.index_version,
        }


def load_embedding_runtime_config(*, environ: dict[str, str] | None = None) -> EmbeddingRuntimeConfig:
    env = environ if environ is not None else dict(os.environ)
    enabled = str(env.get("WATHEFNI_CK_EMBEDDINGS_ENABLED") or "").strip() in {"1", "true", "yes"}
    allow_real = str(env.get("WATHEFNI_CK_VOYAGE_ENABLED") or "").strip() in {"1", "true", "yes"}
    api_key = str(env.get("VOYAGE_API_KEY") or "").strip()
    return EmbeddingRuntimeConfig(
        enabled=enabled or allow_real,
        allow_real_voyage=allow_real and bool(api_key),
        api_key_present=bool(api_key),
    )


def build_embedding_provider(
    config: EmbeddingRuntimeConfig | None = None,
    *,
    force_mock: bool = False,
    mock_fail: bool = False,
) -> EmbeddingProvider:
    cfg = config or load_embedding_runtime_config()
    if force_mock or not cfg.allow_real_voyage:
        return MockEmbeddingProvider(fail=mock_fail, dimensions=cfg.dimensions)
    api_key = str(os.environ.get("VOYAGE_API_KEY") or "").strip()
    return VoyageEmbeddingProvider(api_key=api_key, dimensions=cfg.dimensions)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(a * b for a, b in zip(left, right)))


__all__ = [
    "DOCUMENT_MODEL",
    "QUERY_MODEL",
    "DEFAULT_DIMENSIONS",
    "EMBEDDING_INDEX_VERSION",
    "PROVIDER_VOYAGE",
    "PROVIDER_MOCK",
    "EmbeddingProvider",
    "MockEmbeddingProvider",
    "VoyageEmbeddingProvider",
    "QueryEmbeddingCache",
    "EmbeddingRuntimeConfig",
    "load_embedding_runtime_config",
    "build_embedding_provider",
    "deterministic_mock_embedding",
    "cosine_similarity",
]
