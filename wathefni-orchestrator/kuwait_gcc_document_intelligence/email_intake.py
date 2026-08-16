"""Inbound email attachments for employee/compliance documents.

Uses the SAME shared processor as WhatsApp / ESS / Hub — not an email-only
extraction pipeline. Uncertain tenant/employee/expected-type matches go to a
durable review queue (never auto-attach).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kuwait_gcc_document_intelligence.intake import (
    canonical_document_type,
    extraction_for_receipt,
    is_shared_intake_type,
    shared_channel_extraction,
)

UTC = timezone.utc

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS employee_document_email_intake (
  intake_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  channel text NOT NULL DEFAULT 'email_inbound',
  message_id text NOT NULL,
  content_sha256 text,
  attachment_name text,
  attachment_mime text,
  sender text,
  subject text,
  recipient text,
  match_status text NOT NULL,
  employee_key text,
  document_type text,
  expected_item text,
  review_status text NOT NULL DEFAULT 'pending_review',
  extraction jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, message_id, content_sha256)
);

CREATE INDEX IF NOT EXISTS employee_document_email_intake_review_idx
  ON employee_document_email_intake (company_code, review_status, created_at DESC);
"""


def ensure_email_intake_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def resolve_tenant_from_recipient(
    *,
    recipient: str | None,
    domain_map: dict[str, str] | None = None,
    configured_company: str | None = None,
) -> tuple[str | None, str]:
    """Resolve tenant from receiving address/domain/config. Fail closed on ambiguity."""

    if configured_company and str(configured_company).strip():
        return str(configured_company).strip().upper(), "configured"
    raw = str(recipient or "").strip().lower()
    if not raw:
        return None, "missing_recipient"
    # extract email
    m = re.search(r"[\w.+\-]+@([\w.\-]+)", raw)
    domain = m.group(1).lower() if m else ""
    mapping = domain_map or {}
    env_map = str(os.environ.get("WATHEFNI_EMPLOYEE_DOC_EMAIL_DOMAIN_MAP") or "").strip()
    if env_map and not mapping:
        try:
            mapping = json.loads(env_map)
        except Exception:
            mapping = {}
    if domain and domain in mapping:
        return str(mapping[domain]).strip().upper(), "domain_map"
    # Explicit single-tenant override for qualify
    single = str(os.environ.get("WATHEFNI_EMPLOYEE_DOC_EMAIL_DEFAULT_COMPANY") or "").strip().upper()
    if single:
        return single, "default_company"
    return None, "unresolved_tenant"


