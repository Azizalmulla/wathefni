"""Setup Console — Wave 6 HCM Expansion company policies.

One coherent Wave 6 Setup area with module-specific cards.
Env flags remain kill-switches / allowlists only.
C1: job_architecture (platform capability)
C2: learning (commercial module)
C3: benefits (commercial module)
C4: employee_relations (commercial module)
C5: engagement (commercial module)
C6: comp_planning (commercial module)
C7: workforce_planning (commercial module)
"""
from __future__ import annotations

from typing import Any

import benefits_administration_c3 as bn
import compensation_planning_c6 as cp
import employee_relations_c4 as er
import engagement_c5 as eg
import job_architecture_c1 as ja
import learning_development_c2 as ld
import workforce_planning_c7 as wfp

PHASE = "setup_console_wave6"
CONTRACT_VERSION = "wave6_hcm_expansion_policies_v7"
PASS_STAMP = "WAVE6_HCM_EXPANSION_CHARTER: APPROVED"

WAVE6_MODULE_KEYS = (
    "job_architecture",
    "learning",
    "benefits",
    "employee_relations",
    "engagement",
    "comp_planning",
    "workforce_planning",
)

DEFAULTS: dict[str, dict[str, Any]] = {
    "job_architecture": {
        "enabled": False,
        "migration_mode": "non_destructive",
        "allow_optional_talent_ref": True,
        "allow_optional_recruiting_ref": True,
        "commercial_sku": False,
        "platform_capability": True,
    },
    "learning": {
        "enabled": False,
        "employee_requests_enabled": True,
        "manager_assign_enabled": True,
        "expiry_warning_days": 30,
        "evidence_required_for_completion": True,
        "ja_applicability_enabled": False,
        "development_fulfillment_enabled": True,
        "commercial_sku": True,
    },
    "benefits": {
        "enabled": False,
        "employee_self_service_enabled": True,
        "manager_sees_private_detail": False,
        "payroll_handoff_enabled": False,
        "ja_eligibility_enabled": False,
        "require_documents_when_configured": True,
        "commercial_sku": True,
    },
    "employee_relations": {
        "enabled": False,
        "employee_submission_enabled": True,
        "manager_referral_enabled": True,
        "default_confidentiality": "standard_er",
        "sla_triage_days": 3,
        "commercial_sku": True,
    },
    "engagement": {
        "enabled": False,
        "min_responses": 5,
        "default_privacy_mode": "anonymous",
        "manager_results_enabled": True,
        "free_text_enabled": True,
        "employee_survey_enabled": True,
        "action_plans_enabled": True,
        "commercial_sku": True,
    },
    "comp_planning": {
        "enabled": False,
        "default_currency": "KWD",
        "budget_overrun_mode": "hard_block",
        "sod_required": True,
        "performance_input_enabled": False,
        "talent_input_enabled": False,
        "payroll_handoff_enabled": False,
        "commercial_sku": True,
    },
    "workforce_planning": {
        "enabled": False,
        "default_currency": "KWD",
        "default_horizon": "quarterly",
        "recruiting_handoff_enabled": False,
        "comp_assumptions_enabled": False,
        "talent_skills_enabled": False,
        "commercial_sku": True,
    },
}

STATUS_LABELS = {
    "job_architecture": {"en": "Job Architecture", "ar": "هيكل الوظائف"},
    "learning": {"en": "Learning & Development", "ar": "التعلم والتطوير"},
    "benefits": {"en": "Benefits", "ar": "المزايا"},
    "employee_relations": {"en": "Employee Relations", "ar": "علاقات الموظفين"},
    "engagement": {"en": "Engagement", "ar": "المشاركة والارتباط"},
    "comp_planning": {"en": "Compensation Planning", "ar": "تخطيط التعويضات"},
    "workforce_planning": {"en": "Workforce Planning", "ar": "تخطيط القوى العاملة"},
    "wave6_area": {"en": "HCM Expansion (Wave 6)", "ar": "توسعة إدارة رأس المال البشري (الموجة 6)"},
}

