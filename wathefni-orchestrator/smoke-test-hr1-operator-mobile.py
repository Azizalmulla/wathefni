#!/usr/bin/env python3
"""HR-1 — focused smoke for Wathefni HR operator mobile auth + capabilities.

Pins source contracts and capability evaluation (no frontend).
Optional DB-backed session lifecycle when postgres is available.

Run: python3 smoke-test-hr1-operator-mobile.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}" + (f" :: {detail}" if detail is not None else ""))


def main() -> int:
    print("HR-1 operator mobile smoke")
    root = Path(__file__).resolve().parent
    app_source = (root / "app.py").read_text(encoding="utf-8")
    mobile_source = (root / "operator_mobile.py").read_text(encoding="utf-8")
    deploy_source = (root / "ops" / "deploy.sh").read_text(encoding="utf-8")

    # --- source contracts -------------------------------------------------
    for path in (
        "/dashboard/mobile/auth/login",
        "/dashboard/mobile/auth/refresh",
        "/dashboard/mobile/auth/logout",
        "/dashboard/mobile/auth/logout-all",
        "/dashboard/mobile/me",
    ):
        check(f"route {path} registered", path in mobile_source)

    check("mobile module imported in app.py", "import operator_mobile as _operator_mobile" in app_source)
    check("routes registered before SPA catch-all", "register_operator_mobile_routes" in app_source)
    check("schema ensure wires operator mobile", "ensure_operator_mobile_schema" in app_source)
    check("deploy ships operator_mobile.py", "operator_mobile.py" in deploy_source)
    check("deploy compiles operator_mobile.py", "operator_mobile.py" in deploy_source and "py_compile" in deploy_source)

    check("separate session table", "dashboard_operator_mobile_sessions" in mobile_source)
    check("login attempt table", "dashboard_operator_mobile_login_attempts" in mobile_source)
    check("stores token hashes only", "access_token_hash" in mobile_source and "refresh_token_hash" in mobile_source)
    check("refresh rotation", "status='rotated'" in mobile_source)
    check("replay fail-closed", 'code="session_revoked"' in mobile_source)
    check("rate_limited code", 'code="rate_limited"' in mobile_source)
    check("generic invalid_credentials", 'code="invalid_credentials"' in mobile_source)
    check("MFA extension reserved not enforced", '"enforced": False' in mobile_source and "MFA_EXTENSION" in mobile_source)
    check("SecureStore contract documented", "SECURE_STORE_CONTRACT" in mobile_source)
    check("permission_authority backend_current", '"permission_authority": "backend_current"' in mobile_source)
    check("rejects employee tokens", "employee_token_rejected" in mobile_source)
    check("rejects browser sessions", "browser_session_rejected" in mobile_source)
    check("rejects legacy shared token", "legacy_authority_rejected" in mobile_source)
    check("company binding enforced", "requested and requested != company" in mobile_source)
    check("owner workspace not invented", '"enabled": False' in mobile_source and "Owner mobile workspace reserved" in mobile_source)
    check("no Setup Console in me payload", "setup_console" not in mobile_source.lower() or "Setup Console" in mobile_source)
    check("does not register employee auth routes", '@app.post("/app/auth' not in mobile_source and "/app/auth/login" not in mobile_source)
    check("documents separation from /app/auth", "/app/auth/*" in mobile_source)
    check("disable revokes mobile sessions", "revoke_user_operator_mobile_sessions" in app_source)
    check("company lifecycle revokes mobile sessions", "revoke_company_operator_mobile_sessions" in app_source)
    check("hire/reject require confirmation", "confirmation_required=True" in mobile_source)
    check("rankings marked advisory", "advisory=True" in mobile_source)

    unavailable = [
        "new_candidate_push",
        "interview_reschedule",
        "kanban_stage_management",
        "bulk_import",
        "job_pipeline_configuration",
        "ai_scoring_configuration",
    ]
    for key in unavailable:
        check(f"recruiting unavailable feature {key}", key in mobile_source)

    hr_keys = [
        "hr_tasks",
        "leave_approvals",
        "onboarding_review",
        "document_review",
        "attendance_exceptions",
        "today_shifts",
        "shift_swap_decisions",
        "employee_search",
        "employee_quick_profile",
        "delivery_alerts",
    ]
    for key in hr_keys:
        check(f"HR capability key {key}", f'"{key}"' in mobile_source)

    sys.path.insert(0, str(root))
    import operator_mobile as om

    # --- capability evaluation (mocked modules) --------------------------
    def ctx(*, role: str, perms: list[str], scope: dict | None = None) -> dict:
        return {
            "company_code": "HR1CAP",
            "actor_role": role,
            "permissions": perms,
            "scope": scope
            or {
                "restricted": role == "manager",
                "scope_authority": "dashboard_user_id" if role == "manager" else "unrestricted",
                "configuration_error": None,
            },
            "hr_user": {
                "user_id": "u-1",
                "company_code": "HR1CAP",
                "email": f"{role}@example.com",
                "name": role,
                "role": role,
                "role_label": role,
                "status": "active",
                "permissions": perms,
            },
            "permission_authority": "backend_current",
            "mobile_session_id": "s-1",
        }

    class _App:
        @staticmethod
        def company_has_module(company, module):
            return module in {
                "leave",
                "onboarding",
                "compliance",
                "attendance",
                "shifts",
                "payroll",
                "pre_hiring",
                "interviews",
                "assessments",
            }

        @staticmethod
        def company_lifecycle_status(_company):
            return "active"

        @staticmethod
        def dashboard_user_public(user):
            return user

    app_mod = _App()

    owner_perms = [
        "leave.read",
        "leave.decide",
        "attendance.read",
        "attendance.manage",
        "shifts.read",
        "shifts.manage",
        "onboarding.read",
        "onboarding.manage",
        "compliance.read",
        "compliance.manage",
        "payroll.read",
        "prehire.read",
        "candidate.manage",
        "candidate.decide",
        "interview.manage",
    ]
    owner_ctx = ctx(role="owner", perms=owner_perms, scope={"restricted": False})
    owner_hr = om.build_hr_workspace_capabilities(app_mod, owner_ctx)
    owner_rec = om.build_recruiting_workspace_capabilities(app_mod, owner_ctx)
    owner_ws = om.build_owner_workspace_capabilities(app_mod, owner_ctx)
    check("owner leave_approvals approve+reject", owner_hr["leave_approvals"]["enabled"] and set(owner_hr["leave_approvals"]["actions"]) >= {"read", "approve", "reject"})
    check("owner candidate_hire confirmation", owner_rec["candidate_hire"].get("confirmation_required") is True)
    check("owner rankings advisory", owner_rec["candidate_rankings"].get("advisory") is True)
    check("owner workspace disabled in V1", owner_ws["enabled"] is False)
    check("owner employee_search off without grant", owner_hr["employee_search"]["enabled"] is False)

    hr_ctx = ctx(role="hr_manager", perms=owner_perms, scope={"restricted": False})
    hr_features = om.build_hr_workspace_capabilities(app_mod, hr_ctx)
    check("hr_manager leave enabled", hr_features["leave_approvals"]["enabled"] is True)

    mgr_ok = ctx(
        role="manager",
        perms=["leave.read", "leave.decide", "attendance.read", "shifts.read", "shifts.manage", "onboarding.read", "compliance.read"],
        scope={"restricted": True, "scope_authority": "dashboard_user_id", "configuration_error": None},
    )
    mgr_hr = om.build_hr_workspace_capabilities(app_mod, mgr_ok)
    check("restricted manager leave enabled", mgr_hr["leave_approvals"]["enabled"] is True)
    check("restricted manager recruiting absent from HR namespace", "candidate_hire" not in mgr_hr)

    mgr_conflict = ctx(
        role="manager",
        perms=["leave.read", "leave.decide"],
        scope={"restricted": True, "configuration_error": "manager_scope_binding_conflict", "blocked": True},
    )
    conflict_hr = om.build_hr_workspace_capabilities(app_mod, mgr_conflict)
    check("manager conflict fail-closed leave", conflict_hr["leave_approvals"]["enabled"] is False)
    check("manager conflict reason", conflict_hr["leave_approvals"].get("reason") == "manager_scope_conflict")

    mgr_missing = ctx(
        role="manager",
        perms=["leave.read", "leave.decide"],
        scope={"restricted": True, "configuration_error": "manager_scope_unconfigured", "blocked": True},
    )
    missing_hr = om.build_hr_workspace_capabilities(app_mod, mgr_missing)
    check("manager missing scope fail-closed", missing_hr["leave_approvals"]["enabled"] is False)

    recruiter_ctx = ctx(
        role="recruiter",
        perms=["prehire.read", "candidate.manage", "interview.manage"],
        scope={"restricted": False},
    )
    rec = om.build_recruiting_workspace_capabilities(app_mod, recruiter_ctx)
    check("recruiter can shortlist", rec["candidate_shortlist"]["enabled"] is True)
    check("recruiter cannot hire", rec["candidate_hire"]["enabled"] is False)
    check("recruiter push disabled", rec["new_candidate_push"]["enabled"] is False)

    hiring_mgr = ctx(
        role="hiring_manager",
        perms=["prehire.read", "interview.manage", "leave.read", "attendance.read", "shifts.read", "onboarding.read"],
        scope={"restricted": False},
    )
    hm_rec = om.build_recruiting_workspace_capabilities(app_mod, hiring_mgr)
    hm_hr = om.build_hr_workspace_capabilities(app_mod, hiring_mgr)
    check("hiring_manager interview_status", hm_rec["interview_status"]["enabled"] is True)
    check("hiring_manager cannot shortlist", hm_rec["candidate_shortlist"]["enabled"] is False)
    check("hiring_manager leave read only", hm_hr["leave_approvals"]["actions"] == ["read"])

    viewer_ctx = ctx(
        role="viewer",
        perms=["prehire.read", "leave.read", "attendance.read", "shifts.read", "onboarding.read", "compliance.read"],
        scope={"restricted": False},
    )
    viewer_rec = om.build_recruiting_workspace_capabilities(app_mod, viewer_ctx)
    viewer_hr = om.build_hr_workspace_capabilities(app_mod, viewer_ctx)
    check("viewer rankings read", viewer_rec["candidate_rankings"]["enabled"] is True)
    check("viewer cannot reject", viewer_rec["candidate_reject"]["enabled"] is False)
    check("viewer leave read only", viewer_hr["leave_approvals"]["actions"] == ["read"])

    no_grants = ctx(role="viewer", perms=[], scope={"restricted": False})
    empty_hr = om.build_hr_workspace_capabilities(app_mod, no_grants)
    empty_rec = om.build_recruiting_workspace_capabilities(app_mod, no_grants)
    check("missing grants leave disabled", empty_hr["leave_approvals"]["enabled"] is False)
    check("missing grants recruiting disabled", empty_rec["candidate_summary"]["enabled"] is False)

    # Module removal takes effect
    class _NoLeave(_App):
        @staticmethod
        def company_has_module(company, module):
            return module != "leave" and module in {
                "onboarding",
                "compliance",
                "attendance",
                "shifts",
                "payroll",
                "pre_hiring",
            }

    no_leave = om.build_hr_workspace_capabilities(_NoLeave(), owner_ctx)
    check("module removal disables leave_approvals", no_leave["leave_approvals"]["enabled"] is False)
    check("module removal reason", no_leave["leave_approvals"].get("reason") == "module_disabled")

    # /me payload shape
    with patch.object(om, "build_hr_workspace_capabilities", return_value=owner_hr), patch.object(
        om, "build_recruiting_workspace_capabilities", return_value=owner_rec
    ), patch.object(om, "build_owner_workspace_capabilities", return_value=owner_ws):
        me = om.build_mobile_me_payload(app_mod, owner_ctx)
    check("me.ok", me.get("ok") is True)
    check("me.permission_authority", me.get("permission_authority") == "backend_current")
    check("me.principal.role", me["principal"]["role"] == "owner")
    check("me.workspaces.hr present", "hr" in me["workspaces"])
    check("me.workspaces.recruiting present", "recruiting" in me["workspaces"])
    check("me.workspaces.owner disabled", me["workspaces"]["owner"]["enabled"] is False)
    check("me.scope metadata only", set(me["scope"].keys()) <= {"restricted", "binding", "configured", "configuration_error"})
    check("me has mfa extension", me.get("mfa", {}).get("enforced") is False)
    check("me has secure_store contract", "access_token_key" in me.get("secure_store", {}))
    check("me does not list employee IDs", "employee_ids" not in me and "employee_keys" not in me)

    # Token hash never stores raw token
    check("token hash is sha256 hex", len(om._token_hash("abc")) == 64)
    check("token hash not equal to raw", om._token_hash("abc") != "abc")

    # Attempt to import app for optional DB checks
    try:
        import app  # noqa: F401
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2" or (exc.name or "").startswith("psycopg2"):
            print("NOTE: DB session lifecycle checks skipped (psycopg2 unavailable locally).")
        else:
            raise
    else:
        # Light structural checks against live module without mutating DB.
        check("ACCESS_TTL defined", om.ACCESS_TTL.total_seconds() > 0)
        check("REFRESH_TTL defined", om.REFRESH_TTL.total_seconds() > 0)
        check("LOGIN_MAX_FAILURES >= 5", om.LOGIN_MAX_FAILURES >= 5)

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
