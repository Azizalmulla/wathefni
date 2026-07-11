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

    # Catalog invariants are dependency-free and run everywhere.
    keys = [module.key for module in catalog.MODULE_CATALOG]
    check("catalog module keys are unique", len(keys) == len(set(keys)))
    check("catalog contains exactly the 11 canonical product modules", set(keys) == {
        "pre_hiring", "assessments", "video_interviews", "onboarding",
        "compliance", "attendance", "shifts", "leave", "payroll",
        "analytics", "employee_app",
    })
    check("employee_app is a post-hire employee module", (
        catalog.MODULE_BY_KEY["employee_app"].suite == "post_hire"
        and catalog.MODULE_BY_KEY["employee_app"].audience == "employee"
    ))
    check("employee_app retains the platform master flag", catalog.MODULE_BY_KEY["employee_app"].master_flag == "WATHEFNI_EMPLOYEE_APP")
    check("people modules preserve the former six-module semantics", set(catalog.POSTHIRE_PEOPLE_MODULES) == {
        "onboarding", "compliance", "attendance", "shifts", "leave", "payroll",
    })
    check("post-hire dashboard modules include analytics and compliance", set(catalog.POSTHIRE_MODULES) == {
        "onboarding", "compliance", "attendance", "shifts", "leave", "payroll", "analytics",
    })
    check("tool-call gated modules derive from post-hire catalog metadata", catalog.TOOLCALL_GATED_MODULES == frozenset(catalog.POSTHIRE_MODULES))
    check("Setup Console catalog includes employee_app", "employee_app" in catalog.SETUP_CONSOLE_MODULES)
    check("legacy post_hiring alias remains backward compatible", catalog.normalize_module_key("post-hiring") == "onboarding")

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
    original_configured = app.configured_company_modules
    try:
        # Simulate a post-hire-only tenant with Employee App configured but the
        # platform master switch still off.
        app.configured_company_modules = lambda _company: {"attendance", "employee_app"}
        context = {
            "company_code": "POSTHIREONLY",
            "actor_user_id": "smoke-owner",
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
        check("workspace boot flag defaults to fail-safe OFF semantics", app.workspace_boot_enabled() is False)
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

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    MODULE CATALOG: FAILURES")
        return 1
    print("    MODULE CATALOG: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
