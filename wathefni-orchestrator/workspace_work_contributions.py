"""Permanent module → work-contribution contract for GET /dashboard/work.

Every catalog module must declare exactly one of:
  - My Work (canonically assigned to the actor)
  - Company Attention (unresolved / unassigned / supervisory the actor may oversee)
  - no contribution, with an explicit omit_reason

Loaders only wrap existing module queues / inbox rows. They do not invent
assignees where the source domain has none.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from module_catalog import MODULE_KEYS


@dataclass(frozen=True, slots=True)
class ModuleWorkContribution:
    module: str
    mine: bool
    attention: bool
    omit_reason: str | None
    mine_permissions: tuple[str, ...]
    attention_permissions: tuple[str, ...]
    loader: str
    authority_source: str
    destination_page: str | None
    assignee_fields: tuple[str, ...]


def _none(
    module: str,
    *,
    reason: str,
    destination_page: str | None = None,
) -> ModuleWorkContribution:
    return ModuleWorkContribution(
        module=module,
        mine=False,
        attention=False,
        omit_reason=reason,
        mine_permissions=(),
        attention_permissions=(),
        loader="",
        authority_source="",
        destination_page=destination_page,
        assignee_fields=(),
    )


def _contrib(
    module: str,
    *,
    mine: bool,
    attention: bool,
    loader: str,
    authority_source: str,
    destination_page: str,
    mine_permissions: tuple[str, ...] = (),
    attention_permissions: tuple[str, ...] = (),
    assignee_fields: tuple[str, ...] = (),
) -> ModuleWorkContribution:
    return ModuleWorkContribution(
        module=module,
        mine=mine,
        attention=attention,
        omit_reason=None,
        mine_permissions=mine_permissions,
        attention_permissions=attention_permissions,
        loader=loader,
        authority_source=authority_source,
        destination_page=destination_page,
        assignee_fields=assignee_fields,
    )


# One row per MODULE_CATALOG key. Order follows the catalog.
MODULE_WORK_CONTRIBUTIONS: tuple[ModuleWorkContribution, ...] = (
    _contrib(
        "pre_hiring",
        mine=True,
        attention=True,
        loader="prehire_personal_work",
        authority_source="prehire_personal_work.build_scoped_work_queue",
        destination_page="candidates",
        mine_permissions=("prehire.read", "candidates.read", "candidate.manage"),
        attention_permissions=("prehire.read", "candidates.read", "candidate.manage"),
        assignee_fields=("owner_user_id", "recruiter_user_id", "hiring_manager_user_id"),
    ),
    _contrib(
        "assessments",
        mine=True,
        attention=True,
        loader="prehire_personal_work",
        authority_source="prehire_personal_work.build_scoped_work_queue",
        destination_page="assessments",
        mine_permissions=("assessment.manage", "candidates.read"),
        attention_permissions=("assessment.manage", "candidates.read"),
        assignee_fields=("owner_user_id",),
    ),
    _contrib(
        "interviews",
        mine=True,
        attention=True,
        loader="prehire_personal_work",
        authority_source="prehire_personal_work.build_scoped_work_queue",
        destination_page="interviews",
        mine_permissions=("prehire.read", "interview.manage"),
        attention_permissions=("prehire.read", "interview.manage"),
        assignee_fields=("assignee_user_id", "owner_user_id"),
    ),
    _none("calendar", reason="projection_only", destination_page="calendar"),
    _none(
        "video_interviews",
        reason="module_local_queue_without_reviewer_assignment",
        destination_page="interviews",
    ),
    _contrib(
        "employment_offers",
        mine=False,
        attention=True,
        loader="employment_offers",
        authority_source="offer_lifecycle.pending_approval",
        destination_page="candidates",
        attention_permissions=("offer.approve", "offer.manage"),
        assignee_fields=(),
    ),
    _contrib(
        "requisitions",
        mine=False,
        attention=True,
        loader="requisitions",
        authority_source="requisitions_surfaces.queue_payload",
        destination_page="requisitions",
        attention_permissions=("requisitions.approve", "requisitions.manage"),
        assignee_fields=(),
    ),
    _contrib(
        "onboarding",
        mine=False,
        attention=True,
        loader="onboarding_hr_actionable",
        authority_source="list_onboarding_hr_actionable_page",
        destination_page="onboarding",
        attention_permissions=("onboarding.manage",),
        assignee_fields=(),
    ),
    _contrib(
        "preboarding",
        mine=True,
        attention=True,
        loader="preboarding",
        authority_source="preboarding_surfaces.queue_payload",
        destination_page="preboarding",
        mine_permissions=("preboarding.read", "preboarding.manage"),
        attention_permissions=("preboarding.manage",),
        assignee_fields=("manager_user_id",),
    ),
    _contrib(
        "probation",
        mine=True,
        attention=True,
        loader="probation",
        authority_source="probation_surfaces.queue_payload",
        destination_page="probation",
        mine_permissions=("probation.read", "probation.manage"),
        attention_permissions=("probation.manage",),
        assignee_fields=("manager_user_id",),
    ),
    _contrib(
        "compliance",
        mine=False,
        attention=True,
        loader="action_inbox",
        authority_source="action_inbox_wave1.compliance_findings",
        destination_page="compliance",
        attention_permissions=("compliance.read", "compliance.manage"),
        assignee_fields=(),
    ),
    _contrib(
        "attendance",
        mine=True,
        attention=True,
        loader="attendance_ops",
        authority_source="AttendanceOpsService.list_queue",
        destination_page="attendance",
        mine_permissions=("attendance.manage", "attendance.read"),
        attention_permissions=("attendance.manage",),
        assignee_fields=("owner_phone",),
    ),
    _contrib(
        "shifts",
        mine=False,
        attention=True,
        loader="shift_swaps",
        authority_source="resolve_shift_swaps",
        destination_page="shifts",
        attention_permissions=("shifts.manage",),
        assignee_fields=(),
    ),
    _contrib(
        "leave",
        mine=False,
        attention=True,
        loader="leave_pending",
        authority_source="list_leave_requests",
        destination_page="leave",
        attention_permissions=("leave.decide",),
        assignee_fields=(),
    ),
    _contrib(
        "performance",
        mine=True,
        attention=True,
        loader="performance",
        authority_source="performance_surfaces.list_reviews",
        destination_page="performance",
        mine_permissions=("performance.manage", "performance.read"),
        attention_permissions=("performance.manage",),
        assignee_fields=("reviewer_employee_key",),
    ),
    _none("talent", reason="no_actor_assignment_or_action_queue", destination_page="talent"),
    _contrib(
        "learning",
        mine=False,
        attention=True,
        loader="learning_requests",
        authority_source="learning_surfaces.list_requests",
        destination_page="learning",
        attention_permissions=("learning.approve", "learning.manage", "learning.assign"),
        assignee_fields=(),
    ),
    _contrib(
        "benefits",
        mine=False,
        attention=True,
        loader="benefits_enrollments",
        authority_source="benefits_surfaces.list_enrollments",
        destination_page="benefits",
        attention_permissions=("benefits.manage", "benefits.enroll"),
        assignee_fields=(),
    ),
    _contrib(
        "employee_relations",
        mine=True,
        attention=True,
        loader="employee_relations",
        authority_source="employee_relations_surfaces.list_cases",
        destination_page="employee-relations",
        mine_permissions=("er.read", "er.investigate", "er.decide", "er.manage"),
        attention_permissions=("er.read", "er.investigate", "er.decide", "er.manage"),
        assignee_fields=("assigned_investigator",),
    ),
    _contrib(
        "engagement",
        mine=True,
        attention=True,
        loader="engagement_actions",
        authority_source="engagement_surfaces.list_action_plans",
        destination_page="engagement",
        mine_permissions=("engagement.actions", "engagement.manage", "engagement.read"),
        attention_permissions=("engagement.actions", "engagement.manage"),
        assignee_fields=("owner_key",),
    ),
    _contrib(
        "comp_planning",
        mine=False,
        attention=True,
        loader="comp_planning",
        authority_source="compensation_surfaces.workspace_summary",
        destination_page="compensation-planning",
        attention_permissions=("comp_planning.approve", "comp_planning.manage"),
        assignee_fields=(),
    ),
    _contrib(
        "workforce_planning",
        mine=True,
        attention=True,
        loader="workforce_planning",
        authority_source="workforce_planning_surfaces.list_plans",
        destination_page="workforce-planning",
        mine_permissions=("workforce_planning.plan", "workforce_planning.manage", "workforce_planning.read"),
        attention_permissions=("workforce_planning.approve", "workforce_planning.manage"),
        assignee_fields=("owner_key",),
    ),
    _none("payroll", reason="payroll_money_excluded", destination_page="payroll"),
    _contrib(
        "analytics",
        mine=False,
        attention=True,
        loader="action_inbox",
        authority_source="action_inbox_wave1.analytics_attention",
        destination_page="analytics",
        attention_permissions=("analytics.read",),
        assignee_fields=(),
    ),
    _none("employee_app", reason="employee_channel_not_hr_work_queue"),
)


CONTRIBUTION_BY_MODULE = {row.module: row for row in MODULE_WORK_CONTRIBUTIONS}


def catalog_coverage_errors() -> list[str]:
    declared = {row.module for row in MODULE_WORK_CONTRIBUTIONS}
    missing = [key for key in MODULE_KEYS if key not in declared]
    extra = sorted(declared - set(MODULE_KEYS))
    dupes = []
    seen: set[str] = set()
    for row in MODULE_WORK_CONTRIBUTIONS:
        if row.module in seen:
            dupes.append(row.module)
        seen.add(row.module)
    errors: list[str] = []
    if missing:
        errors.append(f"missing:{','.join(missing)}")
    if extra:
        errors.append(f"extra:{','.join(extra)}")
    if dupes:
        errors.append(f"duplicate:{','.join(dupes)}")
    for row in MODULE_WORK_CONTRIBUTIONS:
        if row.mine and not row.assignee_fields:
            errors.append(f"mine_without_assignee_field:{row.module}")
        if (row.mine or row.attention) and not row.loader:
            errors.append(f"contributes_without_loader:{row.module}")
        if not row.mine and not row.attention and not row.omit_reason:
            errors.append(f"none_without_reason:{row.module}")
        if row.mine and not row.mine_permissions:
            errors.append(f"mine_without_permissions:{row.module}")
        if row.attention and not row.attention_permissions:
            errors.append(f"attention_without_permissions:{row.module}")
    return errors


def attention_entitled(
    spec: ModuleWorkContribution,
    *,
    enabled: set[str],
    permissions: set[str],
    actor_role: str | None,
) -> bool:
    if not spec.attention or spec.module not in enabled:
        return False
    if spec.module in {"pre_hiring", "assessments", "interviews"}:
        import prehire_visibility as pv

        if not pv.actor_has_prehire_oversight(actor_role):
            return False
    return any(p in permissions for p in spec.attention_permissions)


def mine_entitled(
    spec: ModuleWorkContribution,
    *,
    enabled: set[str],
    permissions: set[str],
) -> bool:
    if not spec.mine or spec.module not in enabled:
        return False
    return any(p in permissions for p in spec.mine_permissions)


def contribution_matrix() -> list[dict[str, Any]]:
    rows = []
    for spec in MODULE_WORK_CONTRIBUTIONS:
        kind = "none"
        if spec.mine and spec.attention:
            kind = "both"
        elif spec.mine:
            kind = "mine"
        elif spec.attention:
            kind = "attention"
        rows.append(
            {
                "module": spec.module,
                "kind": kind,
                "mine": spec.mine,
                "attention": spec.attention,
                "omit_reason": spec.omit_reason,
                "loader": spec.loader or None,
                "authority_source": spec.authority_source or None,
                "destination_page": spec.destination_page,
                "assignee_fields": list(spec.assignee_fields),
                "mine_permissions": list(spec.mine_permissions),
                "attention_permissions": list(spec.attention_permissions),
            }
        )
    return rows
