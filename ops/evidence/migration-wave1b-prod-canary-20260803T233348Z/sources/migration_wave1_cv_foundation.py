"""Migration Wave 1 — Foundation contract + chunked CV intake (synthetic).

Shared batch/row/job contract for Wathefni migrations. First consumer: staged
folder / object-storage-style CV intake that reuses the bulk CV import core
(`_import_process_one_file` / `register_imported_cv`) in durable chunks.

Authority: held-by-default. Auto-admit is forced OFF on this path.
Checksum dedupe without identity auto-merge. Dry-run, exception queue, retry,
DLQ, progress, audit, rollback.

Does NOT: real customer data, millions cutover, Migration Center UI,
employee/leave/compensation migration, payroll money, attendance ingest,
AI assistant, or mobile.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from psycopg2.extras import Json

WAVE1_CONTRACT = "migration_wave1_foundation_cv_chunked"
WAVE1_VERSION = "1.0.0"

ROW_STATUSES = frozenset(
    {
        "pending",
        "valid",
        "invalid",
        "duplicate",
        "needs_review",
        "committed",
        "quarantined",
        "skipped",
        "failed",
        "rolled_back",
    }
)
BATCH_STATUSES = frozenset(
    {
        "draft",
        "staged",
        "dry_run",
        "queued",
        "running",
        "paused",
        "completed",
        "failed",
        "rolled_back",
        "cancelled",
    }
)
JOB_STATUSES = frozenset(
    {"pending", "leased", "completed", "failed", "dead_letter", "cancelled"}
)
AUTHORITY_LABELS = frozenset(
    {"held", "draft", "historical", "mirror", "needs_review", "quarantined"}
)

DEFAULT_CHUNK_SIZE = 100
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_PER_FILE_MAX_BYTES = 8 * 1024 * 1024  # align with email honesty
MIGRATION_EXTRACTION_PRIORITY = 500  # live CV/email jobs retain higher priority
EXTRACTION_POLICIES = frozenset({"enqueue", "defer"})
CV_EXTENSIONS = {".pdf", ".docx", ".doc", ".rtf", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp"}


def _flag_on(name: str, default: str = "") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def migration_wave1_enabled() -> bool:
    return _flag_on("WATHEFNI_MIGRATION_WAVE1")


def stage_root() -> Path:
    raw = (
        os.environ.get("WATHEFNI_MIGRATION_WAVE1_STAGE_ROOT")
        or os.environ.get("WATHEFNI_WORKSPACE")
        or "/tmp/wathefni-migration-wave1"
    )
    path = Path(raw) / "migration_wave1_stage"
    path.mkdir(parents=True, exist_ok=True)
    return path


def honesty_payload() -> dict[str, Any]:
    return {
        "contract": WAVE1_CONTRACT,
        "version": WAVE1_VERSION,
        "real_customer_data": False,
        "millions_claim": False,
        "migration_center_ui": False,
        "employee_leave_compensation": False,
        "payroll_money": False,
        "attendance_ingest": False,
        "ai_assistant": False,
        "mobile": False,
        "authority_default": "held",
        "auto_admit": False,
        "auto_merge": False,
        "synthetic_only": migration_wave1_synthetic_only(),
        "allowed_companies": sorted(allowed_companies() or []),
    }


def migration_wave1_synthetic_only() -> bool:
    return _flag_on("WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY", "1")


def allowed_companies() -> set[str] | None:
    """None = unrestricted (staging). Comma list = production allowlist."""
    raw = (os.environ.get("WATHEFNI_MIGRATION_WAVE1_COMPANIES") or "").strip()
    if not raw:
        return None
    return {c.strip().upper() for c in raw.split(",") if c.strip()}


def company_allowed(company_code: str) -> bool:
    allowed = allowed_companies()
    if allowed is None:
        return True
    return str(company_code or "").strip().upper() in allowed


def refuse_if_company_not_allowed(company_code: str) -> dict[str, Any] | None:
    company = str(company_code or "").strip().upper()
    if not company_allowed(company):
        return {
            "ok": False,
            "error": "company_not_allowlisted",
            "company_code": company,
            "allowed": sorted(allowed_companies() or []),
        }
    return None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS migration_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  domain text NOT NULL DEFAULT 'pre_hiring_cv',
  contract text NOT NULL DEFAULT 'migration_wave1_foundation_cv_chunked',
  contract_version text NOT NULL DEFAULT '1.0.0',
  status text NOT NULL DEFAULT 'draft',
  authority_label text NOT NULL DEFAULT 'held',
  dry_run boolean NOT NULL DEFAULT false,
  stage_uri text,
  total_rows integer NOT NULL DEFAULT 0,
  chunk_size integer NOT NULL DEFAULT 100,
  imported_count integer NOT NULL DEFAULT 0,
  duplicate_count integer NOT NULL DEFAULT 0,
  failed_count integer NOT NULL DEFAULT 0,
  quarantined_count integer NOT NULL DEFAULT 0,
  skipped_count integer NOT NULL DEFAULT 0,
  needs_review_count integer NOT NULL DEFAULT 0,
  import_batch_id uuid,
  options jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  rolled_back_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_migration_batches_company
  ON migration_batches(company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS migration_rows (
  row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES migration_batches(batch_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  row_index integer NOT NULL,
  chunk_index integer,
  status text NOT NULL DEFAULT 'pending',
  authority_label text NOT NULL DEFAULT 'held',
  source_filename text,
  content_sha256 text,
  size_bytes bigint,
  external_id text,
  app_key text,
  import_item_id uuid,
  error text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, row_index)
);
CREATE INDEX IF NOT EXISTS idx_migration_rows_batch_status
  ON migration_rows(batch_id, status, chunk_index);
CREATE INDEX IF NOT EXISTS idx_migration_rows_company_checksum
  ON migration_rows(company_code, content_sha256);
CREATE INDEX IF NOT EXISTS idx_migration_rows_external
  ON migration_rows(company_code, external_id) WHERE external_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS migration_chunk_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES migration_batches(batch_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  chunk_index integer NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  leased_by text,
  lease_expires_at timestamptz,
  available_at timestamptz NOT NULL DEFAULT now(),
  row_start integer NOT NULL,
  row_end integer NOT NULL,
  last_error text,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, chunk_index)
);
CREATE INDEX IF NOT EXISTS idx_migration_chunk_jobs_claim
  ON migration_chunk_jobs(status, available_at, created_at)
  WHERE status IN ('pending', 'failed');

CREATE TABLE IF NOT EXISTS migration_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL,
  company_code text NOT NULL,
  event_type text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_migration_events_batch
  ON migration_events(batch_id, created_at);

CREATE TABLE IF NOT EXISTS migration_wave_acks (
  ack_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  wave text NOT NULL,
  company_code text NOT NULL DEFAULT 'WATHEFNI',
  environment text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_migration_wave_acks_wave
  ON migration_wave_acks(wave, created_at DESC);
"""


