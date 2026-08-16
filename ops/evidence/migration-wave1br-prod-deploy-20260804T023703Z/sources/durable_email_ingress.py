"""Durable, tenant-scoped Postmark email ingress foundation.

This module owns only the source-intake boundary:

* durable message/submission/document metadata
* backend-neutral quarantine object storage (``QuarantineStorage``)
* a Postgres leased processing queue (approved production queue)
* backend-neutral malware scanning (``MalwareScanner``)
* safety states, retry/dead-letter mechanics, quotas, and operator summaries

Candidate/application authority remains in ``app.py`` and is invoked only by an
explicit background job after a source document is marked clean.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import uuid
import zipfile
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from psycopg2.extras import Json

from intake_malware_scanner import (
    MalwareScanResult,
    build_malware_scanner_from_env,
)
from intake_quarantine_storage import (
    LocalVolumeQuarantineStorage,
    QuarantineConflictError,
    QuarantineIntegrityError,
    QuarantineMissingError,
    QuarantineStorageError,
)
import inbound_cv_intake as _inbound_cv_intake


UTC = timezone.utc
_ID_NAMESPACE = uuid.UUID("313cd3e9-4161-45ed-96ea-eae435b0b1b4")

JOB_TYPES = frozenset(
    {
        "intake_validation",
        "file_safety_scan",
        "cv_identity_resolution",
        "accepted_intake_preparation",
        # Wave D6A: non-accepted identity still materializes a Held application
        # (or fails loudly) so durable completion is never silent.
        "held_intake_materialization",
        "cv_extraction",
        "profile_structuring",
        "embedding",
        "sender_acknowledgment",
        "retention_privacy",
    }
)

JOB_ACTIVE_STATUSES = frozenset(
    {"pending", "running", "retrying", "waiting_quota", "waiting_budget"}
)
JOB_TERMINAL_STATUSES = frozenset({"completed", "dead_letter", "cancelled"})

SAFETY_STATES = frozenset(
    {
        "scan_pending",
        "clean",
        "quarantined",
        "malware_suspicious",
        "unsupported_type",
        "mime_mismatch",
        "password_protected",
        "too_large",
        "invalid_corrupt",
    }
)

# Permanent first-production accept list. Legacy DOC/RTF and arbitrary ZIP
# remain rejected. Text/Markdown are intentionally excluded.
SUPPORTED_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".webp"}
)


class IngressError(RuntimeError):
    code = "ingress_error"
    http_status = 503

    def __init__(self, code: str | None = None, detail: str | None = None) -> None:
        self.code = code or self.code
        self.detail = detail or self.code
        super().__init__(self.detail)


class IngressValidationError(IngressError):
    code = "invalid_inbound_payload"
    http_status = 400


class IngressLimitError(IngressError):
    code = "inbound_body_too_large"
    http_status = 413


class IngressDurabilityError(IngressError):
    code = "inbound_durability_unavailable"
    http_status = 503


class RetryableJobError(RuntimeError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


class DeferredJob(RuntimeError):
    def __init__(
        self,
        status: str,
        code: str,
        available_at: datetime,
        detail: str | None = None,
    ) -> None:
        if status not in {"waiting_quota", "waiting_budget"}:
            raise ValueError("invalid_deferred_job_status")
        self.status = status
        self.code = code
        self.available_at = available_at
        self.detail = detail or code
        super().__init__(self.detail)


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        return max(minimum, int(str(os.environ.get(name, default)).strip()))
    except (TypeError, ValueError):
        return max(minimum, default)


@dataclass(frozen=True)
class IngressConfig:
    quarantine_root: Path
    max_webhook_body_bytes: int
    max_attachments: int
    max_file_bytes: int
    max_total_attachment_bytes: int
    max_pdf_pages: int
    max_image_pixels: int
    max_archive_members: int
    max_archive_expanded_bytes: int
    max_archive_ratio: int
    orphan_grace_seconds: int
    lease_seconds: int
    max_attempts: int
    retry_base_seconds: int
    retry_max_seconds: int
    per_tenant_concurrency: int
    daily_message_quota: int
    monthly_message_quota: int
    daily_source_bytes_quota: int
    monthly_source_bytes_quota: int
    daily_processing_job_quota: int
    malware_scanner: str

    @classmethod
    def from_env(cls, workspace: Path | str | None = None) -> "IngressConfig":
        base = Path(workspace or os.environ.get("WATHEFNI_WORKSPACE") or ".")
        root = Path(
            os.environ.get("WATHEFNI_INTAKE_QUARANTINE_DIR")
            or base / "quarantine" / "email-intake"
        )
        return cls(
            quarantine_root=root,
            # First-production configurable safety defaults (not temporary
            # architecture limits). Commercial quotas stay disabled (zero)
            # until an owner approves them.
            max_webhook_body_bytes=_env_int(
                "WATHEFNI_INTAKE_MAX_WEBHOOK_BYTES", 24 * 1024 * 1024, minimum=1024
            ),
            max_attachments=_env_int(
                "WATHEFNI_INTAKE_MAX_ATTACHMENTS", 12, minimum=1
            ),
            max_file_bytes=_env_int(
                "WATHEFNI_INTAKE_MAX_FILE_BYTES", 8 * 1024 * 1024, minimum=1024
            ),
            max_total_attachment_bytes=_env_int(
                "WATHEFNI_INTAKE_MAX_TOTAL_BYTES", 12 * 1024 * 1024, minimum=1024
            ),
            max_pdf_pages=_env_int("WATHEFNI_INTAKE_MAX_PDF_PAGES", 40, minimum=1),
            max_image_pixels=_env_int(
                "WATHEFNI_INTAKE_MAX_IMAGE_PIXELS", 30_000_000, minimum=1
            ),
            max_archive_members=_env_int(
                "WATHEFNI_INTAKE_MAX_ARCHIVE_MEMBERS", 200, minimum=1
            ),
            max_archive_expanded_bytes=_env_int(
                "WATHEFNI_INTAKE_MAX_ARCHIVE_EXPANDED_BYTES",
                32 * 1024 * 1024,
                minimum=1024,
            ),
            max_archive_ratio=_env_int(
                "WATHEFNI_INTAKE_MAX_ARCHIVE_RATIO", 100, minimum=1
            ),
            orphan_grace_seconds=_env_int(
                "WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS", 24 * 60 * 60, minimum=60
            ),
            lease_seconds=_env_int(
                "WATHEFNI_INTAKE_JOB_LEASE_SECONDS", 180, minimum=30
            ),
            max_attempts=_env_int(
                "WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS", 5, minimum=1
            ),
            retry_base_seconds=_env_int(
                "WATHEFNI_INTAKE_RETRY_BASE_SECONDS", 5, minimum=1
            ),
            retry_max_seconds=_env_int(
                "WATHEFNI_INTAKE_RETRY_MAX_SECONDS", 900, minimum=1
            ),
            per_tenant_concurrency=_env_int(
                "WATHEFNI_INTAKE_TENANT_CONCURRENCY", 2, minimum=1
            ),
            daily_message_quota=_env_int(
                "WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA", 0
            ),
            monthly_message_quota=_env_int(
                "WATHEFNI_INTAKE_MONTHLY_MESSAGE_QUOTA", 0
            ),
            daily_source_bytes_quota=_env_int(
                "WATHEFNI_INTAKE_DAILY_SOURCE_BYTES_QUOTA", 0
            ),
            monthly_source_bytes_quota=_env_int(
                "WATHEFNI_INTAKE_MONTHLY_SOURCE_BYTES_QUOTA", 0
            ),
            daily_processing_job_quota=_env_int(
                "WATHEFNI_INTAKE_DAILY_PROCESSING_JOB_QUOTA", 0
            ),
            malware_scanner=str(
                os.environ.get("WATHEFNI_INTAKE_MALWARE_SCANNER") or "clamav"
            )
            .strip()
            .lower(),
        )


SCHEMA_SQL = """
ALTER TABLE IF EXISTS inbound_messages
  ADD COLUMN IF NOT EXISTS submission_id uuid;
ALTER TABLE IF EXISTS inbound_messages
  ADD COLUMN IF NOT EXISTS durable_at timestamptz;
ALTER TABLE IF EXISTS inbound_messages
  ADD COLUMN IF NOT EXISTS durability_latency_ms integer;
ALTER TABLE IF EXISTS inbound_messages
  ADD COLUMN IF NOT EXISTS route_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS inbound_messages
  ADD COLUMN IF NOT EXISTS source_provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE IF EXISTS inbound_messages
  ADD COLUMN IF NOT EXISTS total_attachment_bytes bigint NOT NULL DEFAULT 0;
ALTER TABLE IF EXISTS inbound_messages
  ADD COLUMN IF NOT EXISTS processing_error_code text;

CREATE TABLE IF NOT EXISTS intake_submissions (
  submission_id uuid PRIMARY KEY,
  inbound_id uuid NOT NULL UNIQUE REFERENCES inbound_messages(inbound_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  intake_id uuid NOT NULL,
  provider text NOT NULL,
  provider_message_id text NOT NULL,
  source_channel text NOT NULL DEFAULT 'email_inbound',
  envelope_recipient text NOT NULL,
  sender_address text,
  subject text,
  received_at timestamptz,
  route_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  attachment_count integer NOT NULL DEFAULT 0,
  accepted_attachment_count integer NOT NULL DEFAULT 0,
  total_attachment_bytes bigint NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'durable',
  quota_state text,
  import_batch_id uuid,
  durable_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, provider, provider_message_id)
);

CREATE TABLE IF NOT EXISTS intake_documents (
  document_id uuid PRIMARY KEY,
  submission_id uuid NOT NULL REFERENCES intake_submissions(submission_id) ON DELETE CASCADE,
  inbound_id uuid NOT NULL REFERENCES inbound_messages(inbound_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  attachment_ordinal integer NOT NULL,
  original_filename text,
  claimed_mime text,
  detected_mime text,
  size_bytes bigint,
  content_sha256 text,
  quarantine_key text,
  storage_status text NOT NULL DEFAULT 'pending',
  safety_state text NOT NULL DEFAULT 'scan_pending',
  safety_reason_code text,
  duplicate_of_document_id uuid,
  app_key text,
  file_id uuid,
  candidate_document_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  scan_engine text,
  scan_signature_version text,
  scanned_at timestamptz,
  scan_result text,
  scan_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, inbound_id, attachment_ordinal)
);

