"""Shared inbound CV security and processing authority (Wave 2).

Channel-neutral stage catalog, kill switches, stage run ledger, and
``cv_version_id`` dual-write. Live email wrappers in ``durable_email_ingress`` /
``app.py`` remain authoritative for user-visible outcomes.

Wave 2 does not cut over WhatsApp or manual upload. Production dual-write flags
default OFF.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover
    Json = dict  # type: ignore[misc, assignment]

UTC = timezone.utc
PROCESSING_VERSION = "unified-inbound-cv-processing-v1"
CV_VERSION_CONTRACT = "cv-version-v1"
_ID_NAMESPACE = uuid.UUID("a91f2c3d-4e5b-6789-abcd-ef0123456789")

# Ordered shared stages. Email wrappers map existing jobs onto these names.
STAGES = (
    "document_acceptance",
    "mime_content_validation",
    "malware_scan",
    "local_extraction",
    "mistral_ocr",
    "gpt_vision_rescue",
    "structured_facts",
    "immutable_cv_version",
    "classification",
    "candidate_knowledge_indexing",
)

STAGE_VERSIONS = {stage: f"{PROCESSING_VERSION}:{stage}:1" for stage in STAGES}

# Email job_type → shared stage (primary). Reserved jobs map to later stages.
EMAIL_JOB_STAGE = {
    "intake_validation": "document_acceptance",
    "file_safety_scan": "malware_scan",
    "cv_identity_resolution": "mime_content_validation",
    "accepted_intake_preparation": "document_acceptance",
    "cv_extraction": "local_extraction",
    "profile_structuring": "structured_facts",
    "embedding": "candidate_knowledge_indexing",
}

TERMINAL_STAGE_STATUSES = frozenset(
    {"completed", "skipped", "dead_letter", "killed", "failed_closed"}
)
ACTIVE_STAGE_STATUSES = frozenset({"pending", "running", "retrying"})

FEATURE_PROCESSING = "WATHEFNI_UNIFIED_CV_PROCESSING"
FEATURE_CV_VERSION_DUAL_WRITE = "WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE"
FEATURE_STAGE_LEDGER = "WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER"
FEATURE_ENVELOPE_DUAL_WRITE = "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE"

# Per-stage kill switches (independent observability / fail-closed).
STAGE_KILL_SWITCHES = {
    "malware_scan": "WATHEFNI_UNIFIED_STAGE_KILL_MALWARE_SCAN",
    "local_extraction": "WATHEFNI_UNIFIED_STAGE_KILL_LOCAL_EXTRACTION",
    "mistral_ocr": "WATHEFNI_CV_MISTRAL_OCR",  # existing master; OFF = killed/skipped OCR
    "gpt_vision_rescue": "WATHEFNI_CV_GPT_VISION_RESCUE",
    "structured_facts": "WATHEFNI_UNIFIED_STAGE_KILL_STRUCTURED_FACTS",
    "immutable_cv_version": "WATHEFNI_UNIFIED_STAGE_KILL_CV_VERSION",
    "classification": "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS",
    "candidate_knowledge_indexing": "WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cv_versions (
  cv_version_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  content_sha256 text NOT NULL,
  extracted_text_hash text,
  extraction_method text,
  status text NOT NULL DEFAULT 'ready',
  contract_version text NOT NULL DEFAULT 'cv-version-v1',
  processing_version text NOT NULL DEFAULT 'unified-inbound-cv-processing-v1',
  legacy_app_key text,
  legacy_document_id text,
  legacy_text_version_id uuid,
  evidence_id uuid,
  facts_id uuid,
  envelope_item_id uuid,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, content_sha256, legacy_document_id)
);
ALTER TABLE IF EXISTS cv_versions
  ADD COLUMN IF NOT EXISTS person_id uuid;
ALTER TABLE IF EXISTS cv_versions
  ADD COLUMN IF NOT EXISTS subject_id uuid;
ALTER TABLE IF EXISTS cv_versions
  ADD COLUMN IF NOT EXISTS ownership_kind text;
CREATE INDEX IF NOT EXISTS idx_cv_versions_company_created
  ON cv_versions(company_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_cv_versions_legacy_app
  ON cv_versions(company_code, legacy_app_key)
  WHERE legacy_app_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cv_versions_legacy_text
  ON cv_versions(company_code, legacy_text_version_id)
  WHERE legacy_text_version_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cv_versions_person
  ON cv_versions(company_code, person_id, created_at DESC)
  WHERE person_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cv_versions_subject
  ON cv_versions(company_code, subject_id, created_at DESC)
  WHERE subject_id IS NOT NULL;

ALTER TABLE IF EXISTS candidate_cv_text_versions
  ADD COLUMN IF NOT EXISTS cv_version_id uuid;
ALTER TABLE IF EXISTS application_cv_evidence_materializations
  ADD COLUMN IF NOT EXISTS cv_version_id uuid;
ALTER TABLE IF EXISTS application_cv_fact_snapshots
  ADD COLUMN IF NOT EXISTS cv_version_id uuid;

CREATE TABLE IF NOT EXISTS cv_processing_stage_runs (
  run_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  stage text NOT NULL,
  stage_version text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  attempt integer NOT NULL DEFAULT 1,
  max_attempts integer NOT NULL DEFAULT 5,
  idempotency_key text NOT NULL,
  cv_version_id uuid,
  legacy_app_key text,
  legacy_document_id text,
  legacy_job_id uuid,
  envelope_item_id uuid,
  error_code text,
  error_detail text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  available_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  dead_lettered_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_cv_processing_stage_runs_stage_status
  ON cv_processing_stage_runs(company_code, stage, status, available_at);
CREATE INDEX IF NOT EXISTS idx_cv_processing_stage_runs_cv_version
  ON cv_processing_stage_runs(company_code, cv_version_id)
  WHERE cv_version_id IS NOT NULL;
"""


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _json(value: Any) -> Any:
    if Json is dict:
        return value
    return Json(value)


