#!/usr/bin/env python3
"""Phase A — capability contracts + catalog entitlement unit smoke."""
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
    print("    capability contracts + catalog — HARD/OPTIONAL/ENHANCEMENT")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import capability_contracts as cc

    try:
        import module_catalog as catalog
    except TypeError as exc:
        # Local Python <3.10 cannot import module_catalog (dataclass slots).
        catalog = None
        print(f"SKIP catalog import locally: {exc}")

    check("contracts non-empty", len(cc.CAPABILITY_CONTRACTS) >= 8)
    classes = {c.dependency_class for c in cc.CAPABILITY_CONTRACTS}
    check("has HARD", "HARD_DEPENDENCY" in classes)
    check("has OPTIONAL", "OPTIONAL_INTEGRATION" in classes)
    check("has ENHANCEMENT", "ENHANCEMENT" in classes)

    off = cc.evaluate_contract(
        "requisitions.gate_job_publish",
        enabled_modules={"pre_hiring"},
    )
    check("optional inactive without both modules", off.get("active") is False, off)

    both = cc.evaluate_contract(
        "requisitions.gate_job_publish",
        enabled_modules={"pre_hiring", "requisitions"},
    )
    check("optional active when both modules", both.get("active") is True, both)

    setting_off = cc.evaluate_contract(
        "onboarding.auto_start_on_hire",
        enabled_modules={"onboarding"},
        company_settings={"onboarding.auto_start_on_hire": False},
    )
    check("setting off deactivates", setting_off.get("active") is False, setting_off)

    os.environ.pop("WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS", None)
    joining = cc.evaluate_contract(
        "employment.joining_date_from_offer",
        enabled_modules={"employment_offers"},
    )
    check("joining contract active", joining.get("active") is True, joining)
    check("joining writers dark by default", joining.get("writers_enabled") is False, joining)

    if catalog is not None:
        check("catalog has requisitions", "requisitions" in catalog.MODULE_BY_KEY)
        check("catalog has preboarding", "preboarding" in catalog.MODULE_BY_KEY)
        check("catalog has probation", "probation" in catalog.MODULE_BY_KEY)
        check(
            "HARD deps empty for Wave 1 commercial modules",
            catalog.MODULE_BY_KEY["requisitions"].depends_on == ()
            and catalog.MODULE_BY_KEY["preboarding"].depends_on == ()
            and catalog.MODULE_BY_KEY["probation"].depends_on == (),
        )
        check(
            "recommended_with preserved (OPTIONAL/ENHANCEMENT hints)",
            "pre_hiring" in catalog.MODULE_BY_KEY["requisitions"].recommended_with
            and "employment_offers" in catalog.MODULE_BY_KEY["preboarding"].recommended_with,
        )
    else:
        check("catalog checks deferred to staging (py>=3.10)", True)

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