ALTER TABLE IF EXISTS intake_documents
  ADD COLUMN IF NOT EXISTS scan_engine text;
ALTER TABLE IF EXISTS intake_documents
  ADD COLUMN IF NOT EXISTS scan_signature_version text;
ALTER TABLE IF EXISTS intake_documents
  ADD COLUMN IF NOT EXISTS scanned_at timestamptz;
ALTER TABLE IF EXISTS intake_documents
  ADD COLUMN IF NOT EXISTS scan_result text;
ALTER TABLE IF EXISTS intake_documents
  ADD COLUMN IF NOT EXISTS scan_evidence jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS intake_processing_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  job_type text NOT NULL,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  priority integer NOT NULL DEFAULT 100,
  status text NOT NULL DEFAULT 'pending',
  available_at timestamptz NOT NULL DEFAULT now(),
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  lease_owner text,
  lease_expires_at timestamptz,
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb,
  last_error_code text,
  last_error_detail text,
  replay_count integer NOT NULL DEFAULT 0,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, idempotency_key)
);
ALTER TABLE intake_processing_jobs
  ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS intake_processing_job_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES intake_processing_jobs(job_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  event_type text NOT NULL,
  from_status text,
  to_status text,
  error_code text,
  error_detail text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intake_tenant_queue_state (
  company_code text PRIMARY KEY,
  running_jobs integer NOT NULL DEFAULT 0,
  last_claimed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS intake_quota_usage (
  company_code text NOT NULL,
  period_kind text NOT NULL,
  period_start date NOT NULL,
  messages bigint NOT NULL DEFAULT 0,
  attachments bigint NOT NULL DEFAULT 0,
  source_bytes bigint NOT NULL DEFAULT 0,
  processed_jobs bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, period_kind, period_start)
);

CREATE OR REPLACE FUNCTION prevent_intake_submission_provenance_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.company_code IS DISTINCT FROM OLD.company_code
     OR NEW.intake_id IS DISTINCT FROM OLD.intake_id
     OR NEW.provider IS DISTINCT FROM OLD.provider
     OR NEW.provider_message_id IS DISTINCT FROM OLD.provider_message_id
     OR NEW.envelope_recipient IS DISTINCT FROM OLD.envelope_recipient
     OR NEW.sender_address IS DISTINCT FROM OLD.sender_address
     OR NEW.route_snapshot IS DISTINCT FROM OLD.route_snapshot
     OR NEW.source_provenance IS DISTINCT FROM OLD.source_provenance THEN
    RAISE EXCEPTION 'intake_submission_provenance_is_immutable';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS intake_submission_provenance_immutable
  ON intake_submissions;
CREATE TRIGGER intake_submission_provenance_immutable
BEFORE UPDATE ON intake_submissions
FOR EACH ROW EXECUTE FUNCTION prevent_intake_submission_provenance_mutation();

CREATE OR REPLACE FUNCTION prevent_intake_document_source_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.company_code IS DISTINCT FROM OLD.company_code
     OR NEW.submission_id IS DISTINCT FROM OLD.submission_id
     OR NEW.inbound_id IS DISTINCT FROM OLD.inbound_id
     OR NEW.attachment_ordinal IS DISTINCT FROM OLD.attachment_ordinal
     OR NEW.original_filename IS DISTINCT FROM OLD.original_filename
     OR NEW.claimed_mime IS DISTINCT FROM OLD.claimed_mime
     OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes
     OR NEW.content_sha256 IS DISTINCT FROM OLD.content_sha256
     OR NEW.quarantine_key IS DISTINCT FROM OLD.quarantine_key THEN
    RAISE EXCEPTION 'intake_document_source_is_immutable';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS intake_document_source_immutable
  ON intake_documents;
CREATE TRIGGER intake_document_source_immutable
BEFORE UPDATE ON intake_documents
FOR EACH ROW EXECUTE FUNCTION prevent_intake_document_source_mutation();

CREATE INDEX IF NOT EXISTS idx_intake_submissions_company_created
  ON intake_submissions(company_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intake_submissions_status
  ON intake_submissions(company_code, status, created_at);
CREATE INDEX IF NOT EXISTS idx_intake_documents_submission
  ON intake_documents(company_code, submission_id, attachment_ordinal);
CREATE INDEX IF NOT EXISTS idx_intake_documents_safety
  ON intake_documents(company_code, safety_state, updated_at);
CREATE INDEX IF NOT EXISTS idx_intake_documents_checksum
  ON intake_documents(company_code, content_sha256)
  WHERE content_sha256 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_intake_jobs_claim
  ON intake_processing_jobs(status, available_at, priority, created_at)
  WHERE status IN ('pending','retrying','waiting_quota','waiting_budget');
CREATE INDEX IF NOT EXISTS idx_intake_jobs_company
  ON intake_processing_jobs(company_code, status, created_at);
CREATE INDEX IF NOT EXISTS idx_intake_jobs_lease
  ON intake_processing_jobs(lease_expires_at)
  WHERE status='running';
CREATE INDEX IF NOT EXISTS idx_intake_job_events_job
  ON intake_processing_job_events(job_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inbound_messages_submission
  ON inbound_messages(submission_id) WHERE submission_id IS NOT NULL;
"""


REQUIRED_TABLES = [
    "inbound_messages",
    "intake_submissions",
    "intake_documents",
]


def apply_schema(cur: Any) -> None:
    import schema_contract as _schema

    _schema.apply_sql(
        cur,
        SCHEMA_SQL,
        module="durable_email_ingress",
        lock_id=770_911_103,
    )
    _inbound_cv_intake.apply_schema(cur)
    import inbound_cv_processing as _inbound_cv_processing

    _inbound_cv_processing.apply_schema(cur)


def require_schema(cur: Any) -> None:
    import schema_contract as _schema

    _schema.require_relations(cur, REQUIRED_TABLES, module="durable_email_ingress")
    _inbound_cv_intake.require_schema(cur)
    import inbound_cv_processing as _inbound_cv_processing

    _inbound_cv_processing.require_schema(cur)


def ensure_schema(cur: Any) -> None:
    """Runtime-safe: validate only unless WATHEFNI_SCHEMA_APPLY is enabled."""

    import schema_contract as _schema

    if _schema.schema_apply_allowed():
        apply_schema(cur)
    else:
        require_schema(cur)


def stable_inbound_id(provider: str, provider_message_id: str) -> str:
    return str(
        uuid.uuid5(
            _ID_NAMESPACE,
            f"wathefni:intake:{provider.strip().lower()}:{provider_message_id.strip()}",
        )
    )


def stable_submission_id(inbound_id: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:submission:{inbound_id}"))


def stable_document_id(inbound_id: str, ordinal: int) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:document:{inbound_id}:{ordinal}"))


def _safe_company(value: str | None) -> str:
    company = re.sub(r"[^A-Z0-9_-]", "", str(value or "").strip().upper())
    if not company:
        raise IngressValidationError("company_scope_missing")
    return company


def _safe_filename(value: str | None) -> str:
    name = Path(str(value or "attachment")).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return name[:255] or "attachment"


def detect_mime(data: bytes) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" in names and "word/document.xml" in names:
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except Exception:
            return "application/zip"
        return "application/zip"
    if data.startswith(b"{\\rtf"):
        return "application/rtf"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "application/msword"
    try:
        text = data.decode("utf-8")
        if "\x00" not in text:
            return "text/plain"
    except UnicodeDecodeError:
        pass
    return "application/octet-stream"


class LocalQuarantineStore:
    """Compatibility facade over ``LocalVolumeQuarantineStorage``.

    Staging uses this local-volume adapter on an encrypted mount. Production's
    first real deployment should switch to ``S3CompatibleQuarantineStorage``
    via ``WATHEFNI_INTAKE_QUARANTINE_BACKEND`` without changing intake
    authority.
    """

    backend_name = LocalVolumeQuarantineStorage.backend_name

    def __init__(self, root: Path | str) -> None:
        self._impl = LocalVolumeQuarantineStorage(root)
        self.root = self._impl.root

    def object_key(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
    ) -> str:
        try:
            return self._impl.object_key(
                company_code=company_code,
                inbound_id=inbound_id,
                ordinal=ordinal,
                content_sha256=content_sha256,
            )
        except QuarantineStorageError as exc:
            raise IngressValidationError(exc.code, exc.detail) from exc

    def path_for_key(self, key: str) -> Path:
        try:
            return self._impl.path_for_key(key)
        except QuarantineStorageError as exc:
            raise IngressValidationError(exc.code, exc.detail) from exc

    def write(
        self,
        *,
        company_code: str,
        inbound_id: str,
        ordinal: int,
        content_sha256: str,
        data: bytes,
    ) -> tuple[str, bool]:
        try:
            ref = self._impl.write(
                company_code=company_code,
                inbound_id=inbound_id,
                ordinal=ordinal,
                content_sha256=content_sha256,
                data=data,
            )
        except QuarantineConflictError as exc:
            raise IngressDurabilityError(exc.code, exc.detail) from exc
        except QuarantineStorageError as exc:
            raise IngressDurabilityError(exc.code, exc.detail) from exc
        return ref.key, ref.reused

    def verify(self, key: str, expected_sha256: str, expected_size: int) -> Path:
        try:
            self._impl.verify(key, expected_sha256, expected_size)
            return self._impl.path_for_key(key)
        except QuarantineMissingError as exc:
            raise RetryableJobError(exc.code, exc.detail) from exc
        except QuarantineIntegrityError as exc:
            raise RetryableJobError(exc.code, exc.detail) from exc
        except QuarantineStorageError as exc:
            raise RetryableJobError(exc.code, exc.detail) from exc

    def iter_object_keys(self) -> Iterable[tuple[str, Path]]:
        for key in self._impl.iter_object_keys():
            yield key, self._impl.path_for_key(key)

    def health(self) -> dict[str, Any]:
        return self._impl.health()

    def delete(self, key: str) -> bool:
        return bool(self._impl.delete(key))


def _parse_email_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except Exception:
        return None


def _parse_email_address(value: Any) -> str | None:
    from email.utils import parseaddr

    address = parseaddr(str(value or ""))[1].strip().lower()
    return address or None


def _spam_and_auth(payload: dict[str, Any]) -> tuple[float | None, bool, dict[str, str]]:
    score: float | None = None
    flagged = False
    auth: dict[str, str] = {}
    for raw in payload.get("Headers") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("Name") or "").strip().lower()
        value = str(raw.get("Value") or "").strip()
        if name == "x-spam-score":
            try:
                score = float(value)
            except ValueError:
                pass
        elif name == "x-spam-status" and value.lower().startswith("yes"):
            flagged = True
        elif name in {"authentication-results", "received-spf", "dkim-signature"}:
            auth[name] = value[:2000]
    return score, flagged, auth


def _decode_attachment(raw: dict[str, Any]) -> bytes:
    value = raw.get("Content")
    if not isinstance(value, str) or not value.strip():
        raise IngressValidationError("attachment_content_missing")
    compact = re.sub(r"\s+", "", value)
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise IngressValidationError("attachment_base64_invalid") from exc


def _period_starts(now: datetime) -> tuple[date, date]:
    current = now.astimezone(UTC)
    return current.date(), current.date().replace(day=1)


def _next_period(now: datetime, kind: str) -> datetime:
    current = now.astimezone(UTC)
    if kind == "day":
        return datetime.combine(current.date() + timedelta(days=1), datetime.min.time(), UTC)
    if current.month == 12:
        return datetime(current.year + 1, 1, 1, tzinfo=UTC)
    return datetime(current.year, current.month + 1, 1, tzinfo=UTC)


def _record_quota_usage(
    cur: Any,
    *,
    company_code: str,
    messages: int,
    attachments: int,
    source_bytes: int,
    now: datetime,
) -> dict[str, dict[str, int]]:
    day, month = _period_starts(now)
    rows: dict[str, dict[str, int]] = {}
    for kind, start in (("day", day), ("month", month)):
        cur.execute(
            """
            INSERT INTO intake_quota_usage
              (company_code, period_kind, period_start, messages, attachments, source_bytes)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company_code, period_kind, period_start) DO UPDATE
            SET messages=intake_quota_usage.messages + EXCLUDED.messages,
                attachments=intake_quota_usage.attachments + EXCLUDED.attachments,
                source_bytes=intake_quota_usage.source_bytes + EXCLUDED.source_bytes,
                updated_at=now()
            RETURNING messages, attachments, source_bytes, processed_jobs
            """,
            (company_code, kind, start, messages, attachments, source_bytes),
        )
        rows[kind] = {k: int(v or 0) for k, v in dict(cur.fetchone()).items()}
    return rows


def _quota_state(
    usage: dict[str, dict[str, int]], config: IngressConfig
) -> tuple[str | None, str | None]:
    """Hard path only: queue (waiting_quota). Never reject for volume."""
    checks = (
        ("daily_message_quota", "day", "messages", config.daily_message_quota),
        ("monthly_message_quota", "month", "messages", config.monthly_message_quota),
        ("daily_source_bytes_quota", "day", "source_bytes", config.daily_source_bytes_quota),
        (
            "monthly_source_bytes_quota",
            "month",
            "source_bytes",
            config.monthly_source_bytes_quota,
        ),
    )
    for code, period, metric, limit in checks:
        if limit > 0 and usage.get(period, {}).get(metric, 0) > limit:
            return "waiting_quota", code
    return None, None


def _enterprise_quota_decision(
    usage: dict[str, dict[str, int]],
    *,
    company_code: str,
    config: IngressConfig,
    tenant_policy: dict[str, Any] | None = None,
) -> tuple[str | None, str | None, list[str]]:
    """Prefer enterprise soft-warn + queue semantics when a tenant policy is present."""
    if not tenant_policy:
        status, code = _quota_state(usage, config)
        return status, code, []
    try:
        import inbound_enterprise_hardening as _ieh

        settings = tenant_policy.get("settings") if isinstance(tenant_policy.get("settings"), dict) else None
        decision = _ieh.evaluate_quota(
            usage,
            company_code=company_code,
            settings=settings,
            base_config=config,
        )
        return decision.status, decision.code, list(decision.soft_warnings)
    except Exception:
        status, code = _quota_state(usage, config)
        return status, code, []


def enqueue_job(
    cur: Any,
    *,
    company_code: str,
    job_type: str,
    subject_type: str,
    subject_id: str,
    idempotency_key: str,
    payload: dict[str, Any] | None = None,
    priority: int = 100,
    status: str = "pending",
    available_at: datetime | None = None,
    max_attempts: int = 5,
) -> str:
    if job_type not in JOB_TYPES:
        raise ValueError(f"unsupported_intake_job_type:{job_type}")
    if status not in JOB_ACTIVE_STATUSES:
        raise ValueError(f"invalid_initial_job_status:{status}")
    cur.execute(
        """
        INSERT INTO intake_processing_jobs
          (company_code, job_type, subject_type, subject_id, priority, status,
           available_at, max_attempts, idempotency_key, payload)
        VALUES (%s,%s,%s,%s,%s,%s,COALESCE(%s,now()),%s,%s,%s)
        ON CONFLICT (company_code, idempotency_key) DO UPDATE
        SET updated_at=now()
        RETURNING job_id::text
        """,
        (
            _safe_company(company_code),
            job_type,
            subject_type,
            str(subject_id),
            int(priority),
            status,
            available_at,
            int(max_attempts),
            idempotency_key,
            Json(payload or {}),
        ),
    )
    job_id = str(cur.fetchone()["job_id"])
    try:
        import tenant_control_queue_gate as _tc_qg

        _tc_qg.persist_work_epoch(
            cur,
            company_code=_safe_company(company_code),
            work_kind=f"durable_email:{job_type}",
            work_ref=job_id,
            module_key="pre_hiring",
        )
    except Exception:
        pass
    return job_id


def _call_failpoint(
    failpoint: Callable[[str], None] | None, name: str
) -> None:
    if failpoint is not None:
        failpoint(name)


def apply_quota_overrides(config: IngressConfig, overrides: dict[str, int] | None) -> IngressConfig:
    if not overrides:
        return config
    allowed: dict[str, int] = {}
    for key, value in overrides.items():
        if not hasattr(config, key):
            continue
        if key.endswith("_quota") or key == "per_tenant_concurrency":
            try:
                allowed[key] = int(value)
            except (TypeError, ValueError):
                continue
    if not allowed:
        return config
    return replace(config, **allowed)


def durably_receive_postmark(
    payload: dict[str, Any],
    *,
    db_connect: Callable[[], Any],
    resolve_intake_address: Callable[[Any, str | None, str | None], dict[str, Any] | None],
    config: IngressConfig,
    store: LocalQuarantineStore | None = None,
    payload_size_bytes: int | None = None,
    failpoint: Callable[[str], None] | None = None,
    now: datetime | None = None,
    tenant_quota_resolver: Callable[[str], dict[str, int] | None] | None = None,
    tenant_policy_resolver: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise IngressValidationError("invalid_payload")
    started = datetime.now(UTC)
    now = (now or started).astimezone(UTC)
    if payload_size_bytes is not None and payload_size_bytes > config.max_webhook_body_bytes:
        raise IngressLimitError("inbound_body_too_large")

    provider = "postmark"
    provider_message_id = str(payload.get("MessageID") or "").strip()
    if not provider_message_id:
        raise IngressValidationError("provider_message_id_required")

    recipient = str(payload.get("OriginalRecipient") or "").strip()
    if not recipient:
        to_full = payload.get("ToFull") or []
        if isinstance(to_full, list) and to_full:
            first = to_full[0] if isinstance(to_full[0], dict) else {}
            recipient = str(first.get("Email") or "").strip()
    if not recipient:
        recipient = str(payload.get("To") or "").strip()
    if not recipient:
        raise IngressValidationError("envelope_recipient_required")

    mailbox_hash = str(payload.get("MailboxHash") or "").strip() or None
    attachments = [
        item for item in (payload.get("Attachments") or []) if isinstance(item, dict)
    ]
    inbound_id = stable_inbound_id(provider, provider_message_id)
    submission_id = stable_submission_id(inbound_id)
    sender = _parse_email_address(
        (payload.get("FromFull") or {}).get("Email")
        if isinstance(payload.get("FromFull"), dict)
        else payload.get("From")
    ) or _parse_email_address(payload.get("From"))
    subject = str(payload.get("Subject") or "").strip()[:1000] or None
    received_at = _parse_email_date(payload.get("Date"))
    spam_score, spam_flagged, auth_results = _spam_and_auth(payload)
    try:
        spam_threshold = float(
            os.environ.get("WATHEFNI_INBOUND_SPAM_THRESHOLD", "5.0") or "5.0"
        )
    except ValueError:
        spam_threshold = 5.0
    spam_flagged = bool(
        spam_flagged or (spam_score is not None and spam_score >= spam_threshold)
    )
    store = store or LocalQuarantineStore(config.quarantine_root)

    written_keys: list[str] = []
    try:
        with db_connect() as conn:
            with conn.cursor() as cur:
                ensure_schema(cur)
                cur.execute(
                    """
                    INSERT INTO inbound_messages
                      (inbound_id, provider, provider_message_id, from_address,
                       envelope_recipient, subject, received_at, spam_score,
                       auth_results, attachment_count, status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'received')
                    ON CONFLICT (provider, provider_message_id) DO NOTHING
                    """,
                    (
                        inbound_id,
                        provider,
                        provider_message_id,
                        sender,
                        recipient,
                        subject,
                        received_at,
                        spam_score,
                        Json(auth_results),
                        len(attachments),
                    ),
                )
                cur.execute(
                    """
                    SELECT inbound_id::text, company_code, status, submission_id::text,
                           durable_at
                    FROM inbound_messages
                    WHERE provider=%s AND provider_message_id=%s
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (provider, provider_message_id),
                )
                existing = dict(cur.fetchone() or {})
                intake = resolve_intake_address(cur, recipient, mailbox_hash)
                if existing.get("durable_at"):
                    routed_company = (
                        _safe_company(intake.get("company_code")) if intake else None
                    )
                    if (
                        routed_company != existing.get("company_code")
                        or str(existing.get("inbound_id") or "") != inbound_id
                    ):
                        raise IngressValidationError(
                            "provider_message_route_conflict"
                        )
                    conn.commit()
                    return {
                        "duplicate": True,
                        "durable": True,
                        "inbound_id": existing.get("inbound_id"),
                        "submission_id": existing.get("submission_id"),
                        "company_code": existing.get("company_code"),
                        "status": existing.get("status"),
                    }

                if not intake:
                    cur.execute(
                        """
                        UPDATE inbound_messages
                        SET status='rejected', error='unknown_recipient',
                            processing_error_code='unknown_recipient',
                            durable_at=now(), updated_at=now()
                        WHERE inbound_id=%s
                        """,
                        (inbound_id,),
                    )
                    _call_failpoint(failpoint, "before_unknown_recipient_commit")
                    conn.commit()
                    return {
                        "durable": True,
                        "ignored": "unknown_recipient",
                        "inbound_id": inbound_id,
                    }

                company = _safe_company(intake.get("company_code"))
                intake_id = str(intake.get("intake_id") or "")
                if not intake_id:
                    raise IngressValidationError("intake_route_id_missing")
                tenant_policy: dict[str, Any] | None = None
                if tenant_policy_resolver is not None:
                    try:
                        tenant_policy = tenant_policy_resolver(company) or {}
                        limits = tenant_policy.get("limits") if isinstance(tenant_policy.get("limits"), dict) else tenant_policy
                        config = apply_quota_overrides(config, limits if isinstance(limits, dict) else None)
                        if tenant_policy.get("per_tenant_concurrency") is not None:
                            config = apply_quota_overrides(
                                config,
                                {"per_tenant_concurrency": int(tenant_policy["per_tenant_concurrency"])},
                            )
                    except Exception:
                        tenant_policy = None
                elif tenant_quota_resolver is not None:
                    try:
                        config = apply_quota_overrides(
                            config, tenant_quota_resolver(company) or {}
                        )
                    except Exception:
                        # Fail open to global config — never block durable receipt on quota lookup.
                        pass
                route_snapshot = {
                    "intake_id": intake_id,
                    "company_code": company,
                    "envelope_recipient": recipient,
                    "mailbox_hash": mailbox_hash,
                    "position_code": intake.get("position_code"),
                    "position_title": intake.get("position_title"),
                    "label": intake.get("label"),
                }
                source_provenance = {
                    "provider": provider,
                    "provider_message_id": provider_message_id,
                    "sender_address": sender,
                    "received_at": received_at.isoformat() if received_at else None,
                    "spam_flagged": spam_flagged,
                }
                cur.execute(
                    """
                    INSERT INTO intake_submissions
                      (submission_id, inbound_id, company_code, intake_id, provider,
                       provider_message_id, envelope_recipient, sender_address, subject,
                       received_at, route_snapshot, source_provenance, attachment_count,
                       status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'receiving')
                    ON CONFLICT (submission_id) DO NOTHING
                    """,
                    (
                        submission_id,
                        inbound_id,
                        company,
                        intake_id,
                        provider,
                        provider_message_id,
                        recipient,
                        sender,
                        subject,
                        received_at,
                        Json(route_snapshot),
                        Json(source_provenance),
                        len(attachments),
                    ),
                )

                total_stored = 0
                accepted_count = 0
                seen_hashes: dict[str, str] = {}
                document_rows: list[dict[str, Any]] = []
                for ordinal, raw_attachment in enumerate(attachments, start=1):
                    document_id = stable_document_id(inbound_id, ordinal)
                    filename = _safe_filename(raw_attachment.get("Name"))
                    claimed_mime = (
                        str(raw_attachment.get("ContentType") or "").strip().lower()
                        or None
                    )
                    state = "scan_pending"
                    reason = None
                    storage_status = "pending"
                    data: bytes | None = None
                    digest = None
                    detected_mime = None
                    quarantine_key = None
                    duplicate_of = None
                    metadata: dict[str, Any] = {}

                    if ordinal > config.max_attachments:
                        state = "too_large"
                        reason = "attachment_count_limit"
                        storage_status = "rejected"
                    else:
                        try:
                            data = _decode_attachment(raw_attachment)
                        except IngressValidationError as exc:
                            state = "invalid_corrupt"
                            reason = exc.code
                            storage_status = "rejected"
                        if data is not None:
                            digest = hashlib.sha256(data).hexdigest()
                            detected_mime = detect_mime(data)
                            metadata["provider_content_length"] = raw_attachment.get(
                                "ContentLength"
                            )
                            if len(data) > config.max_file_bytes:
                                state = "too_large"
                                reason = "per_file_byte_limit"
                                storage_status = "rejected"
                            elif total_stored + len(data) > config.max_total_attachment_bytes:
                                state = "too_large"
                                reason = "total_attachment_byte_limit"
                                storage_status = "rejected"
                            else:
                                _call_failpoint(failpoint, "before_quarantine_write")
                                quarantine_key, reused = store.write(
                                    company_code=company,
                                    inbound_id=inbound_id,
                                    ordinal=ordinal,
                                    content_sha256=digest,
                                    data=data,
                                )
                                written_keys.append(quarantine_key)
                                _call_failpoint(failpoint, "after_quarantine_write")
                                storage_status = "stored"
                                total_stored += len(data)
                                accepted_count += 1
                                metadata["object_reused"] = reused
                                duplicate_of = seen_hashes.get(digest)
                                seen_hashes.setdefault(digest, document_id)
                                if spam_flagged:
                                    state = "quarantined"
                                    reason = "provider_spam_signal"

                    cur.execute(
                        """
                        INSERT INTO intake_documents
                          (document_id, submission_id, inbound_id, company_code,
                           attachment_ordinal, original_filename, claimed_mime,
                           detected_mime, size_bytes, content_sha256, quarantine_key,
                           storage_status, safety_state, safety_reason_code,
                           duplicate_of_document_id, metadata)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (company_code, inbound_id, attachment_ordinal)
                        DO UPDATE SET updated_at=now()
                        """,
                        (
                            document_id,
                            submission_id,
                            inbound_id,
                            company,
                            ordinal,
                            filename,
                            claimed_mime,
                            detected_mime,
                            len(data) if data is not None else None,
                            digest,
                            quarantine_key,
                            storage_status,
                            state,
                            reason,
                            duplicate_of,
                            Json(metadata),
                        ),
                    )
                    document_rows.append(
                        {
                            "document_id": document_id,
                            "ordinal": ordinal,
                            "filename": filename,
                            "storage_status": storage_status,
                            "safety_state": state,
                            "reason": reason,
                            "duplicate_of_document_id": duplicate_of,
                            "content_sha256": digest,
                        }
                    )

                usage = _record_quota_usage(
                    cur,
                    company_code=company,
                    messages=1,
                    attachments=accepted_count,
                    source_bytes=total_stored,
                    now=now,
                )
                waiting_status, quota_code, soft_warnings = _enterprise_quota_decision(
                    usage,
                    company_code=company,
                    config=config,
                    tenant_policy=tenant_policy,
                )
                # Tenant kill switch: durable hold — never drop legitimate mail.
                if tenant_policy and tenant_policy.get("kill_switch"):
                    waiting_status = waiting_status or "waiting_budget"
                    quota_code = quota_code or "tenant_kill_switch"
                if soft_warnings:
                    route_snapshot["quota_soft_warnings"] = soft_warnings
                    route_snapshot["never_reject_for_volume"] = True
                available_at = None
                if quota_code:
                    if quota_code == "tenant_kill_switch":
                        available_at = now + timedelta(hours=1)
                    else:
                        available_at = _next_period(
                            now, "month" if quota_code.startswith("monthly") else "day"
                        )
                job_id = enqueue_job(
                    cur,
                    company_code=company,
                    job_type="intake_validation",
                    subject_type="intake_submission",
                    subject_id=submission_id,
                    idempotency_key=f"submission:{submission_id}:validate",
                    payload={"submission_id": submission_id},
                    priority=50 if route_snapshot.get("position_code") else 100,
                    status=waiting_status or "pending",
                    available_at=available_at,
                    max_attempts=config.max_attempts,
                )
                if not job_id:
                    raise IngressDurabilityError(
                        "intake_validation_enqueue_failed",
                        "durable intake validation job was not created",
                    )
                cur.execute(
                    """
                    SELECT count(*)::int AS n
                    FROM intake_processing_jobs
                    WHERE company_code=%s
                      AND (
                        subject_id=%s
                        OR payload->>'submission_id'=%s
                        OR idempotency_key=%s
                      )
                    """,
                    (
                        company,
                        submission_id,
                        submission_id,
                        f"submission:{submission_id}:validate",
                    ),
                )
                if int((cur.fetchone() or {}).get("n") or 0) < 1:
                    raise IngressDurabilityError(
                        "intake_durable_without_jobs",
                        "refusing durable submission with zero processing jobs",
                    )
                cur.execute(
                    """
                    INSERT INTO intake_tenant_queue_state (company_code)
                    VALUES (%s) ON CONFLICT (company_code) DO NOTHING
                    """,
                    (company,),
                )
                durable_latency_ms = max(
                    0, int((datetime.now(UTC) - started).total_seconds() * 1000)
                )
                cur.execute(
                    """
                    UPDATE intake_submissions
                    SET accepted_attachment_count=%s, total_attachment_bytes=%s,
                        status=%s, quota_state=%s, durable_at=now(), updated_at=now()
                    WHERE submission_id=%s AND company_code=%s
                    """,
                    (
                        accepted_count,
                        total_stored,
                        waiting_status or ("quarantined" if spam_flagged else "durable"),
                        quota_code,
                        submission_id,
                        company,
                    ),
                )
                cur.execute(
                    """
                    UPDATE inbound_messages
                    SET company_code=%s, intake_id=%s, submission_id=%s,
                        status=%s, route_snapshot=%s, source_provenance=%s,
                        total_attachment_bytes=%s, durable_at=now(),
                        durability_latency_ms=%s, updated_at=now()
                    WHERE inbound_id=%s
                    """,
                    (
                        company,
                        intake_id,
                        submission_id,
                        "quarantined" if spam_flagged else "durable",
                        Json(route_snapshot),
                        Json(source_provenance),
                        total_stored,
                        durable_latency_ms,
                        inbound_id,
                    ),
                )
                # Wave 1 envelope dual-write. Postmark webhook/routing/ACK/ClamAV/
                # retries remain. When EMAIL authority flag is ON for the tenant,
                # accepted processing is unified (see inbound_cv_channel_cutover).
                # UNIFIED_INTAKE_AUTHORITY_EMAIL_RECEIPT
                _inbound_cv_intake.dual_write_email_receipt(
                    cur,
                    company_code=company,
                    inbound_id=inbound_id,
                    submission_id=submission_id,
                    provider=provider,
                    provider_message_id=provider_message_id,
                    route_snapshot=route_snapshot,
                    source_provenance=source_provenance,
                    documents=document_rows,
                    received_at=received_at,
                )
                _call_failpoint(failpoint, "before_commit")
                conn.commit()
                _call_failpoint(failpoint, "after_commit")
                return {
                    "durable": True,
                    "inbound_id": inbound_id,
                    "submission_id": submission_id,
                    "company_code": company,
                    "job_id": job_id,
                    "status": "quarantined" if spam_flagged else (waiting_status or "queued"),
                    "quota_code": quota_code,
                    "soft_warnings": soft_warnings,
                    "attachment_count": len(attachments),
                    "accepted_attachment_count": accepted_count,
                    "total_attachment_bytes": total_stored,
                    "documents": document_rows,
                    "durability_latency_ms": durable_latency_ms,
                }
    except IngressError:
        raise
    except Exception as exc:
        # Any objects written before a rolled-back DB transaction are deliberate
        # orphans. Stable ids/keys let a provider retry verify and reuse them.
        raise IngressDurabilityError(
            "inbound_durability_unavailable", type(exc).__name__
        ) from exc


def _redact_error_detail(value: Any) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()
    text = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[redacted-email]",
        text,
        flags=re.I,
    )
    text = re.sub(r"(?<!\w)/(?:[^/\s]+/){1,}[^/\s]*", "[redacted-path]", text)
    text = re.sub(r"\b[0-9A-Za-z_-]{48,}\b", "[redacted-token]", text)
    return text[:500]


