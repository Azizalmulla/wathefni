#!/usr/bin/env python3
"""Production Readiness R5G — Employee Relations product surface unit contracts (no DB)."""
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
    import employee_relations_surfaces as surfaces
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5G — employee relations surface (unit)")

    check("ER customer enableable", ready.customer_enableable("employee_relations") is True)
    check("ER customer visible", ready.customer_visible("employee_relations") is True)
    check("benefits still enableable", ready.customer_enableable("benefits") is True)
    check("learning still enableable", ready.customer_enableable("learning") is True)
    check("engagement now enableable after R5H", ready.customer_enableable("engagement") is True)
    check("comp planning now enableable after R5I", ready.customer_enableable("comp_planning") is True)
    check("workforce planning still hidden", ready.customer_enableable("workforce_planning") is False)
    check("ER is catalog SKU", "employee_relations" in catalog.MODULE_BY_KEY)
    check("ER people_surface off", catalog.MODULE_BY_KEY["employee_relations"].people_surface is False)
    check("ER audience is hr", catalog.MODULE_BY_KEY["employee_relations"].audience == "hr")
    payload = ready.readiness_payload("employee_relations")
    for flag in ("domain_authority_ready", "http_ready", "hr_web_ready", "mobile_ready"):
        check(f"ER {flag}", payload.get(flag) is True)
    check("ER employee surface not required", payload.get("employee_surface_required") is False)
    check("ER manager surface not required", payload.get("manager_surface_required") is False)
    check("ER employee surface not ready", payload.get("employee_surface_ready") is False)
    check("ER manager surface not ready", payload.get("manager_surface_ready") is False)
    check(
        "fail-closed skips ER namespaces",
        ("employee_relations", "/dashboard/employee-relations") not in ready.all_http_namespaces(),
    )
    check(
        "fail-closed skips engagement",
        ("engagement", "/dashboard/engagement") not in ready.all_http_namespaces(),
    )

    honesty = surfaces.honesty_payload()
    check("submission ≠ proven", honesty.get("submission_is_not_allegation_proven") is True)
    check("investigation ≠ finding", honesty.get("investigation_is_not_finding") is True)
    check("finding ≠ outcome", honesty.get("finding_is_not_outcome") is True)
    check("outcome ≠ employment mutation", honesty.get("outcome_is_not_employment_mutation") is True)
    check("empty assignment ≠ company-wide", honesty.get("empty_assignment_is_not_company_wide") is True)
    check("ordinary HR ≠ ER", honesty.get("ordinary_hr_not_er") is True)
    check("manager ≠ ER", honesty.get("manager_not_er") is True)
    check("no ER scoring", honesty.get("no_er_scoring") is True)
    check("assistant mutations out", honesty.get("assistant_mutations") is False)
    check("C4 remains canonical", "employee_relations_c4" in (honesty.get("canonical_authority") or ()))
    check("wave5 excludes free text", honesty.get("wave5_excludes_sensitive_free_text") is True)

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts ER", "Wave6EmployeeRelationsPoliciesCard" in setup_app)
    check("Setup still remounts Benefits", "Wave6BenefitsPoliciesCard" in setup_app)
    check("Setup remounts Engagement after R5H", "Wave6EngagementPoliciesCard" in setup_app)
    check("Setup remounts Comp Planning after R5I", "Wave6CompensationPlanningPoliciesCard" in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts ER workspace", "EmployeeRelationsWorkspace" in posthire)
    workspace = (DASH / "posthire" / "EmployeeRelationsWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "علاقات الموظفين" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace names intake boundary", "Intake (not a finding)" in workspace or "استلام (ليس نتيجة)" in workspace)
    check("workspace names employment boundary", "not an employment mutation" in workspace or "ليست تغييراً في التوظيف" in workspace)
    check("workspace is not a generic task list", "not a generic HR task list" in workspace or "ليست قائمة مهام" in workspace)
    check("403 is not empty-cases copy", "forbidden" in workspace and "emptyCases" in workspace)

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes employee-relations", "| 'employee-relations'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.employee-relations registered", "nav.employee-relations" in nav)
    check("nav uses er.read", "permission: 'er.read'" in nav)
    catalog_src = (DASH / "lib" / "moduleWorkspace.ts").read_text(encoding="utf-8")
    modules_block = catalog_src.split("CANONICAL_POSTHIRE_MODULES")[1].split("]")[0]
    people_block = catalog_src.split("CANONICAL_POSTHIRE_PEOPLE_MODULES")[1].split("]")[0]
    check("ER is a canonical posthire SKU", "'employee_relations'" in modules_block)
    check("ER is not a people-360 module", "'employee_relations'" not in people_block)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers ER HTTP", "register_employee_relations_http" in app_src)
    for perm in ("er.read", "er.manage", "er.investigate", "er.decide", "er.sensitive", "er.export"):
        check(f"{perm} permission exists", perm in app_src)
    check("notification flow ER", '"employee_relations": "employee_relations"' in app_src.replace(" ", "") or '"employee_relations": "employee_relations"' in app_src)
    manager_block = app_src.split("_POSTHIRE_PERMS_MANAGER")[1].split("}")[0]
    viewer_block = app_src.split("_POSTHIRE_PERMS_VIEWER")[1].split("}")[0]
    check("manager fixture has no er perms", "er." not in manager_block)
    check("viewer fixture has no er perms", "er." not in viewer_block)

    http_src = (ROOT / "employee_relations_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/employee-relations",
        "/dashboard/mobile/employee-relations",
        "/workspace",
        "/cases",
        "/triage",
        "/assign",
        "/notes",
        "/evidence",
        "/findings",
        "/outcomes",
        "/closure",
        "/handoffs",
        "/history",
        "/export",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("no employee app ER workspace", "/app/employee-relations" not in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP refuses manager workspace", "Managers do not have an Employee Relations workspace" in http_src)
    check("privacy-safe notification copy", "Employee Relations action requires your attention" in (ROOT / "employee_relations_surfaces.py").read_text(encoding="utf-8"))
    surf_src = (ROOT / "employee_relations_surfaces.py").read_text(encoding="utf-8")
    check("no second ER model", "canonical_authority" in surf_src and "employee_relations_c4" in surf_src)
    check("no ER scoring", "no_er_scoring" in surf_src)
    check("handoff idempotent", "create_handoff_idempotent" in surf_src)
    check("evidence strips raw URLs", "shared_document_ref" in surf_src and "RAW_URL_KEYS" in surf_src)
    check("assistant wrapper grant-scoped", "assistant_query" in surf_src and "er_access_denied" in surf_src)

    check("HR mobile queue exists", (MOBILE / "app" / "hr" / "employee-relations" / "index.tsx").is_file())
    check("HR mobile case exists", (MOBILE / "app" / "hr" / "employee-relations" / "[caseId].tsx").is_file())
    check("no employee app ER workspace dir", not (MOBILE / "app" / "employee-relations").exists())
    en = (MOBILE / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    ar = (MOBILE / "src" / "i18n" / "ar.json").read_text(encoding="utf-8")
    check("HR mobile EN copy", "hrEmployeeRelations" in en and "Employee Relations action" not in en or "Assigned actions" in en)
    check("HR mobile AR copy", "علاقات الموظفين" in ar)
    emp_comp = (MOBILE / "src" / "composition" / "employeeAppComposition.ts").read_text(encoding="utf-8")
    check("employee composition has no ER case workspace", "employee_relations" not in emp_comp and "employee-relations" not in emp_comp)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    er = client.get("/dashboard/employee-relations/workspace")
    check(
        "fail-closed no longer steals ER",
        not (
            er.status_code == 404
            and isinstance(er.json().get("detail"), dict)
            and er.json()["detail"].get("error") == "capability_not_released"
        ),
        er.json() if er.headers.get("content-type", "").startswith("application/json") else er.status_code,
    )
    engagement = client.get("/dashboard/engagement")
    check(
        "fail-closed no longer steals Engagement",
        not (
            engagement.status_code == 404
            and isinstance(engagement.json().get("detail"), dict)
            and engagement.json()["detail"].get("error") == "capability_not_released"
        ),
        engagement.json() if engagement.headers.get("content-type", "").startswith("application/json") else engagement.status_code,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5G_EMPLOYEE_RELATIONS_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
