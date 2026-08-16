"""Setup Console — Wave 5 HR Intelligence company policies.

Owns customer Intelligence policy over frozen C1 Registry + C6 surfaces.
Does not create a second evaluator, KPI catalog, or analytics authority.
Environment flags remain kill switches / staged rollout only.
"""
from __future__ import annotations

import json
from typing import Any

import hr_intelligence_registry_c1 as c1
import hr_intelligence_surfaces_c6 as c6
import setup_console_effective_state as eff

PHASE = "setup_console_wave5"
CONTRACT_VERSION = "wave5_hr_intelligence_policies_v1"
PASS_STAMP = "WAVE5_HR_INTELLIGENCE_CHARTER: APPROVED"
COMMERCIAL_MODULE_KEY = "analytics"
WAVE5_MODULE_KEYS = ("analytics",)

DEFAULTS = {
    "enabled": False,
    "min_cohort_n": c1.DEFAULT_MIN_COHORT_N,
    "fiscal_year_start_month": 1,
    "nationality_dimension_enabled": False,
    "other_sensitive_demographics_enabled": False,
    "manager_analytics_enabled": False,
    "export_person_level_requires_permission": True,
    "commercial_sku": True,
    "platform_capability": False,
}


def _company(code: str) -> str:
    return c1.company_code_norm(code)


def honesty_payload() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "setup_owns_wave5_policies": True,
        "env_only_ownership": False,
        "env_flags_are_kill_switches_only": True,
        "no_new_analytics_authority": True,
        "uses_frozen_c1_evaluator": True,
        "min_cohort_n_upward_only": True,
        "demographics_off_by_default": True,
        "planned_headcount_never_enters_actual": True,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "job_architecture_not_required": True,
        **c1.honesty_payload(),
        **eff.honesty_payload(),
    }


