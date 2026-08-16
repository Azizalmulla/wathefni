"""Setup Console — Wave 6 HCM Expansion company policies.

One coherent Wave 6 Setup area with module-specific cards.
Env flags remain kill-switches / allowlists only.
C1: job_architecture (platform capability, not separate customer SKU).
"""
from __future__ import annotations

from typing import Any

import job_architecture_c1 as ja

PHASE = "setup_console_wave6"
CONTRACT_VERSION = "wave6_hcm_expansion_policies_v1"
PASS_STAMP = "WAVE6_HCM_EXPANSION_CHARTER: APPROVED"

WAVE6_MODULE_KEYS = ("job_architecture",)

DEFAULTS: dict[str, dict[str, Any]] = {
    "job_architecture": {
        "enabled": False,
        "migration_mode": "non_destructive",
        "allow_optional_talent_ref": True,
        "allow_optional_recruiting_ref": True,
        "commercial_sku": False,
        "platform_capability": True,
    },
}

STATUS_LABELS = {
    "job_architecture": {"en": "Job Architecture", "ar": "هيكل الوظائف"},
    "wave6_area": {"en": "HCM Expansion (Wave 6)", "ar": "توسعة إدارة رأس المال البشري (الموجة 6)"},
}

ENV_FLAG_BY_MODULE = {
    "job_architecture": ("WATHEFNI_JOB_ARCHITECTURE_C1", "WATHEFNI_JOB_ARCHITECTURE_COMPANIES"),
}


def _company(code: str) -> str:
    return str(code or "").upper()


def status_label(module_key: str, *, lang: str = "en") -> str:
    pack = STATUS_LABELS.get(module_key) or {"en": module_key, "ar": module_key}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "setup_owns_wave6_policies": True,
        "env_only_ownership": False,
        "env_flags_are_kill_switches_only": True,
        "one_coherent_area_module_cards": True,
        "no_mega_form": True,
        "no_duplicate_settings_stores": True,
        "assistant_mutations_in_wave6": False,
        "full_pass_not_broad_rollout": True,
        "job_architecture_not_customer_sku": True,
        **{k: v for k, v in ja.honesty_payload().items() if k in {
            "salary_bands_out_of_c1",
            "no_fuzzy_ai_migration",
            "career_edges_are_not_eligibility",
            "recruiting_job_is_not_ja_profile",
            "org_position_is_not_reusable_job_profile",
            "talent_critical_role_is_not_ja_catalog",
        }},
    }


def get_all_wave6_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    ja.ensure_job_architecture_c1_schema(cur)
    modules: dict[str, Any] = {}
    for key in WAVE6_MODULE_KEYS:
        modules[key] = get_wave6_module_policy(cur, company, key)
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "modules": modules,
        "honesty": honesty_payload(),
        "future_hard_contracts": ja.future_hard_contracts(),
        "surface_composition": ja.surface_composition_rules(),
    }


def get_wave6_module_policy(cur: Any, company_code: str, module_key: str) -> dict[str, Any]:
    company = _company(company_code)
    key = str(module_key or "").strip().lower()
    if key not in WAVE6_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave6_module", "module_key": key}
    defaults = dict(DEFAULTS[key])
    if key == "job_architecture":
        ja.ensure_job_architecture_c1_schema(cur)
        cur.execute("SELECT * FROM ja_company_settings WHERE company_code=%s", (company,))
        row = cur.fetchone()
        settings = dict(row) if row else {}
        policy = {
            **defaults,
            "enabled": bool(settings.get("enabled")),
            "migration_mode": settings.get("migration_mode") or "non_destructive",
            "allow_optional_talent_ref": bool(settings.get("allow_optional_talent_ref", True)),
            "allow_optional_recruiting_ref": bool(settings.get("allow_optional_recruiting_ref", True)),
        }
        gate = ja.runtime_gate_for_company(company)
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": gate,
            "platform_capability": True,
            "commercial_sku": False,
            "honesty": ja.honesty_payload(company_code=company),
        }
    return {"ok": False, "error": "unhandled_module", "module_key": key}


def patch_wave6_module_policy(
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
    key = str(module_key or "").strip().lower()
    if key not in WAVE6_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave6_module", "module_key": key}
    body = dict(payload or {})
    if key == "job_architecture":
        enabled = body.get("enabled")
        if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
            result = ja.enable_company_job_architecture(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
            result = ja.disable_company_job_architecture(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        else:
            # policy-only tweaks without toggle
            ja.ensure_job_architecture_c1_schema(cur)
            cur.execute(
                """
                INSERT INTO ja_company_settings (company_code, enabled, updated_by_phone, updated_at)
                VALUES (%s,false,%s,now())
                ON CONFLICT (company_code) DO UPDATE SET
                  allow_optional_talent_ref=COALESCE(%s, ja_company_settings.allow_optional_talent_ref),
                  allow_optional_recruiting_ref=COALESCE(%s, ja_company_settings.allow_optional_recruiting_ref),
                  updated_by_phone=%s, updated_at=now()
                RETURNING *
                """,
                (
                    company,
                    "".join(ch for ch in str(actor_phone or "") if ch.isdigit()),
                    body.get("allow_optional_talent_ref"),
                    body.get("allow_optional_recruiting_ref"),
                    "".join(ch for ch in str(actor_phone or "") if ch.isdigit()),
                ),
            )
            result = {"ok": True, "settings": dict(cur.fetchone())}
        return {
            "ok": bool(result.get("ok")),
            "module_key": key,
            "result": result,
            "policy": get_wave6_module_policy(cur, company, key),
        }
    return {"ok": False, "error": "unhandled_module"}