def ensure_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(SCHEMA_SQL)


def record_wave_ack(
    cur: Any,
    *,
    wave: str,
    company_code: str,
    environment: str,
    detail: dict[str, Any] | None = None,
) -> str:
    cur.execute(
        """
        INSERT INTO migration_wave_acks (wave, company_code, environment, detail)
        VALUES (%s,%s,%s,%s) RETURNING ack_id::text
        """,
        (
            wave,
            str(company_code or "WATHEFNI").upper(),
            environment,
            Json(detail or {}),
        ),
    )
    return str(cur.fetchone()["ack_id"])


def record_event(cur: Any, *, batch_id: str, company_code: str, event_type: str, detail: dict[str, Any] | None = None) -> str:
    cur.execute(
        """
        INSERT INTO migration_events (batch_id, company_code, event_type, detail)
        VALUES (%s,%s,%s,%s) RETURNING event_id::text
        """,
        (batch_id, company_code.upper(), event_type, Json(detail or {})),
    )
    return str(cur.fetchone()["event_id"])


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_external_id(path: Path, sidecar_map: dict[str, str]) -> str | None:
    key = path.name.lower()
    if key in sidecar_map:
        return sidecar_map[key]
    meta = path.with_suffix(path.suffix + ".meta.json")
    if not meta.exists():
        meta = Path(str(path) + ".meta.json")
    if meta.exists():
        try:
            payload = json.loads(meta.read_text(encoding="utf-8"))
            ext = str(payload.get("external_id") or payload.get("ats_candidate_id") or "").strip()
            return ext or None
        except Exception:
            return None
    return None


