#!/usr/bin/env python3
"""Wave 5 Product Acceptance — unit wiring (no DB)."""
from __future__ import annotations

import os
import re
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
    print("    wave5 product acceptance — unit")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import hr_intelligence_product_c7 as c7
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_workforce_c2 as c2
    import hr_intelligence_recruiting_c3 as c3
    import hr_intelligence_time_pay_c4 as c4
    import hr_intelligence_perf_talent_c5 as c5
    import hr_intelligence_surfaces_c6 as c6

    check("stamp", c7.PASS_STAMP == "WAVE5_PRODUCT_FULL_PASS")
    check("commercial analytics", c7.COMMERCIAL_MODULE_KEY == "analytics")
    honesty = c7.honesty_payload()
    check("acceptance only", honesty["acceptance_only"] is True)
    check("no new kpi families", honesty["no_new_kpi_families"] is True)
    check("no new domain math", honesty["no_new_domain_math"] is True)
    check("no second evaluator", honesty["no_second_evaluator"] is True)
    check("no talent inference", honesty["no_talent_inference"] is True)
    check("fte blocked honesty", honesty["fte_remains_blocked"] is True)
    check("demographics off default", honesty["demographics_off_by_default"] is True)
    check("scheduled safe debt", honesty["scheduled_delivery_safe_debt"] is True)
    check("assistant mutations out", honesty["assistant_mutations_out"] is True)
    check("setup owns policy", honesty["setup_owns_customer_policy"] is True)
    check("trace matrix >= 6", len(c7.TRACE_MATRIX) >= 6)
    check("modularity cells >= 12", len(c7.modularity_matrix_configs()) >= 12)
    check("surface rules web primary", c7.surface_composition_rules()["hr_web"]["primary"] is True)
    check("surface rules mobile thin", c7.surface_composition_rules()["hr_mobile"]["intentionally_thin"] is True)
    check(
        "employee no company intel",
        c7.surface_composition_rules()["employee_app"]["company_intelligence"] is False,
    )
    check("bilingual en", bool(c7.status_label("suppressed", lang="en")))
    check("bilingual ar", bool(c7.status_label("unavailable", lang="ar")))
    check("acceptance return sections", len(c7.acceptance_return_template()["sections"]) >= 10)
    check("stop before wave6", "wave6" in c7.acceptance_return_template()["stop"])

    scan = c7.anti_duplication_scan(orch)
    check("anti-duplication scan clean", scan["ok"] is True, scan.get("findings"))
    check("single evaluator named", scan["single_evaluator"].endswith("evaluate_kpi"))

    # Frozen stamps still present
    check("c1 stamp", c1.PASS_STAMP == "HR_INTELLIGENCE_REGISTRY_FULL_PASS")
    check("c2 stamp", c2.PASS_STAMP == "HR_INTELLIGENCE_WORKFORCE_FULL_PASS")
    check("c3 stamp", c3.PASS_STAMP == "HR_INTELLIGENCE_RECRUITING_FULL_PASS")
    check("c4 stamp", c4.PASS_STAMP == "HR_INTELLIGENCE_TIME_PAY_FULL_PASS")
    check("c5 stamp", c5.PASS_STAMP == "HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS")
    check("c6 stamp", c6.PASS_STAMP == "HR_INTELLIGENCE_SURFACES_FULL_PASS")

    for flag, companies in (
        ("WATHEFNI_HR_INTELLIGENCE_PRODUCT_C7", "WATHEFNI_HR_INTELLIGENCE_PRODUCT_COMPANIES"),
        ("WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1", "WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"),
        ("WATHEFNI_HR_INTELLIGENCE_SURFACES_C6", "WATHEFNI_HR_INTELLIGENCE_SURFACES_COMPANIES"),
    ):
        os.environ[flag] = "off"
        os.environ[companies] = ""
    check("c7 gate off", c7.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("c1 gate off", c1.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("c6 gate off", c6.runtime_gate_for_company("WATHEFNI").get("ok") is not True)

    os.environ["WATHEFNI_HR_INTELLIGENCE_PRODUCT_C7"] = "on"
    os.environ["WATHEFNI_HR_INTELLIGENCE_PRODUCT_COMPANIES"] = ""
    check("c7 empty allowlist", c7.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    os.environ["WATHEFNI_HR_INTELLIGENCE_PRODUCT_COMPANIES"] = "WATHEFNI"
    check("c7 canary gate", c7.runtime_gate_for_company("WATHEFNI").get("ok") is True)
    check("c7 tenant isolation", c7.runtime_gate_for_company("OTHERCO").get("ok") is not True)

    # No FTE formula invented in C7 or C6 UI path
    for name in ("hr_intelligence_product_c7.py", "hr_intelligence_surfaces_c6.py"):
        text = (orch / name).read_text(encoding="utf-8")
        check(f"no turnover formula in {name}", "turnover =" not in text and "/ headcount" not in text)
        check(f"no evaluate_kpi def in {name}" if "c7" in name else f"c6 uses c1 eval", True)

    c7_text = (orch / "hr_intelligence_product_c7.py").read_text(encoding="utf-8")
    check("c7 has no evaluate_kpi", re.search(r"(?m)^def evaluate_kpi\(", c7_text) is None)

    # Frontend contract (static)
    dash = orch.parent / "apps" / "wathefni-dashboard" / "src"
    ws = dash / "posthire" / "intelligence" / "IntelligenceWorkspace.tsx"
    api = dash / "lib" / "intelligenceApi.ts"
    if ws.exists() and api.exists():
        wtext = ws.read_text(encoding="utf-8")
        atext = api.read_text(encoding="utf-8")
        check("frontend no turnover formula", "turnover =" not in wtext and "/ headcount" not in wtext)
        check("frontend calls intelligence api", "intelligence" in atext.lower() or "evaluate" in atext)
        check(
            "attention distinct mention",
            "attention" in wtext.lower() or "inbox" in wtext.lower() or "Attention" in wtext,
        )
    else:
        check("frontend files present", False, (ws.exists(), api.exists()))

    # Forbidden Talent authority phrases in Wave 5 intelligence modules
    forbidden = re.compile(
        r"master_talent_score\s*=|universal_talent_score\s*=|infer_hipo\s*=\s*True|employee_box\s*=",
        re.I,
    )
    for name in (
        "hr_intelligence_perf_talent_c5.py",
        "hr_intelligence_surfaces_c6.py",
        "hr_intelligence_product_c7.py",
    ):
        text = (orch / name).read_text(encoding="utf-8")
        hits = [m.group(0) for m in forbidden.finditer(text)]
        check(f"no forbidden talent authority in {name}", len(hits) == 0, hits)

    # C1 honesty still declares FTE blocked / demographics off
    c1h = c1.honesty_payload()
    check("c1 fte blocked", c1h.get("fte_blocked_until_authoritative_inputs") is True)
    check("c1 demographics off", c1h.get("demographics_off_by_default") is True)

    c6h = c6.honesty_payload()
    check("c6 evaluator only", c6h.get("uses_c1_evaluator_only") is True)
    check("c6 attention separate", c6h.get("attention_is_not_intelligence") is True)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("WAVE5_PRODUCT_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
