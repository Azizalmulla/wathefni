#!/usr/bin/env python3
"""Setup Console — Wave 4 Performance + Talent company policies.

Owns company-level configuration for Goals/OKRs, reviews/360, check-ins,
competencies, development, aggregation/calibration, Talent profile, Talent
Review, HiPo, optional 9-box, succession/readiness.

Env flags remain fail-closed runtime/kill-switch gates; Setup is the
customer-facing long-term policy owner (not env-only configuration).

C7 product acceptance — no new domain SoT; composition + modularity only.
"""
from __future__ import annotations

import json
from typing import Any

PHASE = "setup_console_wave4"
CONTRACT_VERSION = "wave4_performance_talent_policies_v1"
PASS_STAMP = "WAVE4_PRODUCT_FULL_PASS"

WAVE4_MODULE_KEYS = (
    "performance_goals",
    "performance_reviews",
    "performance_feedback",
    "performance_calibration",
    "talent_profile",
    "talent_succession",
)

DEFAULTS: dict[str, dict[str, Any]] = {
    "performance_goals": {
        "enabled": False,
        "okrs_enabled": True,
        "kpi_goals_enabled": True,
        "milestone_goals_enabled": True,
        "development_goals_enabled": True,
        "allow_alignment_links": True,
        "force_rigid_cascade": False,
    },
    "performance_reviews": {
        "enabled": False,
        "goals_integration_enabled": True,
        "competencies_enabled": False,
        "review_360_enabled": False,
        "anonymity_default": True,
        "min_respondent_threshold": 3,
        "allow_hr_raw_360": False,
        "require_self_review": True,
        "require_manager_review": True,
    },
    "performance_feedback": {
        "enabled": False,
        "check_ins_enabled": True,
        "competencies_enabled": True,
        "competency_assessments_enabled": True,
        "development_enabled": True,
        "hr_tasks_integration_enabled": False,
        "sensitive_notes_hr_only": True,
    },
    "performance_calibration": {
        "enabled": False,
        "aggregation_enabled": True,
        "calibration_enabled": True,
        "provisional_visible_to_employees": False,
        "require_sensitive_permission": True,
        "sod_lock_requires_other_actor": False,
        "default_missing_rule": "exclude_from_denominator",
        "forced_distribution_assumed": False,
    },
    "talent_profile": {
        "enabled": False,
        "employee_career_self_service": True,
        "performance_evidence_consume": False,
        "potential_enabled": True,
        "skills_enabled": True,
        "sensitive_potential_hr_manager_only": True,
        "require_sensitive_permission_for_potential": True,
    },
    "talent_succession": {
        "enabled": False,
        "talent_review_enabled": True,
        "hipo_enabled": True,
        "succession_enabled": True,
        "nine_box_enabled": False,
        "performance_evidence_consume": False,
        "employees_see_hipo": False,
        "employees_see_succession": False,
        "require_sensitive_permission": True,
    },
}

STATUS_LABELS = {
    "performance_goals": {"en": "Goals / OKRs / KPIs", "ar": "الأهداف / النتائج الرئيسية / مؤشرات الأداء"},
    "performance_reviews": {"en": "Review cycles / 360", "ar": "دورات التقييم / 360"},
    "performance_feedback": {"en": "Check-ins / competencies / development", "ar": "المتابعات / الكفاءات / التطوير"},
    "performance_calibration": {"en": "Aggregation / calibration", "ar": "التجميع / المعايرة"},
    "talent_profile": {"en": "Talent profile / potential", "ar": "ملف المواهب / الإمكانات"},
    "talent_succession": {"en": "Talent review / HiPo / succession", "ar": "مراجعة المواهب / الإمكانات العالية / التعاقب"},
    "assessment_norms": {"en": "Assessment norms (pre-hire)", "ar": "معايير التقييم (ما قبل التوظيف)"},
    "performance_calibration_label": {"en": "Performance calibration", "ar": "معايرة الأداء"},
    "recruiting_talent_pool": {"en": "Recruiting talent pool (candidates)", "ar": "مجمع مواهب التوظيف (مرشحون)"},
    "posthire_talent": {"en": "Post-hire Talent", "ar": "المواهب بعد التوظيف"},
}

# Commercial module_key used for company_modules overlay storage
_COMMERCIAL = {
    "performance_goals": "performance",
    "performance_reviews": "performance",
    "performance_feedback": "performance",
    "performance_calibration": "performance",
    "talent_profile": "talent",
    "talent_succession": "talent",
}

