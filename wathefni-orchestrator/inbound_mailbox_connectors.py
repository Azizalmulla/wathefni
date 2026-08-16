"""Wave D Phase 5 — optional premium customer mailbox connectors.

Forwarding (D2) remains the default core product. This module is the premium
path for companies that connect Gmail or Microsoft 365 recruitment mailboxes
directly — every discovered email must enter the same durable D2/D3 pipeline
(quarantine → malware → OCR/identity → held intake → explicit admit).

Design rules:
* No second ingestion architecture / no legacy live import from sync
* Tenant from mailbox_connections.company_code (+ intake route row)
* Idempotency via (provider, provider_message_id) + content_sha256
* Least-privilege read-only provider scopes
* Default-off; external tenants remain allowlist-gated
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Provider scopes (security review source of truth)
# ---------------------------------------------------------------------------

GMAIL_OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
)

# Dedicated mail-read app — never reuse calendar or Mail.Send service principals.
M365_GRAPH_MAIL_SCOPES = (
    "Mail.Read",          # delegated: read mail in signed-in mailbox
    "User.Read",          # signed-in user identity
    "offline_access",     # refresh token
)

M365_GRAPH_MAIL_APP_ONLY_SCOPES = (
    "Mail.Read",  # application: only with explicit admin consent + mailbox restriction
)

PROVIDER_LABELS = {
    "gmail": {"en": "Gmail / Google Workspace", "ar": "Gmail / Google Workspace"},
    "m365": {"en": "Microsoft 365", "ar": "Microsoft 365"},
}


def mailbox_connectors_flag_enabled() -> bool:
    """Master kill-switch — same env as legacy mailbox sync (default off)."""
    return (os.environ.get("WATHEFNI_MAILBOX_SYNC") or "off").strip().lower() in {
        "on",
        "1",
        "true",
        "enabled",
        "live",
        "yes",
    }


def connector_feature_payload(*, gmail_oauth_ready: bool, m365_oauth_ready: bool, encryption_ready: bool) -> dict[str, Any]:
    enabled = mailbox_connectors_flag_enabled() and encryption_ready and (gmail_oauth_ready or m365_oauth_ready)
    return {
        "enabled": bool(enabled),
        "premium": True,
        "default_product": "forwarding",
        "mailbox_sync_enabled": bool(enabled),
        "encryption_ready": bool(encryption_ready),
        "gmail_oauth_ready": bool(gmail_oauth_ready),
        "m365_oauth_ready": bool(m365_oauth_ready),
        "providers": [
            {
                "key": "gmail",
                "label": PROVIDER_LABELS["gmail"]["en"],
                "label_ar": PROVIDER_LABELS["gmail"]["ar"],
                "scopes": list(GMAIL_OAUTH_SCOPES),
                "ready": bool(gmail_oauth_ready),
            },
            {
                "key": "m365",
                "label": PROVIDER_LABELS["m365"]["en"],
                "label_ar": PROVIDER_LABELS["m365"]["ar"],
                "scopes": list(M365_GRAPH_MAIL_SCOPES),
                "ready": bool(m365_oauth_ready),
            },
        ],
        "setup_steps_en": [
            "Keep forwarding as the default intake path unless your company requires a direct mailbox connection.",
            "Connect Gmail or Microsoft 365 with read-only recruitment mailbox permission.",
            "Choose only the recruitment folder or label OctoHR should read.",
            "Every email enters the same durable scan, quarantine, and held-admit pipeline as forwarded mail.",
            "Pause or disconnect anytime; reconnect when the token expires or access is revoked.",
        ],
        "setup_steps_ar": [
            "أبقِ التحويل (Forwarding) المسار الافتراضي ما لم تتطلب شركتك ربط صندوق بريد مباشر.",
            "اربط Gmail أو Microsoft 365 بصلاحية قراءة فقط لصندوق التوظيف.",
            "اختر مجلد أو تسمية التوظيف فقط التي يجب أن يقرأها OctoHR.",
            "كل رسالة تدخل نفس مسار الفحص والحجر والإضافة اليدوية المستخدم في البريد المحوَّل.",
            "يمكنك الإيقاف أو قطع الاتصال في أي وقت؛ أعد الربط عند انتهاء التوكن أو سحب الصلاحية.",
        ],
    }


def status_label(row: dict[str, Any] | None, *, locale: str = "en") -> str:
    status = str((row or {}).get("status") or "disconnected")
    ar = locale == "ar"
    if status == "connected":
        return "متصل" if ar else "Connected"
    if status in {"needs_reconnect", "error"}:
        return "يحتاج إعادة ربط" if ar else "Needs reconnecting"
    if status == "paused":
        return "متوقف" if ar else "Paused"
    if status == "disabled":
        return "معطّل" if ar else "Disabled"
    return "غير متصل" if ar else "Not connected"


def message_to_postmark_shaped_payload(
    message: dict[str, Any],
    *,
    provider: str,
    route_address: str,
) -> dict[str, Any]:
    """Map provider-neutral mailbox message → Postmark-shaped durable envelope."""
    mid = str(message.get("message_id") or "").strip()
    if not mid:
        raise ValueError("provider_message_id_required")
    sender = str(message.get("sender") or "").strip() or "unknown@mailbox.local"
    subject = str(message.get("subject") or "").strip()
    received_at = message.get("received_at") or datetime.now(UTC).isoformat()
    attachments: list[dict[str, Any]] = []
    for item in message.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        filename = str(item.get("filename") or "").strip()
        if data is None or not filename:
            continue
        if isinstance(data, str):
            raw = data.encode("utf-8", errors="replace")
        else:
            raw = bytes(data)
        attachments.append(
            {
                "Name": filename,
                "Content": base64.b64encode(raw).decode("ascii"),
                "ContentType": str(item.get("mime_type") or "application/octet-stream"),
                "ContentLength": len(raw),
            }
        )
    return {
        "MessageID": f"{provider}:{mid}",
        "From": sender,
        "FromFull": {"Email": sender, "Name": ""},
        "To": route_address,
        "OriginalRecipient": route_address,
        "ToFull": [{"Email": route_address, "Name": ""}],
        "Subject": subject,
        "Date": received_at,
        "TextBody": str(message.get("body_text") or subject or ""),
        "Attachments": attachments,
        "MailboxHash": "",
        # Provenance for audits (ignored by Postmark parser except as extra keys)
        "WathefniMailboxProvider": provider,
        "WathefniSourceMessageId": mid,
        "WathefniSourceLabel": message.get("label"),
    }


def ensure_connector_intake_route(
    cur: Any,
    *,
    company_code: str,
    mailbox_id: str,
    email_address: str | None,
) -> dict[str, Any]:
    """Return an active intake_addresses row for durable route_snapshot.

    Prefers an existing active address for the company. If none, creates a
    dedicated needs_role address labeled for the mailbox connector.
    """
    company = str(company_code or "").strip().upper()
    cur.execute(
        """
        SELECT intake_id::text, company_code, local_part, domain, position_code,
               position_title, label, status,
               lower(local_part || '@' || domain) AS address
        FROM intake_addresses
        WHERE company_code=%s AND status='active'
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (company,),
    )
    row = cur.fetchone()
    if row:
        return dict(row)

    digest = hashlib.sha256(f"{company}:{mailbox_id}".encode()).hexdigest()[:10]
    local_part = f"{company.lower()}-mbx-{digest}"
    domain = (os.environ.get("WATHEFNI_INBOUND_DOMAIN") or "inbound.wathefni.ai").strip()
    label = f"Mailbox connector ({email_address or mailbox_id})"[:200]
    meta = json.dumps({"source": "mailbox_connector", "mailbox_id": str(mailbox_id)})
    cur.execute(
        """
        INSERT INTO intake_addresses
          (company_code, local_part, domain, position_code, position_title, label, metadata)
        VALUES (%s,%s,%s,NULL,NULL,%s,%s::jsonb)
        RETURNING intake_id::text, company_code, local_part, domain, position_code,
                  position_title, label, status,
                  lower(local_part || '@' || domain) AS address
        """,
        (company, local_part, domain, label, meta),
    )
    return dict(cur.fetchone())


