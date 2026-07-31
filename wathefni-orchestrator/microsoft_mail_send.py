"""Microsoft Graph Mail.Send client (separate SP from Calendar/Teams).

Phase 1:
  - Application Mail.Send only (no Mail.Read / Mail.ReadWrite)
  - Exchange RBAC for Applications must scope the SP to approved operational mailboxes
  - saveToSentItems: true
  - Graph success means accepted by Microsoft, not confirmed SMTP delivery

Uses dedicated env (never the calendar SP):
  WATHEFNI_M365_MAIL_CLIENT_ID
  WATHEFNI_M365_MAIL_TENANT_ID   (falls back to WATHEFNI_M365_TENANT_ID)
  WATHEFNI_M365_MAIL_CERT_BUNDLE_PATH
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

GRAPH = "https://graph.microsoft.com/v1.0"


def _text(value: Any) -> str:
    return str(value or "").strip()


def mail_send_env() -> dict[str, str]:
    return {
        "client_id": _text(os.environ.get("WATHEFNI_M365_MAIL_CLIENT_ID")),
        "tenant_id": _text(os.environ.get("WATHEFNI_M365_MAIL_TENANT_ID") or os.environ.get("WATHEFNI_M365_TENANT_ID")),
        "bundle_path": _text(
            os.environ.get("WATHEFNI_M365_MAIL_CERT_BUNDLE_PATH")
            or os.environ.get("WATHEFNI_M365_MAIL_CERT_PATH")
            or ""
        ),
    }


def mail_send_configured() -> bool:
    cfg = mail_send_env()
    return bool(cfg["client_id"] and cfg["tenant_id"] and cfg["bundle_path"] and os.path.exists(cfg["bundle_path"]))


def mint_mail_graph_token() -> str:
    """Mint app-only token for the mail SP. Never uses calendar client id."""
    cfg = mail_send_env()
    if not mail_send_configured():
        raise RuntimeError("microsoft_mail_not_configured")
    # Guard: refuse to silently use calendar SP credentials
    calendar_client = _text(os.environ.get("WATHEFNI_M365_CLIENT_ID"))
    if calendar_client and cfg["client_id"] == calendar_client:
        raise RuntimeError("microsoft_mail_sp_must_differ_from_calendar_sp")
    import platform_connection_c6 as c6

    pem = open(cfg["bundle_path"], encoding="utf-8").read()
    try:
        return c6.mint_microsoft_app_token(
            tenant_id=cfg["tenant_id"],
            client_id=cfg["client_id"],
            certificate_pem=pem,
        )
    finally:
        del pem


def send_mail_as_mailbox(
    *,
    mailbox: str,
    to: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    save_to_sent_items: bool = True,
    content_type: str = "Text",
) -> dict[str, Any]:
    """Send via POST /users/{mailbox}/sendMail.

    Success ⇒ accepted_by_microsoft (not confirmed delivery).
    """
    mailbox_addr = _text(mailbox).lower()
    recipient = _text(to)
    if not mailbox_addr or "@" not in mailbox_addr:
        return {"ok": False, "provider": "microsoft_graph", "error": "mailbox_required", "provider_accept_status": "failed"}
    if not recipient or "@" not in recipient:
        return {"ok": False, "provider": "microsoft_graph", "error": "recipient_required", "provider_accept_status": "failed"}
    if not mail_send_configured():
        return {"ok": False, "provider": "microsoft_graph", "error": "microsoft_mail_not_configured", "provider_accept_status": "failed"}

    message: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": content_type if content_type in {"Text", "HTML"} else "Text", "content": body},
        "toRecipients": [{"emailAddress": {"address": recipient}}],
    }
    reply = _text(reply_to)
    if reply:
        message["replyTo"] = [{"emailAddress": {"address": reply}}]

    payload = {"message": message, "saveToSentItems": bool(save_to_sent_items)}
    try:
        token = mint_mail_graph_token()
    except Exception as exc:
        return {
            "ok": False,
            "provider": "microsoft_graph",
            "error": f"token_error:{type(exc).__name__}",
            "provider_accept_status": "failed",
        }

    url = f"{GRAPH}/users/{urllib.parse.quote(mailbox_addr)}/sendMail"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Graph sendMail returns 202 Accepted with empty body on success
            status_code = getattr(resp, "status", 202) or 202
            raw_body = resp.read().decode("utf-8") if hasattr(resp, "read") else ""
        ok = int(status_code) in {200, 202}
        return {
            "ok": ok,
            "provider": "microsoft_graph",
            "message_id": None,
            "error": None if ok else "microsoft_send_failed",
            "provider_accept_status": "accepted_by_provider" if ok else "failed",
            "user_status": "Accepted by Microsoft" if ok else "Error",
            "raw": {"http_status": status_code, "body": raw_body[:500] if raw_body else ""},
            "dry_run": False,
        }
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:300]
        except Exception:
            detail = ""
        return {
            "ok": False,
            "provider": "microsoft_graph",
            "error": f"microsoft_http_{exc.code}",
            "provider_accept_status": "failed",
            "user_status": "Error",
            "raw": {"http_status": exc.code, "body": detail},
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": "microsoft_graph",
            "error": f"microsoft_error:{type(exc).__name__}",
            "provider_accept_status": "failed",
            "user_status": "Error",
        }
