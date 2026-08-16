#!/usr/bin/env python3
"""Production Readiness R5D — Job Architecture product surface unit contracts (no DB)."""
from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DASH = REPO / "apps" / "wathefni-dashboard" / "src"


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
    import job_architecture_surfaces as surfaces
    import job_architecture_c1 as c1
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5D — job architecture surface (unit)")

    check("JA customer enableable", ready.customer_enableable("job_architecture") is True)
    check("JA customer visible", ready.customer_visible("job_architecture") is True)
    check("performance still enableable", ready.customer_enableable("performance") is True)
    check("talent still enableable", ready.customer_enableable("talent") is True)
    check("learning enableable after R5E", ready.customer_enableable("learning") is True)
    check("comp planning now enableable after R5I", ready.customer_enableable("comp_planning") is True)
    check("workforce planning still hidden", ready.customer_enableable("workforce_planning") is False)
    check("JA is not a catalog SKU", "job_architecture" not in catalog.MODULE_BY_KEY)
    check("JA commercial sku false", c1.COMMERCIAL_SKU is False)
    payload = ready.readiness_payload("job_architecture")
    for flag in ("domain_authority_ready", "http_ready", "hr_web_ready"):
        check(f"JA {flag}", payload.get(flag) is True)
    check("JA employee surface not required", payload.get("employee_surface_required") is False)
    check("JA manager surface not required", payload.get("manager_surface_required") is False)
    check("JA mobile not required", payload.get("mobile_required") is False)
    check("fail-closed skips JA namespaces", ("job_architecture", "/dashboard/job-architecture") not in ready.all_http_namespaces())
    check("fail-closed skips Learning", ("learning", "/dashboard/learning") not in ready.all_http_namespaces())

    honesty = surfaces.honesty_payload()
    check("not separate SKU", honesty.get("not_separate_customer_sku") is True)
    check("salary bands out", honesty.get("salary_bands_out_of_c1") is True)
    check("edges are not eligibility", honesty.get("career_edges_are_not_eligibility") is True)
    check("no fuzzy AI", honesty.get("no_fuzzy_ai_migration") is True)
    check("raw preserved", honesty.get("legacy_raw_preserved") is True)
    check("recruiting job is not JA profile", honesty.get("recruiting_job_is_not_ja_profile") is True)
    check("no employee shadow truth", honesty.get("no_shadow_employee_truth") is True)
    check("talent optional", honesty.get("talent_optional") is True)
    check("learning not required", honesty.get("learning_required") is False)
    check("comp planning not required", honesty.get("comp_planning_required") is False)

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts JA policies", "Wave6JobArchitecturePoliciesCard" in setup_app)
    check("Setup still remounts Talent", "Wave4TalentPoliciesCard" in setup_app)
    check("Setup still remounts Performance", "Wave4PerformancePoliciesCard" in setup_app)
    check("Setup remounts Learning after R5E", "Wave6LearningPoliciesCard" in setup_app)
    check("Setup remounts Comp Planning after R5I", "Wave6CompensationPlanningPoliciesCard" in setup_app)
    check("Setup still omits Workforce Planning", "Wave6WorkforcePlanningPoliciesCard" not in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts JA workspace", "JobArchitectureWorkspace" in posthire)
    workspace = (DASH / "posthire" / "JobArchitectureWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "هيكل الوظائف" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace no career score formula", "career_score =" not in workspace and "master_career_score =" not in workspace)
    check("workspace names Recruiting Job boundary", "Recruiting Job" in workspace or "وظيفة التوظيف" in workspace)
    check("workspace names requisition boundary", "requisition" in workspace.lower() or "طلب توظيف" in workspace)
    check("workspace edges not eligibility", "eligibility" in workspace.lower() or "أهلية" in workspace)
    check("no salary band authoring", "salary_band" not in workspace.lower())

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes job-architecture", "| 'job-architecture'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.job-architecture registered", "nav.job-architecture" in nav)
    check("nav has no catalog module key", "id: 'nav.job-architecture'" in nav and "permission: 'job_architecture.read'" in nav)
    catalog_src = (DASH / "lib" / "moduleWorkspace.ts").read_text(encoding="utf-8")
    check("JA not a canonical posthire SKU", "job-architecture" not in catalog_src.split("CANONICAL_POSTHIRE_MODULES")[1].split("]")[0])
    check("JA is a posthire nav page", "'job-architecture'" in catalog_src.split("POSTHIRE_NAV_PAGES")[1].split("]")[0])

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers JA HTTP", "register_job_architecture_http" in app_src)
    check("JA read permission exists", "job_architecture.read" in app_src)
    check("JA manage permission exists", "job_architecture.manage" in app_src)
    check("JA mapping permission exists", "job_architecture.mapping" in app_src)
    check("JA publish permission exists", "job_architecture.publish" in app_src)
    check("no employee JA feature", 'module_keys": ("job_architecture",)' not in app_src.replace(" ", ""))

    http_src = (ROOT / "job_architecture_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/job-architecture",
        "/workspace",
        "/families",
        "/functions",
        "/profiles",
        "/grades",
        "/levels",
        "/career-edges",
        "/history",
        "/mappings",
        "/assignments",
        "/refs",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP does not register employee app JA", "/app/job-architecture" not in http_src)
    check("HTTP refuses hard delete", "destructive_delete_forbidden" in http_src or "refuse_hard_delete" in http_src)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    ja = client.get("/dashboard/job-architecture/workspace")
    check(
        "fail-closed no longer steals JA",
        not (
            ja.status_code == 404
            and isinstance(ja.json().get("detail"), dict)
            and ja.json()["detail"].get("error") == "capability_not_released"
        ),
        ja.json() if ja.headers.get("content-type", "").startswith("application/json") else ja.status_code,
    )
    learning = client.get("/dashboard/learning")
    detail = learning.json().get("detail") if learning.headers.get("content-type", "").startswith("application/json") else None
    check(
        "fail-closed no longer steals Learning",
        not (
            learning.status_code == 404
            and isinstance(detail, dict)
            and detail.get("error") == "capability_not_released"
        ),
        detail or learning.status_code,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5D_JOB_ARCHITECTURE_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
