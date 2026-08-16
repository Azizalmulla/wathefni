"""Wave 1 tenant control-plane foundation smoke tests (no production DB required)."""

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
    print("    tenant control wave1 — catalog, protection, shadow, kill switches")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))

    import module_catalog as modules
    import tenant_control_catalog as catalog
    import tenant_control_service as service

    payload = catalog.catalog_payload()
    check("catalog version pinned", payload["catalog_version"] == "tenant-control-catalog-v1")
    check("candidates product area exists", "candidates" in catalog.PRODUCT_AREA_BY_KEY)
    check("CK is backend under candidates", (
        catalog.CAPABILITY_BY_KEY["cap.candidate_knowledge"].product_area == "candidates"
        and catalog.CAPABILITY_BY_KEY["cap.candidate_knowledge"].hr_visible is False
        and catalog.CAPABILITY_BY_KEY["cap.candidate_knowledge"].commercial is False
    ))
    check("talent pool is backend under candidates", (
        catalog.CAPABILITY_BY_KEY["cap.talent_pool"].product_area == "candidates"
        and catalog.CAPABILITY_BY_KEY["cap.talent_pool"].hr_visible is False
    ))
    check("interviews and video_interviews are distinct commercial modules", (
        catalog.LEGACY_MODULE_TO_CAPABILITY["interviews"] == "mod.interviews"
        and catalog.LEGACY_MODULE_TO_CAPABILITY["video_interviews"] == "mod.video_interviews"
    ))
    check("all legacy module keys map into capability catalog", set(modules.MODULE_KEYS) <= set(catalog.LEGACY_MODULE_TO_CAPABILITY))

    protected = modules.protect_setup_module_selection(
        ["pre_hiring", "video_interviews"],
        currently_enabled=["pre_hiring", "interviews", "video_interviews"],
    )
    check("P0 protection retains interviews when omitted from save payload", "interviews" in protected)

    validation = service.validate_module_publish(
        ["assessments"],
        currently_enabled=[],
    )
    check("commercial dependency blocks publish without pre_hiring", validation["blocks_publish"] is True)
    check("authoritative mode hard-disabled in wave1", service.authoritative_enabled() is False)
    check("plane defaults on", service.plane_enabled({}) is True)
    check("kill switch disables plane", service.plane_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "off"}) is False)
    check("dual-write follows plane kill switch", service.dual_write_enabled({"WATHEFNI_TENANT_CONTROL_PLANE": "off"}) is False)

    decision = service.shadow_module_decision(
        company_code="WATHEFNI",
        module_key="interviews",
        legacy_enabled=True,
        canonical_enabled=True,
        surface="apis",
        subject_key="apis:interviews",
    )
    check("shadow decision parity true when equal", decision["parity"] is True and decision["shadow_only"] is True)
    mismatch = service.shadow_module_decision(
        company_code="WATHEFNI",
        module_key="interviews",
        legacy_enabled=True,
        canonical_enabled=False,
        surface="navigation",
        subject_key="navigation:interviews",
    )
    check("shadow decision detects mismatch", mismatch["parity"] is False)

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