def _safe_company(value: str | None) -> str:
    company = re.sub(r"[^A-Z0-9_-]", "", str(value or "").strip().upper())
    if not company:
        raise ValueError("company_scope_missing")
    return company


def processing_feature_enabled(environ: dict[str, str] | None = None) -> bool:
    """Master Wave 2 shared-authority feature (staging/local). Default OFF."""

    return _truthy(_env(environ).get(FEATURE_PROCESSING))


def cv_version_dual_write_enabled(environ: dict[str, str] | None = None) -> bool:
    """Additive cv_version_id dual-write. Default OFF (no production enablement)."""

    return _truthy(_env(environ).get(FEATURE_CV_VERSION_DUAL_WRITE))


def stage_ledger_enabled(environ: dict[str, str] | None = None) -> bool:
    if processing_feature_enabled(environ):
        return True
    return _truthy(_env(environ).get(FEATURE_STAGE_LEDGER))


def envelope_dual_write_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_ENVELOPE_DUAL_WRITE))


def stage_killed(stage: str, environ: dict[str, str] | None = None) -> bool:
    """Return True when an independent stage kill switch blocks the stage.

    OCR/rescue use existing flags inverted: OFF means stage unavailable.
    Classification/CK worker flags OFF means workers killed (expected production
    posture for non-canary). Explicit ``WATHEFNI_UNIFIED_STAGE_KILL_*`` are
    fail-closed when truthy.
    """

    env = _env(environ)
    key = STAGE_KILL_SWITCHES.get(stage)
    if not key:
        return False
    raw = str(env.get(key) or "").strip().lower()
    if stage in {"mistral_ocr", "gpt_vision_rescue", "classification", "candidate_knowledge_indexing"}:
        # These flags enable work when ON; killed when unset/off.
        if stage == "gpt_vision_rescue" and not _truthy(env.get("WATHEFNI_CV_MISTRAL_OCR")):
            # Rescue only applies when OCR path is active; otherwise N/A not killed.
            return False
        return not _truthy(raw)
    return _truthy(raw)


REQUIRED_TABLES = [
    "cv_versions",
    "cv_processing_stage_runs",
]


def apply_schema(cur: Any) -> None:
    import schema_contract as _schema

    _schema.apply_sql(
        cur,
        SCHEMA_SQL,
        module="inbound_cv_processing",
        lock_id=770_911_102,
    )


def require_schema(cur: Any) -> None:
    import schema_contract as _schema

    _schema.require_relations(cur, REQUIRED_TABLES, module="inbound_cv_processing")


def ensure_schema(cur: Any) -> None:
    """Runtime-safe: validate only unless WATHEFNI_SCHEMA_APPLY is enabled."""

    import schema_contract as _schema

    _schema.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=REQUIRED_TABLES,
        module="inbound_cv_processing",
        lock_id=770_911_102,
    )


