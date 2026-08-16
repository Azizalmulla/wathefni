#!/usr/bin/env python3
"""Wave 2 Product Acceptance — unit wiring (no DB)."""
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
    print("    wave2 product acceptance — unit")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import setup_console_wave2_policies as w2p
    import attendance_truth_c1 as c1
    import leave_enforcement_c2 as c2
    import shifts_mss_c3 as c3
    import payroll_authoritative_c4 as c4
    import payroll_payslip_payment_c5 as c5
    import payroll_settlement_ot_c6 as c6

    check("setup wave2 policies module", callable(w2p.get_all_wave2_policies))
    check("setup patch wave2", callable(w2p.patch_wave2_module_policy))
    check("modularity matrix configs", len(w2p.modularity_matrix_configs()) >= 8)
    check("setup owns wave2", w2p.honesty_payload().get("setup_owns_wave2_policies") is True)
    check("not env-only ownership", w2p.honesty_payload().get("env_only_ownership") is False)
    check("EN attendance label", w2p.status_label("attendance", lang="en"))
    check("AR payroll label", "رواتب" in w2p.status_label("payroll", lang="ar"))

    # Global off fail-closed
    os.environ["WATHEFNI_ATTENDANCE_CAPTURE_INGEST"] = "off"
    os.environ["WATHEFNI_ATTENDANCE_TRUTH_C1"] = "off"
    os.environ["WATHEFNI_LEAVE_ENFORCEMENT"] = "off"
    os.environ["WATHEFNI_SHIFTS_MSS_C3"] = "off"
    os.environ["WATHEFNI_PAYROLL_AUTHORITATIVE_C4"] = "off"
    os.environ["WATHEFNI_PAYROLL_PAYMENT_C5"] = "off"
    os.environ["WATHEFNI_PAYROLL_SETTLEMENT_C6"] = "off"
    check("C1 module-off", c1.capture_ingest_enabled_for_company("WATHEFNI").get("ok") is not True)
    check("C2 module-off", c2.leave_enforcement_enabled_for_company(None, "WATHEFNI").get("ok") is not True)
    check("C3 module-off", c3.mss_enabled_for_company("WATHEFNI").get("ok") is not True)
    check("C4 module-off", c4.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C5 module-off", c5.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C6 module-off", c6.runtime_gate_for_company("WATHEFNI").get("ok") is not True)

    check("C5 ack ≠ paid", c5.honesty_payload().get("acknowledged_is_not_paid") is True)
    check("C6 settlement ≠ paid", c6.honesty_payload().get("settlement_finalized_is_not_paid") is True)
    check("C6 settlement ≠ clearance", c6.honesty_payload().get("settlement_is_not_clearance") is True)
    check("C4 payroll independent", c4.honesty_payload().get("attendance_required") is False)

    import platform_assistant_spine_wave1 as spine

    # Wave 2 locked: Assistant mutations OUT — explicit off + wave spine deny path
    os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "off"
    check("assistant mutations explicit off", spine.assistant_mutations_allowed() is False)
    os.environ.pop("WATHEFNI_ASSISTANT_MUTATIONS", None)
    os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE1"] = "on"
    check("assistant mutations denied when spine wave on", spine.assistant_mutations_allowed() is False)
    os.environ.pop("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", None)

    app = (orch / "app.py").read_text(encoding="utf-8")
    check("app merges wave2 policies", "setup_console_wave2_policies" in app and '"wave2"' in app)

    web = root / "apps" / "wathefni-dashboard" / "src"
    check("Setup Wave2 card", (web / "setup-console/Wave2WorkforceTruthPoliciesCard.tsx").is_file())
    setup_app = (web / "setup-console/SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup wires Wave2 card", "Wave2WorkforceTruthPoliciesCard" in setup_app)
    check("Setup ModuleCompanyPoliciesCard", "ModuleCompanyPoliciesCard" in setup_app)
    check("Setup PayrollSetupCard", "PayrollSetupCard" in setup_app)

    # Channel convergence surfaces (HR Web / HR Mobile / Employee / Manager)
    mobile = root / "apps" / "wathefni-employee-mobile"
    for label, path in (
        ("HR web leave workspace", web / "posthire/LeaveWorkspace.tsx"),
        ("HR web setup console", web / "setup-console/SetupConsoleApp.tsx"),
        ("employee mobile app", mobile / "app"),
        ("HR mobile features", mobile / "src/hr"),
        ("manager/HR mobile present", (mobile / "src/hr").is_dir() or (mobile / "app/hr").exists()),
    ):
        check(label, path.exists() if hasattr(path, "exists") else bool(path), path)

    # EN/AR/RTL markers
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

    # Queue / customer-scale honesty — Setup + task surfaces exist
    check(
        "queue/customer-scale honesty surfaces",
        (web / "setup-console").is_dir()
        and ("hr_tasks" in app or (orch / "wave1_task_sync.py").is_file()),
    )

    # Freeze docs C1–C6 + Wave1
    for p in (
        "ops/ATTENDANCE_TRUTH_FULL_PASS.md",
        "ops/LEAVE_ENFORCEMENT_FULL_PASS.md",
        "ops/SHIFTS_MSS_FULL_PASS.md",
        "ops/PAYROLL_AUTHORITY_FULL_PASS.md",
        "ops/PAYSLIP_PAYMENT_FULL_PASS.md",
        "ops/SETTLEMENT_OT_FULL_PASS.md",
        "ops/WAVE1_PRODUCT_FULL_PASS.md",
        "ops/WAVE1_PRODUCT_FREEZE.md",
        "ops/WATHEFNI_HCM_WAVE2_WORKFORCE_TRUTH_BUILD_CHARTER.md",
    ):
        check(f"freeze/stamp {Path(p).name}", (root / p).is_file())

    check("product db smoke present", (orch / "smoke-test-wave2-product-acceptance-db.py").is_file())
    for smoke in (
        "smoke-test-attendance-truth-c1.py",
        "smoke-test-leave-enforcement-c2.py",
        "smoke-test-shifts-mss-c3.py",
        "smoke-test-payroll-authoritative-c4.py",
        "smoke-test-payroll-payslip-payment-c5.py",
        "smoke-test-payroll-settlement-ot-c6.py",
    ):
        check(f"regression smoke {smoke}", (orch / smoke).is_file())

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("WAVE2_PRODUCT_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