def _load_sidecar_map(stage_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for name in ("external_ids.json", "manifest.json"):
        path = stage_dir / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            mapping = payload.get("files") if isinstance(payload.get("files"), dict) else payload
            if isinstance(mapping, dict):
                for k, v in mapping.items():
                    if isinstance(v, dict):
                        ext = str(v.get("external_id") or v.get("ats_candidate_id") or "").strip()
                    else:
                        ext = str(v or "").strip()
                    if ext:
                        out[str(k).lower()] = ext
        elif isinstance(payload, list):
            for row in payload:
                if not isinstance(row, dict):
                    continue
                fn = str(row.get("filename") or row.get("file") or "").strip()
                ext = str(row.get("external_id") or row.get("ats_candidate_id") or "").strip()
                if fn and ext:
                    out[fn.lower()] = ext
    # jsonl
    jl = stage_dir / "manifest.jsonl"
    if jl.exists():
        for line in jl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            fn = str(row.get("filename") or "").strip()
            ext = str(row.get("external_id") or "").strip()
            if fn and ext:
                out[fn.lower()] = ext
    return out


def list_stage_cv_files(stage_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(stage_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.name.endswith(".meta.json") or path.name in {"external_ids.json", "manifest.json", "manifest.jsonl"}:
            continue
        if path.suffix.lower() not in CV_EXTENSIONS:
            continue
        files.append(path)
    return files


def create_staged_cv_batch(
    legacy: Any,
    *,
    company_code: str,
    stage_dir: str | Path,
    dry_run: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    created_by: str | None = None,
    per_file_max_bytes: int = DEFAULT_PER_FILE_MAX_BYTES,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a staged folder as a migration batch and materialize migration_rows."""
    if not migration_wave1_enabled():
        return {"ok": False, "error": "migration_wave1_disabled"}
    company = str(company_code or "").strip().upper()
    refused = refuse_if_company_not_allowed(company)
    if refused:
        return refused
    root = Path(stage_dir)
    if not root.is_dir():
        return {"ok": False, "error": "stage_dir_missing", "stage_dir": str(root)}
    files = list_stage_cv_files(root)
    if not files:
        return {"ok": False, "error": "no_cv_files", "stage_dir": str(root)}
    sidecar = _load_sidecar_map(root)
    chunk_size = max(1, int(chunk_size or DEFAULT_CHUNK_SIZE))
    batch_options = dict(options or {})
    extraction_policy = str(batch_options.get("extraction_policy") or "enqueue").strip().lower()
    if extraction_policy not in EXTRACTION_POLICIES:
        return {
            "ok": False,
            "error": "invalid_extraction_policy",
            "extraction_policy": extraction_policy,
            "allowed": sorted(EXTRACTION_POLICIES),
        }
    batch_options["extraction_policy"] = extraction_policy

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                INSERT INTO migration_batches
                  (company_code, domain, status, authority_label, dry_run, stage_uri,
                   total_rows, chunk_size, options, metadata, created_by)
                VALUES (%s,'pre_hiring_cv','staged','held',%s,%s,%s,%s,%s,%s,%s)
                RETURNING batch_id::text
                """,
                (
                    company,
                    bool(dry_run),
                    str(root),
                    len(files),
                    chunk_size,
                    Json({**batch_options, **honesty_payload(), "per_file_max_bytes": per_file_max_bytes}),
                    Json({"wave": "migration_wave1", "synthetic": True}),
                    created_by,
                ),
            )
            batch_id = str(cur.fetchone()["batch_id"])
            for idx, path in enumerate(files):
                data = path.read_bytes()
                checksum = _sha256_bytes(data)
                size = len(data)
                status = "pending"
                error = None
                if size > per_file_max_bytes:
                    status = "invalid"
                    error = f"file_too_large:{size}>{per_file_max_bytes}"
                external_id = _read_external_id(path, sidecar)
                rel = str(path.relative_to(root))
                cur.execute(
                    """
                    INSERT INTO migration_rows
                      (batch_id, company_code, row_index, status, authority_label,
                       source_filename, content_sha256, size_bytes, external_id, error, detail)
                    VALUES (%s,%s,%s,%s,'held',%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        batch_id,
                        company,
                        idx,
                        status,
                        rel,
                        checksum,
                        size,
                        external_id,
                        error,
                        Json({"abs_path": str(path)}),
                    ),
                )
            # Build chunk jobs for non-invalid rows
            cur.execute(
                """
                SELECT row_index FROM migration_rows
                WHERE batch_id=%s AND status='pending'
                ORDER BY row_index
                """,
                (batch_id,),
            )
            pending_idxs = [int(r["row_index"]) for r in cur.fetchall()]
            jobs = 0
            for chunk_i, start in enumerate(range(0, len(pending_idxs), chunk_size)):
                slice_idxs = pending_idxs[start : start + chunk_size]
                if not slice_idxs:
                    continue
                row_start, row_end = slice_idxs[0], slice_idxs[-1]
                cur.execute(
                    """
                    UPDATE migration_rows SET chunk_index=%s, updated_at=now()
                    WHERE batch_id=%s AND row_index = ANY(%s)
                    """,
                    (chunk_i, batch_id, slice_idxs),
                )
                cur.execute(
                    """
                    INSERT INTO migration_chunk_jobs
                      (batch_id, company_code, chunk_index, status, max_attempts, row_start, row_end)
                    VALUES (%s,%s,%s,'pending',%s,%s,%s)
                    """,
                    (batch_id, company, chunk_i, DEFAULT_MAX_ATTEMPTS, row_start, row_end),
                )
                jobs += 1
            record_event(
                cur,
                batch_id=batch_id,
                company_code=company,
                event_type="batch_staged",
                detail={"files": len(files), "chunks": jobs, "dry_run": bool(dry_run)},
            )
            cur.execute(
                "UPDATE migration_batches SET status=%s, updated_at=now() WHERE batch_id=%s",
                ("dry_run" if dry_run else "queued", batch_id),
            )
        conn.commit()
    return {
        "ok": True,
        "batch_id": batch_id,
        "company_code": company,
        "total_rows": len(files),
        "chunks": jobs,
        "dry_run": bool(dry_run),
        "extraction_policy": extraction_policy,
        "stage_dir": str(root),
        "honesty": honesty_payload(),
    }


def batch_progress(legacy: Any, *, batch_id: str, company_code: str) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                "SELECT * FROM migration_batches WHERE batch_id=%s AND company_code=%s LIMIT 1",
                (batch_id, company),
            )
            batch = cur.fetchone()
            if not batch:
                return {"ok": False, "error": "batch_not_found"}
            cur.execute(
                """
                SELECT status, count(*)::int AS c FROM migration_rows
                WHERE batch_id=%s GROUP BY status
                """,
                (batch_id,),
            )
            by_status = {str(r["status"]): int(r["c"]) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT status, count(*)::int AS c FROM migration_chunk_jobs
                WHERE batch_id=%s GROUP BY status
                """,
                (batch_id,),
            )
            jobs = {str(r["status"]): int(r["c"]) for r in cur.fetchall()}
    return {
        "ok": True,
        "batch": dict(batch),
        "rows_by_status": by_status,
        "jobs_by_status": jobs,
        "honesty": honesty_payload(),
    }


def exception_queue(legacy: Any, *, batch_id: str, company_code: str, limit: int = 200) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT row_id::text, row_index, status, source_filename, content_sha256,
                       external_id, error, detail, authority_label
                FROM migration_rows
                WHERE batch_id=%s AND company_code=%s
                  AND status = ANY(%s)
                ORDER BY row_index
                LIMIT %s
                """,
                (
                    batch_id,
                    company,
                    ["invalid", "duplicate", "failed", "quarantined", "needs_review"],
                    int(limit),
                ),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"ok": True, "batch_id": batch_id, "exceptions": rows, "count": len(rows)}


def _claim_chunk_job(
    cur: Any,
    *,
    company_code: str | None,
    worker_id: str,
    batch_id: str | None = None,
    lease_seconds: int = 180,
) -> dict[str, Any] | None:
    company = str(company_code or "").strip().upper() or None
    cur.execute(
        """
        WITH cte AS (
          SELECT job_id FROM migration_chunk_jobs
          WHERE status IN ('pending', 'failed')
            AND available_at <= now()
            AND (%s::text IS NULL OR company_code=%s)
            AND (%s::uuid IS NULL OR batch_id=%s::uuid)
          ORDER BY created_at
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE migration_chunk_jobs j
        SET status='leased',
            leased_by=%s,
            lease_expires_at=now() + (%s || ' seconds')::interval,
            attempts=j.attempts + 1,
            updated_at=now()
        FROM cte WHERE j.job_id=cte.job_id
        RETURNING j.*
        """,
        (company, company, batch_id, batch_id, worker_id, str(int(lease_seconds))),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _process_chunk(
    legacy: Any,
    cur: Any,
    *,
    job: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    """Process one chunk. Auto-admit forced OFF. Reuses import core on commit."""
    batch_id = str(job["batch_id"])
    company = str(job["company_code"]).upper()
    chunk_index = int(job["chunk_index"])
    cur.execute(
        """
        SELECT * FROM migration_rows
        WHERE batch_id=%s AND chunk_index=%s AND status='pending'
        ORDER BY row_index
        """,
        (batch_id, chunk_index),
    )
    rows = [dict(r) for r in cur.fetchall()]
    counts = {"committed": 0, "duplicate": 0, "failed": 0, "invalid": 0, "skipped": 0}
    seen: dict[str, str] = {}
    # Seed seen with already processed checksums in this batch (cross-chunk dedupe)
    cur.execute(
        """
        SELECT content_sha256, app_key, status FROM migration_rows
        WHERE batch_id=%s AND content_sha256 IS NOT NULL
          AND status IN ('committed', 'valid', 'duplicate')
        """,
        (batch_id,),
    )
    for r in cur.fetchall():
        if r.get("content_sha256"):
            seen[str(r["content_sha256"])] = str(r.get("app_key") or r.get("status") or "prior")

    company_positions = legacy._import_load_company_positions(cur, company)
    cur.execute(
        "SELECT options FROM migration_batches WHERE batch_id=%s AND company_code=%s",
        (batch_id, company),
    )
    batch_row = cur.fetchone() or {}
    batch_options = (
        dict(batch_row.get("options") or {})
        if isinstance(batch_row.get("options"), dict)
        else {}
    )
    extraction_policy = str(
        batch_options.get("extraction_policy") or "enqueue"
    ).strip().lower()
    if extraction_policy not in EXTRACTION_POLICIES:
        raise ValueError(f"invalid_extraction_policy:{extraction_policy}")
    import_batch_id = None
    if not dry_run:
        cur.execute(
            "SELECT import_batch_id::text AS id FROM migration_batches WHERE batch_id=%s",
            (batch_id,),
        )
        existing = cur.fetchone()
        import_batch_id = (existing or {}).get("id")
        if not import_batch_id:
            cur.execute(
                """
                INSERT INTO import_batches
                  (company_code, source, status, created_by_user_id, total_files, options, metadata)
                VALUES (%s,'other_ats_export','processing',%s,%s,%s,%s)
                RETURNING batch_id::text
                """,
                (
                    company,
                    f"migration_wave1:{batch_id}",
                    int(job.get("row_end") or 0) - int(job.get("row_start") or 0) + 1,
                    Json({"migration_batch_id": batch_id, "auto_admit": False}),
                    Json({"wave": "migration_wave1"}),
                ),
            )
            import_batch_id = str(cur.fetchone()["batch_id"])
            cur.execute(
                "UPDATE migration_batches SET import_batch_id=%s, updated_at=now() WHERE batch_id=%s",
                (import_batch_id, batch_id),
            )

    for row in rows:
        path = Path(str((row.get("detail") or {}).get("abs_path") or ""))
        filename = str(row.get("source_filename") or path.name)
        checksum = str(row.get("content_sha256") or "")
        external_id = row.get("external_id")
        if not path.exists():
            cur.execute(
                """
                UPDATE migration_rows SET status='failed', error='stage_file_missing', updated_at=now()
                WHERE row_id=%s
                """,
                (row["row_id"],),
            )
            counts["failed"] += 1
            continue
        data = path.read_bytes()
        if dry_run:
            # Validate-only: checksum dups + extension + size already checked
            if checksum in seen:
                cur.execute(
                    """
                    UPDATE migration_rows
                    SET status='duplicate', error='duplicate_in_batch', detail=detail || %s::jsonb, updated_at=now()
                    WHERE row_id=%s
                    """,
                    (Json({"duplicate_of": seen[checksum], "external_id": external_id}), row["row_id"]),
                )
                counts["duplicate"] += 1
                continue
            cur.execute(
                """
                SELECT subject_key FROM file_registry
                WHERE company_code=%s AND file_kind='candidate_cv' AND content_sha256=%s
                ORDER BY updated_at DESC LIMIT 1
                """,
                (company, checksum),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE migration_rows
                    SET status='duplicate', error='duplicate_existing_cv',
                        detail=detail || %s::jsonb, updated_at=now()
                    WHERE row_id=%s
                    """,
                    (Json({"duplicate_of_app_key": existing.get("subject_key")}), row["row_id"]),
                )
                counts["duplicate"] += 1
                continue
            seen[checksum] = f"dry:{filename}"
            cur.execute(
                """
                UPDATE migration_rows
                SET status='valid', detail=detail || %s::jsonb, updated_at=now()
                WHERE row_id=%s
                """,
                (Json({"dry_run": True, "external_id": external_id}), row["row_id"]),
            )
            counts["committed"] += 1  # counted as would-import
            continue

        # Commit path — force auto_admit_enabled=False
        meta: dict[str, str] = {}
        if external_id:
            meta["external_id"] = str(external_id)
        item = legacy._import_process_one_file(
            cur,
            company=company,
            batch_id=str(import_batch_id),
            source="other_ats_export",
            company_positions=company_positions,
            filename=Path(filename).name,
            data=data,
            seen_checksums=seen,
            meta=meta,
            auto_admit_enabled=False,
            extraction_policy=extraction_policy,
            extraction_job_context={
                "migration_batch_id": batch_id,
                "migration_contract": WAVE1_CONTRACT,
                "workload_class": "migration",
                "synthetic": bool(
                    (batch_options.get("synthetic") is True)
                    or batch_options.get("real_customer_data") is False
                ),
            },
            extraction_priority=MIGRATION_EXTRACTION_PRIORITY,
        )
        # Preserve external_id on item metadata
        item_meta = dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {}
        if external_id:
            item_meta["external_id"] = external_id
            item_meta["ats_candidate_id"] = external_id
        item["metadata"] = item_meta
        item_id = legacy._import_insert_item(cur, batch_id=str(import_batch_id), company=company, item_record=item)
        status = str(item.get("status") or "failed")
        app_key = item.get("app_key")
        err = item.get("error")
        # Map import statuses onto migration row statuses
        if status in {"imported", "needs_role", "import_review", "review"} or item.get("ok"):
            mig_status = "committed"
            # Verify held authority
            if app_key:
                cur.execute("SELECT status FROM applications WHERE app_key=%s AND company_code=%s LIMIT 1", (app_key, company))
                app = cur.fetchone()
                app_status = str((app or {}).get("status") or "")
                if app_status == "review_pending":
                    # Should not happen with auto_admit False — quarantine if it did
                    mig_status = "quarantined"
                    err = f"unexpected_auto_admit_status:{app_status}"
                elif app_status and app_status not in legacy.HELD_IMPORT_STATUSES:
                    mig_status = "quarantined"
                    err = f"not_held:{app_status}"
            if mig_status == "committed":
                counts["committed"] += 1
            else:
                counts["failed"] += 1
        elif status == "duplicate" or str(err or "").startswith("duplicate"):
            mig_status = "duplicate"
            counts["duplicate"] += 1
        else:
            mig_status = "failed"
            counts["failed"] += 1
        # Stamp external_id onto application raw_json when present
        if app_key and external_id and mig_status == "committed":
            cur.execute(
                """
                UPDATE applications
                SET raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE app_key=%s AND company_code=%s
                """,
                (
                    Json(
                        {
                            "import": {
                                "external_id": external_id,
                                "ats_candidate_id": external_id,
                                "migration_batch_id": batch_id,
                                "authority_label": "held",
                                "auto_admit": False,
                            }
                        }
                    ),
                    app_key,
                    company,
                ),
            )
        cur.execute(
            """
            UPDATE migration_rows
            SET status=%s, app_key=%s, import_item_id=%s, error=%s,
                detail=detail || %s::jsonb, updated_at=now()
            WHERE row_id=%s
            """,
            (
                mig_status,
                app_key,
                item_id,
                err,
                Json(
                    {
                        "import_status": status,
                        "external_id": external_id,
                        "extraction_policy": extraction_policy,
                        "intake_job_id": item.get("intake_job_id"),
                        "extraction_deferred": bool(item.get("extraction_deferred")),
                    }
                ),
                row["row_id"],
            ),
        )
    return {"counts": counts, "import_batch_id": import_batch_id, "processed": len(rows)}


def run_worker(
    legacy: Any,
    *,
    company_code: str | None = None,
    batch_id: str | None = None,
    limit: int = 10,
    worker_id: str | None = None,
) -> dict[str, Any]:
    if not migration_wave1_enabled():
        return {"ok": False, "error": "migration_wave1_disabled"}
    worker_id = worker_id or f"migw1-{uuid.uuid4().hex[:8]}"
    processed = []
    dead = 0
    # Runtime workers must not execute DDL in the same transaction as chunk
    # inserts. Schema is migrated once before claims, reducing relation-lock
    # deadlocks with the intake worker and app startup.
    with legacy.db_connect() as schema_conn:
        with schema_conn.cursor() as schema_cur:
            ensure_schema(schema_cur)
        schema_conn.commit()
    for _ in range(max(1, int(limit))):
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                job = _claim_chunk_job(
                    cur,
                    company_code=company_code,
                    worker_id=worker_id,
                    batch_id=batch_id,
                )
                if not job:
                    conn.commit()
                    break
                cur.execute(
                    "SELECT dry_run, status FROM migration_batches WHERE batch_id=%s",
                    (job["batch_id"],),
                )
                batch = cur.fetchone() or {}
                dry_run = bool(batch.get("dry_run"))
                cur.execute(
                    "UPDATE migration_batches SET status='running', updated_at=now() WHERE batch_id=%s AND status = ANY(%s)",
                    (job["batch_id"], ["queued", "dry_run", "paused", "running", "staged"]),
                )
                try:
                    cur.execute("SAVEPOINT migration_wave1_chunk_attempt")
                    # Synthetic-only inject: fail first N attempts so retry/DLQ can be proven.
                    inject_until = int(os.environ.get("WATHEFNI_MIGRATION_WAVE1_INJECT_FAIL_UNTIL", "0") or "0")
                    if inject_until > 0 and int(job.get("attempts") or 1) <= inject_until:
                        raise RuntimeError("injected_migration_wave1_fail")
                    inject_db_until = int(
                        os.environ.get(
                            "WATHEFNI_MIGRATION_WAVE1_INJECT_DB_ERROR_UNTIL",
                            "0",
                        )
                        or "0"
                    )
                    if (
                        inject_db_until > 0
                        and int(job.get("attempts") or 1) <= inject_db_until
                    ):
                        # Synthetic test only: proves savepoint recovery from an
                        # aborted PostgreSQL transaction without creating a real
                        # deadlock or racing production workers.
                        cur.execute("SELECT 1/0")
                    result = _process_chunk(legacy, cur, job=job, dry_run=dry_run)
                    cur.execute("RELEASE SAVEPOINT migration_wave1_chunk_attempt")
                    cur.execute(
                        """
                        UPDATE migration_chunk_jobs
                        SET status='completed', result=%s, last_error=NULL, updated_at=now(),
                            leased_by=NULL, lease_expires_at=NULL
                        WHERE job_id=%s
                        """,
                        (Json(result), job["job_id"]),
                    )
                    record_event(
                        cur,
                        batch_id=str(job["batch_id"]),
                        company_code=str(job["company_code"]),
                        event_type="chunk_completed",
                        detail={"job_id": str(job["job_id"]), "chunk_index": job["chunk_index"], **result},
                    )
                    processed.append({"job_id": str(job["job_id"]), "ok": True, **result})
                except Exception as exc:
                    # PostgreSQL errors (including deadlocks) abort the current
                    # transaction. Restore it to a usable state before recording
                    # retry/DLQ state; the whole chunk attempt is rolled back.
                    cur.execute("ROLLBACK TO SAVEPOINT migration_wave1_chunk_attempt")
                    cur.execute("RELEASE SAVEPOINT migration_wave1_chunk_attempt")
                    attempts = int(job.get("attempts") or 1)
                    max_attempts = int(job.get("max_attempts") or DEFAULT_MAX_ATTEMPTS)
                    if attempts >= max_attempts:
                        status = "dead_letter"
                        dead += 1
                    else:
                        status = "failed"
                    pgcode = str(getattr(exc, "pgcode", "") or "")
                    is_deadlock = pgcode == "40P01" or "deadlock" in str(exc).lower()
                    cur.execute(
                        """
                        UPDATE migration_chunk_jobs
                        SET status=%s, last_error=%s,
                            available_at=now() + (%s || ' seconds')::interval,
                            leased_by=NULL, lease_expires_at=NULL, updated_at=now()
                        WHERE job_id=%s
                        """,
                        (
                            status,
                            f"{'deadlock_retry:' if is_deadlock else ''}{str(exc)}"[:500],
                            "1" if is_deadlock else "0",
                            job["job_id"],
                        ),
                    )
                    record_event(
                        cur,
                        batch_id=str(job["batch_id"]),
                        company_code=str(job["company_code"]),
                        event_type="chunk_failed" if status != "dead_letter" else "chunk_dead_letter",
                        detail={
                            "job_id": str(job["job_id"]),
                            "error": str(exc)[:500],
                            "attempts": attempts,
                            "pgcode": pgcode or None,
                            "deadlock_retry": is_deadlock,
                        },
                    )
                    processed.append({"job_id": str(job["job_id"]), "ok": False, "status": status, "error": str(exc)[:200]})
                # Refresh batch counters
                _refresh_batch_counts(cur, batch_id=str(job["batch_id"]))
            conn.commit()
    return {"ok": True, "worker_id": worker_id, "processed": processed, "dead_letter": dead}


def _refresh_batch_counts(cur: Any, *, batch_id: str) -> None:
    cur.execute(
        """
        SELECT
          count(*) FILTER (WHERE status='committed')::int AS imported_count,
          count(*) FILTER (WHERE status='duplicate')::int AS duplicate_count,
          count(*) FILTER (WHERE status='failed')::int AS failed_count,
          count(*) FILTER (WHERE status='quarantined')::int AS quarantined_count,
          count(*) FILTER (WHERE status='skipped')::int AS skipped_count,
          count(*) FILTER (WHERE status='needs_review')::int AS needs_review_count,
          count(*) FILTER (WHERE status='pending')::int AS pending_count,
          count(*) FILTER (WHERE status='valid')::int AS valid_count
        FROM migration_rows WHERE batch_id=%s
        """,
        (batch_id,),
    )
    c = dict(cur.fetchone() or {})
    cur.execute(
        """
        SELECT
          count(*) FILTER (WHERE status='pending')::int AS pending_jobs,
          count(*) FILTER (WHERE status='failed')::int AS failed_jobs,
          count(*) FILTER (WHERE status='dead_letter')::int AS dead_jobs,
          count(*) FILTER (WHERE status='completed')::int AS done_jobs,
          count(*)::int AS total_jobs
        FROM migration_chunk_jobs WHERE batch_id=%s
        """,
        (batch_id,),
    )
    j = dict(cur.fetchone() or {})
    status = "running"
    if int(j.get("dead_jobs") or 0) and int(j.get("pending_jobs") or 0) == 0 and int(j.get("failed_jobs") or 0) == 0:
        status = "failed"
    elif int(j.get("pending_jobs") or 0) == 0 and int(j.get("failed_jobs") or 0) == 0 and int(c.get("pending_count") or 0) == 0:
        status = "completed"
    cur.execute(
        """
        UPDATE migration_batches SET
          imported_count=%s, duplicate_count=%s, failed_count=%s,
          quarantined_count=%s, skipped_count=%s, needs_review_count=%s,
          status=%s,
          completed_at=CASE WHEN %s='completed' THEN now() ELSE completed_at END,
          updated_at=now()
        WHERE batch_id=%s
        """,
        (
            int(c.get("imported_count") or 0) + int(c.get("valid_count") or 0),
            int(c.get("duplicate_count") or 0),
            int(c.get("failed_count") or 0),
            int(c.get("quarantined_count") or 0),
            int(c.get("skipped_count") or 0),
            int(c.get("needs_review_count") or 0),
            status,
            status,
            batch_id,
        ),
    )


def run_until_idle(
    legacy: Any,
    *,
    batch_id: str,
    company_code: str,
    max_loops: int = 5000,
    worker_burst: int = 20,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    loops = 0
    while loops < max_loops:
        loops += 1
        out = run_worker(
            legacy,
            company_code=company,
            batch_id=batch_id,
            limit=worker_burst,
        )
        prog = batch_progress(legacy, batch_id=batch_id, company_code=company)
        batch = prog.get("batch") or {}
        jobs = prog.get("jobs_by_status") or {}
        pending = int(jobs.get("pending") or 0) + int(jobs.get("failed") or 0) + int(jobs.get("leased") or 0)
        if pending == 0 or batch.get("status") in {"completed", "failed", "rolled_back"}:
            return {"ok": True, "loops": loops, "progress": prog, "last_worker": out}
        if not (out.get("processed") or []):
            # reclaim stuck leases
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE migration_chunk_jobs
                        SET status='pending', leased_by=NULL, lease_expires_at=NULL, available_at=now(), updated_at=now()
                        WHERE batch_id=%s AND status='leased' AND lease_expires_at < now()
                        """,
                        (batch_id,),
                    )
                conn.commit()
            time.sleep(0.05)
    return {"ok": False, "error": "max_loops", "loops": loops, "progress": batch_progress(legacy, batch_id=batch_id, company_code=company)}


def _cancel_active_extraction_jobs(
    cur: Any,
    *,
    batch_id: str,
    company_code: str,
    app_keys: list[str],
    document_ids: list[str],
) -> dict[str, Any]:
    """Cancel active CV extraction work before deleting its source records."""
    active = ["pending", "running", "retrying", "waiting_quota", "waiting_budget"]
    cur.execute(
        """
        WITH targets AS (
          SELECT job_id, status AS old_status, company_code
          FROM intake_processing_jobs
          WHERE company_code=%s
            AND job_type='cv_extraction'
            AND status = ANY(%s)
            AND (
              payload->>'migration_batch_id'=%s
              OR payload->>'app_key' = ANY(%s)
              OR coalesce(payload->>'candidate_document_id', subject_id) = ANY(%s)
            )
          FOR UPDATE
        ),
        updated AS (
          UPDATE intake_processing_jobs j
          SET status='cancelled',
              completed_at=now(),
              lease_owner=NULL,
              lease_expires_at=NULL,
              last_error_code='migration_batch_rolled_back',
              last_error_detail=%s,
              updated_at=now()
          FROM targets t
          WHERE j.job_id=t.job_id
          RETURNING j.job_id, j.company_code, t.old_status
        )
        INSERT INTO intake_processing_job_events
          (job_id, company_code, event_type, from_status, to_status,
           error_code, error_detail, metadata)
        SELECT job_id, company_code, 'migration_batch_rollback_cancel',
               old_status, 'cancelled', 'migration_batch_rolled_back',
               %s, %s
        FROM updated
        RETURNING job_id::text
        """,
        (
            company_code,
            active,
            batch_id,
            app_keys,
            document_ids,
            f"migration batch {batch_id} rolled back",
            f"migration batch {batch_id} rolled back",
            Json({"migration_batch_id": batch_id, "authority": "held"}),
        ),
    )
    cancelled_ids = [str(r["job_id"]) for r in cur.fetchall()]
    cur.execute(
        """
        SELECT status, count(*)::int AS c
        FROM intake_processing_jobs
        WHERE company_code=%s
          AND job_type='cv_extraction'
          AND payload->>'migration_batch_id'=%s
        GROUP BY status
        """,
        (company_code, batch_id),
    )
    by_status = {str(r["status"]): int(r["c"]) for r in cur.fetchall()}
    active_remaining = sum(int(by_status.get(s) or 0) for s in active)
    return {
        "cancelled": len(cancelled_ids),
        "job_ids": cancelled_ids,
        "by_status": by_status,
        "active_remaining": active_remaining,
    }


def batch_residual(
    legacy: Any,
    *,
    batch_id: str,
    company_code: str,
) -> dict[str, Any]:
    """Count active records and queue work that would invalidate residual zero."""
    company = str(company_code or "").strip().upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)::int AS c
                FROM migration_rows r
                JOIN applications a
                  ON a.app_key=r.app_key AND a.company_code=r.company_code
                WHERE r.batch_id=%s AND r.company_code=%s
                """,
                (batch_id, company),
            )
            applications = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*)::int AS c
                FROM migration_rows r
                JOIN candidate_documents d ON d.app_key=r.app_key
                WHERE r.batch_id=%s AND r.company_code=%s
                """,
                (batch_id, company),
            )
            documents = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT status, count(*)::int AS c
                FROM intake_processing_jobs
                WHERE company_code=%s
                  AND job_type='cv_extraction'
                  AND payload->>'migration_batch_id'=%s
                GROUP BY status
                """,
                (company, batch_id),
            )
            queue_by_status = {str(r["status"]): int(r["c"]) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT count(*)::int AS c
                FROM migration_rows
                WHERE batch_id=%s AND company_code=%s AND status='committed'
                """,
                (batch_id, company),
            )
            committed_rows = int(cur.fetchone()["c"])
    active_statuses = {"pending", "running", "retrying", "waiting_quota", "waiting_budget"}
    queue_active = sum(int(queue_by_status.get(s) or 0) for s in active_statuses)
    total_active = applications + documents + committed_rows + queue_active
    return {
        "batch_id": batch_id,
        "company_code": company,
        "applications": applications,
        "candidate_documents": documents,
        "committed_rows": committed_rows,
        "queue_jobs_active": queue_active,
        "queue_jobs_by_status": queue_by_status,
        "total_active": total_active,
    }


def _rollback_batch_once(legacy: Any, *, batch_id: str, company_code: str) -> dict[str, Any]:
    """Roll back committed held applications created by this migration batch."""
    company = str(company_code or "").strip().upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                "SELECT * FROM migration_batches WHERE batch_id=%s AND company_code=%s LIMIT 1",
                (batch_id, company),
            )
            batch = cur.fetchone()
            if not batch:
                return {"ok": False, "error": "batch_not_found"}
            cur.execute(
                """
                SELECT app_key FROM migration_rows
                WHERE batch_id=%s AND company_code=%s AND app_key IS NOT NULL AND status='committed'
                """,
                (batch_id, company),
            )
            app_keys = [str(r["app_key"]) for r in cur.fetchall() if r.get("app_key")]
            document_ids: list[str] = []
            if app_keys:
                cur.execute(
                    "SELECT document_id::text FROM candidate_documents WHERE app_key = ANY(%s)",
                    (app_keys,),
                )
                document_ids = [
                    str(r["document_id"]) for r in cur.fetchall() if r.get("document_id")
                ]
            extraction_jobs = _cancel_active_extraction_jobs(
                cur,
                batch_id=batch_id,
                company_code=company,
                app_keys=app_keys,
                document_ids=document_ids,
            )
            if extraction_jobs["active_remaining"] != 0:
                raise RuntimeError(
                    f"migration_extraction_jobs_active_after_cancel:{extraction_jobs['active_remaining']}"
                )
            deleted = {
                "applications": 0,
                "documents": 0,
                "files": 0,
                "candidates": 0,
                "extraction_jobs_cancelled": extraction_jobs["cancelled"],
            }
            if app_keys:
                cur.execute("DELETE FROM candidate_documents WHERE app_key = ANY(%s) RETURNING document_id", (app_keys,))
                deleted["documents"] = cur.rowcount
                cur.execute(
                    "DELETE FROM file_registry WHERE company_code=%s AND subject_key = ANY(%s) RETURNING file_id",
                    (company, app_keys),
                )
                deleted["files"] = cur.rowcount
                cur.execute(
                    """
                    DELETE FROM application_lifecycle_events
                    WHERE app_key = ANY(%s) OR (company_code=%s AND app_key = ANY(%s))
                    """,
                    (app_keys, company, app_keys),
                )
                # Collect surrogate phones before deleting applications
                cur.execute(
                    "SELECT DISTINCT phone FROM applications WHERE app_key = ANY(%s) AND company_code=%s",
                    (app_keys, company),
                )
                phones = [str(r["phone"]) for r in cur.fetchall() if r.get("phone")]
                cur.execute(
                    "DELETE FROM applications WHERE company_code=%s AND app_key = ANY(%s) RETURNING app_key",
                    (company, app_keys),
                )
                deleted["applications"] = cur.rowcount
                # Delete import-surrogate candidates that no longer have applications
                if phones:
                    cur.execute(
                        """
                        DELETE FROM candidates c
                        WHERE c.phone = ANY(%s)
                          AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.phone=c.phone)
                        """,
                        (phones,),
                    )
                    deleted["candidates"] = cur.rowcount
            import_batch_id = batch.get("import_batch_id")
            if import_batch_id:
                cur.execute("DELETE FROM import_items WHERE batch_id=%s AND company_code=%s", (import_batch_id, company))
                cur.execute("DELETE FROM import_batches WHERE batch_id=%s AND company_code=%s", (import_batch_id, company))
            cur.execute(
                """
                UPDATE migration_rows SET status='rolled_back', updated_at=now()
                WHERE batch_id=%s AND status='committed'
                """,
                (batch_id,),
            )
            cur.execute(
                """
                UPDATE migration_chunk_jobs SET status='cancelled', updated_at=now()
                WHERE batch_id=%s AND status IN ('pending','failed','leased')
                """,
                (batch_id,),
            )
            cur.execute(
                """
                UPDATE migration_batches
                SET status='rolled_back', rolled_back_at=now(), updated_at=now()
                WHERE batch_id=%s
                """,
                (batch_id,),
            )
            record_event(
                cur,
                batch_id=batch_id,
                company_code=company,
                event_type="batch_rolled_back",
                detail={
                    "deleted": deleted,
                    "app_keys": len(app_keys),
                    "extraction_jobs": extraction_jobs,
                },
            )
        conn.commit()
    residual = batch_residual(
        legacy,
        batch_id=batch_id,
        company_code=company,
    )
    if residual["total_active"] != 0:
        return {
            "ok": False,
            "error": "rollback_residual_nonzero",
            "batch_id": batch_id,
            "deleted": deleted,
            "extraction_jobs": extraction_jobs,
            "residual": residual,
        }
    return {
        "ok": True,
        "batch_id": batch_id,
        "deleted": deleted,
        "app_keys": len(app_keys),
        "extraction_jobs": extraction_jobs,
        "residual": residual,
    }


def rollback_batch(
    legacy: Any,
    *,
    batch_id: str,
    company_code: str,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Deadlock-safe wrapper around transactional batch rollback."""
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        try:
            result = _rollback_batch_once(
                legacy,
                batch_id=batch_id,
                company_code=company_code,
            )
            result["rollback_attempts"] = attempt
            return result
        except Exception as exc:
            pgcode = str(getattr(exc, "pgcode", "") or "")
            deadlock = pgcode == "40P01" or "deadlock" in str(exc).lower()
            if not deadlock or attempt >= attempts:
                raise
            time.sleep(0.2 * attempt)
    raise RuntimeError("rollback_attempts_exhausted")


def replay_dead_letters(legacy: Any, *, batch_id: str, company_code: str) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE migration_chunk_jobs
                SET status='pending', attempts=0, available_at=now(), last_error=NULL, updated_at=now()
                WHERE batch_id=%s AND company_code=%s AND status='dead_letter'
                RETURNING job_id::text
                """,
                (batch_id, company),
            )
            ids = [r["job_id"] for r in cur.fetchall()]
            if ids:
                cur.execute(
                    "UPDATE migration_batches SET status='queued', updated_at=now() WHERE batch_id=%s",
                    (batch_id,),
                )
                record_event(
                    cur,
                    batch_id=batch_id,
                    company_code=company,
                    event_type="dead_letters_replayed",
                    detail={"jobs": ids},
                )
        conn.commit()
    return {"ok": True, "replayed": len(ids), "job_ids": ids}


def generate_synthetic_cvs(
    target_dir: str | Path,
    *,
    count: int,
    company_code: str = "WATHEFNI",
    with_external_ids: bool = True,
    duplicate_every: int | None = None,
) -> dict[str, Any]:
    """Write tiny unique .txt CV fixtures (synthetic only)."""
    root = Path(target_dir)
    root.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    written = 0
    dup_src: bytes | None = None
    for i in range(int(count)):
        name = f"cv_{i:06d}.txt"
        if duplicate_every and i > 0 and i % int(duplicate_every) == 0 and dup_src is not None:
            body = dup_src
        else:
            body = (
                f"SYNTHETIC CV {i}\ncompany={company_code}\n"
                f"marker=migration_wave1\nnonce={uuid.uuid4().hex}\n"
            ).encode("utf-8")
            if dup_src is None:
                dup_src = body
        (root / name).write_bytes(body)
        if with_external_ids:
            ext = f"ATS-{company_code}-{i:06d}"
            mapping[name] = ext
            (root / f"{name}.meta.json").write_text(
                json.dumps({"external_id": ext, "ats_candidate_id": ext}),
                encoding="utf-8",
            )
        written += 1
    if mapping:
        (root / "external_ids.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    return {"ok": True, "dir": str(root), "count": written, "external_ids": len(mapping)}