def _record_job_event(
    cur: Any,
    job: dict[str, Any],
    *,
    event_type: str,
    from_status: str | None,
    to_status: str | None,
    error_code: str | None = None,
    error_detail: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO intake_processing_job_events
          (job_id, company_code, event_type, from_status, to_status,
           error_code, error_detail, metadata)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            job["job_id"],
            job["company_code"],
            event_type,
            from_status,
            to_status,
            error_code,
            _redact_error_detail(error_detail) if error_detail else None,
            Json(metadata or {}),
        ),
    )


def _backoff_seconds(job_id: str, attempts: int, config: IngressConfig) -> int:
    exponent = max(0, min(int(attempts) - 1, 20))
    base = min(config.retry_max_seconds, config.retry_base_seconds * (2**exponent))
    digest = hashlib.sha256(f"{job_id}:{attempts}".encode()).digest()
    jitter = int.from_bytes(digest[:2], "big") % max(1, min(base, 30))
    return min(config.retry_max_seconds, base + jitter)


def reclaim_expired_leases(
    cur: Any, *, config: IngressConfig, limit: int = 100
) -> dict[str, int]:
    cur.execute(
        """
        SELECT *, job_id::text AS job_id
        FROM intake_processing_jobs
        WHERE status='running' AND lease_expires_at < now()
        ORDER BY lease_expires_at
        FOR UPDATE SKIP LOCKED
        LIMIT %s
        """,
        (max(1, int(limit)),),
    )
    rows = [dict(row) for row in cur.fetchall()]
    reclaimed = 0
    dead = 0
    for job in rows:
        if int(job.get("attempts") or 0) >= int(job.get("max_attempts") or 1):
            new_status = "dead_letter"
            completed_at = datetime.now(UTC)
            dead += 1
        else:
            new_status = "retrying"
            completed_at = None
            reclaimed += 1
        cur.execute(
            """
            UPDATE intake_processing_jobs
            SET status=%s, lease_owner=NULL, lease_expires_at=NULL,
                available_at=now(), completed_at=%s,
                last_error_code='lease_expired',
                last_error_detail='worker lease expired before completion',
                updated_at=now()
            WHERE job_id=%s
            """,
            (new_status, completed_at, job["job_id"]),
        )
        _record_job_event(
            cur,
            job,
            event_type="lease_expired",
            from_status="running",
            to_status=new_status,
            error_code="lease_expired",
            error_detail="worker lease expired before completion",
        )
    if rows:
        cur.execute(
            """
            UPDATE intake_tenant_queue_state state
            SET running_jobs=(
                  SELECT count(*) FROM intake_processing_jobs job
                  WHERE job.company_code=state.company_code
                    AND job.status='running' AND job.lease_expires_at >= now()
                ),
                updated_at=now()
            """
        )
    return {"reclaimed": reclaimed, "dead_letter": dead}


