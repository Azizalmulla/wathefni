"""Authority gate for Kuwait/GCC shared contracts/compliance processing.

Mirrors identity Mistral authority contract. Identity types still delegate to
identity_document_extraction; this gate only controls structuring activation
and shared-channel wiring for contract/education (and omnichannel intake).
"""

from __future__ import annotations

import os
from typing import Any


def kuwait_gcc_authority_mode(*, environ: dict[str, str] | None = None) -> str:
    env = environ if environ is not None else os.environ
    mode = str(env.get("WATHEFNI_KUWAIT_GCC_MISTRAL_AUTHORITY") or "on").strip().lower()
    if mode in {"", "default"}:
        return "on"
    return mode


def kuwait_gcc_authority_enabled(
    *,
    company_code: str | None = None,
    environ: dict[str, str] | None = None,
) -> bool:
    """Global Kuwait/GCC shared processor authority.

    Default: ON for all tenants (current and future).
    Kill switch: WATHEFNI_KUWAIT_GCC_MISTRAL_AUTHORITY=off|kill|disabled
    Optional per-tenant disable: WATHEFNI_KUWAIT_GCC_MISTRAL_DISABLE_COMPANIES=A,B
    Legacy canary allowlist only when AUTHORITY=canary.
    Never enables GPT.
    """

    env = environ if environ is not None else os.environ
    mode = kuwait_gcc_authority_mode(environ=env)
    if mode in {"off", "0", "false", "no", "kill", "disabled", "emergency_stop"}:
        return False
    if mode not in {"1", "true", "on", "yes", "staging", "canary", "production", "authority", "global"}:
        mode = "on"

    company = str(company_code or "").strip().upper()
    disable_raw = str(env.get("WATHEFNI_KUWAIT_GCC_MISTRAL_DISABLE_COMPANIES") or "")
    disabled = {c.strip().upper() for c in disable_raw.split(",") if c.strip()}
    if company and company in disabled:
        return False

    if mode == "canary":
        allow_raw = str(env.get("WATHEFNI_KUWAIT_GCC_MISTRAL_COMPANIES") or "WATHEFNI")
        allow = {c.strip().upper() for c in allow_raw.split(",") if c.strip()}
        return bool(company and company in allow)

    return True


def authority_status(*, company_code: str | None = None) -> dict[str, Any]:
    mode = kuwait_gcc_authority_mode()
    return {
        "mode": mode,
        "enabled": kuwait_gcc_authority_enabled(company_code=company_code),
        "kill_switch": mode in {"off", "kill", "disabled", "emergency_stop"},
        "gpt_fallback": False,
        "cv_v2": False,
    }
