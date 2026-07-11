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


MODULE_CATALOG: tuple[ModuleDefinition, ...] = (
    ModuleDefinition("pre_hiring", "Pre-Hiring", "pre_hire", "candidate", 10),
    ModuleDefinition("assessments", "Assessments", "pre_hire", "candidate", 20),
    ModuleDefinition("video_interviews", "Video Interviews", "pre_hire", "candidate", 30),
    ModuleDefinition("onboarding", "Onboarding", "post_hire", "employee", 110, True, True),
    ModuleDefinition("compliance", "Compliance", "post_hire", "employee", 120, True, True),
    ModuleDefinition("attendance", "Attendance", "post_hire", "employee", 130, True, True),
    ModuleDefinition("shifts", "Shifts", "post_hire", "employee", 140, True, True),
    ModuleDefinition("leave", "Leave", "post_hire", "employee", 150, True, True),
    ModuleDefinition("payroll", "Payroll", "post_hire", "employee", 160, True, True),
    ModuleDefinition("analytics", "Analytics", "post_hire", "hr", 170, False, True),
    ModuleDefinition(
        "employee_app",
        "Employee App",
        "post_hire",
        "employee",
        180,
        False,
        False,
        "WATHEFNI_EMPLOYEE_APP",
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


def module_catalog_payload() -> list[dict[str, object]]:
    """JSON-safe, stable-order metadata for Setup Console and dashboard boot."""
    return [asdict(module) for module in MODULE_CATALOG]
