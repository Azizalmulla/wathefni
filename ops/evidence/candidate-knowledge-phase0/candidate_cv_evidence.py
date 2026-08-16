"""Canonical application CV evidence materialization.

This module owns the versioned readiness contract consumed by Ranking.  It does
not extract files, move lifecycle state, send messages, or recalculate Ranking.
Those side effects remain with their existing owners.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any


CV_EVIDENCE_CONTRACT_VERSION = "application-cv-evidence-v1"
CV_EVIDENCE_MODE_ENV = "WATHEFNI_RANKING_CV_EVIDENCE_MODE"
CV_EVIDENCE_MODES = frozenset({"observe", "enforce"})
READY_STATUS = "ready"
TERMINAL_STATUSES = frozenset({"ready", "failed", "manual_review", "superseded"})


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS application_cv_evidence_materializations (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  app_key text NOT NULL,
  document_id text NOT NULL,
  file_id text NOT NULL,
  source_content_sha256 text NOT NULL,
  extraction_finalization_id uuid NOT NULL,
  extraction_method text,
  extraction_quality_ok boolean NOT NULL DEFAULT false,
  extracted_text_hash text NOT NULL,
  semantic_id text NOT NULL,
  semantic_content_hash text NOT NULL,
  embedding_status text NOT NULL DEFAULT 'missing',
  status text NOT NULL,
  failure_reason text,
  contract_version text NOT NULL DEFAULT 'application-cv-evidence-v1',
  migration_actor text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_current boolean NOT NULL DEFAULT true,
  materialized_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (
    company_code, app_key, document_id, source_content_sha256, contract_version
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_application_cv_evidence_current
  ON application_cv_evidence_materializations(company_code, app_key)
  WHERE is_current=true;
CREATE INDEX IF NOT EXISTS idx_application_cv_evidence_status
  ON application_cv_evidence_materializations(company_code, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_application_cv_evidence_document
  ON application_cv_evidence_materializations(company_code, document_id, updated_at DESC);
"""


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def evidence_mode() -> str:
    value = str(os.getenv(CV_EVIDENCE_MODE_ENV, "enforce") or "enforce").strip().lower()
    return value if value in CV_EVIDENCE_MODES else "enforce"


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def readiness_from_row(row: dict[str, Any] | None) -> dict[str, Any]:
    """Return the fail-closed CV readiness contract for one Ranking pool row."""
    item = row if isinstance(row, dict) else {}
    status = str(item.get("cv_evidence_status") or "").strip().lower()
    file_id = str(item.get("cv_evidence_file_id") or "").strip()
    source_hash = str(item.get("cv_evidence_source_sha256") or "").strip()
    finalization_id = str(item.get("cv_extraction_finalization_id") or "").strip()
    quality_ok = item.get("cv_extraction_quality_ok") is True
    extracted_hash = str(item.get("cv_extracted_text_hash") or "").strip()
    materialized_semantic_hash = str(item.get("cv_evidence_semantic_content_hash") or "").strip()
    selected_semantic_hash = str(item.get("semantic_content_hash") or "").strip()
    semantic_content = str(item.get("semantic_content") or "").strip()
    contract_version = str(item.get("cv_evidence_contract_version") or "").strip()

    reason = None
    if not file_id or not source_hash:
        reason = "cv_file_missing"
    elif not finalization_id:
        reason = "cv_extraction_missing"
    elif not quality_ok:
        reason = "cv_extraction_failed"
    elif not extracted_hash or not semantic_content:
        reason = "cv_processing_incomplete"
    elif not materialized_semantic_hash or materialized_semantic_hash != extracted_hash:
        reason = "cv_semantic_projection_stale"
    elif selected_semantic_hash != materialized_semantic_hash:
        reason = "cv_semantic_projection_stale"
    elif status != READY_STATUS:
        reason = str(item.get("cv_evidence_failure_reason") or "cv_processing_incomplete")
    elif contract_version != CV_EVIDENCE_CONTRACT_VERSION:
        reason = "cv_evidence_contract_stale"

    return {
        "ready": reason is None,
        "reason": reason,
        "status": status or "missing",
        "contract_version": contract_version or CV_EVIDENCE_CONTRACT_VERSION,
        "file_id": file_id or None,
        "source_content_sha256": source_hash or None,
        "extraction_finalization_id": finalization_id or None,
        "extracted_text_hash": extracted_hash or None,
        "semantic_content_hash": materialized_semantic_hash or None,
        "embedding_status": str(item.get("cv_evidence_embedding_status") or "missing"),
    }