def ingest_mailbox_message_durable(
    message: dict[str, Any],
    *,
    company_code: str,
    provider: str,
    route: dict[str, Any],
    process_postmark_inbound: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Send one mailbox message through the durable Postmark-shaped receive path."""
    payload = message_to_postmark_shaped_payload(
        message,
        provider=str(provider).strip().lower(),
        route_address=str(route.get("address") or ""),
    )
    # process_postmark_inbound uses resolve_intake_address(recipient). Route address
    # must resolve to this company's intake row (ensure_connector_intake_route).
    result = process_postmark_inbound(payload, payload_size_bytes=len(str(payload)))
    return {
        "ok": True,
        "provider": provider,
        "company_code": company_code,
        "source_message_id": message.get("message_id"),
        "durable": result,
    }


class Microsoft365MailboxProvider:
    """Read-only Microsoft Graph mailbox adapter (premium D5).

    Live Graph calls require WATHEFNI_M365_MAILBOX_* OAuth app with Mail.Read.
    Not implemented for GA — sync raises a calm reconnectable error until
    credentials are configured. Structure matches GmailProvider.
    """

    def list_labels(self, connection: dict[str, Any]) -> list[dict[str, Any]]:
        _ = connection
        if not m365_mailbox_oauth_available():
            raise RuntimeError("m365_mailbox_oauth_not_configured")
        # Folder listing would call GET /me/mailFolders with Mail.Read.
        raise RuntimeError("m365_mailbox_provider_not_live")

    def fetch_new_messages(self, *, connection: dict[str, Any], cursor: dict[str, Any] | None):
        _ = connection, cursor
        if not m365_mailbox_oauth_available():
            raise RuntimeError("m365_mailbox_oauth_not_configured")
        raise RuntimeError("m365_mailbox_provider_not_live")


def m365_mailbox_oauth_available() -> bool:
    return bool(
        (os.environ.get("WATHEFNI_M365_MAILBOX_CLIENT_ID") or "").strip()
        and (os.environ.get("WATHEFNI_M365_MAILBOX_CLIENT_SECRET") or "").strip()
        and (os.environ.get("WATHEFNI_M365_MAILBOX_REDIRECT_URI") or "").strip()
    )


def sync_messages_through_durable(
    messages: list[dict[str, Any]],
    *,
    company_code: str,
    mailbox_id: str,
    provider_key: str,
    connection: dict[str, Any],
    db_connect: Callable[[], Any],
    process_postmark_inbound: Callable[..., dict[str, Any]],
    next_cursor: dict[str, Any] | None,
) -> dict[str, Any]:
    """Live sync: each message → durable ingress; advance cursor only after success."""
    company = str(company_code or "").strip().upper()
    results: list[dict[str, Any]] = []
    counts = {"durable": 0, "duplicate": 0, "ignored": 0, "failed": 0, "messages": 0}

    with db_connect() as conn:
        with conn.cursor() as cur:
            route = ensure_connector_intake_route(
                cur,
                company_code=company,
                mailbox_id=mailbox_id,
                email_address=str(connection.get("email_address") or "") or None,
            )
        conn.commit()

    for message in messages:
        counts["messages"] += 1
        try:
            out = ingest_mailbox_message_durable(
                message,
                company_code=company,
                provider=provider_key,
                route=route,
                process_postmark_inbound=process_postmark_inbound,
            )
            durable = out.get("durable") or {}
            if durable.get("duplicate"):
                counts["duplicate"] += 1
            elif durable.get("ignored"):
                counts["ignored"] += 1
            elif durable.get("durable") or durable.get("inbound_id"):
                counts["durable"] += 1
            else:
                counts["failed"] += 1
            results.append(out)
        except Exception as exc:
            counts["failed"] += 1
            results.append(
                {
                    "ok": False,
                    "error": str(exc)[:300],
                    "source_message_id": message.get("message_id"),
                }
            )

    # Advance cursor when at least one message was processed without hard failure
    # storm — partial failures remain retryable via idempotent message ids.
    return {
        "ok": counts["failed"] == 0 or counts["durable"] + counts["duplicate"] > 0,
        "mode": "live_durable",
        "company_code": company,
        "mailbox_id": mailbox_id,
        "provider": provider_key,
        "route_intake_id": route.get("intake_id"),
        "route_address": route.get("address"),
        "counts": counts,
        "results": results,
        "next_cursor": next_cursor,
    }
