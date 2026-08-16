"""Canonical Assistant channel readiness — Setup → catalog → execution.

Single source of truth for whether Email / WhatsApp (and related meeting
providers) are actually configured for a company. Catalog offerability,
_visible_tools filtering, and send-time fail-closed checks all call here.

Unsupported product channels (SMS, Telegram, Teams chat) are explicitly
refused — never offered as Assistant capabilities.
"""

from __future__ import annotations

from typing import Any

# Product channels the Assistant must never claim or send through.
UNSUPPORTED_MESSAGING_CHANNELS = frozenset(
    {
        "sms",
        "telegram",
        "teams_chat",
        "teams_message",
        "microsoft_teams_chat",
    }
)

# Registry tools that require a ready outbound email path.
EMAIL_GATED_TOOLS = frozenset(
    {
        "send_email",
    }
)

# Registry tools that require company WhatsApp (candidate audience) ready.
WHATSAPP_CANDIDATE_GATED_TOOLS = frozenset(
    {
        "notify_candidate",
        "send_screening_questions",
    }
)


def _email_env_transport_configured() -> bool:
    import os

    if os.environ.get("WATHEFNI_EMAIL_PROVIDER") or os.environ.get("SMTP_HOST"):
        return True
    if os.environ.get("RESEND_API_KEY") or os.environ.get("SENDGRID_API_KEY"):
        return True
    token = (os.environ.get("WATHEFNI_POSTMARK_SERVER_TOKEN") or "").strip()
    from_addr = (os.environ.get("WATHEFNI_OUTBOUND_FROM") or "recruitment@wathefni.ai").strip()
    if token and from_addr:
        return True
    provider = (os.environ.get("WATHEFNI_OUTBOUND_EMAIL_PROVIDER") or "").strip().lower()
    return provider == "postmark" and bool(token and from_addr)


def email_ready(legacy: Any, company_code: str | None = None) -> bool:
    """True when outbound email is ready for this tenant (Settings-aligned)."""

    company = str(company_code or "").strip().upper()
    try:
        if company and legacy is not None and hasattr(legacy, "db_connect"):
            import tenant_email_authority as tea

            view = tea.public_email_sending_view(legacy, company)
            status = str(view.get("status") or "").strip().lower()
            sender = str(view.get("current_sender") or "wathefni").strip().lower()
            if status == "ready":
                return True
            if sender in {"microsoft_mailbox", "postmark_company_domain"}:
                return False
    except Exception:
        pass
    try:
        if legacy is not None and hasattr(legacy, "outbound_postmark_available"):
            if bool(legacy.outbound_postmark_available()):
                return True
    except Exception:
        pass
    try:
        return _email_env_transport_configured()
    except Exception:
        return False


def whatsapp_candidate_ready(legacy: Any, company_code: str | None) -> bool:
    """True when Setup company WhatsApp is configured for candidate audience."""

    company = str(company_code or "").strip().upper()
    if not company or legacy is None:
        return False
    try:
        if hasattr(legacy, "setup_console_channel_policy"):
            policy = legacy.setup_console_channel_policy(company) or {}
            pre = policy.get("pre_hiring") if isinstance(policy.get("pre_hiring"), dict) else {}
            wa = pre.get("company_whatsapp") if isinstance(pre.get("company_whatsapp"), dict) else {}
            return bool(wa.get("configured"))
    except Exception:
        pass
    return False


def whatsapp_employee_ready(legacy: Any, company_code: str | None) -> bool:
    company = str(company_code or "").strip().upper()
    if not company or legacy is None:
        return False
    try:
        if hasattr(legacy, "setup_console_channel_policy"):
            policy = legacy.setup_console_channel_policy(company) or {}
            post = policy.get("post_hiring") if isinstance(policy.get("post_hiring"), dict) else {}
            wa = post.get("company_whatsapp") if isinstance(post.get("company_whatsapp"), dict) else {}
            return bool(wa.get("configured"))
    except Exception:
        pass
    return False


def push_ready(legacy: Any, company_code: str | None) -> bool:
    """Employee App push effective for this company (awareness only in P0/P2)."""

    company = str(company_code or "").strip().upper()
    if not company or legacy is None:
        return False
    try:
        if hasattr(legacy, "setup_console_channel_policy"):
            policy = legacy.setup_console_channel_policy(company) or {}
            post = policy.get("post_hiring") if isinstance(policy.get("post_hiring"), dict) else {}
            push = post.get("push") if isinstance(post.get("push"), dict) else {}
            return bool(push.get("effective"))
    except Exception:
        pass
    return False


def in_app_inbox_ready(legacy: Any, company_code: str | None) -> bool:
    company = str(company_code or "").strip().upper()
    if not company or legacy is None:
        return False
    try:
        if hasattr(legacy, "setup_console_channel_policy"):
            policy = legacy.setup_console_channel_policy(company) or {}
            post = policy.get("post_hiring") if isinstance(policy.get("post_hiring"), dict) else {}
            inbox = post.get("in_app_inbox") if isinstance(post.get("in_app_inbox"), dict) else {}
            return bool(inbox.get("effective"))
    except Exception:
        pass
    return False


def channel_readiness_snapshot(legacy: Any, company_code: str | None) -> dict[str, Any]:
    """Canonical snapshot for Setup policy, catalog providers, and tests."""

    company = str(company_code or "").strip().upper()
    email = email_ready(legacy, company)
    wa_cand = whatsapp_candidate_ready(legacy, company)
    wa_emp = whatsapp_employee_ready(legacy, company)
    return {
        "company_code": company,
        "email": {"configured": email, "assistant_tools": sorted(EMAIL_GATED_TOOLS)},
        "whatsapp_candidate": {
            "configured": wa_cand,
            "assistant_tools": sorted(WHATSAPP_CANDIDATE_GATED_TOOLS),
        },
        "whatsapp_employee": {"configured": wa_emp},
        "push": {"configured": push_ready(legacy, company)},
        "in_app_inbox": {"configured": in_app_inbox_ready(legacy, company)},
        "unsupported_messaging": sorted(UNSUPPORTED_MESSAGING_CHANNELS),
        "unsupported_policy": "hard_refuse",
    }


def tool_channel_allowed(tool_name: str, legacy: Any, company_code: str | None) -> bool:
    """Whether a channel-gated tool may appear in the Assistant tool catalog."""

    name = str(tool_name or "").strip()
    if name in EMAIL_GATED_TOOLS:
        return email_ready(legacy, company_code)
    if name in WHATSAPP_CANDIDATE_GATED_TOOLS:
        return whatsapp_candidate_ready(legacy, company_code)
    return True


def refuse_unsupported_channel(channel: str | None) -> dict[str, Any] | None:
    """Return a fail-closed refusal payload if channel is unsupported; else None."""

    key = str(channel or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in UNSUPPORTED_MESSAGING_CHANNELS:
        return {
            "ok": False,
            "error": "unsupported_channel",
            "channel": key,
            "message": (
                f"{key} is not an OctoHR Assistant delivery channel. "
                "Use email or WhatsApp when configured, or complete the action in the product UI."
            ),
            "safe_user_message": (
                f"I cannot send via {key}. That channel is not supported for Assistant delivery."
            ),
        }
    return None


def unsupported_channels_prompt_block() -> str:
    return (
        "Hard refuse — never claim or send via: SMS, Telegram, or Microsoft Teams chat. "
        "teams_meet means calendar meeting links only, not Teams chat messages. "
        "Only email and WhatsApp (when AVAILABLE in capability_authority) are Assistant messaging channels."
    )
