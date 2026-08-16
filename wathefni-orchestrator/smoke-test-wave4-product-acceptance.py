#!/usr/bin/env python3
"""Wave 4 Product Acceptance — unit wiring (no DB)."""
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
    print("    wave4 product acceptance — unit")
    orch = Path(__file__).resolve().parent
    root = orch.parent
    sys.path.insert(0, str(orch))

    import setup_console_wave4_policies as w4p
    import performance_goals_c1 as c1
    import performance_reviews_c2 as c2
    import performance_feedback_c3 as c3
    import performance_calibration_c4 as c4
    import talent_profile_c5 as c5
    import talent_succession_c6 as c6

    check("setup wave4 policies module", callable(w4p.get_all_wave4_policies))
    check("setup patch wave4", callable(w4p.patch_wave4_module_policy))
    check("modularity matrix >= 12", len(w4p.modularity_matrix_configs()) >= 12)
    check("setup owns wave4", w4p.honesty_payload().get("setup_owns_wave4_policies") is True)
    check("not env-only", w4p.honesty_payload().get("env_only_ownership") is False)
    check("no new domain in c7", w4p.honesty_payload().get("no_new_domain_authority_in_c7") is True)
    check("c3 sole development", w4p.honesty_payload().get("c3_sole_development_authority") is True)
    check("EN goals label", "Goals" in w4p.status_label("performance_goals", lang="en"))
    check("AR talent label", bool(w4p.status_label("talent_profile", lang="ar")))
    check("wave5 fact catalog", len(w4p.wave5_fact_catalog()) >= 8)
    naming = w4p.naming_boundary_payload()
    check("recruiting pool key", naming["recruiting_talent_pool"]["storage_key"] == "talent_pool")
    check("posthire module talent", naming["posthire_talent"]["module_key"] == "talent")
    check("no naming collision", naming.get("collision") is False)
    check("assessment norms rename", "Assessment norms" in naming["assessment_norms"]["product_label_en"])
    surf = w4p.surface_composition_rules()
    check("assistant no mutations", surf["assistant"]["mutations"] is False)
    check("no empty tabs rule", surf["disabled_capability_ux"]["no_empty_tabs"] is True)
    check("hr mobile not forced heavyweight", "heavyweight_calibration_admin" in surf["hr_mobile"]["not_forced"])

    for flag, companies in (
        ("WATHEFNI_PERFORMANCE_GOALS_C1", "WATHEFNI_PERFORMANCE_GOALS_COMPANIES"),
        ("WATHEFNI_PERFORMANCE_REVIEWS_C2", "WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES"),
        ("WATHEFNI_PERFORMANCE_FEEDBACK_C3", "WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES"),
        ("WATHEFNI_PERFORMANCE_CALIBRATION_C4", "WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES"),
        ("WATHEFNI_TALENT_PROFILE_C5", "WATHEFNI_TALENT_PROFILE_COMPANIES"),
        ("WATHEFNI_TALENT_SUCCESSION_C6", "WATHEFNI_TALENT_SUCCESSION_COMPANIES"),
    ):
        os.environ[flag] = "off"
        os.environ[companies] = ""

    check("C1 off", c1.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C2 off", c2.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C3 off", c3.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C4 off", c4.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C5 off", c5.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    check("C6 off", c6.runtime_gate_for_company("WATHEFNI").get("ok") is not True)

    # Anti-score / anti-box scan on frozen modules
    forbidden = re.compile(
        r"\btalent_score\b|master_talent_score\s*=|employee\.box\s*=|CREATE TABLE[^\n]*employee_box",
        re.I,
    )
    allow_mention = ("no_master_talent_score", "no_canonical_employee_box", "employee_box_canonical_field")
    for mod in (
        "performance_goals_c1.py",
        "performance_reviews_c2.py",
        "performance_feedback_c3.py",
        "performance_calibration_c4.py",
        "talent_profile_c5.py",
        "talent_succession_c6.py",
        "setup_console_wave4_policies.py",
    ):
        text = (orch / mod).read_text(encoding="utf-8")
        hits = []
        for m in forbidden.finditer(text):
            # skip honesty/forbidden asserts
            start = max(0, m.start() - 80)
            ctx = text[start : m.end() + 40]
            if any(a in ctx for a in allow_mention):
                continue
            if "CHECK (" in ctx and "master_talent_score" in ctx:
                continue  # constraint forbidding the key
            if "inferred_from_nine_box = false" in ctx:
                continue
            hits.append(m.group(0))
        check(f"no forbidden authority in {mod}", len(hits) == 0, hits)

    check("c3 development honesty", c3.honesty_payload().get("development_durable_beyond_review_cycles") is True)
    check("c6 nine box projection", c6.honesty_payload().get("nine_box_is_projection_not_sot") is True)
    check("c5 no master score", c5.honesty_payload().get("no_master_talent_score") is True)

    try:
        import platform_assistant_spine_wave1 as spine

        os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "off"
        check("assistant mutations explicit off", spine.assistant_mutations_allowed() is False)
        os.environ.pop("WATHEFNI_ASSISTANT_MUTATIONS", None)
    except Exception as exc:
        check("assistant spine import", False, exc)

    app = (orch / "app.py").read_text(encoding="utf-8")
    check("app merges wave4 policies", "setup_console_wave4_policies" in app and '"wave4"' in app)

    web = root / "apps" / "wathefni-dashboard" / "src"
    check("Setup Wave4 card file retained", (web / "setup-console/Wave4PerformanceTalentPoliciesCard.tsx").is_file())
    setup_app = (web / "setup-console/SetupConsoleApp.tsx").read_text(encoding="utf-8")
    check(
        "Setup remounts Performance card after R5B",
        "Wave4PerformancePoliciesCard" in setup_app,
    )
    check("wave4 honesty performance enableable", w4p.honesty_payload().get("performance_customer_enableable") is True)
    check("wave4 honesty talent enableable after R5C", w4p.honesty_payload().get("talent_customer_enableable") is True)

    mobile = root / "apps" / "wathefni-employee-mobile"
    check("employee mobile present", mobile.exists())
    rtl_hits = 0
    if mobile.exists():
        for p in mobile.rglob("*.tsx"):
            try:
                t = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "rtl" in t.lower() or "I18nManager" in t:
                rtl_hits += 1
                if rtl_hits >= 2:
                    break
    check("EN/AR/RTL surface markers", rtl_hits >= 1, rtl_hits)

    for p in (
        "ops/PERFORMANCE_GOALS_FULL_PASS.md",
        "ops/PERFORMANCE_REVIEWS_FULL_PASS.md",
        "ops/PERFORMANCE_FEEDBACK_COMPETENCIES_FULL_PASS.md",
        "ops/PERFORMANCE_CALIBRATION_DEV_FULL_PASS.md",
        "ops/TALENT_PROFILE_FULL_PASS.md",
        "ops/TALENT_SUCCESSION_MOBILITY_FULL_PASS.md",
        "ops/WAVE1_PRODUCT_FULL_PASS.md",
        "ops/WAVE2_PRODUCT_FULL_PASS.md",
        "ops/WAVE3_PRODUCT_FULL_PASS.md",
    ):
        check(f"prior stamp doc {Path(p).name}", (root / p).is_file())

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("WAVE4_PRODUCT_UNIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
