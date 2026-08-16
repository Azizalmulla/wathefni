#!/usr/bin/env python3
"""Production Readiness R5F — Benefits product surface unit contracts (no DB)."""
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
    import benefits_surfaces as surfaces
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5F — benefits surface (unit)")

    check("benefits customer enableable", ready.customer_enableable("benefits") is True)
    check("benefits customer visible", ready.customer_visible("benefits") is True)
    check("learning still enableable", ready.customer_enableable("learning") is True)
    check("JA still enableable", ready.customer_enableable("job_architecture") is True)
    check("talent still enableable", ready.customer_enableable("talent") is True)
    check("performance still enableable", ready.customer_enableable("performance") is True)
    check("ER now enableable after R5G", ready.customer_enableable("employee_relations") is True)
    check("engagement now enableable after R5H", ready.customer_enableable("engagement") is True)
    check("comp planning now enableable after R5I", ready.customer_enableable("comp_planning") is True)
    check("workforce planning still hidden", ready.customer_enableable("workforce_planning") is False)
    check("benefits is catalog SKU", "benefits" in catalog.MODULE_BY_KEY)
    check("benefits people_surface off", catalog.MODULE_BY_KEY["benefits"].people_surface is False)
    payload = ready.readiness_payload("benefits")
    for flag in ("domain_authority_ready", "http_ready", "hr_web_ready", "employee_surface_ready"):
        check(f"benefits {flag}", payload.get(flag) is True)
    check("benefits manager not required", payload.get("manager_surface_required") is False)
    check("benefits manager not ready", payload.get("manager_surface_ready") is False)
    check("benefits mobile not required", payload.get("mobile_required") is False)
    check("fail-closed skips Benefits namespaces", ("benefits", "/dashboard/benefits") not in ready.all_http_namespaces())
    check("fail-closed skips ER namespaces", ("employee_relations", "/dashboard/employee-relations") not in ready.all_http_namespaces())

    honesty = surfaces.honesty_payload()
    check("eligible ≠ enrolled", honesty.get("eligible_is_not_enrolled") is True)
    check("election ≠ coverage", honesty.get("election_is_not_coverage") is True)
    check("waiver ≠ ineligibility", honesty.get("waiver_is_not_ineligibility") is True)
    check("dependent exists ≠ covered", honesty.get("dependent_exists_is_not_covered") is True)
    check("coverage ≠ provider confirmed", honesty.get("coverage_is_not_provider_confirmed") is True)
    check("contribution ≠ deduction", honesty.get("contribution_is_not_deduction") is True)
    check("handoff ≠ payroll execution", honesty.get("handoff_is_not_payroll_execution") is True)
    check("payroll optional", honesty.get("payroll_optional") is True)
    check("claims out", honesty.get("claims_out") is True)
    check("no invented Kuwait formulas", honesty.get("no_invented_kuwait_formulas") is True)
    check("no manager private default", honesty.get("no_manager_private_default") is True)
    check("no duplicate dependent authority", honesty.get("no_duplicate_dependent_authority") is True)
    check("C3 remains canonical", "benefits_administration_c3" in (honesty.get("canonical_authority") or ()))

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts Benefits", "Wave6BenefitsPoliciesCard" in setup_app)
    check("Setup still remounts Learning", "Wave6LearningPoliciesCard" in setup_app)
    check("Setup still remounts JA", "Wave6JobArchitecturePoliciesCard" in setup_app)
    check("Setup remounts ER after R5G", "Wave6EmployeeRelationsPoliciesCard" in setup_app)
    check("Setup remounts Comp Planning after R5I", "Wave6CompensationPlanningPoliciesCard" in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts Benefits workspace", "BenefitsWorkspace" in posthire)
    workspace = (DASH / "posthire" / "BenefitsWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "إدارة المزايا" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace names eligibility boundary", "Eligible is not enrolled" in workspace or "الأهلية ليست تسجيلاً" in workspace)
    check("workspace names contribution boundary", "not a deduction" in workspace or "ليست استقطاع" in workspace)
    check("workspace does not invent claims", "claim" not in workspace.lower() or "not claims" in workspace.lower())

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes benefits", "| 'benefits'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.benefits registered", "nav.benefits" in nav)
    check("nav.benefits has module key", "module: 'benefits'" in nav and "permission: 'benefits.read'" in nav)
    catalog_src = (DASH / "lib" / "moduleWorkspace.ts").read_text(encoding="utf-8")
    modules_block = catalog_src.split("CANONICAL_POSTHIRE_MODULES")[1].split("]")[0]
    people_block = catalog_src.split("CANONICAL_POSTHIRE_PEOPLE_MODULES")[1].split("]")[0]
    check("benefits is a canonical posthire SKU", "'benefits'" in modules_block)
    check("benefits is not a people-360 module", "'benefits'" not in people_block)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers Benefits HTTP", "register_benefits_http" in app_src)
    check("benefits.read permission exists", "benefits.read" in app_src)
    check("benefits.manage permission exists", "benefits.manage" in app_src)
    check("benefits.eligibility permission exists", "benefits.eligibility" in app_src)
    check("benefits.enroll permission exists", "benefits.enroll" in app_src)
    check("benefits.sensitive permission exists", "benefits.sensitive" in app_src)
    check("employee feature benefits", 'module_keys": ("benefits",)' in app_src.replace(" ", "") or 'module_keys": ("benefits",)' in app_src)
    check("notification flow benefits", '"benefits": "benefits"' in app_src.replace(" ", "") or '"benefits": "benefits"' in app_src)
    manager_block = app_src.split("_POSTHIRE_PERMS_MANAGER")[1].split("}")[0]
    check("manager fixture has no benefits perms", "benefits." not in manager_block)

    http_src = (ROOT / "benefits_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/benefits",
        "/app/benefits",
        "/workspace",
        "/plans",
        "/versions",
        "/eligibility",
        "/enrollments",
        "/waivers",
        "/dependents",
        "/coverage",
        "/contributions",
        "/handoffs",
        "/members",
        "/history",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP uses employee_app_context", "employee_app_context" in http_src)
    check("HTTP refuses manager workspace", "Managers do not have a Benefits workspace" in http_src)
    check("employee elect never confirms coverage", "confirm_enrollment" not in http_src.split("app_benefits_elect")[1][:800])
    surf_src = (ROOT / "benefits_surfaces.py").read_text(encoding="utf-8")
    check("employee elect adapter never confirms", "Never confirms coverage" in surf_src)
    check("no second dependent master", "does_not_create_dependent_master" in surf_src)
    check("no claims engine", "claims_out" in surf_src)
    check("no frontend financial authority in surfaces", "paid_amount" in surf_src and "None" in surf_src)

    emp_comp = (MOBILE / "src" / "composition" / "employeeAppComposition.ts").read_text(encoding="utf-8")
    check("employee composition has benefits", "'benefits'" in emp_comp)
    check("employee hub exists", (MOBILE / "app" / "benefits" / "index.tsx").is_file())
    check("employee plan exists", (MOBILE / "app" / "benefits" / "plan.tsx").is_file())
    check("employee history exists", (MOBILE / "app" / "benefits" / "history.tsx").is_file())
    check("no HR mobile benefits admin", not (MOBILE / "app" / "hr" / "benefits").exists())
    en = (MOBILE / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    ar = (MOBILE / "src" / "i18n" / "ar.json").read_text(encoding="utf-8")
    check("employee EN copy", '"benefits"' in en and "Eligible plans" in en)
    check("employee AR copy", "المزايا" in ar and "الخطط المؤهلة" in ar)
    check("employee error is not empty copy", "ErrorState" in (MOBILE / "app" / "benefits" / "index.tsx").read_text(encoding="utf-8"))

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    benefits = client.get("/dashboard/benefits/workspace")
    check(
        "fail-closed no longer steals Benefits",
        not (
            benefits.status_code == 404
            and isinstance(benefits.json().get("detail"), dict)
            and benefits.json()["detail"].get("error") == "capability_not_released"
        ),
        benefits.json() if benefits.headers.get("content-type", "").startswith("application/json") else benefits.status_code,
    )
    er = client.get("/dashboard/employee-relations/cases")
    er_detail = er.json().get("detail") if er.headers.get("content-type", "").startswith("application/json") else None
    check(
        "fail-closed no longer steals ER",
        not (
            er.status_code == 404
            and isinstance(er_detail, dict)
            and er_detail.get("error") == "capability_not_released"
        ),
        er_detail,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5F_BENEFITS_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
