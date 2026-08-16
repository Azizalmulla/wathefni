"""Universal verified Job binding gate (Wave 4).

Shadow-deny first; enforcement only when the enforce flag is on.
Does not create bindings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import job_binding_authority as binding

FEATURE_GATE = "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE"
FEATURE_SHADOW = "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW"
FEATURE_ENFORCE = "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE"
FEATURE_ENFORCE_TENANTS = "WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS"
GATE_VERSION = "verified-job-binding-gate-v1"

DOWNSTREAM_ACTIONS = frozenset(
    {
        "ranking",
        "screening",
        "assessment",
        "interview",
        "communication",
        "lifecycle_transition",
        "shortlist",
        "reject",
        "offer",
        "hire",
        "ck_ranking_evidence",
    }
)


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _safe_company(value: str | None) -> str:
    return "".join(
        ch for ch in str(value or "").strip().upper() if ch.isalnum() or ch in {"_", "-"}
    )


def gate_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_GATE))


def enforce_flag_on(environ: dict[str, str] | None = None) -> bool:
    """Process-level ENFORCE flag (does not imply a tenant is in scope)."""

    return gate_enabled(environ) and _truthy(_env(environ).get(FEATURE_ENFORCE))


def enforce_tenant_allowed(
    company_code: str, environ: dict[str, str] | None = None
) -> bool:
    """Owner-authorized ENFORCE tenant allowlist. Empty allowlist = no enforce."""

    raw = str(_env(environ).get(FEATURE_ENFORCE_TENANTS) or "").strip()
    if not raw:
        return False
    allowed = {
        _safe_company(part) for part in raw.replace(";", ",").split(",") if part.strip()
    }
    return _safe_company(company_code) in allowed


def enforce_enabled(
    environ: dict[str, str] | None = None, *, company_code: str | None = None
) -> bool:
    """True when ENFORCE is on for the given company (or globally if no company)."""

    if not enforce_flag_on(environ):
        return False
    if company_code is None:
        # Backward-compatible process check used by kill-switch probes.
        return True
    return enforce_tenant_allowed(company_code, environ)


def shadow_enabled(
    environ: dict[str, str] | None = None, *, company_code: str | None = None
) -> bool:
    env = _env(environ)
    if company_code and enforce_enabled(env, company_code=company_code):
        return False
    if enforce_flag_on(env) and not str(env.get(FEATURE_ENFORCE_TENANTS) or "").strip():
        # Legacy: ENFORCE without tenant allowlist ⇒ enforce everywhere.
        return False
    return gate_enabled(env) and (
        _truthy(env.get(FEATURE_SHADOW)) or not enforce_flag_on(env)
    )


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    mode: str  # off | shadow_deny | enforce_deny | allow
    action: str
    reason_codes: tuple[str, ...]
    binding: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "mode": self.mode,
            "action": self.action,
            "reason_codes": list(self.reason_codes),
            "binding": self.binding,
            "gate_version": GATE_VERSION,
        }


def assert_verified_job_binding(
    cur: Any | None,
    *,
    company_code: str,
    app_key: str,
    action: str,
    application: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> GateDecision:
    """Require a verified application_job_binding for Job workflows.

    When gate is off: allow (legacy held-status gates remain elsewhere).
    When shadow: compute deny but allow=True with mode=shadow_deny.
    When enforce: allow only if verified binding exists.
    """

    action_key = str(action or "").strip().lower()
    if action_key not in DOWNSTREAM_ACTIONS:
        return GateDecision(
            allowed=False,
            mode="enforce_deny",
            action=action_key,
            reason_codes=("unknown_downstream_action",),
        )

    if not gate_enabled(environ):
        return GateDecision(
            allowed=True,
            mode="off",
            action=action_key,
            reason_codes=("gate_disabled",),
        )

    # CV-only / held Talent Pool records must never pass Job workflows.
    status = str((application or {}).get("status") or "").strip().lower()
    enforcing = enforce_enabled(environ, company_code=company_code)
    if status in {"needs_role", "import_review", "import_archived"}:
        decision = GateDecision(
            allowed=False,
            mode="enforce_deny" if enforcing else "shadow_deny",
            action=action_key,
            reason_codes=("held_or_unassigned_talent_pool_record",),
        )
        if not enforcing:
            return GateDecision(
                allowed=True,
                mode="shadow_deny",
                action=action_key,
                reason_codes=decision.reason_codes,
            )
        return decision

    verified = None
    if cur is not None and binding.enabled(environ):
        try:
            binding.ensure_schema(cur)
            verified = binding.get_verified_job_binding(
                cur, company_code=company_code, app_key=app_key
            )
        except Exception:
            verified = None

    if verified and verified.get("verified"):
        return GateDecision(
            allowed=True,
            mode="allow",
            action=action_key,
            reason_codes=("verified_job_binding",),
            binding=verified,
        )

    reasons = ("verified_job_binding_missing",)
    if enforcing:
        return GateDecision(
            allowed=False,
            mode="enforce_deny",
            action=action_key,
            reason_codes=reasons,
        )
    # Default Wave 4 posture: shadow-deny.
    return GateDecision(
        allowed=True,
        mode="shadow_deny",
        action=action_key,
        reason_codes=reasons,
    )


__all__ = [
    "FEATURE_GATE",
    "FEATURE_SHADOW",
    "FEATURE_ENFORCE",
    "FEATURE_ENFORCE_TENANTS",
    "GATE_VERSION",
    "DOWNSTREAM_ACTIONS",
    "gate_enabled",
    "shadow_enabled",
    "enforce_enabled",
    "enforce_flag_on",
    "enforce_tenant_allowed",
    "GateDecision",
    "assert_verified_job_binding",
]
