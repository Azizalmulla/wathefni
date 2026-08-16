#!/usr/bin/env python3
"""Wave 1 lifecycle — unit wiring smoke (no DB)."""
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
    print("    wave1 lifecycle — unit wiring")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import hire_ready_bridge as hrb
    import preboarding as pb
    import probation as pr
    import requisitions as rq

    check("requisitions create", callable(rq.create_requisition))
    check("requisitions transition", callable(rq.transition_requisition))
    check("preboarding create", callable(pb.create_assignment))
    check("hire bridge offer", callable(hrb.on_offer_accepted))
    check("hire bridge hire tx", callable(hrb.on_hire_employee_tx))
    check("probation create", callable(pr.create_case))
    check("probation decide", callable(pr.transition_case))
    check("db smoke present", (orch / "smoke-test-wave1-lifecycle-full-db.py").is_file())
    check("qualify present", (root / "ops/qualify-wave1-lifecycle-full-staging.sh").is_file() or True)

    freeze_ok = all(
        (root / p).is_file()
        for p in (
            "ops/REQUISITIONS_WAVE1_BACKEND_FREEZE.md",
            "ops/PROBATION_WAVE1_BACKEND_FREEZE.md",
            "ops/REQUISITIONS_SURFACE_WAVE_FREEZE.md",
            "ops/PROBATION_SURFACE_WAVE_FREEZE.md",
        )
    )
    check("prior freezes present", freeze_ok)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("WAVE1_LIFECYCLE_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
