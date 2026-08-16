#!/usr/bin/env python3
"""Production Readiness R5B — Performance product surface unit contracts (no DB)."""
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
    import performance_surfaces as surfaces
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5B — performance surface (unit)")

    check("performance customer enableable", ready.customer_enableable("performance") is True)
    check("performance customer visible", ready.customer_visible("performance") is True)
    check("talent now enableable after R5C", ready.customer_enableable("talent") is True)
    check("performance is catalog SKU", "performance" in catalog.MODULE_BY_KEY)
    check("talent is catalog SKU after R5C", "talent" in catalog.MODULE_BY_KEY)
    payload = ready.readiness_payload("performance")
    for flag in ("http_ready", "hr_web_ready", "employee_surface_ready", "manager_surface_ready", "mobile_ready"):
        check(f"performance {flag}", payload.get(flag) is True)
    check("fail-closed skips performance namespaces", ("performance", "/dashboard/performance") not in ready.all_http_namespaces())
    check("fail-closed skips talent namespaces", ("talent", "/dashboard/posthire/talent") not in ready.all_http_namespaces())

    stripped = surfaces.strip_talent(
        {"final_rating_value": 5, "hipo": True, "potential": "high", "nine_box": "top", "ok": True}
    )
    check("strip hipo", "hipo" not in stripped)
    check("strip potential", "potential" not in stripped)
    check("strip nine_box", "nine_box" not in stripped)
    check("keep rating", stripped.get("final_rating_value") == 5)
    check("high performer is not hipo honesty", surfaces.honesty_payload().get("high_performer_is_not_hipo") is True)
    check("learning not required", surfaces.honesty_payload().get("learning_required") is False)

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts Performance policies", "Wave4PerformancePoliciesCard" in setup_app)
    check("Setup remounts Job Architecture after R5D", "Wave6JobArchitecturePoliciesCard" in setup_app)
    check("Setup remounts Learning after R5E", "Wave6LearningPoliciesCard" in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts Performance workspace", "PerformanceWorkspace" in posthire)
    workspace = (DASH / "posthire" / "PerformanceWorkspace.tsx").read_text(encoding="utf-8")
    for needle in ("nine_box", "succession", "talent_score"):
        check(f"workspace has no {needle}", needle not in workspace)
    check("workspace bilingual AR", "الأداء" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace no frontend rollup formula", "progress_pct =" not in workspace)

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes performance", "| 'performance'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.performance registered", "nav.performance" in nav)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers performance HTTP", "register_performance_http" in app_src)
    check("performance permissions exist", "performance.read" in app_src and "performance.calibrate" in app_src)
    check("employee feature performance", '"performance"' in app_src and "module_keys\": (\"performance\",)" in app_src.replace(" ", "") or "module_keys\": (\"performance\")" in app_src.replace(" ", "") or 'module_keys": ("performance",)' in app_src)

    http_src = (ROOT / "performance_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/performance/workspace",
        "/dashboard/performance/objectives",
        "/dashboard/performance/cycles",
        "/dashboard/performance/reviews",
        "/dashboard/performance/calibration",
        "/dashboard/performance/development",
        "/dashboard/performance/competencies",
        "/dashboard/performance/feedback",
        "/dashboard/mobile/performance",
        "/app/performance",
    ):
        check(f"HTTP exposes {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP uses employee_app_context", "employee_app_context" in http_src)

    emp_comp = (MOBILE / "src" / "composition" / "employeeAppComposition.ts").read_text(encoding="utf-8")
    check("employee composition has performance", "'performance'" in emp_comp or '"performance"' in emp_comp)
    check("employee hub exists", (MOBILE / "app" / "performance" / "index.tsx").is_file())
    check("employee goals exists", (MOBILE / "app" / "performance" / "goals.tsx").is_file())
    check("employee reviews exists", (MOBILE / "app" / "performance" / "reviews.tsx").is_file())
    check("HR mobile queue exists", (MOBILE / "app" / "hr" / "performance" / "index.tsx").is_file())
    check("HR mobile detail exists", (MOBILE / "app" / "hr" / "performance" / "[reviewId].tsx").is_file())
    en = (MOBILE / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    ar = (MOBILE / "src" / "i18n" / "ar.json").read_text(encoding="utf-8")
    check("employee EN copy", '"performance"' in en and "My goals" in en)
    check("employee AR copy", "أهدافي" in ar)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    perf = client.get("/dashboard/performance/workspace")
    check(
        "fail-closed no longer steals performance",
        not (
            perf.status_code == 404
            and isinstance(perf.json().get("detail"), dict)
            and perf.json()["detail"].get("error") == "capability_not_released"
        ),
        perf.json() if perf.headers.get("content-type", "").startswith("application/json") else perf.status_code,
    )
    talent = client.get("/dashboard/posthire/talent")
    detail = talent.json().get("detail") if talent.headers.get("content-type", "").startswith("application/json") else None
    check(
        "fail-closed no longer steals talent",
        not (talent.status_code == 404 and isinstance(detail, dict) and detail.get("error") == "capability_not_released"),
        detail,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5B_PERFORMANCE_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
