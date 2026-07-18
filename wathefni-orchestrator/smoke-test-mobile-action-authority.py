#!/usr/bin/env python3
"""Prove mobile advertised recruiting actions match executable authority.

Dependency-light: no FastAPI/DB. Covers advertisement ≡ authorize matrix,
role/tenant fail-closed behavior, stale vs permission errors, web/mobile
parity for overlapping actions, and registry entitlement context markers.
"""

from __future__ import annotations

import json
from typing import Any

import operator_mobile as capabilities
import operator_mobile_data as mobile
import recruiting_lifecycle as rl
import tool_call_orchestrator as tco


failures: list[str] = []
checks = 0


def check(condition: bool, message: str, detail: Any = None) -> None:
    global checks
    checks += 1
    if condition:
        print(f"PASS: {message}")
    else:
        failures.append(message if detail is None else f"{message} :: {detail}")
        print(f"FAIL: {message}" + (f" :: {detail}" if detail is not None else ""))


class AuthorityApp:
    """Minimal app surface mirroring context_permissions fail-closed rules."""

    @staticmethod
    def json_safe(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))

    @staticmethod
    def company_has_module(_company: str, module: str) -> bool:
        return module == "pre_hiring"

    @staticmethod
    def context_permissions(context: dict[str, Any], role_key: str | None = None) -> set[str]:
        data = context or {}
        access = data.get("access") if isinstance(data.get("access"), dict) else {}
        authority = str(data.get("permission_authority") or access.get("permission_authority") or "")
        if authority != "backend_current":
            return set()
        subject_user_id = str(
            data.get("permission_subject_user_id")
            or access.get("permission_subject_user_id")
            or ""
        ).strip()
        actor_user_id = str(data.get("actor_user_id") or "").strip()
        if not subject_user_id or (actor_user_id and subject_user_id != actor_user_id):
            return set()
        subject_company = str(
            data.get("permission_subject_company")
            or access.get("permission_subject_company")
            or ""
        ).strip().upper()
        context_company = str(data.get("company_code") or data.get("company_id") or "").strip().upper()
        if not subject_company or (context_company and subject_company != context_company):
            return set()
        permissions = data.get("permissions")
        if not isinstance(permissions, list):
            permissions = access.get("permissions") if isinstance(access.get("permissions"), list) else []
        return {str(item) for item in permissions or [] if str(item).strip()}


def trusted_context(
    *permissions: str,
    company: str = "AUTHCO",
    user_id: str = "user-1",
    role: str = "hr_manager",
) -> dict[str, Any]:
    perms = list(permissions)
    return {
        "company_code": company,
        "company_id": company,
        "actor_user_id": user_id,
        "admin_user_id": user_id,
        "actor_role": role,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "permissions": perms,
        "access": {
            "role": role,
            "permissions": perms,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": company,
        },
        "hr_user": {
            "user_id": user_id,
            "company_code": company,
            "role": role,
            "status": "active",
            "permissions": perms,
        },
    }


