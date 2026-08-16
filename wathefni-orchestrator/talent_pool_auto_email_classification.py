"""Bounded automatic post-extraction Talent Pool classification.

This module is intentionally narrow:

* WATHEFNI allowlist only (empty allowlist means nobody).
* New canonical extractions at/after an explicit canary timestamp only.
* Exact immutable document/text/evidence/facts versions.
* No OCR, Job binding, lifecycle, ranking, intake-admit, or outbound calls.
* One-row claims with retries and dead-letter state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json

import talent_pool_classification as tpc


FEATURE = "WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION"
TENANTS = "WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS"
STARTED_AT = "WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_STARTED_AT"
MAX_ATTEMPTS = "WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_MAX_ATTEMPTS"
AUTHORIZED_RECIPIENT = "WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_RECIPIENT"
JOB_SOURCE = "automatic_post_extraction"
DEFAULT_MAX_ATTEMPTS = 3


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candidate_cv_text_versions (
  version_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  app_key text NOT NULL,
  document_id text NOT NULL,
  source_content_sha256 text NOT NULL,
  extracted_text_hash text,
  extraction_finalization_id uuid,
  evidence_id uuid,
  facts_id uuid,
  extraction_method text,
  text_content text,
  status text NOT NULL,
  is_current boolean NOT NULL DEFAULT true,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  UNIQUE (company_code, app_key, document_id, source_content_sha256)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_cv_text_versions_current
  ON candidate_cv_text_versions(company_code, app_key)
  WHERE is_current=true;
CREATE INDEX IF NOT EXISTS idx_candidate_cv_text_versions_document
  ON candidate_cv_text_versions(company_code, document_id, created_at DESC);

ALTER TABLE talent_pool_classification_jobs
  ADD COLUMN IF NOT EXISTS available_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE talent_pool_classification_jobs
  ADD COLUMN IF NOT EXISTS claimed_at timestamptz;
ALTER TABLE talent_pool_classification_jobs
  ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE talent_pool_classification_jobs
  ADD COLUMN IF NOT EXISTS dead_lettered_at timestamptz;
ALTER TABLE talent_pool_classification_jobs
  ADD COLUMN IF NOT EXISTS claim_owner text;
ALTER TABLE talent_pool_classification_jobs
  ADD COLUMN IF NOT EXISTS max_attempts integer NOT NULL DEFAULT 3;
"""


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def allowed_tenants(environ: dict[str, str] | None = None) -> set[str]:
    raw = str(_env(environ).get(TENANTS) or "").strip()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def enabled_for_company(company_code: str | None, environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    company = str(company_code or "").strip().upper()
    return bool(company) and _truthy(env.get(FEATURE)) and company in allowed_tenants(env)


def canary_started_at(environ: dict[str, str] | None = None) -> datetime:
    raw = str(_env(environ).get(STARTED_AT) or "").strip()
    if not raw:
        raise RuntimeError("auto_classification_canary_start_required")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def authorized_recipient(environ: dict[str, str] | None = None) -> str:
    recipient = str(_env(environ).get(AUTHORIZED_RECIPIENT) or "").strip().lower()
    if not recipient:
        raise RuntimeError("auto_classification_authorized_recipient_required")
    return recipient


def ensure_schema(cur: Any) -> None:
    tpc.ensure_classification_schema(cur)
    cur.execute(SCHEMA_SQL)


def _stable_key(*parts: Any) -> str:
    source = "\0".join(str(part or "") for part in parts)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _row(cur: Any) -> dict[str, Any] | None:
    value = cur.fetchone()
    return dict(value) if value else None


def preserve_existing_version_without_enqueue(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    document_id: str,
    source_content_sha256: str,
    extracted_text_hash: str | None,
    extraction_finalization_id: str | None,
    evidence_id: str | None,
    facts_id: str | None,
    extraction_method: str | None,
    text_content: str | None,
    status: str,
    is_current: bool,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    """Create a no-queue audit version during controlled authority remediation."""
    ensure_schema(cur)
    company = str(company_code or "").strip().upper()
    if text_content and hashlib.sha256(text_content.encode("utf-8")).hexdigest() != str(extracted_text_hash or ""):
        raise RuntimeError("preserved_text_hash_mismatch")
    if is_current:
        cur.execute(
            """
            UPDATE candidate_cv_text_versions
            SET is_current=false, superseded_at=COALESCE(superseded_at, now())
            WHERE company_code=%s AND app_key=%s AND is_current=true
            """,
            (company, app_key),
        )
    version_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO candidate_cv_text_versions(
          version_id, company_code, app_key, document_id, source_content_sha256,
          extracted_text_hash, extraction_finalization_id, evidence_id, facts_id,
          extraction_method, text_content, status, is_current, provenance,
          superseded_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                  CASE WHEN %s THEN NULL ELSE now() END)
        ON CONFLICT (company_code, app_key, document_id, source_content_sha256)
        DO NOTHING
        RETURNING version_id
        """,
        (
            version_id,
            company,
            app_key,
            document_id,
            source_content_sha256,
            extracted_text_hash,
            extraction_finalization_id or None,
            evidence_id or None,
            facts_id or None,
            extraction_method,
            text_content,
            status,
            is_current,
            Json(provenance),
            is_current,
        ),
    )
    inserted = _row(cur)
    if not inserted:
        cur.execute(
            """
            SELECT version_id FROM candidate_cv_text_versions
            WHERE company_code=%s AND app_key=%s AND document_id=%s
              AND source_content_sha256=%s
            LIMIT 1
            """,
            (company, app_key, document_id, source_content_sha256),
        )
        inserted = _row(cur)
    if is_current and inserted:
        cur.execute(
            "UPDATE candidate_cv_text_versions SET is_current=true, superseded_at=NULL WHERE version_id=%s",
            (inserted["version_id"],),
        )
    return {
        "version_id": str((inserted or {}).get("version_id") or ""),
        "document_id": document_id,
        "status": status,
        "is_current": is_current,
        "queued": False,
    }


def record_extraction_and_enqueue(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    document_id: str,
    extracted_text: str,
    extraction_method: str | None,
    evidence: dict[str, Any],
    facts_snapshot: dict[str, Any],
    provenance: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Persist an immutable text version and enqueue one exact-version job.

    Called inside the canonical extraction transaction after evidence/facts
    materialization. Returning ``eligible=False`` is a safe no-op.
    """
    ensure_schema(cur)
    company = str(company_code or "").strip().upper()
    app_key = str(app_key or "").strip()
    document_id = str(document_id or "").strip()
    if not company or not app_key or not document_id:
        raise ValueError("company_app_document_required")
    if not enabled_for_company(company, environ):
        return {"eligible": False, "reason": "tenant_not_enabled"}

    started_at = canary_started_at(environ)
    cur.execute(
        """
        SELECT created_at, metadata, extraction_status
        FROM candidate_documents
        WHERE document_id=%s AND app_key=%s
        LIMIT 1
        """,
        (document_id, app_key),
    )
    document = _row(cur)
    if not document:
        raise RuntimeError("candidate_document_missing")
    created_at = document.get("created_at")
    if not created_at or created_at.astimezone(timezone.utc) < started_at:
        return {"eligible": False, "reason": "document_before_canary_start"}
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    import_batch_id = str(metadata.get("import_batch_id") or "").strip()
    recipient = authorized_recipient(environ)
    if not import_batch_id:
        return {"eligible": False, "reason": "not_authorized_email_route"}
    cur.execute(
        """
        SELECT inbound_id
        FROM inbound_messages
        WHERE batch_id::text=%s
          AND company_code=%s
          AND lower(coalesce(envelope_recipient,''))=%s
        LIMIT 1
        """,
        (import_batch_id, company, recipient),
    )
    inbound = _row(cur)
    if not inbound:
        return {"eligible": False, "reason": "not_authorized_email_route"}

    evidence_id = str(evidence.get("evidence_id") or "")
    facts_id = str(facts_snapshot.get("facts_id") or "")
    source_sha = str(evidence.get("source_content_sha256") or "")
    text_hash = str(evidence.get("extracted_text_hash") or "")
    finalization_id = str(evidence.get("extraction_finalization_id") or "")
    if not all((evidence_id, facts_id, source_sha, text_hash, finalization_id)):
        raise RuntimeError("canonical_extraction_versions_required")
    if not extracted_text or hashlib.sha256(extracted_text.encode("utf-8")).hexdigest() != text_hash:
        raise RuntimeError("immutable_text_hash_mismatch")

    cur.execute(
        """
        SELECT evidence_id, facts_id, is_current, status, embedding_status
        FROM application_cv_evidence_materializations
        WHERE company_code=%s AND app_key=%s AND document_id=%s
          AND evidence_id=%s AND is_current=true
        LIMIT 1
        """,
        (company, app_key, document_id, evidence_id),
    )
    current_evidence = _row(cur)
    if not current_evidence or str(current_evidence.get("status")) != "ready":
        raise RuntimeError("current_cv_evidence_not_ready")
    cur.execute(
        """
        SELECT facts_id, is_current, status
        FROM application_cv_fact_snapshots
        WHERE company_code=%s AND app_key=%s AND document_id=%s
          AND facts_id=%s AND is_current=true
        LIMIT 1
        """,
        (company, app_key, document_id, facts_id),
    )
    current_facts = _row(cur)
    if not current_facts or str(current_facts.get("status")) != "ready":
        raise RuntimeError("current_cv_facts_not_ready")

    cur.execute(
        """
        SELECT version_id FROM candidate_cv_text_versions
        WHERE company_code=%s AND app_key=%s AND document_id=%s
          AND source_content_sha256=%s
        LIMIT 1
        """,
        (company, app_key, document_id, source_sha),
    )
    existing_version = _row(cur)
    version_id = str(uuid.uuid4())
    if existing_version:
        version_id = str(existing_version["version_id"])
    else:
        cur.execute(
            """
            UPDATE candidate_cv_text_versions
            SET is_current=false, superseded_at=COALESCE(superseded_at, now())
            WHERE company_code=%s AND app_key=%s AND is_current=true
            """,
            (company, app_key),
        )
        cur.execute(
            """
            INSERT INTO candidate_cv_text_versions(
              version_id, company_code, app_key, document_id, source_content_sha256,
              extracted_text_hash, extraction_finalization_id, evidence_id, facts_id,
              extraction_method, text_content, status, is_current, provenance
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'ready',true,%s)
            """,
            (
                version_id,
                company,
                app_key,
                document_id,
                source_sha,
                text_hash,
                finalization_id,
                evidence_id,
                facts_id,
                extraction_method,
                extracted_text,
                Json(provenance or {}),
            ),
        )
    cur.execute(
        "UPDATE candidate_cv_text_versions SET is_current=true, superseded_at=NULL WHERE version_id=%s",
        (version_id,),
    )

    taxonomy_version = str(tpc.load_taxonomy_pack().get("taxonomy_version") or "")
    key = _stable_key(
        JOB_SOURCE,
        company,
        app_key,
        document_id,
        version_id,
        finalization_id,
        evidence_id,
        facts_id,
        taxonomy_version,
        tpc.CLASSIFIER_VERSION,
    )
    payload = {
        "source": JOB_SOURCE,
        "inbound_id": str(inbound["inbound_id"]),
        "import_batch_id": import_batch_id,
        "authorized_recipient": recipient,
        "canary_started_at": started_at.isoformat(),
        "version_id": version_id,
        "document_id": document_id,
        "extraction_finalization_id": finalization_id,
        "evidence_id": evidence_id,
        "facts_id": facts_id,
        "source_content_sha256": source_sha,
        "extracted_text_hash": text_hash,
        "taxonomy_version": taxonomy_version,
        "classifier_version": tpc.CLASSIFIER_VERSION,
        "enqueued_at": datetime.now(timezone.utc).isoformat(),
        "ocr_triggered_by_classification": False,
    }
    max_attempts = max(1, int(str(_env(environ).get(MAX_ATTEMPTS) or DEFAULT_MAX_ATTEMPTS)))
    cur.execute(
        """
        INSERT INTO talent_pool_classification_jobs(
          job_id, company_code, app_key, job_type, idempotency_key, status,
          payload, available_at, max_attempts
        ) VALUES (%s,%s,%s,%s,%s,'queued',%s,now(),%s)
        ON CONFLICT (company_code, idempotency_key) DO NOTHING
        RETURNING job_id, status
        """,
        (str(uuid.uuid4()), company, app_key, tpc.JOB_TYPE, key, Json(payload), max_attempts),
    )
    queued = _row(cur)
    if not queued:
        cur.execute(
            """
            SELECT job_id, status FROM talent_pool_classification_jobs
            WHERE company_code=%s AND idempotency_key=%s
            LIMIT 1
            """,
            (company, key),
        )
        queued = _row(cur)
        idempotent = True
    else:
        idempotent = False
    return {
        "eligible": True,
        "version_id": version_id,
        "job_id": str((queued or {}).get("job_id") or ""),
        "job_status": (queued or {}).get("status"),
        "idempotent_hit": idempotent,
        "ocr_triggered": False,
    }


def _claim_one(cur: Any, *, owner: str, environ: dict[str, str] | None = None) -> dict[str, Any] | None:
    ensure_schema(cur)
    started_at = canary_started_at(environ)
    tenants = sorted(allowed_tenants(environ))
    if tenants != ["WATHEFNI"] or not enabled_for_company("WATHEFNI", environ):
        raise RuntimeError("worker_requires_exact_wathefni_allowlist")
    recipient = authorized_recipient(environ)
    cur.execute(
        """
        SELECT j.*
        FROM talent_pool_classification_jobs j
        JOIN candidate_documents d
          ON d.app_key=j.app_key
         AND d.document_id::text=(j.payload->>'document_id')
        JOIN applications a
          ON a.app_key=j.app_key
         AND a.company_code=j.company_code
        WHERE j.company_code='WATHEFNI'
          AND j.job_type=%s
          AND j.status IN ('queued','retrying')
          AND j.dead_letter=false
          AND j.available_at<=now()
          AND j.created_at >= %s
          AND d.created_at >= %s
          AND j.payload->>'source'=%s
          AND lower(j.payload->>'authorized_recipient')=%s
          AND a.status IN ('needs_role','import_review','import_archived')
          AND coalesce(a.position_code,'')=''
          AND EXISTS (
            SELECT 1 FROM inbound_messages im
            WHERE im.inbound_id::text=j.payload->>'inbound_id'
              AND im.batch_id::text=j.payload->>'import_batch_id'
              AND im.company_code='WATHEFNI'
              AND lower(coalesce(im.envelope_recipient,''))=%s
          )
        ORDER BY j.created_at
        FOR UPDATE OF j SKIP LOCKED
        LIMIT 1
        """,
        (tpc.JOB_TYPE, started_at, started_at, JOB_SOURCE, recipient, recipient),
    )
    job = _row(cur)
    if not job:
        return None
    cur.execute(
        """
        UPDATE talent_pool_classification_jobs
        SET status='processing', claim_owner=%s, claimed_at=now(),
            attempt_count=attempt_count+1, updated_at=now()
        WHERE job_id=%s
        RETURNING *
        """,
        (owner, job["job_id"]),
    )
    return _row(cur)


def _load_bundle(cur: Any, job: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    cur.execute(
        """
        SELECT v.*, f.facts
        FROM candidate_cv_text_versions v
        JOIN application_cv_fact_snapshots f
          ON f.facts_id=v.facts_id
         AND f.company_code=v.company_code
         AND f.app_key=v.app_key
         AND f.document_id=v.document_id
        JOIN application_cv_evidence_materializations e
          ON e.evidence_id=v.evidence_id
         AND e.company_code=v.company_code
         AND e.app_key=v.app_key
         AND e.document_id=v.document_id
        WHERE v.version_id=%s AND v.company_code='WATHEFNI'
          AND v.app_key=%s AND v.document_id=%s
          AND v.is_current=true AND v.status='ready'
          AND f.is_current=true AND f.status='ready'
          AND e.is_current=true AND e.status='ready'
        LIMIT 1
        """,
        (payload.get("version_id"), job["app_key"], payload.get("document_id")),
    )
    version = _row(cur)
    if not version:
        raise RuntimeError("exact_current_cv_version_not_ready")
    text = str(version.get("text_content") or "")
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != str(version.get("extracted_text_hash") or ""):
        raise RuntimeError("stored_text_hash_mismatch")
    bundle = tpc.build_input_bundle(
        cv_text=text,
        facts=version.get("facts") if isinstance(version.get("facts"), dict) else {},
        hr_confirmed_facts={},
        document_version_id=str(version["document_id"]),
        extraction_version_id=str(version.get("extraction_finalization_id") or ""),
        completeness=[],
        embedding_present=True,
    )
    return version, bundle


def process_one(db_connect: Any, *, owner: str | None = None, environ: dict[str, str] | None = None) -> dict[str, Any]:
    owner = owner or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    with db_connect() as conn:
        with conn.cursor() as cur:
            job = _claim_one(cur, owner=owner, environ=environ)
        conn.commit()
    if not job:
        return {"processed": 0, "owner": owner}

    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                version, bundle = _load_bundle(cur, job)
                result = tpc.classify_bundle(bundle)
                persisted = tpc.persist_classification_run(
                    cur,
                    company_code="WATHEFNI",
                    app_key=str(job["app_key"]),
                    bundle=bundle,
                    result=result,
                    document_version_id=str(version["document_id"]),
                    extraction_version_id=str(version.get("extraction_finalization_id") or ""),
                )
                payload = dict(job.get("payload") or {})
                payload.update(
                    {
                        "run_id": persisted["run_id"],
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "ocr_triggered_by_classification": False,
                        "document_version_id": str(version["document_id"]),
                        "extraction_version_id": str(version.get("extraction_finalization_id") or ""),
                    }
                )
                cur.execute(
                    """
                    UPDATE talent_pool_classification_jobs
                    SET status='completed', completed_at=now(), updated_at=now(),
                        last_error=NULL, payload=%s
                    WHERE job_id=%s AND claim_owner=%s
                    """,
                    (Json(payload), job["job_id"], owner),
                )
            conn.commit()
        return {
            "processed": 1,
            "job_id": str(job["job_id"]),
            "run_id": persisted["run_id"],
            "document_version_id": str(version["document_id"]),
            "idempotent_hit": persisted.get("idempotent_hit"),
            "ocr_triggered": False,
        }
    except Exception as exc:
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT attempt_count, max_attempts FROM talent_pool_classification_jobs WHERE job_id=%s",
                    (job["job_id"],),
                )
                attempts = _row(cur) or {}
                dead = int(attempts.get("attempt_count") or 0) >= int(attempts.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)
                cur.execute(
                    """
                    UPDATE talent_pool_classification_jobs
                    SET status=%s, dead_letter=%s,
                        dead_lettered_at=CASE WHEN %s THEN now() ELSE dead_lettered_at END,
                        available_at=CASE WHEN %s THEN available_at ELSE now() + interval '30 seconds' END,
                        last_error=%s, updated_at=now()
                    WHERE job_id=%s
                    """,
                    ("dead_letter" if dead else "retrying", dead, dead, dead, str(exc)[:2000], job["job_id"]),
                )
            conn.commit()
        return {
            "processed": 1,
            "job_id": str(job["job_id"]),
            "status": "dead_letter" if dead else "retrying",
            "error": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    if args.limit != 1:
        raise SystemExit("bounded canary worker requires --limit 1")
    import app

    result = process_one(app.db_connect)
    print(json.dumps(result, default=str))
    return 0 if not result.get("error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