def match_employee(
    *,
    cur: Any,
    company_code: str,
    trusted_employee_key: str | None = None,
    trusted_phone: str | None = None,
    trusted_email: str | None = None,
    civil_id: str | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Strong-match only. Weak matches → review queue."""

    company = str(company_code or "").strip().upper()
    if trusted_employee_key:
        cur.execute(
            """
            SELECT employee_key, phone, name, company_code
            FROM employees
            WHERE company_code=%s AND employee_key=%s
            LIMIT 1
            """,
            (company, trusted_employee_key),
        )
        row = cur.fetchone()
        if row:
            return dict(row), "trusted_employee_key"
        return None, "employee_key_not_found"

    hits: list[dict[str, Any]] = []
    if trusted_phone:
        digits = re.sub(r"\D+", "", str(trusted_phone))
        if digits:
            cur.execute(
                """
                SELECT employee_key, phone, name, company_code
                FROM employees
                WHERE company_code=%s AND regexp_replace(COALESCE(phone,''), '\\D', '', 'g')=%s
                LIMIT 3
                """,
                (company, digits),
            )
            hits.extend(dict(r) for r in cur.fetchall())
    if trusted_email:
        email = str(trusted_email).strip().lower()
        cur.execute(
            """
            SELECT employee_key, phone, name, company_code
            FROM employees
            WHERE company_code=%s AND lower(COALESCE(email,''))=%s
            LIMIT 3
            """,
            (company, email),
        )
        hits.extend(dict(r) for r in cur.fetchall())
    if civil_id:
        cur.execute(
            """
            SELECT e.employee_key, e.phone, e.name, e.company_code
            FROM employees e
            JOIN employee_documents d ON d.employee_key=e.employee_key
            WHERE e.company_code=%s AND d.document_type IN ('civil_id')
              AND COALESCE(d.document_number,'')=%s
            LIMIT 3
            """,
            (company, str(civil_id).strip()),
        )
        hits.extend(dict(r) for r in cur.fetchall())

    # Deduplicate
    by_key: dict[str, dict[str, Any]] = {}
    for h in hits:
        by_key[str(h["employee_key"])] = h
    uniq = list(by_key.values())
    if len(uniq) == 1:
        return uniq[0], "unique_trusted_identifier"
    if len(uniq) > 1:
        return None, "ambiguous_employee_match"
    return None, "employee_unmatched"


def process_email_attachment(
    *,
    cur: Any,
    company_code: str | None,
    message_id: str,
    attachment_name: str,
    attachment_bytes: bytes,
    attachment_mime: str | None,
    sender: str | None,
    subject: str | None,
    recipient: str | None,
    expected_item: str | None = None,
    trusted_employee_key: str | None = None,
    trusted_phone: str | None = None,
    trusted_email: str | None = None,
    tmp_dir: Path | None = None,
    auto_attach: bool = True,
) -> dict[str, Any]:
    """Classify one attachment via shared processor; auto-attach only on strong match."""

    ensure_email_intake_schema(cur)
    content_sha = _sha256_bytes(attachment_bytes)
    mid = str(message_id or "").strip() or f"synthetic-{content_sha[:16]}"

    # Duplicate suppression (forward/retry)
    cur.execute(
        """
        SELECT intake_id, match_status, review_status, employee_key, document_type
        FROM employee_document_email_intake
        WHERE company_code=COALESCE(%s,'UNRESOLVED') AND message_id=%s AND content_sha256=%s
        LIMIT 1
        """,
        (str(company_code or "").upper() or None, mid, content_sha),
    )
    existing = cur.fetchone()
    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "intake_id": str(existing["intake_id"]),
            "match_status": existing["match_status"],
            "review_status": existing["review_status"],
            "gpt_used": False,
        }

    tenant, tenant_reason = resolve_tenant_from_recipient(
        recipient=recipient,
        configured_company=company_code,
    )
    provenance = {
        "sender": sender,
        "subject": subject,
        "message_id": mid,
        "recipient": recipient,
        "attachment_name": attachment_name,
        "attachment_mime": attachment_mime,
        "content_sha256": content_sha,
        "tenant_reason": tenant_reason,
        "received_at": _utcnow().isoformat(),
    }

    if not tenant:
        intake_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO employee_document_email_intake (
              intake_id, company_code, message_id, content_sha256, attachment_name,
              attachment_mime, sender, subject, recipient, match_status, review_status,
              provenance, error
            ) VALUES (%s,'UNRESOLVED',%s,%s,%s,%s,%s,%s,%s,'unresolved_tenant','pending_review',%s::jsonb,%s)
            ON CONFLICT (company_code, message_id, content_sha256) DO NOTHING
            """,
            (
                str(intake_id),
                mid,
                content_sha,
                attachment_name,
                attachment_mime,
                sender,
                subject,
                recipient,
                json.dumps(provenance),
                tenant_reason,
            ),
        )
        return {
            "ok": False,
            "intake_id": str(intake_id),
            "match_status": "unresolved_tenant",
            "review_status": "pending_review",
            "auto_attached": False,
            "gpt_used": False,
            "reason": tenant_reason,
        }

    employee, emp_reason = match_employee(
        cur=cur,
        company_code=tenant,
        trusted_employee_key=trusted_employee_key,
        trusted_phone=trusted_phone,
        trusted_email=trusted_email,
    )

    # Write temp file for shared processor
    base = tmp_dir or Path(os.environ.get("WATHEFNI_WORKSPACE") or "/tmp") / "employee-doc-email"
    base.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w.\-]+", "_", attachment_name or "attachment.bin")[:120]
    path = base / f"{content_sha[:16]}_{safe_name}"
    path.write_bytes(attachment_bytes)
    media = {"path": str(path), "mime_type": attachment_mime or "application/octet-stream"}

    expected = canonical_document_type(expected_item) if expected_item else None
    if expected and is_shared_intake_type(expected):
        dtype = expected
        mode = "verify"
    else:
        dtype = expected or "employment_contract"
        mode = "classify" if not expected else "extract"

    extraction = shared_channel_extraction(
        document_type=dtype,
        media=media,
        company_code=tenant,
        subject_key=(employee or {}).get("employee_key"),
        channel="email_inbound",
        expected_item=expected,
        mode="extract" if mode != "classify" else "classify",
    )
    if mode == "classify" and not expected:
        detected = canonical_document_type(extraction.get("detected_item") or extraction.get("document_type"))
        if detected and is_shared_intake_type(detected):
            extraction = shared_channel_extraction(
                document_type=detected,
                media=media,
                company_code=tenant,
                subject_key=(employee or {}).get("employee_key"),
                channel="email_inbound",
                mode="extract",
            )
            dtype = detected
        else:
            dtype = detected or "unknown"

    receipt = extraction_for_receipt(extraction)
    intake_id = uuid.uuid4()
    match_status = emp_reason
    review_status = "pending_review"
    auto_attached = False
    error = None

    strong = employee is not None and emp_reason in {"trusted_employee_key", "unique_trusted_identifier"}
    type_ok = bool(dtype and is_shared_intake_type(dtype))
    if expected and mode == "verify":
        # When expected was given, re-verify
        verify = shared_channel_extraction(
            document_type=expected,
            media=media,
            company_code=tenant,
            subject_key=(employee or {}).get("employee_key"),
            channel="email_inbound",
            expected_item=expected,
            mode="verify",
        )
        type_ok = bool(verify.get("matches_expected_item")) and float(verify.get("confidence") or 0) >= 0.65
        if not type_ok:
            match_status = "document_type_uncertain"
            receipt = extraction_for_receipt(verify)

    if strong and type_ok and auto_attach and receipt.get("extraction_status") not in {None, "needs_review"}:
        review_status = "auto_attached_pending_hr"
        auto_attached = True
    elif not strong:
        review_status = "pending_review"
        auto_attached = False
        error = emp_reason
    else:
        review_status = "pending_review"
        auto_attached = False
        error = match_status if match_status != emp_reason else "type_or_extraction_uncertain"

    cur.execute(
        """
        INSERT INTO employee_document_email_intake (
          intake_id, company_code, message_id, content_sha256, attachment_name,
          attachment_mime, sender, subject, recipient, match_status, employee_key,
          document_type, expected_item, review_status, extraction, provenance, error
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s
        )
        ON CONFLICT (company_code, message_id, content_sha256) DO UPDATE
          SET updated_at=now()
        RETURNING intake_id
        """,
        (
            str(intake_id),
            tenant,
            mid,
            content_sha,
            attachment_name,
            attachment_mime,
            sender,
            subject,
            recipient,
            match_status,
            (employee or {}).get("employee_key"),
            dtype,
            expected,
            review_status,
            json.dumps(receipt, default=str),
            json.dumps(provenance, default=str),
            error,
        ),
    )
    row = cur.fetchone()
    return {
        "ok": True,
        "intake_id": str((row or {}).get("intake_id") or intake_id),
        "company_code": tenant,
        "employee_key": (employee or {}).get("employee_key"),
        "document_type": dtype,
        "match_status": match_status,
        "review_status": review_status,
        "auto_attached": auto_attached,
        "extraction": receipt,
        "media_path": str(path),
        "gpt_used": False,
        "duplicate": False,
    }
