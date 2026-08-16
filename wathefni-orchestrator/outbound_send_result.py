"""Shared outbound send-result contract (Wave 2).

One backend-authoritative result envelope for every outbound candidate
communication (assessments, interview invitations, reminders, email, WhatsApp,
offers, document requests). Request accepted is not delivered.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


OUTBOUND_STATES = {"sent", "queued", "partially_sent", "failed"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _channel_label(channel: str) -> str:
    normalized = _lower(channel)
    if normalized == "whatsapp":
        return "WhatsApp"
    if normalized == "email":
        return "Email"
    return channel.replace("_", " ").title() or "Message"


def _human_error(error: Any) -> str | None:
    text = _lower(error)
    if not text:
        return None
    if "invalid_grant" in text or "token has been expired or revoked" in text or "gmail_auth" in text:
        return "Email needs reconnecting."
    if "no_usable_conversation" in text or "conversation_closed" in text or "conversation_inactive" in text:
        return "WhatsApp conversation is not active."
    if "missing_candidate_email" in text:
        return "Candidate has no email address."
    if "missing_candidate_phone" in text or "missing_candidate_contact" in text:
        return "Candidate has no phone number."
    if "rate" in text and "limit" in text:
        return "The provider is rate limiting sends. Try again shortly."
    return "Delivery did not complete on this channel."


def build_send_result(
    *,
    kind: str,
    recipient: dict[str, Any] | None,
    delivery: dict[str, Any] | None,
    attempts: list[dict[str, Any]] | None = None,
    ok: bool | None = None,
    next_action: str | None = None,
    locale: str = "en",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical outbound send-result envelope.

    States: sent / queued / partially_sent / failed.
    Never exposes raw provider codes; per-channel results are separated.
    """
    recipient = recipient if isinstance(recipient, dict) else {}
    delivery = delivery if isinstance(delivery, dict) else {}
    raw_attempts = attempts if isinstance(attempts, list) else list(delivery.get("attempts") or [])

    channels: list[dict[str, Any]] = []
    for attempt in raw_attempts:
        if not isinstance(attempt, dict):
            continue
        channel = _lower(attempt.get("channel") or attempt.get("channel_key"))
        if not channel:
            continue
        success = bool(attempt.get("ok"))
        status = _lower(attempt.get("status"))
        provider = attempt.get("provider") or (attempt.get("result") or {}).get("provider") if isinstance(attempt.get("result"), dict) else attempt.get("provider")
        message_id = attempt.get("external_message_id") or attempt.get("message_id") or (attempt.get("result") or {}).get("message_id") if isinstance(attempt.get("result"), dict) else None
        channels.append(
            {
                "channel": channel,
                "label": _channel_label(channel),
                "state": "sent" if success else ("queued" if status in {"queued", "pending"} else "failed"),
                "ok": success,
                "provider": provider or ("gmail" if channel == "email" else "whatsapp"),
                "message_id": message_id,
                "sent_at": attempt.get("sent_at") or attempt.get("created_at"),
                "error": None if success else _human_error(attempt.get("error") or attempt.get("last_error") or attempt.get("stderr") or attempt.get("result")),
            }
        )

    if not channels and delivery:
        # Fallback single-channel view from last_successful_channel
        single = _lower(delivery.get("last_successful_channel") or delivery.get("channel"))
        if single:
            channels.append(
                {
                    "channel": single,
                    "label": _channel_label(single),
                    "state": "sent" if delivery.get("ok") else "failed",
                    "ok": bool(delivery.get("ok")),
                    "provider": "gmail" if single == "email" else "whatsapp",
                    "message_id": delivery.get("external_message_id"),
                    "sent_at": delivery.get("sent_at"),
                    "error": None if delivery.get("ok") else _human_error(delivery.get("error") or delivery.get("last_error")),
                }
            )

    sent_channels = [c for c in channels if c["state"] == "sent" and c["ok"]]
    queued_channels = [c for c in channels if c["state"] == "queued"]
    failed_channels = [c for c in channels if c["state"] == "failed"]

    if ok is False or (channels and failed_channels and not sent_channels and not queued_channels):
        state = "failed"
    elif sent_channels and failed_channels:
        state = "partially_sent"
    elif sent_channels and not failed_channels and ok is not False:
        state = "sent"
    elif sent_channels:
        state = "partially_sent"
    elif queued_channels or not channels:
        state = "queued"
    else:
        state = "failed"

    recipient_name = recipient.get("name") or recipient.get("candidate_name")
    recipient_email = recipient.get("email") or recipient.get("candidate_email")
    recipient_phone = recipient.get("phone") or recipient.get("candidate_phone")

    error_text = next((c["error"] for c in failed_channels if c.get("error")), None)
    if state == "sent":
        message = "Invitation sent."
        if locale == "ar":
            message = "تم إرسال الدعوة."
    elif state == "partially_sent":
        message = "Invitation partially sent — one channel succeeded, another failed."
        if locale == "ar":
            message = "تم إرسال الدعوة جزئيًا — نجحت قناة وفشلت أخرى."
    elif state == "queued":
        message = "Invitation queued for sending."
        if locale == "ar":
            message = "تمت جدولة الدعوة للإرسال."
    else:
        message = "The invitation could not be sent."
        if locale == "ar":
            message = "تعذر إرسال الدعوة."

    suggested = next_action
    if not suggested:
        if state == "failed":
            suggested = "Review the candidate contact details and retry."
        elif state == "partially_sent":
            suggested = "Retry the failed channel if the candidate did not receive it."
        else:
            suggested = None

    return {
        "version": "outbound_send_result_v1",
        "kind": kind,
        "state": state,
        "ok": state in {"sent", "partially_sent", "queued"},
        "message": message,
        "human_error": error_text,
        "suggested_next_action": suggested,
        "recipient": {
            "name": recipient_name,
            "email": recipient_email,
            "phone": recipient_phone,
        },
        "channels": channels,
        "channels_attempted": [c["channel"] for c in channels],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "extra": extra or {},
    }
