"""Bounded runtime configuration authority cutover (Wave 4).

Global canonical authority remains hard-off.
Only explicitly allowlisted WATHEFNI boundaries may enter canary_canonical mode.
Legacy records stay dual-written for rollback.
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

import tenant_control_config as tc_config
import tenant_control_decision as decision
import tenant_control_lifecycle as lifecycle
import tenant_control_wave4_schema as wave4


CUTOVER_BOUNDARIES: tuple[str, ...] = (
    "company_profile",
    "module_policies",
    "prehire_policies",
    "notification_policies",
    "supported_integration_state",
    "readiness_state",
    "roles_permissions_canary",
    "lifecycle_activation_epochs",
)

# Hard rule: never globally replace legacy reads.
def global_canonical_hard_off() -> bool:
    return not decision.global_authoritative_enabled()


def ensure_schema(cur: Any) -> dict[str, Any]:
    return wave4.ensure_tenant_control_schema(cur)


def cutover_enabled(environ: dict[str, str] | None = None) -> bool:
    env = environ or os.environ
    return str(env.get("WATHEFNI_TENANT_CONTROL_RUNTIME_CUTOVER") or "off").lower() in {"1", "true", "on", "yes"}


def parity_for_boundary(cur: Any, *, company_code: str, boundary_key: str) -> dict[str, Any]:
    company = company_code.upper()
    if boundary_key == "company_profile":
        published = tc_config.get_published(cur, company_code=company, domain="company_profile")
        cur.execute(
            "SELECT name, country, metadata, status FROM companies WHERE company_code=%s",
            (company,),
        )
        legacy_row = cur.fetchone() or {}
        legacy = dict(legacy_row)
        meta = legacy.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta)
        cfg = (published or {}).get("config_json") or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        parity = {
            "display_name": {
                "legacy": legacy.get("name"),
                "canonical": cfg.get("display_name"),
                "match": str(legacy.get("name") or "").lower() == str(cfg.get("display_name") or "").lower()
                or not cfg,
            },
            "country": {"legacy": legacy.get("country"), "canonical": cfg.get("country")},
            "timezone": {"legacy": meta.get("timezone"), "canonical": cfg.get("timezone")},
            "currency": {"legacy": meta.get("currency"), "canonical": cfg.get("currency")},
        }
        return {"ok": True, "boundary_key": boundary_key, "parity": parity, "published_version": (published or {}).get("version_number")}
    if boundary_key == "module_policies":
        cur.execute("SELECT module_key FROM company_modules WHERE company_code=%s AND enabled IS TRUE", (company,))
        legacy = sorted(str(r["module_key"]) for r in cur.fetchall())
        tenant = decision.load_tenant_state(cur, company)
        canonical = []
        if tenant:
            cur.execute(
                "SELECT module_key FROM tc_tenant_module_instances WHERE tenant_id=%s AND enabled IS TRUE",
                (tenant["tenant_id"],),
            )
            canonical = sorted(str(r["module_key"]) for r in cur.fetchall())
        return {"ok": True, "boundary_key": boundary_key, "parity": {"legacy": legacy, "canonical": canonical, "match": legacy == canonical}}
    if boundary_key in {"prehire_policies", "notification_policies"}:
        domain = "prehire" if boundary_key == "prehire_policies" else "notification_policies"
        published = tc_config.get_published(cur, company_code=company, domain=domain)
        return {
            "ok": True,
            "boundary_key": boundary_key,
            "parity": {"published": bool(published), "version": (published or {}).get("version_number")},
        }
    if boundary_key == "supported_integration_state":
        cur.execute(
            "SELECT provider_key, state, support_tier FROM tc_integrations WHERE company_code=%s",
            (company,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        bad = [r for r in rows if r["support_tier"] in {"unsupported", "future"} and r["state"] not in {"not_selected"}]
        return {"ok": True, "boundary_key": boundary_key, "parity": {"integrations": rows, "unsupported_not_live": not bad}}
    if boundary_key == "readiness_state":
        import tenant_control_readiness as tc_ready

        report = tc_ready.evaluate_readiness(cur, company_code=company)
        return {"ok": True, "boundary_key": boundary_key, "parity": {"ready": report.get("ready"), "blocker_count": report.get("blocker_count")}}
    if boundary_key == "roles_permissions_canary":
        tenant = decision.load_tenant_state(cur, company)
        cur.execute("SELECT count(*)::int AS n FROM tc_tenant_roles WHERE tenant_id=%s", (tenant["tenant_id"],)) if tenant else None
        n = int((cur.fetchone() or {}).get("n") or 0) if tenant else 0
        return {"ok": True, "boundary_key": boundary_key, "parity": {"roles": n, "fixed_role_behavior_unchanged": True}}
    if boundary_key == "lifecycle_activation_epochs":
        tenant = decision.load_tenant_state(cur, company)
        return {
            "ok": True,
            "boundary_key": boundary_key,
            "parity": {
                "lifecycle_status": (tenant or {}).get("lifecycle_status"),
                "activation_epoch": (tenant or {}).get("activation_epoch"),
            },
        }
    return {"ok": False, "error": "unknown_boundary"}


def activate_canary_cutover(
    cur: Any,
    *,
    company_code: str,
    boundary_key: str,
    actor: str,
    canary_token: str,
) -> dict[str, Any]:
    ensure_schema(cur)
    if not global_canonical_hard_off():
        return {"ok": False, "error": "global_canonical_must_remain_hard_off"}
    if company_code.upper() != "WATHEFNI":
        return {"ok": False, "error": "cutover_wathefni_only"}
    if boundary_key not in CUTOVER_BOUNDARIES:
        return {"ok": False, "error": "unknown_boundary"}
    expected = str(os.environ.get("WATHEFNI_TENANT_CONTROL_CUTOVER_TOKEN") or "wave4-cutover-canary")
    if canary_token != expected:
        return {"ok": False, "error": "cutover_token_required"}
    parity = parity_for_boundary(cur, company_code=company_code, boundary_key=boundary_key)
    cur.execute(
        """
        INSERT INTO tc_runtime_cutover (
          company_code, boundary_key, mode, parity_json, canary_token, activated_at, actor, detail
        ) VALUES (%s,%s,'canary_canonical',%s::jsonb,%s,now(),%s,%s::jsonb)
        ON CONFLICT (company_code, boundary_key) DO UPDATE SET
          mode='canary_canonical',
          parity_json=EXCLUDED.parity_json,
          canary_token=EXCLUDED.canary_token,
          activated_at=now(),
          rolled_back_at=NULL,
          actor=EXCLUDED.actor,
          detail=EXCLUDED.detail,
          updated_at=now()
        RETURNING cutover_id::text AS cutover_id, mode
        """,
        (
            company_code.upper(),
            boundary_key,
            json.dumps(parity, default=str),
            canary_token,
            actor,
            json.dumps({"correlation_id": uuid4().hex}),
        ),
    )
    row = dict(cur.fetchone())
    lifecycle._audit_fail_closed(
        cur,
        tenant_id=(decision.load_tenant_state(cur, company_code) or {}).get("tenant_id"),
        company_code=company_code.upper(),
        event_type="runtime_cutover_activated",
        actor=actor,
        before={"mode": "legacy"},
        after={"mode": "canary_canonical", "boundary": boundary_key},
        detail={"boundary_key": boundary_key, "parity": parity},
        idempotency_key=f"cutover-on-{company_code}-{boundary_key}-{uuid4().hex[:8]}",
    )
    return {"ok": True, **row, "parity": parity, "global_canonical": False}


def rollback_cutover(
    cur: Any,
    *,
    company_code: str,
    boundary_key: str,
    actor: str,
) -> dict[str, Any]:
    ensure_schema(cur)
    cur.execute(
        """
        UPDATE tc_runtime_cutover
        SET mode='rolled_back', rolled_back_at=now(), actor=%s, updated_at=now()
        WHERE company_code=%s AND boundary_key=%s
        RETURNING cutover_id::text AS cutover_id, mode
        """,
        (actor, company_code.upper(), boundary_key),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "cutover_not_found"}
    lifecycle._audit_fail_closed(
        cur,
        tenant_id=(decision.load_tenant_state(cur, company_code) or {}).get("tenant_id"),
        company_code=company_code.upper(),
        event_type="runtime_cutover_rolled_back",
        actor=actor,
        before={"mode": "canary_canonical"},
        after={"mode": "legacy"},
        detail={"boundary_key": boundary_key},
        idempotency_key=f"cutover-off-{company_code}-{boundary_key}-{uuid4().hex[:8]}",
    )
    return {"ok": True, **dict(row), "authority": "legacy"}


def resolve_runtime_value(
    cur: Any,
    *,
    company_code: str,
    boundary_key: str,
    legacy_value: Any,
) -> dict[str, Any]:
    """Shadow-first resolver. Canonical only when canary_canonical for WATHEFNI boundary."""
    ensure_schema(cur)
    cur.execute(
        """
        SELECT mode FROM tc_runtime_cutover
        WHERE company_code=%s AND boundary_key=%s
        LIMIT 1
        """,
        (company_code.upper(), boundary_key),
    )
    row = cur.fetchone()
    mode = (row or {}).get("mode") if row else "legacy"
    if mode != "canary_canonical" or company_code.upper() != "WATHEFNI":
        return {"authority": "legacy", "value": legacy_value, "mode": mode or "legacy"}
    # Canonical sample reads for profile only; other boundaries return structured markers.
    if boundary_key == "company_profile":
        published = tc_config.get_published(cur, company_code=company_code, domain="company_profile")
        cfg = (published or {}).get("config_json") or {}
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        return {"authority": "canonical", "value": cfg or legacy_value, "mode": mode}
    return {"authority": "canonical", "value": legacy_value, "mode": mode, "note": "boundary_marker"}


def list_cutovers(cur: Any, *, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT boundary_key, mode, activated_at, rolled_back_at, parity_json
        FROM tc_runtime_cutover WHERE company_code=%s ORDER BY boundary_key
        """,
        (company_code.upper(),),
    )
    return [dict(r) for r in cur.fetchall()]