def stable_cv_version_id(
    *,
    company_code: str,
    content_sha256: str,
    legacy_document_id: str,
) -> str:
    key = "|".join(
        [
            str(company_code or "").strip().upper(),
            str(content_sha256 or "").strip().lower(),
            str(legacy_document_id or "").strip(),
        ]
    )
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:cv-version:{key}"))


def stable_stage_run_id(*, company_code: str, idempotency_key: str) -> str:
    key = f"{str(company_code or '').strip().upper()}|{idempotency_key}"
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:cv-stage-run:{key}"))


def stage_idempotency_key(
    *,
    stage: str,
    company_code: str,
    subject_id: str,
    content_sha256: str | None = None,
) -> str:
    digest = str(content_sha256 or "").strip().lower() or "nosha"
    return f"{stage}:{company_code}:{subject_id}:{digest}:{STAGE_VERSIONS[stage]}"


@dataclass(frozen=True)
class ExtractionProviderPlan:
    """Deterministic provider plan for an accepted document (no network)."""

    local_first: bool
    mistral_ocr_eligible: bool
    gpt_vision_rescue_eligible: bool
    reason_codes: tuple[str, ...]


def plan_extraction_providers(
    *,
    mime_or_suffix: str,
    local_text_ok: bool,
    needs_ocr: bool,
    environ: dict[str, str] | None = None,
) -> ExtractionProviderPlan:
    """Describe local → Mistral OCR without GPT rescue (rescue retired)."""

    env = _env(environ)
    suffix = str(mime_or_suffix or "").strip().lower()
    is_docx = "wordprocessingml" in suffix or suffix.endswith(".docx") or suffix == "docx"
    is_image = suffix.startswith("image/") or suffix in {".png", ".jpg", ".jpeg", ".webp", "png", "jpg", "jpeg", "webp"}
    is_pdf = "pdf" in suffix or suffix.endswith(".pdf")

    reasons: list[str] = []
    if is_docx and local_text_ok:
        reasons.append("docx_local_xml_primary")
        return ExtractionProviderPlan(
            local_first=True,
            mistral_ocr_eligible=False,
            gpt_vision_rescue_eligible=False,
            reason_codes=tuple(reasons),
        )

    ocr_on = _truthy(env.get("WATHEFNI_CV_MISTRAL_OCR"))
    # WATHEFNI_CV_GPT_VISION_RESCUE is ignored — CV GPT rescue permanently retired.

    if local_text_ok and not needs_ocr and not is_image:
        reasons.append("accepted_local_poppler_or_text")
        return ExtractionProviderPlan(
            local_first=True,
            mistral_ocr_eligible=False,
            gpt_vision_rescue_eligible=False,
            reason_codes=tuple(reasons),
        )

    if needs_ocr or is_image:
        reasons.append("scanned_or_image_needs_ocr" if needs_ocr or is_image else "ocr_required")
        if not ocr_on:
            reasons.append("mistral_ocr_disabled")
            reasons.append("cv_gpt_rescue_retired")
            return ExtractionProviderPlan(
                local_first=True,
                mistral_ocr_eligible=False,
                gpt_vision_rescue_eligible=False,
                reason_codes=tuple(reasons),
            )
        reasons.append("mistral_ocr_eligible")
        reasons.append("cv_gpt_rescue_retired")
        return ExtractionProviderPlan(
            local_first=True,
            mistral_ocr_eligible=True,
            gpt_vision_rescue_eligible=False,
            reason_codes=tuple(reasons),
        )

    reasons.append("local_only")
    return ExtractionProviderPlan(
        local_first=True,
        mistral_ocr_eligible=False,
        gpt_vision_rescue_eligible=False,
        reason_codes=tuple(reasons),
    )


