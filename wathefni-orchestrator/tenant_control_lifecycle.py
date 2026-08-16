"""Tenant and module lifecycle + activation epochs (Wave 2).

WATHEFNI suspension is blocked unless an explicit canary allow token is set.
Synthetic canary tenants are control-plane only (not externally usable).
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import module_catalog as modules
import tenant_control_catalog as catalog
import tenant_control_decision as decision
import tenant_control_service as wave1


ALLOW_WATHEFNI_SUSPEND = "WATHEFNI_TENANT_CONTROL_ALLOW_WATHEFNI_SUSPEND"
PROTECTED_TENANT = "WATHEFNI"
SYNTHETIC_PREFIX = "__TC_WAVE2_"


def _env() -> dict[str, str]:
    return os.environ


def wathefni_suspend_allowed(token: str | None = None) -> bool:
    expected = str(_env().get(ALLOW_WATHEFNI_SUSPEND) or "").strip()
    if not expected:
        return False
    return bool(token) and str(token).strip() == expected


def ensure_schema(cur: Any) -> dict[str, Any]:
    return decision.ensure_schema(cur)


def _audit_fail_closed(
    cur: Any,
    *,
    tenant_id: str | None,
    company_code: str,
    event_type: str,
    actor: str,
    before: dict[str, Any],
    after: dict[str, Any],
    detail: dict[str, Any],
    idempotency_key: str,
) -> None:
    """Mandatory audit + outbox; raise if persistence fails."""
    diff = wave1._json_diff(before, after)
    cur.execute(
        """
        INSERT INTO tc_audit_events (
          tenant_id, company_code, event_type, actor, idempotency_key,
          before_json, after_json, diff_json, detail
        )
        SELECT %s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb
        WHERE NOT EXISTS (
          SELECT 1 FROM tc_audit_events
          WHERE company_code=%s AND event_type=%s AND idempotency_key=%s
        )
        """,
        (
            tenant_id,
            company_code.upper(),
            event_type,
            actor,
            idempotency_key,
            json.dumps(before),
            json.dumps(after),
            json.dumps(diff),
            json.dumps(detail),
            company_code.upper(),
            event_type,
            idempotency_key,
        ),
    )
    cur.execute(
        """
        INSERT INTO tc_outbox_events (
          tenant_id, company_code, event_type, payload, status, idempotency_key
        )
        SELECT %s,%s,%s,%s::jsonb,'pending',%s
        WHERE NOT EXISTS (
          SELECT 1 FROM tc_outbox_events
          WHERE company_code=%s AND event_type=%s AND idempotency_key=%s
        )
        """,
        (
            tenant_id,
            company_code.upper(),
            event_type,
            json.dumps({"before": before, "after": after, "diff": diff, "detail": detail, "actor": actor}),
            idempotency_key,
            company_code.upper(),
            event_type,
            idempotency_key,
        ),
    )
    # Verify at least one of audit/outbox exists for this key.
    cur.execute(
        """
        SELECT
          EXISTS(
            SELECT 1 FROM tc_audit_events
            WHERE company_code=%s AND event_type=%s AND idempotency_key=%s
          ) AS has_audit,
          EXISTS(
            SELECT 1 FROM tc_outbox_events
            WHERE company_code=%s AND event_type=%s AND idempotency_key=%s
          ) AS has_outbox
        """,
        (company_code.upper(), event_type, idempotency_key, company_code.upper(), event_type, idempotency_key),
    )
    row = cur.fetchone() or {}
    has_audit = bool(row["has_audit"] if isinstance(row, dict) else row[0])
    has_outbox = bool(row["has_outbox"] if isinstance(row, dict) else row[1])
    if not (has_audit and has_outbox):
        raise RuntimeError("control_plane_audit_outbox_persistence_failed")


def bump_tenant_epoch(
    cur: Any,
    *,
    company_code: str,
    reason: str,
    actor: str,
    correlation_id: str | None = None,
) -> int:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        raise RuntimeError("tenant_not_imported")
    new_epoch = int(tenant["activation_epoch"] or 1) + 1
    cur.execute(
        """
        UPDATE tc_tenants
        SET activation_epoch=%s, updated_at=now()
        WHERE tenant_id=%s
        """,
        (new_epoch, tenant["tenant_id"]),
    )
    cur.execute(
        """
        INSERT INTO tc_activation_epochs (
          tenant_id, module_key, scope, epoch_number, reason, actor, correlation_id
        ) VALUES (%s,NULL,'tenant',%s,%s,%s,%s)
        """,
        (tenant["tenant_id"], new_epoch, reason, actor, correlation_id or uuid4().hex),
    )
    return new_epoch


def bump_module_epoch(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    reason: str,
    actor: str,
    correlation_id: str | None = None,
) -> int:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        raise RuntimeError("tenant_not_imported")
    module = modules.normalize_module_key(module_key)
    state = decision.load_module_state(cur, tenant["tenant_id"], module)
    if not state:
        raise RuntimeError("module_instance_missing")
    new_epoch = int(state.get("activation_epoch") or 1) + 1
    cur.execute(
        """
        UPDATE tc_tenant_module_instances
        SET activation_epoch=%s, updated_at=now()
        WHERE tenant_id=%s AND module_key=%s
        """,
        (new_epoch, tenant["tenant_id"], module),
    )
    cur.execute(
        """
        INSERT INTO tc_activation_epochs (
          tenant_id, module_key, scope, epoch_number, reason, actor, correlation_id
        ) VALUES (%s,%s,'module',%s,%s,%s,%s)
        """,
        (tenant["tenant_id"], module, new_epoch, reason, actor, correlation_id or uuid4().hex),
    )
    return new_epoch


def sync_module_dimensions_from_legacy(
    cur: Any,
    *,
    company_code: str,
    enabled_modules: set[str] | list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Backfill purchased/desired/configured/tested/ready/live from legacy enabled set."""
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return {"ok": False, "error": "tenant_not_imported"}
    enabled = {modules.normalize_module_key(k) for k in enabled_modules}
    updated = 0
    for key in modules.MODULE_KEYS:
        is_on = key in enabled
        capability_key = catalog.LEGACY_MODULE_TO_CAPABILITY.get(key, f"legacy.{key}")
        cur.execute(
            """
            INSERT INTO tc_tenant_module_instances (
              tenant_id, module_key, capability_key, enabled, instance_state,
              purchased, desired, configured, tested, ready, live,
              paused, degraded, blocked, activation_epoch, catalog_version, metadata, updated_at
            ) VALUES (
              %s,%s,%s,%s,%s,
              %s,%s,%s,%s,%s,%s,
              false,false,false,1,%s,%s::jsonb,now()
            )
            ON CONFLICT (tenant_id, module_key) DO UPDATE SET
              enabled = EXCLUDED.enabled,
              purchased = EXCLUDED.purchased,
              desired = EXCLUDED.desired,
              configured = CASE WHEN EXCLUDED.enabled THEN true ELSE tc_tenant_module_instances.configured END,
              tested = CASE WHEN EXCLUDED.enabled THEN true ELSE tc_tenant_module_instances.tested END,
              ready = CASE WHEN EXCLUDED.enabled THEN true ELSE tc_tenant_module_instances.ready END,
              live = EXCLUDED.live,
              instance_state = CASE
                WHEN EXCLUDED.enabled THEN 'live'
                ELSE 'disabled'
              END,
              capability_key = EXCLUDED.capability_key,
              updated_at = now()
            """,
            (
                tenant["tenant_id"],
                key,
                capability_key,
                is_on,
                "live" if is_on else "disabled",
                is_on,
                is_on,
                is_on,
                is_on,
                is_on,
                is_on,
                catalog.CATALOG_VERSION,
                json.dumps({"synced_from_legacy": True}),
            ),
        )
        updated += 1
    return {"ok": True, "updated": updated, "enabled": sorted(enabled)}