def claim_next_job(
    *,
    db_connect: Callable[[], Any],
    worker_id: str,
    config: IngressConfig,
    allowed_job_types: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    allowed = sorted(set(allowed_job_types or JOB_TYPES) & set(JOB_TYPES))
    if not allowed:
        return None
    with db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            reclaim_expired_leases(cur, config=config)
            cur.execute(
                """
                INSERT INTO intake_tenant_queue_state (company_code)
                SELECT DISTINCT company_code
                FROM intake_processing_jobs
                WHERE status IN ('pending','retrying','waiting_quota','waiting_budget')
                ON CONFLICT (company_code) DO NOTHING
                """
            )
            cur.execute(
                """
                SELECT state.company_code
                FROM intake_tenant_queue_state state
                WHERE state.running_jobs < %s
                  AND EXISTS (
                    SELECT 1 FROM intake_processing_jobs job
                    WHERE job.company_code=state.company_code
                      AND job.status IN ('pending','retrying','waiting_quota','waiting_budget')
                      AND job.available_at <= now()
                      AND job.job_type = ANY(%s)
                  )
                ORDER BY state.last_claimed_at ASC NULLS FIRST,
                         (
                           SELECT min(job.priority)
                           FROM intake_processing_jobs job
                           WHERE job.company_code=state.company_code
                             AND job.status IN ('pending','retrying','waiting_quota','waiting_budget')
                             AND job.available_at <= now()
                             AND job.job_type = ANY(%s)
                         ) ASC,
                         state.company_code
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (config.per_tenant_concurrency, allowed, allowed),
            )
            tenant = cur.fetchone()
            if not tenant:
                conn.commit()
                return None
            company = tenant["company_code"]
            cur.execute(
                """
                SELECT *, job_id::text AS job_id
                FROM intake_processing_jobs
                WHERE company_code=%s
                  AND status IN ('pending','retrying','waiting_quota','waiting_budget')
                  AND available_at <= now()
                  AND job_type = ANY(%s)
                ORDER BY priority ASC, available_at ASC, created_at ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """,
                (company, allowed),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            job = dict(row)
            old_status = str(job["status"])
            lease_expires = datetime.now(UTC) + timedelta(seconds=config.lease_seconds)
            cur.execute(
                """
                UPDATE intake_processing_jobs
                SET status='running', attempts=attempts+1, lease_owner=%s,
                    lease_expires_at=%s, started_at=COALESCE(started_at,now()),
                    updated_at=now()
                WHERE job_id=%s
                RETURNING *, job_id::text AS job_id
                """,
                (worker_id, lease_expires, job["job_id"]),
            )
            claimed = dict(cur.fetchone())
            cur.execute(
                """
                UPDATE intake_tenant_queue_state
                SET running_jobs=running_jobs+1, last_claimed_at=now(), updated_at=now()
                WHERE company_code=%s
                """,
                (company,),
            )
            _record_job_event(
                cur,
                claimed,
                event_type="claimed",
                from_status=old_status,
                to_status="running",
                metadata={"worker_id": worker_id},
            )
            # Wave 3: stamp/compare activation epoch; authoritative deny releases claim.
            try:
                import tenant_control_queue_gate as _tc_qg

                meta = claimed.get("metadata") if isinstance(claimed.get("metadata"), dict) else {}
                queued_epoch = meta.get("activation_epoch")
                if queued_epoch is None:
                    queued_epoch = _tc_qg.persist_work_epoch(
                        cur,
                        company_code=str(company),
                        work_kind="durable_email_ingress",
                        work_ref=str(claimed.get("job_id")),
                        module_key="pre_hiring",
                    )
                    meta = {**meta, "activation_epoch": queued_epoch}
                    cur.execute("SAVEPOINT intake_job_metadata_stamp")
                    try:
                        cur.execute(
                            "UPDATE intake_processing_jobs SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb WHERE job_id=%s",
                            (json.dumps({"activation_epoch": queued_epoch}), claimed["job_id"]),
                        )
                        cur.execute("RELEASE SAVEPOINT intake_job_metadata_stamp")
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT intake_job_metadata_stamp")
                allowed, decision = _tc_qg.gate_or_skip(
                    cur,
                    company_code=str(company),
                    module_key="pre_hiring",
                    work_kind="durable_email_ingress",
                    work_ref=str(claimed.get("job_id")),
                    queued_epoch=int(queued_epoch),
                    surface="workers",
                )
                claimed["activation_epoch"] = int(queued_epoch)
                claimed["tenant_control_decision"] = decision.as_dict()
                if not allowed:
                    cur.execute(
                        """
                        UPDATE intake_processing_jobs
                        SET status='pending', lease_owner=NULL, lease_expires_at=NULL,
                            available_at=now() + interval '5 minutes', updated_at=now()
                        WHERE job_id=%s
                        """,
                        (claimed["job_id"],),
                    )
                    _release_tenant_slot(cur, company)
                    _record_job_event(
                        cur,
                        claimed,
                        event_type="tenant_control_hold",
                        from_status="running",
                        to_status="pending",
                        metadata={"reason": decision.reason_code, "correlation_id": decision.audit_correlation_id},
                    )
                    conn.commit()
                    return None
            except Exception:
                pass
        conn.commit()
    return claimed


def _release_tenant_slot(cur: Any, company_code: str) -> None:
    cur.execute(
        """
        UPDATE intake_tenant_queue_state
        SET running_jobs=GREATEST(0,running_jobs-1), updated_at=now()
        WHERE company_code=%s
        """,
        (company_code,),
    )


def complete_job(
    *,
    db_connect: Callable[[], Any],
    job: dict[str, Any],
    worker_id: str,
    result: dict[str, Any] | None,
) -> bool:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *, job_id::text AS job_id
                FROM intake_processing_jobs
                WHERE job_id=%s AND status='running' AND lease_owner=%s
                  AND lease_expires_at >= now()
                FOR UPDATE
                """,
                (job["job_id"], worker_id),
            )
            current = cur.fetchone()
            if not current:
                conn.commit()
                return False
            current = dict(current)
            cur.execute(
                """
                UPDATE intake_processing_jobs
                SET status='completed', result=%s, lease_owner=NULL,
                    lease_expires_at=NULL, completed_at=now(),
                    last_error_code=NULL, last_error_detail=NULL, updated_at=now()
                WHERE job_id=%s
                """,
                (Json(result or {}), job["job_id"]),
            )
            _release_tenant_slot(cur, current["company_code"])
            _record_job_event(
                cur,
                current,
                event_type="completed",
                from_status="running",
                to_status="completed",
            )
            day, _month = _period_starts(datetime.now(UTC))
            cur.execute(
                """
                INSERT INTO intake_quota_usage
                  (company_code, period_kind, period_start, processed_jobs)
                VALUES (%s,'day',%s,1)
                ON CONFLICT (company_code, period_kind, period_start) DO UPDATE
                SET processed_jobs=intake_quota_usage.processed_jobs+1, updated_at=now()
                """,
                (current["company_code"], day),
            )
        conn.commit()
    return True


def fail_job(
    *,
    db_connect: Callable[[], Any],
    job: dict[str, Any],
    worker_id: str,
    error_code: str,
    error_detail: str,
    config: IngressConfig,
) -> str:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *, job_id::text AS job_id
                FROM intake_processing_jobs
                WHERE job_id=%s AND status='running' AND lease_owner=%s
                  AND lease_expires_at >= now()
                FOR UPDATE
                """,
                (job["job_id"], worker_id),
            )
            current = cur.fetchone()
            if not current:
                conn.commit()
                return "lease_lost"
            current = dict(current)
            attempts = int(current.get("attempts") or 0)
            max_attempts = int(current.get("max_attempts") or config.max_attempts)
            detail = _redact_error_detail(error_detail)
            if attempts >= max_attempts:
                status = "dead_letter"
                available_at = current.get("available_at")
                completed_at = datetime.now(UTC)
            else:
                status = "retrying"
                available_at = datetime.now(UTC) + timedelta(
                    seconds=_backoff_seconds(str(current["job_id"]), attempts, config)
                )
                completed_at = None
            cur.execute(
                """
                UPDATE intake_processing_jobs
                SET status=%s, available_at=%s, lease_owner=NULL,
                    lease_expires_at=NULL, completed_at=%s,
                    last_error_code=%s, last_error_detail=%s, updated_at=now()
                WHERE job_id=%s
                """,
                (
                    status,
                    available_at,
                    completed_at,
                    str(error_code)[:120],
                    detail,
                    current["job_id"],
                ),
            )
            _release_tenant_slot(cur, current["company_code"])
            _record_job_event(
                cur,
                current,
                event_type="failed" if status == "dead_letter" else "retry_scheduled",
                from_status="running",
                to_status=status,
                error_code=str(error_code)[:120],
                error_detail=detail,
            )
        conn.commit()
    return status


def defer_job(
    *,
    db_connect: Callable[[], Any],
    job: dict[str, Any],
    worker_id: str,
    deferred: DeferredJob,
) -> str:
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *, job_id::text AS job_id
                FROM intake_processing_jobs
                WHERE job_id=%s AND status='running' AND lease_owner=%s
                  AND lease_expires_at >= now()
                FOR UPDATE
                """,
                (job["job_id"], worker_id),
            )
            current = cur.fetchone()
            if not current:
                conn.commit()
                return "lease_lost"
            current = dict(current)
            cur.execute(
                """
                UPDATE intake_processing_jobs
                SET status=%s, available_at=%s, attempts=GREATEST(0,attempts-1),
                    lease_owner=NULL, lease_expires_at=NULL,
                    last_error_code=%s, last_error_detail=%s, updated_at=now()
                WHERE job_id=%s
                """,
                (
                    deferred.status,
                    deferred.available_at,
                    deferred.code[:120],
                    _redact_error_detail(deferred.detail),
                    current["job_id"],
                ),
            )
            _release_tenant_slot(cur, current["company_code"])
            _record_job_event(
                cur,
                current,
                event_type="deferred",
                from_status="running",
                to_status=deferred.status,
                error_code=deferred.code,
                error_detail=deferred.detail,
            )
        conn.commit()
    return deferred.status