ACTION_MATRIX = [
    {
        "action": "shortlist",
        "permission": "candidate.manage",
        "valid_stages": ["ready_for_review"],
        "invalid_stages": ["shortlisted", "hired"],
        "manager_scope": "not applied to recruiting candidate decisions",
        "web": True,
        "mobile": True,
        "endpoint": "POST /dashboard/mobile/candidates/{app_key}/decision",
        "same_authority": "authorize_recruiting_action / allowed_actions_for_stage",
    },
    {
        "action": "reject",
        "permission": "candidate.decide",
        "valid_stages": ["ready_for_review", "shortlisted", "interview"],
        "invalid_stages": ["hired", "rejected"],
        "manager_scope": "not applied to recruiting candidate decisions",
        "web": True,
        "mobile": True,
        "endpoint": "POST /dashboard/mobile/candidates/{app_key}/decision",
        "same_authority": "authorize_recruiting_action / allowed_actions_for_stage",
    },
    {
        "action": "hire",
        "permission": "candidate.decide",
        "valid_stages": ["shortlisted", "interview"],
        "invalid_stages": ["ready_for_review", "hired"],
        "manager_scope": "not applied to recruiting candidate decisions",
        "web": True,
        "mobile": True,
        "endpoint": "POST /dashboard/mobile/candidates/{app_key}/decision",
        "same_authority": "authorize_recruiting_action / allowed_actions_for_stage",
    },
    {
        "action": "schedule_interview",
        "permission": "interview.manage",
        "valid_stages": ["ready_for_review", "shortlisted"],
        "invalid_stages": ["interview", "hired"],
        "manager_scope": "not applied",
        "web": True,
        "mobile": False,
        "endpoint": "registry schedule_interview (web/assistant); not mobile decision API",
        "same_authority": "allowed_actions_for_stage (web) / filtered out of mobile_candidate_allowed_actions",
    },
    {
        "action": "reschedule",
        "permission": "interview.manage",
        "valid_stages": ["interview"],
        "invalid_stages": [],
        "manager_scope": "not applied",
        "web": True,
        "mobile": False,
        "endpoint": "web interview PATCH; mobile interview_reschedule=feature_disabled",
        "same_authority": "capability gate (no mobile execute path)",
    },
    {
        "action": "cancel_interview",
        "permission": "interview.manage",
        "valid_stages": ["interview"],
        "invalid_stages": [],
        "manager_scope": "not applied",
        "web": True,
        "mobile": False,
        "endpoint": "web interview status; not advertised on mobile",
        "same_authority": "capability gate (no mobile execute path)",
    },
    {
        "action": "write_notes",
        "permission": "interview.manage",
        "valid_stages": ["interview"],
        "invalid_stages": [],
        "manager_scope": "not applied",
        "web": True,
        "mobile": True,
        "endpoint": "POST /dashboard/mobile/interviews/{interview_id}/notes",
        "same_authority": "require_entitlement(interview.manage) + interview_notes capability",
    },
]