def record_stage_run(
    cur: Any,
    *,
    company_code: str,
    stage: str,
    status: str,
    subject_id: str,
    content_sha256: str | None = None,
    attempt: int = 1,
    max_attempts: int = 5,
    cv_version_id: str | None = None,
    legacy_app_key: str | None = None,
    legacy_document_id: str | None = None,
    legacy_job_id: str | None = None,
    envelope_item_id: str | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    metadata: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Idempotently upsert one observable stage run. No-op when ledger disabled."""

    if stage not in STAGES:
        raise ValueError(f"unknown_stage:{stage}")
    if not stage_ledger_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "stage_ledger_disabled"}

    if stage_killed(stage, environ) and status in {"pending", "running"}:
        status = "killed"
        error_code = error_code or "stage_kill_switch"
        error_detail = error_detail or STAGE_KILL_SWITCHES.get(stage)

    company = _safe_company(company_code)
    ensure_schema(cur)
    idem = stage_idempotency_key(
        stage=stage,
        company_code=company,
        subject_id=subject_id,
        content_sha256=content_sha256,
    )
    run_id = stable_stage_run_id(company_code=company, idempotency_key=idem)
    now = datetime.now(UTC)
    completed = now if status in TERMINAL_STAGE_STATUSES else None
    dead = now if status == "dead_letter" else None
    started = now if status in {"running", "completed", "failed_closed", "dead_letter", "killed", "skipped"} else None

    cur.execute(
        """
        INSERT INTO cv_processing_stage_runs
          (run_id, company_code, stage, stage_version, status, attempt, max_attempts,
           idempotency_key, cv_version_id, legacy_app_key, legacy_document_id,
           legacy_job_id, envelope_item_id, error_code, error_detail, metadata,
           started_at, completed_at, dead_lettered_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, idempotency_key)
        DO UPDATE SET
          status=EXCLUDED.status,
          attempt=GREATEST(cv_processing_stage_runs.attempt, EXCLUDED.attempt),
          error_code=COALESCE(EXCLUDED.error_code, cv_processing_stage_runs.error_code),
          error_detail=COALESCE(EXCLUDED.error_detail, cv_processing_stage_runs.error_detail),
          metadata=EXCLUDED.metadata,
          cv_version_id=COALESCE(cv_processing_stage_runs.cv_version_id, EXCLUDED.cv_version_id),
          completed_at=COALESCE(EXCLUDED.completed_at, cv_processing_stage_runs.completed_at),
          dead_lettered_at=COALESCE(EXCLUDED.dead_lettered_at, cv_processing_stage_runs.dead_lettered_at),
          updated_at=now()
        RETURNING run_id::text AS run_id, status
        """,
        (
            run_id,
            company,
            stage,
            STAGE_VERSIONS[stage],
            status,
            attempt,
            max_attempts,
            idem,
            cv_version_id,
            legacy_app_key,
            legacy_document_id,
            legacy_job_id,
            envelope_item_id,
            error_code,
            (str(error_detail)[:500] if error_detail else None),
            _json(metadata or {"processing_version": PROCESSING_VERSION}),
            started,
            completed,
            dead,
        ),
    )
    row = cur.fetchone() or {"run_id": run_id, "status": status}
    return {"ok": True, "skipped": False, "run_id": row.get("run_id"), "status": row.get("status"), "idempotency_key": idem}


def mark_stage_retry_or_dead_letter(
    *,
    attempt: int,
    max_attempts: int,
    error_code: str,
) -> str:
    if attempt >= max_attempts:
        return "dead_letter"
    return "retrying"


def dual_write_cv_version(
    cur: Any,
    *,
    company_code: str,
    content_sha256: str,
    legacy_document_id: str,
    legacy_app_key: str | None = None,
    legacy_text_version_id: str | None = None,
    extracted_text_hash: str | None = None,
    extraction_method: str | None = None,
    evidence_id: str | None = None,
    facts_id: str | None = None,
    envelope_item_id: str | None = None,
    person_id: str | None = None,
    subject_id: str | None = None,
    ownership_kind: str | None = None,
    provenance: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Idempotently mirror an accepted extraction into ``cv_versions``.

    Does not cut over app_key readers. Bridges ``candidate_cv_text_versions`` /
    evidence / facts with nullable ``cv_version_id`` when present.
    Wave 4: optional person/subject ownership without rewriting Ranking evidence.
    """

    if not cv_version_dual_write_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "cv_version_dual_write_disabled"}
    if stage_killed("immutable_cv_version", environ):
        return {"ok": True, "skipped": True, "reason": "stage_killed"}

    company = _safe_company(company_code)
    sha = str(content_sha256 or "").strip().lower()
    document_id = str(legacy_document_id or "").strip()
    if not sha or not document_id:
        raise ValueError("content_sha_and_document_required")

    ensure_schema(cur)
    cv_version_id = stable_cv_version_id(
        company_code=company,
        content_sha256=sha,
        legacy_document_id=document_id,
    )
    kind = str(ownership_kind or "").strip() or (
        "person" if person_id else ("subject" if subject_id else "legacy_document")
    )
    cur.execute(
        """
        INSERT INTO cv_versions
          (cv_version_id, company_code, content_sha256, extracted_text_hash,
           extraction_method, status, contract_version, processing_version,
           legacy_app_key, legacy_document_id, legacy_text_version_id,
           evidence_id, facts_id, envelope_item_id, person_id, subject_id,
           ownership_kind, provenance)
        VALUES (%s,%s,%s,%s,%s,'ready',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, content_sha256, legacy_document_id)
        DO UPDATE SET
          extracted_text_hash=COALESCE(EXCLUDED.extracted_text_hash, cv_versions.extracted_text_hash),
          extraction_method=COALESCE(EXCLUDED.extraction_method, cv_versions.extraction_method),
          legacy_app_key=COALESCE(cv_versions.legacy_app_key, EXCLUDED.legacy_app_key),
          legacy_text_version_id=COALESCE(cv_versions.legacy_text_version_id, EXCLUDED.legacy_text_version_id),
          evidence_id=COALESCE(cv_versions.evidence_id, EXCLUDED.evidence_id),
          facts_id=COALESCE(cv_versions.facts_id, EXCLUDED.facts_id),
          envelope_item_id=COALESCE(cv_versions.envelope_item_id, EXCLUDED.envelope_item_id),
          person_id=COALESCE(cv_versions.person_id, EXCLUDED.person_id),
          subject_id=COALESCE(cv_versions.subject_id, EXCLUDED.subject_id),
          ownership_kind=CASE
            WHEN cv_versions.person_id IS NOT NULL OR EXCLUDED.person_id IS NOT NULL THEN 'person'
            WHEN cv_versions.subject_id IS NOT NULL OR EXCLUDED.subject_id IS NOT NULL THEN 'subject'
            ELSE COALESCE(cv_versions.ownership_kind, EXCLUDED.ownership_kind, 'legacy_document')
          END,
          provenance=EXCLUDED.provenance,
          updated_at=now()
        RETURNING cv_version_id::text AS cv_version_id
        """,
        (
            cv_version_id,
            company,
            sha,
            extracted_text_hash,
            extraction_method,
            CV_VERSION_CONTRACT,
            PROCESSING_VERSION,
            legacy_app_key,
            document_id,
            legacy_text_version_id,
            evidence_id,
            facts_id,
            envelope_item_id,
            person_id,
            subject_id,
            kind,
            _json(
                {
                    **(provenance or {}),
                    "dual_write": True,
                    "reader_cutover": False,
                    "processing_version": PROCESSING_VERSION,
                    "ownership_kind": kind,
                    "rewrites_historical_ranking": False,
                }
            ),
        ),
    )
    row = cur.fetchone() or {"cv_version_id": cv_version_id}
    cv_version_id = str(row.get("cv_version_id") or cv_version_id)

    if legacy_text_version_id:
        cur.execute(
            """
            UPDATE candidate_cv_text_versions
            SET cv_version_id=%s
            WHERE company_code=%s AND version_id=%s AND cv_version_id IS NULL
            """,
            (cv_version_id, company, legacy_text_version_id),
        )
    if evidence_id:
        cur.execute(
            """
            UPDATE application_cv_evidence_materializations
            SET cv_version_id=%s
            WHERE company_code=%s AND evidence_id=%s AND cv_version_id IS NULL
            """,
            (cv_version_id, company, evidence_id),
        )
    if facts_id:
        cur.execute(
            """
            UPDATE application_cv_fact_snapshots
            SET cv_version_id=%s
            WHERE company_code=%s AND facts_id=%s AND cv_version_id IS NULL
            """,
            (cv_version_id, company, facts_id),
        )

    record_stage_run(
        cur,
        company_code=company,
        stage="immutable_cv_version",
        status="completed",
        subject_id=document_id,
        content_sha256=sha,
        cv_version_id=cv_version_id,
        legacy_app_key=legacy_app_key,
        legacy_document_id=document_id,
        envelope_item_id=envelope_item_id,
        metadata={"legacy_text_version_id": legacy_text_version_id},
        environ=environ,
    )
    return {
        "ok": True,
        "skipped": False,
        "cv_version_id": cv_version_id,
        "reader_cutover": False,
    }