ENV_FLAG_BY_MODULE = {
    "job_architecture": ("WATHEFNI_JOB_ARCHITECTURE_C1", "WATHEFNI_JOB_ARCHITECTURE_COMPANIES"),
    "learning": ("WATHEFNI_LEARNING_C2", "WATHEFNI_LEARNING_COMPANIES"),
    "benefits": ("WATHEFNI_BENEFITS_C3", "WATHEFNI_BENEFITS_COMPANIES"),
    "employee_relations": ("WATHEFNI_EMPLOYEE_RELATIONS_C4", "WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"),
    "engagement": ("WATHEFNI_ENGAGEMENT_C5", "WATHEFNI_ENGAGEMENT_COMPANIES"),
    "comp_planning": ("WATHEFNI_COMP_PLANNING_C6", "WATHEFNI_COMP_PLANNING_COMPANIES"),
    "workforce_planning": ("WATHEFNI_WORKFORCE_PLANNING_C7", "WATHEFNI_WORKFORCE_PLANNING_COMPANIES"),
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
        "customer_enableable": True,
        "customer_visible_in_setup": True,
        "job_architecture_customer_enableable": True,
        "learning_customer_enableable": True,
        "benefits_customer_enableable": True,
        "employee_relations_customer_enableable": True,
        "engagement_customer_enableable": False,
        "comp_planning_customer_enableable": False,
        "workforce_planning_customer_enableable": False,
        "remaining_wave6_not_customer_enableable": True,
        "domain_full_pass_is_not_customer_enableable": True,
        "stored_enabled_does_not_imply_usable": True,
        "one_coherent_area_module_cards": True,
        "no_mega_form": True,
        "no_duplicate_settings_stores": True,
        "assistant_mutations_in_wave6": False,
        "full_pass_not_broad_rollout": True,
        "job_architecture_not_customer_sku": True,
        "learning_does_not_duplicate_c3": True,
        "benefits_claims_out": True,
        "benefits_works_payroll_off": True,
        "er_case_level_need_to_know": True,
        "er_ordinary_hr_not_er": True,
        "er_manager_not_er": True,
        "engagement_recognition_out": True,
        "engagement_anonymity_fail_closed": True,
        "comp_planning_ja_hard": True,
        "comp_planning_not_payroll": True,
        "workforce_planning_ja_hard": True,
        "workforce_planning_not_actual_headcount": True,
        **{k: v for k, v in ja.honesty_payload().items() if k in {
            "salary_bands_out_of_c1",
            "no_fuzzy_ai_migration",
            "career_edges_are_not_eligibility",
            "recruiting_job_is_not_ja_profile",
            "org_position_is_not_reusable_job_profile",
            "talent_critical_role_is_not_ja_catalog",
        }},
        **{k: v for k, v in ld.honesty_payload().items() if k in {
            "does_not_duplicate_c3_development",
            "completion_does_not_silently_close_development_action",
            "works_performance_talent_off",
            "ja_optional",
        }},
        **{k: v for k, v in bn.honesty_payload().items() if k in {
            "claims_adjudication_out",
            "contribution_not_payroll_deduction",
            "works_payroll_off",
            "manager_fail_closed_on_private_detail",
            "no_invented_statutory_kuwait_policy",
        }},
        **{k: v for k, v in er.honesty_payload().items() if k in {
            "case_level_need_to_know",
            "ordinary_hr_not_er",
            "manager_not_er",
            "outcome_not_employment_mutation",
            "wave5_excludes_sensitive_free_text",
        }},
        **{k: v for k, v in eg.honesty_payload().items() if k in {
            "recognition_out_of_mvp",
            "min_responses_default_5",
            "threshold_upward_only",
            "anonymous_no_respondent_answer_map",
            "below_threshold_fail_closed",
        }},
        **{k: v for k, v in cp.honesty_payload().items() if k in {
            "ja_is_hard",
            "not_payroll",
            "finalized_not_applied",
            "performance_optional",
            "talent_optional",
        }},
        **{k: v for k, v in wfp.honesty_payload().items() if k in {
            "ja_is_hard",
            "planned_headcount_never_enters_actual_wave5",
            "recruiting_optional",
            "comp_planning_optional",
            "approved_ne_execution",
            "no_ai_forecast_authority",
        }},
    }