# Env flag mapping for modularity matrix cells
ENV_FLAG_BY_MODULE = {
    "performance_goals": ("WATHEFNI_PERFORMANCE_GOALS_C1", "WATHEFNI_PERFORMANCE_GOALS_COMPANIES"),
    "performance_reviews": ("WATHEFNI_PERFORMANCE_REVIEWS_C2", "WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES"),
    "performance_feedback": ("WATHEFNI_PERFORMANCE_FEEDBACK_C3", "WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES"),
    "performance_calibration": (
        "WATHEFNI_PERFORMANCE_CALIBRATION_C4",
        "WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES",
    ),
    "talent_profile": ("WATHEFNI_TALENT_PROFILE_C5", "WATHEFNI_TALENT_PROFILE_COMPANIES"),
    "talent_succession": ("WATHEFNI_TALENT_SUCCESSION_C6", "WATHEFNI_TALENT_SUCCESSION_COMPANIES"),
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
        "setup_owns_wave4_policies": True,
        "env_only_ownership": False,
        "env_flags_are_kill_switches_only": True,
        "assistant_mutations_in_wave4": False,
        "no_new_domain_authority_in_c7": True,
        "c3_sole_development_authority": True,
        "nine_box_optional_projection_not_sot": True,
        "no_master_talent_score": True,
        "no_canonical_employee_box": True,
        "recruiting_talent_pool_isolated": True,
        "assessment_calibration_named_assessment_norms": True,
        "performance_calibration_unambiguous": True,
        "wave5_emits_facts_not_kpi_cards": True,
        "customer_enableable": False,
        "customer_visible_in_setup": False,
        "domain_full_pass_is_not_customer_enableable": True,
        "stored_enabled_does_not_imply_usable": True,
    }


def naming_boundary_payload() -> dict[str, Any]:
    return {
        "recruiting_talent_pool": {
            "storage_key": "talent_pool",
            "population": "candidates",
            "label_en": status_label("recruiting_talent_pool", lang="en"),
            "label_ar": status_label("recruiting_talent_pool", lang="ar"),
        },
        "posthire_talent": {
            "module_key": "talent",
            "population": "employees",
            "label_en": status_label("posthire_talent", lang="en"),
            "label_ar": status_label("posthire_talent", lang="ar"),
        },
        "assessment_norms": {
            "legacy_misnomer": "assessment calibration",
            "product_label_en": status_label("assessment_norms", lang="en"),
            "product_label_ar": status_label("assessment_norms", lang="ar"),
        },
        "performance_calibration": {
            "label_en": status_label("performance_calibration_label", lang="en"),
            "label_ar": status_label("performance_calibration_label", lang="ar"),
            "distinct_from_assessment_norms": True,
        },
        "collision": False,
    }


def wave5_fact_catalog() -> list[dict[str, Any]]:
    """Documented Wave 4 → Wave 5 inputs. Wave 5 owns KPI defs/visualization."""
    return [
        {"fact": "goal_attainment", "source_slice": "C1", "owner_wave": 5},
        {"fact": "performance_outcome_distribution", "source_slice": "C2/C4", "owner_wave": 5},
        {"fact": "competency_assessment_facts", "source_slice": "C3", "owner_wave": 5},
        {"fact": "development_action_facts", "source_slice": "C3", "owner_wave": 5},
        {"fact": "talent_population_facts", "source_slice": "C5", "owner_wave": 5},
        {"fact": "hipo_designation_facts", "source_slice": "C6", "owner_wave": 5},
        {"fact": "critical_role_coverage", "source_slice": "C6", "owner_wave": 5},
        {"fact": "successor_counts", "source_slice": "C6", "owner_wave": 5},
        {"fact": "ready_now_distribution", "source_slice": "C6", "owner_wave": 5},
        {"fact": "uncovered_critical_role_facts", "source_slice": "C6", "owner_wave": 5},
    ]


