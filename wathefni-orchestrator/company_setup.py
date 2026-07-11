"""Pure company-provisioning rules shared by Setup Console backend tests.

No database or FastAPI imports belong here. Keeping normalization and defaults
independent makes the operator workflow deterministic and easy to validate.
"""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


GCC_PROFILE_DEFAULTS: dict[str, tuple[str, str]] = {
    "KW": ("Asia/Kuwait", "KWD"),
    "SA": ("Asia/Riyadh", "SAR"),
    "AE": ("Asia/Dubai", "AED"),
    "QA": ("Asia/Qatar", "QAR"),
    "BH": ("Asia/Bahrain", "BHD"),
    "OM": ("Asia/Muscat", "OMR"),
}
DEFAULT_COUNTRY = "KW"
DEFAULT_TIMEZONE, DEFAULT_CURRENCY = GCC_PROFILE_DEFAULTS[DEFAULT_COUNTRY]

CHANNEL_ACCOUNT_PROVIDERS = frozenset({"octopus"})
CHANNEL_ACCOUNT_STATUSES = frozenset({"pending_verification", "active", "disabled"})
CHANNEL_ACCOUNT_AUDIENCES = frozenset({"candidate", "employee"})


def normalize_country(value: str | None, *, default: str = "") -> str:
    country = str(value or default).strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("country_invalid")
    return country


def default_timezone_for_country(country: str | None) -> str:
    return GCC_PROFILE_DEFAULTS.get(normalize_country(country, default=DEFAULT_COUNTRY), (DEFAULT_TIMEZONE, DEFAULT_CURRENCY))[0]


def default_currency_for_country(country: str | None) -> str:
    return GCC_PROFILE_DEFAULTS.get(normalize_country(country, default=DEFAULT_COUNTRY), (DEFAULT_TIMEZONE, DEFAULT_CURRENCY))[1]


def normalize_timezone(value: str | None, *, country: str | None = None) -> str:
    timezone = str(value or default_timezone_for_country(country)).strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone_invalid") from None
    return timezone


def normalize_currency(value: str | None, *, country: str | None = None) -> str:
    currency = str(value or default_currency_for_country(country)).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency_invalid")
    return currency


def normalize_channel_provider(value: str | None) -> str:
    provider = str(value or "").strip().lower()
    if provider not in CHANNEL_ACCOUNT_PROVIDERS:
        raise ValueError("channel_provider_invalid")
    return provider


def normalize_channel_audiences(values: list[str] | tuple[str, ...] | None) -> list[str]:
    audiences = sorted({str(value or "").strip().lower() for value in (values or []) if str(value or "").strip()})
    if not audiences or any(value not in CHANNEL_ACCOUNT_AUDIENCES for value in audiences):
        raise ValueError("channel_audiences_invalid")
    return audiences


def normalize_channel_status(value: str | None, *, verified: bool = False) -> str:
    status = str(value or "pending_verification").strip().lower()
    if status not in CHANNEL_ACCOUNT_STATUSES:
        raise ValueError("channel_status_invalid")
    if status == "active" and not verified:
        return "pending_verification"
    return status
