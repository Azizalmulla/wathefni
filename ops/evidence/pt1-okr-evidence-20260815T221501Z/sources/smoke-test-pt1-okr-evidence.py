#!/usr/bin/env python3
"""PT1 — OKR operating depth + Talent Evidence Index unit/honesty prove."""
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
    print("    pt1 okr evidence — unit prove")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import okr_operating_pt1 as pt1
    import performance_goals_c1 as c1
    import talent_evidence_index_pt1 as idx

    h = pt1.honesty_payload()
    check("pt1 overlay stamp", pt1.PASS_STAMP == "PT1_OKR_EVIDENCE_FULL_PASS")
    check("c1 remains OKR SoT", h.get("c1_remains_okr_sot") is True)
    check("okr cycle ≠ review cycle", h.get("okr_cycle_is_not_review_cycle") is True)
    check("alignment no score inheritance", h.get("alignment_does_not_inherit_score") is True)
    check("check-in ≠ progress", h.get("check_in_is_not_progress_authority") is True)
    check("confidence ≠ progress", h.get("confidence_is_not_progress") is True)
    check("no second goals table", h.get("no_second_goals_table") is True)
    check("no frontend progress truth", h.get("no_frontend_progress_truth") is True)
    check("okr not goal_kind", h.get("okr_not_stored_as_goal_kind") is True)
    check("no trajectory labels", h.get("trajectory_labels_not_computed") is True)
    check("no assistant talent tools", h.get("assistant_talent_tools") is False)
    check("c1 stamp unchanged", c1.PASS_STAMP == "PERFORMANCE_GOALS_FULL_PASS")

    ih = idx.honesty_payload()
    check("pointer not second SoT", ih.get("pointer_not_second_sot") is True)
    check("no universal talent score", ih.get("no_universal_talent_score") is True)
    check("no classification in PT1", ih.get("no_talent_classification_in_pt1") is True)
    check("AI not classification input", ih.get("ai_synthesized_not_classification_input") is True)
    check("contradictions coexist", ih.get("contradictions_coexist") is True)
    check("consume default off", ih.get("consume_contracts_default_off") is True)
    check("okr ≠ potential", ih.get("okr_is_not_potential") is True)
    check("okr ≠ hipo", ih.get("okr_is_not_hipo") is True)
    check("okr ≠ readiness", ih.get("okr_is_not_readiness") is True)
    check("claimed not verified", ih.get("claimed_skill_is_not_verified") is True)
    check("no second analytics engine", ih.get("no_second_analytics_engine") is True)
    forbid = idx.assert_no_classification_writes()
    check("no potential writes", forbid.get("potential_writes") is False)
    check("no hipo writes", forbid.get("hipo_writes") is False)
    check("no readiness writes", forbid.get("readiness_writes") is False)
    check("no talent model writes", forbid.get("talent_model_writes") is False)
    check("AI classification input false", forbid.get("ai_classification_input") is False)

    contracts = idx.default_consume_contracts()
    check("okr consume default off", contracts.get("okr_as_talent_evidence_v1") is False)
    check("learning consume default off", contracts.get("learning_cert_as_evidence_v1") is False)
    check("ja consume default off", contracts.get("ja_assignment_as_evidence_v1") is False)
    check("assessment consume default off", contracts.get("assessment_as_evidence_v1") is False)
    check("claimed display default on", contracts.get("claimed_skill_display_v1") is True)

    check("EN okr cycle", pt1.status_label("okr_cycle", lang="en") == "OKR cycle")
    check("AR okr cycle", "نتائج" in pt1.status_label("okr_cycle", lang="ar"))
    check("EN review cycle distinct", pt1.status_label("review_cycle", lang="en") == "Review cycle")
    check("AR review cycle distinct", "مراجعة" in pt1.status_label("review_cycle", lang="ar"))
    check("EN confidence", pt1.status_label("confidence", lang="en") == "Confidence")
    check("AR confidence", pt1.status_label("confidence", lang="ar") == "الثقة")
    check("EN claimed", "Claimed" in idx.status_label("claimed", lang="en"))
    check("AR claimed", "مُدّعى" in idx.status_label("claimed", lang="ar") or "مدعى" in idx.status_label("claimed", lang="ar"))
    check("EN AI provenance", "explanation" in idx.status_label("AI-SYNTHESIZED", lang="en").lower())
    check("AR AI provenance", "شرح" in idx.status_label("AI-SYNTHESIZED", lang="ar"))

    check(
        "employee cannot see private team objective",
        pt1.can_view_objective(
            actor_role="employee",
            visibility="owner_manager",
            owner_employee_key="EMP-A",
            actor_employee_key="EMP-B",
            manager_scope_keys=[],
            objective_scope="team",
        )
        is False,
    )
    check(
        "owner can see own restricted objective",
        pt1.can_view_objective(
            actor_role="employee",
            visibility="owner_manager",
            owner_employee_key="EMP-A",
            actor_employee_key="EMP-A",
            manager_scope_keys=[],
            objective_scope="individual",
        )
        is True,
    )
    check(
        "company objective broadly visible",
        pt1.can_view_objective(
            actor_role="employee",
            visibility="owner_manager",
            owner_employee_key="EMP-A",
            actor_employee_key="EMP-B",
            manager_scope_keys=[],
            company_objectives_broadly_visible=True,
            objective_scope="company",
        )
        is True,
    )
    check(
        "hr can see restricted",
        pt1.can_view_objective(
            actor_role="hr",
            visibility="owner_manager",
            owner_employee_key="EMP-A",
            actor_employee_key="HR-1",
            manager_scope_keys=[],
            objective_scope="individual",
        )
        is True,
    )
    check(
        "manager sees only scoped reports",
        pt1.can_view_objective(
            actor_role="manager",
            visibility="owner_manager",
            owner_employee_key="EMP-A",
            actor_employee_key="MGR",
            manager_scope_keys=["EMP-A"],
            objective_scope="individual",
        )
        is True
        and pt1.can_view_objective(
            actor_role="manager",
            visibility="owner_manager",
            owner_employee_key="EMP-B",
            actor_employee_key="MGR",
            manager_scope_keys=["EMP-A"],
            objective_scope="individual",
        )
        is False,
    )

    hib = c1.compute_progress(direction="higher_is_better", baseline=0, target=100, current=65)
    check("c1 measure math unchanged", hib.get("progress_pct") == 65.0, hib)
    dec = c1.reject_decorative_progress_pct(progress_pct=87)
    check("decorative % still forbidden", dec.get("error") == "decorative_progress_pct_forbidden", dec)

    src = (root / "okr_operating_pt1.py").read_text(encoding="utf-8")
    idx_src = (root / "talent_evidence_index_pt1.py").read_text(encoding="utf-8")
    http = (root / "performance_http.py").read_text(encoding="utf-8")
    talent_http = (root / "talent_http.py").read_text(encoding="utf-8")
    check("no okr_objectives_v2", "okr_objectives_v2" not in src)
    check(
        "no generic goal_kind storage",
        "goal_kind=" not in src and "goal_kind =" not in src and "'goal_kind'" not in src,
    )
    check("no accelerating label", "accelerating" not in src.lower() or "trajectory_labels" in src)
    check("no declining computation", "declining" not in src)
    check("HTTP okr-cycles", "/dashboard/performance/okr-cycles" in http)
    check("HTTP alignment", "/dashboard/performance/alignment" in http)
    check("HTTP updates", "/objectives/{objective_id}/updates" in http)
    check("app current cycle", "/app/performance/okr-cycles/current" in http)
    check("no generic evidence storage API", "/dashboard/posthire/talent/evidence-index/raw" not in talent_http)
    check("talent evidence-index GET", "/evidence-index/{employee_key}" in talent_http)
    check("talent okr index POST only", "/evidence-index/okr" in talent_http)
    check("AI constraint in schema", "ter_ai_not_input_chk" in idx_src)
    check("no copied rating constraint", "ter_no_copied_rating_chk" in idx_src)

    dash = root.parent / "apps/wathefni-dashboard/src/posthire/PerformanceWorkspace.tsx"
    mobile_en = root.parent / "apps/wathefni-employee-mobile/src/i18n/en.json"
    mobile_ar = root.parent / "apps/wathefni-employee-mobile/src/i18n/ar.json"
    setup = root.parent / "apps/wathefni-dashboard/src/setup-console/Wave4PerformanceTalentPoliciesCard.tsx"
    if dash.exists():
        text = dash.read_text(encoding="utf-8")
        check("HR Web OKR cycle copy EN", "OKR cycle" in text)
        check("HR Web OKR cycle copy AR", "دورة النتائج الرئيسية" in text)
        check("HR Web alignment on request", "showAlignment" in text)
        check("HR Web no default tree dump", "Show alignment" in text)
    if mobile_en.exists() and mobile_ar.exists():
        en = mobile_en.read_text(encoding="utf-8")
        ar = mobile_ar.read_text(encoding="utf-8")
        check("Employee EN okrCycle", '"okrCycle"' in en)
        check("Employee AR okrCycle", '"okrCycle"' in ar and "دورة النتائج الرئيسية" in ar)
        check("Employee EN check-in ≠ progress", "checkInNotProgress" in en)
        check("Employee AR check-in ≠ progress", "المتابعة لا تغيّر التقدم" in ar)
    if setup.exists():
        st = setup.read_text(encoding="utf-8")
        check("Setup confidence policy", "confidence_enabled" in st)
        check("Setup OKR consume contract", "okr_as_talent_evidence" in st)

    digest = idx.payload_hash(source_authority="perf_objectives", source_id="x", source_version="1", marker={"a": 1})
    digest2 = idx.payload_hash(source_authority="perf_objectives", source_id="x", source_version="1", marker={"a": 1})
    check("payload hash stable", digest == digest2 and len(digest) == 64)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT1_OKR_EVIDENCE_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
