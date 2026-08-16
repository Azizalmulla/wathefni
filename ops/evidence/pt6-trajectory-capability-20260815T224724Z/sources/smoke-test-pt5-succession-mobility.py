#!/usr/bin/env python3
"""PT5 — Succession + mobility intelligence unit/honesty prove."""
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
    print("    pt5 succession mobility — unit prove")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import talent_succession_c6 as c6
    import talent_succession_intel_pt5 as pt5

    h = pt5.honesty_payload()
    check("stamp", pt5.PASS_STAMP == "PT5_SUCCESSION_MOBILITY_INTELLIGENCE_FULL_PASS")
    check("C6 remains SoT", h.get("c6_remains_succession_sot") is True)
    check("no second holder", h.get("no_second_holder_record") is True)
    check("bench is counts", h.get("bench_is_counts_not_score") is True)
    check("no opaque rank", h.get("no_opaque_rank_score") is True)
    check("mobility ≠ application", h.get("mobility_is_not_application") is True)
    check("no silent candidate", h.get("no_silent_candidate") is True)
    check("no silent transfer", h.get("no_silent_transfer") is True)
    check("Talent works Recruiting OFF", h.get("talent_works_recruiting_off") is True)
    check("what-if is PT8", h.get("what_if_is_pt8") is True)
    check("C6 stamp unchanged", c6.PASS_STAMP == "TALENT_SUCCESSION_MOBILITY_FULL_PASS")
    check("C6 uncovered reused", callable(c6.list_uncovered_critical_roles))
    src = (root / "talent_succession_intel_pt5.py").read_text(encoding="utf-8")
    check("no candidate insert", "INSERT INTO talent_pool" not in src)
    check("advisory check", "is_not_application = true" in src)
    http = (root / "talent_http.py").read_text(encoding="utf-8")
    check("HTTP intel", "/succession-intelligence" in http)
    check("HTTP mobility discover", "/mobility/discover" in http)
    check("EN single successor", "Single-successor" in pt5.status_label("single_successor", lang="en"))
    check("AR single successor", "خلف واحد" in pt5.status_label("single_successor", lang="ar"))

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT5_SUCCESSION_MOBILITY_INTELLIGENCE_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
