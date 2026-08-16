#!/usr/bin/env python3
"""Production Readiness R5E — Learning product surface unit contracts (no DB)."""
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
    import learning_surfaces as surfaces
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5E — learning surface (unit)")

    check("learning customer enableable", ready.customer_enableable("learning") is True)
    check("learning customer visible", ready.customer_visible("learning") is True)
    check("performance still enableable", ready.customer_enableable("performance") is True)
    check("talent still enableable", ready.customer_enableable("talent") is True)
    check("JA still enableable", ready.customer_enableable("job_architecture") is True)
    check("benefits still hidden", ready.customer_enableable("benefits") is False)
    check("learning is catalog SKU", "learning" in catalog.MODULE_BY_KEY)
    check("JA is not a catalog SKU", "job_architecture" not in catalog.MODULE_BY_KEY)
    payload = ready.readiness_payload("learning")
    for flag in ("domain_authority_ready", "http_ready", "hr_web_ready", "employee_surface_ready", "manager_surface_ready"):
        check(f"learning {flag}", payload.get(flag) is True)
    check("learning mobile not required", payload.get("mobile_required") is False)
    check("fail-closed skips Learning namespaces", ("learning", "/dashboard/learning") not in ready.all_http_namespaces())
    check("fail-closed keeps Benefits", ("benefits", "/dashboard/benefits") in ready.all_http_namespaces())

    honesty = surfaces.honesty_payload()
    check("assignment ≠ enrollment", honesty.get("assignment_is_not_enrollment") is True)
    check("enrollment ≠ completion", honesty.get("enrollment_is_not_completion") is True)
    check("attendance ≠ completion", honesty.get("attendance_is_not_completion") is True)
    check("completion ≠ certification", honesty.get("completion_is_not_certification") is True)
    check("no competency auto-verify", honesty.get("course_completion_is_not_competency_verification") is True)
    check("overdue ≠ failure", honesty.get("overdue_is_not_automatic_failure") is True)
    check("performance optional", honesty.get("performance_optional") is True)
    check("talent optional", honesty.get("talent_optional") is True)
    check("JA optional", honesty.get("job_architecture_optional") is True)
    check("no learning talent score", honesty.get("no_learning_talent_score") is True)
    check("no auto hipo", honesty.get("no_auto_hipo") is True)
    check("C3 remains canonical", honesty.get("c3_development_remains_canonical") is True)
    check("no silent C3 close", honesty.get("learning_completion_does_not_silently_close_development") is True)
    check("no duplicate skills authority", honesty.get("no_duplicate_skills_authority") is True)

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup remounts Learning", "Wave6LearningPoliciesCard" in setup_app)
    check("Setup still remounts JA", "Wave6JobArchitecturePoliciesCard" in setup_app)
    check("Setup still remounts Talent", "Wave4TalentPoliciesCard" in setup_app)
    check("Setup still remounts Performance", "Wave4PerformancePoliciesCard" in setup_app)
    check("Setup still omits Benefits", "Wave6BenefitsPoliciesCard" not in setup_app)
    check("Setup still omits Comp Planning", "Wave6CompensationPlanningPoliciesCard" not in setup_app)
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire mounts Learning workspace", "LearningWorkspace" in posthire)
    workspace = (DASH / "posthire" / "LearningWorkspace.tsx").read_text(encoding="utf-8")
    check("workspace bilingual AR", "التعلم والتطوير" in workspace)
    check("workspace uses ResourceState", "ResourceState" in workspace and "resolveListDataState" in workspace)
    check("workspace names assignment boundary", "Assigned is not enrolled" in workspace or "الإسناد ليس تسجيلاً" in workspace)
    check("workspace overdue not fail", "automatic failure" in workspace or "رسوباً تلقائياً" in workspace)

    types = (DASH / "types.ts").read_text(encoding="utf-8")
    check("Page includes learning", "| 'learning'" in types)
    nav = (DASH / "lib" / "workspaceCapability.ts").read_text(encoding="utf-8")
    check("nav.learning registered", "nav.learning" in nav)
    check("nav.learning has module key", "module: 'learning'" in nav and "permission: 'learning.read'" in nav)
    catalog_src = (DASH / "lib" / "moduleWorkspace.ts").read_text(encoding="utf-8")
    check("learning is a canonical posthire SKU", "'learning'" in catalog_src.split("CANONICAL_POSTHIRE_MODULES")[1].split("]")[0])

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers Learning HTTP", "register_learning_http" in app_src)
    check("learning.read permission exists", "learning.read" in app_src)
    check("learning.manage permission exists", "learning.manage" in app_src)
    check("learning.assign permission exists", "learning.assign" in app_src)
    check("learning.approve permission exists", "learning.approve" in app_src)
    check("employee feature learning", 'module_keys": ("learning",)' in app_src.replace(" ", "") or 'module_keys": ("learning",)' in app_src)
    check("notification flow learning", '"learning": "learning"' in app_src.replace(" ", "") or '"learning": "learning"' in app_src)

    http_src = (ROOT / "learning_http.py").read_text(encoding="utf-8")
    for path in (
        "/dashboard/learning",
        "/app/learning",
        "/workspace",
        "/catalog",
        "/assignments",
        "/requests",
        "/sessions",
        "/completions",
        "/certificates",
        "/mandatory",
        "/development-links",
        "/programs",
        "/history",
    ):
        check(f"HTTP mentions {path}", path in http_src)
    check("HTTP never accepts client company authority as write", "X-Company-Code" not in http_src)
    check("HTTP uses dashboard_context", "dashboard_context" in http_src)
    check("HTTP uses employee_app_context", "employee_app_context" in http_src)
    check("HTTP refuses employee mandatory self-complete", "employee_self_completion_forbidden" in (ROOT / "learning_surfaces.py").read_text(encoding="utf-8"))

    emp_comp = (MOBILE / "src" / "composition" / "employeeAppComposition.ts").read_text(encoding="utf-8")
    check("employee composition has learning", "'learning'" in emp_comp)
    check("employee hub exists", (MOBILE / "app" / "learning" / "index.tsx").is_file())
    check("employee catalog exists", (MOBILE / "app" / "learning" / "catalog.tsx").is_file())
    check("employee certificates exist", (MOBILE / "app" / "learning" / "certificates.tsx").is_file())
    check("no HR mobile learning admin", not (MOBILE / "app" / "hr" / "learning").exists())
    en = (MOBILE / "src" / "i18n" / "en.json").read_text(encoding="utf-8")
    ar = (MOBILE / "src" / "i18n" / "ar.json").read_text(encoding="utf-8")
    check("employee EN copy", '"learning"' in en and "Required" in en)
    check("employee AR copy", "التعلم" in ar and "مطلوب" in ar)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    learning = client.get("/dashboard/learning/workspace")
    check(
        "fail-closed no longer steals Learning",
        not (
            learning.status_code == 404
            and isinstance(learning.json().get("detail"), dict)
            and learning.json()["detail"].get("error") == "capability_not_released"
        ),
        learning.json() if learning.headers.get("content-type", "").startswith("application/json") else learning.status_code,
    )
    benefits = client.get("/dashboard/benefits")
    benefits_detail = benefits.json().get("detail") if benefits.headers.get("content-type", "").startswith("application/json") else None
    check(
        "Benefits still fail-closed",
        benefits.status_code == 404
        and isinstance(benefits_detail, dict)
        and benefits_detail.get("error") == "capability_not_released",
        benefits_detail,
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5E_LEARNING_SURFACE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
