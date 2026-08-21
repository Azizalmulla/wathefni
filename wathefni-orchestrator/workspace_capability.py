"""Shared Wathefni workspace capability authority (backend mirror).

Keep surface rules in sync with:
  apps/wathefni-dashboard/src/lib/workspaceCapability.ts
"""

from __future__ import annotations

from typing import Any

OWNER_PERMISSIONS = [
    "candidate.manage",
    "candidates.read",
    "jobs.create",
    "jobs.read",
    "jobs.edit",
    "jobs.publish",
    "jobs.close",
    "report.export",
    "prehire.read",
    "assessment.manage",
    "interview.manage",
    "calendar.read",
    "leave.read",
    "attendance.read",
    "onboarding.read",
    "payroll.read",
    "shifts.read",
    "compliance.read",
    "analytics.read",
    "performance.read",
    "employees.read",
    "settings.manage",
    "users.manage",
    "audit.read",
]

RECRUITER_PERMISSIONS = [
    "prehire.read",
    "candidates.read",
    "jobs.read",
    "interview.manage",
]

PEOPLE_MODULES = {"onboarding", "attendance", "leave", "payroll", "shifts", "compliance", "performance"}
POSTHIRE_MODULES = PEOPLE_MODULES | {"analytics"}

# Deterministic primary when several workforce modules are on and Inbox is not used.
POSTHIRE_OPERATIONAL_LANDING_PRIORITY = (
    "leave",
    "attendance",
    "shifts",
    "payroll",
    "onboarding",
    "compliance",
    "analytics",
)