def observe_email_job_stage(
    cur: Any,
    *,
    job: dict[str, Any],
    status: str,
    result: dict[str, Any] | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Map one live email ingress job onto the shared stage ledger."""

    job_type = str(job.get("job_type") or "")
    stage = EMAIL_JOB_STAGE.get(job_type)
    if not stage:
        return {"ok": True, "skipped": True, "reason": "unmapped_job_type"}
    company = str(job.get("company_code") or "").strip().upper()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    subject_id = str(
        payload.get("candidate_document_id")
        or payload.get("document_id")
        or payload.get("submission_id")
        or job.get("subject_id")
        or job.get("job_id")
        or ""
    )
    content_sha = None
    if isinstance(result, dict):
        content_sha = result.get("content_sha256") or (result.get("evidence") or {}).get(
            "source_content_sha256"
        )
    return record_stage_run(
        cur,
        company_code=company,
        stage=stage,
        status=status,
        subject_id=subject_id,
        content_sha256=str(content_sha) if content_sha else None,
        attempt=int(job.get("attempts") or 1),
        max_attempts=int(job.get("max_attempts") or 5),
        legacy_app_key=str(payload.get("app_key") or "") or None,
        legacy_document_id=str(payload.get("document_id") or payload.get("candidate_document_id") or "")
        or None,
        legacy_job_id=str(job.get("job_id") or "") or None,
        error_code=error_code,
        error_detail=error_detail,
        metadata={
            "email_job_type": job_type,
            "result_status": (result or {}).get("status") if isinstance(result, dict) else None,
            "authoritative_path": "email_ingress",
        },
        environ=environ,
    )


def advance_envelope_processing_state(
    cur: Any,
    *,
    company_code: str,
    envelope_item_id: str,
    processing_state: str,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Optional envelope item state mirror. No-op unless envelope dual-write ON."""

    if not envelope_dual_write_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "envelope_dual_write_disabled"}
    company = _safe_company(company_code)
    cur.execute(
        """
        UPDATE intake_items
        SET processing_state=%s, updated_at=now()
        WHERE company_code=%s AND item_id=%s
        """,
        (processing_state, company, envelope_item_id),
    )
    return {"ok": True, "skipped": False, "processing_state": processing_state}


