#!/usr/bin/env python3
"""Wave 3 Product Acceptance — unit wiring (no DB)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0


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
    print("    wave3 product acceptance — unit")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import setup_console_wave3_policies as w3p
    import employment_change_c1 as c1
    import ess_letters_dependents_c2 as c2
    import exit_intent_c3 as c3
    import offboarding_c4 as c4
    import exit_close_c5 as c5

    check("setup wave3 policies module", callable(w3p.get_all_wave3_policies))
    check("setup patch wave3", callable(w3p.patch_wave3_module_policy))
    check("modularity matrix configs", len(w3p.modularity_matrix_configs()) >= 8)
    check("setup owns wave3", w3p.honesty_payload().get("setup_owns_wave3_policies") is True)
    check("not env-only ownership", w3p.honesty_payload().get("env_only_ownership") is False)
    check("EN employment_change label", w3p.status_label("employment_change", lang="en"))
    check("AR offboarding label", "مخالصة" in w3p.status_label("offboarding", lang="ar") or "إنهاء" in w3p.status_label("offboarding", lang="ar"))
    check("sole left authority declared", w3p.honesty_payload().get("sole_employment_left_authority") == "exit_close")

    for flag in (
        "WATHEFNI_EMPLOYMENT_CHANGE_C1",
        "WATHEFNI_ESS_LETTERS_DEPENDENTS_C2",
        "WATHEFNI_RESIGNATION_ESS_C3",
        "WATHEFNI_OFFBOARDING_C4",
        "WATHEFNI_EXIT_CLOSE_C5",
        "WATHEFNI_REAL_TERMINATION_CANARY",
    ):
        os.environ[flag] = "off"
    for companies in (
        "WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES",
        "WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES",
        "WATHEFNI_RESIGNATION_ESS_COMPANIES",
        "WATHEFNI_OFFBOARDING_COMPANIES",
        "WATHEFNI_EXIT_CLOSE_COMPANIES",
    ):
        os.environ[companies] = ""

    check("C1 module-off", c1.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C2 module-off", c2.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C3 module-off", c3.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C4 module-off", c4.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C5 module-off", c5.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("real termination dark", c3.real_termination_canary_on() is False)
    check("C3 assert dark", c3.assert_real_termination_dark().get("ok") is True)
    check("C5 sole left", c5.honesty_payload().get("sole_employment_left_authority") is True)
    check("C5 finalized ≠ paid", c5.honesty_payload().get("settlement_finalized_is_not_paid") is True)
    check("C4 completion ≠ left", c4.honesty_payload().get("employment_left_on_complete") is False)

    import platform_assistant_spine_wave1 as spine

    os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "off"
    check("assistant mutations explicit off", spine.assistant_mutations_allowed() is False)
    os.environ.pop("WATHEFNI_ASSISTANT_MUTATIONS", None)
    os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE1"] = "on"
    check("assistant mutations denied when spine wave on", spine.assistant_mutations_allowed() is False)
    os.environ.pop("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", None)

    app = (orch / "app.py").read_text(encoding="utf-8")
    check("app merges wave3 policies", "setup_console_wave3_policies" in app and '"wave3"' in app)

    web = root / "apps" / "wathefni-dashboard" / "src"
    check("Setup Wave3 card", (web / "setup-console/Wave3EmployeeLifecyclePoliciesCard.tsx").is_file())
    setup_app = (web / "setup-console/SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup wires Wave3 card", "Wave3EmployeeLifecyclePoliciesCard" in setup_app)

    mobile = root / "apps" / "wathefni-employee-mobile"
    for label, path in (
        ("HR web setup console", web / "setup-console/SetupConsoleApp.tsx"),
        ("employee mobile app", mobile / "app"),
        ("HR mobile features", mobile / "src/hr"),
        ("manager/HR mobile present", (mobile / "src/hr").is_dir() or (mobile / "app/hr").exists()),
    ):
        check(label, path.exists() if hasattr(path, "exists") else bool(path), path)

    rtl_hits = 0
    for p in mobile.rglob("*.tsx"):
        try:
            t = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "rtl" in t.lower() or "I18nManager" in t or "dir=" in t:
            rtl_hits += 1
            if rtl_hits >= 3:
                break
    check("EN/AR/RTL surface markers", rtl_hits >= 1, rtl_hits)

    for p in (
        "ops/EMPLOYMENT_CHANGE_FULL_PASS.md",
        "ops/ESS_LETTERS_DEPENDENTS_FULL_PASS.md",
        "ops/RESIGNATION_TERMINATION_FULL_PASS.md",
        "ops/OFFBOARDING_FULL_PASS.md",
        "ops/EXIT_CLOSE_HANDOFF_FULL_PASS.md",
        "ops/WAVE1_PRODUCT_FULL_PASS.md",
        "ops/WAVE2_PRODUCT_FULL_PASS.md",
        "ops/WATHEFNI_HCM_WAVE3_EMPLOYEE_LIFECYCLE_BUILD_CHARTER.md",
    ):
        check(f"freeze/stamp {Path(p).name}", (root / p).is_file())

    check("product db smoke present", (orch / "smoke-test-wave3-product-acceptance-db.py").is_file())
    for smoke in (
        "smoke-test-employment-change-c1.py",
        "smoke-test-ess-letters-dependents-c2.py",
        "smoke-test-exit-intent-c3.py",
        "smoke-test-offboarding-c4.py",
        "smoke-test-exit-close-c5.py",
    ):
        check(f"regression smoke {smoke}", (orch / smoke).is_file())

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("WAVE3_PRODUCT_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