def get_all_wave6_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    ja.ensure_job_architecture_c1_schema(cur)
    ld.ensure_learning_development_c2_schema(cur)
    bn.ensure_benefits_administration_c3_schema(cur)
    er.ensure_employee_relations_c4_schema(cur)
    eg.ensure_engagement_c5_schema(cur)
    cp.ensure_compensation_planning_c6_schema(cur)
    wfp.ensure_workforce_planning_c7_schema(cur)
    modules: dict[str, Any] = {}
    for key in WAVE6_MODULE_KEYS:
        modules[key] = get_wave6_module_policy(cur, company, key)
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "modules": modules,
        "honesty": honesty_payload(),
        "future_hard_contracts": ja.future_hard_contracts(),
        "surface_composition": {
            "job_architecture": ja.surface_composition_rules(),
            "learning": ld.surface_composition_rules(),
            "benefits": bn.surface_composition_rules(),
            "employee_relations": er.surface_composition_rules(),
            "engagement": eg.surface_composition_rules(),
            "comp_planning": cp.surface_composition_rules(),
            "workforce_planning": wfp.surface_composition_rules(),
        },
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
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": ja.runtime_gate_for_company(company),
            "platform_capability": True,
            "commercial_sku": False,
            "honesty": ja.honesty_payload(company_code=company),
        }
    if key == "learning":
        ld.ensure_learning_development_c2_schema(cur)
        cur.execute("SELECT * FROM ld_company_settings WHERE company_code=%s", (company,))
        row = cur.fetchone()
        settings = dict(row) if row else {}
        policy = {
            **defaults,
            "enabled": bool(settings.get("enabled")),
            "employee_requests_enabled": bool(settings.get("employee_requests_enabled", True)),
            "manager_assign_enabled": bool(settings.get("manager_assign_enabled", True)),
            "expiry_warning_days": int(settings.get("expiry_warning_days") or 30),
            "evidence_required_for_completion": bool(settings.get("evidence_required_for_completion", True)),
            "ja_applicability_enabled": bool(settings.get("ja_applicability_enabled", False)),
            "development_fulfillment_enabled": bool(settings.get("development_fulfillment_enabled", True)),
        }
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": ld.runtime_gate_for_company(company),
            "platform_capability": False,
            "commercial_sku": True,
            "honesty": ld.honesty_payload(company_code=company),
        }
    if key == "benefits":
        bn.ensure_benefits_administration_c3_schema(cur)
        cur.execute("SELECT * FROM bn_company_settings WHERE company_code=%s", (company,))
        row = cur.fetchone()
        settings = dict(row) if row else {}
        policy = {
            **defaults,
            "enabled": bool(settings.get("enabled")),
            "employee_self_service_enabled": bool(settings.get("employee_self_service_enabled", True)),
            "manager_sees_private_detail": bool(settings.get("manager_sees_private_detail", False)),
            "payroll_handoff_enabled": bool(settings.get("payroll_handoff_enabled", False)),
            "ja_eligibility_enabled": bool(settings.get("ja_eligibility_enabled", False)),
            "require_documents_when_configured": bool(settings.get("require_documents_when_configured", True)),
        }
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": bn.runtime_gate_for_company(company),
            "platform_capability": False,
            "commercial_sku": True,
            "honesty": bn.honesty_payload(company_code=company),
        }
    if key == "employee_relations":
        er.ensure_employee_relations_c4_schema(cur)
        cur.execute("SELECT * FROM er_company_settings WHERE company_code=%s", (company,))
        row = cur.fetchone()
        settings = dict(row) if row else {}
        policy = {
            **defaults,
            "enabled": bool(settings.get("enabled")),
            "employee_submission_enabled": bool(settings.get("employee_submission_enabled", True)),
            "manager_referral_enabled": bool(settings.get("manager_referral_enabled", True)),
            "default_confidentiality": settings.get("default_confidentiality") or "standard_er",
            "sla_triage_days": int(settings.get("sla_triage_days") or 3),
        }
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": er.runtime_gate_for_company(company),
            "platform_capability": False,
            "commercial_sku": True,
            "honesty": er.honesty_payload(company_code=company),
        }
    if key == "engagement":
        eg.ensure_engagement_c5_schema(cur)
        cur.execute("SELECT * FROM eng_company_settings WHERE company_code=%s", (company,))
        row = cur.fetchone()
        settings = dict(row) if row else {}
        policy = {
            **defaults,
            "enabled": bool(settings.get("enabled")),
            "min_responses": int(settings.get("min_responses") or 5),
            "default_privacy_mode": settings.get("default_privacy_mode") or "anonymous",
            "manager_results_enabled": bool(settings.get("manager_results_enabled", True)),
            "free_text_enabled": bool(settings.get("free_text_enabled", True)),
            "employee_survey_enabled": bool(settings.get("employee_survey_enabled", True)),
            "action_plans_enabled": bool(settings.get("action_plans_enabled", True)),
        }
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": eg.runtime_gate_for_company(company),
            "platform_capability": False,
            "commercial_sku": True,
            "honesty": eg.honesty_payload(company_code=company),
        }
    if key == "comp_planning":
        cp.ensure_compensation_planning_c6_schema(cur)
        cur.execute("SELECT * FROM cp_company_settings WHERE company_code=%s", (company,))
        row = cur.fetchone()
        settings = dict(row) if row else {}
        policy = {
            **defaults,
            "enabled": bool(settings.get("enabled")),
            "default_currency": settings.get("default_currency") or "KWD",
            "budget_overrun_mode": settings.get("budget_overrun_mode") or "hard_block",
            "sod_required": bool(settings.get("sod_required", True)),
            "performance_input_enabled": bool(settings.get("performance_input_enabled", False)),
            "talent_input_enabled": bool(settings.get("talent_input_enabled", False)),
            "payroll_handoff_enabled": bool(settings.get("payroll_handoff_enabled", False)),
        }
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": cp.runtime_gate_for_company(company),
            "platform_capability": False,
            "commercial_sku": True,
            "honesty": cp.honesty_payload(company_code=company),
        }
    if key == "workforce_planning":
        wfp.ensure_workforce_planning_c7_schema(cur)
        cur.execute("SELECT * FROM wfp_company_settings WHERE company_code=%s", (company,))
        row = cur.fetchone()
        settings = dict(row) if row else {}
        policy = {
            **defaults,
            "enabled": bool(settings.get("enabled")),
            "default_currency": settings.get("default_currency") or "KWD",
            "default_horizon": settings.get("default_horizon") or "quarterly",
            "recruiting_handoff_enabled": bool(settings.get("recruiting_handoff_enabled", False)),
            "comp_assumptions_enabled": bool(settings.get("comp_assumptions_enabled", False)),
            "talent_skills_enabled": bool(settings.get("talent_skills_enabled", False)),
        }
        return {
            "ok": True,
            "module_key": key,
            "label_en": status_label(key, lang="en"),
            "label_ar": status_label(key, lang="ar"),
            "policy": policy,
            "runtime_gate": wfp.runtime_gate_for_company(company),
            "platform_capability": False,
            "commercial_sku": True,
            "honesty": wfp.honesty_payload(company_code=company),
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
    if key == "learning":
        enabled = body.get("enabled")
        policy_kwargs = {
            k: body[k]
            for k in (
                "employee_requests_enabled",
                "manager_assign_enabled",
                "expiry_warning_days",
                "evidence_required_for_completion",
                "ja_applicability_enabled",
                "development_fulfillment_enabled",
            )
            if k in body
        }
        if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
            result = ld.enable_company_learning(
                cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
            )
        elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
            result = ld.disable_company_learning(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        else:
            if not ld.module_enabled_for_company(cur, company):
                result = {"ok": False, "error": "learning_disabled_for_company"}
            else:
                result = ld.enable_company_learning(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
                )
        now_enabled = ld.module_enabled_for_company(cur, company)
        try:
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'learning', %s, 'wave6_setup', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key)
                DO UPDATE SET enabled=EXCLUDED.enabled, source='wave6_setup', updated_at=now()
                """,
                (company, bool(now_enabled)),
            )
        except Exception:
            pass
        return {
            "ok": bool(result.get("ok")),
            "module_key": key,
            "result": result,
            "policy": get_wave6_module_policy(cur, company, key),
        }
    if key == "benefits":
        enabled = body.get("enabled")
        policy_kwargs = {
            k: body[k]
            for k in (
                "employee_self_service_enabled",
                "manager_sees_private_detail",
                "payroll_handoff_enabled",
                "ja_eligibility_enabled",
                "require_documents_when_configured",
            )
            if k in body
        }
        if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
            result = bn.enable_company_benefits(
                cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
            )
        elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
            result = bn.disable_company_benefits(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        else:
            if not bn.module_enabled_for_company(cur, company):
                result = {"ok": False, "error": "benefits_disabled_for_company"}
            else:
                result = bn.enable_company_benefits(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
                )
        now_enabled = bn.module_enabled_for_company(cur, company)
        try:
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'benefits', %s, 'wave6_setup', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key)
                DO UPDATE SET enabled=EXCLUDED.enabled, source='wave6_setup', updated_at=now()
                """,
                (company, bool(now_enabled)),
            )
        except Exception:
            pass
        return {
            "ok": bool(result.get("ok")),
            "module_key": key,
            "result": result,
            "policy": get_wave6_module_policy(cur, company, key),
        }
    if key == "employee_relations":
        enabled = body.get("enabled")
        policy_kwargs = {
            k: body[k]
            for k in (
                "employee_submission_enabled",
                "manager_referral_enabled",
                "default_confidentiality",
                "sla_triage_days",
            )
            if k in body
        }
        if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
            result = er.enable_company_employee_relations(
                cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
            )
        elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
            result = er.disable_company_employee_relations(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        else:
            if not er.module_enabled_for_company(cur, company):
                result = {"ok": False, "error": "employee_relations_disabled_for_company"}
            else:
                result = er.enable_company_employee_relations(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
                )
        now_enabled = er.module_enabled_for_company(cur, company)
        try:
            cur.execute(
                """
                INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                VALUES (%s, 'employee_relations', %s, 'wave6_setup', '{}'::jsonb, now())
                ON CONFLICT (company_code, module_key)
                DO UPDATE SET enabled=EXCLUDED.enabled, source='wave6_setup', updated_at=now()
                """,
                (company, bool(now_enabled)),
            )
        except Exception:
            pass
        return {
            "ok": bool(result.get("ok")),
            "module_key": key,
            "result": result,
            "policy": get_wave6_module_policy(cur, company, key),
        }
    if key == "engagement":
        enabled = body.get("enabled")
        policy_kwargs = {
            k: body[k]
            for k in (
                "min_responses",
                "default_privacy_mode",
                "manager_results_enabled",
                "free_text_enabled",
                "employee_survey_enabled",
                "action_plans_enabled",
            )
            if k in body
        }
        if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
            result = eg.enable_company_engagement(
                cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
            )
        elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
            result = eg.disable_company_engagement(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        else:
            if not eg.module_enabled_for_company(cur, company):
                result = {"ok": False, "error": "engagement_disabled_for_company"}
            else:
                result = eg.enable_company_engagement(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
                )
        return {
            "ok": bool(result.get("ok")),
            "module_key": key,
            "result": result,
            "policy": get_wave6_module_policy(cur, company, key),
        }
    if key == "comp_planning":
        enabled = body.get("enabled")
        policy_kwargs = {
            k: body[k]
            for k in (
                "default_currency",
                "budget_overrun_mode",
                "sod_required",
                "performance_input_enabled",
                "talent_input_enabled",
                "payroll_handoff_enabled",
            )
            if k in body
        }
        if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
            result = cp.enable_company_comp_planning(
                cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
            )
        elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
            result = cp.disable_company_comp_planning(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        else:
            if not cp.module_enabled_for_company(cur, company):
                result = {"ok": False, "error": "comp_planning_disabled_for_company"}
            else:
                result = cp.enable_company_comp_planning(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
                )
        return {
            "ok": bool(result.get("ok")),
            "module_key": key,
            "result": result,
            "policy": get_wave6_module_policy(cur, company, key),
        }
    if key == "workforce_planning":
        enabled = body.get("enabled")
        policy_kwargs = {
            k: body[k]
            for k in (
                "default_currency",
                "default_horizon",
                "recruiting_handoff_enabled",
                "comp_assumptions_enabled",
                "talent_skills_enabled",
            )
            if k in body
        }
        if enabled is True or str(enabled).lower() in {"1", "true", "yes", "on"}:
            result = wfp.enable_company_workforce_planning(
                cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
            )
        elif enabled is False or str(enabled).lower() in {"0", "false", "no", "off"}:
            result = wfp.disable_company_workforce_planning(
                cur, company_code=company, actor_phone=actor_phone, reason=reason
            )
        else:
            if not wfp.module_enabled_for_company(cur, company):
                result = {"ok": False, "error": "workforce_planning_disabled_for_company"}
            else:
                result = wfp.enable_company_workforce_planning(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason, **policy_kwargs
                )
        return {
            "ok": bool(result.get("ok")),
            "module_key": key,
            "result": result,
            "policy": get_wave6_module_policy(cur, company, key),
        }
    return {"ok": False, "error": "unhandled_module"}
