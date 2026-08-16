#!/usr/bin/env python3
"""Production Readiness R5A — Capability Honesty unit contracts (no DB).

Proves: surface-less Wave 4/6 capabilities are not customer-enableable;
Setup omits their enable toggles; catalog SKUs stay enableable; Wave 5
Intelligence remains; reserved HTTP namespaces fail closed without calling
domain libraries.
"""
from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DASH = REPO / "apps" / "wathefni-dashboard" / "src"

UNRELEASED = (
    "workforce_planning",
)

WAVE6_HIDDEN_CARDS = (
    "Wave6WorkforcePlanningPoliciesCard",
)


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
    import unreleased_capability_http as http_mod

    print("    PRODUCTION READINESS R5A — capability honesty (unit)")

    print("\n    readiness contract")
    check("one unreleased capability after R5I", len(ready.UNRELEASED_CAPABILITY_KEYS) == 1)
    check("unreleased tuple matches", tuple(ready.UNRELEASED_CAPABILITY_KEYS) == UNRELEASED)
    check("performance left unreleased set", "performance" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("talent left unreleased set", "talent" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("job architecture left unreleased set", "job_architecture" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("learning left unreleased set", "learning" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("benefits left unreleased set", "benefits" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("employee relations left unreleased set", "employee_relations" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("engagement left unreleased set", "engagement" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("comp planning left unreleased set", "comp_planning" not in ready.UNRELEASED_CAPABILITY_KEYS)
    check("performance customer enableable", ready.customer_enableable("performance") is True)
    check("talent customer enableable", ready.customer_enableable("talent") is True)
    check("job architecture customer enableable", ready.customer_enableable("job_architecture") is True)
    check("learning customer enableable", ready.customer_enableable("learning") is True)
    check("benefits customer enableable", ready.customer_enableable("benefits") is True)
    check("employee relations customer enableable", ready.customer_enableable("employee_relations") is True)
    check("engagement customer enableable", ready.customer_enableable("engagement") is True)
    check("comp planning customer enableable", ready.customer_enableable("comp_planning") is True)
    check("engagement is a catalog SKU", "engagement" in catalog.MODULE_BY_KEY)
    check("comp planning is a catalog SKU", "comp_planning" in catalog.MODULE_BY_KEY)
    check("learning is a catalog SKU", "learning" in catalog.MODULE_BY_KEY)
    check("benefits is a catalog SKU", "benefits" in catalog.MODULE_BY_KEY)
    check("employee relations is a catalog SKU", "employee_relations" in catalog.MODULE_BY_KEY)
    bn_ready = ready.readiness_payload("benefits")
    check("benefits http_ready", bn_ready.get("http_ready") is True)
    check("benefits hr_web_ready", bn_ready.get("hr_web_ready") is True)
    check("benefits employee surface ready", bn_ready.get("employee_surface_ready") is True)
    check("benefits manager surface not required", bn_ready.get("manager_surface_required") is False)
    check("benefits mobile not required", bn_ready.get("mobile_required") is False)
    er_ready = ready.readiness_payload("employee_relations")
    check("employee relations http_ready", er_ready.get("http_ready") is True)
    check("employee relations hr_web_ready", er_ready.get("hr_web_ready") is True)
    check("employee relations mobile ready", er_ready.get("mobile_ready") is True)
    check("employee relations employee surface not required", er_ready.get("employee_surface_required") is False)
    check("employee relations manager surface not required", er_ready.get("manager_surface_required") is False)
    check("employee relations people_surface off", catalog.MODULE_BY_KEY["employee_relations"].people_surface is False)
    eg_ready = ready.readiness_payload("engagement")
    check("engagement http_ready", eg_ready.get("http_ready") is True)
    check("engagement hr_web_ready", eg_ready.get("hr_web_ready") is True)
    check("engagement employee surface ready", eg_ready.get("employee_surface_ready") is True)
    check("engagement manager surface ready", eg_ready.get("manager_surface_ready") is True)
    check("engagement mobile not required", eg_ready.get("mobile_required") is False)
    check("engagement people_surface off", catalog.MODULE_BY_KEY["engagement"].people_surface is False)
    cp_ready = ready.readiness_payload("comp_planning")
    check("comp planning http_ready", cp_ready.get("http_ready") is True)
    check("comp planning hr_web_ready", cp_ready.get("hr_web_ready") is True)
    check("comp planning employee surface not required", cp_ready.get("employee_surface_required") is False)
    check("comp planning mobile not required", cp_ready.get("mobile_required") is False)
    check("comp planning people_surface off", catalog.MODULE_BY_KEY["comp_planning"].people_surface is False)
    check("comp planning depends on JA", "job_architecture" in (cp_ready.get("depends_on") or ()))
    check("job architecture is not a catalog SKU", "job_architecture" not in catalog.MODULE_BY_KEY)
    ja_ready = ready.readiness_payload("job_architecture")
    check("job architecture http_ready", ja_ready.get("http_ready") is True)
    check("job architecture hr_web_ready", ja_ready.get("hr_web_ready") is True)
    check("job architecture employee surface not required", ja_ready.get("employee_surface_required") is False)
    check("job architecture manager surface not required", ja_ready.get("manager_surface_required") is False)
    alignment = ready.assert_catalog_alignment()
    check("unreleased keys absent from catalog", alignment["ok"] is True, alignment)
    check("analytics remains a catalog SKU", "analytics" in catalog.MODULE_BY_KEY)
    check("leave remains a catalog SKU", "leave" in catalog.MODULE_BY_KEY)
    check("onboarding remains a catalog SKU", "onboarding" in catalog.MODULE_BY_KEY)
    check("employee_app remains a catalog SKU", "employee_app" in catalog.MODULE_BY_KEY)
    for key in ("leave", "attendance", "payroll", "analytics", "requisitions", "preboarding"):
        check(f"catalog {key} customer enableable", ready.catalog_module_customer_enableable(key) is True)

    for key in UNRELEASED:
        payload = ready.readiness_payload(key)
        check(f"{key} domain_authority_ready", payload.get("domain_authority_ready") is True)
        check(f"{key} http_ready false", payload.get("http_ready") is False)
        check(f"{key} hr_web_ready false", payload.get("hr_web_ready") is False)
        check(f"{key} customer_enableable false", payload.get("customer_enableable") is False)
        check(f"{key} customer_visible false", payload.get("customer_visible") is False)
        check(
            f"{key} domain pass is not enableable",
            payload.get("domain_full_pass_is_not_customer_enableable") is True,
        )
        check(
            f"{key} stored enabled is not usable",
            ready.customer_usable(capability_key=key, stored_enabled=True, runtime_available=True) is False,
        )
        blocked = ready.customer_setup_write_block(key)
        check(f"{key} setup write blocked", (blocked or {}).get("error") == "capability_not_customer_enableable")
        check(f"{key} write preserves rows", (blocked or {}).get("preserved") is True)

    check("wave4 performance write unblocked", ready.customer_setup_write_block("wave4_performance_goals") is None)
    check("wave4 talent write unblocked", ready.customer_setup_write_block("wave4_talent_profile") is None)
    check("wave6 job architecture write unblocked", ready.customer_setup_write_block("wave6_job_architecture") is None)
    check("wave6 learning write unblocked", ready.customer_setup_write_block("wave6_learning") is None)
    check("wave6 benefits write unblocked", ready.customer_setup_write_block("wave6_benefits") is None)
    check("wave6 employee relations write unblocked", ready.customer_setup_write_block("wave6_employee_relations") is None)
    check("wave6 engagement write unblocked", ready.customer_setup_write_block("wave6_engagement") is None)
    check("wave6 comp planning write unblocked", ready.customer_setup_write_block("wave6_comp_planning") is None)
    for setup_key in (
        "wave6_workforce_planning",
    ):
        check(
            f"HTTP block {setup_key}",
            (ready.customer_setup_write_block(setup_key) or {}).get("error") == "capability_not_customer_enableable",
        )

    annotated = ready.annotate_policy_payload(
        "wave4_performance_goals",
        {"ok": True, "policy": {"enabled": True}},
    )
    check("stored_enabled preserved on GET", annotated.get("stored_enabled") is True)
    check("usable true when performance released and stored enabled", annotated.get("usable") is True)
    check("customer_facing_state enabled", annotated.get("customer_facing_state") == "enabled")

    check("leave is not an unreleased capability", ready.is_unreleased_capability_key("leave") is False)
    check("wave1 write not blocked", ready.customer_setup_write_block("leave") is None)
    check("wave2 write not blocked", ready.customer_setup_write_block("wave2_payroll") is None)
    check("wave3 write not blocked", ready.customer_setup_write_block("wave3_exit") is None)

    catalog_block = ready.unreleased_catalog_enable_block("performance")
    check("catalog enable performance unblocked", catalog_block is None)
    check("catalog enable talent unblocked", ready.unreleased_catalog_enable_block("talent") is None)
    check("catalog enable learning unblocked", ready.unreleased_catalog_enable_block("learning") is None)
    check("catalog enable benefits unblocked", ready.unreleased_catalog_enable_block("benefits") is None)
    check("catalog enable employee relations unblocked", ready.unreleased_catalog_enable_block("employee_relations") is None)
    check("catalog enable engagement unblocked", ready.unreleased_catalog_enable_block("engagement") is None)
    check("catalog enable comp planning unblocked", ready.unreleased_catalog_enable_block("comp_planning") is None)
    check("catalog enable leave not blocked", ready.unreleased_catalog_enable_block("leave") is None)
    check("catalog enable analytics not blocked", ready.unreleased_catalog_enable_block("analytics") is None)

    print("\n    Setup UX omission")
    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Wave1 card still mounted", "Wave1HireReadyPoliciesCard" in setup_app)
    check("Wave2 card still mounted", "Wave2WorkforceTruthPoliciesCard" in setup_app)
    check("Wave3 card still mounted", "Wave3EmployeeLifecyclePoliciesCard" in setup_app)
    check("Wave4 Performance card remounted", "Wave4PerformancePoliciesCard" in setup_app)
    check("Wave4 Talent card remounted", "Wave4TalentPoliciesCard" in setup_app)
    check(
        "Wave4 card file retained",
        (DASH / "setup-console" / "Wave4PerformanceTalentPoliciesCard.tsx").is_file(),
    )
    check("Wave6 Job Architecture card remounted", "Wave6JobArchitecturePoliciesCard" in setup_app)
    check(
        "Wave6 Job Architecture card file retained",
        (DASH / "setup-console" / "Wave6JobArchitecturePoliciesCard.tsx").is_file(),
    )
    for name in WAVE6_HIDDEN_CARDS:
        check(f"{name} omitted from Setup", name not in setup_app)
        check(f"{name} file retained", (DASH / "setup-console" / f"{name}.tsx").is_file())
    check("classic-wave4-performance mounted", "classic-wave4-performance" in setup_app or "Wave4PerformancePoliciesCard" in setup_app)
    check("classic-wave6-job-architecture mounted", "classic-wave6-job-architecture" in setup_app or "Wave6JobArchitecturePoliciesCard" in setup_app)
    check("Wave6 Learning card remounted", "Wave6LearningPoliciesCard" in setup_app)
    check("classic-wave6-learning mounted", "classic-wave6-learning" in setup_app or "Wave6LearningPoliciesCard" in setup_app)
    check("Wave6 Benefits card remounted", "Wave6BenefitsPoliciesCard" in setup_app)
    check("classic-wave6-benefits mounted", "classic-wave6-benefits" in setup_app or "Wave6BenefitsPoliciesCard" in setup_app)
    check("Wave6 Employee Relations card remounted", "Wave6EmployeeRelationsPoliciesCard" in setup_app)
    check("classic-wave6-employee-relations mounted", "classic-wave6-employee-relations" in setup_app or "Wave6EmployeeRelationsPoliciesCard" in setup_app)
    check("Wave6 Engagement card remounted", "Wave6EngagementPoliciesCard" in setup_app)
    check("classic-wave6-engagement mounted", "classic-wave6-engagement" in setup_app or "Wave6EngagementPoliciesCard" in setup_app)
    check("Wave6 Compensation Planning card remounted", "Wave6CompensationPlanningPoliciesCard" in setup_app)
    check("classic-wave6-comp-planning mounted", "classic-wave6-comp-planning" in setup_app or "Wave6CompensationPlanningPoliciesCard" in setup_app)
    check(
        "Wave6 Engagement card file retained",
        (DASH / "setup-console" / "Wave6EngagementPoliciesCard.tsx").is_file(),
    )
    check(
        "Wave6 Employee Relations card file retained",
        (DASH / "setup-console" / "Wave6EmployeeRelationsPoliciesCard.tsx").is_file(),
    )
    check(
        "Wave6 Benefits card file retained",
        (DASH / "setup-console" / "Wave6BenefitsPoliciesCard.tsx").is_file(),
    )
    check(
        "Wave6 Compensation Planning card file retained",
        (DASH / "setup-console" / "Wave6CompensationPlanningPoliciesCard.tsx").is_file(),
    )

    intel = DASH / "posthire" / "intelligence" / "IntelligenceWorkspace.tsx"
    check("Wave 5 Intelligence workspace present", intel.is_file())
    intel_text = intel.read_text(encoding="utf-8") if intel.is_file() else ""
    check("Intelligence workspace still a real surface", "IntelligenceWorkspace" in intel_text or "semantic" in intel_text.lower() or "evaluate" in intel_text.lower())
    posthire = (DASH / "posthire" / "PostHire.tsx").read_text(encoding="utf-8")
    check("PostHire still mounts Intelligence", "IntelligenceWorkspace" in posthire)

    print("\n    fail-closed HTTP")
    http_src = (ROOT / "unreleased_capability_http.py").read_text(encoding="utf-8")
    for needle in (
        "performance_goals_c1",
        "talent_profile_c5",
        "job_architecture_c1",
        "learning_development_c2",
        "benefits_administration_c3",
        "employee_relations_c4",
        "engagement_c5",
        "compensation_planning_c6",
        "workforce_planning_c7",
    ):
        check(f"fail-closed HTTP does not import {needle}", needle not in http_src)
    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("app registers fail-closed namespaces", "register_unreleased_capability_failclosed" in app_src)
    check("app blocks unreleased Setup writes", "customer_setup_write_block" in app_src)
    check("app annotates wave4/wave6 GET", "annotate_wave4_setup" in app_src and "annotate_wave6_setup" in app_src)

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    mini = FastAPI()

    class _Box:
        app = mini

    http_mod.register_unreleased_capability_failclosed(_Box)
    client = TestClient(mini)
    for cap, path in (
        ("workforce_planning", "/dashboard/workforce-planning/plans"),
    ):
        response = client.get(path)
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        check(f"GET {path} is 404", response.status_code == 404, response.status_code)
        check(
            f"GET {path} capability_not_released",
            isinstance(detail, dict) and detail.get("error") == "capability_not_released",
            detail,
        )
        check(
            f"GET {path} names {cap}",
            isinstance(detail, dict) and detail.get("capability_key") == cap,
            detail,
        )
        posted = client.post(path, json={"enabled": True})
        posted_detail = posted.json().get("detail") if posted.headers.get("content-type", "").startswith("application/json") else None
        check(f"POST {path} is 404", posted.status_code == 404, posted.status_code)
        check(
            f"POST {path} not released",
            isinstance(posted_detail, dict) and posted_detail.get("error") == "capability_not_released",
            posted_detail,
        )

    benefits_hit = client.get("/dashboard/benefits")
    check(
        "fail-closed does not steal Benefits namespace",
        not (
            benefits_hit.status_code == 404
            and isinstance(benefits_hit.json().get("detail"), dict)
            and benefits_hit.json()["detail"].get("error") == "capability_not_released"
        ),
        benefits_hit.json() if benefits_hit.headers.get("content-type", "").startswith("application/json") else benefits_hit.status_code,
    )
    er_hit = client.get("/dashboard/employee-relations")
    check(
        "fail-closed does not steal Employee Relations namespace",
        not (
            er_hit.status_code == 404
            and isinstance(er_hit.json().get("detail"), dict)
            and er_hit.json()["detail"].get("error") == "capability_not_released"
        ),
        er_hit.json() if er_hit.headers.get("content-type", "").startswith("application/json") else er_hit.status_code,
    )
    eg_hit = client.get("/dashboard/engagement")
    check(
        "fail-closed does not steal Engagement namespace",
        not (
            eg_hit.status_code == 404
            and isinstance(eg_hit.json().get("detail"), dict)
            and eg_hit.json()["detail"].get("error") == "capability_not_released"
        ),
        eg_hit.json() if eg_hit.headers.get("content-type", "").startswith("application/json") else eg_hit.status_code,
    )
    cp_hit = client.get("/dashboard/compensation-planning")
    check(
        "fail-closed does not steal Compensation Planning namespace",
        not (
            cp_hit.status_code == 404
            and isinstance(cp_hit.json().get("detail"), dict)
            and cp_hit.json()["detail"].get("error") == "capability_not_released"
        ),
        cp_hit.json() if cp_hit.headers.get("content-type", "").startswith("application/json") else cp_hit.status_code,
    )

    intel_path = "/dashboard/posthire/intelligence/bootstrap"
    intel_hit = client.get(intel_path)
    check(
        "fail-closed does not steal Intelligence namespace",
        intel_hit.status_code == 404
        and not (
            isinstance(intel_hit.json().get("detail"), dict)
            and intel_hit.json()["detail"].get("capability_key") in UNRELEASED
        ),
        intel_hit.json(),
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5A_CAPABILITY_HONESTY_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