def replay_dead_letter(
    *,
    db_connect: Callable[[], Any],
    company_code: str,
    job_id: str,
    actor: str,
) -> dict[str, Any]:
    company = _safe_company(company_code)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *, job_id::text AS job_id
                FROM intake_processing_jobs
                WHERE company_code=%s AND job_id=%s
                FOR UPDATE
                """,
                (company, job_id),
            )
            row = cur.fetchone()
            if not row:
                raise IngressValidationError("intake_job_not_found")
            job = dict(row)
            if job["status"] != "dead_letter":
                raise IngressValidationError("intake_job_not_dead_letter")
            cur.execute(
                """
                UPDATE intake_processing_jobs
                SET status='pending', available_at=now(), attempts=0,
                    lease_owner=NULL, lease_expires_at=NULL, completed_at=NULL,
                    replay_count=replay_count+1, updated_at=now()
                WHERE job_id=%s
                """,
                (job_id,),
            )
            _record_job_event(
                cur,
                job,
                event_type="explicit_replay",
                from_status="dead_letter",
                to_status="pending",
                metadata={"actor": _redact_error_detail(actor)[:120]},
            )
        conn.commit()
    return {"job_id": job_id, "company_code": company, "status": "pending"}


def _processing_quota_defer(
    *,
    db_connect: Callable[[], Any],
    company_code: str,
    config: IngressConfig,
    tenant_policy_resolver: Callable[[str], dict[str, Any] | None] | None = None,
) -> DeferredJob | None:
    limit = int(config.daily_processing_job_quota or 0)
    kill_switch = False
    if tenant_policy_resolver is not None:
        try:
            policy = tenant_policy_resolver(company_code) or {}
            kill_switch = bool(policy.get("kill_switch"))
            limits = policy.get("limits") if isinstance(policy.get("limits"), dict) else {}
            if "daily_processing_job_quota" in limits:
                limit = int(limits.get("daily_processing_job_quota") or 0)
        except Exception:
            pass
    if kill_switch:
        return DeferredJob(
            "waiting_budget",
            "tenant_kill_switch",
            datetime.now(UTC) + timedelta(hours=1),
        )
    if limit <= 0:
        return None
    now = datetime.now(UTC)
    day, _month = _period_starts(now)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT processed_jobs FROM intake_quota_usage
                WHERE company_code=%s AND period_kind='day' AND period_start=%s
                """,
                (company_code, day),
            )
            row = cur.fetchone()
    used = int((row or {}).get("processed_jobs") or 0)
    if used >= limit:
        return DeferredJob(
            "waiting_quota",
            "daily_processing_job_quota",
            _next_period(now, "day"),
        )
    return None


