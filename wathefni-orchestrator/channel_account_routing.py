"""Company WhatsApp account routing helpers (Phase 7D).

Pure decision logic + thin DB loaders. Secrets never enter these helpers.
When WATHEFNI_COMPANY_CHANNEL_ACCOUNTS is OFF, always return shared default.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

Audience = Literal["candidate", "employee"]
RouteSource = Literal["shared_default", "company_owned", "fallback_shared"]

SHARED_ACCOUNT_ID = "default"
ALLOWED_AUDIENCES = frozenset({"candidate", "employee"})


def normalize_audience(value: str | None) -> str | None:
    audience = str(value or "").strip().lower()
    if not audience:
        return None
    if audience not in ALLOWED_AUDIENCES:
        raise ValueError("audience_invalid")
    return audience


def resolve_outbound_whatsapp_route(
    *,
    flag_enabled: bool,
    company_code: str | None,
    audience: str | None,
    account: dict[str, Any] | None,
    shared_account_id: str = SHARED_ACCOUNT_ID,
    known_provider_account_ids: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    """Decide which provider account id to use for an outbound WhatsApp send.

    known_provider_account_ids: optional set of account ids present in local octopus
    config. If the company account's provider_account_id is not in that set, fall
    back to shared (never invent credentials).
    """
    shared = {
        "account_id": shared_account_id or SHARED_ACCOUNT_ID,
        "source": "shared_default",
        "reason": "flag_off_or_no_company",
        "runtime_routing_changed": False,
        "company_code": (company_code or "").strip().upper() or None,
        "audience": None,
        "provider_account_id": None,
        "status": None,
    }
    if not flag_enabled:
        shared["reason"] = "flag_off"
        return shared
    company = str(company_code or "").strip().upper()
    if not company:
        shared["reason"] = "missing_company_code"
        return shared

    try:
        aud = normalize_audience(audience)
    except ValueError:
        return {
            **shared,
            "source": "fallback_shared",
            "reason": "audience_invalid",
            "company_code": company,
            "runtime_routing_changed": False,
        }
    if not aud:
        return {
            **shared,
            "source": "fallback_shared",
            "reason": "audience_required",
            "company_code": company,
            "runtime_routing_changed": False,
        }

    if not account:
        return {
            **shared,
            "source": "fallback_shared",
            "reason": "no_company_account",
            "company_code": company,
            "audience": aud,
            "runtime_routing_changed": False,
        }

    status = str(account.get("status") or "").strip().lower()
    provider_account_id = str(account.get("provider_account_id") or "").strip()
    audiences = account.get("audiences") if isinstance(account.get("audiences"), list) else []
    audiences_norm = {str(a).strip().lower() for a in audiences}

    if status != "active":
        return {
            **shared,
            "source": "fallback_shared",
            "reason": f"account_status_{status or 'unknown'}",
            "company_code": company,
            "audience": aud,
            "provider_account_id": provider_account_id or None,
            "status": status or None,
            "runtime_routing_changed": False,
        }
    if aud not in audiences_norm:
        return {
            **shared,
            "source": "fallback_shared",
            "reason": "audience_not_permitted",
            "company_code": company,
            "audience": aud,
            "provider_account_id": provider_account_id or None,
            "status": status,
            "runtime_routing_changed": False,
        }
    if not provider_account_id:
        return {
            **shared,
            "source": "fallback_shared",
            "reason": "missing_provider_account_id",
            "company_code": company,
            "audience": aud,
            "status": status,
            "runtime_routing_changed": False,
        }
    if known_provider_account_ids is not None and provider_account_id not in known_provider_account_ids:
        return {
            **shared,
            "source": "fallback_shared",
            "reason": "provider_account_not_in_sender_config",
            "company_code": company,
            "audience": aud,
            "provider_account_id": provider_account_id,
            "status": status,
            "runtime_routing_changed": False,
        }

    return {
        "account_id": provider_account_id,
        "source": "company_owned",
        "reason": "active_audience_ok",
        "runtime_routing_changed": True,
        "company_code": company,
        "audience": aud,
        "provider_account_id": provider_account_id,
        "status": status,
    }


def resolve_inbound_company_from_account(
    *,
    flag_enabled: bool,
    provider: str | None,
    provider_account_id: str | None,
    lookup: Callable[[str, str], dict[str, Any] | None],
) -> dict[str, Any]:
    """Map inbound provider account → company when flag ON.

    lookup(provider, provider_account_id) → row with company_code/status or None.
    When flag OFF or unknown account, returns no company (caller uses phone fallback).
    """
    if not flag_enabled:
        return {
            "company_code": None,
            "source": "shared_default",
            "reason": "flag_off",
            "runtime_routing_changed": False,
        }
    provider_norm = str(provider or "").strip().lower()
    account_id = str(provider_account_id or "").strip()
    if not provider_norm or not account_id:
        return {
            "company_code": None,
            "source": "shared_default",
            "reason": "missing_provider_account",
            "runtime_routing_changed": False,
        }
    row = lookup(provider_norm, account_id)
    if not row:
        return {
            "company_code": None,
            "source": "shared_default",
            "reason": "account_not_registered",
            "runtime_routing_changed": False,
        }
    status = str(row.get("status") or "").strip().lower()
    company = str(row.get("company_code") or "").strip().upper()
    if status != "active" or not company:
        return {
            "company_code": None,
            "source": "fallback_shared",
            "reason": f"inbound_account_status_{status or 'unknown'}",
            "runtime_routing_changed": False,
            "provider_account_id": account_id,
        }
    return {
        "company_code": company,
        "source": "company_owned",
        "reason": "inbound_account_mapped",
        "runtime_routing_changed": True,
        "provider_account_id": account_id,
        "status": status,
    }
