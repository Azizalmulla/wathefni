"""Smoke test: Phase 3 canonical module catalog + workspace bootstrap.

Read-only/in-memory checks only; no database rows are created.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    module catalog — canonical sets + effective entitlements + workspace boot")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))

    import module_catalog as catalog
    import company_setup

    # Catalog invariants are dependency-free and run everywhere.
    keys = [module.key for module in catalog.MODULE_CATALOG]
    check("catalog module keys are unique", len(keys) == len(set(keys)))
    check("catalog contains exactly the 20 canonical product modules", set(keys) == {
        "pre_hiring", "assessments", "interviews", "calendar", "video_interviews", "employment_offers",
        "requisitions", "preboarding", "onboarding", "probation",
        "compliance", "attendance", "shifts", "leave", "payroll",
        "analytics", "employee_app",
        "performance", "talent", "learning",
    })
    check("requisitions has no HARD module dependency", catalog.MODULE_BY_KEY["requisitions"].depends_on == ())
    check("preboarding has no HARD module dependency", catalog.MODULE_BY_KEY["preboarding"].depends_on == ())
    check("probation has no HARD module dependency", catalog.MODULE_BY_KEY["probation"].depends_on == ())
    check("requisitions alias maps", catalog.normalize_module_key("headcount_request") == "requisitions")
    check("preboard alias maps", catalog.normalize_module_key("pre_boarding") == "preboarding")
    check("calendar module is opt-in pre_hire hr suite", (
        catalog.MODULE_BY_KEY["calendar"].suite == "pre_hire"
        and catalog.MODULE_BY_KEY["calendar"].audience == "hr"
        and catalog.MODULE_BY_KEY["calendar"].order == 28
        and catalog.MODULE_BY_KEY["calendar"].depends_on == ()
    ))
    check("calendar is not legacy-implied from pre_hiring", (
        "calendar" not in catalog.apply_legacy_module_implications({"pre_hiring"})
    ))
    check("live interviews is independent of video_interviews", (
        catalog.MODULE_BY_KEY["interviews"].depends_on == ("pre_hiring",)
        and catalog.MODULE_BY_KEY["video_interviews"].depends_on == ("pre_hiring",)
        and "video_interviews" not in catalog.MODULE_BY_KEY["interviews"].depends_on
        and "interviews" not in catalog.MODULE_BY_KEY["video_interviews"].depends_on
    ))
    check("setup save protects currently-enabled interviews", catalog.protect_setup_module_selection(
        ["pre_hiring", "assessments", "video_interviews"],
        currently_enabled=["pre_hiring", "interviews", "video_interviews"],
    ) == ["assessments", "interviews", "pre_hiring", "video_interviews"])
    check("apply_legacy_module_implications grants interviews from pre_hiring seed", (
        catalog.apply_legacy_module_implications({"pre_hiring"}) == {"pre_hiring", "interviews"}
    ))
    check("employee_app is a post-hire employee module", (
        catalog.MODULE_BY_KEY["employee_app"].suite == "post_hire"
        and catalog.MODULE_BY_KEY["employee_app"].audience == "employee"
    ))
    check("employee_app retains the platform master flag", catalog.MODULE_BY_KEY["employee_app"].master_flag == "WATHEFNI_EMPLOYEE_APP")
    check("people modules include Wave 1 hire-ready surfaces", set(catalog.POSTHIRE_PEOPLE_MODULES) == {
        "preboarding", "onboarding", "probation", "compliance", "attendance", "shifts", "leave", "payroll",
    })
    check("post-hire dashboard modules include Wave 1 + analytics", set(catalog.POSTHIRE_MODULES) == {
        "preboarding", "onboarding", "probation", "compliance", "attendance", "shifts", "leave", "payroll", "analytics",
    })
    check(
        "tool-call gated includes Wave 1 + post-hire operational modules",
        {"requisitions", "preboarding", "probation"}.issubset(catalog.TOOLCALL_GATED_MODULES)
        and set(catalog.POSTHIRE_MODULES).issubset(catalog.TOOLCALL_GATED_MODULES)
        and {"assessments", "interviews", "video_interviews", "calendar", "employment_offers"}.issubset(
            catalog.TOOLCALL_GATED_MODULES
        ),
    )
    check("Setup Console catalog includes employee_app", "employee_app" in catalog.SETUP_CONSOLE_MODULES)
    check("legacy post_hiring alias remains backward compatible", catalog.normalize_module_key("post-hiring") == "onboarding")
    check("assessments hard-depends on pre_hiring only", catalog.MODULE_BY_KEY["assessments"].depends_on == ("pre_hiring",))
    check("video_interviews hard-depends on pre_hiring only", catalog.MODULE_BY_KEY["video_interviews"].depends_on == ("pre_hiring",))
    check("employment_offers hard-depends on pre_hiring only", catalog.MODULE_BY_KEY["employment_offers"].depends_on == ("pre_hiring",))
    check("offers alias maps to employment_offers", catalog.normalize_module_key("offers") == "employment_offers")
    check("workforce ops modules remain independently selectable", all(
        not catalog.MODULE_BY_KEY[key].depends_on
        for key in ("attendance", "shifts", "leave", "payroll")
    ))
    check("expand auto-includes pre_hiring for assessments", catalog.expand_module_dependencies(["assessments"]) == ["assessments", "pre_hiring"])
    check("missing deps reports assessments without pre_hiring", catalog.missing_module_dependencies(["assessments"]) == [{
        "module": "assessments",
        "requires": "pre_hiring",
        "message": "Assessments requires Pre-Hiring.",
    }])
    check("payroll soft-recommends attendance and leave without requiring them", (
        catalog.MODULE_BY_KEY["payroll"].recommended_with == ("attendance", "leave")
        and catalog.missing_module_dependencies(["payroll"]) == []
        and catalog.expand_module_dependencies(["payroll"]) == ["payroll"]
    ))
    check("payroll has no employee-app surface in V1", catalog.MODULE_BY_KEY["payroll"].app_surface_key is None)
    check("bundles include hire-ready suite", {bundle.id for bundle in catalog.MODULE_BUNDLES} == {
        "pre_hiring_suite",
        "hiring_assessment_suite",
        "core_hr_suite",
        "hire_ready_suite",
        "workforce_operations",
        "compliance_onboarding",
        "employee_self_service",
    })
    check("hiring assessment bundle expands with pre_hiring", catalog.expand_module_dependencies(
        catalog.BUNDLE_BY_ID["hiring_assessment_suite"].modules
    ) == ["assessments", "interviews", "pre_hiring", "video_interviews"])
    check("app surfaces require employee_app selection", catalog.app_surfaces_for_modules(["attendance", "leave"]) == [])
    surfaces = catalog.app_surfaces_for_modules(["employee_app", "attendance", "payroll"])
    check("app surface preview derives from selected modules and excludes payroll", (
        {item["surface_key"] for item in surfaces} == {"inbox", "attendance"}
    ))
    check("GCC setup defaults are canonical", (
        company_setup.default_timezone_for_country("KW") == "Asia/Kuwait"
        and company_setup.default_currency_for_country("SA") == "SAR"
        and company_setup.default_currency_for_country("AE") == "AED"
    ))

    try:
        import app
        import tool_call_orchestrator as tco
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; app-level checks run on staging.")
            print(f"\n    {PASS} passed, {FAIL} failed")
            return 1 if FAIL else 0
        raise

    check("app Setup Console uses canonical catalog", tuple(app.SETUP_CONSOLE_MODULES) == catalog.SETUP_CONSOLE_MODULES)
    check("app post-hire dashboard set derives from catalog", tuple(app.POSTHIRE_DASHBOARD_MODULES) == catalog.POSTHIRE_MODULES)
    check("app people surfaces derive from catalog", tuple(app.POSTHIRE_PEOPLE_MODULES) == catalog.POSTHIRE_PEOPLE_MODULES)
    check("tool orchestrator imports canonical gated set", tco.TOOLCALL_GATED_MODULES == catalog.TOOLCALL_GATED_MODULES)
    check("compliance actions are now module-mapped", all(
        app.ACTION_REQUIRED_MODULES.get(action) == "compliance"
        for action in ("list_compliance_documents", "compliance_send_reminder", "compliance_mark_reviewed")
    ))
    check("compliance audit category is explicit", app.AUDIT_MODULE_CATEGORY.get("compliance") == "Compliance")

    saved_workspace = os.environ.get("WATHEFNI_WORKSPACE_BOOT")
    saved_employee_app = os.environ.get("WATHEFNI_EMPLOYEE_APP")
    saved_setup_v2 = os.environ.get("WATHEFNI_SETUP_CONSOLE_V2")
    saved_channel_accounts = os.environ.get("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS")
    original_configured = app.configured_company_modules
    try:
        # Simulate a post-hire-only tenant with Employee App configured but the
        # platform master switch still off.
        app.configured_company_modules = lambda _company: {"attendance", "employee_app"}
        context = {
            "company_code": "POSTHIREONLY",
            "actor_user_id": "smoke-owner",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "smoke-owner",
            "permission_subject_company": "POSTHIREONLY",
            "actor_role": "owner",
            "access": {
                "role": "owner",
                "permissions": ["attendance.read", "users.manage", "settings.manage"],
                "user": {"company_code": "POSTHIREONLY", "role": "owner", "status": "active"},
            },
            "permissions": ["attendance.read", "users.manage", "settings.manage"],
            "hr_user": {"company_code": "POSTHIREONLY", "role": "owner", "status": "active"},
        }

        os.environ["WATHEFNI_WORKSPACE_BOOT"] = "off"
        os.environ["WATHEFNI_EMPLOYEE_APP"] = "off"
        os.environ.pop("WATHEFNI_SETUP_CONSOLE_V2", None)
        os.environ.pop("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", None)
        check("workspace boot flag defaults to fail-safe OFF semantics", app.workspace_boot_enabled() is False)
        check("Setup Console V2 defaults OFF", app.setup_console_v2_enabled() is False)
        check("company channel accounts default OFF", app.company_channel_accounts_enabled() is False)
        try:
            app.dashboard_workspace_bootstrap(context)
            check("bootstrap is hidden while flag OFF", False)
        except app.HTTPException as exc:
            check("bootstrap is hidden while flag OFF", exc.status_code == 404)
        try:
            app.workspace_dashboard_context(context)
            check("flag OFF preserves historical pre_hiring gate", False)
        except app.HTTPException as exc:
            check("flag OFF preserves historical pre_hiring gate", exc.status_code == 403)

        from fastapi.testclient import TestClient

        app.app.dependency_overrides[app.dashboard_context] = lambda: context
        client = TestClient(app.app)
        check("team route remains pre_hiring-protected while flag OFF", client.get("/dashboard/team").status_code == 403)

        os.environ["WATHEFNI_WORKSPACE_BOOT"] = "on"
        check("post-hire-only tenant enters workspace when flag ON", app.workspace_dashboard_context(context) is context)
        check("workspace mutation uses permission, not pre_hiring module", app.require_workspace_permission(context, "users.manage") is context)
        check("post-hire-only tenant can load team route when flag ON", client.get("/dashboard/team").status_code == 200)

        denied = {**context, "permissions": ["attendance.read"], "access": {**context["access"], "permissions": ["attendance.read"]}}
        try:
            app.require_workspace_permission(denied, "users.manage")
            check("workspace mutation fails closed without permission", False)
        except app.HTTPException as exc:
            check("workspace mutation fails closed without permission", exc.status_code == 403)

        boot = app.dashboard_workspace_bootstrap(context)
        check("bootstrap reports configured tenant entitlements", set(boot["configured_modules"]) == {"attendance", "employee_app"})
        check("master-disabled employee_app is not effective", set(boot["effective_modules"]) == {"attendance"})
        employee_item = next(item for item in boot["module_catalog"] if item["key"] == "employee_app")
        check("bootstrap explains configured-but-platform-disabled state", (
            employee_item["configured"] is True
            and employee_item["platform_available"] is False
            and employee_item["effective"] is False
        ))

        os.environ["WATHEFNI_EMPLOYEE_APP"] = "on"
        boot_app_on = app.dashboard_workspace_bootstrap(context)
        check("employee_app becomes effective only when both gates are on", "employee_app" in boot_app_on["effective_modules"])

        try:
            app.require_entitlement(context, "compliance", "compliance.read")
            check("disabled product module remains server-protected", False)
        except app.HTTPException as exc:
            check("disabled product module remains server-protected", exc.status_code == 403)
    finally:
        app.app.dependency_overrides.clear()
        app.configured_company_modules = original_configured
        if saved_workspace is None:
            os.environ.pop("WATHEFNI_WORKSPACE_BOOT", None)
        else:
            os.environ["WATHEFNI_WORKSPACE_BOOT"] = saved_workspace
        if saved_employee_app is None:
            os.environ.pop("WATHEFNI_EMPLOYEE_APP", None)
        else:
            os.environ["WATHEFNI_EMPLOYEE_APP"] = saved_employee_app
        if saved_setup_v2 is None:
            os.environ.pop("WATHEFNI_SETUP_CONSOLE_V2", None)
        else:
            os.environ["WATHEFNI_SETUP_CONSOLE_V2"] = saved_setup_v2
        if saved_channel_accounts is None:
            os.environ.pop("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", None)
        else:
            os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = saved_channel_accounts

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    MODULE CATALOG: FAILURES")
        return 1
    print("    MODULE CATALOG: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
