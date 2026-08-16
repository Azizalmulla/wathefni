"""Channel-neutral inbound CV intake envelope (Wave 1).

Additive dual-write authority for source events, subjects, and intake items.
The live email path in durable_email_ingress remains authoritative for scanning,
identity, extraction, classification, and candidate/application creation.

Wave 1 does not cut over WhatsApp or manual upload.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from psycopg2.extras import Json
except ImportError:  # pragma: no cover
    Json = dict  # type: ignore[misc, assignment]

UTC = timezone.utc
ENVELOPE_VERSION = "unified-inbound-cv-envelope-v1"
_ID_NAMESPACE = uuid.UUID("313cd3e9-7c4a-4f2d-9c1e-8a6b5d4e3f21")

CHANNELS = frozenset({"email_inbound", "whatsapp", "manual_upload", "api_import"})

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS intake_source_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  channel text NOT NULL,
  provider text NOT NULL,
  provider_account_id text NOT NULL DEFAULT '',
  external_event_id text NOT NULL,
  trusted_route_key text,
  route_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  legacy_inbound_id uuid,
  legacy_submission_id uuid,
  received_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, channel, provider, provider_account_id, external_event_id)
);
CREATE INDEX IF NOT EXISTS idx_intake_source_events_company_created
  ON intake_source_events(company_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intake_source_events_legacy_inbound
  ON intake_source_events(company_code, legacy_inbound_id)
  WHERE legacy_inbound_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS intake_subjects (
  subject_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  originating_event_id uuid NOT NULL REFERENCES intake_source_events(event_id) ON DELETE CASCADE,
  originating_item_id uuid,
  status text NOT NULL DEFAULT 'provisional',
  person_id uuid,
  membership_id uuid,
  legacy_candidate_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_intake_subjects_company_status
  ON intake_subjects(company_code, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_intake_subjects_event
  ON intake_subjects(company_code, originating_event_id);

CREATE TABLE IF NOT EXISTS intake_items (
  item_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  event_id uuid NOT NULL REFERENCES intake_source_events(event_id) ON DELETE CASCADE,
  subject_id uuid NOT NULL REFERENCES intake_subjects(subject_id) ON DELETE CASCADE,
  legacy_submission_id uuid,
  item_kind text NOT NULL DEFAULT 'cv_primary',
  acceptance_state text NOT NULL DEFAULT 'received',
  identity_state text NOT NULL DEFAULT 'pending',
  processing_state text NOT NULL DEFAULT 'pending',
  requested_job_binding_state text NOT NULL DEFAULT 'unassigned',
  primary_document_id uuid,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_intake_items_event_doc
  ON intake_items(
    company_code,
    event_id,
    item_kind,
    COALESCE(primary_document_id, '00000000-0000-0000-0000-000000000000'::uuid)
  );
CREATE INDEX IF NOT EXISTS idx_intake_items_company_event
  ON intake_items(company_code, event_id, created_at);
CREATE INDEX IF NOT EXISTS idx_intake_items_subject
  ON intake_items(company_code, subject_id);

CREATE TABLE IF NOT EXISTS intake_item_documents (
  company_code text NOT NULL,
  item_id uuid NOT NULL REFERENCES intake_items(item_id) ON DELETE CASCADE,
  document_id uuid NOT NULL,
  document_role text NOT NULL DEFAULT 'primary_cv',
  is_primary boolean NOT NULL DEFAULT false,
  legacy_intake_document_id uuid,
  content_sha256 text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, item_id, document_id)
);
CREATE INDEX IF NOT EXISTS idx_intake_item_documents_legacy
  ON intake_item_documents(company_code, legacy_intake_document_id)
  WHERE legacy_intake_document_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_intake_item_documents_sha
  ON intake_item_documents(company_code, content_sha256)
  WHERE content_sha256 IS NOT NULL;

ALTER TABLE IF EXISTS intake_submissions
  ADD COLUMN IF NOT EXISTS envelope_event_id uuid;
ALTER TABLE IF EXISTS intake_documents
  ADD COLUMN IF NOT EXISTS envelope_item_id uuid;
ALTER TABLE IF EXISTS intake_documents
  ADD COLUMN IF NOT EXISTS envelope_subject_id uuid;
"""