def main() -> int:
    print("Mobile action authority smoke")
    print("\n--- Action authority matrix ---")
    for row in ACTION_MATRIX:
        print(
            f"  {row['action']}: permission={row['permission']} "
            f"web={row['web']} mobile={row['mobile']} "
            f"authority={row['same_authority']}"
        )
        check(
            rl.permission_for_recruiting_action(row["action"]) == row["permission"],
            f"permission token for {row['action']}",
            rl.permission_for_recruiting_action(row["action"]),
        )

    owner = {"prehire.read", "candidate.manage", "candidate.decide", "interview.manage"}
    print("\n--- Advertised ≡ executable (same fixture) ---")
    for stage in ("ready_for_review", "shortlisted", "interview"):
        web_actions = set(rl.allowed_actions_for_stage(stage, owner))
        mobile_actions = set(rl.mobile_candidate_allowed_actions(stage, owner))
        check(
            mobile_actions <= rl.MOBILE_EXECUTABLE_CANDIDATE_ACTIONS,
            f"mobile actions at {stage} are executable-only",
            mobile_actions,
        )
        check(
            mobile_actions <= web_actions,
            f"mobile actions at {stage} are a subset of web matrix",
            {"web": sorted(web_actions), "mobile": sorted(mobile_actions)},
        )
        for action in mobile_actions:
            check(
                rl.authorize_recruiting_action(action, stage, owner),
                f"advertised {action} at {stage} authorizes with same fixture",
            )

    check(
        "schedule_interview" not in rl.mobile_candidate_allowed_actions("ready_for_review", owner),
        "schedule_interview is not advertised on mobile",
    )
    check(
        "schedule_interview" in rl.allowed_actions_for_stage("ready_for_review", owner),
        "schedule_interview remains available on web matrix",
    )

    print("\n--- Unauthorized actions absent ---")
    viewer = {"prehire.read"}
    for stage in ("ready_for_review", "shortlisted", "interview"):
        check(
            rl.mobile_candidate_allowed_actions(stage, viewer) == [],
            f"viewer has no candidate mutations at {stage}",
        )

    print("\n--- Recruiter vs HR manager ---")
    recruiter = {"prehire.read", "candidate.manage", "interview.manage"}
    hr_manager = {"prehire.read", "candidate.manage", "candidate.decide", "interview.manage"}
    rec_ready = set(rl.mobile_candidate_allowed_actions("ready_for_review", recruiter))
    hr_ready = set(rl.mobile_candidate_allowed_actions("ready_for_review", hr_manager))
    check(rec_ready == {"shortlist"}, "recruiter may shortlist only from ready_for_review", rec_ready)
    check(hr_ready == {"shortlist", "reject"}, "HR manager may shortlist+reject from ready_for_review", hr_ready)
    check(
        "hire" not in rl.mobile_candidate_allowed_actions("ready_for_review", hr_manager),
        "hire absent from ready_for_review for HR manager",
    )
    check(
        set(rl.mobile_candidate_allowed_actions("shortlisted", hr_manager)) >= {"hire", "reject"},
        "HR manager may hire/reject from shortlisted",
    )
    check(
        "hire" not in rl.mobile_candidate_allowed_actions("shortlisted", recruiter),
        "recruiter cannot hire from shortlisted",
    )

    print("\n--- Restricted manager recruiting capabilities ---")
    mgr_ctx = trusted_context(
        "leave.read",
        "leave.decide",
        "prehire.read",
        role="manager",
        user_id="mgr-1",
    )
    mgr_ctx["scope"] = {
        "restricted": True,
        "blocked": False,
        "configuration_error": None,
        "scope_authority": "dashboard_user_id",
    }
    rec_caps = capabilities.build_recruiting_workspace_capabilities(AuthorityApp, mgr_ctx)
    check(rec_caps["candidate_shortlist"]["enabled"] is False, "restricted manager cannot shortlist without candidate.manage")
    check(rec_caps["candidate_hire"]["enabled"] is False, "restricted manager cannot hire without candidate.decide")
    check(rec_caps["interview_reschedule"]["enabled"] is False, "interview reschedule remains feature_disabled on mobile")

    print("\n--- DTO advertisement uses authoritative context ---")
    ready_item = {
        "app_key": "app-ready",
        "name": "Lina",
        "status": "ready_for_review",
        "application": {
            "candidate": {"name": "Lina"},
            "position": {"title": "Designer"},
        },
    }
    owner_ctx = trusted_context(
        "prehire.read",
        "candidate.manage",
        "candidate.decide",
        "interview.manage",
        role="hr_manager",
    )
    advertised = mobile.candidate_mobile_item(AuthorityApp, ready_item, context=owner_ctx)
    check(
        set(advertised["allowed_actions"]) == {"shortlist", "reject"},
        "owner ready_for_review advertises shortlist+reject only",
        advertised["allowed_actions"],
    )
    for action in advertised["allowed_actions"]:
        check(
            rl.authorize_recruiting_action(action, "ready_for_review", owner),
            f"DTO-advertised {action} would authorize on execute",
        )

    print("\n--- Fail-closed without authority markers ---")
    bare = {
        "company_code": "AUTHCO",
        "actor_user_id": "user-1",
        "permissions": ["candidate.manage", "candidate.decide"],
    }
    check(
        mobile._candidate_allowed_actions(AuthorityApp, bare, "ready_for_review") == [],
        "missing backend_current markers yield no candidate actions",
    )
    cross_tenant = trusted_context("candidate.manage", "candidate.decide", company="AUTHCO", user_id="user-1")
    cross_tenant["permission_subject_company"] = "OTHERCO"
    cross_tenant["access"]["permission_subject_company"] = "OTHERCO"
    check(
        mobile._candidate_allowed_actions(AuthorityApp, cross_tenant, "ready_for_review") == [],
        "tenant subject mismatch fails closed",
    )

    print("\n--- Stale vs permission denial remain distinct ---")
    check(
        not rl.authorize_recruiting_action("hire", "ready_for_review", owner),
        "invalid stage is rejected by authorize (not confused with permission)",
    )
    check(
        not rl.authorize_recruiting_action("hire", "shortlisted", recruiter),
        "missing candidate.decide is rejected by authorize",
    )
    check(
        rl.permission_for_recruiting_action("hire") == "candidate.decide",
        "hire permission token is candidate.decide",
    )
    # Source contract: decision handler keeps already_decided/stale_decision separate.
    decision_source = open(
        __file__.replace("smoke-test-mobile-action-authority.py", "operator_mobile_data.py"),
        encoding="utf-8",
    ).read()
    check("already_decided" in decision_source, "terminal state uses already_decided")
    check("stale_decision" in decision_source, "confirm path uses stale_decision")
    check("permission_denied" in decision_source, "missing grant uses permission_denied")
    check("authorize_recruiting_action" in decision_source, "decision uses authorize_recruiting_action")

    print("\n--- Interview mobile executable filter ---")
    interview_actions = mobile._mobile_interview_allowed_actions(
        ["read", "cancel_interview", "reschedule"],
        ["write", "write_notes"],
    )
    check(
        set(interview_actions) == {"read", "write", "write_notes"},
        "cancel/reschedule stripped from interview allowed_actions",
        interview_actions,
    )

    print("\n--- Registry entitlement context preserves authority markers ---")
    scope = {
        "company_id": "AUTHCO",
        "admin_user_id": "user-1",
        "permissions": ["candidate.manage", "leave.decide"],
        "permission_authority": "backend_current",
        "permission_subject_user_id": "user-1",
        "permission_subject_company": "AUTHCO",
        "role_scope": "hr_manager",
        "hr_user": {"user_id": "user-1", "status": "active", "role": "hr_manager"},
        "access": {
            "permission_authority": "backend_current",
            "permission_subject_user_id": "user-1",
            "permission_subject_company": "AUTHCO",
            "permissions": ["candidate.manage", "leave.decide"],
        },
    }
    ent = tco._entitlement_context(scope)
    check(ent.get("permission_authority") == "backend_current", "entitlement context keeps permission_authority")
    check(ent.get("permission_subject_user_id") == "user-1", "entitlement context keeps subject user")
    check(ent.get("permission_subject_company") == "AUTHCO", "entitlement context keeps subject company")
    check(
        AuthorityApp.context_permissions(ent) == {"candidate.manage", "leave.decide"},
        "preserved markers yield the same grant set as advertisement",
    )

    # Registry shortlist/reject executor must read metadata as a dict, not set(...).get
    registry_source = open(
        __file__.replace("smoke-test-mobile-action-authority.py", "action_registry.py"),
        encoding="utf-8",
    ).read()
    check(
        'permissions = set(getattr(ctx.request, "metadata"' not in registry_source,
        "status mutation executor does not call set(metadata).get",
    )
    check(
        "permissions = meta.get(\"permissions\") or []" in registry_source,
        "status mutation executor reads metadata permissions safely",
    )

    print("\n--- Web/mobile parity for overlapping executable actions ---")
    for stage in ("ready_for_review", "shortlisted", "interview"):
        web = set(rl.allowed_actions_for_stage(stage, owner))
        mobile_set = set(rl.mobile_candidate_allowed_actions(stage, owner))
        overlap = web & rl.MOBILE_EXECUTABLE_CANDIDATE_ACTIONS
        check(
            mobile_set == overlap,
            f"mobile executable overlap equals web∩executable at {stage}",
            {"web": sorted(web), "mobile": sorted(mobile_set), "overlap": sorted(overlap)},
        )

    print(f"\nAuthority smoke: {checks - len(failures)}/{checks} passed")
    if failures:
        print("Failures:")
        for item in failures:
            print(f"  - {item}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