def preview_module_pause(module_key: str) -> dict[str, Any]:
    key = modules.normalize_module_key(module_key)
    capability = catalog.LEGACY_MODULE_TO_CAPABILITY.get(key)
    cap_def = catalog.CAPABILITY_BY_KEY.get(capability or "")
    surfaces = list(cap_def.surfaces) if cap_def else list(catalog.SHADOW_SURFACES)
    dependents = [
        item.key
        for item in catalog.CAPABILITY_CATALOG
        if key and any(dep == capability for dep in item.depends_on)
    ]
    return {
        "module_key": key,
        "capability_key": capability,
        "impacted_surfaces": surfaces,
        "ui": "navigation" in surfaces or "direct_routes" in surfaces,
        "apis": "apis" in surfaces or "direct_routes" in surfaces,
        "mobile": "mobile" in surfaces,
        "workers": "workers" in surfaces or "queue_claims" in surfaces,
        "timers": "timers" in surfaces,
        "queues": "queue_claims" in surfaces,
        "webhooks": "webhooks" in surfaces,
        "integrations": "integrations" in surfaces,
        "notifications": "notifications" in surfaces or "outbound_notifications" in surfaces,
        "dependent_capabilities": dependents,
    }


def pause_module(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    actor: str,
    reason: str,
    bump_epoch: bool = True,
) -> dict[str, Any]:
    company = company_code.upper()
    module = modules.normalize_module_key(module_key)
    ensure_schema(cur)
    tenant = decision.load_tenant_state(cur, company)
    if not tenant:
        raise RuntimeError("tenant_not_imported")
    before = decision.load_module_state(cur, tenant["tenant_id"], module) or {}
    impact = preview_module_pause(module)
    correlation = uuid4().hex
    cur.execute(
        """
        UPDATE tc_tenant_module_instances
        SET paused=true, live=false, instance_state='paused',
            pause_reason=%s, updated_at=now()
        WHERE tenant_id=%s AND module_key=%s
        """,
        (reason, tenant["tenant_id"], module),
    )
    new_epoch = None
    if bump_epoch:
        new_epoch = bump_module_epoch(
            cur,
            company_code=company,
            module_key=module,
            reason=f"pause:{reason}",
            actor=actor,
            correlation_id=correlation,
        )
    after = decision.load_module_state(cur, tenant["tenant_id"], module) or {}
    _audit_fail_closed(
        cur,
        tenant_id=tenant["tenant_id"],
        company_code=company,
        event_type="module_paused",
        actor=actor,
        before=before,
        after=after,
        detail={"impact": impact, "reason": reason, "activation_epoch": new_epoch, "correlation_id": correlation},
        idempotency_key=f"module-pause-{company}-{module}-{correlation}",
    )
    cur.execute(
        """
        INSERT INTO tc_activation_events (
          tenant_id, event_type, capability_key, from_state, to_state, actor, detail
        ) VALUES (%s,'module_pause',%s,%s,'paused',%s,%s::jsonb)
        """,
        (
            tenant["tenant_id"],
            catalog.LEGACY_MODULE_TO_CAPABILITY.get(module),
            before.get("instance_state"),
            actor,
            json.dumps({"module_key": module, "impact": impact, "epoch": new_epoch}),
        ),
    )
    return {
        "ok": True,
        "company_code": company,
        "module_key": module,
        "impact": impact,
        "activation_epoch": new_epoch,
        "correlation_id": correlation,
        "before": before,
        "after": after,
    }


