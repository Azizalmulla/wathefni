#!/usr/bin/env python3
"""Production Readiness R5C — Talent product surface unit contracts (no DB)."""
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
    import talent_surfaces as surfaces
    import performance_surfaces as perf
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5C — talent surface (unit)")

    check("talent customer enableable", ready.customer_enableable("talent") is True)
    check("talent customer visible", ready.customer_visible("talent") is True)
    check("performance still enableable", ready.customer_enableable("performance") is True)
    check("job architecture still hidden", ready.customer_enableable("job_architecture") is False)
    check("talent is catalog SKU", "talent" in catalog.MODULE_BY_KEY)
    check("talent_pool is not the HCM SKU", catalog.MODULE_BY_KEY["talent"].app_surface_key == "talent")
    payload = ready.readiness_payload("talent")
    for flag in ("http_ready", "hr_web_ready", "employee_surface_ready", "manager_surface_ready"):
        check(f"talent {flag}", payload.get(flag) is True)
    check("talent mobile not required", payload.get("mobile_required") is False)
    check("fail-closed skips talent namespaces", ("talent", "/dashboard/posthire/talent") not in ready.all_http_namespaces())
    check("fail-closed keeps JA namespaces", ("job_architecture", "/dashboard/job-architecture") in ready.all_http_namespaces())

    honesty = surfaces.honesty_payload()
    check("no master score", honesty.get("no_master_talent_score") is True)
    check("high performer is not hipo", honesty.get("high_performer_is_not_hipo") is True)
    check("nine-box derived", honesty.get("nine_box_is_projection_not_sot") is True)
    check("pool isolated", honesty.get("recruiting_talent_pool_isolated") is True)
    check("learning not required", honesty.get("learning_required") is False)
    check("JA not required", honesty.get("job_architecture_required") is False)

    stripped = surfaces.strip_employee_judgments(
        {"facts": [{"title_en": "ok"}], "hipo": True, "potential": "high", "nine_box": "top"}
    )
    check("employee strip hipo", "hipo" not in stripped)
    check("employee strip potential", "potential" not in stripped)
    check("employee keeps facts", bool(stripped.get("facts")))

    perf_stripped = perf.strip_talent({"final_rating_value": 5, "hipo": True, "ok": True})
    check("performance still strips hipo", "hipo" not in perf_stripped)
    check("performance keeps rating", perf_stripped.get("final_rating_value") == 5)

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts Talent policies", "Wave4TalentPoliciesCard" in setup_app)
    check("Setup still remounts Performance", "Wave4PerformancePoliciesCard" in setup_app)
    check("Setup still omits Wave6 cards", "Wave6JobArchitecturePoliciesCard" not in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts Talent workspace", "TalentWorkspace" in posthire)
    workspace = (DASH / "posthire" / "TalentWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "المواهب" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace no talent_score formula", "talent_score =" not in workspace)
    check("workspace names recruiting pool boundary", "talent_pool" in workspace or "recruiting" in workspace.lower())

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes talent", "| 'talent'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.talent registered", "nav.talent" in nav)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers talent HTTP", "register_talent_http" in app_src)
    check("talent permissions exist", "talent.read" in app_src and "talent.sensitive" in app_src and "talent.succession" in app_src)
    check("employee feature talent", 'module_keys": ("talent",)' in app_src.replace(" ", "") or 'module_keys": ("talent",)' in app_src)

    http_src = (ROOT / "talent_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/posthire/talent",
        "/dashboard/talent",
        "/app/talent",
        "/workspace",
        "/profiles",
        "/reviews",
        "/hipo",
        "/succession",
        "/nine-box",
        "/mobility",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP uses employee_app_context", "employee_app_context" in http_src)
    check("HTTP does not write talent_pool", "INSERT INTO talent_pool" not in http_src)

    emp_comp = (MOBILE / "src" / "composition" / "employeeAppComposition.ts").read_text(encoding="utf-8")
    check("employee composition has talent", "'talent'" in emp_comp or '"talent"' in emp_comp)
    check("employee hub exists", (MOBILE / "app" / "talent" / "index.tsx").is_file())
    check("employee profile exists", (MOBILE / "app" / "talent" / "profile.tsx").is_file())
    check("no HR mobile talent admin", not (MOBILE / "app" / "hr" / "talent").exists())
    en = (MOBILE / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    ar = (MOBILE / "src" / "i18n" / "ar.json").read_text(encoding="utf-8")
    check("employee EN copy", '"talent"' in en and "Career interests" in en)
    check("employee AR copy", "الاهتمامات المهنية" in ar)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    talent = client.get("/dashboard/posthire/talent/workspace")
    check(
        "fail-closed no longer steals talent",
        not (
            talent.status_code == 404
            and isinstance(talent.json().get("detail"), dict)
            and talent.json()["detail"].get("error") == "capability_not_released"
        ),
        talent.json() if talent.headers.get("content-type", "").startswith("application/json") else talent.status_code,
    )
    ja = client.get("/dashboard/job-architecture")
    detail = ja.json().get("detail") if ja.headers.get("content-type", "").startswith("application/json") else None
    check(
        "JA still fail-closed",
        ja.status_code == 404 and isinstance(detail, dict) and detail.get("error") == "capability_not_released",
        detail,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5C_TALENT_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