def run_worker_once(
    *,
    db_connect: Callable[[], Any],
    handler: Callable[[dict[str, Any]], dict[str, Any] | None],
    worker_id: str,
    config: IngressConfig,
    limit: int = 10,
    allowed_job_types: Iterable[str] | None = None,
    tenant_policy_resolver: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    outcomes: list[dict[str, Any]] = []
    for _index in range(max(0, int(limit))):
        job = claim_next_job(
            db_connect=db_connect,
            worker_id=worker_id,
            config=config,
            allowed_job_types=allowed_job_types,
        )
        if not job:
            break
        quota_defer = _processing_quota_defer(
            db_connect=db_connect,
            company_code=job["company_code"],
            config=config,
            tenant_policy_resolver=tenant_policy_resolver,
        )
        if quota_defer:
            status = defer_job(
                db_connect=db_connect,
                job=job,
                worker_id=worker_id,
                deferred=quota_defer,
            )
            outcomes.append({"job_id": job["job_id"], "status": status})
            continue
        try:
            result = handler(job) or {}
            stored = complete_job(
                db_connect=db_connect,
                job=job,
                worker_id=worker_id,
                result=result,
            )
            outcomes.append(
                {
                    "job_id": job["job_id"],
                    "status": "completed" if stored else "lease_lost",
                }
            )
        except DeferredJob as exc:
            status = defer_job(
                db_connect=db_connect,
                job=job,
                worker_id=worker_id,
                deferred=exc,
            )
            outcomes.append({"job_id": job["job_id"], "status": status})
        except RetryableJobError as exc:
            status = fail_job(
                db_connect=db_connect,
                job=job,
                worker_id=worker_id,
                error_code=exc.code,
                error_detail=exc.detail,
                config=config,
            )
            outcomes.append({"job_id": job["job_id"], "status": status})
        except Exception as exc:
            status = fail_job(
                db_connect=db_connect,
                job=job,
                worker_id=worker_id,
                error_code="unhandled_job_error",
                error_detail=type(exc).__name__,
                config=config,
            )
            outcomes.append({"job_id": job["job_id"], "status": status})
    return {
        "worker_id": worker_id,
        "processed": len(outcomes),
        "outcomes": outcomes,
    }


def _mime_matches(claimed: str | None, detected: str) -> bool:
    if not claimed or claimed in {"application/octet-stream", "binary/octet-stream"}:
        return True
    aliases = {
        "image/jpg": "image/jpeg",
        "application/x-pdf": "application/pdf",
        "application/zip": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return aliases.get(claimed, claimed) == aliases.get(detected, detected)


def _pdf_page_count(data: bytes) -> int:
    # This preflight count is conservative and independent of Poppler/OCR.
    return max(
        1,
        len(re.findall(rb"/Type\s*/Page(?!s)\b", data)),
    )


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2 or index + length > len(data):
            return None
        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += length
    return None


def _archive_safety(
    data: bytes, config: IngressConfig
) -> tuple[str | None, dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > config.max_archive_members:
                return "archive_member_limit", {"archive_members": len(infos)}
            expanded = sum(max(0, int(info.file_size)) for info in infos)
            compressed = sum(max(0, int(info.compress_size)) for info in infos)
            encrypted = any(bool(info.flag_bits & 0x1) for info in infos)
            ratio = expanded / max(1, compressed)
            metadata = {
                "archive_members": len(infos),
                "archive_expanded_bytes": expanded,
                "archive_ratio": round(ratio, 2),
            }
            if encrypted:
                return "password_protected", metadata
            if expanded > config.max_archive_expanded_bytes:
                return "archive_expanded_byte_limit", metadata
            if ratio > config.max_archive_ratio:
                return "archive_expansion_ratio", metadata
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                return "invalid_docx_package", metadata
            return None, metadata
    except Exception:
        return "invalid_archive", {}


def default_malware_scanner(
    path: Path, config: IngressConfig
) -> tuple[str, str | None]:
    """Legacy tuple adapter around ``MalwareScanner``."""
    result = scan_path_with_evidence(path, config)
    return result.state, result.reason_code


def scan_path_with_evidence(path: Path, config: IngressConfig) -> MalwareScanResult:
    mode = config.malware_scanner
    if mode == "test_clean":
        allowed = (
            str(os.environ.get("WATHEFNI_ENV") or "").lower() == "test"
            or str(os.environ.get("WATHEFNI_INTAKE_ALLOW_TEST_SCANNER") or "").lower()
            in {"1", "true", "yes", "on"}
        )
        if not allowed:
            return MalwareScanResult(
                state="unavailable",
                reason_code="test_scanner_forbidden",
                engine="test_clean",
                signature_version=None,
                scanned_at=datetime.now(UTC),
                evidence={"detail": "test_scanner_forbidden"},
            )
        data = path.read_bytes()
        if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
            return MalwareScanResult(
                state="malware",
                reason_code="eicar_test_signature",
                engine="test_clean",
                signature_version="test",
                scanned_at=datetime.now(UTC),
                evidence={"path": str(path)},
            )
        return MalwareScanResult(
            state="clean",
            reason_code=None,
            engine="test_clean",
            signature_version="test",
            scanned_at=datetime.now(UTC),
            evidence={"path": str(path), "mode": "test_clean"},
        )
    previous = os.environ.get("WATHEFNI_INTAKE_MALWARE_SCANNER")
    os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = mode
    try:
        scanner = build_malware_scanner_from_env()
        return scanner.scan_path(path)
    finally:
        if previous is None:
            os.environ.pop("WATHEFNI_INTAKE_MALWARE_SCANNER", None)
        else:
            os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = previous


def inspect_document_safety(
    *,
    data: bytes,
    original_filename: str,
    claimed_mime: str | None,
    detected_mime: str,
    config: IngressConfig,
) -> tuple[str, str | None, dict[str, Any]]:
    extension = Path(original_filename).suffix.lower()
    metadata: dict[str, Any] = {}
    if extension not in SUPPORTED_EXTENSIONS:
        return "unsupported_type", "unsupported_extension", metadata
    if not _mime_matches(claimed_mime, detected_mime):
        return "mime_mismatch", "claimed_detected_mime_mismatch", metadata
    expected = {
        ".pdf": {"application/pdf"},
        ".docx": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        },
        ".png": {"image/png"},
        ".jpg": {"image/jpeg"},
        ".jpeg": {"image/jpeg"},
        ".webp": {"image/webp"},
    }.get(extension, set())
    if detected_mime not in expected:
        return "mime_mismatch", "extension_detected_mime_mismatch", metadata
    if detected_mime == "application/pdf":
        if re.search(rb"/Encrypt\b", data):
            return "password_protected", "pdf_encrypted", metadata
        pages = _pdf_page_count(data)
        metadata["pdf_pages"] = pages
        if pages > config.max_pdf_pages:
            return "too_large", "pdf_page_limit", metadata
        if b"%%EOF" not in data[-2048:]:
            return "invalid_corrupt", "pdf_eof_missing", metadata
    elif detected_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        archive_error, archive_meta = _archive_safety(data, config)
        metadata.update(archive_meta)
        if archive_error == "password_protected":
            return "password_protected", archive_error, metadata
        if archive_error in {
            "archive_member_limit",
            "archive_expanded_byte_limit",
            "archive_expansion_ratio",
        }:
            return "too_large", archive_error, metadata
        if archive_error:
            return "invalid_corrupt", archive_error, metadata
    elif detected_mime in {"image/png", "image/jpeg"}:
        dimensions = (
            _png_dimensions(data)
            if detected_mime == "image/png"
            else _jpeg_dimensions(data)
        )
        if not dimensions:
            return "invalid_corrupt", "image_dimensions_unreadable", metadata
        width, height = dimensions
        metadata.update({"image_width": width, "image_height": height})
        if width * height > config.max_image_pixels:
            return "too_large", "image_pixel_limit", metadata
    return "clean", None, metadata


def scan_document(
    *,
    db_connect: Callable[[], Any],
    document_id: str,
    company_code: str,
    config: IngressConfig,
    store: LocalQuarantineStore | None = None,
    scanner: Callable[[Path, IngressConfig], tuple[str, str | None]] | None = None,
) -> dict[str, Any]:
    company = _safe_company(company_code)
    store = store or LocalQuarantineStore(config.quarantine_root)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *, document_id::text AS document_id,
                       duplicate_of_document_id::text AS duplicate_of_document_id
                FROM intake_documents
                WHERE company_code=%s AND document_id=%s
                FOR UPDATE
                """,
                (company, document_id),
            )
            row = cur.fetchone()
            if not row:
                raise RetryableJobError("intake_document_missing")
            document = dict(row)
            import inbound_cv_authority as authority

            authority.ensure_schema(cur)
            if document["safety_state"] == "clean" and authority.scan_is_authoritatively_clean(
                cur,
                company_code=company,
                intake_document_id=document_id,
                content_sha256=str(document.get("content_sha256") or ""),
            ):
                conn.commit()
                return {"document_id": document_id, "safety_state": "clean", "duplicate": True}
            if document["storage_status"] != "stored" or not document.get("quarantine_key"):
                # Ingress has already assigned a deterministic terminal safety state.
                conn.commit()
                return {
                    "document_id": document_id,
                    "safety_state": document["safety_state"],
                    "reason": document.get("safety_reason_code"),
                }
            path = store.verify(
                document["quarantine_key"],
                document["content_sha256"],
                document["size_bytes"],
            )
            pending_scan = authority.begin_scan(
                cur,
                company_code=company,
                inbound_id=str(document["inbound_id"]),
                intake_document_id=document_id,
                attachment_ordinal=int(document.get("attachment_ordinal") or 0),
                content_sha256=str(document.get("content_sha256") or ""),
                quarantine_object_ref=str(document.get("quarantine_key") or "") or None,
            )
            reusable = authority.reusable_clean_scan(
                cur,
                company_code=company,
                content_sha256=str(document.get("content_sha256") or ""),
            )
            if reusable and str(reusable.get("intake_document_id")) != document_id:
                scan = MalwareScanResult(
                    state="clean",
                    reason_code=None,
                    engine=str(reusable.get("scanner_engine") or "reused"),
                    signature_version=str(
                        reusable.get("signature_database_version") or ""
                    )
                    or None,
                    scanned_at=datetime.now(UTC),
                    evidence={
                        "reused_clean_decision_id": reusable.get("decision_id"),
                        "scanner_policy_version": reusable.get(
                            "scanner_policy_version"
                        ),
                    },
                )
            else:
                reusable = None
                if scanner is not None:
                    scan_state, scan_reason = scanner(path, config)
                    scan = MalwareScanResult(
                        state=scan_state,  # type: ignore[arg-type]
                        reason_code=scan_reason,
                        engine="injected",
                        signature_version=None,
                        scanned_at=datetime.now(UTC),
                        evidence={"injected_scanner": True},
                    )
                else:
                    scan = scan_path_with_evidence(path, config)
            scan_state, scan_reason = scan.state, scan.reason_code
            scan_record = scan.to_record()
            if scan_state == "unavailable":
                authority.complete_scan(
                    cur,
                    pending_decision=pending_scan,
                    state="scan_failed",
                    scanner_engine=scan.engine,
                    signature_version=scan.signature_version,
                    failure_reason=scan_reason or "scanner_unavailable",
                    evidence=scan_record,
                )
                cur.execute(
                    """
                    UPDATE intake_documents
                    SET safety_state='scan_pending', safety_reason_code=%s,
                        scan_engine=%s, scan_signature_version=%s,
                        scanned_at=%s, scan_result=%s, scan_evidence=%s,
                        updated_at=now()
                    WHERE company_code=%s AND document_id=%s
                    """,
                    (
                        scan_reason or "scanner_unavailable",
                        scan.engine,
                        scan.signature_version,
                        scan.scanned_at,
                        scan_state,
                        Json(scan_record),
                        company,
                        document_id,
                    ),
                )
                conn.commit()
                raise RetryableJobError(
                    "scanner_unavailable", scan_reason or "scanner unavailable"
                )
            if scan_state != "clean":
                state = "malware_suspicious" if scan_state == "malware" else "quarantined"
                authority.complete_scan(
                    cur,
                    pending_decision=pending_scan,
                    state="infected" if scan_state == "malware" else "quarantined",
                    scanner_engine=scan.engine,
                    signature_version=scan.signature_version,
                    failure_reason=scan_reason or "safety_scan_failed",
                    evidence=scan_record,
                )
                cur.execute(
                    """
                    UPDATE intake_documents
                    SET safety_state=%s, safety_reason_code=%s,
                        scan_engine=%s, scan_signature_version=%s,
                        scanned_at=%s, scan_result=%s, scan_evidence=%s,
                        updated_at=now()
                    WHERE company_code=%s AND document_id=%s
                    """,
                    (
                        state,
                        scan_reason or "safety_scan_failed",
                        scan.engine,
                        scan.signature_version,
                        scan.scanned_at,
                        scan_state,
                        Json(scan_record),
                        company,
                        document_id,
                    ),
                )
                conn.commit()
                return {
                    "document_id": document_id,
                    "safety_state": state,
                    "reason": scan_reason,
                    "scan": scan_record,
                }
            data = path.read_bytes()
            state, reason, safety_meta = inspect_document_safety(
                data=data,
                original_filename=document.get("original_filename") or "attachment",
                claimed_mime=document.get("claimed_mime"),
                detected_mime=document.get("detected_mime") or detect_mime(data),
                config=config,
            )
            safety_meta = {**safety_meta, "malware_scan": scan_record}
            authority.complete_scan(
                cur,
                pending_decision=pending_scan,
                state="clean" if state == "clean" else "quarantined",
                scanner_engine=scan.engine,
                signature_version=scan.signature_version,
                failure_reason=reason,
                evidence=safety_meta,
                reused_from_decision_id=(
                    str(reusable.get("decision_id")) if reusable else None
                ),
            )
            cur.execute(
                """
                UPDATE intake_documents
                SET safety_state=%s, safety_reason_code=%s,
                    scan_engine=%s, scan_signature_version=%s,
                    scanned_at=%s, scan_result=%s, scan_evidence=%s,
                    metadata=COALESCE(metadata,'{}'::jsonb) || %s,
                    updated_at=now()
                WHERE company_code=%s AND document_id=%s
                """,
                (
                    state,
                    reason,
                    scan.engine,
                    scan.signature_version,
                    scan.scanned_at,
                    scan_state,
                    Json(scan_record),
                    Json(safety_meta),
                    company,
                    document_id,
                ),
            )
            if state == "clean":
                priority = 100
                cur.execute(
                    "SELECT route_snapshot FROM intake_submissions WHERE submission_id=%s",
                    (document["submission_id"],),
                )
                submission = cur.fetchone() or {}
                route = submission.get("route_snapshot") or {}
                if route.get("position_code"):
                    priority = 50
                enqueue_job(
                    cur,
                    company_code=company,
                    job_type="cv_identity_resolution",
                    subject_type="intake_document",
                    subject_id=document_id,
                    idempotency_key=f"document:{document_id}:identity-resolve",
                    payload={
                        "document_id": document_id,
                        "submission_id": str(document["submission_id"]),
                    },
                    priority=priority,
                    max_attempts=config.max_attempts,
                )
        conn.commit()
    return {"document_id": document_id, "safety_state": state, "reason": reason}


def validate_submission(
    *,
    db_connect: Callable[[], Any],
    submission_id: str,
    company_code: str,
    config: IngressConfig,
) -> dict[str, Any]:
    company = _safe_company(company_code)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM intake_submissions
                WHERE company_code=%s AND submission_id=%s
                FOR UPDATE
                """,
                (company, submission_id),
            )
            submission = cur.fetchone()
            if not submission:
                raise RetryableJobError("intake_submission_missing")
            cur.execute(
                """
                SELECT document_id::text, storage_status, safety_state
                FROM intake_documents
                WHERE company_code=%s AND submission_id=%s
                ORDER BY attachment_ordinal
                """,
                (company, submission_id),
            )
            documents = [dict(row) for row in cur.fetchall()]
            queued = 0
            for document in documents:
                if (
                    document["storage_status"] == "stored"
                    and document["safety_state"] == "scan_pending"
                ):
                    enqueue_job(
                        cur,
                        company_code=company,
                        job_type="file_safety_scan",
                        subject_type="intake_document",
                        subject_id=document["document_id"],
                        idempotency_key=f"document:{document['document_id']}:safety-scan",
                        payload={
                            "document_id": document["document_id"],
                            "submission_id": submission_id,
                        },
                        priority=50
                        if (submission.get("route_snapshot") or {}).get("position_code")
                        else 100,
                        max_attempts=config.max_attempts,
                    )
                    queued += 1
            status = "scan_pending" if queued else "validated_no_scannable_files"
            cur.execute(
                """
                UPDATE intake_submissions SET status=%s, updated_at=now()
                WHERE company_code=%s AND submission_id=%s
                """,
                (status, company, submission_id),
            )
        conn.commit()
    return {
        "submission_id": submission_id,
        "documents": len(documents),
        "scan_jobs_queued": queued,
        "status": status,
    }


def sign_quarantine_download(
    *,
    company_code: str,
    document_id: str,
    expires_at_epoch: int,
    secret: str,
) -> str:
    if not secret:
        raise IngressValidationError("quarantine_signing_unconfigured")
    message = f"{_safe_company(company_code)}:{document_id}:{int(expires_at_epoch)}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def verify_quarantine_download(
    *,
    company_code: str,
    document_id: str,
    expires_at_epoch: int,
    signature: str,
    secret: str,
    now_epoch: int,
) -> bool:
    if not secret or int(expires_at_epoch) < int(now_epoch):
        return False
    expected = sign_quarantine_download(
        company_code=company_code,
        document_id=document_id,
        expires_at_epoch=expires_at_epoch,
        secret=secret,
    )
    return bool(signature) and hmac.compare_digest(expected, str(signature))