# (id, kind, page, group, module, module_any_of, permission, permission_any_of, jobs_permission)
WORKSPACE_SURFACES: list[dict[str, Any]] = [
    {"id": "nav.overview", "kind": "nav", "page": "overview", "group": "prehire", "module": "pre_hiring", "permission_any_of": ["candidate.manage", "jobs.create", "report.export"]},
    {"id": "nav.ai", "kind": "nav", "page": "ai", "group": "prehire", "module_any_of": ["pre_hiring", "leave", "attendance", "onboarding", "shifts", "payroll", "compliance", "analytics"], "permission_any_of": ["candidate.manage", "jobs.create", "report.export", "leave.read", "attendance.read", "onboarding.read", "payroll.read"]},
    {"id": "nav.jobs", "kind": "nav", "page": "jobs", "group": "prehire", "module": "pre_hiring", "jobs_permission": "jobs.read"},
    {"id": "nav.candidates", "kind": "nav", "page": "candidates", "group": "prehire", "module": "pre_hiring", "permission": "candidates.read"},
    {"id": "nav.interviews", "kind": "nav", "page": "interviews", "group": "prehire", "module_any_of": ["interviews", "video_interviews"], "permission": "prehire.read"},
    {"id": "nav.calendar", "kind": "nav", "page": "calendar", "group": "prehire", "module": "calendar", "permission": "calendar.read"},
    {"id": "nav.assessments", "kind": "nav", "page": "assessments", "group": "prehire", "module": "assessments", "permission": "assessment.manage"},
    {"id": "nav.ranking", "kind": "nav", "page": "ranking", "group": "prehire", "module": "pre_hiring", "permission_any_of": ["candidate.manage", "jobs.create", "report.export"]},
    {"id": "nav.reports", "kind": "nav", "page": "reports", "group": "prehire", "module": "pre_hiring", "permission": "report.export"},
    {"id": "nav.employees", "kind": "nav", "page": "employees", "group": "posthire", "permission": "employees.read"},
    {"id": "nav.onboarding", "kind": "nav", "page": "onboarding", "group": "posthire", "module": "onboarding", "permission": "onboarding.read"},
    {"id": "nav.attendance", "kind": "nav", "page": "attendance", "group": "posthire", "module": "attendance", "permission": "attendance.read"},
    {"id": "nav.leave", "kind": "nav", "page": "leave", "group": "posthire", "module": "leave", "permission": "leave.read"},
    {"id": "nav.performance", "kind": "nav", "page": "performance", "group": "posthire", "module": "performance", "permission": "performance.read"},
    {"id": "nav.talent", "kind": "nav", "page": "talent", "group": "posthire", "module": "talent", "permission": "talent.read"},
    {"id": "nav.learning", "kind": "nav", "page": "learning", "group": "posthire", "module": "learning", "permission": "learning.read"},
    {"id": "nav.benefits", "kind": "nav", "page": "benefits", "group": "posthire", "module": "benefits", "permission": "benefits.read"},
    {"id": "nav.job-architecture", "kind": "nav", "page": "job-architecture", "group": "posthire", "permission": "job_architecture.read"},
    {"id": "nav.shifts", "kind": "nav", "page": "shifts", "group": "posthire", "module": "shifts", "permission": "shifts.read"},
    {"id": "nav.payroll", "kind": "nav", "page": "payroll", "group": "posthire", "module": "payroll", "permission": "payroll.read"},
    {"id": "nav.analytics", "kind": "nav", "page": "analytics", "group": "posthire", "module": "analytics", "permission": "analytics.read"},
    {"id": "nav.compliance", "kind": "nav", "page": "compliance", "group": "posthire", "module": "compliance", "permission": "compliance.read"},
    {"id": "nav.notifications", "kind": "nav", "page": "notifications", "group": "settings"},
    {"id": "nav.activity", "kind": "nav", "page": "activity", "group": "settings", "permission": "audit.read"},
    {"id": "nav.settings", "kind": "nav", "page": "settings", "group": "settings", "permission_any_of": ["settings.manage", "users.manage"]},
    {"id": "overview.action.review", "kind": "overview", "module": "pre_hiring", "permission": "candidates.read"},
    {"id": "overview.action.assessment", "kind": "overview", "module": "assessments", "permission": "assessment.manage"},
    {"id": "overview.action.followup", "kind": "overview", "module": "pre_hiring", "permission": "candidates.read"},
    {"id": "overview.work_queue", "kind": "overview", "module_any_of": ["pre_hiring", "assessments", "interviews", "employment_offers", "requisitions", "preboarding", "probation", "analytics", "compliance", "onboarding", "attendance", "leave", "shifts", "performance", "learning", "benefits", "employee_relations", "engagement", "comp_planning", "workforce_planning"], "permission_any_of": ["candidate.manage", "jobs.create", "report.export", "candidates.read", "assessment.manage", "interview.manage", "offer.approve", "requisitions.approve", "preboarding.manage", "probation.manage", "analytics.read", "compliance.read", "onboarding.manage", "leave.decide", "attendance.manage", "shifts.manage", "performance.manage", "learning.approve", "benefits.manage", "er.read", "engagement.actions", "comp_planning.approve", "workforce_planning.approve", "employees.read"]},
    {"id": "overview.role_priority", "kind": "overview", "module": "pre_hiring", "permission_any_of": ["candidate.manage", "jobs.create", "report.export"]},
    {"id": "overview.calendar", "kind": "overview", "module": "calendar", "permission": "calendar.read"},
    {"id": "overview.approvals", "kind": "overview", "module_any_of": ["analytics", "compliance", "onboarding", "attendance", "leave", "shifts", "payroll"], "permission_any_of": ["analytics.read", "compliance.read", "onboarding.read", "attendance.read", "leave.read", "shifts.read", "payroll.read", "employees.read"]},
    {"id": "overview.signals", "kind": "overview", "module": "analytics", "permission": "analytics.read"},
    {"id": "tab.interviews.video", "kind": "tab", "module": "video_interviews", "permission": "interview.manage"},
    {"id": "settings.team", "kind": "settings", "permission": "users.manage"},
    {"id": "settings.integrations", "kind": "settings", "permission": "settings.manage"},
    {"id": "settings.platform", "kind": "settings", "permission": "settings.manage"},
]