def resume_module(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    actor: str,
    reason: str = "resume",
    bump_epoch: bool = True,
) -> dict[str, Any]:
    company = company_code.upper()
    module = modules.normalize_module_key(module_key)
    tenant = decision.load_tenant_state(cur, company)
    if not tenant:
        raise RuntimeError("tenant_not_imported")
    before = decision.load_module_state(cur, tenant["tenant_id"], module) or {}
    correlation = uuid4().hex
    cur.execute(
        """
        UPDATE tc_tenant_module_instances
        SET paused=false, live=true, enabled=true, instance_state='live',
            pause_reason=NULL, updated_at=now()
        WHERE tenant_id=%s AND module_key=%s
        """,
        (tenant["tenant_id"], module),
    )
    new_epoch = None
    if bump_epoch:
        new_epoch = bump_module_epoch(
            cur,
            company_code=company,
            module_key=module,
            reason=f"resume:{reason}",
            actor=actor,
            correlation_id=correlation,
        )
    after = decision.load_module_state(cur, tenant["tenant_id"], module) or {}
    _audit_fail_closed(
        cur,
        tenant_id=tenant["tenant_id"],
        company_code=company,
        event_type="module_resumed",
        actor=actor,
        before=before,
        after=after,
        detail={"reason": reason, "activation_epoch": new_epoch, "correlation_id": correlation},
        idempotency_key=f"module-resume-{company}-{module}-{correlation}",
    )
    return {
        "ok": True,
        "company_code": company,
        "module_key": module,
        "activation_epoch": new_epoch,
        "correlation_id": correlation,
        "before": before,
        "after": after,
    }


