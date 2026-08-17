"""Tenant outbound email authority (Phase 1).

Defaults preserve current production behavior:
- outbound mode wathefni (technical mode name; global OctoHR Postmark From)
- no Microsoft inbound
- dual-send interview email off when calendar already invited

Company Settings projections stay product-language only (no SP/RBAC/capability IDs).
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

OUTBOUND_MODES = ("wathefni", "microsoft_mailbox", "postmark_company_domain")
DOMAIN_STATUSES = ("unconfigured", "pending_verification", "verified", "failed", "active")
MAILBOX_STATUSES = ("draft", "pending_admin", "approved", "disabled", "error")
UX_STATUSES = ("ready", "setup_required", "verifying", "error")

DEFAULT_OPERATIONAL_LOCAL_PARTS = ("careers", "hr", "onboarding", "payroll", "compliance")
_LEGACY_CUSTOMER_BRAND_RE = re.compile(r"\bwathefni\b|وظفني|وظّفني|وثفني|وثّفني", re.IGNORECASE)


def _customer_brand_text(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or _LEGACY_CUSTOMER_BRAND_RE.search(text):
        return None
    return text

POSTMARK_DOMAINS_API = "https://api.postmarkapp.com/domains"


class TenantEmailError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status

    def as_http_detail(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _company(code: str | None) -> str:
    return str(code or "").strip().upper()


def _norm_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _email_host(address: str | None) -> str:
    addr = _norm_email(address)
    if "@" not in addr:
        return ""
    return addr.split("@", 1)[1]


def _norm_domain(value: str | None) -> str:
    domain = str(value or "").strip().lower().rstrip(".")
    if domain.startswith("@"):
        domain = domain[1:]
    return domain


def postmark_account_token() -> str:
    return (os.environ.get("WATHEFNI_POSTMARK_ACCOUNT_TOKEN") or os.environ.get("POSTMARK_ACCOUNT_TOKEN") or "").strip()


def postmark_server_configured(legacy: Any | None = None) -> bool:
    if legacy is not None and hasattr(legacy, "outbound_postmark_available"):
        try:
            return bool(legacy.outbound_postmark_available())
        except Exception:
            pass
    token = (os.environ.get("WATHEFNI_POSTMARK_SERVER_TOKEN") or "").strip()
    from_addr = (os.environ.get("WATHEFNI_OUTBOUND_FROM") or "no-reply@octo-hr.com").strip()
    return bool(token and from_addr)


def microsoft_mail_send_configured() -> bool:
    try:
        import microsoft_mail_send as mms

        return bool(mms.mail_send_configured())
    except Exception:
        return False


def ensure_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_email_settings (
          company_code text PRIMARY KEY,
          outbound_mode text NOT NULL DEFAULT 'wathefni',
          display_name text,
          from_address text,
          reply_to text,
          company_name_en text,
          company_name_ar text,
          logo_url text,
          outbound_mailbox_id uuid,
          interview_email_when_calendar_sent boolean NOT NULL DEFAULT false,
          allow_wathefni_emergency_fallback boolean NOT NULL DEFAULT false,
          public_forward_address text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          updated_by_user_id text
        )
        """
    )
    cur.execute(
        "ALTER TABLE IF EXISTS company_email_settings ADD COLUMN IF NOT EXISTS allow_wathefni_emergency_fallback boolean NOT NULL DEFAULT false"
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_operational_mailboxes (
          mailbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          address text NOT NULL,
          display_name text,
          provider text NOT NULL DEFAULT 'microsoft',
          allow_send boolean NOT NULL DEFAULT false,
          status text NOT NULL DEFAULT 'draft',
          entra_user_id text,
          exchange_scope_ref text,
          last_probe_at timestamptz,
          last_probe_ok boolean,
          last_error text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, address)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS company_email_domains (
          domain_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          domain text NOT NULL,
          verification_status text NOT NULL DEFAULT 'unconfigured',
          postmark_domain_id text,
          dkim_host text,
          dkim_value text,
          return_path_domain text,
          spf_host text,
          spf_value text,
          last_checked_at timestamptz,
          last_error text,
          verified_at timestamptz,
          activated_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, domain)
        )
        """
    )
    for col_sql in (
        "ALTER TABLE IF EXISTS outbound_delivery_events ADD COLUMN IF NOT EXISTS sender_mode text",
        "ALTER TABLE IF EXISTS outbound_delivery_events ADD COLUMN IF NOT EXISTS visible_from text",
        "ALTER TABLE IF EXISTS outbound_delivery_events ADD COLUMN IF NOT EXISTS visible_reply_to text",
        "ALTER TABLE IF EXISTS outbound_delivery_events ADD COLUMN IF NOT EXISTS provider text",
        "ALTER TABLE IF EXISTS outbound_delivery_events ADD COLUMN IF NOT EXISTS purpose text",
        "ALTER TABLE IF EXISTS outbound_delivery_events ADD COLUMN IF NOT EXISTS provider_accept_status text",
    ):
        cur.execute(col_sql)


def default_settings(company_code: str | None = None) -> dict[str, Any]:
    return {
        "company_code": _company(company_code) or None,
        "outbound_mode": "wathefni",
        "display_name": None,
        "from_address": None,
        "reply_to": None,
        "company_name_en": None,
        "company_name_ar": None,
        "logo_url": None,
        "outbound_mailbox_id": None,
        "interview_email_when_calendar_sent": False,
        "allow_wathefni_emergency_fallback": False,
        "public_forward_address": None,
        "updated_at": None,
        "updated_by_user_id": None,
    }


def _row_settings(row: dict[str, Any] | None, company_code: str) -> dict[str, Any]:
    base = default_settings(company_code)
    if not row:
        return base
    out = dict(base)
    out.update(
        {
            "company_code": company_code,
            "outbound_mode": str(row.get("outbound_mode") or "wathefni"),
            "display_name": row.get("display_name"),
            "from_address": row.get("from_address"),
            "reply_to": row.get("reply_to"),
            "company_name_en": row.get("company_name_en"),
            "company_name_ar": row.get("company_name_ar"),
            "logo_url": row.get("logo_url"),
            "outbound_mailbox_id": str(row["outbound_mailbox_id"]) if row.get("outbound_mailbox_id") else None,
            "interview_email_when_calendar_sent": bool(row.get("interview_email_when_calendar_sent")),
            "allow_wathefni_emergency_fallback": bool(row.get("allow_wathefni_emergency_fallback")),
            "public_forward_address": row.get("public_forward_address"),
            "updated_at": row.get("updated_at"),
            "updated_by_user_id": row.get("updated_by_user_id"),
        }
    )
    if out["outbound_mode"] not in OUTBOUND_MODES:
        out["outbound_mode"] = "wathefni"
    return out


def get_email_settings(legacy: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    if not company:
        return default_settings()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute("SELECT * FROM company_email_settings WHERE company_code=%s", (company,))
            row = cur.fetchone()
        conn.commit()
    return _row_settings(dict(row) if row else None, company)


def list_operational_mailboxes(legacy: Any, company_code: str, *, include_disabled: bool = True) -> list[dict[str, Any]]:
    company = _company(company_code)
    if not company:
        return []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if include_disabled:
                cur.execute(
                    """
                    SELECT *, mailbox_id::text AS mailbox_id
                    FROM company_operational_mailboxes
                    WHERE company_code=%s
                    ORDER BY lower(address)
                    """,
                    (company,),
                )
            else:
                cur.execute(
                    """
                    SELECT *, mailbox_id::text AS mailbox_id
                    FROM company_operational_mailboxes
                    WHERE company_code=%s AND status <> 'disabled'
                    ORDER BY lower(address)
                    """,
                    (company,),
                )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return rows


def list_email_domains(legacy: Any, company_code: str) -> list[dict[str, Any]]:
    company = _company(company_code)
    if not company:
        return []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT *, domain_id::text AS domain_id
                FROM company_email_domains
                WHERE company_code=%s
                ORDER BY lower(domain)
                """,
                (company,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return rows


def get_mailbox(legacy: Any, company_code: str, mailbox_id: str) -> dict[str, Any] | None:
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT *, mailbox_id::text AS mailbox_id
                FROM company_operational_mailboxes
                WHERE company_code=%s AND mailbox_id=%s
                """,
                (company, mailbox_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def approved_send_mailboxes(legacy: Any, company_code: str) -> list[dict[str, Any]]:
    return [
        m
        for m in list_operational_mailboxes(legacy, company_code, include_disabled=False)
        if m.get("status") == "approved"
        and bool(m.get("allow_send"))
        and m.get("provider") == "microsoft"
        and bool(m.get("last_probe_ok"))
    ]


def microsoft_mailbox_ready(mailbox: dict[str, Any] | None) -> bool:
    if not mailbox:
        return False
    return bool(
        mailbox.get("status") == "approved"
        and mailbox.get("allow_send")
        and mailbox.get("provider") == "microsoft"
        and mailbox.get("last_probe_ok")
        and microsoft_mail_send_configured()
    )


def verified_domains(legacy: Any, company_code: str) -> list[dict[str, Any]]:
    return [
        d
        for d in list_email_domains(legacy, company_code)
        if str(d.get("verification_status") or "") in {"verified", "active"}
    ]


def mode_availability(legacy: Any, company_code: str, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = settings or get_email_settings(legacy, company_code)
    wathefni_ok = postmark_server_configured(legacy)
    ms_mailboxes = approved_send_mailboxes(legacy, company_code)
    ms_ready = bool(microsoft_mail_send_configured() and ms_mailboxes)
    domains = verified_domains(legacy, company_code)
    from_host = _email_host(settings.get("from_address"))
    domain_match = any(str(d.get("domain") or "") == from_host for d in domains) if from_host else False
    pending_domains = [
        d for d in list_email_domains(legacy, company_code) if str(d.get("verification_status") or "") == "pending_verification"
    ]
    failed_domains = [d for d in list_email_domains(legacy, company_code) if str(d.get("verification_status") or "") == "failed"]
    company_domain_ready = bool(postmark_account_token() and domain_match and postmark_server_configured(legacy))

    matrix = {
        "wathefni": {
            "available": wathefni_ok,
            "status": "ready" if wathefni_ok else "setup_required",
            "reason": None if wathefni_ok else "wathefni_sender_unavailable",
        },
        "microsoft_mailbox": {
            "available": ms_ready,
            "status": (
                "ready"
                if ms_ready
                else "error"
                if any(m.get("status") == "error" or m.get("last_probe_ok") is False for m in list_operational_mailboxes(legacy, company_code))
                else "setup_required"
            ),
            "reason": None
            if ms_ready
            else (
                "microsoft_not_configured"
                if not microsoft_mail_send_configured()
                else "mailbox_probe_required"
                if any(m.get("status") == "approved" and m.get("allow_send") and not m.get("last_probe_ok") for m in list_operational_mailboxes(legacy, company_code))
                else "mailbox_setup_required"
            ),
        },
        "postmark_company_domain": {
            "available": company_domain_ready,
            "status": (
                "ready"
                if company_domain_ready
                else "error"
                if failed_domains
                else "verifying"
                if pending_domains
                else "setup_required"
            ),
            "reason": None if company_domain_ready else ("domain_verifying" if pending_domains else "domain_verification_required"),
        },
    }
    return matrix


def resolve_outbound_sender(
    legacy: Any,
    company_code: str | None,
    *,
    purpose: str | None = None,
    for_send: bool = True,
) -> dict[str, Any]:
    """Resolve visible From / Reply-To / provider for a send.

    Missing settings / legacy / explicit wathefni ⇒ global OctoHR Postmark.
    Branded modes never silently switch to the global sender.
    If an active branded provider is unavailable:
      - default: fail closed (activatable=False)
      - optional allow_wathefni_emergency_fallback: send via OctoHR and flag audit
    """
    company = _company(company_code)
    cfg = None
    if legacy is not None and hasattr(legacy, "outbound_postmark_config"):
        try:
            cfg = legacy.outbound_postmark_config()
        except Exception:
            cfg = None
    cfg = cfg or {
        "from_address": (os.environ.get("WATHEFNI_OUTBOUND_FROM") or "no-reply@octo-hr.com").strip(),
        "reply_to": (os.environ.get("WATHEFNI_OUTBOUND_REPLY_TO") or "support@octo-hr.com").strip(),
    }
    global_from = str(cfg.get("from_address") or "no-reply@octo-hr.com").strip()
    global_reply = str(cfg.get("reply_to") or "").strip() or None

    def _wathefni(
        display_name: str | None = None,
        reply_to: str | None = None,
        branding: dict[str, Any] | None = None,
        *,
        emergency_fallback_used: bool = False,
        intended_mode: str | None = None,
        intended_from: str | None = None,
    ) -> dict[str, Any]:
        return {
            "mode": "wathefni" if not emergency_fallback_used else "wathefni",
            "selected_mode": intended_mode or "wathefni",
            "from_address": global_from,
            "reply_to": reply_to or global_reply,
            "display_name": display_name or "OctoHR",
            "provider": "postmark",
            "mailbox_id": None,
            "activatable": True,
            "block_reason": None,
            "purpose": purpose,
            "branding": branding or {},
            "emergency_fallback_used": bool(emergency_fallback_used),
            "intended_mode": intended_mode,
            "intended_from": intended_from,
            "user_status": (
                "Sent through OctoHR (emergency fallback)"
                if emergency_fallback_used
                else None
            ),
            "hr_notice": (
                "Your selected company sender was unavailable, so this message was sent through OctoHR as an emergency fallback."
                if emergency_fallback_used
                else None
            ),
        }

    if not company:
        return _wathefni()

    settings = get_email_settings(legacy, company)
    mode = str(settings.get("outbound_mode") or "wathefni")
    if mode not in OUTBOUND_MODES:
        mode = "wathefni"
    company_name_en = _customer_brand_text(settings.get("company_name_en"))
    company_name_ar = _customer_brand_text(settings.get("company_name_ar"))
    branding = {
        "company_name_en": company_name_en,
        "company_name_ar": company_name_ar,
        # Do not pair a legacy-branded tenant record with an old logo.
        "logo_url": settings.get("logo_url") if company_name_en or company_name_ar else None,
    }
    display_name = _customer_brand_text(settings.get("display_name"))
    # Activation happens before the tenant workspace is established on-device.
    # Keep this security-sensitive message under the platform identity even when
    # a tenant has configured a customer-facing sender display name.
    if str(purpose or "").strip().lower() == "app_activation":
        display_name = "OctoHR"
    reply_to = str(settings.get("reply_to") or "").strip() or global_reply
    emergency = bool(settings.get("allow_wathefni_emergency_fallback"))

    if mode == "wathefni":
        out = _wathefni(display_name, reply_to, branding)
        out["selected_mode"] = "wathefni"
        return out

    def _maybe_emergency(block_reason: str, intended_from: str | None, provider: str) -> dict[str, Any]:
        if for_send and emergency:
            return _wathefni(
                display_name,
                reply_to,
                branding,
                emergency_fallback_used=True,
                intended_mode=mode,
                intended_from=intended_from,
            )
        return {
            "mode": mode,
            "selected_mode": mode,
            "from_address": intended_from,
            "reply_to": reply_to,
            "display_name": display_name,
            "provider": provider,
            "mailbox_id": None,
            "activatable": False,
            "block_reason": block_reason,
            "purpose": purpose,
            "branding": branding,
            "emergency_fallback_used": False,
            "intended_mode": mode,
            "intended_from": intended_from,
            "user_status": "Error",
            "hr_notice": _block_message(block_reason),
        }

    if mode == "microsoft_mailbox":
        mailbox = None
        mailbox_id = settings.get("outbound_mailbox_id")
        if mailbox_id:
            mailbox = get_mailbox(legacy, company, str(mailbox_id))
        if not mailbox:
            approved = approved_send_mailboxes(legacy, company)
            mailbox = approved[0] if approved else None
        # Also consider approved-but-unprobed for clearer errors (not in approved_send_mailboxes)
        if not mailbox:
            candidates = [
                m
                for m in list_operational_mailboxes(legacy, company, include_disabled=False)
                if m.get("status") == "approved" and m.get("allow_send") and m.get("provider") == "microsoft"
            ]
            mailbox = candidates[0] if candidates else None
        intended_from = _norm_email((mailbox or {}).get("address")) if mailbox else None
        if not microsoft_mailbox_ready(mailbox):
            if not mailbox:
                reason = "microsoft_mailbox_not_approved"
            elif not microsoft_mail_send_configured():
                reason = "microsoft_mail_not_configured"
            elif not mailbox.get("last_probe_ok"):
                reason = "mailbox_probe_required"
            else:
                reason = "microsoft_mailbox_not_approved"
            return _maybe_emergency(reason, intended_from, "microsoft_graph")
        return {
            "mode": "microsoft_mailbox",
            "selected_mode": "microsoft_mailbox",
            "from_address": intended_from,
            "reply_to": reply_to,
            "display_name": display_name or str((mailbox or {}).get("display_name") or "").strip() or None,
            "provider": "microsoft_graph",
            "mailbox_id": str(mailbox.get("mailbox_id")),
            "activatable": True,
            "block_reason": None,
            "purpose": purpose,
            "branding": branding,
            "emergency_fallback_used": False,
            "intended_mode": "microsoft_mailbox",
            "intended_from": intended_from,
            "user_status": "Accepted by Microsoft",
            "hr_notice": None,
        }

    # postmark_company_domain
    from_address = _norm_email(settings.get("from_address"))
    host = _email_host(from_address)
    domains = verified_domains(legacy, company)
    matched = next((d for d in domains if str(d.get("domain") or "") == host), None) if host else None
    if not from_address or not matched or not postmark_server_configured(legacy):
        reason = "company_domain_not_verified" if not matched else "wathefni_sender_unavailable"
        return _maybe_emergency(reason, from_address or None, "postmark")
    return {
        "mode": "postmark_company_domain",
        "selected_mode": "postmark_company_domain",
        "from_address": from_address,
        "reply_to": reply_to,
        "display_name": display_name,
        "provider": "postmark",
        "mailbox_id": None,
        "activatable": True,
        "block_reason": None,
        "purpose": purpose,
        "branding": branding,
        "emergency_fallback_used": False,
        "intended_mode": "postmark_company_domain",
        "intended_from": from_address,
        "user_status": None,
        "hr_notice": None,
    }


def assert_sender_allowed(resolved: dict[str, Any]) -> None:
    if resolved.get("activatable") and resolved.get("from_address"):
        return
    reason = str(resolved.get("block_reason") or "sender_not_ready")
    raise TenantEmailError(reason, _block_message(reason), http_status=409)


def _block_message(reason: str) -> str:
    return {
        "company_domain_not_verified": "Company domain sending is not ready until the domain is verified.",
        "microsoft_mailbox_not_approved": "Microsoft mailbox sending needs an approved mailbox from OctoHR support.",
        "microsoft_mail_not_configured": "Microsoft mailbox sending is not available yet.",
        "mailbox_probe_required": "Microsoft mailbox sending needs a successful connection check before it can be used.",
        "sender_not_ready": "Email sending is not ready for this choice yet.",
        "wathefni_sender_unavailable": "OctoHR email sending is temporarily unavailable.",
        "branded_sender_unavailable": "Your selected company sender is unavailable. Turn on emergency fallback in Settings, or switch back to OctoHR.",
    }.get(reason, "Email sending is not ready for this choice yet.")


def format_from_header(display_name: str | None, from_address: str) -> str:
    addr = str(from_address or "").strip()
    name = _customer_brand_text(display_name) or ""
    if not name:
        return addr
    safe = name.replace('"', "")
    return f'"{safe}" <{addr}>'


def branding_for_company(legacy: Any, company_code: str | None) -> dict[str, Any]:
    if not company_code:
        return {}
    settings = get_email_settings(legacy, company_code)
    company_name_en = _customer_brand_text(settings.get("company_name_en"))
    company_name_ar = _customer_brand_text(settings.get("company_name_ar"))
    return {
        "company_name_en": company_name_en,
        "company_name_ar": company_name_ar,
        "logo_url": settings.get("logo_url") if company_name_en or company_name_ar else None,
        "display_name": _customer_brand_text(settings.get("display_name")) or "OctoHR",
    }


def should_skip_interview_email_for_calendar(
    legacy: Any,
    *,
    company_code: str | None,
    interview: dict[str, Any] | None,
    explicit: bool = False,
) -> tuple[bool, str | None]:
    """Return (skip, reason). Explicit manual send never auto-skips.

    Only skips when a real calendar attendee invite succeeded
    (calendar_invite_sent + candidate email). Failed calendar sync must not suppress email.
    """
    if explicit:
        return False, None
    if not interview:
        return False, None
    calendar_sent = bool(interview.get("calendar_invite_sent"))
    candidate_email = _norm_email(interview.get("candidate_email"))
    # Failed / incomplete calendar invite must not suppress transactional email.
    if not calendar_sent or not candidate_email:
        return False, None
    # Provider sync failure markers never count as a successful attendee invite.
    if interview.get("calendar_invite_failed") or interview.get("provider_sync_ok") is False:
        return False, None
    settings = get_email_settings(legacy, company_code or "")
    if bool(settings.get("interview_email_when_calendar_sent")):
        return False, None
    return True, "calendar_invite_already_sent"


def public_email_sending_view(
    legacy: Any,
    company_code: str,
    *,
    intake_addresses: list[dict[str, Any]] | None = None,
    intake_feature: dict[str, Any] | None = None,
    intake_setup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Company-facing Settings projection — no internal architecture language."""
    company = _company(company_code)
    settings = get_email_settings(legacy, company)
    matrix = mode_availability(legacy, company, settings)
    mode = settings.get("outbound_mode") or "wathefni"
    current = matrix.get(mode) or matrix["wathefni"]
    status = str(current.get("status") or "setup_required")
    if status not in UX_STATUSES:
        status = "setup_required"

    choices = [
        {
            "id": "wathefni",
            "title": "Send through OctoHR",
            "description": "Ready immediately",
            "recommended": False,
            "status": matrix["wathefni"]["status"],
            "selectable": bool(matrix["wathefni"]["available"]),
        },
        {
            "id": "microsoft_mailbox",
            "title": "Send from our Microsoft mailbox",
            "description": "Recommended for Microsoft 365",
            "recommended": True,
            "status": matrix["microsoft_mailbox"]["status"],
            "selectable": bool(matrix["microsoft_mailbox"]["available"]),
        },
        {
            "id": "postmark_company_domain",
            "title": "Send from our company domain",
            "description": "DNS verification required",
            "recommended": False,
            "status": matrix["postmark_company_domain"]["status"],
            "selectable": bool(matrix["postmark_company_domain"]["available"]),
        },
    ]

    primary_action = None
    if mode == "wathefni" and matrix["wathefni"]["available"]:
        primary_action = {"id": "test", "label": "Test"}
    elif mode == "microsoft_mailbox":
        primary_action = {"id": "connect", "label": "Connect"} if not matrix["microsoft_mailbox"]["available"] else {"id": "test", "label": "Test"}
    elif mode == "postmark_company_domain":
        if matrix["postmark_company_domain"]["status"] in {"setup_required", "verifying", "error"}:
            primary_action = {"id": "verify", "label": "Verify"}
        else:
            primary_action = {"id": "test", "label": "Test"}

    resolved = resolve_outbound_sender(legacy, company, purpose="settings_preview", for_send=False)
    visible_from = None
    if mode == "wathefni":
        visible_from = resolved.get("from_address")
    elif resolved.get("activatable"):
        visible_from = resolved.get("from_address")
    elif resolved.get("intended_from"):
        visible_from = resolved.get("intended_from")

    intake = intake_addresses or []
    intake_public = []
    for row in intake:
        addr = row.get("address") or row.get("email") or ""
        if not addr and row.get("local_part"):
            domain = row.get("domain") or "inbound.wathefni.ai"
            addr = f"{row.get('local_part')}@{domain}"
        if addr:
            entry = {
                "intake_id": row.get("intake_id"),
                "address": addr,
                "label": row.get("label") or row.get("position_title"),
                "status": row.get("status") or "active",
                "position_code": row.get("position_code"),
                "position_title": row.get("position_title"),
                "role_bound": bool(row.get("role_bound") if "role_bound" in row else row.get("position_code")),
                "hold_policy": row.get("hold_policy") or ("role_bound" if row.get("position_code") else "needs_role"),
                "health": row.get("health") if isinstance(row.get("health"), dict) else None,
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            intake_public.append(entry)

    setup = intake_setup if isinstance(intake_setup, dict) else {}
    primary = next((r.get("address") for r in intake_public if r.get("status") == "active"), None)
    if not setup:
        try:
            import inbound_intake_product as _iip

            setup = _iip.setup_instructions(primary_address=primary)
        except Exception:
            setup = {
                "forward_instructions_en": (
                    "Forward CVs and documents to your OctoHR intake address. "
                    "OctoHR does not read your Microsoft inbox for documents in this phase."
                ),
                "forward_instructions_ar": (
                    "قم بتحويل السير الذاتية والمستندات إلى عنوان استقبال OctoHR. "
                    "لا يقرأ OctoHR صندوق بريد مايكروسوفت للمستندات في هذه المرحلة."
                ),
                "setup_steps_en": [],
                "setup_steps_ar": [],
            }

    feature = intake_feature if isinstance(intake_feature, dict) else {"enabled": bool(intake_public), "domain": "inbound.wathefni.ai"}

    return {
        "company_code": company,
        "current_sender": mode,
        "status": status,
        "status_label": {
            "ready": "Ready",
            "setup_required": "Setup required",
            "verifying": "Verifying",
            "error": "Error",
        }.get(status, "Setup required"),
        "choices": choices,
        "display_name": settings.get("display_name"),
        "reply_to": settings.get("reply_to"),
        "visible_from": visible_from,
        "interview_email_when_calendar_sent": bool(settings.get("interview_email_when_calendar_sent")),
        "allow_wathefni_emergency_fallback": bool(settings.get("allow_wathefni_emergency_fallback")),
        "primary_action": primary_action,
        "hr_notice": resolved.get("hr_notice"),
        "intake": {
            "feature": feature,
            "addresses": intake_public,
            "public_forward_address": settings.get("public_forward_address"),
            "forward_instructions_en": setup.get("forward_instructions_en") or "",
            "forward_instructions_ar": setup.get("forward_instructions_ar") or "",
            "setup_steps_en": list(setup.get("setup_steps_en") or []),
            "setup_steps_ar": list(setup.get("setup_steps_ar") or []),
            "inbound_forwarding_enabled": company_settings_flag(legacy, company),
        },
    }


def company_settings_flag(legacy: Any, company_code: str) -> bool | None:
    try:
        settings = legacy.get_company_settings(company_code) if hasattr(legacy, "get_company_settings") else {}
        if not isinstance(settings, dict):
            return None
        if "inbound_forwarding_enabled" not in settings:
            return None
        return bool(settings.get("inbound_forwarding_enabled"))
    except Exception:
        return None


def admin_email_snapshot(legacy: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    settings = get_email_settings(legacy, company)
    return {
        "company_code": company,
        "settings": settings,
        "mode_availability": mode_availability(legacy, company, settings),
        "mailboxes": list_operational_mailboxes(legacy, company),
        "domains": list_email_domains(legacy, company),
        "microsoft_mail_configured": microsoft_mail_send_configured(),
        "postmark_account_configured": bool(postmark_account_token()),
        "postmark_server_configured": postmark_server_configured(legacy),
        "resolved": resolve_outbound_sender(legacy, company, purpose="admin_preview"),
    }


def upsert_email_settings(
    legacy: Any,
    company_code: str,
    patch: dict[str, Any],
    *,
    updated_by_user_id: str | None = None,
    allow_unready_mode: bool = False,
) -> dict[str, Any]:
    company = _company(company_code)
    if not company:
        raise TenantEmailError("tenant_scope_required", "Company is required.")
    current = get_email_settings(legacy, company)
    next_settings = dict(current)

    if "display_name" in patch:
        next_settings["display_name"] = str(patch.get("display_name") or "").strip() or None
    if "reply_to" in patch:
        reply = _norm_email(patch.get("reply_to"))
        next_settings["reply_to"] = reply or None
    if "from_address" in patch:
        next_settings["from_address"] = _norm_email(patch.get("from_address")) or None
    if "company_name_en" in patch:
        next_settings["company_name_en"] = str(patch.get("company_name_en") or "").strip() or None
    if "company_name_ar" in patch:
        next_settings["company_name_ar"] = str(patch.get("company_name_ar") or "").strip() or None
    if "logo_url" in patch:
        next_settings["logo_url"] = str(patch.get("logo_url") or "").strip() or None
    if "public_forward_address" in patch:
        next_settings["public_forward_address"] = _norm_email(patch.get("public_forward_address")) or None
    if "interview_email_when_calendar_sent" in patch:
        next_settings["interview_email_when_calendar_sent"] = bool(patch.get("interview_email_when_calendar_sent"))
    if "allow_wathefni_emergency_fallback" in patch:
        next_settings["allow_wathefni_emergency_fallback"] = bool(patch.get("allow_wathefni_emergency_fallback"))
    if "outbound_mailbox_id" in patch:
        mid = str(patch.get("outbound_mailbox_id") or "").strip() or None
        if mid:
            mb = get_mailbox(legacy, company, mid)
            if not mb:
                raise TenantEmailError("mailbox_not_found", "That mailbox was not found for this company.", http_status=404)
        next_settings["outbound_mailbox_id"] = mid

    if "outbound_mode" in patch:
        mode = str(patch.get("outbound_mode") or "").strip()
        if mode not in OUTBOUND_MODES:
            raise TenantEmailError("invalid_outbound_mode", "Choose a valid email sending option.")
        # Branded modes cannot become active until fully ready (unless admin allow_unready_mode).
        if mode != "wathefni" and not allow_unready_mode:
            probe = dict(next_settings)
            probe["outbound_mode"] = mode
            matrix = mode_availability(legacy, company, probe)
            if not matrix.get(mode, {}).get("available"):
                raise TenantEmailError(
                    "mode_not_ready",
                    _block_message(str(matrix.get(mode, {}).get("reason") or "sender_not_ready")),
                    http_status=409,
                )
            if mode == "postmark_company_domain":
                assert_no_unverified_company_from(legacy, company, probe.get("from_address"))
            if mode == "microsoft_mailbox":
                approved = approved_send_mailboxes(legacy, company)
                if not approved or not microsoft_mail_send_configured():
                    raise TenantEmailError(
                        "mode_not_ready",
                        _block_message("mailbox_probe_required" if approved else "microsoft_mailbox_not_approved"),
                        http_status=409,
                    )
        next_settings["outbound_mode"] = mode

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                INSERT INTO company_email_settings (
                  company_code, outbound_mode, display_name, from_address, reply_to,
                  company_name_en, company_name_ar, logo_url, outbound_mailbox_id,
                  interview_email_when_calendar_sent, allow_wathefni_emergency_fallback, public_forward_address,
                  updated_at, updated_by_user_id
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s)
                ON CONFLICT (company_code) DO UPDATE SET
                  outbound_mode=EXCLUDED.outbound_mode,
                  display_name=EXCLUDED.display_name,
                  from_address=EXCLUDED.from_address,
                  reply_to=EXCLUDED.reply_to,
                  company_name_en=EXCLUDED.company_name_en,
                  company_name_ar=EXCLUDED.company_name_ar,
                  logo_url=EXCLUDED.logo_url,
                  outbound_mailbox_id=EXCLUDED.outbound_mailbox_id,
                  interview_email_when_calendar_sent=EXCLUDED.interview_email_when_calendar_sent,
                  allow_wathefni_emergency_fallback=EXCLUDED.allow_wathefni_emergency_fallback,
                  public_forward_address=EXCLUDED.public_forward_address,
                  updated_at=now(),
                  updated_by_user_id=EXCLUDED.updated_by_user_id
                """,
                (
                    company,
                    next_settings["outbound_mode"],
                    next_settings.get("display_name"),
                    next_settings.get("from_address"),
                    next_settings.get("reply_to"),
                    next_settings.get("company_name_en"),
                    next_settings.get("company_name_ar"),
                    next_settings.get("logo_url"),
                    next_settings.get("outbound_mailbox_id"),
                    bool(next_settings.get("interview_email_when_calendar_sent")),
                    bool(next_settings.get("allow_wathefni_emergency_fallback")),
                    next_settings.get("public_forward_address"),
                    updated_by_user_id,
                ),
            )
        conn.commit()
    return get_email_settings(legacy, company)


def force_wathefni_fallback(legacy: Any, company_code: str, *, updated_by_user_id: str | None = None) -> dict[str, Any]:
    return upsert_email_settings(
        legacy,
        company_code,
        {"outbound_mode": "wathefni"},
        updated_by_user_id=updated_by_user_id,
        allow_unready_mode=True,
    )


def assert_no_unverified_company_from(legacy: Any, company_code: str, from_address: str | None) -> None:
    addr = _norm_email(from_address)
    host = _email_host(addr)
    if not addr or not host:
        raise TenantEmailError("from_address_required", "Enter a From address on your verified company domain.")
    domains = verified_domains(legacy, company_code)
    if not any(str(d.get("domain") or "") == host for d in domains):
        raise TenantEmailError(
            "unverified_company_from",
            "Cannot send from that address until the company domain is verified.",
            http_status=409,
        )


def upsert_operational_mailbox(
    legacy: Any,
    company_code: str,
    *,
    address: str,
    display_name: str | None = None,
    provider: str = "microsoft",
    allow_send: bool = False,
    status: str = "draft",
    entra_user_id: str | None = None,
    exchange_scope_ref: str | None = None,
    last_error: str | None = None,
) -> dict[str, Any]:
    company = _company(company_code)
    addr = _norm_email(address)
    if not company or not addr or "@" not in addr:
        raise TenantEmailError("mailbox_address_required", "A valid mailbox address is required.")
    if status not in MAILBOX_STATUSES:
        raise TenantEmailError("invalid_mailbox_status", "Invalid mailbox status.")
    if provider not in {"microsoft", "label_only"}:
        raise TenantEmailError("invalid_mailbox_provider", "Unsupported mailbox provider.")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                INSERT INTO company_operational_mailboxes (
                  mailbox_id, company_code, address, display_name, provider, allow_send, status,
                  entra_user_id, exchange_scope_ref, last_error, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT (company_code, address) DO UPDATE SET
                  display_name=EXCLUDED.display_name,
                  provider=EXCLUDED.provider,
                  allow_send=EXCLUDED.allow_send,
                  status=EXCLUDED.status,
                  entra_user_id=COALESCE(EXCLUDED.entra_user_id, company_operational_mailboxes.entra_user_id),
                  exchange_scope_ref=COALESCE(EXCLUDED.exchange_scope_ref, company_operational_mailboxes.exchange_scope_ref),
                  last_error=EXCLUDED.last_error,
                  updated_at=now()
                RETURNING *, mailbox_id::text AS mailbox_id
                """,
                (
                    str(uuid.uuid4()),
                    company,
                    addr,
                    str(display_name or "").strip() or None,
                    provider,
                    bool(allow_send),
                    status,
                    entra_user_id,
                    exchange_scope_ref,
                    last_error,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return row


def set_mailbox_status(
    legacy: Any,
    company_code: str,
    mailbox_id: str,
    *,
    status: str,
    allow_send: bool | None = None,
    last_error: str | None = None,
    exchange_scope_ref: str | None = None,
    entra_user_id: str | None = None,
) -> dict[str, Any]:
    company = _company(company_code)
    if status not in MAILBOX_STATUSES:
        raise TenantEmailError("invalid_mailbox_status", "Invalid mailbox status.")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                UPDATE company_operational_mailboxes
                SET status=%s,
                    allow_send=COALESCE(%s, allow_send),
                    last_error=%s,
                    exchange_scope_ref=COALESCE(%s, exchange_scope_ref),
                    entra_user_id=COALESCE(%s, entra_user_id),
                    updated_at=now()
                WHERE company_code=%s AND mailbox_id=%s
                RETURNING *, mailbox_id::text AS mailbox_id
                """,
                (status, allow_send, last_error, exchange_scope_ref, entra_user_id, company, mailbox_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise TenantEmailError("mailbox_not_found", "Mailbox not found.", http_status=404)
    return dict(row)


def seed_default_operational_mailboxes(legacy: Any, company_code: str, *, domain: str | None = None) -> list[dict[str, Any]]:
    """Admin helper: create draft careers/hr/... rows. Does not approve send."""
    company = _company(company_code)
    host = _norm_domain(domain)
    if not host:
        raise TenantEmailError("domain_required", "Provide a company domain for mailbox drafts.")
    out = []
    for local in DEFAULT_OPERATIONAL_LOCAL_PARTS:
        out.append(
            upsert_operational_mailbox(
                legacy,
                company,
                address=f"{local}@{host}",
                display_name=local.title(),
                provider="microsoft",
                allow_send=False,
                status="draft",
            )
        )
    return out


def record_mailbox_probe(legacy: Any, company_code: str, mailbox_id: str, *, ok: bool, error: str | None = None) -> dict[str, Any]:
    company = _company(company_code)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                UPDATE company_operational_mailboxes
                SET last_probe_at=now(),
                    last_probe_ok=%s,
                    last_error=%s,
                    status=CASE WHEN %s THEN status ELSE 'error' END,
                    updated_at=now()
                WHERE company_code=%s AND mailbox_id=%s
                RETURNING *, mailbox_id::text AS mailbox_id
                """,
                (ok, None if ok else (error or "probe_failed")[:500], ok, company, mailbox_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise TenantEmailError("mailbox_not_found", "Mailbox not found.", http_status=404)
    return dict(row)


# --- Postmark Domains API -------------------------------------------------


def _postmark_account_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    token = postmark_account_token()
    if not token:
        raise TenantEmailError("postmark_account_not_configured", "Domain verification is not available yet.", http_status=503)
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{POSTMARK_DOMAINS_API}{path}",
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Account-Token": token,
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            detail = str(payload.get("Message") or payload.get("ErrorCode") or "")[:200]
        except Exception:
            detail = ""
        raise TenantEmailError("postmark_domain_api_error", detail or f"Postmark domain API HTTP {exc.code}", http_status=502) from exc
    except Exception as exc:
        raise TenantEmailError("postmark_domain_api_error", f"Postmark domain API error: {type(exc).__name__}", http_status=502) from exc


def map_postmark_domain_status(payload: dict[str, Any]) -> str:
    dkim = bool(payload.get("DKIMVerified"))
    return_path = bool(payload.get("ReturnPathDomainVerified"))
    update = str(payload.get("DKIMUpdateStatus") or "").strip().lower()
    if dkim and return_path:
        return "verified"
    if update == "pending" or payload.get("DKIMPendingHost") or not dkim:
        return "pending_verification"
    if not dkim:
        return "failed"
    return "pending_verification"


def _domain_row_from_postmark(company: str, domain: str, payload: dict[str, Any], *, existing_status: str | None = None) -> dict[str, Any]:
    status = map_postmark_domain_status(payload)
    if existing_status == "active" and status == "verified":
        status = "active"
    return {
        "company_code": company,
        "domain": domain,
        "verification_status": status,
        "postmark_domain_id": str(payload.get("ID") or "") or None,
        "dkim_host": payload.get("DKIMPendingHost") or payload.get("DKIMHost"),
        "dkim_value": payload.get("DKIMPendingTextValue") or payload.get("DKIMTextValue"),
        "return_path_domain": payload.get("ReturnPathDomain"),
        "spf_host": payload.get("SPFHost"),
        "spf_value": payload.get("SPFTextValue"),
        "last_error": None if status in {"verified", "active", "pending_verification"} else "domain_verification_failed",
        "verified_at": _now() if status in {"verified", "active"} else None,
    }


def create_or_link_domain(legacy: Any, company_code: str, domain: str) -> dict[str, Any]:
    company = _company(company_code)
    host = _norm_domain(domain)
    if not company or not host or "." not in host:
        raise TenantEmailError("domain_required", "Enter a valid company domain.")
    existing = next((d for d in list_email_domains(legacy, company) if d.get("domain") == host), None)
    if existing and existing.get("postmark_domain_id"):
        return refresh_domain(legacy, company, str(existing["domain_id"]))
    payload = _postmark_account_request("POST", "", {"Name": host})
    mapped = _domain_row_from_postmark(company, host, payload)
    return _upsert_domain_row(legacy, mapped, domain_id=str(existing["domain_id"]) if existing else None)


def refresh_domain(legacy: Any, company_code: str, domain_id: str) -> dict[str, Any]:
    company = _company(company_code)
    domains = list_email_domains(legacy, company)
    row = next((d for d in domains if str(d.get("domain_id")) == str(domain_id)), None)
    if not row:
        raise TenantEmailError("domain_not_found", "Domain not found.", http_status=404)
    pm_id = row.get("postmark_domain_id")
    if not pm_id:
        raise TenantEmailError("domain_not_linked", "Domain is not linked for verification yet.")
    # Verify endpoints help Postmark re-check DNS
    for suffix in (f"/{pm_id}/verifyDkim", f"/{pm_id}/verifyReturnPath"):
        try:
            _postmark_account_request("PUT", suffix, {})
        except TenantEmailError:
            pass
    payload = _postmark_account_request("GET", f"/{pm_id}")
    mapped = _domain_row_from_postmark(company, str(row.get("domain")), payload, existing_status=str(row.get("verification_status")))
    return _upsert_domain_row(legacy, mapped, domain_id=str(domain_id))


def activate_domain(legacy: Any, company_code: str, domain_id: str, *, switch_mode: bool = True, updated_by_user_id: str | None = None) -> dict[str, Any]:
    company = _company(company_code)
    row = refresh_domain(legacy, company, domain_id)
    status = str(row.get("verification_status") or "")
    if status not in {"verified", "active"}:
        raise TenantEmailError("domain_not_verified", "Domain must be verified before activation.", http_status=409)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                UPDATE company_email_domains
                SET verification_status='active', activated_at=COALESCE(activated_at, now()), updated_at=now()
                WHERE company_code=%s AND domain_id=%s
                RETURNING *, domain_id::text AS domain_id
                """,
                (company, domain_id),
            )
            updated = dict(cur.fetchone())
        conn.commit()
    if switch_mode:
        settings = get_email_settings(legacy, company)
        from_addr = settings.get("from_address") or f"hr@{updated.get('domain')}"
        if _email_host(from_addr) == str(updated.get("domain") or ""):
            upsert_email_settings(
                legacy,
                company,
                {"outbound_mode": "postmark_company_domain", "from_address": from_addr},
                updated_by_user_id=updated_by_user_id,
                allow_unready_mode=False,
            )
    return updated


def _upsert_domain_row(legacy: Any, mapped: dict[str, Any], *, domain_id: str | None = None) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if domain_id:
                cur.execute(
                    """
                    UPDATE company_email_domains SET
                      verification_status=%s,
                      postmark_domain_id=%s,
                      dkim_host=%s,
                      dkim_value=%s,
                      return_path_domain=%s,
                      spf_host=%s,
                      spf_value=%s,
                      last_checked_at=now(),
                      last_error=%s,
                      verified_at=COALESCE(%s, verified_at),
                      updated_at=now()
                    WHERE company_code=%s AND domain_id=%s
                    RETURNING *, domain_id::text AS domain_id
                    """,
                    (
                        mapped["verification_status"],
                        mapped.get("postmark_domain_id"),
                        mapped.get("dkim_host"),
                        mapped.get("dkim_value"),
                        mapped.get("return_path_domain"),
                        mapped.get("spf_host"),
                        mapped.get("spf_value"),
                        mapped.get("last_error"),
                        mapped.get("verified_at"),
                        mapped["company_code"],
                        domain_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO company_email_domains (
                      domain_id, company_code, domain, verification_status, postmark_domain_id,
                      dkim_host, dkim_value, return_path_domain, spf_host, spf_value,
                      last_checked_at, last_error, verified_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,now())
                    ON CONFLICT (company_code, domain) DO UPDATE SET
                      verification_status=EXCLUDED.verification_status,
                      postmark_domain_id=EXCLUDED.postmark_domain_id,
                      dkim_host=EXCLUDED.dkim_host,
                      dkim_value=EXCLUDED.dkim_value,
                      return_path_domain=EXCLUDED.return_path_domain,
                      spf_host=EXCLUDED.spf_host,
                      spf_value=EXCLUDED.spf_value,
                      last_checked_at=now(),
                      last_error=EXCLUDED.last_error,
                      verified_at=COALESCE(EXCLUDED.verified_at, company_email_domains.verified_at),
                      updated_at=now()
                    RETURNING *, domain_id::text AS domain_id
                    """,
                    (
                        str(uuid.uuid4()),
                        mapped["company_code"],
                        mapped["domain"],
                        mapped["verification_status"],
                        mapped.get("postmark_domain_id"),
                        mapped.get("dkim_host"),
                        mapped.get("dkim_value"),
                        mapped.get("return_path_domain"),
                        mapped.get("spf_host"),
                        mapped.get("spf_value"),
                        mapped.get("last_error"),
                        mapped.get("verified_at"),
                    ),
                )
            row = dict(cur.fetchone())
        conn.commit()
    return row


def dns_records_public(domain_row: dict[str, Any]) -> list[dict[str, str]]:
    records = []
    if domain_row.get("dkim_host") and domain_row.get("dkim_value"):
        records.append({"type": "TXT", "host": str(domain_row["dkim_host"]), "value": str(domain_row["dkim_value"]), "purpose": "DKIM"})
    if domain_row.get("return_path_domain"):
        records.append(
            {
                "type": "CNAME",
                "host": str(domain_row["return_path_domain"]),
                "value": "pm.mtasv.net",
                "purpose": "Return-Path",
            }
        )
    if domain_row.get("spf_host") and domain_row.get("spf_value"):
        records.append({"type": "TXT", "host": str(domain_row["spf_host"]), "value": str(domain_row["spf_value"]), "purpose": "SPF"})
    return records


# Pure helpers for unit tests (no DB) -----------------------------------------


def resolve_outbound_sender_pure(
    *,
    settings: dict[str, Any] | None,
    global_from: str,
    global_reply: str | None = None,
    approved_mailboxes: list[dict[str, Any]] | None = None,
    verified_domain_names: list[str] | None = None,
    microsoft_configured: bool = False,
    postmark_configured: bool = True,
    for_send: bool = True,
) -> dict[str, Any]:
    settings = settings or default_settings()
    mode = str(settings.get("outbound_mode") or "wathefni")
    if mode not in OUTBOUND_MODES:
        mode = "wathefni"
    reply_to = str(settings.get("reply_to") or "").strip() or global_reply
    display_name = str(settings.get("display_name") or "").strip() or None
    emergency = bool(settings.get("allow_wathefni_emergency_fallback"))
    if mode == "wathefni":
        return {
            "mode": "wathefni",
            "selected_mode": "wathefni",
            "from_address": global_from,
            "reply_to": reply_to,
            "display_name": display_name,
            "provider": "postmark",
            "activatable": bool(postmark_configured),
            "block_reason": None if postmark_configured else "wathefni_sender_unavailable",
            "emergency_fallback_used": False,
        }
    if mode == "microsoft_mailbox":
        mailboxes = [
            m
            for m in (approved_mailboxes or [])
            if m.get("status") == "approved" and m.get("allow_send") and m.get("last_probe_ok")
        ]
        ready = bool(mailboxes and microsoft_configured)
        if not ready:
            reason = "microsoft_mailbox_not_approved" if not mailboxes else "microsoft_mail_not_configured"
            if for_send and emergency:
                return {
                    "mode": "wathefni",
                    "selected_mode": "microsoft_mailbox",
                    "from_address": global_from,
                    "reply_to": reply_to,
                    "display_name": display_name,
                    "provider": "postmark",
                    "activatable": True,
                    "block_reason": None,
                    "emergency_fallback_used": True,
                    "intended_mode": "microsoft_mailbox",
                    "hr_notice": "Your selected company sender was unavailable, so this message was sent through OctoHR as an emergency fallback.",
                }
            return {
                "mode": "microsoft_mailbox",
                "selected_mode": "microsoft_mailbox",
                "from_address": (mailboxes[0].get("address") if mailboxes else None),
                "reply_to": reply_to,
                "display_name": display_name,
                "provider": "microsoft_graph",
                "activatable": False,
                "block_reason": reason,
                "emergency_fallback_used": False,
            }
        return {
            "mode": "microsoft_mailbox",
            "selected_mode": "microsoft_mailbox",
            "from_address": _norm_email(mailboxes[0].get("address")),
            "reply_to": reply_to,
            "display_name": display_name,
            "provider": "microsoft_graph",
            "activatable": True,
            "block_reason": None,
            "emergency_fallback_used": False,
        }
    from_address = _norm_email(settings.get("from_address"))
    host = _email_host(from_address)
    ok = bool(host and host in set(verified_domain_names or []) and postmark_configured)
    if not ok:
        if for_send and emergency:
            return {
                "mode": "wathefni",
                "selected_mode": "postmark_company_domain",
                "from_address": global_from,
                "reply_to": reply_to,
                "display_name": display_name,
                "provider": "postmark",
                "activatable": True,
                "block_reason": None,
                "emergency_fallback_used": True,
                "intended_mode": "postmark_company_domain",
            }
        return {
            "mode": "postmark_company_domain",
            "selected_mode": "postmark_company_domain",
            "from_address": from_address or None,
            "reply_to": reply_to,
            "display_name": display_name,
            "provider": "postmark",
            "activatable": False,
            "block_reason": "company_domain_not_verified",
            "emergency_fallback_used": False,
        }
    return {
        "mode": "postmark_company_domain",
        "selected_mode": "postmark_company_domain",
        "from_address": from_address,
        "reply_to": reply_to,
        "display_name": display_name,
        "provider": "postmark",
        "activatable": True,
        "block_reason": None,
        "emergency_fallback_used": False,
    }


def should_skip_interview_email_pure(
    *,
    calendar_invite_sent: bool,
    candidate_email: str | None,
    interview_email_when_calendar_sent: bool,
    explicit: bool = False,
    calendar_invite_failed: bool = False,
    provider_sync_ok: bool | None = None,
) -> bool:
    if explicit:
        return False
    if calendar_invite_failed or provider_sync_ok is False:
        return False
    if not calendar_invite_sent or not _norm_email(candidate_email):
        return False
    return not bool(interview_email_when_calendar_sent)