def dual_write_enabled(environ: dict[str, str] | None = None) -> bool:
    """Production-dark by default. Enable only for local/staging dual-write qualification."""

    env = environ if environ is not None else os.environ
    raw = str(env.get("WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE") or "").strip().lower()
    return raw in {"1", "true", "on", "yes", "enabled"}


REQUIRED_TABLES = [
    "intake_source_events",
    "intake_subjects",
    "intake_items",
    "intake_item_documents",
]


def apply_schema(cur: Any) -> None:
    import schema_contract as _schema

    _schema.apply_sql(
        cur,
        SCHEMA_SQL,
        module="inbound_cv_intake",
        lock_id=770_911_101,
    )


def require_schema(cur: Any) -> None:
    import schema_contract as _schema

    _schema.require_relations(cur, REQUIRED_TABLES, module="inbound_cv_intake")


def ensure_schema(cur: Any) -> None:
    """Runtime-safe: validate only unless WATHEFNI_SCHEMA_APPLY is enabled."""

    import schema_contract as _schema

    _schema.ensure_sql(
        cur,
        SCHEMA_SQL,
        required_tables=REQUIRED_TABLES,
        module="inbound_cv_intake",
        lock_id=770_911_101,
    )


def stable_event_id(
    *,
    company_code: str,
    channel: str,
    provider: str,
    provider_account_id: str,
    external_event_id: str,
) -> str:
    key = "|".join(
        [
            str(company_code or "").strip().upper(),
            str(channel or "").strip().lower(),
            str(provider or "").strip().lower(),
            str(provider_account_id or "").strip(),
            str(external_event_id or "").strip(),
        ]
    )
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:intake-event:{key}"))


def stable_subject_id(*, event_id: str, ordinal: int = 1) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"wathefni:intake-subject:{event_id}:{ordinal}"))


def stable_item_id(*, event_id: str, document_id: str | None, ordinal: int) -> str:
    return str(
        uuid.uuid5(
            _ID_NAMESPACE,
            f"wathefni:intake-item:{event_id}:{document_id or 'none'}:{ordinal}",
        )
    )


def _safe_company(value: str | None) -> str:
    company = re.sub(r"[^A-Z0-9_-]", "", str(value or "").strip().upper())
    if not company:
        raise ValueError("company_scope_missing")
    return company


def _json(value: Any) -> Any:
    if Json is dict:
        return value
    return Json(value)


