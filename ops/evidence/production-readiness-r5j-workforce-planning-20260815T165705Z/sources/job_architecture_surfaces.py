#!/usr/bin/env python3
"""R5D Job Architecture product surfaces — thin composition over frozen C1.

HTTP and HR Web are adapters. No second catalog. No salary bands.
Career edges are not eligibility. Recruiting Job ≠ JA Job Profile.
"""
from __future__ import annotations

from typing import Any

import job_architecture_c1 as c1

PHASE = "job_architecture_surfaces_r5d"
CONTRACT_VERSION = "job_architecture_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5D_JOB_ARCHITECTURE_SURFACE_FULL_PASS"
PLATFORM_CAPABILITY_KEY = "job_architecture"


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "platform_capability_key": PLATFORM_CAPABILITY_KEY,
        "canonical_authority": ("job_architecture_c1",),
        "not_separate_customer_sku": True,
        "commercial_sku": False,
        "salary_bands_out_of_c1": True,
        "career_edges_are_not_eligibility": True,
        "no_employee_eligibility_scoring": True,
        "no_fuzzy_ai_migration": True,
        "legacy_raw_preserved": True,
        "recruiting_job_is_not_ja_profile": True,
        "talent_critical_role_is_not_ja_catalog": True,
        "org_position_is_not_reusable_job_profile": True,
        "no_shadow_employee_truth": True,
        "no_shadow_position_truth": True,
        "talent_optional": True,
        "recruiting_optional": True,
        "learning_required": False,
        "performance_required": False,
        "comp_planning_required": False,
        "workforce_planning_required": False,
        "company_code": c1.company_code_norm(company_code) if company_code else None,
    }