COMPOSITION_MATRIX = [
    {
        "id": "one_module_prehire",
        "label": "One enabled module (pre_hiring)",
        "modules": ["pre_hiring"],
        "role": "owner",
        "expect_nav_groups": ["prehire", "settings"],
        "expect_nav_includes": ["overview", "jobs", "candidates", "ai"],
        "expect_nav_excludes": ["payroll", "assessments", "attendance", "interviews"],
        "expect_overview_layout": "two",
    },
    {
        "id": "two_modules",
        "label": "Two modules (pre_hiring + assessments)",
        "modules": ["pre_hiring", "assessments"],
        "role": "owner",
        "expect_nav_groups": ["prehire", "settings"],
        "expect_nav_includes": ["overview", "assessments", "jobs"],
        "expect_nav_excludes": ["payroll", "leave", "interviews"],
        "expect_overview_layout": "three",
    },
    {
        "id": "three_four_modules",
        "label": "Three to four modules",
        "modules": ["pre_hiring", "assessments", "interviews", "calendar"],
        "role": "owner",
        "expect_nav_groups": ["prehire", "settings"],
        "expect_nav_includes": ["interviews", "calendar", "assessments"],
        "expect_nav_excludes": ["payroll"],
        "expect_overview_layout": "three",
    },
    {
        "id": "full_prehiring",
        "label": "Full pre-hiring",
        "modules": ["pre_hiring", "assessments", "interviews", "video_interviews", "calendar"],
        "role": "owner",
        "expect_nav_groups": ["prehire", "settings"],
        "expect_nav_includes": ["overview", "ai", "jobs", "candidates", "interviews", "calendar", "assessments", "ranking", "reports"],
        "expect_nav_excludes": ["payroll", "onboarding"],
        "expect_overview_layout": "three",
    },
    {
        "id": "posthire_only",
        "label": "Post-hire only",
        "modules": ["onboarding", "attendance", "leave", "payroll"],
        "role": "owner",
        "expect_nav_groups": ["posthire", "settings"],
        "expect_nav_includes": ["overview", "ai", "onboarding", "attendance", "leave", "payroll", "employees"],
        "expect_nav_excludes": ["jobs", "candidates", "assessments"],
        "expect_overview_layout": "none",
    },
    {
        "id": "mixed",
        "label": "Mixed pre/post-hire",
        "modules": ["pre_hiring", "assessments", "leave", "attendance"],
        "role": "owner",
        "expect_nav_groups": ["prehire", "posthire", "settings"],
        "expect_nav_includes": ["overview", "assessments", "leave", "attendance"],
        "expect_nav_excludes": ["payroll", "interviews"],
        "expect_overview_layout": "three",
    },
    {
        "id": "restricted_recruiter",
        "label": "Restricted recruiter vs owner",
        "modules": ["pre_hiring", "assessments", "interviews", "leave", "payroll"],
        "role": "recruiter",
        "expect_nav_groups": ["prehire", "settings"],
        "expect_nav_includes": ["jobs", "candidates", "interviews"],
        "expect_nav_excludes": ["overview", "ai", "ranking", "reports", "payroll", "assessments"],
        "expect_overview_layout": "two",
    },
]


def _perm_ok(perms: set[str], required: str | None) -> bool:
    if not required:
        return True
    return required in perms or "*:*" in perms


def _any_perm_ok(perms: set[str], required: list[str] | None) -> bool:
    if not required:
        return True
    return any(_perm_ok(perms, p) for p in required)


def _module_ok(enabled: set[str], surface: dict[str, Any]) -> bool:
    sid = surface["id"]
    if sid == "nav.employees":
        return bool(enabled & PEOPLE_MODULES)
    if sid == "nav.notifications":
        return "pre_hiring" in enabled or bool(enabled & POSTHIRE_MODULES)
    any_of = surface.get("module_any_of")
    if any_of:
        return any(m in enabled for m in any_of)
    module = surface.get("module")
    if not module:
        return True
    return module in enabled


def resolve_surface(surface: dict[str, Any], enabled: set[str], perms: set[str]) -> dict[str, Any]:
    row = dict(surface)
    if not _module_ok(enabled, surface):
        row["status"] = "module_off"
        row["offerable"] = False
        return row
    if surface.get("jobs_permission") and not _perm_ok(perms, surface["jobs_permission"]):
        row["status"] = "permission_denied"
        row["offerable"] = False
        return row
    if surface.get("permission") and not _perm_ok(perms, surface["permission"]):
        row["status"] = "permission_denied"
        row["offerable"] = False
        return row
    if surface.get("permission_any_of") and not _any_perm_ok(perms, surface["permission_any_of"]):
        row["status"] = "permission_denied"
        row["offerable"] = False
        return row
    row["status"] = "available"
    row["offerable"] = True
    return row


def compose_overview_layout(surfaces: dict[str, dict[str, Any]]) -> str:
    priority = [
        sid
        for sid in ("overview.action.review", "overview.action.assessment", "overview.action.followup")
        if surfaces.get(sid, {}).get("offerable")
    ]
    n = len(priority)
    if n <= 0:
        return "none"
    if n == 1:
        return "one"
    if n == 2:
        return "two"
    if n == 3:
        return "three"
    return "grid"


