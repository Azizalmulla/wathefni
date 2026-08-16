"""Versioned tenant control-plane product and capability catalog (Wave 1).

Distinguishes:

- business modules purchased by the company
- internal sub-capabilities
- hidden technical dependencies
- UI surfaces / APIs / workers / timers / webhooks / notifications / integrations

Candidate Knowledge and Talent Pool remain backend capabilities under the single
HR-facing Candidates product area (commercial module: pre_hiring).

This catalog is additive and shadow-friendly. Live entitlement reads continue to
use `module_catalog` + `company_modules` until a later wave flips authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


CATALOG_VERSION = "tenant-control-catalog-v1"

CapabilityKind = Literal[
    "business_module",
    "sub_capability",
    "hidden_technical",
    "ui_surface",
    "api",
    "worker",
    "timer",
    "webhook",
    "notification",
    "integration",
]

DependencyClass = Literal["technical", "commercial"]
GrantMode = Literal["purchased", "implied_technical", "compatibility", "flag_gated"]


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    key: str
    label: str
    kind: CapabilityKind
    product_area: str
    hr_visible: bool = False
    commercial: bool = False
    legacy_module_key: str | None = None
    depends_on: tuple[str, ...] = ()
    dependency_class: DependencyClass = "technical"
    grant_mode: GrantMode = "purchased"
    surfaces: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ProductAreaDefinition:
    key: str
    label: str
    hr_nav_label: str
    commercial_module: str | None


PRODUCT_AREAS: tuple[ProductAreaDefinition, ...] = (
    ProductAreaDefinition("candidates", "Candidates", "Candidates", "pre_hiring"),
    ProductAreaDefinition("assessments", "Assessments", "Assessments", "assessments"),
    ProductAreaDefinition("interviews", "Interviews", "Interviews", "interviews"),
    ProductAreaDefinition("video_interviews", "Video Interviews", "Video Interviews", "video_interviews"),
    ProductAreaDefinition("offers", "Employment Offers", "Offers", "employment_offers"),
    ProductAreaDefinition("onboarding", "Onboarding", "Onboarding", "onboarding"),
    ProductAreaDefinition("compliance", "Compliance", "Compliance", "compliance"),
    ProductAreaDefinition("attendance", "Attendance", "Attendance", "attendance"),
    ProductAreaDefinition("shifts", "Shifts", "Shifts", "shifts"),
    ProductAreaDefinition("leave", "Leave", "Leave", "leave"),
    ProductAreaDefinition("payroll", "Payroll", "Payroll", "payroll"),
    ProductAreaDefinition("analytics", "Analytics", "Analytics", "analytics"),
    ProductAreaDefinition("employee_app", "Employee App", "Employee App", "employee_app"),
    ProductAreaDefinition("platform", "Platform", "Workspace", None),
)

CAPABILITY_CATALOG: tuple[CapabilityDefinition, ...] = (
    # --- Purchased business modules (1:1 with module_catalog commercial keys) ---
    CapabilityDefinition(
        "mod.pre_hiring",
        "Pre-Hiring",
        "business_module",
        "candidates",
        hr_visible=True,
        commercial=True,
        legacy_module_key="pre_hiring",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile", "intake"),
        notes="Single HR-facing Candidates product area. Owns jobs, applications, and intake.",
    ),
    CapabilityDefinition(
        "mod.assessments",
        "Assessments",
        "business_module",
        "assessments",
        hr_visible=True,
        commercial=True,
        legacy_module_key="assessments",
        depends_on=("mod.pre_hiring",),
        dependency_class="commercial",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile", "workers"),
    ),
    CapabilityDefinition(
        "mod.interviews",
        "Interviews (live scheduled)",
        "business_module",
        "interviews",
        hr_visible=True,
        commercial=True,
        legacy_module_key="interviews",
        depends_on=("mod.pre_hiring",),
        dependency_class="commercial",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile", "timers", "notifications"),
        notes="Protected compatibility capability for Setup Console bulk saves.",
    ),
    CapabilityDefinition(
        "mod.video_interviews",
        "Video Interviews (async recorded)",
        "business_module",
        "video_interviews",
        hr_visible=True,
        commercial=True,
        legacy_module_key="video_interviews",
        depends_on=("mod.pre_hiring",),
        dependency_class="commercial",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "workers", "webhooks", "notifications"),
    ),
    CapabilityDefinition(
        "mod.employment_offers",
        "Employment Offers",
        "business_module",
        "offers",
        hr_visible=True,
        commercial=True,
        legacy_module_key="employment_offers",
        depends_on=("mod.pre_hiring",),
        dependency_class="commercial",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "notifications"),
    ),
    CapabilityDefinition(
        "mod.onboarding",
        "Onboarding",
        "business_module",
        "onboarding",
        hr_visible=True,
        commercial=True,
        legacy_module_key="onboarding",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile", "timers", "notifications"),
    ),
    CapabilityDefinition(
        "mod.compliance",
        "Compliance",
        "business_module",
        "compliance",
        hr_visible=True,
        commercial=True,
        legacy_module_key="compliance",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile", "timers", "notifications"),
    ),
    CapabilityDefinition(
        "mod.attendance",
        "Attendance",
        "business_module",
        "attendance",
        hr_visible=True,
        commercial=True,
        legacy_module_key="attendance",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile"),
    ),
    CapabilityDefinition(
        "mod.shifts",
        "Shifts",
        "business_module",
        "shifts",
        hr_visible=True,
        commercial=True,
        legacy_module_key="shifts",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile", "timers", "notifications"),
    ),
    CapabilityDefinition(
        "mod.leave",
        "Leave",
        "business_module",
        "leave",
        hr_visible=True,
        commercial=True,
        legacy_module_key="leave",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools", "mobile", "workers", "timers"),
    ),
    CapabilityDefinition(
        "mod.payroll",
        "Payroll",
        "business_module",
        "payroll",
        hr_visible=True,
        commercial=True,
        legacy_module_key="payroll",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools"),
    ),
    CapabilityDefinition(
        "mod.analytics",
        "Analytics",
        "business_module",
        "analytics",
        hr_visible=True,
        commercial=True,
        legacy_module_key="analytics",
        grant_mode="purchased",
        surfaces=("navigation", "direct_routes", "apis", "ai_tools"),
    ),
    CapabilityDefinition(
        "mod.employee_app",
        "Employee App",
        "business_module",
        "employee_app",
        hr_visible=True,
        commercial=True,
        legacy_module_key="employee_app",
        grant_mode="flag_gated",
        surfaces=("mobile", "apis", "notifications"),
        notes="Requires platform master flag WATHEFNI_EMPLOYEE_APP.",
    ),
    # --- Backend capabilities under Candidates (not separate HR products) ---
    CapabilityDefinition(
        "cap.candidate_knowledge",
        "Candidate Knowledge",
        "sub_capability",
        "candidates",
        hr_visible=False,
        commercial=False,
        depends_on=("mod.pre_hiring",),
        dependency_class="technical",
        grant_mode="implied_technical",
        surfaces=("apis", "ai_tools", "workers"),
        notes="Backend capability under Candidates. Not a purchasable Setup Console module.",
    ),
    CapabilityDefinition(
        "cap.talent_pool",
        "Talent Pool",
        "sub_capability",
        "candidates",
        hr_visible=False,
        commercial=False,
        depends_on=("mod.pre_hiring",),
        dependency_class="technical",
        grant_mode="implied_technical",
        surfaces=("apis", "ai_tools", "workers", "intake"),
        notes="Backend capability under Candidates. Classification is flag-gated, not a module.",
    ),
    CapabilityDefinition(
        "cap.unified_inbound_cv",
        "Unified Inbound CV Pipeline",
        "hidden_technical",
        "candidates",
        depends_on=("mod.pre_hiring",),
        dependency_class="technical",
        grant_mode="flag_gated",
        surfaces=("intake", "workers", "webhooks", "apis"),
        notes="Frozen production pipeline; tenant allowlists remain env-scoped.",
    ),
    CapabilityDefinition(
        "cap.verified_job_binding",
        "Verified Job Binding Gate",
        "hidden_technical",
        "candidates",
        depends_on=("cap.unified_inbound_cv",),
        dependency_class="technical",
        grant_mode="flag_gated",
        surfaces=("intake", "apis", "ai_tools"),
        notes="ENFORCE allowlisted to WATHEFNI only.",
    ),
    # --- Hidden technical / compatibility ---
    CapabilityDefinition(
        "cap.interviews_compatibility",
        "Live Interviews Compatibility Shield",
        "hidden_technical",
        "interviews",
        legacy_module_key="interviews",
        depends_on=("mod.interviews",),
        dependency_class="technical",
        grant_mode="compatibility",
        surfaces=("apis", "ai_tools"),
        notes="Prevents Setup Console bulk saves from disabling live interviews.",
    ),
    # --- Platform integrations (not commercial modules) ---
    CapabilityDefinition(
        "int.whatsapp_octopus",
        "WhatsApp (Octopus)",
        "integration",
        "platform",
        grant_mode="flag_gated",
        surfaces=("integrations", "notifications", "webhooks"),
        notes="Platform-global today; company channel accounts flag OFF.",
    ),
    CapabilityDefinition(
        "int.email_postmark",
        "Email (Postmark)",
        "integration",
        "platform",
        grant_mode="flag_gated",
        surfaces=("integrations", "intake", "notifications", "webhooks"),
    ),
    CapabilityDefinition(
        "int.gmail_gog",
        "Gmail (gog)",
        "integration",
        "platform",
        grant_mode="flag_gated",
        surfaces=("integrations", "intake"),
        notes="Live mailbox import blocked pending durable scan authority.",
    ),
    # --- Representative UI / API / worker surfaces for shadow matrix ---
    CapabilityDefinition(
        "ui.dashboard_nav",
        "HR Dashboard Navigation",
        "ui_surface",
        "platform",
        hr_visible=True,
        grant_mode="implied_technical",
        surfaces=("navigation",),
    ),
    CapabilityDefinition(
        "api.require_entitlement",
        "HTTP require_entitlement Gate",
        "api",
        "platform",
        grant_mode="implied_technical",
        surfaces=("apis", "direct_routes"),
    ),
    CapabilityDefinition(
        "api.ai_tools",
        "AI Tool Entitlement Gate",
        "api",
        "platform",
        grant_mode="implied_technical",
        surfaces=("ai_tools",),
    ),
    CapabilityDefinition(
        "worker.video_interview",
        "Video Interview Worker",
        "worker",
        "video_interviews",
        depends_on=("mod.video_interviews",),
        dependency_class="technical",
        grant_mode="implied_technical",
        surfaces=("workers",),
        notes="Legacy worker currently lacks universal module gate (Wave 2).",
    ),
    CapabilityDefinition(
        "worker.candidate_knowledge_index",
        "Candidate Knowledge Index Worker",
        "worker",
        "candidates",
        depends_on=("cap.candidate_knowledge",),
        dependency_class="technical",
        grant_mode="implied_technical",
        surfaces=("workers", "queue_claims"),
    ),
    CapabilityDefinition(
        "worker.inbound_cv",
        "Inbound CV / Durable Email Workers",
        "worker",
        "candidates",
        depends_on=("cap.unified_inbound_cv",),
        dependency_class="technical",
        grant_mode="flag_gated",
        surfaces=("workers", "queue_claims", "webhooks", "intake"),
    ),
    CapabilityDefinition(
        "timer.module_automation",
        "Module Automation Timers",
        "timer",
        "platform",
        grant_mode="implied_technical",
        surfaces=("timers",),
        notes="Uses company_module_automation_enabled for selected reminder paths.",
    ),
    CapabilityDefinition(
        "notify.outbound_delivery",
        "Outbound Delivery / Notifications",
        "notification",
        "platform",
        grant_mode="flag_gated",
        surfaces=("notifications", "outbound_notifications"),
    ),
)

CAPABILITY_BY_KEY = {item.key: item for item in CAPABILITY_CATALOG}
PRODUCT_AREA_BY_KEY = {item.key: item for item in PRODUCT_AREAS}

LEGACY_MODULE_TO_CAPABILITY = {
    item.legacy_module_key: item.key
    for item in CAPABILITY_CATALOG
    if item.legacy_module_key and item.kind == "business_module"
}

SHADOW_SURFACES: tuple[str, ...] = (
    "navigation",
    "direct_routes",
    "apis",
    "ai_tools",
    "mobile",
    "workers",
    "timers",
    "queue_claims",
    "webhooks",
    "intake",
    "outbound_notifications",
)


def catalog_payload() -> dict[str, object]:
    return {
        "catalog_version": CATALOG_VERSION,
        "product_areas": [asdict(item) for item in PRODUCT_AREAS],
        "capabilities": [
            {
                **asdict(item),
                "depends_on": list(item.depends_on),
                "surfaces": list(item.surfaces),
            }
            for item in CAPABILITY_CATALOG
        ],
        "legacy_module_to_capability": dict(LEGACY_MODULE_TO_CAPABILITY),
        "shadow_surfaces": list(SHADOW_SURFACES),
    }


def commercial_dependency_gaps(enabled_capability_keys: set[str]) -> list[dict[str, str]]:
    """Commercial deps block publish; technical deps may be auto-granted."""
    gaps: list[dict[str, str]] = []
    for key in sorted(enabled_capability_keys):
        item = CAPABILITY_BY_KEY.get(key)
        if not item:
            continue
        for dep in item.depends_on:
            dep_item = CAPABILITY_BY_KEY.get(dep)
            if not dep_item:
                continue
            if dep in enabled_capability_keys:
                continue
            if item.dependency_class == "commercial" or dep_item.commercial:
                gaps.append(
                    {
                        "capability": key,
                        "requires": dep,
                        "dependency_class": "commercial",
                        "message": f"{item.label} requires purchased module {dep_item.label}.",
                    }
                )
    return gaps


def technical_dependencies_to_grant(enabled_capability_keys: set[str]) -> set[str]:
    """Return technical (non-commercial) dependencies that may be granted internally."""
    grants: set[str] = set()
    pending = set(enabled_capability_keys)
    changed = True
    while changed:
        changed = False
        for key in list(pending):
            item = CAPABILITY_BY_KEY.get(key)
            if not item:
                continue
            for dep in item.depends_on:
                dep_item = CAPABILITY_BY_KEY.get(dep)
                if not dep_item or dep_item.commercial:
                    continue
                if dep not in pending:
                    pending.add(dep)
                    grants.add(dep)
                    changed = True
    return grants