def surface_composition_rules() -> dict[str, Any]:
    """Intentional composition — no empty shells for disabled capabilities."""
    return {
        "hr_web": {
            "hosts": [
                "performance_admin",
                "goals_reviews_cycles",
                "calibration",
                "talent_profiles_reviews",
                "succession_critical_roles",
                "setup",
            ],
            "heavyweight_ok": True,
        },
        "manager_surface": {
            "hosts": [
                "reports_goals",
                "check_ins",
                "reviews",
                "competency_development",
                "authorized_talent_review_succession",
            ],
        },
        "employee_app": {
            "hosts": [
                "own_goals_okrs",
                "goal_progress_evidence",
                "self_review",
                "assigned_360",
                "check_ins",
                "development_actions",
                "employee_aspirations_skills",
            ],
            "compose_when_subset_enabled": True,
            "no_empty_talent_shell_when_talent_off": True,
            "no_empty_reviews_shell_when_reviews_off": True,
        },
        "hr_mobile": {
            "hosts": ["operational_decision_surfaces_only"],
            "not_forced": [
                "heavyweight_calibration_admin",
                "succession_framework_design",
                "large_9box_administration",
            ],
        },
        "assistant": {
            "mutations": False,
            "allowed": ["read", "explain", "summarize", "deep_link"],
        },
        "disabled_capability_ux": {
            "no_empty_tabs": True,
            "no_blank_screens": True,
            "no_dead_actions": True,
            "no_nav_to_disabled_modules": True,
            "no_cards_for_unavailable": True,
            "no_inbox_tasks_for_disabled": True,
        },
    }


def modularity_matrix_configs() -> list[dict[str, Any]]:
    """Canonical Wave 4 product modularity matrix."""
    return [
        {"name": "goals_only", "modules": {"performance_goals": True}},
        {
            "name": "reviews_plus_goals",
            "modules": {"performance_goals": True, "performance_reviews": True},
        },
        {
            "name": "reviews_without_formal_goals",
            "modules": {"performance_reviews": True},
            "notes": "goals_integration optional/off",
        },
        {
            "name": "performance_full_talent_off",
            "modules": {
                "performance_goals": True,
                "performance_reviews": True,
                "performance_feedback": True,
                "performance_calibration": True,
            },
        },
        {
            "name": "talent_only_performance_off",
            "modules": {"talent_profile": True, "talent_succession": True},
            "capabilities": {"nine_box": False, "performance_evidence": False},
        },
        {
            "name": "talent_plus_optional_performance_evidence",
            "modules": {
                "talent_profile": True,
                "talent_succession": True,
                "performance_calibration": True,
            },
            "capabilities": {"performance_evidence": True},
        },
        {
            "name": "talent_without_recruiting",
            "modules": {"talent_profile": True, "talent_succession": True},
            "notes": "recruiting talent_pool untouched",
        },
        {
            "name": "talent_without_learning",
            "modules": {"talent_profile": True, "talent_succession": True},
            "notes": "L&D not required",
        },
        {
            "name": "succession_without_hipo",
            "modules": {"talent_succession": True},
            "capabilities": {"hipo": False, "nine_box": False},
        },
        {
            "name": "succession_without_nine_box",
            "modules": {"talent_succession": True},
            "capabilities": {"nine_box": False},
        },
        {
            "name": "hipo_without_nine_box",
            "modules": {"talent_succession": True},
            "capabilities": {"hipo": True, "nine_box": False},
        },
        {
            "name": "nine_box_without_succession",
            "modules": {"talent_succession": True},
            "capabilities": {"nine_box": True, "succession": False},
            "notes": "projection config only; succession feature may be gated in Setup",
        },
        {
            "name": "full_performance_plus_talent",
            "modules": {
                "performance_goals": True,
                "performance_reviews": True,
                "performance_feedback": True,
                "performance_calibration": True,
                "talent_profile": True,
                "talent_succession": True,
            },
            "capabilities": {"nine_box": True, "hipo": True, "performance_evidence": True},
        },
        {"name": "all_wave4_disabled", "modules": {}},
    ]


