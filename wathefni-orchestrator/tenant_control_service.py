"""Tenant control-plane service (Wave 1) — shadow-only decisions + safe dual-write.

Kill switches:
- WATHEFNI_TENANT_CONTROL_PLANE: master (default on for schema helpers when called)
- WATHEFNI_TENANT_CONTROL_DUAL_WRITE: setup mutation dual-write (default on when plane on)
- WATHEFNI_TENANT_CONTROL_SHADOW: persist shadow comparisons (default on when plane on)
- WATHEFNI_TENANT_CONTROL_AUTHORITATIVE: NEVER enable in Wave 1 (ignored / forced false)

Live entitlement enforcement continues to use company_modules / require_entitlement.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import module_catalog as modules
import tenant_control_catalog as catalog
import tenant_control_schema as schema


FEATURE_PLANE = "WATHEFNI_TENANT_CONTROL_PLANE"
FEATURE_DUAL_WRITE = "WATHEFNI_TENANT_CONTROL_DUAL_WRITE"
FEATURE_SHADOW = "WATHEFNI_TENANT_CONTROL_SHADOW"
FEATURE_AUTHORITATIVE = "WATHEFNI_TENANT_CONTROL_AUTHORITATIVE"


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def plane_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_PLANE), default=True)


def dual_write_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if not plane_enabled(env):
        return False
    return _truthy(env.get(FEATURE_DUAL_WRITE), default=True)


def shadow_enabled(environ: dict[str, str] | None = None) -> bool:
    env = _env(environ)
    if not plane_enabled(env):
        return False
    return _truthy(env.get(FEATURE_SHADOW), default=True)


def authoritative_enabled(environ: dict[str, str] | None = None) -> bool:
    # Wave 2: global authoritative replacement remains hard-disabled.
    # Canary-only authority is handled by tenant_control_decision.canary_authority_enabled.
    _ = environ
    return False


def ensure_schema(cur: Any) -> dict[str, Any]:
    try:
        import tenant_control_wave4_schema as wave4

        return wave4.ensure_tenant_control_schema(cur)
    except Exception:
        try:
            import tenant_control_wave3_schema as wave3

            return wave3.ensure_tenant_control_schema(cur)
        except Exception:
            try:
                import tenant_control_wave2_schema as wave2

                return wave2.ensure_tenant_control_schema(cur)
            except Exception:
                return schema.ensure_tenant_control_schema(cur)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_idempotency(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


def _json_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_keys = set(before)
    after_keys = set(after)
    added = {key: after[key] for key in sorted(after_keys - before_keys)}
    removed = {key: before[key] for key in sorted(before_keys - after_keys)}
    changed = {
        key: {"before": before[key], "after": after[key]}
        for key in sorted(before_keys & after_keys)
        if before[key] != after[key]
    }
    return {"added": added, "removed": removed, "changed": changed}


def seed_dependency_definitions(cur: Any) -> int:
    count = 0
    for item in catalog.CAPABILITY_CATALOG:
        for dep in item.depends_on:
            cur.execute(
                """
                INSERT INTO tc_dependency_definitions (
                  capability_key, requires_capability_key, dependency_class, catalog_version, metadata
                ) VALUES (%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (capability_key, requires_capability_key, catalog_version) DO UPDATE
                  SET dependency_class = EXCLUDED.dependency_class,
                      metadata = EXCLUDED.metadata
                """,
                (
                    item.key,
                    dep,
                    item.dependency_class,
                    catalog.CATALOG_VERSION,
                    json.dumps({"commercial": item.commercial}),
                ),
            )
            count += 1
    return count


def get_tenant_id(cur: Any, company_code: str) -> str | None:
    cur.execute("SELECT tenant_id::text FROM tc_tenants WHERE company_code=%s", (company_code.upper(),))
    row = cur.fetchone()
    if not row:
        return None
    if isinstance(row, dict):
        return str(row.get("tenant_id"))
    return str(row[0])


def import_company_into_control_plane(
    cur: Any,
    *,
    company_code: str,
    legacy_modules: set[str] | list[str] | tuple[str, ...],
    company_status: str | None = None,
    display_name: str | None = None,
    module_rows: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    actor: str = "wave1_import",
) -> dict[str, Any]:
    """Import a live company into additive control-plane tables without changing legacy rows."""
    company = company_code.upper()
    enabled = {modules.normalize_module_key(key) for key in legacy_modules if modules.normalize_module_key(key)}
    ensure_schema(cur)
    seed_dependency_definitions(cur)

    cur.execute(
        """
        INSERT INTO tc_tenants (
          company_code, display_name, lifecycle_status, legacy_company_status,
          imported_from, catalog_version, metadata, updated_at
        ) VALUES (%s,%s,'active',%s,'companies',%s,%s::jsonb,now())
        ON CONFLICT (company_code) DO UPDATE SET
          display_name = EXCLUDED.display_name,
          legacy_company_status = EXCLUDED.legacy_company_status,
          catalog_version = EXCLUDED.catalog_version,
          metadata = EXCLUDED.metadata,
          updated_at = now()
        RETURNING tenant_id::text
        """,
        (
            company,
            display_name or company,
            company_status,
            catalog.CATALOG_VERSION,
            json.dumps(
                {
                    "imported_at": _now_iso(),
                    "settings_present": bool(settings),
                    "legacy_module_count": len(enabled),
                }
            ),
        ),
    )
    tenant_row = cur.fetchone()
    tenant_id = str(tenant_row["tenant_id"] if isinstance(tenant_row, dict) else tenant_row[0])

    settings_by_module = {
        str(row.get("module_key")): dict(row.get("settings") or {})
        for row in (module_rows or [])
        if row.get("module_key")
    }
    source_by_module = {
        str(row.get("module_key")): row.get("source")
        for row in (module_rows or [])
        if row.get("module_key")
    }

    capability_keys: set[str] = set()
    for module_key in sorted(enabled):
        capability_key = catalog.LEGACY_MODULE_TO_CAPABILITY.get(module_key)
        if not capability_key:
            # Preserve unknown/orphan legacy keys as synthetic capability grants.
            capability_key = f"legacy.{module_key}"
        capability_keys.add(capability_key)
        cur.execute(
            """
            INSERT INTO tc_tenant_module_instances (
              tenant_id, module_key, capability_key, enabled, instance_state,
              legacy_source, settings, catalog_version, metadata, updated_at
            ) VALUES (%s,%s,%s,true,'live',%s,%s::jsonb,%s,%s::jsonb,now())
            ON CONFLICT (tenant_id, module_key) DO UPDATE SET
              enabled = true,
              instance_state = 'live',
              legacy_source = EXCLUDED.legacy_source,
              settings = EXCLUDED.settings,
              catalog_version = EXCLUDED.catalog_version,
              metadata = EXCLUDED.metadata,
              updated_at = now()
            """,
            (
                tenant_id,
                module_key,
                capability_key,
                source_by_module.get(module_key),
                json.dumps(settings_by_module.get(module_key) or {}),
                catalog.CATALOG_VERSION,
                json.dumps({"imported": True}),
            ),
        )
        cur.execute(
            """
            INSERT INTO tc_contract_entitlements (
              tenant_id, capability_key, commercial, status, source, metadata, updated_at
            ) VALUES (%s,%s,true,'entitled','import',%s::jsonb,now())
            ON CONFLICT (tenant_id, capability_key) DO UPDATE SET
              status = 'entitled',
              commercial = true,
              source = 'import',
              updated_at = now()
            """,
            (tenant_id, capability_key, json.dumps({"module_key": module_key})),
        )
        cur.execute(
            """
            INSERT INTO tc_tenant_capability_grants (
              tenant_id, capability_key, granted, grant_mode, grant_reason, commercial, metadata, updated_at
            ) VALUES (%s,%s,true,'purchased','import',true,%s::jsonb,now())
            ON CONFLICT (tenant_id, capability_key) DO UPDATE SET
              granted = true,
              grant_mode = 'purchased',
              grant_reason = 'import',
              commercial = true,
              updated_at = now()
            """,
            (tenant_id, capability_key, json.dumps({"module_key": module_key})),
        )

    # Technical / backend capabilities implied by Candidates.
    if "pre_hiring" in enabled:
        for tech_key, reason in (
            ("cap.candidate_knowledge", "backend_under_candidates"),
            ("cap.talent_pool", "backend_under_candidates"),
            ("cap.unified_inbound_cv", "flag_gated_import"),
            ("cap.verified_job_binding", "flag_gated_import"),
        ):
            capability_keys.add(tech_key)
            cur.execute(
                """
                INSERT INTO tc_tenant_capability_grants (
                  tenant_id, capability_key, granted, grant_mode, grant_reason, commercial, metadata, updated_at
                ) VALUES (%s,%s,true,'implied_technical',%s,false,%s::jsonb,now())
                ON CONFLICT (tenant_id, capability_key) DO UPDATE SET
                  granted = true,
                  grant_mode = 'implied_technical',
                  grant_reason = EXCLUDED.grant_reason,
                  commercial = false,
                  updated_at = now()
                """,
                (tenant_id, tech_key, reason, json.dumps({"imported": True})),
            )

    if "interviews" in enabled:
        capability_keys.add("cap.interviews_compatibility")
        cur.execute(
            """
            INSERT INTO tc_tenant_capability_grants (
              tenant_id, capability_key, granted, grant_mode, grant_reason, commercial, metadata, updated_at
            ) VALUES (%s,%s,true,'compatibility','setup_protect',false,%s::jsonb,now())
            ON CONFLICT (tenant_id, capability_key) DO UPDATE SET
              granted = true,
              grant_mode = 'compatibility',
              grant_reason = 'setup_protect',
              updated_at = now()
            """,
            (tenant_id, "cap.interviews_compatibility", json.dumps({"protected": True})),
        )

    technical_grants = catalog.technical_dependencies_to_grant(capability_keys)
    for tech_key in sorted(technical_grants):
        cur.execute(
            """
            INSERT INTO tc_tenant_capability_grants (
              tenant_id, capability_key, granted, grant_mode, grant_reason, commercial, metadata, updated_at
            ) VALUES (%s,%s,true,'implied_technical','dependency_closure',false,%s::jsonb,now())
            ON CONFLICT (tenant_id, capability_key) DO NOTHING
            """,
            (tenant_id, tech_key, json.dumps({"auto": True})),
        )

    commercial_gaps = catalog.commercial_dependency_gaps(capability_keys)
    snapshot = {
        "modules": sorted(enabled),
        "modules_enabled": sorted(enabled),  # backward-compatible alias
        "capability_keys": sorted(capability_keys | technical_grants),
        "commercial_gaps": commercial_gaps,
        "settings": settings or {},
    }
    idempotency = _stable_idempotency("import", company, catalog.CATALOG_VERSION, ",".join(sorted(enabled)))
    cur.execute(
        """
        INSERT INTO tc_tenant_config_versions (
          tenant_id, version_number, status, catalog_version, config_json,
          before_json, after_json, diff_json, idempotency_key, published_by, published_at
        )
        SELECT %s,
               COALESCE((SELECT max(version_number) FROM tc_tenant_config_versions WHERE tenant_id=%s), 0) + 1,
               'published', %s, %s::jsonb, '{}'::jsonb, %s::jsonb, %s::jsonb, %s, %s, now()
        WHERE NOT EXISTS (
          SELECT 1 FROM tc_tenant_config_versions WHERE tenant_id=%s AND idempotency_key=%s
        )
        RETURNING version_number
        """,
        (
            tenant_id,
            tenant_id,
            catalog.CATALOG_VERSION,
            json.dumps(snapshot),
            json.dumps(snapshot),
            json.dumps({"added": snapshot, "removed": {}, "changed": {}}),
            idempotency,
            actor,
            tenant_id,
            idempotency,
        ),
    )
    version_row = cur.fetchone()
    version_number = None
    if version_row:
        version_number = int(version_row["version_number"] if isinstance(version_row, dict) else version_row[0])

    _persist_audit_outbox(
        cur,
        tenant_id=tenant_id,
        company_code=company,
        event_type="tenant_imported",
        actor=actor,
        idempotency_key=idempotency,
        before={},
        after=snapshot,
        detail={"version_number": version_number, "commercial_gaps": commercial_gaps},
    )

    cur.execute(
        """
        INSERT INTO tc_activation_events (
          tenant_id, event_type, from_state, to_state, actor, detail
        ) VALUES (%s,'import_shadow','legacy_only','shadow_imported',%s,%s::jsonb)
        """,
        (tenant_id, actor, json.dumps({"modules": sorted(enabled)})),
    )

    cur.execute(
        """
        INSERT INTO tc_readiness_checks (tenant_id, check_key, capability_key, status, detail, checked_at)
        VALUES
          (%s,'legacy_modules_imported',NULL,%s,%s::jsonb,now()),
          (%s,'interviews_preserved','mod.interviews',%s,%s::jsonb,now()),
          (%s,'commercial_deps_clear',NULL,%s,%s::jsonb,now())
        ON CONFLICT (tenant_id, check_key) DO UPDATE SET
          status = EXCLUDED.status,
          detail = EXCLUDED.detail,
          checked_at = now()
        """,
        (
            tenant_id,
            "pass" if enabled else "fail",
            json.dumps({"modules": sorted(enabled)}),
            tenant_id,
            "pass" if "interviews" in enabled else "warn",
            json.dumps({"interviews_enabled": "interviews" in enabled}),
            tenant_id,
            "pass" if not commercial_gaps else "fail",
            json.dumps({"gaps": commercial_gaps}),
        ),
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "company_code": company,
        "modules_enabled": sorted(enabled),
        "capability_keys": sorted(capability_keys | technical_grants),
        "commercial_gaps": commercial_gaps,
        "version_number": version_number,
        "catalog_version": catalog.CATALOG_VERSION,
    }


def canonical_modules_for_tenant(cur: Any, company_code: str) -> set[str]:
    tenant_id = get_tenant_id(cur, company_code)
    if not tenant_id:
        return set()
    cur.execute(
        """
        SELECT module_key
        FROM tc_tenant_module_instances
        WHERE tenant_id=%s AND enabled IS TRUE
        """,
        (tenant_id,),
    )
    rows = cur.fetchall() or []
    out: set[str] = set()
    for row in rows:
        key = row["module_key"] if isinstance(row, dict) else row[0]
        out.add(str(key))
    return out


def canonical_capability_granted(cur: Any, company_code: str, capability_key: str) -> bool:
    tenant_id = get_tenant_id(cur, company_code)
    if not tenant_id:
        return False
    cur.execute(
        """
        SELECT granted
        FROM tc_tenant_capability_grants
        WHERE tenant_id=%s AND capability_key=%s
        LIMIT 1
        """,
        (tenant_id, capability_key),
    )
    row = cur.fetchone()
    if not row:
        return False
    return bool(row["granted"] if isinstance(row, dict) else row[0])


def shadow_module_decision(
    *,
    company_code: str,
    module_key: str,
    legacy_enabled: bool,
    canonical_enabled: bool,
    surface: str,
    subject_key: str,
) -> dict[str, Any]:
    parity = bool(legacy_enabled) == bool(canonical_enabled)
    return {
        "company_code": company_code.upper(),
        "surface": surface,
        "subject_key": subject_key,
        "module_key": modules.normalize_module_key(module_key),
        "legacy_decision": {"enabled": bool(legacy_enabled)},
        "canonical_decision": {"enabled": bool(canonical_enabled), "authoritative": False},
        "parity": parity,
        "shadow_only": True,
    }


def persist_shadow_decision(cur: Any, decision: dict[str, Any]) -> None:
    if not shadow_enabled():
        return
    tenant_id = get_tenant_id(cur, str(decision.get("company_code") or ""))
    cur.execute(
        """
        INSERT INTO tc_shadow_decision_runs (
          tenant_id, company_code, surface, subject_key,
          legacy_decision, canonical_decision, parity, detail
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb)
        """,
        (
            tenant_id,
            str(decision.get("company_code") or "").upper(),
            str(decision.get("surface") or ""),
            str(decision.get("subject_key") or ""),
            json.dumps(decision.get("legacy_decision") or {}),
            json.dumps(decision.get("canonical_decision") or {}),
            bool(decision.get("parity")),
            json.dumps({k: v for k, v in decision.items() if k not in {
                "legacy_decision", "canonical_decision", "parity", "surface", "subject_key", "company_code"
            }}),
        ),
    )


def run_shadow_matrix(
    cur: Any,
    *,
    company_code: str,
    legacy_modules: set[str],
    surface_subjects: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Compare legacy configured modules vs canonical instances across surfaces."""
    company = company_code.upper()
    canonical = canonical_modules_for_tenant(cur, company)
    subjects = surface_subjects or {
        surface: sorted(set(legacy_modules) | set(canonical) | set(modules.MODULE_KEYS))
        for surface in catalog.SHADOW_SURFACES
    }
    results: list[dict[str, Any]] = []
    mismatches = 0
    for surface, module_list in subjects.items():
        for module_key in module_list:
            key = modules.normalize_module_key(module_key)
            decision = shadow_module_decision(
                company_code=company,
                module_key=key,
                legacy_enabled=key in legacy_modules,
                canonical_enabled=key in canonical,
                surface=surface,
                subject_key=f"{surface}:{key}",
            )
            persist_shadow_decision(cur, decision)
            results.append(decision)
            if not decision["parity"]:
                mismatches += 1
    return {
        "company_code": company,
        "checked": len(results),
        "mismatches": mismatches,
        "parity": mismatches == 0,
        "legacy_modules": sorted(legacy_modules),
        "canonical_modules": sorted(canonical),
        "results": results,
    }


def validate_module_publish(
    requested_modules: list[str] | set[str] | tuple[str, ...],
    *,
    currently_enabled: list[str] | set[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    protected = modules.protect_setup_module_selection(requested_modules, currently_enabled)
    capability_keys = {
        catalog.LEGACY_MODULE_TO_CAPABILITY[key]
        for key in protected
        if key in catalog.LEGACY_MODULE_TO_CAPABILITY
    }
    technical = catalog.technical_dependencies_to_grant(capability_keys)
    commercial_gaps = catalog.commercial_dependency_gaps(capability_keys)
    # Also validate legacy module dependency graph.
    module_gaps = modules.missing_module_dependencies(protected)
    ok = not commercial_gaps and not module_gaps
    return {
        "ok": ok,
        "modules": protected,
        "protected_retained": sorted(set(protected) - set(requested_modules)),
        "technical_grants": sorted(technical),
        "commercial_gaps": commercial_gaps,
        "module_gaps": module_gaps,
        "blocks_publish": (not ok),
    }


def dual_write_module_save(
    cur: Any,
    *,
    company_code: str,
    requested_modules: list[str],
    currently_enabled: list[str] | set[str] | tuple[str, ...] | None,
    actor: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Safe dual-write companion for setup_console_set_modules.

    Does not mutate company_modules. Caller remains responsible for legacy writes.
    """
    if not dual_write_enabled():
        return {"ok": True, "skipped": True, "reason": "dual_write_disabled"}

    company = company_code.upper()
    ensure_schema(cur)
    validation = validate_module_publish(requested_modules, currently_enabled=currently_enabled)
    if validation["blocks_publish"]:
        return {
            "ok": False,
            "error": "commercial_or_module_dependency",
            "validation": validation,
        }

    before_modules = sorted(
        {modules.normalize_module_key(key) for key in (currently_enabled or []) if modules.normalize_module_key(key)}
    )
    after_modules = list(validation["modules"])
    before = {"modules": before_modules}
    after = {
        "modules": after_modules,
        "technical_grants": validation["technical_grants"],
    }
    diff = _json_diff(before, after)
    idem = idempotency_key or _stable_idempotency(
        "modules_save", company, ",".join(after_modules), actor, _now_iso()[:16]
    )

    # Ensure tenant exists (import-lite).
    tenant_id = get_tenant_id(cur, company)
    if not tenant_id:
        imported = import_company_into_control_plane(
            cur,
            company_code=company,
            legacy_modules=set(before_modules),
            actor=actor,
        )
        tenant_id = imported["tenant_id"]

    cur.execute(
        """
        INSERT INTO tc_configuration_drafts (
          tenant_id, draft_kind, status, base_version_number, proposed_json,
          validation_json, idempotency_key, created_by, updated_at
        )
        SELECT %s, 'modules', 'validated',
               COALESCE((SELECT max(version_number) FROM tc_tenant_config_versions WHERE tenant_id=%s), 0),
               %s::jsonb, %s::jsonb, %s, %s, now()
        WHERE NOT EXISTS (
          SELECT 1 FROM tc_configuration_drafts WHERE tenant_id=%s AND idempotency_key=%s
        )
        RETURNING draft_id::text
        """,
        (
            tenant_id,
            tenant_id,
            json.dumps(after),
            json.dumps(validation),
            idem,
            actor,
            tenant_id,
            idem,
        ),
    )
    draft_row = cur.fetchone()
    draft_id = None
    if draft_row:
        draft_id = str(draft_row["draft_id"] if isinstance(draft_row, dict) else draft_row[0])

    # Upsert module instances to match protected selection.
    for key in after_modules:
        capability_key = catalog.LEGACY_MODULE_TO_CAPABILITY.get(key, f"legacy.{key}")
        cur.execute(
            """
            INSERT INTO tc_tenant_module_instances (
              tenant_id, module_key, capability_key, enabled, instance_state,
              legacy_source, catalog_version, metadata, updated_at
            ) VALUES (%s,%s,%s,true,'live','setup_console_dual_write',%s,%s::jsonb,now())
            ON CONFLICT (tenant_id, module_key) DO UPDATE SET
              enabled = true,
              instance_state = 'live',
              legacy_source = 'setup_console_dual_write',
              updated_at = now()
            """,
            (tenant_id, key, capability_key, catalog.CATALOG_VERSION, json.dumps({"dual_write": True})),
        )
        cur.execute(
            """
            INSERT INTO tc_tenant_capability_grants (
              tenant_id, capability_key, granted, grant_mode, grant_reason, commercial, metadata, updated_at
            ) VALUES (%s,%s,true,'purchased','setup_console_dual_write',true,%s::jsonb,now())
            ON CONFLICT (tenant_id, capability_key) DO UPDATE SET
              granted = true, updated_at = now()
            """,
            (tenant_id, capability_key, json.dumps({"module_key": key})),
        )
    # Disable modules not in after set, except never disable protected compatibility if still in after.
    cur.execute(
        """
        UPDATE tc_tenant_module_instances
        SET enabled=false, instance_state='disabled', updated_at=now()
        WHERE tenant_id=%s AND enabled IS TRUE AND module_key <> ALL(%s)
        """,
        (tenant_id, after_modules),
    )

    for tech_key in validation["technical_grants"]:
        cur.execute(
            """
            INSERT INTO tc_tenant_capability_grants (
              tenant_id, capability_key, granted, grant_mode, grant_reason, commercial, metadata, updated_at
            ) VALUES (%s,%s,true,'implied_technical','dual_write_closure',false,%s::jsonb,now())
            ON CONFLICT (tenant_id, capability_key) DO UPDATE SET
              granted = true, updated_at = now()
            """,
            (tenant_id, tech_key, json.dumps({"auto": True})),
        )

    if "interviews" in after_modules:
        cur.execute(
            """
            INSERT INTO tc_tenant_capability_grants (
              tenant_id, capability_key, granted, grant_mode, grant_reason, commercial, metadata, updated_at
            ) VALUES (%s,'cap.interviews_compatibility',true,'compatibility','setup_protect',false,%s::jsonb,now())
            ON CONFLICT (tenant_id, capability_key) DO UPDATE SET
              granted = true, grant_mode='compatibility', updated_at=now()
            """,
            (tenant_id, json.dumps({"protected": True})),
        )

    cur.execute(
        """
        INSERT INTO tc_tenant_config_versions (
          tenant_id, version_number, status, catalog_version, config_json,
          before_json, after_json, diff_json, idempotency_key, rollback_of_version,
          published_by, published_at
        )
        SELECT %s,
               COALESCE((SELECT max(version_number) FROM tc_tenant_config_versions WHERE tenant_id=%s), 0) + 1,
               'published', %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s,
               COALESCE((SELECT max(version_number) FROM tc_tenant_config_versions WHERE tenant_id=%s), 0),
               %s, now()
        WHERE NOT EXISTS (
          SELECT 1 FROM tc_tenant_config_versions WHERE tenant_id=%s AND idempotency_key=%s
        )
        RETURNING version_number
        """,
        (
            tenant_id,
            tenant_id,
            catalog.CATALOG_VERSION,
            json.dumps(after),
            json.dumps(before),
            json.dumps(after),
            json.dumps(diff),
            idem,
            tenant_id,
            actor,
            tenant_id,
            idem,
        ),
    )
    version_row = cur.fetchone()
    version_number = int(version_row["version_number"] if isinstance(version_row, dict) else version_row[0]) if version_row else None

    if draft_id:
        cur.execute(
            "UPDATE tc_configuration_drafts SET status='published', updated_at=now() WHERE draft_id=%s",
            (draft_id,),
        )

    _persist_audit_outbox(
        cur,
        tenant_id=tenant_id,
        company_code=company,
        event_type="setup_modules_dual_write",
        actor=actor,
        idempotency_key=idem,
        before=before,
        after=after,
        detail={"diff": diff, "version_number": version_number, "draft_id": draft_id, "validation": validation},
    )
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "modules": after_modules,
        "protected_retained": validation["protected_retained"],
        "version_number": version_number,
        "draft_id": draft_id,
        "diff": diff,
        "rollback_target": (version_number - 1) if version_number and version_number > 1 else None,
        "validation": validation,
    }


def rollback_config_version(cur: Any, *, company_code: str, target_version: int, actor: str) -> dict[str, Any]:
    """Create a new published version restoring a prior config snapshot (control-plane only)."""
    company = company_code.upper()
    tenant_id = get_tenant_id(cur, company)
    if not tenant_id:
        return {"ok": False, "error": "tenant_not_imported"}
    cur.execute(
        """
        SELECT version_number, after_json
        FROM tc_tenant_config_versions
        WHERE tenant_id=%s AND version_number=%s
        LIMIT 1
        """,
        (tenant_id, target_version),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "version_not_found"}
    snapshot = row["after_json"] if isinstance(row, dict) else row[1]
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    modules_list = list((snapshot or {}).get("modules") or (snapshot or {}).get("modules_enabled") or [])
    if not modules_list:
        return {"ok": False, "error": "version_snapshot_missing_modules"}
    result = dual_write_module_save(
        cur,
        company_code=company,
        requested_modules=modules_list,
        currently_enabled=list(canonical_modules_for_tenant(cur, company)),
        actor=actor,
        idempotency_key=_stable_idempotency("rollback", company, target_version, actor, uuid4().hex),
    )
    if result.get("ok") and result.get("version_number"):
        cur.execute(
            """
            UPDATE tc_tenant_config_versions
            SET status='published', rollback_of_version=%s
            WHERE tenant_id=%s AND version_number=%s
            """,
            (target_version, tenant_id, result["version_number"]),
        )
        cur.execute(
            """
            INSERT INTO tc_activation_events (
              tenant_id, event_type, from_state, to_state, actor, detail
            ) VALUES (%s,'config_rollback',%s,%s,%s,%s::jsonb)
            """,
            (
                tenant_id,
                str(target_version),
                str(result["version_number"]),
                actor,
                json.dumps({"restored_modules": modules_list}),
            ),
        )
    return result


def classify_orphan_settings(cur: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("company_code") or "").upper()
        settings = row.get("settings") or {}
        updated_at = str(row.get("updated_at") or "")
        if code.startswith("ZZSEED"):
            classification = "test_seed"
            ownership = "ops_seed_harness"
            origin = "Deterministic ZZSEED* company_settings residue from seed/provision tests."
        elif code.startswith(("ASST", "RANK", "OFFER")):
            classification = "test_seed"
            ownership = "feature_canary_harness"
            origin = "Named production canary/test company_code leftover after companies row cleanup."
        elif code.startswith("TENANTREAD"):
            classification = "test_seed"
            ownership = "tenant_read_hardening_suite"
            origin = "Tenant read isolation harness company_settings without companies row."
        else:
            classification = "unknown"
            ownership = "unassigned"
            origin = "Orphan company_settings with no matching companies row; retain pending Wave 2 cleanup."
        item = {
            "record_table": "company_settings",
            "record_key": code,
            "company_code": code,
            "classification": classification,
            "ownership": ownership,
            "origin_hypothesis": origin,
            "evidence": {
                "settings_empty": settings == {} or settings == "{}",
                "updated_at": updated_at,
                "settings": settings,
            },
            "action_plan": "retain_do_not_delete",
        }
        cur.execute(
            """
            INSERT INTO tc_orphan_classifications (
              record_table, record_key, company_code, classification, ownership,
              origin_hypothesis, evidence, action_plan
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (record_table, record_key) DO UPDATE SET
              classification = EXCLUDED.classification,
              ownership = EXCLUDED.ownership,
              origin_hypothesis = EXCLUDED.origin_hypothesis,
              evidence = EXCLUDED.evidence,
              action_plan = EXCLUDED.action_plan
            """,
            (
                item["record_table"],
                item["record_key"],
                item["company_code"],
                item["classification"],
                item["ownership"],
                item["origin_hypothesis"],
                json.dumps(item["evidence"]),
                item["action_plan"],
            ),
        )
        classified.append(item)
    return classified


def _persist_audit_outbox(
    cur: Any,
    *,
    tenant_id: str | None,
    company_code: str,
    event_type: str,
    actor: str,
    idempotency_key: str,
    before: dict[str, Any],
    after: dict[str, Any],
    detail: dict[str, Any],
) -> None:
    diff = _json_diff(before, after)
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


def compare_legacy_callable(
    *,
    company_code: str,
    module_key: str,
    legacy_checker: Callable[[str, str], bool],
    canonical_modules: set[str],
    surface: str,
) -> dict[str, Any]:
    legacy = bool(legacy_checker(company_code, module_key))
    canonical = modules.normalize_module_key(module_key) in canonical_modules
    return shadow_module_decision(
        company_code=company_code,
        module_key=module_key,
        legacy_enabled=legacy,
        canonical_enabled=canonical,
        surface=surface,
        subject_key=f"{surface}:{module_key}",
    )
