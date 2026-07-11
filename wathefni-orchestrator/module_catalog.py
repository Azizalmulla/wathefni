"""Canonical Wathefni product-module catalog.

This module is intentionally dependency-free so both the FastAPI application
and the tool-call orchestrator can import it without creating an import cycle.
It defines product entitlements only; workspace capabilities such as auth,
team management, organisation settings, and audit access are not modules.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Literal


ModuleSuite = Literal["pre_hire", "post_hire"]
ModuleAudience = Literal["candidate", "employee", "hr"]


@dataclass(frozen=True, slots=True)
class ModuleDefinition:
    key: str
    label: str
    suite: ModuleSuite
    audience: ModuleAudience
    order: int
    people_surface: bool = False
    toolcall_gated: bool = False
    master_flag: str | None = None
    depends_on: tuple[str, ...] = ()
    recommended_with: tuple[str, ...] = ()
    recommendation_copy: str = ""
    # Employee-app surface metadata. "none" means HR-dashboard-first for V1.
    app_surface_key: str | None = None
    app_surface_label: str | None = None


@dataclass(frozen=True, slots=True)
class ModuleBundle:
    id: str
    label: str
    description: str
    modules: tuple[str, ...]


MODULE_CATALOG: tuple[ModuleDefinition, ...] = (
    ModuleDefinition(
        "pre_hiring",
        "Pre-Hiring",
        "pre_hire",
        "candidate",
        10,
        recommendation_copy="Jobs, candidates, and application links for the hiring funnel.",
    ),
    ModuleDefinition(
        "assessments",
        "Assessments",
        "pre_hire",
        "candidate",
        20,
        depends_on=("pre_hiring",),
        recommended_with=("video_interviews",),
        recommendation_copy="Requires Pre-Hiring. Works best with Video Interviews for deeper evaluation.",
    ),
    ModuleDefinition(
        "video_interviews",
        "Video Interviews",
        "pre_hire",
        "candidate",
        30,
        depends_on=("pre_hiring",),
        recommended_with=("assessments",),
        recommendation_copy="Requires Pre-Hiring. Works best with Assessments for a full hiring package.",
    ),
    ModuleDefinition(
        "onboarding",
        "Onboarding",
        "post_hire",
        "employee",
        110,
        True,
        True,
        recommended_with=("compliance", "employee_app"),
        recommendation_copy="Stronger with Compliance document tracking and Employee App self-service.",
        app_surface_key="onboarding",
        app_surface_label="Onboarding tasks",
    ),
    ModuleDefinition(
        "compliance",
        "Compliance",
        "post_hire",
        "employee",
        120,
        True,
        True,
        recommended_with=("onboarding",),
        recommendation_copy="Works alone. Stronger with Onboarding for hire-to-ready readiness.",
        app_surface_key="documents",
        app_surface_label="Documents and expiry reminders",
    ),
    ModuleDefinition(
        "attendance",
        "Attendance",
        "post_hire",
        "employee",
        130,
        True,
        True,
        recommended_with=("shifts",),
        recommendation_copy="Works alone. Recommend Shifts when the company uses scheduled shift work.",
        app_surface_key="attendance",
        app_surface_label="Attendance status",
    ),
    ModuleDefinition(
        "shifts",
        "Shifts",
        "post_hire",
        "employee",
        140,
        True,
        True,
        recommended_with=("attendance",),
        recommendation_copy="Works alone. Clearer with Attendance when punches and scheduled shifts are both tracked.",
        app_surface_key="shifts",
        app_surface_label="Today and upcoming shifts",
    ),
    ModuleDefinition(
        "leave",
        "Leave",
        "post_hire",
        "employee",
        150,
        True,
        True,
        recommended_with=("payroll",),
        recommendation_copy="Works alone. Recommend Payroll Review when leave decisions affect pay.",
        app_surface_key="leave",
        app_surface_label="Leave requests and status",
    ),
    ModuleDefinition(
        "payroll",
        "Payroll",
        "post_hire",
        "employee",
        160,
        True,
        True,
        recommended_with=("attendance", "leave"),
        recommendation_copy="Works alone. Recommend Attendance and Leave so hours and leave feed payroll review. HR-dashboard-first for V1.",
        # Intentionally no employee-app surface in V1.
        app_surface_key=None,
        app_surface_label=None,
    ),
    ModuleDefinition(
        "analytics",
        "Analytics",
        "post_hire",
        "hr",
        170,
        False,
        True,
        recommendation_copy="Insights improve as more operational modules produce data.",
    ),
    ModuleDefinition(
        "employee_app",
        "Employee App",
        "post_hire",
        "employee",
        180,
        False,
        False,
        "WATHEFNI_EMPLOYEE_APP",
        recommended_with=("onboarding", "compliance", "attendance", "shifts", "leave"),
        recommendation_copy="Can be selected alone. Remains inactive until the platform Employee App flag is enabled. Surfaces reflect selected modules.",
        app_surface_key="inbox",
        app_surface_label="In-app inbox and push",
    ),
)

MODULE_BUNDLES: tuple[ModuleBundle, ...] = (
    ModuleBundle(
        "pre_hiring_suite",
        "Pre-Hiring Suite",
        "Jobs, candidates, and application links.",
        ("pre_hiring",),
    ),
    ModuleBundle(
        "hiring_assessment_suite",
        "Hiring Assessment Suite",
        "Full candidate evaluation with assessments and video interviews.",
        ("pre_hiring", "assessments", "video_interviews"),
    ),
    ModuleBundle(
        "core_hr_suite",
        "Core HR Suite",
        "Hire-ready people operations with onboarding, compliance, and leave.",
        ("onboarding", "compliance", "leave"),
    ),
    ModuleBundle(
        "workforce_operations",
        "Workforce Operations",
        "Suggested package for shift-based operations. Modules remain independently removable.",
        ("shifts", "attendance", "leave", "payroll"),
    ),
    ModuleBundle(
        "compliance_onboarding",
        "Compliance & Onboarding",
        "Legal file readiness and employee checklist tracking.",
        ("onboarding", "compliance"),
    ),
    ModuleBundle(
        "employee_self_service",
        "Employee Self-Service / App",
        "Employee App channel. Stays awaiting platform activation until the master flag is ON.",
        ("employee_app",),
    ),
)

MODULE_BY_KEY = {module.key: module for module in MODULE_CATALOG}
MODULE_KEYS = tuple(module.key for module in MODULE_CATALOG)
MODULE_DISPLAY_NAMES = {module.key: module.label for module in MODULE_CATALOG}
PREHIRE_MODULES = tuple(module.key for module in MODULE_CATALOG if module.suite == "pre_hire")
POSTHIRE_MODULES = tuple(module.key for module in MODULE_CATALOG if module.suite == "post_hire" and module.key != "employee_app")
POSTHIRE_PEOPLE_MODULES = tuple(module.key for module in MODULE_CATALOG if module.people_surface)
TOOLCALL_GATED_MODULES = frozenset(module.key for module in MODULE_CATALOG if module.toolcall_gated)
SETUP_CONSOLE_MODULES = MODULE_KEYS
BUNDLE_BY_ID = {bundle.id: bundle for bundle in MODULE_BUNDLES}

# Compatibility aliases are inputs only. In particular, post_hiring is an old
# alias for the onboarding entitlement; it is not itself a product module.
MODULE_ALIASES = {
    "hiring": "pre_hiring",
    "prehire": "pre_hiring",
    "pre_hiring": "pre_hiring",
    "recruiting": "pre_hiring",
    "recruitment": "pre_hiring",
    "assessment": "assessments",
    "assessments": "assessments",
    "testing": "assessments",
    "tests": "assessments",
    "video_interview": "video_interviews",
    "video_interviews": "video_interviews",
    "ai_video_interview": "video_interviews",
    "ai_video_interviews": "video_interviews",
    "onboarding": "onboarding",
    "posthire": "onboarding",
    "post_hiring": "onboarding",
    "post-hiring": "onboarding",
    "compliance": "compliance",
    "pro": "compliance",
    "shifts": "shifts",
    "shift": "shifts",
    "shifting": "shifts",
    "scheduling": "shifts",
    "attendance": "attendance",
    "leave": "leave",
    "payroll": "payroll",
    "analytics": "analytics",
    "insights": "analytics",
    "dashboard": "analytics",
    "reports": "analytics",
    "employee_app": "employee_app",
    "employee_portal": "employee_app",
    "employee_mobile": "employee_app",
}


def normalize_module_key(value: str | None) -> str:
    key = re.sub(r"[^a-z0-9_ -]+", "", (value or "").strip().lower()).replace("-", "_").replace(" ", "_")
    return MODULE_ALIASES.get(key, key)


def expand_module_dependencies(modules: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    """Return modules with hard dependencies auto-included (stable sorted)."""
    selected = {normalize_module_key(key) for key in modules if normalize_module_key(key) in MODULE_BY_KEY}
    changed = True
    while changed:
        changed = False
        for key in list(selected):
            for dependency in MODULE_BY_KEY[key].depends_on:
                if dependency not in selected:
                    selected.add(dependency)
                    changed = True
    return sorted(selected)


def missing_module_dependencies(modules: list[str] | tuple[str, ...] | set[str]) -> list[dict[str, str]]:
    """Return hard dependency violations without auto-including anything."""
    selected = {normalize_module_key(key) for key in modules if normalize_module_key(key) in MODULE_BY_KEY}
    missing: list[dict[str, str]] = []
    for key in sorted(selected):
        for dependency in MODULE_BY_KEY[key].depends_on:
            if dependency not in selected:
                missing.append({
                    "module": key,
                    "requires": dependency,
                    "message": f"{MODULE_DISPLAY_NAMES[key]} requires {MODULE_DISPLAY_NAMES[dependency]}.",
                })
    return missing


def app_surfaces_for_modules(modules: list[str] | tuple[str, ...] | set[str]) -> list[dict[str, object]]:
    """Employee-app surfaces implied by the currently selected modules."""
    selected = {normalize_module_key(key) for key in modules if normalize_module_key(key) in MODULE_BY_KEY}
    surfaces: list[dict[str, object]] = []
    employee_app_selected = "employee_app" in selected
    for module in MODULE_CATALOG:
        if not module.app_surface_key:
            continue
        if module.key == "employee_app":
            if employee_app_selected:
                surfaces.append({
                    "module_key": module.key,
                    "surface_key": module.app_surface_key,
                    "label": module.app_surface_label,
                    "available_when_app_live": True,
                })
            continue
        if module.key in selected and employee_app_selected:
            surfaces.append({
                "module_key": module.key,
                "surface_key": module.app_surface_key,
                "label": module.app_surface_label,
                "available_when_app_live": True,
            })
    return surfaces


def module_bundles_payload() -> list[dict[str, object]]:
    return [asdict(bundle) for bundle in MODULE_BUNDLES]


def module_catalog_payload() -> list[dict[str, object]]:
    """JSON-safe, stable-order metadata for Setup Console and dashboard boot."""
    return [asdict(module) for module in MODULE_CATALOG]