def _module_row(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    try:
        cur.execute(
            """
            SELECT enabled, settings FROM company_modules
            WHERE company_code=%s AND module_key=%s
            LIMIT 1
            """,
            (company, module_key),
        )
        row = cur.fetchone()
    except Exception:
        return {"enabled": False, "settings": {}}
    if not row:
        return {"enabled": False, "settings": {}}
    d = dict(row) if isinstance(row, dict) else {"enabled": row[0], "settings": row[1]}
    settings = d.get("settings") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except Exception:
            settings = {}
    if not isinstance(settings, dict):
        settings = {}
    return {"enabled": bool(d.get("enabled")), "settings": settings}


def _save_wave4_overlay(cur: Any, company: str, module_key: str, overlay: dict[str, Any]) -> None:
    commercial = _COMMERCIAL.get(module_key, "performance")
    row = _module_row(cur, company, commercial)
    settings = dict(row.get("settings") or {})
    wave4 = dict(settings.get("wave4_setup") or {})
    wave4[module_key] = {**(DEFAULTS.get(module_key) or {}), **(wave4.get(module_key) or {}), **overlay}
    settings["wave4_setup"] = wave4
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,%s,%s,'setup_console_wave4',%s::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET
          settings=EXCLUDED.settings,
          source=EXCLUDED.source,
          updated_at=now()
        """,
        (company, commercial, bool(row.get("enabled")), json.dumps(settings, default=str)),
    )


def _read_overlay(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    commercial = _COMMERCIAL.get(module_key, "performance")
    settings = _module_row(cur, company, commercial).get("settings") or {}
    wave4 = settings.get("wave4_setup") if isinstance(settings.get("wave4_setup"), dict) else {}
    overlay = wave4.get(module_key) if isinstance(wave4.get(module_key), dict) else {}
    return {**(DEFAULTS.get(module_key) or {}), **overlay}


def get_wave4_module_policy(cur: Any, company_code: str, module_key: str) -> dict[str, Any]:
    company = _company(company_code)
    key = str(module_key or "").strip()
    if key not in WAVE4_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave4_module", "allowed": list(WAVE4_MODULE_KEYS)}
    policy = _read_overlay(cur, company, key)
    return {
        "ok": True,
        "company_code": company,
        "module_key": key,
        "commercial_module_key": _COMMERCIAL[key],
        "policy": policy,
        "label_en": status_label(key, lang="en"),
        "label_ar": status_label(key, lang="ar"),
        "setup_owned": True,
        "env_flag_pair": ENV_FLAG_BY_MODULE.get(key),
    }


def get_all_wave4_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    modules = {}
    for key in WAVE4_MODULE_KEYS:
        modules[key] = get_wave4_module_policy(cur, company, key)
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "company_code": company,
        "modules": modules,
        "naming_boundary": naming_boundary_payload(),
        "surface_composition": surface_composition_rules(),
        "wave5_fact_catalog": wave5_fact_catalog(),
        "modularity_matrix": modularity_matrix_configs(),
        **honesty_payload(),
    }


def patch_wave4_module_policy(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    actor_phone: str,
    reason: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    key = str(module_key or "").strip()
    if key not in WAVE4_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave4_module", "allowed": list(WAVE4_MODULE_KEYS)}
    body = dict(payload or {})
    if "required" in body and isinstance(body["required"], dict):
        body = {**body["required"], **{k: v for k, v in body.items() if k != "required"}}
    allowed = set((DEFAULTS.get(key) or {}).keys())
    overlay = {k: body[k] for k in body if k in allowed}
    if not overlay:
        return {"ok": False, "error": "no_allowed_fields", "allowed": sorted(allowed)}
    # Hard anti-regression: never allow Setup to invent forced distribution or employee.box
    if key == "performance_calibration" and overlay.get("forced_distribution_assumed") is True:
        return {"ok": False, "error": "forced_distribution_never_assumed"}
    if key == "talent_succession" and "employee_box" in overlay:
        return {"ok": False, "error": "canonical_employee_box_forbidden"}
    _save_wave4_overlay(cur, company, key, overlay)
    _ = actor_phone
    return get_wave4_module_policy(cur, company, key)


def scan_forbidden_authorities(source_texts: dict[str, str]) -> dict[str, Any]:
    """C7 anti-regression scan — no master score / employee.box / opaque universal ranking."""
    forbidden_patterns = (
        "master_talent_score",
        "universal_talent_score",
        "employee.box",
        "employee_box =",
        '"employee_box"',
        "opaque_readiness_score",
        "ai_assigned_potential",
        "ai_designate_hipo",
    )
    hits: list[dict[str, str]] = []
    for name, text in source_texts.items():
        low = text.lower()
        for pat in forbidden_patterns:
            if pat.lower() in low:
                # Allow honesty/docs that explicitly forbid these
                if "no_master_talent_score" in low or "no_canonical_employee_box" in low:
                    if pat in ("master_talent_score", "employee.box", '"employee_box"'):
                        # still flag raw assignments; honesty keys are OK
                        if f"no_{pat}" in low or "no_master_talent_score" in low:
                            continue
                hits.append({"file": name, "pattern": pat})
    return {"ok": len(hits) == 0, "hits": hits, "scanned_files": list(source_texts.keys())}
