"""Wave 5 C7 — Product Acceptance / Full Intelligence Trust Gate.

Acceptance/integration slice only. No new KPI families, domain math,
second evaluator, Talent inference, or operational authority.
Consumes frozen C1–C6 exclusively.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

PHASE = "hr_intelligence_product_c7"
PASS_STAMP = "WAVE5_PRODUCT_FULL_PASS"
COMMERCIAL_MODULE_KEY = "analytics"
FLAG = "WATHEFNI_HR_INTELLIGENCE_PRODUCT_C7"
COMPANIES_FLAG = "WATHEFNI_HR_INTELLIGENCE_PRODUCT_COMPANIES"

# Representative KPI traceability matrix (family → semantic_key)
TRACE_MATRIX: tuple[tuple[str, str], ...] = (
    ("workforce", "workforce.headcount.active_heads"),
    ("recruiting", "recruiting.time_to_fill"),
    ("time_leave", "leave.utilization.rate"),
    ("payroll", "payroll.workforce_cost"),
    ("performance", "performance.goal_attainment"),
    ("talent", "talent.succession_coverage"),
    ("platform", "intelligence.spine.fact_count"),
)

MODULARITY_CELLS: tuple[str, ...] = (
    "workforce_only",
    "recruiting_only",
    "time_leave_only",
    "payroll_only",
    "performance_only",
    "talent_only",
    "talent_without_performance",
    "performance_without_talent",
    "mixed_operational_subset",
    "full_intelligence",
    "analytics_disabled",
    "source_module_off_stale_publication",
)

SAFE_DEBT: tuple[str, ...] = (
    "scheduled_report_recurring_delivery",
    "broad_production_rollout_beyond_canary",
    "hr_mobile_executive_summary_polish",
)


def _flag_on(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _companies(name: str) -> set[str]:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "acceptance_only": True,
        "no_new_kpi_families": True,
        "no_new_domain_math": True,
        "no_second_evaluator": True,
        "no_talent_inference": True,
        "no_operational_authority_expansion": True,
        "uses_c1_through_c6_only": True,
        "attention_is_not_intelligence": True,
        "fte_remains_blocked": True,
        "demographics_off_by_default": True,
        "scheduled_delivery_safe_debt": True,
        "employee_app_no_company_intelligence": True,
        "assistant_mutations_out": True,
        "setup_owns_customer_policy": True,
        "env_flags_are_gates_only": True,
        "global_wave5_remains_off": True,
        "company_code": company_code,
        "trace_matrix": [{"family": f, "semantic_key": k} for f, k in TRACE_MATRIX],
        "modularity_cells": list(MODULARITY_CELLS),
        "safe_debt": list(SAFE_DEBT),
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    if not company:
        return {"ok": False, "error": "company_required"}
    if _flag_on("WATHEFNI_ANALYTICS_KILL"):
        return {"ok": False, "error": "analytics_kill"}
    if not _flag_on(FLAG):
        return {"ok": False, "error": "product_c7_off"}
    allow = _companies(COMPANIES_FLAG)
    if not allow or company not in allow:
        return {"ok": False, "error": "company_not_allowlisted"}
    return {"ok": True, "company_code": company, "phase": PHASE}


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {
            "primary": True,
            "overview_concise": True,
            "explore_deeper": True,
            "about_metric": True,
            "drill": True,
            "saved_views": True,
            "export": True,
            "ops_attention_separate": True,
        },
        "hr_mobile": {
            "intentionally_thin": True,
            "no_deep_segmentation_studio": True,
            "no_heavy_succession_admin": True,
            "no_large_payroll_analysis": True,
        },
        "employee_app": {
            "company_intelligence": False,
            "personal_insights_separate_decision": True,
        },
        "assistant": {
            "mutations": False,
            "uses_published_registry_only": True,
            "uses_shared_evaluator": True,
            "deep_link_authorized_views": True,
        },
        "disabled_capability_ux": {
            "no_empty_section_shells": True,
            "no_fake_zero": True,
            "governed_unavailable": True,
        },
    }


def modularity_matrix_configs() -> list[dict[str, Any]]:
    """Declarative composition matrix — prove runtime in DB smoke."""
    return [
        {"cell": "workforce_only", "enable": ["c1", "c2", "c6"], "expect_families": ["workforce"]},
        {"cell": "recruiting_only", "enable": ["c1", "c3", "c6"], "expect_families": ["hiring"]},
        {"cell": "time_leave_only", "enable": ["c1", "c4", "c6"], "expect_families": ["time_leave"], "publish_subset": "time_leave"},
        {"cell": "payroll_only", "enable": ["c1", "c4", "c6"], "expect_families": ["pay"], "publish_subset": "payroll"},
        {"cell": "performance_only", "enable": ["c1", "c5", "c6"], "expect_families": ["performance"], "c5_mode": "performance"},
        {"cell": "talent_only", "enable": ["c1", "c5", "c6"], "expect_families": ["talent"], "c5_mode": "talent"},
        {
            "cell": "talent_without_performance",
            "enable": ["c1", "c5", "c6"],
            "expect_families": ["talent"],
            "c5_mode": "talent",
            "performance_off": True,
        },
        {
            "cell": "performance_without_talent",
            "enable": ["c1", "c5", "c6"],
            "expect_families": ["performance"],
            "c5_mode": "performance",
            "talent_off": True,
        },
        {
            "cell": "mixed_operational_subset",
            "enable": ["c1", "c2", "c4", "c6"],
            "expect_families": ["workforce", "time_leave"],
        },
        {
            "cell": "full_intelligence",
            "enable": ["c1", "c2", "c3", "c4", "c5", "c6"],
            "expect_families": ["workforce", "hiring", "time_leave", "pay", "performance", "talent"],
        },
        {"cell": "analytics_disabled", "enable": [], "expect_unavailable": True},
        {
            "cell": "source_module_off_stale_publication",
            "enable": ["c1", "c6"],
            "stale_published": True,
            "expect_unavailable_or_omitted": True,
        },
    ]


def anti_duplication_scan(orch_dir: Path | None = None) -> dict[str, Any]:
    """Source scan: only one Wave 5 evaluator / registry authority."""
    root = orch_dir or Path(__file__).resolve().parent
    modules = [
        "hr_intelligence_registry_c1.py",
        "hr_intelligence_workforce_c2.py",
        "hr_intelligence_recruiting_c3.py",
        "hr_intelligence_time_pay_c4.py",
        "hr_intelligence_perf_talent_c5.py",
        "hr_intelligence_surfaces_c6.py",
        "hr_intelligence_surfaces_http.py",
        "hr_intelligence_product_c7.py",
    ]
    findings: list[str] = []
    c1_eval = "c1.evaluate_kpi("
    second_eval = re.compile(r"def\s+evaluate_kpi\s*\(")
    frontend_formula = re.compile(r"turnover\s*=|/\s*headcount", re.I)
    for name in modules:
        path = root / name
        if not path.exists():
            findings.append(f"missing:{name}")
            continue
        text = path.read_text(encoding="utf-8")
        if name == "hr_intelligence_registry_c1.py":
            if "\ndef evaluate_kpi(" not in text and not text.lstrip().startswith("def evaluate_kpi("):
                # Prefer real definition; allow module-level def
                if re.search(r"(?m)^def evaluate_kpi\(", text) is None:
                    findings.append("c1_missing_evaluate_kpi")
            continue
        if name == "hr_intelligence_product_c7.py":
            # C7 may mention evaluate_kpi in scan strings; forbid a real definition.
            if re.search(r"(?m)^def evaluate_kpi\(", text):
                findings.append("c7_must_not_define_evaluate_kpi")
            continue
        # Domain/surface modules must not define a competing evaluate_kpi
        if re.search(r"(?m)^def evaluate_kpi\(", text):
            findings.append(f"second_evaluate_kpi:{name}")
        if name.endswith("_c6.py") or name.endswith("_http.py"):
            if c1_eval not in text and name.endswith("_c6.py"):
                findings.append("c6_missing_c1_evaluate_call")
            if frontend_formula.search(text):
                findings.append(f"frontend_like_formula:{name}")
    return {
        "ok": len(findings) == 0,
        "findings": findings,
        "single_registry": "hr_intelligence_registry_c1",
        "single_evaluator": "hr_intelligence_registry_c1.evaluate_kpi",
        "scanned": modules,
    }


def bilingual_status_labels() -> dict[str, dict[str, str]]:
    return {
        "ok": {"en": "Available", "ar": "متاح"},
        "zero": {"en": "Zero", "ar": "صفر"},
        "not_applicable": {"en": "Not applicable", "ar": "غير منطبق"},
        "insufficient_data": {"en": "Insufficient data", "ar": "بيانات غير كافية"},
        "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
        "suppressed": {"en": "Suppressed", "ar": "محجوب"},
        "stale": {"en": "Stale", "ar": "قديم"},
        "refreshing": {"en": "Refreshing", "ar": "جارٍ التحديث"},
        "reconciliation_pending": {"en": "Reconciliation pending", "ar": "بانتظار المطابقة"},
    }


def status_label(status: str, *, lang: str = "en") -> str:
    row = bilingual_status_labels().get(str(status or "").strip().lower()) or {}
    return str(row.get("ar" if lang == "ar" else "en") or status)


def acceptance_return_template() -> dict[str, Any]:
    return {
        "stamp": PASS_STAMP,
        "sections": [
            "full_c1_c6_product_prove",
            "kpi_traceability_matrix",
            "modularity_matrix",
            "permission_confidentiality_matrix",
            "historical_reproducibility",
            "reconciliation_correction",
            "ui_export_assistant_parity",
            "en_ar",
            "scale_performance",
            "setup_ownership",
            "anti_duplication_scan",
            "frozen_wave_regressions",
            "genuine_blockers",
            "safe_debt",
        ],
        "stop": "owner_signoff_before_wave6",
        "do_not_begin": [
            "learning_development",
            "benefits",
            "employee_relations",
            "engagement",
            "compensation_planning",
            "workforce_planning",
        ],
    }
