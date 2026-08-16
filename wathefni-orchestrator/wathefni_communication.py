"""Canonical Wathefni communication authority.

Calendar and other modules emit intents; this module decides lifecycle policy,
qualified channels, fallback order, and sender adapters. Calendar must not
select provider credentials or call Octopus/email directly.

Readiness truth (audit-locked):
  whatsapp session  — production_ready
  email             — production_ready (Postmark/Gmail)
  wathefni_push     — dark (Expo flag)
  whatsapp_hsm      — dark
  wathefni_in_app   — planned (no production-qualified inbox sender yet)
  microsoft_teams / telegram / sms — absent
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

READINESS_PRODUCTION = "production_ready"
READINESS_DARK = "dark"
READINESS_PLANNED = "planned"
READINESS_ABSENT = "absent"
READINESS_LEGACY = "legacy"

CHANNEL_REGISTRY: dict[str, dict[str, Any]] = {
    "wathefni_in_app": {
        "readiness": READINESS_PLANNED,
        "label": "OctoHR in-app inbox",
        "lifecycles": ("post_hire", "hr_ops"),
        "notes": "Intended foundation for employees/HR; not production-qualified as a sender yet.",
    },
    "wathefni_push": {
        "readiness": READINESS_DARK,
        "label": "OctoHR push (Expo)",
        "lifecycles": ("post_hire", "hr_ops"),
        "gate_env": "WATHEFNI_PUSH_NOTIFICATIONS",
        "notes": "Implemented behind flag; default OFF.",
    },
    "whatsapp": {
        "readiness": READINESS_PRODUCTION,
        "label": "WhatsApp session (Octopus)",
        "lifecycles": ("pre_hire", "post_hire", "hr_ops", "external_guest"),
        "notes": "Production-ready on shared account; company accounts dark by default.",
    },
    "email": {
        "readiness": READINESS_PRODUCTION,
        "label": "Email (Postmark/Gmail)",
        "lifecycles": ("pre_hire", "post_hire", "hr_ops", "external_guest"),
        "notes": "Production-ready platform senders.",
    },
    "whatsapp_hsm": {
        "readiness": READINESS_DARK,
        "label": "WhatsApp HSM template",
        "lifecycles": ("pre_hire", "post_hire", "hr_ops", "external_guest"),
        "gate_env": "WATHEFNI_OUTBOUND_TEMPLATES",
        "notes": "Dark / incomplete.",
    },
    "microsoft_teams": {
        "readiness": READINESS_ABSENT,
        "label": "Microsoft Teams",
        "lifecycles": ("post_hire", "hr_ops"),
        "notes": "Registry placeholder only.",
    },
    "telegram": {
        "readiness": READINESS_ABSENT,
        "label": "Telegram",
        "lifecycles": ("post_hire", "hr_ops", "pre_hire", "external_guest"),
        "notes": "Registry placeholder only.",
    },
    "sms": {
        "readiness": READINESS_ABSENT,
        "label": "SMS",
        "lifecycles": ("pre_hire", "post_hire", "hr_ops", "external_guest"),
        "notes": "Vocabulary only; no sender.",
    },
}

LIFECYCLES = frozenset({"pre_hire", "post_hire", "hr_ops", "external_guest"})
RECIPIENT_TYPES = frozenset({"candidate", "external_guest", "employee", "hr", "unknown"})

CANONICAL_PURPOSES = frozenset(
    {
        "calendar_invitation",
        "calendar_event_changed",
        "calendar_event_cancelled",
        "calendar_reminder",
        "calendar_rsvp_required",
        "calendar_rsvp_received",
        "calendar_reschedule_requested",
        "calendar_reschedule_resolved",
    }
)

LEGACY_PURPOSE_MAP: dict[str, str] = {
    "guest_invite": "calendar_invitation",
    "attendee_invite": "calendar_invitation",
    "guest_reminder": "calendar_reminder",
    "attendee_reminder": "calendar_reminder",
    "guest_cancel": "calendar_event_cancelled",
    "attendee_cancel": "calendar_event_cancelled",
    "guest_update": "calendar_event_changed",
    "attendee_update": "calendar_event_changed",
    "rsvp_notice": "calendar_rsvp_received",
    "reschedule_notice": "calendar_reschedule_requested",
}

# Defaults are company-overridable. They are NOT a global WhatsApp-first assumption
# and do not encode role stereotypes. Unqualified preferred channels are skipped.
_DEFAULT_ALLOWED_CALENDAR = sorted(CANONICAL_PURPOSES)

DEFAULT_COMMUNICATION_POLICY: dict[str, Any] = {
    "pre_hire": {
        "preferred_channels": ["email"],
        "fallback_channels": ["whatsapp"],
        "enabled_channels": ["email", "whatsapp"],
        "allowed_purposes": _DEFAULT_ALLOWED_CALENDAR,
        "require_consent": False,
        "connected_account": None,
        "quiet_hours": {},
    },
    "external_guest": {
        "preferred_channels": ["email"],
        "fallback_channels": ["whatsapp"],
        "enabled_channels": ["email", "whatsapp"],
        "allowed_purposes": _DEFAULT_ALLOWED_CALENDAR,
        "require_consent": False,
        "connected_account": None,
        "quiet_hours": {},
    },
    "post_hire": {
        # Foundation first; live extras empty until the company enables them.
        "preferred_channels": ["wathefni_in_app", "wathefni_push"],
        "fallback_channels": [],
        "enabled_channels": ["wathefni_in_app", "wathefni_push"],
        "allowed_purposes": _DEFAULT_ALLOWED_CALENDAR,
        "require_consent": False,
        "connected_account": None,
        "quiet_hours": {},
    },
    "hr_ops": {
        "preferred_channels": ["wathefni_in_app", "wathefni_push"],
        "fallback_channels": [],
        "enabled_channels": ["wathefni_in_app", "wathefni_push"],
        "allowed_purposes": _DEFAULT_ALLOWED_CALENDAR,
        "require_consent": False,
        "connected_account": None,
        "quiet_hours": {},
    },
    "purpose_overrides": {},
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _env_on(name: str) -> bool:
    return _text(os.environ.get(name)).lower() in {"1", "true", "on", "yes", "enabled", "all"}


def channel_readiness(channel: str) -> str:
    meta = CHANNEL_REGISTRY.get(_text(channel).lower())
    if not meta:
        return READINESS_ABSENT
    readiness = str(meta.get("readiness") or READINESS_ABSENT)
    gate = meta.get("gate_env")
    if readiness == READINESS_DARK and gate and not _env_on(str(gate)):
        return READINESS_DARK
    if readiness == READINESS_DARK and gate and _env_on(str(gate)):
        # Still dark/incomplete for HSM; push becomes selectable only when gate on.
        if channel == "wathefni_push":
            return READINESS_PRODUCTION  # gated live when flag on
        return READINESS_DARK
    return readiness


def channel_is_selectable(channel: str) -> bool:
    """Only production_ready (or gated-live push) channels may be selected."""
    readiness = channel_readiness(channel)
    if readiness == READINESS_PRODUCTION:
        return True
    # Push: treat gate-on as selectable production path for routing purposes.
    if channel == "wathefni_push" and _env_on("WATHEFNI_PUSH_NOTIFICATIONS"):
        return True
    return False


def normalize_purpose(purpose: str | None) -> str:
    raw = _text(purpose)
    if raw in CANONICAL_PURPOSES:
        return raw
    return LEGACY_PURPOSE_MAP.get(raw, raw or "calendar_invitation")


def classify_lifecycle(
    *,
    recipient_type: str | None = None,
    lifecycle: str | None = None,
    guest_kind: str | None = None,
    app_key: str | None = None,
    person_key: str | None = None,
) -> str:
    """Classify by recipient identity/lifecycle — never by event type alone."""
    if _text(lifecycle).lower() in LIFECYCLES:
        return _text(lifecycle).lower()
    rtype = _text(recipient_type).lower()
    if rtype == "hr":
        return "hr_ops"
    if rtype == "employee":
        return "post_hire"
    if rtype == "candidate" or _text(guest_kind).lower() == "candidate" or _text(app_key) or _text(person_key):
        return "pre_hire"
    if rtype == "external_guest" or _text(guest_kind).lower() in {"external", "other"}:
        return "external_guest"
    if rtype == "candidate":
        return "pre_hire"
    return "external_guest"


def deep_merge_policy(base: Mapping[str, Any], overlay: Mapping[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    if not overlay:
        return out
    for key, value in overlay.items():
        if key in LIFECYCLES and isinstance(value, dict):
            merged = dict(out.get(key) or {})
            merged.update({k: v for k, v in value.items() if v is not None})
            out[key] = merged
        elif key == "purpose_overrides" and isinstance(value, dict):
            po = dict(out.get("purpose_overrides") or {})
            for pk, pv in value.items():
                if isinstance(pv, dict):
                    po[pk] = {**(po.get(pk) or {}), **pv}
            out["purpose_overrides"] = po
        else:
            out[key] = value
    return out


def load_company_communication_policy(legacy: Any, company_code: str) -> dict[str, Any]:
    company = _text(company_code).upper()
    raw: dict[str, Any] = {}
    try:
        if hasattr(legacy, "get_company_settings"):
            settings = legacy.get_company_settings(company) or {}
            blob = settings.get("communication_policy")
            if isinstance(blob, dict):
                raw = blob
    except Exception:
        raw = {}
    return deep_merge_policy(DEFAULT_COMMUNICATION_POLICY, raw)


def policy_for_lifecycle(policy: Mapping[str, Any], lifecycle: str, purpose: str) -> dict[str, Any]:
    life = _text(lifecycle).lower() if _text(lifecycle).lower() in LIFECYCLES else "external_guest"
    base = dict(policy.get(life) or DEFAULT_COMMUNICATION_POLICY.get(life) or {})
    overrides = policy.get("purpose_overrides") if isinstance(policy.get("purpose_overrides"), dict) else {}
    purpose_over = overrides.get(purpose) if isinstance(overrides.get(purpose), dict) else None
    if purpose_over:
        base = {**base, **purpose_over}
    return base


def build_channel_ladder(
    *,
    policy_slice: Mapping[str, Any],
    preferred_hint: str | None = None,
) -> list[str]:
    """Ordered unique channels: optional recipient hint (if allowed), then preferred, then fallback.

    Never sends all channels. Unqualified / disabled channels are omitted.
    """
    enabled = {
        _text(c).lower()
        for c in (policy_slice.get("enabled_channels") or [])
        if _text(c)
    }
    preferred = [_text(c).lower() for c in (policy_slice.get("preferred_channels") or []) if _text(c)]
    fallback = [_text(c).lower() for c in (policy_slice.get("fallback_channels") or []) if _text(c)]
    ordered: list[str] = []
    hint = _text(preferred_hint).lower()
    # Map legacy Calendar labels onto registry keys.
    if hint == "in_app":
        hint = "wathefni_in_app"
    if hint and hint in enabled:
        ordered.append(hint)
    for ch in preferred + fallback:
        if ch and ch not in ordered:
            ordered.append(ch)
    selectable: list[str] = []
    for ch in ordered:
        if enabled and ch not in enabled:
            continue
        if not channel_is_selectable(ch):
            continue
        selectable.append(ch)
    return selectable


def quiet_hours_block(policy_slice: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    """Return True when quiet hours should defer send. Empty config = no block."""
    qh = policy_slice.get("quiet_hours") if isinstance(policy_slice.get("quiet_hours"), dict) else {}
    if not qh:
        return False
    start = _text(qh.get("start"))
    end = _text(qh.get("end"))
    if not start or not end:
        return False
    try:
        sh, sm = [int(x) for x in start.split(":")[:2]]
        eh, em = [int(x) for x in end.split(":")[:2]]
    except Exception:
        return False
    current = now or datetime.now(timezone.utc)
    # Company-local TZ enforcement is future work; compare UTC clock minutes for structure only.
    mins = current.hour * 60 + current.minute
    s = sh * 60 + sm
    e = eh * 60 + em
    if s == e:
        return False
    if s < e:
        return s <= mins < e
    return mins >= s or mins < e


def resolve_route(
    legacy: Any,
    *,
    company_code: str,
    purpose: str,
    recipient_type: str | None = None,
    lifecycle: str | None = None,
    guest_kind: str | None = None,
    app_key: str | None = None,
    person_key: str | None = None,
    preferred_channel_hint: str | None = None,
) -> dict[str, Any]:
    canon_purpose = normalize_purpose(purpose)
    life = classify_lifecycle(
        recipient_type=recipient_type,
        lifecycle=lifecycle,
        guest_kind=guest_kind,
        app_key=app_key,
        person_key=person_key,
    )
    policy = load_company_communication_policy(legacy, company_code)
    slice_ = policy_for_lifecycle(policy, life, canon_purpose)
    allowed = {_text(p) for p in (slice_.get("allowed_purposes") or []) if _text(p)}
    if allowed and canon_purpose not in allowed:
        return {
            "ok": False,
            "error": "purpose_not_allowed",
            "lifecycle": life,
            "purpose": canon_purpose,
            "channels": [],
            "policy_slice": slice_,
        }
    channels = build_channel_ladder(policy_slice=slice_, preferred_hint=preferred_channel_hint)
    return {
        "ok": True,
        "lifecycle": life,
        "purpose": canon_purpose,
        "channels": channels,
        "policy_slice": slice_,
        "quiet_hours_block": quiet_hours_block(slice_),
        "require_consent": bool(slice_.get("require_consent")),
        "connected_account": slice_.get("connected_account"),
    }


def _contact_for_channel(channel: str, recipient: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "phone": _text(recipient.get("phone")),
        "email": _text(recipient.get("email")),
        "user_id": _text(recipient.get("user_id")),
        "display_name": _text(recipient.get("display_name")),
    }


def _subject_body(intent: Mapping[str, Any]) -> tuple[str, str]:
    payload = intent.get("payload") if isinstance(intent.get("payload"), dict) else {}
    title = _text(payload.get("title") or intent.get("title") or "OctoHR")
    message = _text(payload.get("message"))
    link = _text(payload.get("link") or payload.get("invite_path"))
    purpose = normalize_purpose(_text(intent.get("purpose")))
    if not message:
        if purpose == "calendar_event_cancelled":
            message = f"Cancelled: “{title}”."
        elif purpose == "calendar_event_changed":
            message = f"Updated: “{title}”."
        elif purpose == "calendar_reminder":
            message = f"Reminder: “{title}” starts soon."
        elif purpose == "calendar_rsvp_received":
            message = f"RSVP update for “{title}”."
        elif purpose == "calendar_reschedule_requested":
            message = f"Reschedule requested for “{title}”."
        elif purpose == "calendar_reschedule_resolved":
            message = f"Reschedule request updated for “{title}”."
        else:
            message = f"You are invited: {title}."
            if link:
                message = f"{message} Respond: {link}"
    subject_map = {
        "calendar_invitation": f"Invitation: {title}",
        "calendar_event_cancelled": f"Cancelled: {title}",
        "calendar_event_changed": f"Updated: {title}",
        "calendar_reminder": f"Reminder: {title}",
        "calendar_rsvp_received": f"RSVP: {title}",
        "calendar_reschedule_requested": f"Reschedule request: {title}",
        "calendar_reschedule_resolved": f"Reschedule update: {title}",
    }
    subject = _text(payload.get("subject")) or subject_map.get(purpose, f"OctoHR: {title}")
    return subject, message


def _force_calendar_dry_run() -> bool:
    return _text(os.environ.get("CALENDAR_DELIVERY_DRY_RUN")).lower() in {"1", "true", "yes", "on"}


def _adapter_whatsapp(legacy: Any, *, intent: Mapping[str, Any], contact: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    phone = _text(contact.get("phone"))
    if not phone:
        return {"ok": False, "channel": "whatsapp", "error": "missing_phone"}
    _, body = _subject_body(intent)
    if _force_calendar_dry_run() and not (
        hasattr(legacy, "delivery_is_dry_run") and legacy.delivery_is_dry_run()
    ):
        # Calendar-only dry-run: still record via shared sender when available under dry mode,
        # otherwise simulate without inventing credentials.
        if hasattr(legacy, "delivery_is_dry_run") and hasattr(legacy, "send_octopus_whatsapp"):
            # Prefer shared dry-run path by temporarily not forcing live.
            pass
    company = _text(intent.get("company_code")).upper()
    lifecycle = _text(route.get("lifecycle"))
    audience = "candidate" if lifecycle in {"pre_hire", "external_guest"} else "employee"
    account = route.get("connected_account") or "default"
    if _force_calendar_dry_run():
        # Do not call live Octopus when Calendar dry-run is set; shared dry-run is preferred.
        if hasattr(legacy, "delivery_is_dry_run") and legacy.delivery_is_dry_run() and hasattr(legacy, "send_octopus_whatsapp"):
            result = legacy.send_octopus_whatsapp(
                account_id=_text(account) or "default",
                phone=phone,
                text=body,
                subject_type=_text(intent.get("subject_type")) or "calendar",
                subject_key=_text(intent.get("event_id") or intent.get("subject_key")),
                company_code=company,
                audience=audience,
            )
            return {
                "ok": bool(result.get("ok")),
                "channel": "whatsapp",
                "provider_ref": _text(result.get("external_message_id") or result.get("message_id") or result.get("outbound_event_id")) or None,
                "dry_run": bool(result.get("dry_run")),
                "error": None if result.get("ok") else _text(result.get("error")) or "whatsapp_failed",
                "raw": result,
            }
        return {
            "ok": True,
            "channel": "whatsapp",
            "provider_ref": f"dry_run:whatsapp:{_text(intent.get('idempotency_key'))}",
            "dry_run": True,
        }
    if not hasattr(legacy, "send_octopus_whatsapp"):
        return {"ok": False, "channel": "whatsapp", "error": "whatsapp_unavailable"}
    result = legacy.send_octopus_whatsapp(
        account_id=_text(account) or "default",
        phone=phone,
        text=body,
        subject_type=_text(intent.get("subject_type")) or "calendar",
        subject_key=_text(intent.get("event_id") or intent.get("subject_key")),
        company_code=company,
        audience=audience,
    )
    return {
        "ok": bool(result.get("ok")),
        "channel": "whatsapp",
        "provider_ref": _text(
            result.get("external_message_id") or result.get("provider_message_id") or result.get("message_id") or result.get("outbound_event_id")
        )
        or None,
        "dry_run": bool(result.get("dry_run")),
        "error": None if result.get("ok") else _text(result.get("error")) or "whatsapp_failed",
        "raw": result,
        "account_id": result.get("account_id") or account,
        "company_code": company,
    }


def _adapter_email(legacy: Any, *, intent: Mapping[str, Any], contact: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    email = _text(contact.get("email"))
    if not email:
        return {"ok": False, "channel": "email", "error": "missing_email"}
    subject, body = _subject_body(intent)
    company = _text(intent.get("company_code")).upper()
    if _force_calendar_dry_run() and not (hasattr(legacy, "delivery_is_dry_run") and legacy.delivery_is_dry_run()):
        if hasattr(legacy, "send_outbound_email"):
            # Still prefer shared sender under global dry-run; else synthetic dry-run.
            pass
        return {
            "ok": True,
            "channel": "email",
            "provider_ref": f"dry_run:email:{_text(intent.get('idempotency_key'))}",
            "dry_run": True,
        }
    if not hasattr(legacy, "send_outbound_email"):
        return {"ok": False, "channel": "email", "error": "email_unavailable"}
    result = legacy.send_outbound_email(
        to=email,
        subject=subject,
        body=body,
        company_code=company,
        subject_type=_text(intent.get("subject_type")) or "calendar",
        subject_key=_text(intent.get("event_id") or intent.get("subject_key")),
        account_id=_text(route.get("connected_account")) or None,
        message_kind=normalize_purpose(intent.get("purpose")),
    )
    return {
        "ok": bool(result.get("ok")),
        "channel": "email",
        "provider_ref": _text(result.get("message_id") or result.get("provider")) or None,
        "dry_run": bool(result.get("dry_run")),
        "error": None if result.get("ok") else _text(result.get("error")) or "email_failed",
        "raw": result,
        "company_code": company,
    }


def _adapter_push(legacy: Any, *, intent: Mapping[str, Any], contact: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    if not channel_is_selectable("wathefni_push"):
        return {"ok": False, "channel": "wathefni_push", "error": "channel_not_qualified"}
    if not hasattr(legacy, "send_outbound_push"):
        return {"ok": False, "channel": "wathefni_push", "error": "push_unavailable"}
    subject, body = _subject_body(intent)
    employee_key = _text(contact.get("user_id") or intent.get("recipient_ref"))
    result = legacy.send_outbound_push(
        company_code=_text(intent.get("company_code")).upper(),
        employee_key=employee_key,
        title=subject,
        body=body,
        flow="calendar",
        subject_type=_text(intent.get("subject_type")) or "calendar",
        subject_key=_text(intent.get("event_id") or intent.get("subject_key")),
        account_id=_text(route.get("connected_account")) or "default",
    )
    return {
        "ok": bool(result.get("ok")),
        "channel": "wathefni_push",
        "provider_ref": _text(result.get("provider")) or None,
        "error": None if result.get("ok") else _text(result.get("error")) or "push_failed",
        "raw": result,
    }


ADAPTERS = {
    "whatsapp": _adapter_whatsapp,
    "email": _adapter_email,
    "wathefni_push": _adapter_push,
}


def resolve_recipient_contact(legacy: Any, *, company_code: str, recipient: Mapping[str, Any]) -> dict[str, Any]:
    """Enrich recipient with phone/email from identity refs without crossing tenants."""
    out = dict(recipient or {})
    company = _text(company_code).upper()
    user_id = _text(out.get("user_id"))
    if user_id and (not _text(out.get("phone")) or not _text(out.get("email"))):
        try:
            if hasattr(legacy, "hr_admin_users"):
                for user in legacy.hr_admin_users(company) or []:
                    if _text(user.get("user_id")) == user_id:
                        out.setdefault("phone", user.get("phone"))
                        out.setdefault("email", user.get("email"))
                        out.setdefault("display_name", user.get("name"))
                        break
        except Exception:
            pass
        try:
            # Wave personal resolver may know assignee phones for the company.
            import prehire_personal_work as _ppw

            targets, _aud = _ppw.resolve_notify_targets(
                company=company,
                db_connect=legacy.db_connect,
                assignee_user_ids=[user_id],
                assignee_phones=None,
                fallback_company_broadcast=False,
                company_users_loader=getattr(legacy, "hr_admin_users", lambda _c: []),
            )
            for t in targets or []:
                if _text(t.get("user_id")) == user_id or _text(t.get("phone")):
                    out.setdefault("phone", t.get("phone"))
                    out.setdefault("email", t.get("email"))
                    out.setdefault("display_name", t.get("name"))
                    break
        except Exception:
            pass
    return out


def deliver_intent(legacy: Any, intent: Mapping[str, Any]) -> dict[str, Any]:
    """Route and deliver one communication intent. Stops after first confirmed success.

    Never selects unqualified channels. Never invents cross-tenant accounts —
    company_code is always threaded into adapters.
    """
    company = _text(intent.get("company_code")).upper()
    if not company:
        return {"ok": False, "error": "missing_company_code", "attempts": []}

    recipient = resolve_recipient_contact(
        legacy,
        company_code=company,
        recipient=intent.get("recipient") if isinstance(intent.get("recipient"), dict) else {},
    )
    # Re-bind enriched recipient for adapters.
    intent = {**dict(intent), "recipient": recipient}
    route = resolve_route(
        legacy,
        company_code=company,
        purpose=_text(intent.get("purpose")),
        recipient_type=_text(intent.get("recipient_type")),
        lifecycle=_text(intent.get("lifecycle")) or None,
        guest_kind=_text(recipient.get("guest_kind")) or None,
        app_key=_text(recipient.get("app_key")) or None,
        person_key=_text(recipient.get("person_key")) or None,
        preferred_channel_hint=_text(intent.get("preferred_channel_hint") or recipient.get("preferred_channel")),
    )
    if not route.get("ok"):
        return {**route, "attempts": []}

    if route.get("require_consent") and not intent.get("consent_ok"):
        return {
            "ok": False,
            "error": "consent_required",
            "lifecycle": route.get("lifecycle"),
            "purpose": route.get("purpose"),
            "attempts": [],
        }

    if route.get("quiet_hours_block") and not intent.get("bypass_quiet_hours"):
        return {
            "ok": False,
            "error": "quiet_hours",
            "retryable": True,
            "lifecycle": route.get("lifecycle"),
            "purpose": route.get("purpose"),
            "channels": route.get("channels"),
            "attempts": [],
        }

    channels: Sequence[str] = list(route.get("channels") or [])
    if not channels:
        return {
            "ok": False,
            "error": "no_qualified_channel",
            "lifecycle": route.get("lifecycle"),
            "purpose": route.get("purpose"),
            "policy_slice": route.get("policy_slice"),
            "attempts": [],
        }

    attempts: list[dict[str, Any]] = []
    for channel in channels:
        if not channel_is_selectable(channel):
            attempts.append({"channel": channel, "ok": False, "error": "channel_not_qualified", "skipped": True})
            continue
        adapter = ADAPTERS.get(channel)
        if not adapter:
            attempts.append({"channel": channel, "ok": False, "error": "adapter_missing", "skipped": True})
            continue
        contact = _contact_for_channel(channel, recipient)
        try:
            result = adapter(legacy, intent=intent, contact=contact, route=route)
        except Exception as exc:
            result = {"ok": False, "channel": channel, "error": str(exc)[:300]}
        attempts.append({k: v for k, v in result.items() if k != "raw"})
        if result.get("ok"):
            return {
                "ok": True,
                "channel_used": channel,
                "provider_ref": result.get("provider_ref"),
                "dry_run": bool(result.get("dry_run")),
                "lifecycle": route.get("lifecycle"),
                "purpose": route.get("purpose"),
                "attempts": attempts,
                "fallback_used": len(attempts) > 1,
                "company_code": company,
            }

    return {
        "ok": False,
        "error": "all_channels_failed",
        "lifecycle": route.get("lifecycle"),
        "purpose": route.get("purpose"),
        "attempts": attempts,
        "company_code": company,
    }


def channel_readiness_matrix() -> list[dict[str, Any]]:
    rows = []
    for key, meta in CHANNEL_REGISTRY.items():
        rows.append(
            {
                "channel": key,
                "readiness": channel_readiness(key),
                "registry_readiness": meta.get("readiness"),
                "selectable": channel_is_selectable(key),
                "label": meta.get("label"),
                "notes": meta.get("notes"),
            }
        )
    return rows
