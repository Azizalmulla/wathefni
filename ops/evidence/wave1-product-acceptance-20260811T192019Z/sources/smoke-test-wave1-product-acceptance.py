#!/usr/bin/env python3
"""Wave 1 Product Acceptance — unit wiring (no DB)."""
from __future__ import annotations

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
    print("    wave1 product acceptance — unit")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import setup_console_wave1_policies as w1p
    import wave1_task_sync as w1t

    check("setup wave1 policies module", callable(w1p.get_all_wave1_policies))
    check("setup patch requisitions", callable(w1p.patch_requisitions_company_policy))
    check("setup patch preboarding", callable(w1p.patch_preboarding_company_policy))
    check("setup patch probation", callable(w1p.patch_probation_company_policy))
    check("task sync requisition", callable(w1t.on_requisition_pending_approval))
    check("task sync probation", callable(w1t.on_probation_decision_required))
    check("task sync preboard remind", callable(w1t.on_preboard_remind))

    app = (orch / "app.py").read_text(encoding="utf-8")
    check("app merges wave1 policies", "setup_console_wave1_policies" in app and "onboarding_auto_start" in app)
    check("req http task sync", "wave1_task_sync" in (orch / "requisitions_http.py").read_text(encoding="utf-8"))
    check("probation remind task sync", "wave1_task_sync" in (orch / "probation_http.py").read_text(encoding="utf-8"))
    check("preboard remind task sync", "wave1_task_sync" in (orch / "preboarding_http.py").read_text(encoding="utf-8"))

    web = root / "apps" / "wathefni-dashboard" / "src"
    check("Setup Wave1 card", (web / "setup-console/Wave1HireReadyPoliciesCard.tsx").is_file())
    setup_app = (web / "setup-console/SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check("Setup wires Wave1 card", "Wave1HireReadyPoliciesCard" in setup_app)
    for name, path in (
        ("req banner fixed", web / "prehire/RequisitionsWorkspace.tsx"),
        ("preboard banner fixed", web / "posthire/PreboardingWorkspace.tsx"),
        ("probation banner fixed", web / "posthire/ProbationWorkspace.tsx"),
    ):
        txt = path.read_text(encoding="utf-8")
        check(name, "ConfigureInSetupBanner" in txt and "title=" in txt and "moduleKey=" not in txt)

    mobile = root / "apps" / "wathefni-employee-mobile"
    check("HR mobile requisitions", (mobile / "src/hr/features/requisitions/HRRequisitionsQueueView.tsx").is_file())
    check("HR mobile preboarding", (mobile / "src/hr/features/preboarding").is_dir() or (mobile / "app/hr/preboarding").is_dir())
    check("HR mobile probation", (mobile / "src/hr/features/probation/HRProbationQueueView.tsx").is_file())
    check("employee preboarding", (mobile / "app/preboarding.tsx").is_file())
    check("employee probation", (mobile / "app/probation.tsx").is_file())
    check("visual seed script", (orch / "ops-seed-wave1-visual-canary.py").is_file())
    check("product db smoke", (orch / "smoke-test-wave1-product-acceptance-db.py").is_file())

    # Lifecycle + surface freezes present
    for p in (
        "ops/WAVE1_LIFECYCLE_FULL_PASS.md",
        "ops/REQUISITIONS_SURFACE_WAVE_FREEZE.md",
        "ops/PREBOARDING_SURFACE_WAVE_FREEZE.md",
        "ops/PROBATION_SURFACE_WAVE_FREEZE.md",
        "ops/HIRE_READY_BRIDGE_FREEZE.md",
    ):
        check(f"freeze {Path(p).name}", (root / p).is_file())

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("WAVE1_PRODUCT_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
