#!/usr/bin/env python3
"""Production Readiness R6 — Setup self-service unit contracts (no DB)."""
from __future__ import annotations

import os
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
    import setup_console_effective_state as eff
    import setup_console_env_classification as envc
    import setup_console_policy_convergence as conv
    import setup_console_wave5_policies as w5
    import setup_console_wave6_policies as w6
    import hr_intelligence_registry_c1 as c1

    print("    PRODUCTION READINESS R6 — setup self-service (unit)")

    check("R5A readiness contract preserved", ready.customer_enableable("workforce_planning") is True)
    check("performance still enableable", ready.customer_enableable("performance") is True)
    check("comp still enableable", ready.customer_enableable("comp_planning") is True)
    check("JA still enableable", ready.customer_enableable("job_architecture") is True)
    check("no unreleased capability keys", ready.UNRELEASED_CAPABILITY_KEYS == ())
    check("analytics remains catalog SKU", "analytics" in catalog.MODULE_BY_KEY)
    check("JA is not a catalog SKU", "job_architecture" not in catalog.MODULE_BY_KEY)
    check("JA marked platform in wave6", w6.DEFAULTS["job_architecture"].get("platform_capability") is True)
    check("JA not commercial SKU", w6.DEFAULTS["job_architecture"].get("commercial_sku") is False)
    check("WFP is commercial SKU", w6.DEFAULTS["workforce_planning"].get("commercial_sku") is True)

    disabled = eff.resolve_effective_state(
        "leave",
        {"policy": {"enabled": False}, "runtime_gate": {"ok": True}},
    )
    check("available but disabled", disabled["effective_state"] == "available_disabled")
    check("disabled not usable", disabled["usable"] is False)

    usable = eff.resolve_effective_state(
        "leave",
        {"policy": {"enabled": True}, "runtime_gate": {"ok": True}},
    )
    check("enabled and usable", usable["effective_state"] == "enabled_usable" and usable["usable"] is True)
    annotated = ready.annotate_policy_payload(
        "wave4_performance_goals",
        {"ok": True, "policy": {"enabled": True}},
    )
    check("R5A customer_facing_state still enabled when usable", annotated.get("customer_facing_state") == "enabled")
    check("R5A usable still true on happy path", annotated.get("usable") is True)
    gated_ann = ready.annotate_policy_payload(
        "wave4_performance_goals",
        {"ok": True, "policy": {"enabled": True}, "runtime_gate": {"ok": False, "error": "kill_switch"}},
    )
    check("R5A/R6 never Enabled when runtime blocked", gated_ann.get("customer_facing_state") != "enabled")

    blocked = eff.resolve_effective_state(
        "analytics",
        {"policy": {"enabled": True}, "runtime_gate": {"ok": False, "error": "analytics_kill_switch", "gate": "kill"}},
    )
    check("stored on + kill switch is not Enabled", blocked["effective_state"] == "unavailable_deployment")
    check("stored on + kill switch unusable", blocked["usable"] is False)
    check("kill switch copy hides env", "WATHEFNI" not in str(blocked["deployment"]))

    dep = eff.resolve_effective_state(
        "comp_planning",
        {"policy": {"enabled": False}, "runtime_gate": {"ok": False, "error": "ja_hard_dependency_unmet"}},
    )
    check("Comp without JA is dependency_unmet", dep["effective_state"] == "dependency_unmet")

    wfp = eff.resolve_effective_state(
        "workforce_planning",
        {"policy": {"enabled": False}, "runtime_gate": {"ok": False, "error": "ja_must_be_enabled"}},
    )
    check("WFP without JA is dependency_unmet", wfp["effective_state"] == "dependency_unmet")

    forbidden = eff.resolve_effective_state(
        "leave",
        {"policy": {"enabled": True}, "runtime_gate": {"ok": True}},
        principal_permitted=False,
    )
    check("ordinary HR is not_permitted", forbidden["effective_state"] == "not_permitted")

    matrix = envc.classification_matrix()
    check("env classification exists", matrix.get("ok") is True)
    check("secrets stay out of Setup", matrix.get("secrets_never_moved_to_setup") is True)
    classes = {item["key"]: item["class"] for item in matrix["entries"]}
    check("push flag is infrastructure", classes.get("WATHEFNI_PUSH_NOTIFICATIONS") == envc.CLASS_A)
    check("notification preset is customer policy", classes.get("notification_preset") == envc.CLASS_B)
    check("onboarding seed is infrastructure", classes.get("WATHEFNI_ONBOARDING_SEED") == envc.CLASS_A)
    check("legacy HTML preset is non-authoritative", classes.get("legacy HTML notification_preset (~app.py:42600)") == envc.CLASS_C)

    res = conv.resolution_matrix()
    check("leave canonical is leave_policies", res["resolutions"]["leave"]["canonical"] == "leave_policies")
    check("onboarding auto-start canonical", "onboarding.auto_start_on_hire" in res["resolutions"]["onboarding"]["canonical_auto_start"])
    check("duplicate stores resolved", res.get("duplicate_stores_removed_or_non_authoritative") is True)

    honesty = w5.honesty_payload()
    check("wave5 setup owns policy", honesty.get("setup_owns_wave5_policies") is True)
    check("wave5 no second analytics authority", honesty.get("no_new_analytics_authority") is True)
    check("wave5 uses frozen C1", honesty.get("uses_frozen_c1_evaluator") is True)

    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = "on"
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = ""
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    check("empty Intelligence allowlist admits after R6", c1.runtime_gate_for_company("R6UNIT") .get("ok") is True)
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = "OTHERCO"
    check("explicit allowlist still blocks", c1.runtime_gate_for_company("R6UNIT").get("ok") is not True)
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "on"
    check("kill switch still wins", c1.runtime_gate_for_company("OTHERCO").get("ok") is not True)
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = ""

    setup_app = (DASH / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup mounts Wave 5 Intelligence card", "Wave5HrIntelligencePoliciesCard" in setup_app)
    check("Setup mounts delivery card", "NotificationDeliveryPoliciesCard" in setup_app)
    check("Setup still remounts WFP", "Wave6WorkforcePlanningPoliciesCard" in setup_app)
    check("Setup still remounts Comp", "Wave6CompensationPlanningPoliciesCard" in setup_app)

    wave5_card = (DASH / "setup-console" / "Wave5HrIntelligencePoliciesCard.tsx").read_text(encoding="utf-8")
    check("Wave5 card bilingual AR", "ذكاء الموارد البشرية" in wave5_card)
    check("Wave5 card uses effective state", "SetupEffectiveStateBanner" in wave5_card)
    check("Wave5 failed save restores previous", "setPolicy(previous)" in wave5_card)

    comp_card = (DASH / "setup-console" / "Wave6CompensationPlanningPoliciesCard.tsx").read_text(encoding="utf-8")
    check("Comp card no longer lies Enabled+env gate", "Enabled for this company (env gate" not in comp_card)
    check("Comp card shows effective state", "SetupEffectiveStateBanner" in comp_card)
    check("Comp failed save reloads", "await reload()" in comp_card)

    wfp_card = (DASH / "setup-console" / "Wave6WorkforcePlanningPoliciesCard.tsx").read_text(encoding="utf-8")
    check("WFP card no longer lies Enabled+env gate", "Enabled for this company (env gate" not in wfp_card)
    check("WFP card shows effective state", "SetupEffectiveStateBanner" in wfp_card)

    ja_card = (DASH / "setup-console" / "Wave6JobArchitecturePoliciesCard.tsx").read_text(encoding="utf-8")
    check("JA card says not a commercial SKU", "Not a commercial SKU" in ja_card)
    for name in (
        "Wave6LearningPoliciesCard.tsx",
        "Wave6BenefitsPoliciesCard.tsx",
        "Wave6EmployeeRelationsPoliciesCard.tsx",
        "Wave6EngagementPoliciesCard.tsx",
        "Wave6JobArchitecturePoliciesCard.tsx",
    ):
        text = (DASH / "setup-console" / name).read_text(encoding="utf-8")
        check(f"{name} no Enabled+env-gate lie", "Enabled for this company (env gate" not in text)
        check(f"{name} shows effective state", "SetupEffectiveStateBanner" in text)

    app_src = (ROOT / "app.py").read_text(encoding="utf-8")
    check("module-policies includes wave5", "setup_console_wave5_policies" in app_src)
    check("company-scoped Setup routes exist", "/dashboard/setup/company/module-policies" in app_src)
    check("dependency enable is 409", "dependency_unmet" in app_src)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("R6_SETUP_SELF_SERVICE_UNIT_FAIL")
        return 1
    print("R6_SETUP_SELF_SERVICE_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
