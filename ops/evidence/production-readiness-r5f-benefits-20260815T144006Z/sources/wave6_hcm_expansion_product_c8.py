"""Wave 6 C8 — Product Acceptance / Full HCM Expansion Gate.

Acceptance/integration slice only. No new module authority or domain math.
Consumes frozen C1–C7 exclusively. FULL_PASS ≠ broad rollout.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

PHASE = "wave6_hcm_expansion_product_c8"
CONTRACT_VERSION = "wave6_hcm_expansion_product_c8_v1"
PASS_STAMP = "WAVE6_PRODUCT_FULL_PASS"
FLAG = "WATHEFNI_HCM_EXPANSION_PRODUCT_C8"
COMPANIES_FLAG = "WATHEFNI_HCM_EXPANSION_PRODUCT_COMPANIES"
_ON = {"1", "true", "yes", "on"}

WAVE6_SLICES: tuple[tuple[str, str, str], ...] = (
    ("c1", "job_architecture", "JOB_ARCHITECTURE_FULL_PASS"),
    ("c2", "learning", "LEARNING_DEVELOPMENT_FULL_PASS"),
    ("c3", "benefits", "BENEFITS_FULL_PASS"),
    ("c4", "employee_relations", "EMPLOYEE_RELATIONS_FULL_PASS"),
    ("c5", "engagement", "ENGAGEMENT_FULL_PASS"),
    ("c6", "comp_planning", "COMPENSATION_PLANNING_FULL_PASS"),
    ("c7", "workforce_planning", "WORKFORCE_PLANNING_FULL_PASS"),
)

MODULARITY_CELLS: tuple[str, ...] = (
    "ja_only",
    "learning_only",
    "benefits_only",
    "er_only",
    "engagement_only",
    "comp_plus_ja_only",
    "wfp_plus_ja_only",
    "learning_plus_performance_optional",
    "learning_plus_talent_optional",
    "benefits_plus_payroll_optional",
    "benefits_without_payroll",
    "comp_plus_payroll_optional",
    "comp_without_payroll",
    "wfp_plus_recruiting_optional",
    "wfp_without_recruiting",
    "full_wave6_enabled",
    "all_wave6_disabled",
)

SAFE_DEBT: tuple[str, ...] = (
    "broad_production_rollout_beyond_canary",
    "hr_mobile_heavyweight_worksheet_parity_not_required",
    "employee_app_personal_comp_communication_via_downstream_only",
    "scheduled_cross_module_ops_polish",
)

STATUS_LABELS = {
    "wave6_product": {"en": "Wave 6 Product Acceptance", "ar": "قبول منتج الموجة 6"},
    "available": {"en": "Available", "ar": "متاح"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
    "disabled_clean": {"en": "Disabled (clean)", "ar": "متوقف (نظيف)"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "acceptance_only": True,
        "no_new_module_authority": True,
        "no_new_domain_math": True,
        "consumes_c1_through_c7_only": True,
        "one_canonical_employee_employment_org": True,
        "ja_sole_wave6_job_grade_authority": True,
        "no_second_analytics_engine": True,
        "assistant_mutations": False,
        "setup_owns_wave6_policies": True,
        "env_flags_are_gates_only": True,
        "full_pass_not_broad_rollout": True,
        "global_wave6_remains_off": True,
        "modularity_cells": list(MODULARITY_CELLS),
        "safe_debt": list(SAFE_DEBT),
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {"primary": True, "intentional_product_surfaces": True, "not_raw_domain_tables": True},
        "hr_mobile": {"intentionally_thin": True, "no_artificial_parity": True},
        "employee_app": {"self_service_only_where_applicable": True, "no_future_plan_or_draft_comp_leak": True},
        "assistant": {"mutations": False, "read_explain_summarize_deep_link": True},
        "setup": {"one_coherent_wave6_area": True, "module_cards": True},
        "disabled_capability_ux": {
            "no_empty_section_shells": True,
            "no_fake_zero": True,
            "disappear_cleanly": True,
        },
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "wave6_product_c8_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow or company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "wave6_product_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE, "acceptance_only": True}


def modularity_matrix_configs() -> list[dict[str, Any]]:
    """Declarative composition matrix — prove via flags/honesty (no fake fallback truth)."""
    return [
        {"cell": "ja_only", "enable": ["ja"], "hard_deps": [], "optional_off": ["learning", "benefits", "er", "engagement", "comp", "wfp"]},
        {"cell": "learning_only", "enable": ["learning"], "optional_off": ["ja", "perf", "talent"]},
        {"cell": "benefits_only", "enable": ["benefits"], "optional_off": ["payroll"]},
        {"cell": "er_only", "enable": ["er"], "optional_off": ["engagement"]},
        {"cell": "engagement_only", "enable": ["engagement"], "optional_off": ["er"]},
        {"cell": "comp_plus_ja_only", "enable": ["ja", "comp"], "hard_deps": ["ja"], "optional_off": ["payroll", "perf", "talent"]},
        {"cell": "wfp_plus_ja_only", "enable": ["ja", "wfp"], "hard_deps": ["ja"], "optional_off": ["recruiting", "comp", "talent"]},
        {"cell": "learning_plus_performance_optional", "enable": ["learning"], "optional_on": ["perf"], "c3_remains_sot": True},
        {"cell": "learning_plus_talent_optional", "enable": ["learning"], "optional_on": ["talent"], "no_auto_hipo": True},
        {"cell": "benefits_plus_payroll_optional", "enable": ["benefits"], "optional_on": ["payroll"]},
        {"cell": "benefits_without_payroll", "enable": ["benefits"], "optional_off": ["payroll"], "works_payroll_off": True},
        {"cell": "comp_plus_payroll_optional", "enable": ["ja", "comp"], "optional_on": ["payroll"], "explicit_handoff_only": True},
        {"cell": "comp_without_payroll", "enable": ["ja", "comp"], "optional_off": ["payroll"], "works_payroll_off": True},
        {"cell": "wfp_plus_recruiting_optional", "enable": ["ja", "wfp"], "optional_on": ["recruiting"], "draft_req_only": True},
        {"cell": "wfp_without_recruiting", "enable": ["ja", "wfp"], "optional_off": ["recruiting"], "works_recruiting_off": True},
        {"cell": "full_wave6_enabled", "enable": ["ja", "learning", "benefits", "er", "engagement", "comp", "wfp"]},
        {"cell": "all_wave6_disabled", "enable": [], "expect_unavailable": True, "waves_1_5_unaffected": True},
    ]


def module_authority_matrix() -> list[dict[str, Any]]:
    return [
        {"module": "job_architecture", "owns": ["families", "functions", "profiles", "grades", "levels", "assignments"], "does_not_own": ["salary_bands", "employee_master"]},
        {"module": "learning", "owns": ["offerings", "assignments", "completions", "mandatory"], "does_not_own": ["development_plan_sot", "competency_verification"]},
        {"module": "benefits", "owns": ["plans", "eligibility", "elections", "coverage"], "does_not_own": ["claims", "payroll_execution", "dependent_master"]},
        {"module": "employee_relations", "owns": ["cases", "investigations", "outcomes"], "does_not_own": ["employment_mutation", "engagement"]},
        {"module": "engagement", "owns": ["surveys", "campaigns", "aggregates", "action_plans"], "does_not_own": ["recognition", "er_cases"]},
        {"module": "comp_planning", "owns": ["cycles", "bands", "budgets", "recommendations", "handoffs"], "does_not_own": ["payroll", "ja_grades", "salary_mutation"]},
        {"module": "workforce_planning", "owns": ["baselines", "plans", "scenarios", "demand", "execution_handoffs"], "does_not_own": ["actual_headcount", "requisition_sm", "ja_catalog"]},
    ]


def permission_confidentiality_matrix() -> list[dict[str, Any]]:
    return [
        {"domain": "tenant", "rule": "company_allowlist_fail_closed"},
        {"domain": "employee_self", "rule": "no_draft_comp_no_future_wfp"},
        {"domain": "manager_scope", "rule": "authorized_reports_only_not_company_budget"},
        {"domain": "hr_ops", "rule": "module_enabled_plus_rbac"},
        {"domain": "setup_admin", "rule": "owns_wave6_policies"},
        {"domain": "learning", "rule": "assign_complete_permissions"},
        {"domain": "benefits", "rule": "private_detail_manager_fail_closed"},
        {"domain": "er", "rule": "case_level_need_to_know_ordinary_hr_not_er"},
        {"domain": "engagement", "rule": "anonymity_min5_upward_complementary"},
        {"domain": "comp", "rule": "sensitive_access_plus_sod_recommend_ne_approve"},
        {"domain": "wfp", "rule": "sensitive_plan_access_execution_restricted"},
        {"domain": "frontend", "rule": "cannot_exceed_backend_authority"},
    ]


def handoff_contract_matrix() -> list[dict[str, Any]]:
    return [
        {"from": "learning", "to": "wave4_c3_development", "class": "optional", "rule": "fulfillment_evidence_not_silent_close"},
        {"from": "benefits", "to": "payroll", "class": "optional", "rule": "contribution_handoff_ne_deduction_applied"},
        {"from": "er", "to": "employment_change", "class": "explicit", "rule": "outcome_ne_employment_mutation"},
        {"from": "comp", "to": "employment_change_or_payroll", "class": "explicit", "rule": "finalized_ne_applied_ne_paid"},
        {"from": "wfp", "to": "wave1_requisition", "class": "explicit", "rule": "draft_only_no_auto_post_hire"},
    ]


def anti_duplication_scan(orch_dir: Path | None = None) -> dict[str, Any]:
    """Source scan: no competing employee/employment/org/payroll/analytics authorities in Wave 6."""
    root = orch_dir or Path(__file__).resolve().parent
    modules = [
        "job_architecture_c1.py",
        "learning_development_c2.py",
        "benefits_administration_c3.py",
        "employee_relations_c4.py",
        "engagement_c5.py",
        "compensation_planning_c6.py",
        "workforce_planning_c7.py",
        "setup_console_wave6_policies.py",
        "wave6_hcm_expansion_product_c8.py",
    ]
    findings: list[str] = []
    # Construct needles so this acceptance file does not itself contain full DDL literals.
    create = "create table if not exists "
    forbidden_ddl = [
        create + "employees ",
        create + "employments ",
        create + "org_units ",
        create + "payroll_runs ",
        create + "cp_grade",
        create + "wfp_grade",
        create + "wfp_job_profile",
        create + "eng_recognition",
        create + "bn_claims",
    ]
    ja_grade_ddl = create + "ja_grade"
    ja_grade_owners = 0
    for name in modules:
        path = root / name
        if not path.exists():
            findings.append(f"missing:{name}")
            continue
        raw = path.read_text(encoding="utf-8")
        text = raw.lower()
        if name == "wave6_hcm_expansion_product_c8.py":
            # Acceptance module must not define evaluator or execute schema DDL.
            if re.search(r"(?m)^def evaluate_kpi\(", raw):
                findings.append("c8_must_not_define_evaluate_kpi")
            if re.search(r"(?m)^\s*cur\.execute\(\s*[\"'].*create table", raw, flags=re.I):
                findings.append("c8_must_not_create_tables")
            continue
        for needle in forbidden_ddl:
            if needle in text:
                findings.append(f"{name}:{needle.strip()}")
        if ja_grade_ddl in text:
            if name == "job_architecture_c1.py":
                ja_grade_owners += 1
            else:
                findings.append(f"second_ja_grade_ddl:{name}")
        if re.search(r"(?m)^def evaluate_kpi\(", raw):
            findings.append(f"second_evaluate_kpi:{name}")
    return {
        "ok": len(findings) == 0 and ja_grade_owners == 1,
        "findings": findings,
        "ja_sole_grade_ddl": ja_grade_owners == 1,
        "scanned": modules,
        "single_wave5_evaluator": "hr_intelligence_registry_c1.evaluate_kpi",
    }


def contract_reprove() -> dict[str, Any]:
    """Import frozen modules and assert binding honesty contracts."""
    import benefits_administration_c3 as bn
    import compensation_planning_c6 as cp
    import employee_relations_c4 as er
    import engagement_c5 as eg
    import job_architecture_c1 as ja
    import learning_development_c2 as ld
    import setup_console_wave6_policies as w6
    import workforce_planning_c7 as wfp

    checks: dict[str, bool] = {}
    checks["ja_stamp"] = ja.PASS_STAMP == "JOB_ARCHITECTURE_FULL_PASS"
    checks["ld_stamp"] = ld.PASS_STAMP == "LEARNING_DEVELOPMENT_FULL_PASS"
    checks["bn_stamp"] = bn.PASS_STAMP == "BENEFITS_FULL_PASS"
    checks["er_stamp"] = er.PASS_STAMP == "EMPLOYEE_RELATIONS_FULL_PASS"
    checks["eg_stamp"] = eg.PASS_STAMP == "ENGAGEMENT_FULL_PASS"
    checks["cp_stamp"] = cp.PASS_STAMP == "COMPENSATION_PLANNING_FULL_PASS"
    checks["wfp_stamp"] = wfp.PASS_STAMP == "WORKFORCE_PLANNING_FULL_PASS"
    checks["setup_seven_modules"] = set(w6.WAVE6_MODULE_KEYS) >= {
        "job_architecture", "learning", "benefits", "employee_relations",
        "engagement", "comp_planning", "workforce_planning",
    }
    jh = ja.honesty_payload()
    checks["ja_salary_bands_out"] = jh.get("salary_bands_out_of_c1") is True
    checks["ja_assistant_ro"] = jh.get("assistant_mutations") is False
    lh = ld.honesty_payload()
    checks["ld_no_dup_c3"] = lh.get("does_not_duplicate_c3_development") is True
    checks["ld_no_silent_close"] = lh.get("completion_does_not_silently_close_development_action") is True
    checks["ld_no_auto_skill"] = lh.get("completion_does_not_auto_verify_skill_or_competency") is True
    checks["ld_works_ja_off"] = lh.get("works_without_ja") is True
    bh = bn.honesty_payload()
    checks["bn_claims_out"] = bh.get("claims_adjudication_out") is True
    checks["bn_works_payroll_off"] = bh.get("works_payroll_off") is True
    checks["bn_eligible_ne_enrolled"] = bh.get("eligible_not_enrolled") is True
    eh = er.honesty_payload()
    checks["er_ordinary_hr_not"] = eh.get("ordinary_hr_not_er") is True
    checks["er_manager_not"] = eh.get("manager_not_er") is True
    checks["er_outcome_ne_mutation"] = eh.get("outcome_not_employment_mutation") is True
    gh = eg.honesty_payload()
    checks["eg_recognition_out"] = gh.get("recognition_out_of_mvp") is True
    checks["eg_min5"] = gh.get("min_responses_default_5") is True
    checks["eg_upward"] = gh.get("threshold_upward_only") is True
    checks["eg_no_map"] = gh.get("anonymous_no_respondent_answer_map") is True
    ch = cp.honesty_payload()
    checks["cp_ja_hard"] = ch.get("ja_is_hard") is True
    checks["cp_finalized_ne_applied"] = ch.get("finalized_not_applied") is True
    checks["cp_rating_ne_auto"] = ch.get("rating_not_automatic_increase") is True
    checks["cp_hipo_ne_auto"] = ch.get("hipo_not_automatic_pay") is True
    wh = wfp.honesty_payload()
    checks["wfp_ja_hard"] = wh.get("ja_is_hard") is True
    checks["wfp_planned_ne_actual"] = wh.get("planned_headcount_never_enters_actual_wave5") is True
    checks["wfp_no_auto_hire"] = wh.get("no_auto_post_hire") is True
    checks["wfp_approved_ne_exec"] = wh.get("approved_ne_execution") is True
    contracts = ja.future_hard_contracts()
    checks["comp_hard_on_ja"] = contracts["compensation_planning"]["hard"] is True
    checks["wfp_hard_on_ja"] = contracts["workforce_planning"]["hard"] is True
    checks["talent_ja_optional"] = contracts["talent_optional_ref"]["hard"] is False
    checks["recruiting_ja_optional"] = contracts["recruiting_optional_ref"]["hard"] is False
    for mod in (ja, ld, bn, er, eg, cp, wfp):
        key = f"{mod.PHASE}_assistant_ro"
        checks[key] = mod.honesty_payload().get("assistant_mutations") is False
    failed = [k for k, v in checks.items() if not v]
    return {"ok": len(failed) == 0, "checks": checks, "failed": failed}


def frontend_setup_cards_scan(dashboard_setup_dir: Path | None = None) -> dict[str, Any]:
    candidates: list[Path] = []
    if dashboard_setup_dir is not None:
        candidates.append(dashboard_setup_dir)
    env_root = str(os.environ.get("WATHEFNI_REPO_ROOT") or "").strip()
    if env_root:
        candidates.append(Path(env_root) / "apps" / "wathefni-dashboard" / "src" / "setup-console")
    # Monorepo relative to orchestrator package
    candidates.append(Path(__file__).resolve().parents[1] / "apps" / "wathefni-dashboard" / "src" / "setup-console")
    # Common local absolute (qualify frontend step)
    candidates.append(Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/setup-console"))

    root = next((p for p in candidates if p.exists()), None)
    if root is None:
        return {
            "ok": False,
            "missing_cards": ["dashboard_setup_console_not_found"],
            "unmounted": [],
            "setup_owns_seven_cards": True,
            "skipped_reason": "dashboard_tree_unavailable_in_this_runtime",
        }
    required = [
        "Wave6JobArchitecturePoliciesCard.tsx",
        "Wave6LearningPoliciesCard.tsx",
        "Wave6BenefitsPoliciesCard.tsx",
        "Wave6EmployeeRelationsPoliciesCard.tsx",
        "Wave6EngagementPoliciesCard.tsx",
        "Wave6CompensationPlanningPoliciesCard.tsx",
        "Wave6WorkforcePlanningPoliciesCard.tsx",
    ]
    missing = [n for n in required if not (root / n).exists()]
    app = root / "SetupConsoleApp.tsx"
    app_text = app.read_text(encoding="utf-8") if app.exists() else ""
    component_names = [n.replace(".tsx", "") for n in required]
    # R5F: Job Architecture + Learning + Benefits Setup cards are customer-visible.
    # Remaining Wave 6 cards stay omitted.
    released = {"Wave6JobArchitecturePoliciesCard", "Wave6LearningPoliciesCard", "Wave6BenefitsPoliciesCard"}
    still_hidden = [name for name in component_names if name not in released]
    mounted = [name for name in component_names if name in app_text]
    mounted_hidden = [name for name in still_hidden if name in app_text]
    ja_mounted = "Wave6JobArchitecturePoliciesCard" in app_text
    ld_mounted = "Wave6LearningPoliciesCard" in app_text
    bn_mounted = "Wave6BenefitsPoliciesCard" in app_text
    return {
        "ok": not missing and not mounted_hidden and ja_mounted and ld_mounted and bn_mounted and app.exists(),
        "missing_cards": missing,
        "unmounted": [name for name in still_hidden if name not in app_text],
        "mounted_customer_cards": mounted,
        "setup_owns_seven_cards": True,
        "customer_setup_omits_unreleased_cards": not mounted_hidden,
        "job_architecture_setup_remounted": ja_mounted,
        "learning_setup_remounted": ld_mounted,
        "benefits_setup_remounted": bn_mounted,
    }


def acceptance_return_template() -> dict[str, Any]:
    return {
        "stamp": PASS_STAMP,
        "sections": [
            "full_wave6_product_prove",
            "module_authority_matrix",
            "dependency_modularity_matrix",
            "cross_module_handoff_proof",
            "permissions_confidentiality_matrix",
            "historical_reconstruction",
            "setup_ownership",
            "wave5_fact_integration",
            "en_ar_rtl",
            "anti_duplication_scan",
            "waves_1_5_regression_status",
            "genuine_blockers",
            "safe_debt",
        ],
        "stop": "owner_signoff_freeze_wave6",
        "do_not_begin_automatically": [
            "additional_hcm_domains",
            "wave7",
            "broad_production_rollout",
        ],
    }
