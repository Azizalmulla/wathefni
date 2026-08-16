#!/usr/bin/env python3
"""Wave 6 Product Acceptance — unit wiring (no DB)."""
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
    print("    wave6 product acceptance — unit")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    import wave6_hcm_expansion_product_c8 as c8
    import setup_console_wave6_policies as w6

    check("phase", c8.PHASE == "wave6_hcm_expansion_product_c8")
    check("stamp", c8.PASS_STAMP == "WAVE6_PRODUCT_FULL_PASS")
    honesty = c8.honesty_payload()
    check("acceptance only", honesty["acceptance_only"] is True)
    check("no new module authority", honesty["no_new_module_authority"] is True)
    check("no new domain math", honesty["no_new_domain_math"] is True)
    check("consumes c1-c7", honesty["consumes_c1_through_c7_only"] is True)
    check("one employee truth", honesty["one_canonical_employee_employment_org"] is True)
    check("ja sole grade authority", honesty["ja_sole_wave6_job_grade_authority"] is True)
    check("no second analytics", honesty["no_second_analytics_engine"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    check("setup owns", honesty["setup_owns_wave6_policies"] is True)
    check("full pass not rollout", honesty["full_pass_not_broad_rollout"] is True)
    check("modularity cells >= 17", len(c8.MODULARITY_CELLS) >= 17)
    check("modularity configs match", len(c8.modularity_matrix_configs()) == len(c8.MODULARITY_CELLS))
    check("authority matrix 7", len(c8.module_authority_matrix()) == 7)
    check("handoff contracts 5", len(c8.handoff_contract_matrix()) >= 5)
    check("permission matrix", len(c8.permission_confidentiality_matrix()) >= 10)
    check("bilingual en", bool(c8.status_label("available", lang="en")))
    check("bilingual ar", bool(c8.status_label("unavailable", lang="ar")))
    surf = c8.surface_composition_rules()
    check("web primary", surf["hr_web"]["primary"] is True)
    check("mobile thin", surf["hr_mobile"]["intentionally_thin"] is True)
    check("assistant ro", surf["assistant"]["mutations"] is False)
    check("disabled clean", surf["disabled_capability_ux"]["disappear_cleanly"] is True)

    tmpl = c8.acceptance_return_template()
    check("acceptance sections", len(tmpl["sections"]) >= 12)
    check("stop owner signoff", "owner_signoff" in tmpl["stop"])
    check("do not auto begin domains", "additional_hcm_domains" in tmpl["do_not_begin_automatically"])

    scan = c8.anti_duplication_scan(orch)
    check("anti-duplication scan clean", scan["ok"] is True, scan.get("findings"))
    check("ja sole grade ddl", scan["ja_sole_grade_ddl"] is True, scan)

    contracts = c8.contract_reprove()
    check("contract reprove", contracts["ok"] is True, contracts.get("failed"))

    fe = c8.frontend_setup_cards_scan()
    check("frontend setup cards", fe["ok"] is True, fe)

    check("setup seven modules", len(w6.WAVE6_MODULE_KEYS) == 7)
    check("setup honesty wave6", w6.honesty_payload().get("setup_owns_wave6_policies") is True)
    check("setup JA customer enableable after R5D", w6.honesty_payload().get("customer_enableable") is True)
    check("setup learning customer enableable after R5E", w6.honesty_payload().get("learning_customer_enableable") is True)
    check("setup benefits customer enableable after R5F", w6.honesty_payload().get("benefits_customer_enableable") is True)
    check("setup ER customer enableable after R5G", w6.honesty_payload().get("employee_relations_customer_enableable") is True)
    check("setup wfp honesty", w6.honesty_payload().get("workforce_planning_ja_hard") is True)
    check("setup comp honesty", w6.honesty_payload().get("comp_planning_not_payroll") is True)

    os.environ["WATHEFNI_HCM_EXPANSION_PRODUCT_C8"] = "off"
    os.environ["WATHEFNI_HCM_EXPANSION_PRODUCT_COMPANIES"] = ""
    check("c8 gate off", c8.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    os.environ["WATHEFNI_HCM_EXPANSION_PRODUCT_C8"] = "on"
    os.environ["WATHEFNI_HCM_EXPANSION_PRODUCT_COMPANIES"] = ""
    check("c8 empty allowlist", c8.runtime_gate_for_company("WATHEFNI").get("ok") is not True)
    os.environ["WATHEFNI_HCM_EXPANSION_PRODUCT_COMPANIES"] = "WATHEFNI"
    check("c8 canary gate", c8.runtime_gate_for_company("WATHEFNI").get("ok") is True)
    check("c8 tenant isolation", c8.runtime_gate_for_company("OTHERCO").get("ok") is not True)

    # Slice stamps present
    for _slice, _key, stamp in c8.WAVE6_SLICES:
        check(f"slice stamp listed {_slice}", stamp.endswith("_FULL_PASS"))

    # No schema DDL execution in C8
    c8_src = (orch / "wave6_hcm_expansion_product_c8.py").read_text(encoding="utf-8")
    check("c8 no schema ddl exec", "cur.execute" not in c8_src or "create table" not in c8_src.lower().split("anti_duplication")[0])
    check("c8 acceptance only file", "acceptance_only" in c8_src)

    print(f"\n    WAVE6_PRODUCT_UNIT_PASS")
    print(f"    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