def set_tenant_lifecycle(
    cur: Any,
    *,
    company_code: str,
    lifecycle_status: str,
    actor: str,
    reason: str,
    wathefni_suspend_token: str | None = None,
    revoke_sessions_callback: Any | None = None,
    synthetic: bool = False,
    externally_usable: bool = False,
) -> dict[str, Any]:
    company = company_code.upper()
    status = str(lifecycle_status or "").strip().lower()
    allowed = {
        "draft", "setup", "provisioning", "testing", "ready", "active",
        "paused", "suspended", "offboarding", "archived",
    }
    if status not in allowed:
        raise ValueError(f"invalid_lifecycle_status:{status}")

    if company == PROTECTED_TENANT and status in {"suspended", "offboarding", "archived"}:
        if not wathefni_suspend_allowed(wathefni_suspend_token):
            raise PermissionError("wathefni_suspension_blocked_without_explicit_canary_token")

    ensure_schema(cur)
    tenant = decision.load_tenant_state(cur, company)
    correlation = uuid4().hex
    if not tenant:
        # Synthetic control-plane-only tenant (never companies row).
        if not synthetic and not company.startswith(SYNTHETIC_PREFIX):
            raise RuntimeError("tenant_not_imported")
        cur.execute(
            """
            INSERT INTO tc_tenants (
              company_code, display_name, lifecycle_status, catalog_version,
              activation_epoch, synthetic, externally_usable, lifecycle_reason, metadata
            ) VALUES (%s,%s,%s,%s,1,%s,%s,%s,%s::jsonb)
            RETURNING tenant_id::text AS tenant_id, activation_epoch, lifecycle_status
            """,
            (
                company,
                company,
                status,
                catalog.CATALOG_VERSION,
                True,
                False,
                reason,
                json.dumps({"synthetic": True, "externally_usable": False}),
            ),
        )
        tenant = dict(cur.fetchone())

    before = {
        "lifecycle_status": tenant.get("lifecycle_status"),
        "activation_epoch": tenant.get("activation_epoch"),
    }
    new_epoch = bump_tenant_epoch(
        cur,
        company_code=company,
        reason=f"lifecycle:{status}:{reason}",
        actor=actor,
        correlation_id=correlation,
    )
    cur.execute(
        """
        UPDATE tc_tenants
        SET lifecycle_status=%s,
            lifecycle_reason=%s,
            synthetic=COALESCE(%s, synthetic),
            externally_usable=COALESCE(%s, externally_usable),
            suspended_at=CASE WHEN %s='suspended' THEN now() ELSE suspended_at END,
            restored_at=CASE WHEN %s='active' THEN now() ELSE restored_at END,
            updated_at=now()
        WHERE company_code=%s
        RETURNING tenant_id::text AS tenant_id, lifecycle_status, activation_epoch,
                  synthetic, externally_usable
        """,
        (
            status,
            reason,
            True if synthetic else None,
            False if synthetic else (False if externally_usable is False else None),
            status,
            status,
            company,
        ),
    )
    after_row = dict(cur.fetchone())
    session_revoke = None
    if status in {"suspended", "offboarding", "archived"} and callable(revoke_sessions_callback):
        session_revoke = revoke_sessions_callback(company, reason=f"lifecycle_{status}")

    after = {
        "lifecycle_status": after_row.get("lifecycle_status"),
        "activation_epoch": after_row.get("activation_epoch"),
        "synthetic": after_row.get("synthetic"),
        "externally_usable": after_row.get("externally_usable"),
    }
    _audit_fail_closed(
        cur,
        tenant_id=after_row.get("tenant_id"),
        company_code=company,
        event_type=f"tenant_lifecycle_{status}",
        actor=actor,
        before=before,
        after=after,
        detail={
            "reason": reason,
            "correlation_id": correlation,
            "session_revoke": session_revoke,
            "activation_epoch": new_epoch,
            "effects": {
                "reject_new_intake": status in {"suspended", "offboarding", "archived"},
                "block_queue_claims": status in {"suspended", "offboarding", "archived", "paused"},
                "suppress_outbound": status in {"suspended", "offboarding", "archived", "paused"},
                "stop_timers_workers": status in {"suspended", "offboarding", "archived", "paused"},
                "preserve_data": True,
            },
        },
        idempotency_key=f"tenant-lifecycle-{company}-{status}-{correlation}",
    )
    cur.execute(
        """
        INSERT INTO tc_activation_events (
          tenant_id, event_type, from_state, to_state, actor, detail
        ) VALUES (%s,'tenant_lifecycle',%s,%s,%s,%s::jsonb)
        """,
        (
            after_row.get("tenant_id"),
            before.get("lifecycle_status"),
            status,
            actor,
            json.dumps({"reason": reason, "epoch": new_epoch}),
        ),
    )
    return {
        "ok": True,
        "company_code": company,
        "before": before,
        "after": after,
        "activation_epoch": new_epoch,
        "correlation_id": correlation,
        "session_revoke": session_revoke,
        "externally_usable": bool(after.get("externally_usable")),
    }


