#!/usr/bin/env python3
"""Production Readiness R5H — Engagement product surface unit contracts (no DB)."""
from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DASH = REPO / "apps" / "wathefni-dashboard" / "src"
MOBILE = REPO / "apps" / "wathefni-employee-mobile"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import capability_readiness as ready
    import module_catalog as catalog
    import engagement_surfaces as surfaces
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5H — engagement surface (unit)")

    check("engagement customer enableable", ready.customer_enableable("engagement") is True)
    check("engagement customer visible", ready.customer_visible("engagement") is True)
    check("ER still enableable", ready.customer_enableable("employee_relations") is True)
    check("benefits still enableable", ready.customer_enableable("benefits") is True)
    check("learning still enableable", ready.customer_enableable("learning") is True)
    check("comp planning now enableable after R5I", ready.customer_enableable("comp_planning") is True)
    check("workforce planning now enableable after R5J", ready.customer_enableable("workforce_planning") is True)
    check("engagement is catalog SKU", "engagement" in catalog.MODULE_BY_KEY)
    check("engagement people_surface off", catalog.MODULE_BY_KEY["engagement"].people_surface is False)
    check("engagement audience is employee", catalog.MODULE_BY_KEY["engagement"].audience == "employee")
    payload = ready.readiness_payload("engagement")
    for flag in ("domain_authority_ready", "http_ready", "hr_web_ready", "employee_surface_ready", "manager_surface_ready"):
        check(f"engagement {flag}", payload.get(flag) is True)
    check("engagement mobile not required", payload.get("mobile_required") is False)
    check("engagement mobile not ready", payload.get("mobile_ready") is False)
    check(
        "fail-closed skips engagement namespaces",
        ("engagement", "/dashboard/engagement") not in ready.all_http_namespaces()
        and ("engagement", "/app/engagement") not in ready.all_http_namespaces(),
    )
    check(
        "fail-closed skips comp planning after R5I",
        ("comp_planning", "/dashboard/compensation-planning") not in ready.all_http_namespaces(),
    )

    honesty = surfaces.honesty_payload()
    check("anonymous ≠ identified", honesty.get("anonymous_is_not_identified") is True)
    check("participation ≠ answer mapping", honesty.get("participation_is_not_answer_mapping") is True)
    check("suppressed ≠ zero", honesty.get("suppressed_is_not_zero") is True)
    check("result ≠ action plan", honesty.get("survey_result_is_not_action_plan") is True)
    check("action plan ≠ ER", honesty.get("action_plan_is_not_er_case") is True)
    check("no auto ER", honesty.get("no_auto_er") is True)
    check("no engagement AI", honesty.get("no_engagement_ai_authority") is True)
    check("no universal score", honesty.get("no_universal_employee_score") is True)
    check("recognition out", honesty.get("recognition_out") is True)
    check("empty manager ≠ company-wide", honesty.get("empty_manager_scope_is_not_company_wide") is True)
    check("export obeys suppression", honesty.get("export_obeys_suppression") is True)
    check("assistant mutations out", honesty.get("assistant_mutations") is False)
    check("C5 remains canonical", "engagement_c5" in (honesty.get("canonical_authority") or ()))
    check("min_n default 5", honesty.get("min_responses_default_5") is True)
    check("threshold upward only", honesty.get("threshold_upward_only") is True)
    check("complementary suppression", honesty.get("complementary_suppression") is True)
    check("enps explicit only", honesty.get("enps_only_on_explicit_scale") is True)

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts Engagement", "Wave6EngagementPoliciesCard" in setup_app)
    check("Setup still remounts ER", "Wave6EmployeeRelationsPoliciesCard" in setup_app)
    check("Setup still remounts Benefits", "Wave6BenefitsPoliciesCard" in setup_app)
    check("Setup remounts Comp Planning after R5I", "Wave6CompensationPlanningPoliciesCard" in setup_app)
    check("Setup remounts Workforce Planning after R5J", "Wave6WorkforcePlanningPoliciesCard" in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts Engagement workspace", "EngagementWorkspace" in posthire)
    workspace = (DASH / "posthire" / "EngagementWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "المشاركة والارتباط" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace names suppression", "Suppressed" in workspace or "محجوب" in workspace)
    check("workspace names action-plan boundary", "not an ER case" in workspace or "ليست قضية" in workspace)
    check("403 is not empty-surveys copy", "forbidden" in workspace and "emptySurveys" in workspace)

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes engagement", "| 'engagement'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.engagement registered", "nav.engagement" in nav)
    check("nav allows manager or read", "engagement.manager" in nav and "engagement.read" in nav)
    catalog_src = (DASH / "lib" / "moduleWorkspace.ts").read_text(encoding="utf-8")
    modules_block = catalog_src.split("CANONICAL_POSTHIRE_MODULES")[1].split("]")[0]
    people_block = catalog_src.split("CANONICAL_POSTHIRE_PEOPLE_MODULES")[1].split("]")[0]
    check("engagement is a canonical posthire SKU", "'engagement'" in modules_block)
    check("engagement is not a people-360 module", "'engagement'" not in people_block)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers Engagement HTTP", "register_engagement_http" in app_src)
    for perm in (
        "engagement.read",
        "engagement.manage",
        "engagement.launch",
        "engagement.results",
        "engagement.manager",
        "engagement.actions",
        "engagement.export",
    ):
        check(f"{perm} permission exists", perm in app_src)
    check("notification flow engagement", '"engagement": "engagement"' in app_src)
    manager_block = app_src.split("_POSTHIRE_PERMS_MANAGER")[1].split("}")[0]
    viewer_block = app_src.split("_POSTHIRE_PERMS_VIEWER")[1].split("}")[0]
    full_block = app_src.split("_POSTHIRE_PERMS_FULL")[1].split("}")[0]
    check("manager fixture has engagement.manager", '"engagement.manager"' in manager_block)
    check("manager fixture has no engagement.manage", '"engagement.manage"' not in manager_block)
    check("viewer fixture has no engagement admin", '"engagement.manage"' not in viewer_block)
    check("HR full has engagement.read", "engagement.read" in full_block)

    http_src = (ROOT / "engagement_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/engagement",
        "/app/engagement",
        "/workspace",
        "/surveys",
        "/versions",
        "/campaigns",
        "/launch",
        "/results",
        "/segments",
        "/action-plans",
        "/history",
        "/export",
        "/manager",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP uses employee_app_context", "employee_app_context" in http_src)
    check("HTTP refuses manager admin workspace", "Managers do not have an Engagement administration workspace" in http_src)
    check("no HR Mobile engagement namespace", "/dashboard/mobile/engagement" not in http_src)
    surf_src = (ROOT / "engagement_surfaces.py").read_text(encoding="utf-8")
    check("no second survey engine", "canonical_authority" in surf_src and "engagement_c5" in surf_src)
    check("no recognition", "recognition_out" in surf_src)
    check("no AI scoring", "no_engagement_ai_authority" in surf_src)
    check("export wraps suppression", "export_obeys_suppression" in surf_src)
    check("assistant wrapper exists", "assistant_query" in surf_src)

    check("employee hub exists", (MOBILE / "app" / "engagement" / "index.tsx").is_file())
    check("employee survey exists", (MOBILE / "app" / "engagement" / "survey.tsx").is_file())
    check("no HR mobile engagement dir", not (MOBILE / "app" / "hr" / "engagement").exists())
    en = (MOBILE / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    ar = (MOBILE / "src" / "i18n" / "ar.json").read_text(encoding="utf-8")
    check("employee EN copy", '"engagement"' in en and "Anonymous is not identified" in en)
    check("employee AR copy", "المشاركة والارتباط" in ar)
    emp_comp = (MOBILE / "src" / "composition" / "employeeAppComposition.ts").read_text(encoding="utf-8")
    check("employee composition has engagement", "engagement" in emp_comp and "'/engagement'" in emp_comp)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    eg = client.get("/dashboard/engagement/workspace")
    check(
        "fail-closed no longer steals Engagement",
        not (
            eg.status_code == 404
            and isinstance(eg.json().get("detail"), dict)
            and eg.json()["detail"].get("error") == "capability_not_released"
        ),
        eg.json() if eg.headers.get("content-type", "").startswith("application/json") else eg.status_code,
    )
    app_eg = client.get("/app/engagement")
    check(
        "fail-closed no longer steals employee Engagement",
        not (
            app_eg.status_code == 404
            and isinstance(app_eg.json().get("detail"), dict)
            and app_eg.json()["detail"].get("error") == "capability_not_released"
        ),
        app_eg.json() if app_eg.headers.get("content-type", "").startswith("application/json") else app_eg.status_code,
    )
    comp = client.get("/dashboard/compensation-planning")
    check(
        "fail-closed no longer steals Compensation Planning",
        not (
            comp.status_code == 404
            and isinstance(comp.json().get("detail"), dict)
            and comp.json()["detail"].get("error") == "capability_not_released"
        ),
        comp.json() if comp.headers.get("content-type", "").startswith("application/json") else comp.status_code,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5H_ENGAGEMENT_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