def _sync_catalog(cur: Any, company: str, *, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,'analytics',%s,'setup_console_wave5','{}'::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET
          enabled=EXCLUDED.enabled,
          source=EXCLUDED.source,
          updated_at=now()
        """,
        (company, bool(enabled)),
    )


def _publications(cur: Any, company: str) -> list[dict[str, Any]]:
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        """
        SELECT p.semantic_key, p.effective_version, p.published, d.name_en, d.name_ar, d.status
          FROM hr_kpi_company_publications p
          JOIN hr_kpi_definitions d ON d.kpi_definition_id = p.kpi_definition_id
         WHERE p.company_code=%s
         ORDER BY p.semantic_key
        """,
        (company,),
    )
    rows = []
    for raw in cur.fetchall() or []:
        row = dict(raw) if isinstance(raw, dict) else {
            "semantic_key": raw[0],
            "effective_version": raw[1],
            "published": raw[2],
            "name_en": raw[3],
            "name_ar": raw[4],
            "status": raw[5],
        }
        rows.append(row)
    return rows


def get_wave5_module_policy(cur: Any, company_code: str, module_key: str = "analytics") -> dict[str, Any]:
    company = _company(company_code)
    key = str(module_key or "analytics").strip().lower()
    if key not in {"analytics", "intelligence", "hr_intelligence", "wave5"}:
        return {"ok": False, "error": "unknown_wave5_module", "allowed": list(WAVE5_MODULE_KEYS)}
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    c6.ensure_hr_intelligence_surfaces_c6_schema(cur)
    cur.execute("SELECT * FROM hr_intelligence_c1_company_settings WHERE company_code=%s", (company,))
    raw_c1 = cur.fetchone()
    c1_row = dict(raw_c1) if raw_c1 and not isinstance(raw_c1, tuple) else {}
    cur.execute("SELECT * FROM hr_intelligence_c6_company_settings WHERE company_code=%s", (company,))
    raw_c6 = cur.fetchone()
    c6_row = dict(raw_c6) if raw_c6 and not isinstance(raw_c6, tuple) else {}
    policy = {
        **DEFAULTS,
        "enabled": bool(c1_row.get("enabled")),
        "min_cohort_n": int(c1_row.get("min_cohort_n") or c1.DEFAULT_MIN_COHORT_N),
        "fiscal_year_start_month": int(c1_row.get("fiscal_year_start_month") or 1),
        "nationality_dimension_enabled": bool(c1_row.get("nationality_dimension_enabled")),
        "other_sensitive_demographics_enabled": bool(c1_row.get("other_sensitive_demographics_enabled")),
        "manager_analytics_enabled": bool(c6_row.get("manager_analytics_enabled")),
        "export_person_level_requires_permission": bool(
            c6_row.get("export_person_level_requires_permission", True)
        ),
        "surfaces_enabled": bool(c6_row.get("enabled")),
    }
    payload = {
        "ok": True,
        "module_key": "analytics",
        "label_en": "HR Intelligence",
        "label_ar": "ذكاء الموارد البشرية",
        "policy": policy,
        "publications": _publications(cur, company),
        "runtime_gate": c1.runtime_gate_for_company(company),
        "surfaces_runtime_gate": c6.runtime_gate_for_company(company),
        "platform_capability": False,
        "commercial_sku": True,
        "honesty": honesty_payload(),
        "headcount_policy": dict(c1.HEADCOUNT_POLICY),
    }
    return eff.annotate_with_effective_state("analytics", payload)


def get_all_wave5_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    modules = {"analytics": get_wave5_module_policy(cur, company, "analytics")}
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "modules": modules,
        "honesty": honesty_payload(),
        "customer_enableable": True,
        "customer_visible": True,
    }


def _set_c1_customer_fields(
    cur: Any,
    *,
    company: str,
    actor_phone: str,
    reason: str,
    body: dict[str, Any],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute("SELECT * FROM hr_intelligence_c1_company_settings WHERE company_code=%s", (company,))
    existing = dict(cur.fetchone() or {})
    if not existing:
        return actions
    fields: list[str] = []
    params: list[Any] = []
    if "fiscal_year_start_month" in body:
        month = int(body.get("fiscal_year_start_month") or 1)
        if month < 1 or month > 12:
            raise ValueError("fiscal_year_start_month_invalid")
        fields.append("fiscal_year_start_month=%s")
        params.append(month)
        actions.append({"action": "set_fiscal_year_start_month", "from": existing.get("fiscal_year_start_month"), "to": month})
    if "nationality_dimension_enabled" in body:
        val = bool(body.get("nationality_dimension_enabled"))
        fields.append("nationality_dimension_enabled=%s")
        params.append(val)
        actions.append({"action": "set_nationality_dimension", "from": existing.get("nationality_dimension_enabled"), "to": val})
    if "other_sensitive_demographics_enabled" in body:
        val = bool(body.get("other_sensitive_demographics_enabled"))
        fields.append("other_sensitive_demographics_enabled=%s")
        params.append(val)
        actions.append({"action": "set_other_demographics", "from": existing.get("other_sensitive_demographics_enabled"), "to": val})
    if not fields:
        return actions
    params.append(company)
    cur.execute(
        f"UPDATE hr_intelligence_c1_company_settings SET {', '.join(fields)}, updated_at=now() WHERE company_code=%s",
        tuple(params),
    )
    c1._audit(
        cur,
        company_code=company,
        action="setup_wave5_policy_updated",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"actions": actions},
    )
    return actions


def patch_wave5_module_policy(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    actor_phone: str,
    reason: str,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    key = str(module_key or "analytics").strip().lower()
    if key.startswith("wave5_"):
        key = key[len("wave5_") :]
    if key not in {"analytics", "intelligence", "hr_intelligence", ""}:
        return {"ok": False, "error": "unknown_wave5_module", "allowed": list(WAVE5_MODULE_KEYS)}
    body = dict(payload or {})
    if "required" in body and isinstance(body["required"], dict):
        body = {**body["required"], **{k: v for k, v in body.items() if k != "required"}}
    if "optional" in body and isinstance(body["optional"], dict):
        body = {**body, **body["optional"]}
    actions: list[dict[str, Any]] = []

    enabled = body.get("enabled")
    if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
        result = c1.enable_company_hr_intelligence(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            reason=reason,
            min_cohort_n=int(body.get("min_cohort_n") or c1.DEFAULT_MIN_COHORT_N),
        )
        if not result.get("ok"):
            return result
        surf = c6.enable_company_hr_intelligence_surfaces(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            reason=reason,
            manager_analytics_enabled=bool(body.get("manager_analytics_enabled", False)),
            export_person_level_requires_permission=bool(
                body.get("export_person_level_requires_permission", True)
            ),
        )
        if not surf.get("ok") and str(surf.get("error") or "") not in {
            "hr_intelligence_surfaces_c6_off",
            "hr_intelligence_surfaces_company_not_allowlisted",
            "c1_registry_required",
        }:
            return surf
        _sync_catalog(cur, company, enabled=True)
        actions.append({"action": "enable_hr_intelligence", "surfaces": bool(surf.get("ok"))})
    elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
        result = c1.disable_company_hr_intelligence(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        if not result.get("ok"):
            return result
        _sync_catalog(cur, company, enabled=False)
        actions.append({"action": "disable_hr_intelligence", "preserves_history": True})

    if "min_cohort_n" in body and enabled is not False:
        cohort = c1.set_min_cohort_n(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            min_cohort_n=int(body.get("min_cohort_n") or c1.DEFAULT_MIN_COHORT_N),
            reason=reason,
        )
        if not cohort.get("ok"):
            return cohort
        actions.append({"action": "set_min_cohort_n"})

    try:
        actions.extend(
            _set_c1_customer_fields(cur, company=company, actor_phone=actor_phone, reason=reason, body=body)
        )
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    if any(k in body for k in ("manager_analytics_enabled", "export_person_level_requires_permission")):
        gate = c6.runtime_gate_for_company(company)
        if gate.get("ok"):
            c1_ent = c1._entitled(cur, company)
            if c1_ent.get("ok"):
                surf = c6.enable_company_hr_intelligence_surfaces(
                    cur,
                    company_code=company,
                    actor_phone=actor_phone,
                    reason=reason,
                    manager_analytics_enabled=bool(body.get("manager_analytics_enabled", False)),
                    export_person_level_requires_permission=bool(
                        body.get("export_person_level_requires_permission", True)
                    ),
                )
                if not surf.get("ok"):
                    return surf
                actions.append({"action": "update_surfaces_policy"})

    publish_key = str(body.get("publish_semantic_key") or "").strip()
    if publish_key:
        pub = c1.publish_kpi_for_company(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            semantic_key=publish_key,
            reason=reason,
        )
        if not pub.get("ok"):
            return pub
        actions.append({"action": "publish_kpi", "semantic_key": publish_key})

    policy = get_wave5_module_policy(cur, company, "analytics")
    return {"ok": True, "actions": actions, **policy}
