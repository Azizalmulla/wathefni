#!/usr/bin/env python3
"""PT3 — Role Fit + Readiness Intelligence unit/honesty prove."""
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
    print("    pt3 role fit — unit prove")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import job_architecture_c1 as ja
    import talent_models_pt2 as pt2
    import talent_role_fit_pt3 as pt3
    import talent_succession_c6 as c6

    h = pt3.honesty_payload()
    check("pt3 stamp", pt3.PASS_STAMP == "PT3_ROLE_FIT_READINESS_FULL_PASS")
    check("fit ≠ readiness", h.get("role_fit_is_not_readiness") is True)
    check("fit ≠ promotion", h.get("role_fit_is_not_promotion_eligibility") is True)
    check("readiness ≠ promotion", h.get("readiness_is_not_promotion_eligibility") is True)
    check("C6 readiness authoritative", h.get("human_c6_readiness_authoritative") is True)
    check("no JA write-back", h.get("no_write_back_to_ja") is True)
    check("no universal %", h.get("no_universal_fit_percent") is True)
    check("missing not 0", h.get("missing_is_not_zero") is True)
    check("missing not 100", h.get("missing_is_not_one_hundred") is True)
    check("JA off unavailable", h.get("ja_off_fit_unavailable") is True)
    check("Talent works without JA", h.get("talent_works_without_ja") is True)
    check("PT2 stamp unchanged", pt2.PASS_STAMP == "PT2_TALENT_MODELS_WHY_FULL_PASS")
    check("JA stamp unchanged", ja.PASS_STAMP == "JOB_ARCHITECTURE_FULL_PASS")
    check("C6 stamp unchanged", c6.PASS_STAMP == "TALENT_SUCCESSION_MOBILITY_FULL_PASS")

    bad = pt3._validate_requirements(
        [{"id": "a", "kind": "skill", "priority": "required"}],
        derivation="weighted_v1",
        weights={},
        missing_data_policy="insufficient",
    )
    check("weighted refused without weights", (bad or {}).get("error") == "weighted_v1_requires_explicit_weights", bad)

    overall = pt3._overall_fit(
        [{"priority": "required", "outcome": "not_assessed"}],
        ja_required=False,
        ja_on=False,
    )
    check("missing → not_assessed not gap/ready", overall == "not_assessed", overall)
    check("JA required + JA off → unavailable", pt3._overall_fit([], ja_required=True, ja_on=False) == "unavailable")
    check("all met → strong_fit", pt3._overall_fit([{"priority": "required", "outcome": "met"}], ja_required=False, ja_on=True) == "strong_fit")
    check("partial required → partial_fit", pt3._overall_fit([{"priority": "required", "outcome": "partial"}], ja_required=False, ja_on=True) == "partial_fit")
    check("required gap → gaps", pt3._overall_fit([{"priority": "required", "outcome": "gap"}], ja_required=False, ja_on=True) == "gaps")
    check("suggestion unassessed for missing", pt3._suggest_readiness("not_assessed", []) == "unassessed")
    check("suggestion does not invent not_ready from missing", pt3._suggest_readiness("not_assessed", []) != "not_ready")

    check("EN strong fit", pt3.status_label("strong_fit", lang="en") == "Strong fit")
    check("AR strong fit", "قوية" in pt3.status_label("strong_fit", lang="ar"))
    check("EN not assessed", "Not assessed" in pt3.status_label("not_assessed", lang="en"))
    check("AR not assessed", "غير" in pt3.status_label("not_assessed", lang="ar"))
    check("EN unavailable", pt3.status_label("unavailable", lang="en") == "Unavailable")
    check("AR unavailable", "غير متاح" in pt3.status_label("unavailable", lang="ar"))
    check("EN fit ≠ readiness labels", pt3.status_label("role_fit", lang="en") != pt3.status_label("readiness", lang="en"))
    check("AR fit ≠ readiness labels", pt3.status_label("role_fit", lang="ar") != pt3.status_label("readiness", lang="ar"))

    src = (root / "talent_role_fit_pt3.py").read_text(encoding="utf-8")
    http = (root / "talent_http.py").read_text(encoding="utf-8")
    check("no JA score write", "UPDATE ja_" not in src)
    check("ja_written CHECK false", "ja_written = false" in src)
    check("c6 readiness CHECK false", "c6_readiness_written = false" in src)
    check("HTTP role-fit sets", "/role-fit/sets" in http)
    check("HTTP evaluate", "/role-fit/evaluate" in http)
    check("HTTP import-ja", "/role-fit/import-ja" in http)
    check("no PT mini-API", "/dashboard/pt3" not in http)

    dash = root.parent / "apps/wathefni-dashboard/src/posthire/TalentWorkspace.tsx"
    if dash.exists():
        text = dash.read_text(encoding="utf-8")
        check("HR Web role fit EN", "Role fit" in text)
        check("HR Web role fit AR", "ملاءمة الدور" in text)
        check("HR Web fit ≠ ready EN", "not readiness" in text)
        check("HR Web fit ≠ ready AR", "ليست جاهزية" in text)
        check("HR Web JA off honesty EN", "honestly unavailable" in text)
        check("HR Web JA off honesty AR", "غير متاحة بصدق" in text)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT3_ROLE_FIT_READINESS_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
