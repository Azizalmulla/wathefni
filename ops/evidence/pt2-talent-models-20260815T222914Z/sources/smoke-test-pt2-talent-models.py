#!/usr/bin/env python3
"""PT2 — Configurable Talent Models + WHY Graph unit/honesty prove."""
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
    print("    pt2 talent models — unit prove")
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root))
    import talent_evidence_index_pt1 as idx
    import talent_models_pt2 as pt2
    import talent_profile_c5 as c5
    import talent_succession_c6 as c6

    h = pt2.honesty_payload()
    check("pt2 overlay stamp", pt2.PASS_STAMP == "PT2_TALENT_MODELS_WHY_FULL_PASS")
    check("derived ≠ designated HiPo", h.get("derived_signal_is_not_designated_hipo") is True)
    check("no universal talent score", h.get("no_universal_talent_score") is True)
    check("no auto HiPo", h.get("no_auto_hipo") is True)
    check("AI not classification input", h.get("ai_not_classification_input") is True)
    check("missing is not zero", h.get("missing_is_not_zero") is True)
    check("missing is not 100", h.get("missing_is_not_one_hundred") is True)
    check("contradictions not reconciled", h.get("contradictions_not_reconciled") is True)
    check("C5 potential unchanged", h.get("c5_potential_unchanged") is True)
    check("C6 HiPo unchanged", h.get("c6_hipo_unchanged") is True)
    check("no second analytics engine", h.get("no_second_analytics_engine") is True)
    check("C5 stamp unchanged", c5.PASS_STAMP == "TALENT_PROFILE_FULL_PASS")
    check("C6 stamp unchanged", c6.PASS_STAMP == "TALENT_SUCCESSION_MOBILITY_FULL_PASS")
    check("PT1 stamp unchanged", idx.PASS_STAMP == "PT1_OKR_EVIDENCE_FULL_PASS")

    cfg = pt2.default_high_potential_signal_config()
    check("default derivation rules_v1", cfg.get("derivation") == "rules_v1")
    check("default missing insufficient", cfg.get("missing_data_policy") == "insufficient")
    check("default AI narration forbidden", cfg.get("ai_narration") == "forbidden")
    rule = (cfg.get("rules") or [{}])[0]
    pot_clause = next((c for c in (rule.get("all") or []) if c.get("dimension") == "potential"), None)
    check("default HiPo signal requires human potential", pot_clause is not None, pot_clause)
    check(
        "default does not mint from OKR alone",
        not any(c.get("dimension") == "okr" for c in (rule.get("all") or [])),
        rule,
    )
    check(
        "default does not mint from performance alone",
        not any(c.get("dimension") == "performance" for c in (rule.get("all") or [])),
        rule,
    )

    missing_w = pt2._validate_config(
        derivation="weighted_v1",
        dimensions=[{"id": "a"}, {"id": "b"}],
        rules=[],
        weights={"a": 1.0},
        missing_data_policy="insufficient",
    )
    check("weighted_v1 refused without every weight", (missing_w or {}).get("error") == "weighted_v1_missing_weight", missing_w)

    no_w = pt2._validate_config(
        derivation="weighted_v1",
        dimensions=[{"id": "a"}],
        rules=[],
        weights={},
        missing_data_policy="insufficient",
    )
    check("weighted_v1 refused without weights", (no_w or {}).get("error") == "weighted_v1_requires_explicit_weights", no_w)

    bad_sum = pt2._validate_config(
        derivation="weighted_v1",
        dimensions=[{"id": "a"}, {"id": "b"}],
        rules=[],
        weights={"a": 0.4, "b": 0.4},
        missing_data_policy="insufficient",
    )
    check("weighted_v1 weights must sum to 1", (bad_sum or {}).get("error") == "weighted_v1_weights_must_sum_to_1", bad_sum)

    ok_w = pt2._validate_config(
        derivation="weighted_v1",
        dimensions=[{"id": "a"}, {"id": "b"}],
        rules=[],
        weights={"a": 0.6, "b": 0.4},
        missing_data_policy="insufficient",
    )
    check("weighted_v1 accepted when complete", ok_w is None, ok_w)

    no_rules = pt2._validate_config(
        derivation="rules_v1",
        dimensions=[{"id": "potential"}],
        rules=[],
        weights={},
        missing_data_policy="insufficient",
    )
    check("rules_v1 requires rules", (no_rules or {}).get("error") == "rules_v1_requires_rules", no_rules)

    collected = {"a": {"value": None}, "b": {"value": 80}}
    label, pct, terms = pt2._apply_weighted({"a": 0.5, "b": 0.5}, collected, "insufficient", [])
    check("missing weighted → insufficient_evidence", label == "insufficient_evidence")
    check("missing weighted pct is None not 0", pct is None, pct)
    check("missing not treated as 0", all(t.get("treated_as") is None for t in terms), terms)
    check("missing not treated as 100", all(t.get("treated_as") != 100 for t in terms), terms)

    unmapped, unmapped_pct, _ = pt2._apply_weighted(
        {"a": 1.0}, {"a": {"value": "unknown-band"}}, "insufficient", []
    )
    check("unmapped weighted value is insufficient not 100", unmapped == "insufficient_evidence" and unmapped_pct is None)

    label2, fired = pt2._apply_rules(
        [{"id": "hipo", "classification": "derived_high_potential", "all": [{"dimension": "potential", "op": "in", "value": ["high", "expanding"]}]}],
        {"potential": {"value": "low"}, "okr": {"value": 95}, "performance": {"value": "exceeds"}},
    )
    check("high OKR+perf + low potential → no derived HiPo", label2 == "none", (label2, fired))

    label3, fired3 = pt2._apply_rules(
        [{"id": "hipo", "classification": "derived_high_potential", "all": [{"dimension": "potential", "op": "in", "value": ["high", "expanding"]}]}],
        {"potential": {"value": "high"}},
    )
    check("human high potential can fire derived signal", label3 == "derived_high_potential", (label3, fired3))

    check("EN derived signal", "Derived" in pt2.status_label("derived_high_potential", lang="en"))
    check("AR derived signal", "مشتقة" in pt2.status_label("derived_high_potential", lang="ar"))
    check("EN insufficient", "Insufficient" in pt2.status_label("insufficient_evidence", lang="en"))
    check("AR insufficient", "غير كاف" in pt2.status_label("insufficient_evidence", lang="ar"))
    check("EN designated HiPo distinct", "Designated" in pt2.status_label("designated_hipo", lang="en"))
    check("AR designated HiPo distinct", "معيّن" in pt2.status_label("designated_hipo", lang="ar") or "معين" in pt2.status_label("designated_hipo", lang="ar"))
    check("EN published", pt2.status_label("published", lang="en") == "Published")
    check("AR published", pt2.status_label("published", lang="ar") == "منشور")

    src = (root / "talent_models_pt2.py").read_text(encoding="utf-8")
    http = (root / "talent_http.py").read_text(encoding="utf-8")
    surfaces = (root / "talent_surfaces.py").read_text(encoding="utf-8")
    check("no hipo write from evaluate", "decide_hipo" not in src)
    check("no potential write from evaluate", "submit_potential_assessment" not in src)
    check("hipo_written CHECK false", "hipo_written = false" in src)
    check("potential_written CHECK false", "potential_written = false" in src)
    check("published immutable trigger", "published_version_immutable" in src)
    check("contradictions_reconciled hardcoded false", '"contradictions_reconciled": False' in src)
    check("HTTP models list", '"/models"' in http)
    check("HTTP evaluate", '"/models/evaluate"' in http)
    check("HTTP why", '"/models/why/{why_id}"' in http)
    check("HTTP classifications", '"/models/classifications"' in http)
    check("surfaces attach derived", "derived_classifications" in surfaces)
    check("surfaces derived ≠ hipo", "derived_signal_is_not_designated_hipo" in surfaces)
    check("no PT mini-API", "/dashboard/pt2" not in http and "/dashboard/performance-talent" not in http)

    dash = root.parent / "apps/wathefni-dashboard/src/posthire/TalentWorkspace.tsx"
    if dash.exists():
        text = dash.read_text(encoding="utf-8")
        check("HR Web models tab EN", "Derived models" in text)
        check("HR Web models tab AR", "نماذج المشتق" in text)
        check("HR Web derived ≠ HiPo EN", "not a HiPo designation" in text)
        check("HR Web derived ≠ HiPo AR", "ليست تعيين إمكانات عالية" in text)
        check("HR Web WHY label", "why: 'WHY'" in text or "why: 'لماذا'" in text)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT2_TALENT_MODELS_WHY_UNIT_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