def _dump(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"), default=str)


def resolve_managed_file(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    document_id: str | None = None,
    source_content_sha256: str | None = None,
    local_path: str | None = None,
) -> dict[str, Any] | None:
    """Resolve the exact managed file for a document without legacy text fallback."""
    company = str(company_code or "").strip().upper()
    application = str(app_key or "").strip()
    source_hash = str(source_content_sha256 or "").strip().lower()
    path = str(local_path or "").strip()
    cur.execute(
        """
        SELECT file_id, content_sha256, local_path, storage_object_key, mime_type,
               storage_status, metadata, updated_at
        FROM file_registry
        WHERE company_code=%s
          AND subject_type='application'
          AND subject_key=%s
          AND (
            lower(coalesce(document_type,'')) LIKE '%%cv%%'
            OR lower(coalesce(file_kind,'')) LIKE '%%cv%%'
          )
          AND storage_status IN ('stored','uploaded','ready','ok')
        ORDER BY
          CASE WHEN %s<>'' AND content_sha256=%s THEN 0 ELSE 1 END,
          CASE WHEN %s<>'' AND local_path=%s THEN 0 ELSE 1 END,
          CASE WHEN metadata->>'document_id'=%s THEN 0 ELSE 1 END,
          CASE WHEN metadata->>'latest'='true' THEN 0 ELSE 1 END,
          updated_at DESC NULLS LAST
        LIMIT 1
        """,
        (
            company,
            application,
            source_hash,
            source_hash,
            path,
            path,
            str(document_id or ""),
        ),
    )
    row = cur.fetchone()
    if not row:
        return None
    result = dict(row)
    if source_hash and str(result.get("content_sha256") or "").lower() != source_hash:
        return None
    if path and not source_hash and str(result.get("local_path") or "") != path:
        return None
    return result


def materialize_extracted_cv(
    cur: Any,
    *,
    db_execute: Any,
    application: dict[str, Any],
    document_id: str,
    local_path: str | None,
    source_content_sha256: str | None,
    extracted_text: str,
    extraction_method: str | None,
    extraction_metadata: dict[str, Any] | None,
    semantic_upsert: Any,
    actor: str,
) -> dict[str, Any]:
    """Validate, finalize, index, and atomically publish extracted CV evidence."""
    import cv_extraction

    company = str(application.get("company_code") or "").strip().upper()
    app_key = str(application.get("app_key") or "").strip()
    content = str(extracted_text or "").strip()
    if not cv_extraction.cv_text_quality_ok(content):
        raise ValueError("cv_text_quality_rejected")

    file_row = resolve_managed_file(
        cur,
        company_code=company,
        app_key=app_key,
        document_id=document_id,
        source_content_sha256=source_content_sha256,
        local_path=local_path,
    )
    if not file_row:
        raise ValueError("managed_cv_file_missing")

    registered_hash = str(file_row.get("content_sha256") or "").strip().lower()
    managed_path = str(file_row.get("local_path") or local_path or "").strip()
    if managed_path and os.path.isfile(managed_path):
        digest = hashlib.sha256()
        with open(managed_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual_hash = digest.hexdigest()
        if registered_hash and registered_hash != actual_hash:
            raise ValueError("managed_cv_file_hash_mismatch")
        if not registered_hash:
            registered_hash = actual_hash
            cur.execute(
                "UPDATE file_registry SET content_sha256=%s, updated_at=now() WHERE file_id=%s",
                (registered_hash, file_row["file_id"]),
            )
    elif not registered_hash or not str(file_row.get("storage_object_key") or "").strip():
        raise ValueError("managed_cv_file_unavailable")

    semantic = semantic_upsert(
        cur,
        application=application,
        content=content,
        metadata={
            **(extraction_metadata or {}),
            "cv_evidence_contract_version": CV_EVIDENCE_CONTRACT_VERSION,
            "document_id": str(document_id),
        },
    )
    if not semantic.get("ok") or not semantic.get("semantic_id") or not semantic.get("content_hash"):
        raise ValueError("cv_semantic_upsert_failed")
    text_hash = sha256_text(content)
    if str(semantic.get("content_hash") or "").lower() != text_hash:
        raise ValueError("cv_semantic_hash_mismatch")

    finalization = cv_extraction.record_extraction_finalization(
        db_execute,
        company_code=company,
        document_id=str(document_id),
        app_key=app_key,
        source_content_sha256=registered_hash,
        extracted_text=content,
        extraction_method=extraction_method,
        quality_ok=True,
        metadata={
            **(extraction_metadata or {}),
            "semantic_id": semantic.get("semantic_id"),
            "semantic_content_hash": semantic.get("content_hash"),
            "contract_version": CV_EVIDENCE_CONTRACT_VERSION,
        },
    )
    finalization_id = str(finalization.get("finalization_id") or "")
    if not finalization_id:
        raise ValueError("cv_extraction_finalization_failed")
    evidence = materialize_ready(
        cur,
        company_code=company,
        app_key=app_key,
        document_id=str(document_id),
        file_id=str(file_row["file_id"]),
        source_content_sha256=registered_hash,
        extraction_finalization_id=finalization_id,
        extraction_method=extraction_method,
        extracted_text=content,
        semantic_id=str(semantic["semantic_id"]),
        semantic_content_hash=str(semantic["content_hash"]),
        embedded=bool(semantic.get("embedded")),
        actor=actor,
        provenance={
            **(extraction_metadata or {}),
            "document_id": str(document_id),
            "file_id": str(file_row["file_id"]),
        },
    )
    return {"ok": True, "semantic": semantic, "finalization": finalization, "evidence": evidence}


def materialize_ready(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    document_id: str,
    file_id: str,
    source_content_sha256: str,
    extraction_finalization_id: str,
    extraction_method: str | None,
    extracted_text: str,
    semantic_id: str,
    semantic_content_hash: str,
    embedded: bool,
    actor: str,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically publish one current, quality-approved CV evidence version."""
    ensure_schema(cur)
    company = str(company_code or "").strip().upper()
    application = str(app_key or "").strip()
    document = str(document_id or "").strip()
    managed_file = str(file_id or "").strip()
    source_hash = str(source_content_sha256 or "").strip().lower()
    finalization = str(extraction_finalization_id or "").strip()
    content = str(extracted_text or "").strip()
    semantic_hash = str(semantic_content_hash or "").strip().lower()
    if not all((company, application, document, managed_file, source_hash, finalization, content, semantic_id)):
        raise ValueError("canonical_cv_evidence_fields_required")
    text_hash = sha256_text(content)
    if semantic_hash != text_hash:
        raise ValueError("canonical_cv_semantic_hash_mismatch")

    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{company}:{application}:{CV_EVIDENCE_CONTRACT_VERSION}",),
    )
    cur.execute(
        """
        UPDATE application_cv_evidence_materializations
        SET is_current=false, status='superseded', superseded_at=now(), updated_at=now()
        WHERE company_code=%s AND app_key=%s AND is_current=true
          AND NOT (
            document_id=%s AND source_content_sha256=%s AND contract_version=%s
          )
        """,
        (company, application, document, source_hash, CV_EVIDENCE_CONTRACT_VERSION),
    )
    evidence_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO application_cv_evidence_materializations(
          evidence_id, company_code, app_key, document_id, file_id,
          source_content_sha256, extraction_finalization_id, extraction_method,
          extraction_quality_ok, extracted_text_hash, semantic_id,
          semantic_content_hash, embedding_status, status, failure_reason,
          contract_version, migration_actor, provenance, is_current,
          materialized_at, created_at, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s,'ready',NULL,%s,%s,%s::jsonb,
          true,now(),now(),now()
        )
        ON CONFLICT (
          company_code, app_key, document_id, source_content_sha256, contract_version
        ) DO UPDATE SET
          file_id=EXCLUDED.file_id,
          extraction_finalization_id=EXCLUDED.extraction_finalization_id,
          extraction_method=EXCLUDED.extraction_method,
          extraction_quality_ok=true,
          extracted_text_hash=EXCLUDED.extracted_text_hash,
          semantic_id=EXCLUDED.semantic_id,
          semantic_content_hash=EXCLUDED.semantic_content_hash,
          embedding_status=EXCLUDED.embedding_status,
          status='ready',
          failure_reason=NULL,
          migration_actor=EXCLUDED.migration_actor,
          provenance=EXCLUDED.provenance,
          is_current=true,
          materialized_at=now(),
          superseded_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (
            evidence_id,
            company,
            application,
            document,
            managed_file,
            source_hash,
            finalization,
            extraction_method,
            text_hash,
            semantic_id,
            semantic_hash,
            "ready" if embedded else "missing",
            CV_EVIDENCE_CONTRACT_VERSION,
            actor,
            _dump(provenance),
        ),
    )
    row = cur.fetchone()
    return dict(row) if row else {
        "evidence_id": evidence_id,
        "company_code": company,
        "app_key": application,
        "status": "ready",
        "contract_version": CV_EVIDENCE_CONTRACT_VERSION,
    }


def materialize_failure(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    document_id: str,
    file_id: str | None,
    source_content_sha256: str | None,
    reason: str,
    actor: str,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a current failed/manual-review version without claiming readiness."""
    ensure_schema(cur)
    company = str(company_code or "").strip().upper()
    application = str(app_key or "").strip()
    document = str(document_id or "").strip()
    failure = str(reason or "cv_processing_incomplete").strip()
    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{company}:{application}:{CV_EVIDENCE_CONTRACT_VERSION}",),
    )
    cur.execute(
        """
        UPDATE application_cv_evidence_materializations
        SET is_current=false, status='superseded', superseded_at=now(), updated_at=now()
        WHERE company_code=%s AND app_key=%s AND is_current=true
        """,
        (company, application),
    )
    # Failed rows intentionally use deterministic placeholders for required columns.
    source_hash = str(source_content_sha256 or f"missing:{document}")
    evidence_id = str(uuid.uuid4())
    finalization_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{company}:{application}:{document}:{failure}"))
    cur.execute(
        """
        INSERT INTO application_cv_evidence_materializations(
          evidence_id, company_code, app_key, document_id, file_id,
          source_content_sha256, extraction_finalization_id, extraction_quality_ok,
          extracted_text_hash, semantic_id, semantic_content_hash, embedding_status,
          status, failure_reason, contract_version, migration_actor, provenance,
          is_current, materialized_at, created_at, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,false,'','', '', 'missing',
          'failed',%s,%s,%s,%s::jsonb,true,now(),now(),now()
        )
        ON CONFLICT (
          company_code, app_key, document_id, source_content_sha256, contract_version
        ) DO UPDATE SET
          file_id=EXCLUDED.file_id,
          extraction_quality_ok=false,
          status='failed',
          failure_reason=EXCLUDED.failure_reason,
          migration_actor=EXCLUDED.migration_actor,
          provenance=EXCLUDED.provenance,
          is_current=true,
          superseded_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (
            evidence_id,
            company,
            application,
            document,
            str(file_id or ""),
            source_hash,
            finalization_id,
            failure,
            CV_EVIDENCE_CONTRACT_VERSION,
            actor,
            _dump(provenance),
        ),
    )
    row = cur.fetchone()
    return dict(row) if row else {"status": "failed", "failure_reason": failure}


def health_counts(
    cur: Any,
    *,
    company_code: str,
    position_code: str | None = None,
    production_only: bool = False,
) -> dict[str, Any]:
    ensure_schema(cur)
    params: list[Any] = [str(company_code or "").strip().upper()]
    position_sql = ""
    if position_code:
        position = str(position_code).strip().upper()
        position_sql = " AND (upper(a.position_code)=%s OR upper(coalesce(a.position_title,''))=%s)"
        params.extend([position, position.replace("_", " ")])
    scope_sql = "TRUE"
    if production_only:
        scope_sql = """
          COALESCE(a.data_source, a.raw_json->>'data_source', 'production') = 'production'
          AND COALESCE(a.status, '') NOT IN ('needs_role','import_review','import_archived')
          AND COALESCE(a.phone, '') NOT LIKE '9655555%%'
          AND COALESCE(a.app_key, '') NOT ILIKE '%%TEST%%'
          AND COALESCE(a.raw_json->>'candidate_name', a.raw_json->>'name', '') NOT ILIKE 'test %%'
        """
    cur.execute(
        f"""
        SELECT
          count(*) AS total,
          count(*) FILTER (WHERE e.status='ready' AND e.is_current=true) AS ready,
          count(*) FILTER (WHERE e.status='failed' AND e.is_current=true) AS failed,
          count(*) FILTER (WHERE e.evidence_id IS NULL) AS missing,
          count(*) FILTER (
            WHERE e.is_current=true AND e.status NOT IN ('ready','failed')
          ) AS pending
        FROM applications a
        LEFT JOIN application_cv_evidence_materializations e
          ON e.company_code=a.company_code AND e.app_key=a.app_key AND e.is_current=true
        WHERE a.company_code=%s {position_sql}
          AND ({scope_sql})
          AND a.status NOT IN ('hired','rejected','withdrawn')
        """,
        tuple(params),
    )
    row = dict(cur.fetchone() or {})
    cur.execute(
        f"""
        SELECT reason, count(*) AS count
        FROM (
          SELECT CASE
            WHEN e.evidence_id IS NULL THEN 'processing_needed'
            WHEN e.failure_reason ILIKE '%%hash%%' THEN 'hash_mismatch'
            WHEN e.failure_reason ILIKE '%%file%%' THEN 'file_unavailable'
            WHEN e.status='failed' THEN 'processing_failed'
            WHEN e.status<>'ready' THEN 'processing_needed'
            ELSE NULL
          END AS reason
          FROM applications a
          LEFT JOIN application_cv_evidence_materializations e
            ON e.company_code=a.company_code AND e.app_key=a.app_key AND e.is_current=true
          WHERE a.company_code=%s {position_sql}
            AND ({scope_sql})
            AND a.status NOT IN ('hired','rejected','withdrawn')
        ) reasons
        WHERE reason IS NOT NULL
        GROUP BY reason
        ORDER BY reason
        """,
        tuple(params),
    )
    reasons = {
        str(item.get("reason")): int(item.get("count") or 0)
        for item in (cur.fetchall() or [])
        if item.get("reason")
    }
    return {
        "contract_version": CV_EVIDENCE_CONTRACT_VERSION,
        "total": int(row.get("total") or 0),
        "ready": int(row.get("ready") or 0),
        "failed": int(row.get("failed") or 0),
        "missing": int(row.get("missing") or 0),
        "pending": int(row.get("pending") or 0),
        "reasons": reasons,
    }
