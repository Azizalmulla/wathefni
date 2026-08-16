#!/usr/bin/env python3
"""Production Readiness R5J — Workforce Planning product surface unit contracts (no DB)."""
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
    import workforce_planning_surfaces as surfaces
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5J — workforce planning surface (unit)")

    check("workforce planning customer enableable", ready.customer_enableable("workforce_planning") is True)
    check("workforce planning customer visible", ready.customer_visible("workforce_planning") is True)
    check("JA still enableable (hard dep)", ready.customer_enableable("job_architecture") is True)
    check("comp planning still enableable", ready.customer_enableable("comp_planning") is True)
    check("engagement still enableable", ready.customer_enableable("engagement") is True)
    check("no remaining unreleased keys", ready.UNRELEASED_CAPABILITY_KEYS == ())
    check("workforce planning is catalog SKU", "workforce_planning" in catalog.MODULE_BY_KEY)
    check("workforce planning people_surface off", catalog.MODULE_BY_KEY["workforce_planning"].people_surface is False)
    check("workforce planning audience is hr", catalog.MODULE_BY_KEY["workforce_planning"].audience == "hr")
    check("workforce planning has no employee app surface", catalog.MODULE_BY_KEY["workforce_planning"].app_surface_key is None)
    payload = ready.readiness_payload("workforce_planning")
    for flag in ("domain_authority_ready", "http_ready", "hr_web_ready"):
        check(f"workforce planning {flag}", payload.get(flag) is True)
    check("workforce planning employee surface not required", payload.get("employee_surface_required") is False)
    check("workforce planning employee surface not ready", payload.get("employee_surface_ready") is False)
    check("workforce planning manager surface not required", payload.get("manager_surface_required") is False)
    check("workforce planning manager surface ready (optional)", payload.get("manager_surface_ready") is True)
    check("workforce planning mobile not required", payload.get("mobile_required") is False)
    check("workforce planning mobile not ready", payload.get("mobile_ready") is False)
    check("workforce planning depends on JA", "job_architecture" in (payload.get("depends_on") or ()))
    check(
        "fail-closed skips workforce planning namespaces",
        ("workforce_planning", "/dashboard/workforce-planning") not in ready.all_http_namespaces(),
    )

    honesty = surfaces.honesty_payload()
    check("actual ≠ baseline", honesty.get("actual_ne_baseline") is True)
    check("actual ≠ plan", honesty.get("actual_ne_plan") is True)
    check("baseline ≠ scenario", honesty.get("baseline_ne_scenario") is True)
    check("scenario ≠ approved execution", honesty.get("scenario_ne_approved_execution") is True)
    check("planned HC never actual Wave 5", honesty.get("planned_headcount_never_enters_actual_wave5") is True)
    check("planned position ≠ actual", honesty.get("planned_position_ne_actual_position") is True)
    check("planned cost ≠ payroll", honesty.get("planned_cost_ne_finalized_payroll_cost") is True)
    check("approval ≠ actual change", honesty.get("approval_ne_actual_workforce_change") is True)
    check("JA is hard", honesty.get("ja_is_hard") is True)
    check("no duplicate job catalog", honesty.get("no_duplicate_planning_job_catalog") is True)
    check("no AI forecast", honesty.get("no_ai_forecast_authority") is True)
    check("no frontend forecast", honesty.get("no_frontend_forecast_authority") is True)
    check("no universal gap score", honesty.get("no_universal_workforce_gap_score") is True)
    check("no FX", honesty.get("no_fx") is True)
    check("KWD explicit", honesty.get("kwd_explicit") is True)
    check("recruiting optional", honesty.get("recruiting_optional") is True)
    check("comp optional", honesty.get("comp_planning_optional") is True)
    check("talent optional", honesty.get("talent_optional") is True)
    check("empty manager is zero rows", honesty.get("empty_manager_scope_is_zero_rows") is True)
    check("assistant mutations out", honesty.get("assistant_mutations") is False)
    check("C7 remains canonical", "workforce_planning_c7" in (honesty.get("canonical_authority") or ()))

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts Workforce Planning", "Wave6WorkforcePlanningPoliciesCard" in setup_app)
    check("Setup still remounts Comp Planning", "Wave6CompensationPlanningPoliciesCard" in setup_app)
    check("Setup still remounts JA", "Wave6JobArchitecturePoliciesCard" in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts Workforce Planning workspace", "WorkforcePlanningWorkspace" in posthire)
    workspace = (DASH / "posthire" / "WorkforcePlanningWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "تخطيط القوى العاملة" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace names actual/baseline boundary", "actual is not baseline" in workspace.lower() or "الفعلي ليس خط الأساس" in workspace)
    check("workspace names planned cost", "planned / estimated" in workspace.lower() or "تكلفة القوى العاملة المخططة" in workspace)
    check("workspace names KWD", "KWD" in workspace and "د.ك" in workspace)
    check("403 is not empty-plans copy", "forbidden" in workspace and "emptyPlans" in workspace)
    check("403 copy is not No workforce gap", "No workforce gap" not in workspace)
    check("403 copy is not 0 planned hires", "0 planned hires" not in workspace)

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes workforce-planning", "| 'workforce-planning'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.workforce-planning registered", "nav.workforce-planning" in nav)
    check("nav allows manager or read", "workforce_planning.manager" in nav and "workforce_planning.read" in nav)
    catalog_src = (DASH / "lib" / "moduleWorkspace.ts").read_text(encoding="utf-8")
    modules_block = catalog_src.split("CANONICAL_POSTHIRE_MODULES")[1].split("]")[0]
    people_block = catalog_src.split("CANONICAL_POSTHIRE_PEOPLE_MODULES")[1].split("]")[0]
    check("workforce_planning is a canonical posthire SKU", "'workforce_planning'" in modules_block)
    check("workforce_planning is not a people-360 module", "'workforce_planning'" not in people_block)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers Workforce Planning HTTP", "register_workforce_planning_http" in app_src)
    for perm in (
        "workforce_planning.read",
        "workforce_planning.manage",
        "workforce_planning.plan",
        "workforce_planning.cost",
        "workforce_planning.approve",
        "workforce_planning.execute",
        "workforce_planning.export",
        "workforce_planning.manager",
    ):
        check(f"{perm} permission exists", perm in app_src)
    check("notification flow workforce_planning", '"workforce_planning": "workforce_planning"' in app_src)
    manager_block = app_src.split("_POSTHIRE_PERMS_MANAGER")[1].split("}")[0]
    viewer_block = app_src.split("_POSTHIRE_PERMS_VIEWER")[1].split("}")[0]
    full_block = app_src.split("_POSTHIRE_PERMS_FULL")[1].split("}")[0]
    check("manager fixture has workforce_planning.manager", '"workforce_planning.manager"' in manager_block)
    check("manager fixture has no workforce_planning.manage", '"workforce_planning.manage"' not in manager_block)
    check("viewer fixture has no workforce_planning admin", '"workforce_planning.manage"' not in viewer_block)
    check("HR full has workforce_planning.read", "workforce_planning.read" in full_block)
    check("HR full has workforce_planning.cost", "workforce_planning.cost" in full_block)

    http_src = (ROOT / "workforce_planning_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/workforce-planning",
        "/workspace",
        "/plans",
        "/baseline",
        "/scenarios",
        "/assumptions",
        "/demand",
        "/planned-positions",
        "/projection",
        "/cost",
        "/gaps",
        "/compare",
        "/submit",
        "/approve",
        "/handoffs",
        "/execution",
        "/actual-vs-plan",
        "/history",
        "/export",
        "/manager",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP derives actor_key from context", "_actor_key" in http_src)
    check("HTTP refuses manager admin workspace", "Managers do not have a Workforce Planning administration workspace" in http_src)
    check("no Employee App workforce-planning namespace", "/app/workforce-planning" not in http_src)
    check("no HR Mobile workforce-planning namespace", "/dashboard/mobile/workforce-planning" not in http_src)
    check("notification copy is generic", "A Workforce Planning action requires your attention." in http_src)
    notify_text = http_src.split('text="')[1].split('"')[0] if 'text="' in http_src else ""
    check(
        "notification text does not leak restructuring/cost",
        "KWD" not in notify_text
        and "reduction" not in notify_text.lower()
        and "layoff" not in notify_text.lower()
        and "cost" not in notify_text.lower(),
    )
    surf_src = (ROOT / "workforce_planning_surfaces.py").read_text(encoding="utf-8")
    check("no second workforce planning model", "canonical_authority" in surf_src and "workforce_planning_c7" in surf_src)
    check("projection stays C7", "c7.project_headcount" in surf_src)
    check("handoff idempotent wrapper", "handoff_idempotent" in surf_src)
    check("assistant wrapper exists", "assistant_query" in surf_src)
    check("no local job catalog", "wfp_job_profile" not in surf_src and "wfp_grade" not in surf_src)
    check("actual vs plan queries canonical actual", "canonical_actual_headcount" in surf_src)

    check("no employee hub", not (MOBILE / "app" / "workforce-planning").exists())
    check("no employee workforce dir", not (MOBILE / "app" / "workforce").exists())
    check("no HR mobile workforce-planning dir", not (MOBILE / "app" / "hr" / "workforce-planning").exists())

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    wfp = client.get("/dashboard/workforce-planning/workspace")
    check(
        "fail-closed no longer steals Workforce Planning",
        not (
            wfp.status_code == 404
            and isinstance(wfp.json().get("detail"), dict)
            and wfp.json()["detail"].get("error") == "capability_not_released"
        ),
        wfp.json() if wfp.headers.get("content-type", "").startswith("application/json") else wfp.status_code,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5J_WORKFORCE_PLANNING_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