def ensure_schema(cur: Any) -> None:
    c1.ensure_job_architecture_c1_schema(cur)


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync job architecture entitlement",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c1.company_code_norm(company_code)
    if enabled:
        result = c1.enable_company_job_architecture(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        result = c1.disable_company_job_architecture(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    return {
        "ok": bool(result.get("ok")),
        "company_code": company,
        "enabled": bool(enabled),
        "history_preserved": True,
        "result": result,
        **honesty_payload(company_code=company),
    }


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


def workspace_summary(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    gate = c1.runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "resource_state": "unavailable", **honesty_payload(company_code=company_code)}
    company = gate["company_code"]
    enabled = c1.module_enabled_for_company(cur, company)
    if not enabled:
        return {
            "ok": True,
            "company_code": company,
            "enabled": False,
            "resource_state": "unavailable",
            "counts": None,
            "active_version_status": None,
            "legacy_text_still_works": True,
            "master_career_score": None,
            **honesty_payload(company_code=company),
        }
    catalog = c1.list_catalog(cur, company_code=company)
    cur.execute(
        """
        SELECT match_kind, COUNT(*) AS n
          FROM ja_legacy_mapping
         WHERE company_code=%s
         GROUP BY match_kind
        """,
        (company,),
    )
    mapping_counts = {str(r["match_kind"]): int(r["n"] or 0) for r in (cur.fetchall() or [])}
    cur.execute(
        "SELECT COUNT(*) AS n FROM ja_employment_assignment WHERE company_code=%s AND effective_end IS NULL",
        (company,),
    )
    assigned = int((_row(cur.fetchone()).get("n") or 0))
    profiles = catalog.get("profiles") or []
    published = sum(1 for p in profiles if str(p.get("status")) == "published")
    return {
        "ok": True,
        "company_code": company,
        "enabled": True,
        "resource_state": "ok" if profiles or mapping_counts else "empty",
        "counts": {
            "families": len(catalog.get("families") or []),
            "functions": len(catalog.get("functions") or []),
            "profiles": len(profiles),
            "published_profiles": published,
            "grades": len(catalog.get("grades") or []),
            "levels": len(catalog.get("levels") or []),
            "career_edges": len(catalog.get("career_edges") or []),
            "active_assignments": assigned,
            "mapped": mapping_counts.get("deterministic_unique", 0) + mapping_counts.get("manual", 0),
            "unmapped": mapping_counts.get("unmapped_none", 0),
            "ambiguous": mapping_counts.get("unmapped_ambiguous", 0),
        },
        "mapping_counts": mapping_counts,
        "master_career_score": None,
        **honesty_payload(company_code=company),
    }


def list_catalog(cur: Any, *, company_code: str) -> dict[str, Any]:
    result = c1.list_catalog(cur, company_code=company_code)
    if result.get("ok") is False:
        return {**result, "resource_state": "unavailable"}
    if not result.get("enabled"):
        return {**result, "resource_state": "unavailable", "counts_are_not_empty": True}
    return {**result, "resource_state": "ok", **honesty_payload(company_code=company_code)}


def list_mappings(
    cur: Any,
    *,
    company_code: str,
    match_kind: str | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    gate = c1.runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "resource_state": "unavailable"}
    company = gate["company_code"]
    if not c1.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "mappings": None,
            "resource_state": "unavailable",
            "legacy_raw_preserved": True,
            **honesty_payload(company_code=company),
        }
    params: list[Any] = [company]
    extra = ""
    if match_kind:
        extra = " AND match_kind=%s"
        params.append(match_kind)
    cur.execute(
        f"""
        SELECT * FROM ja_legacy_mapping
         WHERE company_code=%s{extra}
         ORDER BY updated_at DESC
        """,
        params,
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "mappings": rows,
        "resource_state": "empty" if not rows else "ok",
        "raw_preserved": True,
        "fuzzy_ai_used": False,
        **honesty_payload(company_code=company),
    }


def resolve_legacy_mapping(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    mapping_id: str,
    mapped_entity_type: str,
    mapped_entity_id: str,
    reason: str = "human resolve ambiguous mapping",
) -> dict[str, Any]:
    """Authorized human resolution. Never auto-promotes fuzzy/AI matches."""
    ent = c1._require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    kind = str(mapped_entity_type or "").strip()
    if kind not in {"job_profile", "grade", "level"}:
        return {"ok": False, "error": "invalid_mapped_entity_type"}
    cur.execute(
        "SELECT * FROM ja_legacy_mapping WHERE company_code=%s AND mapping_id=%s",
        (company, mapping_id),
    )
    existing = cur.fetchone()
    if not existing:
        return {"ok": False, "error": "mapping_not_found"}
    existing = dict(existing)
    raw_value = existing.get("raw_value")
    cur.execute(
        """
        UPDATE ja_legacy_mapping
           SET match_kind='manual',
               mapped_entity_type=%s,
               mapped_entity_id=%s,
               provenance = provenance || jsonb_build_object(
                 'resolved_by_human', true,
                 'raw_value_preserved', %s::text,
                 'reason', %s::text
               ),
               updated_at=now()
         WHERE mapping_id=%s AND company_code=%s
        RETURNING *
        """,
        (kind, mapped_entity_id, raw_value, str(reason)[:500], mapping_id, company),
    )
    row = dict(cur.fetchone())
    c1._audit(
        cur,
        company=company,
        actor=actor_phone,
        action="resolve_legacy_mapping",
        entity_type="legacy_mapping",
        entity_id=str(mapping_id),
        detail={"reason": reason, "raw_preserved": True, "match_kind": "manual"},
    )
    return {
        "ok": True,
        "mapping": row,
        "raw_preserved": True,
        "raw_value": raw_value,
        "fuzzy_ai_used": False,
        "auto_canonical": False,
    }


def list_assignments(cur: Any, *, company_code: str, employee_key: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    gate = c1.runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "resource_state": "unavailable"}
    company = gate["company_code"]
    params: list[Any] = [company]
    extra = ""
    if employee_key:
        extra = " AND employee_key=%s"
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT * FROM ja_employment_assignment
         WHERE company_code=%s{extra}
         ORDER BY effective_start DESC
        """,
        params,
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "assignments": rows,
        "does_not_mutate_employment_status": True,
        "does_not_change_salary": True,
        **honesty_payload(company_code=company),
    }


def list_history(cur: Any, *, company_code: str, entity_type: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    gate = c1.runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "resource_state": "unavailable"}
    company = gate["company_code"]
    params: list[Any] = [company]
    extra = ""
    if entity_type:
        extra = " AND entity_type=%s"
        params.append(entity_type)
    cur.execute(
        f"""
        SELECT * FROM ja_audit_events
         WHERE company_code=%s{extra}
         ORDER BY created_at DESC
         LIMIT 200
        """,
        params,
    )
    return {
        "ok": True,
        "events": [_row(r) for r in (cur.fetchall() or [])],
        **honesty_payload(company_code=company),
    }


def list_downstream_refs(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    gate = c1.runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "resource_state": "unavailable"}
    company = gate["company_code"]
    cur.execute(
        "SELECT * FROM ja_optional_external_ref WHERE company_code=%s ORDER BY created_at DESC",
        (company,),
    )
    refs = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "refs": refs,
        "talent_judgment_not_acquired": True,
        "recruiting_lifecycle_not_replaced": True,
        **honesty_payload(company_code=company),
    }


def refuse_hard_delete(*, entity_type: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "destructive_delete_forbidden",
        "entity_type": entity_type,
        "use": "retire_or_supersede",
        "history_must_remain_reconstructable": True,
    }