def orphan_storage_report(
    *,
    db_connect: Callable[[], Any],
    config: IngressConfig,
    delete: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    store = LocalQuarantineStore(config.quarantine_root)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT quarantine_key FROM intake_documents
                WHERE storage_status='stored' AND quarantine_key IS NOT NULL
                """
            )
            referenced = {str(row["quarantine_key"]) for row in cur.fetchall()}
    orphans: list[str] = []
    deleted = 0
    cutoff = now.timestamp() - config.orphan_grace_seconds
    for key, path in store.iter_object_keys() or []:
        if key in referenced or path.stat().st_mtime > cutoff:
            continue
        orphans.append(key)
        if delete:
            path.unlink(missing_ok=True)
            deleted += 1
    if delete and config.quarantine_root.exists():
        for directory in sorted(
            (p for p in config.quarantine_root.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass
    return {
        "quarantine_root": str(config.quarantine_root),
        "referenced_objects": len(referenced),
        "orphan_objects": len(orphans),
        "deleted_objects": deleted,
        "orphan_keys": orphans[:100],
        "truncated": len(orphans) > 100,
    }


def operations_summary(
    *,
    db_connect: Callable[[], Any],
    config: IngressConfig,
    company_code: str | None = None,
    include_orphans: bool = True,
) -> dict[str, Any]:
    company = _safe_company(company_code) if company_code else None
    with db_connect() as conn:
        with conn.cursor() as cur:
            params: tuple[Any, ...] = (company, company)
            cur.execute(
                """
                SELECT count(*) AS messages_received,
                       count(*) FILTER (WHERE durable_at IS NOT NULL) AS durable_messages,
                       COALESCE(avg(durability_latency_ms)
                         FILTER (WHERE durability_latency_ms IS NOT NULL),0) AS avg_durability_latency_ms,
                       COALESCE(max(durability_latency_ms)
                         FILTER (WHERE durability_latency_ms IS NOT NULL),0) AS max_durability_latency_ms
                FROM inbound_messages
                WHERE (%s::text IS NULL OR company_code=%s)
                """,
                params,
            )
            messages = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT status, count(*) AS count,
                       COALESCE(
                         extract(
                           epoch FROM now() - (
                             min(created_at) FILTER (
                               WHERE status IN ('pending','retrying','waiting_quota','waiting_budget')
                             )
                           )
                         ),
                         0
                       )
                         AS oldest_age_seconds
                FROM intake_processing_jobs
                WHERE (%s::text IS NULL OR company_code=%s)
                GROUP BY status ORDER BY status
                """,
                params,
            )
            jobs = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT safety_state, count(*) AS count
                FROM intake_documents
                WHERE (%s::text IS NULL OR company_code=%s)
                GROUP BY safety_state ORDER BY safety_state
                """,
                params,
            )
            safety = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT company_code, running_jobs, last_claimed_at, updated_at
                FROM intake_tenant_queue_state
                WHERE (%s::text IS NULL OR company_code=%s)
                ORDER BY company_code
                """,
                params,
            )
            tenants = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT company_code, period_kind, period_start, messages,
                       attachments, source_bytes, processed_jobs
                FROM intake_quota_usage
                WHERE (%s::text IS NULL OR company_code=%s)
                ORDER BY period_start DESC, company_code, period_kind
                LIMIT 200
                """,
                params,
            )
            quotas = [dict(row) for row in cur.fetchall()]
    result = {
        "company_code": company,
        "messages": messages,
        "jobs": jobs,
        "safety_states": safety,
        "tenant_leases": tenants,
        "quota_usage": quotas,
        "limits": {
            "max_webhook_body_bytes": config.max_webhook_body_bytes,
            "max_attachments": config.max_attachments,
            "max_file_bytes": config.max_file_bytes,
            "max_total_attachment_bytes": config.max_total_attachment_bytes,
            "per_tenant_concurrency": config.per_tenant_concurrency,
        },
    }
    if include_orphans:
        result["orphan_storage"] = orphan_storage_report(
            db_connect=db_connect, config=config, delete=False
        )
    return result
