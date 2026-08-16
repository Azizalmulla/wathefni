#!/usr/bin/env python3
"""PT6 — Trajectory + capability intelligence unit/honesty prove."""
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
    print("    pt6 trajectory — unit prove")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import hr_intelligence_registry_c1 as w5
    import talent_trajectory_pt6 as pt6

    h = pt6.honesty_payload()
    check("stamp", pt6.PASS_STAMP == "PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_FULL_PASS")
    check("no label without policy", h.get("no_label_without_policy") is True)
    check("closed periods only", h.get("closed_periods_only") is True)
    check("insufficient history unlabeled", h.get("insufficient_history_has_no_label") is True)
    check("does not overwrite performance", h.get("does_not_overwrite_performance") is True)
    check("no second analytics engine", h.get("no_second_analytics_engine") is True)
    check("no flight-risk score", h.get("no_flight_risk_score") is True)
    check("holder dep no employment mutate", h.get("holder_dependency_does_not_mutate_employment") is True)
    check("Wave 5 registry stamp unchanged", w5.PASS_STAMP == "HR_INTELLIGENCE_REGISTRY_FULL_PASS")
    for kind in pt6.PT6_FORMULA_KINDS.values():
        check(f"handler registered {kind}", kind in w5._FORMULA_HANDLERS, list(w5._FORMULA_HANDLERS)[:8])
    check("EN accelerating", pt6.status_label("accelerating", lang="en") == "Accelerating")
    check("AR accelerating", "متسارع" in pt6.status_label("accelerating", lang="ar"))
    src = (root / "talent_trajectory_pt6.py").read_text(encoding="utf-8")
    check("no UPDATE employees", "UPDATE employees" not in src)
    http = (root / "talent_http.py").read_text(encoding="utf-8")
    check("HTTP trajectory policy", "/trajectory/policy" in http)
    check("HTTP holder dependency", "/capability/holder-dependency/" in http)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
