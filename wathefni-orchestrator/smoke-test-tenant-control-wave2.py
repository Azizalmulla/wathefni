"""Wave 2 tenant control unit smokes (no DB required)."""

from __future__ import annotations

import sys
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    tenant control wave2 — decision contract, kill switches, lifecycle guards")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import tenant_control_decision as decision
    import tenant_control_lifecycle as lifecycle
    import tenant_control_roles as roles

    check("decision defaults on", decision.decision_enabled({}) is True)
    check("global authoritative hard-off", decision.global_authoritative_enabled({"WATHEFNI_TENANT_CONTROL_AUTHORITATIVE": "on"}) is False)
    check("plane kill switch", decision.plane_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "off"}) is False)
    check("decision kill switch", decision.decision_enabled({"WATHEFNI_TENANT_CONTROL_DECISION": "off"}) is False)
    check("lifecycle kill switch", decision.lifecycle_enforce_enabled({"WATHEFNI_TENANT_CONTROL_LIFECYCLE_ENFORCE": "off"}) is False)
    check("epoch kill switch", decision.epoch_enforce_enabled({"WATHEFNI_TENANT_CONTROL_EPOCH_ENFORCE": "off"}) is False)

    bypass = decision.evaluate_decision(
        None,
        company_code="WATHEFNI",
        surface="apis",
        module_key="analytics",
        legacy_allow=True,
        persist=False,
        environ={"WATHEFNI_TENANT_CONTROL_DECISION": "off"},
    )
    check("decision off bypasses to legacy", bypass.mode == "bypass" and bypass.allow is True)

    impact = lifecycle.preview_module_pause("analytics")
    check("pause impact includes navigation/apis", impact["ui"] and impact["apis"])
    import os as _os
    _os.environ["WATHEFNI_TENANT_CONTROL_ALLOW_WATHEFNI_SUSPEND"] = "tok"
    check("WATHEFNI suspend blocked without token", lifecycle.wathefni_suspend_allowed(None) is False)
    check("WATHEFNI suspend allowed with matching token", lifecycle.wathefni_suspend_allowed("tok") is True)
    _os.environ.pop("WATHEFNI_TENANT_CONTROL_ALLOW_WATHEFNI_SUSPEND", None)

    warnings = roles.sod_warnings(["payroll.approve", "payroll.export"])
    check("SoD warning emitted for conflicting perms", any("separation_of_duties" in w for w in warnings))
    check("owner legacy perms include wildcard", "*" in roles.legacy_permissions_for_role("owner"))

    result = decision.DecisionResult(
        allow=False,
        reason_code="module_paused",
        tenant="WATHEFNI",
        module="analytics",
        capability="mod.analytics",
        configuration_version=1,
        activation_epoch=2,
        remediation="Resume module.",
        mode="authoritative",
        surface="apis",
    )
    payload = result.as_dict()
    check("decision contract has required fields", all(
        k in payload for k in (
            "allow", "reason_code", "tenant", "module", "capability",
            "configuration_version", "activation_epoch", "remediation", "audit_correlation_id",
        )
    ))

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