def dual_write_email_receipt(
    cur: Any,
    *,
    company_code: str,
    inbound_id: str,
    submission_id: str,
    provider: str,
    provider_message_id: str,
    route_snapshot: dict[str, Any],
    source_provenance: dict[str, Any],
    documents: list[dict[str, Any]],
    received_at: datetime | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Idempotently mirror one durable email receipt into the generic envelope.

    Does not create candidates, applications, OCR, classification, or CK writes.
    """

    if not dual_write_enabled(environ):
        return {"ok": True, "skipped": True, "reason": "dual_write_disabled"}

    company = _safe_company(company_code)
    provider_key = str(provider or "postmark").strip().lower() or "postmark"
    external_id = str(provider_message_id or "").strip()
    if not external_id:
        raise ValueError("external_event_id_required")

    event_id = stable_event_id(
        company_code=company,
        channel="email_inbound",
        provider=provider_key,
        provider_account_id="",
        external_event_id=external_id,
    )
    when = received_at or datetime.now(UTC)
    trusted_route = str((route_snapshot or {}).get("intake_id") or "").strip() or None

    cur.execute(
        """
        INSERT INTO intake_source_events
          (event_id, company_code, channel, provider, provider_account_id,
           external_event_id, trusted_route_key, route_snapshot, provenance,
           legacy_inbound_id, legacy_submission_id, received_at)
        VALUES (%s,%s,'email_inbound',%s,'',%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, channel, provider, provider_account_id, external_event_id)
        DO UPDATE SET
          route_snapshot=EXCLUDED.route_snapshot,
          provenance=EXCLUDED.provenance,
          legacy_inbound_id=COALESCE(intake_source_events.legacy_inbound_id, EXCLUDED.legacy_inbound_id),
          legacy_submission_id=COALESCE(intake_source_events.legacy_submission_id, EXCLUDED.legacy_submission_id)
        RETURNING event_id::text AS event_id
        """,
        (
            event_id,
            company,
            provider_key,
            external_id,
            trusted_route,
            _json(route_snapshot or {}),
            _json(source_provenance or {}),
            inbound_id,
            submission_id,
            when,
        ),
    )
    event_row = cur.fetchone() or {"event_id": event_id}
    event_id = str(event_row.get("event_id") or event_id)

    subject_id = stable_subject_id(event_id=event_id, ordinal=1)
    cur.execute(
        """
        INSERT INTO intake_subjects
          (subject_id, company_code, originating_event_id, status)
        VALUES (%s,%s,%s,'provisional')
        ON CONFLICT (subject_id) DO NOTHING
        """,
        (subject_id, company, event_id),
    )

    item_ids: list[str] = []
    doc_links = 0
    primary_docs = [
        doc
        for doc in (documents or [])
        if str(doc.get("storage_status") or "") == "stored"
        or str(doc.get("safety_state") or "") in {"scan_pending", "clean"}
    ]
    if not primary_docs:
        # Still create one envelope item for the submission so parity can map the event.
        primary_docs = [{"document_id": None, "ordinal": 0, "content_sha256": None}]

    for index, doc in enumerate(primary_docs, start=1):
        document_id = doc.get("document_id")
        item_id = stable_item_id(
            event_id=event_id,
            document_id=str(document_id) if document_id else None,
            ordinal=int(doc.get("ordinal") or index),
        )
        cur.execute(
            """
            INSERT INTO intake_items
              (item_id, company_code, event_id, subject_id, legacy_submission_id,
               item_kind, acceptance_state, primary_document_id, metadata)
            VALUES (%s,%s,%s,%s,%s,'cv_primary','received',%s,%s)
            ON CONFLICT (item_id)
            DO UPDATE SET
              updated_at=now(),
              metadata=EXCLUDED.metadata,
              legacy_submission_id=COALESCE(intake_items.legacy_submission_id, EXCLUDED.legacy_submission_id)
            RETURNING item_id::text AS item_id
            """,
            (
                item_id,
                company,
                event_id,
                subject_id,
                submission_id,
                document_id,
                _json(
                    {
                        "envelope_version": ENVELOPE_VERSION,
                        "legacy_inbound_id": inbound_id,
                        "safety_state": doc.get("safety_state"),
                        "filename": doc.get("filename"),
                    }
                ),
            ),
        )
        inserted = cur.fetchone() or {"item_id": item_id}
        item_id = str(inserted.get("item_id") or item_id)
        item_ids.append(item_id)
        if index == 1:
            cur.execute(
                """
                UPDATE intake_subjects
                SET originating_item_id=%s, updated_at=now()
                WHERE subject_id=%s AND company_code=%s
                  AND originating_item_id IS NULL
                """,
                (item_id, subject_id, company),
            )
        if document_id:
            cur.execute(
                """
                INSERT INTO intake_item_documents
                  (company_code, item_id, document_id, document_role, is_primary,
                   legacy_intake_document_id, content_sha256)
                VALUES (%s,%s,%s,'primary_cv',%s,%s,%s)
                ON CONFLICT (company_code, item_id, document_id) DO NOTHING
                """,
                (
                    company,
                    item_id,
                    document_id,
                    index == 1,
                    document_id,
                    doc.get("content_sha256") or doc.get("digest"),
                ),
            )
            doc_links += 1
            cur.execute(
                """
                UPDATE intake_documents
                SET envelope_item_id=%s, envelope_subject_id=%s, updated_at=now()
                WHERE company_code=%s AND document_id=%s
                """,
                (item_id, subject_id, company, document_id),
            )

    cur.execute(
        """
        UPDATE intake_submissions
        SET envelope_event_id=%s, updated_at=now()
        WHERE company_code=%s AND submission_id=%s
        """,
        (event_id, company, submission_id),
    )

    return {
        "ok": True,
        "skipped": False,
        "envelope_version": ENVELOPE_VERSION,
        "event_id": event_id,
        "subject_id": subject_id,
        "item_ids": item_ids,
        "document_links": doc_links,
    }


def parity_summary(
    cur: Any,
    *,
    company_code: str,
    submission_id: str,
) -> dict[str, Any]:
    """Compare one email submission to its dual-written envelope mapping."""

    company = _safe_company(company_code)
    cur.execute(
        """
        SELECT submission_id::text, inbound_id::text, provider, provider_message_id,
               envelope_event_id::text AS envelope_event_id, status,
               accepted_attachment_count, attachment_count
        FROM intake_submissions
        WHERE company_code=%s AND submission_id=%s
        LIMIT 1
        """,
        (company, submission_id),
    )
    submission = cur.fetchone()
    if not submission:
        return {"ok": False, "error": "submission_not_found"}

    event_id = submission.get("envelope_event_id")
    cur.execute(
        """
        SELECT count(*)::int AS n FROM intake_documents
        WHERE company_code=%s AND submission_id=%s
        """,
        (company, submission_id),
    )
    doc_count = int((cur.fetchone() or {}).get("n") or 0)

    event = None
    item_count = 0
    link_count = 0
    if event_id:
        cur.execute(
            """
            SELECT event_id::text, channel, provider, external_event_id,
                   legacy_inbound_id::text, legacy_submission_id::text
            FROM intake_source_events
            WHERE company_code=%s AND event_id=%s
            LIMIT 1
            """,
            (company, event_id),
        )
        event = cur.fetchone()
        cur.execute(
            """
            SELECT count(*)::int AS n FROM intake_items
            WHERE company_code=%s AND event_id=%s
            """,
            (company, event_id),
        )
        item_count = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            """
            SELECT count(*)::int AS n FROM intake_item_documents
            WHERE company_code=%s AND item_id IN (
              SELECT item_id FROM intake_items
              WHERE company_code=%s AND event_id=%s
            )
            """,
            (company, company, event_id),
        )
        link_count = int((cur.fetchone() or {}).get("n") or 0)

    mapped = bool(event_id and event)
    return {
        "ok": mapped,
        "submission_id": submission_id,
        "envelope_event_id": event_id,
        "legacy_document_count": doc_count,
        "envelope_item_count": item_count,
        "envelope_document_links": link_count,
        "provider_message_match": bool(
            event
            and str(event.get("external_event_id") or "")
            == str(submission.get("provider_message_id") or "")
        ),
        "no_duplicate_event": mapped,
    }


def channel_dual_write_enabled(
    channel: str,
    environ: dict[str, str] | None = None,
) -> bool:
    """Master envelope flag enables all channels; per-channel flags can narrow."""

    env = environ if environ is not None else os.environ
    if not dual_write_enabled(env):
        return False
    channel_key = str(channel or "").strip().lower()
    per_channel = {
        "email_inbound": "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE_EMAIL",
        "manual_upload": "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE_MANUAL",
        "whatsapp": "WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE_WHATSAPP",
    }.get(channel_key)
    if not per_channel:
        return False
    raw = str(env.get(per_channel) or "").strip().lower()
    # Empty per-channel flag inherits master ON (staging convenience).
    if raw == "":
        return True
    return raw in {"1", "true", "on", "yes", "enabled"}


def dual_write_channel_receipt(
    cur: Any,
    *,
    company_code: str,
    channel: str,
    provider: str,
    external_event_id: str,
    documents: list[dict[str, Any]] | None = None,
    provider_account_id: str = "",
    route_snapshot: dict[str, Any] | None = None,
    source_provenance: dict[str, Any] | None = None,
    legacy_inbound_id: str | None = None,
    legacy_submission_id: str | None = None,
    legacy_candidate_phone: str | None = None,
    item_kind: str = "cv_primary",
    acceptance_state: str = "received",
    processing_state: str = "pending",
    hr_visible: bool = False,
    actionable: bool = False,
    received_at: datetime | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Idempotent channel-neutral envelope dual-write.

    Does not create candidates, applications, OCR, classification, or CK writes.
    """

    channel_key = str(channel or "").strip().lower()
    if channel_key not in CHANNELS:
        raise ValueError(f"unsupported_channel:{channel_key}")
    if not channel_dual_write_enabled(channel_key, environ):
        return {"ok": True, "skipped": True, "reason": "dual_write_disabled"}

    company = _safe_company(company_code)
    provider_key = str(provider or "unknown").strip().lower() or "unknown"
    external_id = str(external_event_id or "").strip()
    if not external_id:
        raise ValueError("external_event_id_required")
    account = str(provider_account_id or "").strip()

    event_id = stable_event_id(
        company_code=company,
        channel=channel_key,
        provider=provider_key,
        provider_account_id=account,
        external_event_id=external_id,
    )
    when = received_at or datetime.now(UTC)
    trusted_route = str((route_snapshot or {}).get("intake_id") or (route_snapshot or {}).get("apply_code") or "").strip() or None

    cur.execute(
        """
        INSERT INTO intake_source_events
          (event_id, company_code, channel, provider, provider_account_id,
           external_event_id, trusted_route_key, route_snapshot, provenance,
           legacy_inbound_id, legacy_submission_id, received_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, channel, provider, provider_account_id, external_event_id)
        DO UPDATE SET
          route_snapshot=EXCLUDED.route_snapshot,
          provenance=EXCLUDED.provenance,
          legacy_inbound_id=COALESCE(intake_source_events.legacy_inbound_id, EXCLUDED.legacy_inbound_id),
          legacy_submission_id=COALESCE(intake_source_events.legacy_submission_id, EXCLUDED.legacy_submission_id)
        RETURNING event_id::text AS event_id
        """,
        (
            event_id,
            company,
            channel_key,
            provider_key,
            account,
            external_id,
            trusted_route,
            _json(route_snapshot or {}),
            _json(source_provenance or {}),
            legacy_inbound_id,
            legacy_submission_id,
            when,
        ),
    )
    event_row = cur.fetchone() or {"event_id": event_id}
    event_id = str(event_row.get("event_id") or event_id)

    subject_id = stable_subject_id(event_id=event_id, ordinal=1)
    cur.execute(
        """
        INSERT INTO intake_subjects
          (subject_id, company_code, originating_event_id, status, legacy_candidate_phone)
        VALUES (%s,%s,%s,'provisional',%s)
        ON CONFLICT (subject_id) DO UPDATE SET
          legacy_candidate_phone=COALESCE(intake_subjects.legacy_candidate_phone, EXCLUDED.legacy_candidate_phone),
          updated_at=now()
        """,
        (subject_id, company, event_id, legacy_candidate_phone),
    )

    item_ids: list[str] = []
    doc_links = 0
    docs = list(documents or [])
    if not docs:
        docs = [{"document_id": None, "ordinal": 0, "content_sha256": None}]

    for index, doc in enumerate(docs, start=1):
        document_id = doc.get("document_id")
        item_id = stable_item_id(
            event_id=event_id,
            document_id=str(document_id) if document_id else None,
            ordinal=int(doc.get("ordinal") or index),
        )
        cur.execute(
            """
            INSERT INTO intake_items
              (item_id, company_code, event_id, subject_id, legacy_submission_id,
               item_kind, acceptance_state, processing_state, primary_document_id, metadata)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (item_id)
            DO UPDATE SET
              updated_at=now(),
              metadata=EXCLUDED.metadata,
              processing_state=EXCLUDED.processing_state,
              acceptance_state=EXCLUDED.acceptance_state
            RETURNING item_id::text AS item_id
            """,
            (
                item_id,
                company,
                event_id,
                subject_id,
                legacy_submission_id,
                item_kind,
                acceptance_state,
                processing_state,
                document_id,
                _json(
                    {
                        "envelope_version": ENVELOPE_VERSION,
                        "channel": channel_key,
                        "hr_visible": bool(hr_visible),
                        "actionable": bool(actionable),
                        "talent_pool_intake": bool(hr_visible and not actionable),
                        "filename": doc.get("filename"),
                        "safety_state": doc.get("safety_state"),
                        "content_sha256": doc.get("content_sha256") or doc.get("digest"),
                        "legacy_app_key": doc.get("app_key"),
                        "pending_id": doc.get("pending_id"),
                    }
                ),
            ),
        )
        inserted = cur.fetchone() or {"item_id": item_id}
        item_id = str(inserted.get("item_id") or item_id)
        item_ids.append(item_id)
        if index == 1:
            cur.execute(
                """
                UPDATE intake_subjects
                SET originating_item_id=%s, updated_at=now()
                WHERE subject_id=%s AND company_code=%s
                  AND originating_item_id IS NULL
                """,
                (item_id, subject_id, company),
            )
        if document_id:
            cur.execute(
                """
                INSERT INTO intake_item_documents
                  (company_code, item_id, document_id, document_role, is_primary,
                   legacy_intake_document_id, content_sha256)
                VALUES (%s,%s,%s,'primary_cv',%s,%s,%s)
                ON CONFLICT (company_code, item_id, document_id) DO NOTHING
                """,
                (
                    company,
                    item_id,
                    document_id,
                    index == 1,
                    doc.get("legacy_intake_document_id") or document_id,
                    doc.get("content_sha256") or doc.get("digest"),
                ),
            )
            doc_links += 1

    return {
        "ok": True,
        "skipped": False,
        "envelope_version": ENVELOPE_VERSION,
        "channel": channel_key,
        "event_id": event_id,
        "subject_id": subject_id,
        "item_ids": item_ids,
        "document_links": doc_links,
        "hr_visible": bool(hr_visible),
        "actionable": bool(actionable),
    }


def dual_write_manual_receipt(
    cur: Any,
    *,
    company_code: str,
    batch_id: str,
    content_sha256: str,
    filename: str | None = None,
    document_id: str | None = None,
    app_key: str | None = None,
    held_status: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Dual-write one manual Import Center CV into the envelope."""

    external_id = f"{batch_id}:{content_sha256}"
    return dual_write_channel_receipt(
        cur,
        company_code=company_code,
        channel="manual_upload",
        provider="dashboard_import",
        external_event_id=external_id,
        documents=[
            {
                "document_id": document_id,
                "ordinal": 1,
                "filename": filename,
                "content_sha256": content_sha256,
                "app_key": app_key,
                "safety_state": "adapter_pending",
            }
        ],
        route_snapshot={"batch_id": batch_id, "held_status": held_status},
        source_provenance={
            "channel": "manual_upload",
            "batch_id": batch_id,
            "app_key": app_key,
            "held_by_default": True,
        },
        acceptance_state="received",
        processing_state="pending_shared",
        hr_visible=True,
        actionable=False,
        environ=environ,
    )


def dual_write_whatsapp_receipt(
    cur: Any,
    *,
    company_code: str,
    provider_message_id: str,
    phone: str | None = None,
    account_id: str | None = None,
    conversation_id: str | None = None,
    pending_id: str | None = None,
    document_id: str | None = None,
    content_sha256: str | None = None,
    filename: str | None = None,
    app_key: str | None = None,
    job_bound: bool = False,
    apply_code: str | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Dual-write one WhatsApp CV receipt (unsolicited or job-bound)."""

    external_id = str(provider_message_id or pending_id or "").strip()
    if not external_id:
        raise ValueError("whatsapp_external_event_id_required")
    return dual_write_channel_receipt(
        cur,
        company_code=company_code,
        channel="whatsapp",
        provider="octopus",
        provider_account_id=str(account_id or ""),
        external_event_id=external_id,
        documents=[
            {
                "document_id": document_id,
                "ordinal": 1,
                "filename": filename,
                "content_sha256": content_sha256,
                "app_key": app_key,
                "pending_id": pending_id,
                "safety_state": "adapter_pending",
            }
        ],
        route_snapshot={
            "conversation_id": conversation_id,
            "apply_code": apply_code,
            "job_bound": bool(job_bound),
        },
        source_provenance={
            "channel": "whatsapp",
            "phone": phone,
            "account_id": account_id,
            "conversation_id": conversation_id,
            "pending_id": pending_id,
            "provider_message_id": provider_message_id,
            "job_bound": bool(job_bound),
        },
        legacy_candidate_phone=phone,
        acceptance_state="received",
        processing_state="pending_shared" if not job_bound else "attached_pending_extract",
        hr_visible=True,
        # Unsolicited: durable Talent Pool intake, never actionable Job.
        # Job-bound attach still requires exact confirmation upstream.
        actionable=False,
        environ=environ,
    )


def content_fingerprint(parts: list[str]) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "ENVELOPE_VERSION",
    "CHANNELS",
    "dual_write_enabled",
    "channel_dual_write_enabled",
    "ensure_schema",
    "stable_event_id",
    "stable_subject_id",
    "stable_item_id",
    "dual_write_email_receipt",
    "dual_write_channel_receipt",
    "dual_write_manual_receipt",
    "dual_write_whatsapp_receipt",
    "parity_summary",
    "content_fingerprint",
]
