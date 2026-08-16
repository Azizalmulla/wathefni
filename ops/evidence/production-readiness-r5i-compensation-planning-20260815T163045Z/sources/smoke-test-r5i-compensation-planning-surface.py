#!/usr/bin/env python3
"""Production Readiness R5I — Compensation Planning product surface unit contracts (no DB)."""
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
    import compensation_surfaces as surfaces
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5I — compensation planning surface (unit)")

    check("comp planning customer enableable", ready.customer_enableable("comp_planning") is True)
    check("comp planning customer visible", ready.customer_visible("comp_planning") is True)
    check("JA still enableable (hard dep)", ready.customer_enableable("job_architecture") is True)
    check("engagement still enableable", ready.customer_enableable("engagement") is True)
    check("workforce planning still hidden", ready.customer_enableable("workforce_planning") is False)
    check("comp planning is catalog SKU", "comp_planning" in catalog.MODULE_BY_KEY)
    check("comp planning people_surface off", catalog.MODULE_BY_KEY["comp_planning"].people_surface is False)
    check("comp planning audience is hr", catalog.MODULE_BY_KEY["comp_planning"].audience == "hr")
    check("comp planning has no employee app surface", catalog.MODULE_BY_KEY["comp_planning"].app_surface_key is None)
    payload = ready.readiness_payload("comp_planning")
    for flag in ("domain_authority_ready", "http_ready", "hr_web_ready"):
        check(f"comp planning {flag}", payload.get(flag) is True)
    check("comp planning employee surface not required", payload.get("employee_surface_required") is False)
    check("comp planning employee surface not ready", payload.get("employee_surface_ready") is False)
    check("comp planning manager surface not required", payload.get("manager_surface_required") is False)
    check("comp planning manager surface ready (optional)", payload.get("manager_surface_ready") is True)
    check("comp planning mobile not required", payload.get("mobile_required") is False)
    check("comp planning mobile not ready", payload.get("mobile_ready") is False)
    check("comp planning depends on JA", "job_architecture" in (payload.get("depends_on") or ()))
    check(
        "fail-closed skips comp planning namespaces",
        ("comp_planning", "/dashboard/compensation-planning") not in ready.all_http_namespaces(),
    )
    check(
        "fail-closed keeps workforce planning",
        ("workforce_planning", "/dashboard/workforce-planning") in ready.all_http_namespaces(),
    )

    honesty = surfaces.honesty_payload()
    check("plan ≠ salary change", honesty.get("compensation_plan_is_not_salary_change") is True)
    check("salary change ≠ payroll", honesty.get("salary_change_is_not_payroll_application") is True)
    check("payroll ≠ paid", honesty.get("payroll_application_is_not_paid") is True)
    check("finalized ≠ applied", honesty.get("finalized_is_not_applied") is True)
    check("eligible ≠ increase", honesty.get("eligible_is_not_increase") is True)
    check("grade ≠ band", honesty.get("grade_is_not_salary_band") is True)
    check("range ≠ salary", honesty.get("salary_range_is_not_employee_salary") is True)
    check("recommendation ≠ approval", honesty.get("recommendation_is_not_approval") is True)
    check("original preserved", honesty.get("original_recommendation_preserved") is True)
    check("JA is hard", honesty.get("ja_is_hard") is True)
    check("no duplicate grades", honesty.get("no_duplicate_grades") is True)
    check("no FX", honesty.get("no_fx") is True)
    check("KWD explicit", honesty.get("kwd_explicit") is True)
    check("performance optional", honesty.get("performance_optional") is True)
    check("rating not automatic", honesty.get("rating_not_automatic_increase") is True)
    check("talent optional", honesty.get("talent_optional") is True)
    check("HiPo not automatic", honesty.get("hipo_not_automatic_pay") is True)
    check("empty manager is zero rows", honesty.get("empty_manager_scope_is_zero_rows") is True)
    check("assistant mutations out", honesty.get("assistant_mutations") is False)
    check("C6 remains canonical", "compensation_planning_c6" in (honesty.get("canonical_authority") or ()))

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts Comp Planning", "Wave6CompensationPlanningPoliciesCard" in setup_app)
    check("Setup still remounts Engagement", "Wave6EngagementPoliciesCard" in setup_app)
    check("Setup still remounts JA", "Wave6JobArchitecturePoliciesCard" in setup_app)
    check("Setup still omits Workforce Planning", "Wave6WorkforcePlanningPoliciesCard" not in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts Comp Planning workspace", "CompensationPlanningWorkspace" in posthire)
    workspace = (DASH / "posthire" / "CompensationPlanningWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "تخطيط التعويضات" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace names plan boundary", "not a salary change" in workspace or "ليست تغييراً في الراتب" in workspace)
    check("workspace names eligible boundary", "eligible is not an increase" in workspace or "الأهلية ليست زيادة" in workspace)
    check("workspace names finalized boundary", "Finalized is not applied" in workspace or "النهائي ليس تطبيقاً" in workspace)
    check("workspace names KWD", "KWD" in workspace and "د.ك" in workspace)
    check("403 is not empty-cycles copy", "forbidden" in workspace and "emptyCycles" in workspace)
    check("403 copy is not No compensation changes", "No compensation changes" not in workspace)

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes compensation-planning", "| 'compensation-planning'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.compensation-planning registered", "nav.compensation-planning" in nav)
    check("nav allows manager or read", "comp_planning.manager" in nav and "comp_planning.read" in nav)
    catalog_src = (DASH / "lib" / "moduleWorkspace.ts").read_text(encoding="utf-8")
    modules_block = catalog_src.split("CANONICAL_POSTHIRE_MODULES")[1].split("]")[0]
    people_block = catalog_src.split("CANONICAL_POSTHIRE_PEOPLE_MODULES")[1].split("]")[0]
    check("comp_planning is a canonical posthire SKU", "'comp_planning'" in modules_block)
    check("comp_planning is not a people-360 module", "'comp_planning'" not in people_block)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers Comp Planning HTTP", "register_compensation_planning_http" in app_src)
    for perm in (
        "comp_planning.read",
        "comp_planning.manage",
        "comp_planning.recommend",
        "comp_planning.calibrate",
        "comp_planning.approve",
        "comp_planning.finalize",
        "comp_planning.export",
        "comp_planning.manager",
    ):
        check(f"{perm} permission exists", perm in app_src)
    check("notification flow compensation_planning", '"compensation_planning": "comp_planning"' in app_src)
    manager_block = app_src.split("_POSTHIRE_PERMS_MANAGER")[1].split("}")[0]
    viewer_block = app_src.split("_POSTHIRE_PERMS_VIEWER")[1].split("}")[0]
    full_block = app_src.split("_POSTHIRE_PERMS_FULL")[1].split("}")[0]
    check("manager fixture has comp_planning.manager", '"comp_planning.manager"' in manager_block)
    check("manager fixture has no comp_planning.manage", '"comp_planning.manage"' not in manager_block)
    check("viewer fixture has no comp_planning admin", '"comp_planning.manage"' not in viewer_block)
    check("HR full has comp_planning.read", "comp_planning.read" in full_block)

    http_src = (ROOT / "compensation_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/compensation-planning",
        "/workspace",
        "/cycles",
        "/eligibility",
        "/budgets",
        "/bands",
        "/worksheet",
        "/recommendations",
        "/calibrate",
        "/approve",
        "/finalize",
        "/finalized",
        "/handoffs",
        "/execution",
        "/history",
        "/export",
        "/manager",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP derives actor_key from context", "_actor_key" in http_src)
    check("HTTP refuses manager admin workspace", "Managers do not have a Compensation Planning administration workspace" in http_src)
    check("no Employee App compensation namespace", "/app/compensation-planning" not in http_src)
    check("no HR Mobile compensation namespace", "/dashboard/mobile/compensation-planning" not in http_src)
    check("notification copy has no salary", "A Compensation Planning action requires your attention." in http_src)
    notify_text = http_src.split('text="')[1].split('"')[0] if 'text="' in http_src else ""
    check("notification text does not leak salary values", "KWD" not in notify_text and "salary" not in notify_text.lower() and "amount" not in notify_text.lower())
    surf_src = (ROOT / "compensation_surfaces.py").read_text(encoding="utf-8")
    check("no second compensation model", "canonical_authority" in surf_src and "compensation_planning_c6" in surf_src)
    check("no frontend math authority", "compute_compa_ratio" in surf_src and "c6.compute_compa_ratio" in surf_src)
    check("handoff idempotent wrapper", "idempotent_replay" in surf_src)
    check("assistant wrapper exists", "assistant_query" in surf_src)
    check("no local grade table", "cp_grade" not in surf_src)

    check("no employee hub", not (MOBILE / "app" / "compensation-planning").exists())
    check("no employee compensation dir", not (MOBILE / "app" / "compensation").exists())
    check("no HR mobile compensation dir", not (MOBILE / "app" / "hr" / "compensation-planning").exists())

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    cp = client.get("/dashboard/compensation-planning/workspace")
    check(
        "fail-closed no longer steals Compensation Planning",
        not (
            cp.status_code == 404
            and isinstance(cp.json().get("detail"), dict)
            and cp.json()["detail"].get("error") == "capability_not_released"
        ),
        cp.json() if cp.headers.get("content-type", "").startswith("application/json") else cp.status_code,
    )
    wfp = client.get("/dashboard/workforce-planning/plans")
    wfp_detail = wfp.json().get("detail") if wfp.headers.get("content-type", "").startswith("application/json") else None
    check(
        "workforce planning still fail-closed",
        wfp.status_code == 404
        and isinstance(wfp_detail, dict)
        and wfp_detail.get("error") == "capability_not_released",
        wfp_detail,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5I_COMPENSATION_PLANNING_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