def parity_zero_duplicate_proof(counts: dict[str, int]) -> dict[str, Any]:
    """Validate staging parity counters for one email submission dual-write."""

    required = {
        "live_submissions": 1,
        "envelope_events": 1,
        "live_documents": int(counts.get("live_documents") or 0),
        "envelope_document_links": int(counts.get("envelope_document_links") or 0),
        "candidate_creates": 0,
        "application_creates": 0,
        "ocr_provider_calls": int(counts.get("ocr_provider_calls") or 0),
        "classification_writes": int(counts.get("classification_writes") or 0),
        "ck_writes": int(counts.get("ck_writes") or 0),
        "duplicate_candidate_creates": 0,
        "duplicate_application_creates": 0,
        "duplicate_ocr_writes": 0,
        "duplicate_classification_writes": 0,
        "duplicate_ck_writes": 0,
    }
    merged = {**required, **{k: int(v) for k, v in counts.items()}}
    errors: list[str] = []
    if merged["live_submissions"] != 1 or merged["envelope_events"] != 1:
        errors.append("envelope_event_parity")
    if merged["live_documents"] != merged["envelope_document_links"]:
        errors.append("document_link_parity")
    for key in (
        "duplicate_candidate_creates",
        "duplicate_application_creates",
        "duplicate_ocr_writes",
        "duplicate_classification_writes",
        "duplicate_ck_writes",
    ):
        if merged[key] != 0:
            errors.append(key)
    # Dual-write itself must not create candidates/apps; OCR/class/CK remain on live path only.
    if merged["candidate_creates"] != 0 or merged["application_creates"] != 0:
        errors.append("envelope_must_not_create_candidates_or_apps")
    return {
        "ok": not errors,
        "errors": errors,
        "counts": merged,
        "processing_version": PROCESSING_VERSION,
    }


def content_fingerprint(parts: list[str]) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "PROCESSING_VERSION",
    "CV_VERSION_CONTRACT",
    "STAGES",
    "STAGE_VERSIONS",
    "EMAIL_JOB_STAGE",
    "FEATURE_PROCESSING",
    "FEATURE_CV_VERSION_DUAL_WRITE",
    "FEATURE_STAGE_LEDGER",
    "processing_feature_enabled",
    "cv_version_dual_write_enabled",
    "stage_ledger_enabled",
    "envelope_dual_write_enabled",
    "stage_killed",
    "ensure_schema",
    "stable_cv_version_id",
    "stable_stage_run_id",
    "stage_idempotency_key",
    "ExtractionProviderPlan",
    "plan_extraction_providers",
    "record_stage_run",
    "mark_stage_retry_or_dead_letter",
    "dual_write_cv_version",
    "observe_email_job_stage",
    "advance_envelope_processing_state",
    "parity_zero_duplicate_proof",
    "content_fingerprint",
]
