#!/usr/bin/env python3
"""Wave 1 — Hire→Ready bridge unit smoke (no DB required)."""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
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
    print("    hire-ready bridge — flags, ranks, wiring, freeze docs")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import hire_ready_bridge as hrb
    import employment_truth_sync as ets

    check("bridge version", hrb.BRIDGE_VERSION == "1.0.0")
    os.environ.pop("WATHEFNI_HIRE_READY_WAVE1", None)
    os.environ.pop("WATHEFNI_HIRE_READY_COMPANIES", None)
    check("wave1 off by default", hrb.wave1_enabled_for_company("ACME").get("enabled") is False)

    os.environ["WATHEFNI_HIRE_READY_WAVE1"] = "on"
    os.environ["WATHEFNI_HIRE_READY_COMPANIES"] = "CANARY1"
    check("allowlist denies other", hrb.wave1_enabled_for_company("OTHER").get("enabled") is False)
    check("allowlist allows canary", hrb.wave1_enabled_for_company("CANARY1").get("enabled") is True)

    os.environ["WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS"] = "on"
    os.environ.pop("WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES", None)
    check("truth writers dark without company allowlist", ets.writers_enabled_for_company("CANARY1") is False)
    os.environ["WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES"] = "CANARY1"
    check("truth writers canary only", ets.writers_enabled_for_company("CANARY1") is True)
    check("truth writers not global", ets.writers_enabled_for_company("OTHER") is False)

    check("rank hr > hire > offer", ets.joining_date_authority_rank("hr_explicit_edit") > ets.joining_date_authority_rank("hire_tx"))
    check("rank hire > offer", ets.joining_date_authority_rank("hire_tx") > ets.joining_date_authority_rank("offer_accept"))

    offer = {
        "company_code": "CANARY1",
        "candidate_phone_snapshot": "96550001111",
        "proposed_start_date": (date.today() + timedelta(days=10)).isoformat(),
        "offer_id": "o1",
    }
    check("resolve employee_key from offer phone", hrb.resolve_offer_employee_key(offer) == "CANARY1-96550001111")

    hire_src = (orch / "hire_operations.py").read_text(encoding="utf-8")
    offer_src = (orch / "offer_service.py").read_text(encoding="utf-8")
    http_src = (orch / "preboarding_http.py").read_text(encoding="utf-8")
    check("hire_operations wires bridge", "hire_ready_bridge" in hire_src and "on_hire_employee_tx" in hire_src)
    check("offer_service wires accept hook", "on_offer_accepted" in offer_src)
    check("token accept path wires bridge", offer_src.count("on_offer_accepted") >= 2)
    check("preboarding convert route", "/convert" in http_src and "convert_ready_assignment_to_hire" in http_src)
    check("cancel closes provisional", "on_preboard_cancelled" in http_src)
    check("joining-date fan-out hook", "on_joining_date_changed" in http_src)

    freeze = root / "ops" / "PREBOARDING_SURFACE_WAVE_FREEZE.md"
    check("surface freeze doc", freeze.is_file() and "FROZEN" in freeze.read_text(encoding="utf-8"))
    check("rollback guidance present", "WATHEFNI_HIRE_READY_WAVE1=off" in str(hrb.rollback_guidance()))

    # Restore dark defaults for process
    os.environ["WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS"] = "off"
    os.environ.pop("WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES", None)
    os.environ["WATHEFNI_HIRE_READY_WAVE1"] = "off"

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("HIRE_READY_BRIDGE_UNIT_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