def enable_canary_authority(
    cur: Any,
    *,
    company_code: str,
    module_key: str | None,
    capability_key: str | None,
    surface: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO tc_canary_authority (
          company_code, module_key, capability_key, surface, enabled, reason, actor
        ) VALUES (%s,%s,%s,%s,true,%s,%s)
        ON CONFLICT (company_code, module_key, capability_key, surface) DO UPDATE SET
          enabled=true, reason=EXCLUDED.reason, actor=EXCLUDED.actor
        RETURNING canary_id::text AS canary_id
        """,
        (
            company_code.upper(),
            module_key if module_key is not None else "*",
            capability_key if capability_key is not None else "*",
            surface or "*",
            reason,
            actor,
        ),
    )
    row = cur.fetchone()
    return {"ok": True, "canary_id": (row or {}).get("canary_id") if isinstance(row, dict) else (row[0] if row else None)}


def disable_canary_authority(
    cur: Any,
    *,
    company_code: str,
    module_key: str | None = None,
    capability_key: str | None = None,
    surface: str | None = None,
) -> int:
    clauses = ["company_code=%s"]
    params: list[Any] = [company_code.upper()]
    if module_key is not None:
        clauses.append("module_key=%s")
        params.append(module_key)
    if capability_key is not None:
        clauses.append("capability_key=%s")
        params.append(capability_key)
    if surface is not None:
        clauses.append("surface=%s")
        params.append(surface)
    cur.execute(
        f"UPDATE tc_canary_authority SET enabled=false WHERE {' AND '.join(clauses)}",
        params,
    )
    return int(cur.rowcount or 0)