def resolve_workspace_authority(modules: list[str], role: str) -> dict[str, Any]:
    enabled = set(modules)
    perms = set(OWNER_PERMISSIONS if role == "owner" else RECRUITER_PERMISSIONS)
    surfaces = {s["id"]: resolve_surface(s, enabled, perms) for s in WORKSPACE_SURFACES}

    # Move Assistant into posthire group when pre_hiring is off.
    ai = surfaces.get("nav.ai")
    if ai and ai.get("offerable") and "pre_hiring" not in enabled:
        surfaces["nav.ai"] = {**ai, "group": "posthire"}

    # Overview is module-composed: recruiting off must not hide the company home.
    overview = surfaces.get("nav.overview")
    if overview and not overview.get("offerable") and "pre_hiring" not in enabled:
        any_posthire = any(
            surfaces[s["id"]].get("offerable")
            for s in WORKSPACE_SURFACES
            if s.get("kind") == "nav" and surfaces[s["id"]].get("group") == "posthire"
        )
        any_band = any(
            surfaces.get(sid, {}).get("offerable")
            for sid in ("overview.calendar", "overview.approvals", "overview.signals")
        )
        if any_posthire or any_band:
            surfaces["nav.overview"] = {
                **overview,
                "offerable": True,
                "status": "available",
                "group": "posthire",
            }

    group_order = ("prehire", "posthire", "settings")
    nav_groups = []
    nav_ids: list[str] = []
    for group in group_order:
        ids = [
            str(surfaces[s["id"]]["page"])
            for s in WORKSPACE_SURFACES
            if s["kind"] == "nav"
            and surfaces[s["id"]].get("offerable")
            and surfaces[s["id"]].get("group") == group
        ]
        if ids:
            nav_groups.append({"group": group, "ids": ids})
            nav_ids.extend(ids)

    return {
        "nav_ids": nav_ids,
        "nav_groups": [g["group"] for g in nav_groups],
        "nav_group_detail": nav_groups,
        "overview_layout": compose_overview_layout(surfaces),
        "surfaces": surfaces,
        "offerable": {sid: bool(row.get("offerable")) for sid, row in surfaces.items()},
    }


def action_inbox_has_entitled_source(enabled: set[str], perms: set[str]) -> bool:
    if "analytics" in enabled and _perm_ok(perms, "analytics.read"):
        return True
    if "compliance" in enabled and _perm_ok(perms, "compliance.read"):
        return True
    if enabled & PEOPLE_MODULES and _perm_ok(perms, "employees.read"):
        return True
    return False


def resolve_focused_posthire_landing(
    modules: list[str],
    *,
    role: str = "owner",
    available_pages: list[str] | None = None,
    action_inbox_offerable: bool = False,
) -> str:
    """Mirror of dashboard resolveFocusedPosthireLanding for matrix proofs."""
    enabled = set(modules)
    perms = set(OWNER_PERMISSIONS if role == "owner" else RECRUITER_PERMISSIONS)
    authority = resolve_workspace_authority(modules, role)
    available = set(available_pages if available_pages is not None else authority["nav_ids"])
    # Frontend also requires inbox in nav surfaces; backend mirror may lack nav.inbox — accept explicit available_pages.
    if "pre_hiring" in enabled and "overview" in available:
        return "overview"
    operational = [p for p in POSTHIRE_OPERATIONAL_LANDING_PRIORITY if p in enabled and p in available]
    if len(operational) == 1:
        return operational[0]
    if len(operational) >= 2:
        if action_inbox_offerable and "inbox" in available and action_inbox_has_entitled_source(enabled, perms):
            return "inbox"
        return operational[0]
    if "employees" in available:
        return "employees"
    if action_inbox_offerable and "inbox" in available:
        return "inbox"
    return next(iter(available), "settings")


def authority_fixture_for_matrix_row(row: dict[str, Any]) -> dict[str, Any]:
    authority = resolve_workspace_authority(row["modules"], row["role"])
    return {
        "id": row["id"],
        "label": row["label"],
        "modules": row["modules"],
        "role": row["role"],
        "nav_groups": authority["nav_groups"],
        "nav_ids": authority["nav_ids"],
        "overview_layout": authority["overview_layout"],
        "offerable_tabs": {
            "video_interviews": authority["offerable"].get("tab.interviews.video", False),
        },
        "settings": {
            "team": authority["offerable"].get("settings.team", False),
            "integrations": authority["offerable"].get("settings.integrations", False),
        },
    }
