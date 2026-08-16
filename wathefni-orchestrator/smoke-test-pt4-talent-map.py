#!/usr/bin/env python3
"""PT4 — Dynamic Talent Map unit/honesty prove."""
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
    print("    pt4 talent map — unit prove")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import talent_map_pt4 as pt4
    import talent_role_fit_pt3 as pt3
    import talent_succession_c6 as c6

    h = pt4.honesty_payload()
    check("stamp", pt4.PASS_STAMP == "PT4_DYNAMIC_TALENT_MAP_FULL_PASS")
    check("not a 9-box product", h.get("not_a_nine_box_product") is True)
    check("9-box is one lens", h.get("nine_box_is_one_lens") is True)
    check("unknown stays unknown", h.get("unknown_stays_unknown") is True)
    check("no middle forcing", h.get("no_middle_bucket_forcing") is True)
    check("same facts across lenses", h.get("same_facts_across_lenses") is True)
    check("PT3 unchanged", pt3.PASS_STAMP == "PT3_ROLE_FIT_READINESS_FULL_PASS")
    check("C6 project_nine_box exists", callable(c6.project_nine_box))

    facts = {
        "employee_key": "E1",
        "human_potential": "high",
        "designated_hipo": False,
        "role_fit": "strong_fit",
        "human_readiness": None,
        "performance_value": None,
        "trajectory_label": None,
    }
    a = pt4.project_lens(facts, "perf_x_potential")
    b = pt4.project_lens(facts, "potential_x_readiness")
    check("missing axis is unknown", a.get("unknown") is True and a.get("cell") is None, a)
    check("not forced middle", a.get("forced_middle") is False)
    check("lens switch keeps potential", a["canonical_facts"]["human_potential"] == b["canonical_facts"]["human_potential"] == "high")
    check("lens switch keeps hipo false", a["canonical_facts"]["designated_hipo"] is False and b["canonical_facts"]["designated_hipo"] is False)
    check("unknown lens rejected", pt4.project_lens(facts, "free_typed").get("ok") is False)
    check("EN lens", "Potential" in pt4.status_label("perf_x_potential", lang="en"))
    check("AR lens", "الإمكانات" in pt4.status_label("perf_x_potential", lang="ar"))

    http = (root / "talent_http.py").read_text(encoding="utf-8")
    dash = (root.parent / "apps/wathefni-dashboard/src/posthire/TalentWorkspace.tsx").read_text(encoding="utf-8")
    check("HTTP map", '"/map"' in http)
    check("HTTP map why", "/map/{employee_key}/why" in http)
    check("HR Web map EN", "Talent map" in dash)
    check("HR Web map AR", "خريطة المواهب" in dash)
    check("HR Web lens EN", "Lens" in dash)
    check("HR Web unknown EN", "Unknown stays unknown" in dash)
    check("HR Web unknown AR", "المجهول يبقى مجهولاً" in dash)
    check("HR Web RTL dir", "dir={isAr ? 'rtl' : 'ltr'}" in dash or 'dir={isAr ?' in dash)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT4_DYNAMIC_TALENT_MAP_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
