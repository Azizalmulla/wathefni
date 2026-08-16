"""Canonical tenant/module/capability decision service (Wave 2).

Shadow-first. Legacy reads remain the default authority. Canonical authority is
enabled only for explicitly allowlisted WATHEFNI canary capabilities.

Kill switches:
- WATHEFNI_TENANT_CONTROL_PLANE (master)
- WATHEFNI_TENANT_CONTROL_DECISION (decision service itself)
- WATHEFNI_TENANT_CONTROL_AUTHORITATIVE (global — still never auto-on)
- WATHEFNI_TENANT_CONTROL_LIFECYCLE_ENFORCE
- WATHEFNI_TENANT_CONTROL_EPOCH_ENFORCE
- WATHEFNI_TENANT_CONTROL_CANARY_AUTHORITY (allow canary-only authority)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

import module_catalog as modules
import tenant_control_catalog as catalog
import tenant_control_wave2_schema as wave2_schema


FEATURE_PLANE = "WATHEFNI_TENANT_CONTROL_PLANE"
FEATURE_DECISION = "WATHEFNI_TENANT_CONTROL_DECISION"
FEATURE_AUTHORITATIVE = "WATHEFNI_TENANT_CONTROL_AUTHORITATIVE"
FEATURE_LIFECYCLE = "WATHEFNI_TENANT_CONTROL_LIFECYCLE_ENFORCE"
FEATURE_EPOCH = "WATHEFNI_TENANT_CONTROL_EPOCH_ENFORCE"
FEATURE_CANARY_AUTHORITY = "WATHEFNI_TENANT_CONTROL_CANARY_AUTHORITY"
FEATURE_SHADOW = "WATHEFNI_TENANT_CONTROL_SHADOW"
FEATURE_DECISION_PERSIST = "WATHEFNI_TENANT_CONTROL_DECISION_AUDIT"

PROTECTED_TENANT = "WATHEFNI"
ALLOW_WATHEFNI_SUSPEND = "WATHEFNI_TENANT_CONTROL_ALLOW_WATHEFNI_SUSPEND"

ACTIVE_LIFECYCLES = frozenset({"active", "ready", "testing"})
BLOCKING_LIFECYCLES = frozenset({"suspended", "offboarding", "archived", "draft", "setup", "provisioning"})


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def plane_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_PLANE), default=True)


def decision_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if not plane_enabled(env):
        return False
    return _truthy(env.get(FEATURE_DECISION), default=True)


def lifecycle_enforce_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if not decision_enabled(env):
        return False
    return _truthy(env.get(FEATURE_LIFECYCLE), default=True)


def epoch_enforce_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if not decision_enabled(env):
        return False
    return _truthy(env.get(FEATURE_EPOCH), default=True)


def canary_authority_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if not decision_enabled(env):
        return False
    return _truthy(env.get(FEATURE_CANARY_AUTHORITY), default=True)


def global_authoritative_enabled(environ: dict[str, str] | None = None) -> bool:
    # Wave 2 still refuses global replacement of legacy authority.
    _ = environ
    return False


def shadow_persist_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if not decision_enabled(env):
        return False
    return _truthy(env.get(FEATURE_SHADOW), default=True) and _truthy(
        env.get(FEATURE_DECISION_PERSIST), default=True
    )


@dataclass
class DecisionResult:
    allow: bool
    reason_code: str
    tenant: str
    module: str | None = None
    capability: str | None = None
    configuration_version: int | None = None
    activation_epoch: int | None = None
    remediation: str | None = None
    audit_correlation_id: str = field(default_factory=lambda: uuid4().hex)
    mode: str = "shadow"  # shadow | authoritative | bypass | legacy
    surface: str = "unknown"
    legacy_allow: bool | None = None
    parity: bool | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_schema(cur: Any) -> dict[str, Any]:
    return wave2_schema.ensure_tenant_control_schema(cur)


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def load_tenant_state(cur: Any, company_code: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT tenant_id::text AS tenant_id, company_code, lifecycle_status,
               activation_epoch, synthetic, externally_usable, legacy_company_status,
               metadata
        FROM tc_tenants
        WHERE company_code=%s
        LIMIT 1
        """,
        (company_code.upper(),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def load_module_state(cur: Any, tenant_id: str, module_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT module_key, capability_key, enabled, instance_state,
               purchased, desired, configured, tested, ready, live,
               paused, degraded, blocked, activation_epoch, block_reason, pause_reason
        FROM tc_tenant_module_instances
        WHERE tenant_id=%s AND module_key=%s
        LIMIT 1
        """,
        (tenant_id, modules.normalize_module_key(module_key)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def load_latest_config_version(cur: Any, tenant_id: str) -> int | None:
    cur.execute(
        """
        SELECT max(version_number) AS version_number
        FROM tc_tenant_config_versions
        WHERE tenant_id=%s AND status='published'
        """,
        (tenant_id,),
    )
    row = cur.fetchone()
    value = _row_get(row, "version_number")
    return int(value) if value is not None else None


def capability_for_module(module_key: str | None) -> str | None:
    if not module_key:
        return None
    key = modules.normalize_module_key(module_key)
    return catalog.LEGACY_MODULE_TO_CAPABILITY.get(key)


def is_canary_authoritative(
    cur: Any,
    *,
    company_code: str,
    module_key: str | None,
    capability_key: str | None,
    surface: str,
) -> bool:
    if not canary_authority_enabled():
        return False
    if global_authoritative_enabled():
        return False
    cur.execute(
        """
        SELECT 1
        FROM tc_canary_authority
        WHERE enabled IS TRUE
          AND company_code=%s
          AND (
            module_key IS NULL OR module_key IN ('', '*') OR module_key=%s
          )
          AND (
            capability_key IS NULL OR capability_key IN ('', '*') OR capability_key=%s
          )
          AND (
            surface IS NULL OR surface IN ('', '*') OR surface=%s
          )
          AND (expires_at IS NULL OR expires_at > now())
        LIMIT 1
        """,
        (
            company_code.upper(),
            module_key or "",
            capability_key or "",
            surface or "",
        ),
    )
    return cur.fetchone() is not None


def evaluate_decision(
    cur: Any | None,
    *,
    company_code: str,
    surface: str,
    module_key: str | None = None,
    capability_key: str | None = None,
    legacy_allow: bool | None = None,
    queued_epoch: int | None = None,
    actor_permission_ok: bool | None = None,
    integration_ready: bool | None = None,
    runtime_healthy: bool | None = True,
    persist: bool = True,
    environ: dict[str, str] | None = None,
) -> DecisionResult:
    """Evaluate canonical allow/deny. Default mode is shadow unless canary authority matches."""
    company = (company_code or "").strip().upper()
    module = modules.normalize_module_key(module_key) if module_key else None
    capability = capability_key or capability_for_module(module)
    correlation = uuid4().hex

    if not decision_enabled(environ):
        result = DecisionResult(
            allow=True if legacy_allow is None else bool(legacy_allow),
            reason_code="decision_bypass",
            tenant=company or "UNKNOWN",
            module=module,
            capability=capability,
            remediation=None,
            audit_correlation_id=correlation,
            mode="bypass",
            surface=surface,
            legacy_allow=legacy_allow,
            parity=True if legacy_allow is not None else None,
            detail={"kill_switch": FEATURE_DECISION},
        )
        return result

    if not company:
        return DecisionResult(
            allow=False,
            reason_code="tenant_required",
            tenant="UNKNOWN",
            module=module,
            capability=capability,
            remediation="Provide a company_code / tenant.",
            audit_correlation_id=correlation,
            mode="shadow",
            surface=surface,
            legacy_allow=legacy_allow,
        )

    if runtime_healthy is False:
        result = DecisionResult(
            allow=False,
            reason_code="runtime_unhealthy",
            tenant=company,
            module=module,
            capability=capability,
            remediation="Restore runtime health before retrying.",
            audit_correlation_id=correlation,
            mode="shadow",
            surface=surface,
            legacy_allow=legacy_allow,
        )
        _maybe_persist(cur, result, persist)
        return result

    tenant = load_tenant_state(cur, company) if cur is not None else None
    config_version = load_latest_config_version(cur, tenant["tenant_id"]) if cur and tenant else None
    activation_epoch = int(tenant["activation_epoch"]) if tenant else None
    module_state = load_module_state(cur, tenant["tenant_id"], module) if cur and tenant and module else None

    # Canonical evaluation
    allow = True
    reason = "allow"
    remediation = None

    if tenant is None:
        # Unknown to control plane: do not invent denials for live tenants in shadow.
        # Synthetic canary tenants must exist in tc_tenants.
        allow = True if legacy_allow is None else bool(legacy_allow)
        reason = "tenant_not_imported_shadow_pass"
        remediation = "Import tenant into control plane."
    else:
        lifecycle = str(tenant.get("lifecycle_status") or "active")
        if lifecycle_enforce_enabled(environ) and lifecycle in BLOCKING_LIFECYCLES:
            allow = False
            reason = f"tenant_lifecycle_{lifecycle}"
            remediation = f"Restore tenant lifecycle from {lifecycle} to active."
        elif lifecycle_enforce_enabled(environ) and lifecycle == "paused":
            allow = False
            reason = "tenant_lifecycle_paused"
            remediation = "Resume tenant before accepting interactive or background work."
        elif module and module_state:
            if module_state.get("blocked"):
                allow = False
                reason = "module_blocked"
                remediation = module_state.get("block_reason") or "Clear module block."
            elif bool(module_state.get("paused")) or module_state.get("instance_state") == "paused":
                allow = False
                reason = "module_paused"
                remediation = module_state.get("pause_reason") or "Resume module."
            elif module_state.get("purchased") is False and not bool(module_state.get("enabled")):
                allow = False
                reason = "module_unpurchased"
                remediation = "Purchase/enable the module entitlement."
            elif not bool(module_state.get("enabled")) or module_state.get("live") is False:
                allow = False
                reason = "module_not_live"
                remediation = "Enable and activate the module."
            activation_epoch = int(module_state.get("activation_epoch") or activation_epoch or 1)
        elif module and tenant and module_state is None:
            # Module not present in control-plane instances.
            if legacy_allow is False:
                allow = False
                reason = "module_not_granted"
                remediation = "Grant module in control plane and legacy registry."
            else:
                allow = True if legacy_allow is None else bool(legacy_allow)
                reason = "module_instance_missing_shadow_pass"

        if allow and actor_permission_ok is False:
            allow = False
            reason = "permission_denied"
            remediation = "Grant required permission or role scope."

        if allow and integration_ready is False:
            allow = False
            reason = "integration_not_ready"
            remediation = "Complete integration readiness checks."

        if allow and queued_epoch is not None and epoch_enforce_enabled(environ):
            live_epoch = int(activation_epoch or 1)
            if int(queued_epoch) != live_epoch:
                allow = False
                reason = "activation_epoch_mismatch"
                remediation = (
                    f"Queued epoch {queued_epoch} != live epoch {live_epoch}. "
                    "Cancel, hold, or re-enqueue under the live epoch."
                )
                detail_epoch = {"queued_epoch": queued_epoch, "live_epoch": live_epoch}
            else:
                detail_epoch = {"queued_epoch": queued_epoch, "live_epoch": live_epoch}
        else:
            detail_epoch = {"queued_epoch": queued_epoch, "live_epoch": activation_epoch}

    authoritative = False
    if cur is not None and tenant is not None:
        authoritative = is_canary_authoritative(
            cur,
            company_code=company,
            module_key=module,
            capability_key=capability,
            surface=surface,
        )

    mode = "authoritative" if authoritative else "shadow"
    # In shadow mode, effective allow follows legacy when provided.
    effective_allow = allow
    if mode == "shadow" and legacy_allow is not None:
        effective_allow = bool(legacy_allow)
    elif mode == "authoritative":
        effective_allow = allow

    parity = None
    if legacy_allow is not None:
        parity = bool(legacy_allow) == bool(allow)

    result = DecisionResult(
        allow=effective_allow,
        reason_code=reason if (mode == "authoritative" or legacy_allow is None) else (
            reason if parity else f"shadow_observed_{reason}"
        ),
        tenant=company,
        module=module,
        capability=capability,
        configuration_version=config_version,
        activation_epoch=activation_epoch,
        remediation=remediation,
        audit_correlation_id=correlation,
        mode=mode,
        surface=surface,
        legacy_allow=legacy_allow,
        parity=parity,
        detail={
            "canonical_allow": allow,
            "effective_allow": effective_allow,
            "lifecycle": (tenant or {}).get("lifecycle_status"),
            "module_state": {
                k: module_state.get(k)
                for k in (
                    "enabled", "instance_state", "purchased", "desired", "configured",
                    "tested", "ready", "live", "paused", "degraded", "blocked",
                    "activation_epoch",
                )
            } if module_state else None,
            **detail_epoch,
        },
    )
    _maybe_persist(cur, result, persist)
    return result


def _maybe_persist(cur: Any | None, result: DecisionResult, persist: bool) -> None:
    if not persist or cur is None or not shadow_persist_enabled():
        return
    cur.execute(
        """
        INSERT INTO tc_decision_audit (
          correlation_id, company_code, surface, module_key, capability_key,
          allowed, reason_code, mode, legacy_allowed, parity,
          config_version, activation_epoch, remediation, detail
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            result.audit_correlation_id,
            result.tenant,
            result.surface,
            result.module,
            result.capability,
            bool(result.allow),
            result.reason_code,
            result.mode,
            result.legacy_allow,
            result.parity,
            result.configuration_version,
            result.activation_epoch,
            result.remediation,
            json.dumps(result.detail),
        ),
    )


def record_blocked_work(
    cur: Any,
    *,
    company_code: str,
    work_kind: str,
    reason_code: str,
    surface: str,
    module_key: str | None = None,
    capability_key: str | None = None,
    work_ref: str | None = None,
    disposition: str = "hold",
    queued_epoch: int | None = None,
    live_epoch: int | None = None,
    correlation_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    tenant = load_tenant_state(cur, company_code)
    cur.execute(
        """
        INSERT INTO tc_blocked_work (
          tenant_id, company_code, work_kind, work_ref, module_key, capability_key,
          surface, reason_code, disposition, queued_epoch, live_epoch, detail, correlation_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (tenant or {}).get("tenant_id"),
            company_code.upper(),
            work_kind,
            work_ref,
            module_key,
            capability_key,
            surface,
            reason_code,
            disposition,
            queued_epoch,
            live_epoch,
            json.dumps(detail or {}),
            correlation_id or uuid4().hex,
        ),
    )


def decide_with_legacy(
    cur: Any | None,
    *,
    company_code: str,
    surface: str,
    module_key: str | None,
    legacy_checker: Any,
    **kwargs: Any,
) -> DecisionResult:
    legacy_allow = None
    if module_key is not None and callable(legacy_checker):
        try:
            legacy_allow = bool(legacy_checker(company_code, module_key))
        except Exception as exc:
            legacy_allow = False
            kwargs = {**kwargs, "detail_error": str(exc)[:200]}
    return evaluate_decision(
        cur,
        company_code=company_code,
        surface=surface,
        module_key=module_key,
        legacy_allow=legacy_allow,
        **{k: v for k, v in kwargs.items() if k != "detail_error"},
    )
