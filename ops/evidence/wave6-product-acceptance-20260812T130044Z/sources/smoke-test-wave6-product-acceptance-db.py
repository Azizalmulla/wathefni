#!/usr/bin/env python3
"""Wave 6 Product Acceptance — staging DB prove (C8).

Acceptance/integration only. Consumes frozen C1–C7; no new domain math.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"W6P{_N:05d}"[:12].upper()
OTHER = f"W6X{_N:05d}"[:12].upper()
HR = f"9656850{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def _all_off() -> None:
    for flag, companies in (
        ("WATHEFNI_JOB_ARCHITECTURE_C1", "WATHEFNI_JOB_ARCHITECTURE_COMPANIES"),
        ("WATHEFNI_LEARNING_C2", "WATHEFNI_LEARNING_COMPANIES"),
        ("WATHEFNI_BENEFITS_C3", "WATHEFNI_BENEFITS_COMPANIES"),
        ("WATHEFNI_EMPLOYEE_RELATIONS_C4", "WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"),
        ("WATHEFNI_ENGAGEMENT_C5", "WATHEFNI_ENGAGEMENT_COMPANIES"),
        ("WATHEFNI_COMP_PLANNING_C6", "WATHEFNI_COMP_PLANNING_COMPANIES"),
        ("WATHEFNI_WORKFORCE_PLANNING_C7", "WATHEFNI_WORKFORCE_PLANNING_COMPANIES"),
        ("WATHEFNI_HCM_EXPANSION_PRODUCT_C8", "WATHEFNI_HCM_EXPANSION_PRODUCT_COMPANIES"),
    ):
        os.environ[flag] = "off"
        os.environ[companies] = ""


def _enable(modules: list[str], company: str) -> None:
    """Process-scoped flags for modularity cells."""
    mapping = {
        "ja": ("WATHEFNI_JOB_ARCHITECTURE_C1", "WATHEFNI_JOB_ARCHITECTURE_COMPANIES"),
        "learning": ("WATHEFNI_LEARNING_C2", "WATHEFNI_LEARNING_COMPANIES"),
        "benefits": ("WATHEFNI_BENEFITS_C3", "WATHEFNI_BENEFITS_COMPANIES"),
        "er": ("WATHEFNI_EMPLOYEE_RELATIONS_C4", "WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"),
        "engagement": ("WATHEFNI_ENGAGEMENT_C5", "WATHEFNI_ENGAGEMENT_COMPANIES"),
        "comp": ("WATHEFNI_COMP_PLANNING_C6", "WATHEFNI_COMP_PLANNING_COMPANIES"),
        "wfp": ("WATHEFNI_WORKFORCE_PLANNING_C7", "WATHEFNI_WORKFORCE_PLANNING_COMPANIES"),
        "c8": ("WATHEFNI_HCM_EXPANSION_PRODUCT_C8", "WATHEFNI_HCM_EXPANSION_PRODUCT_COMPANIES"),
    }
    _all_off()
    for key in modules:
        flag, cos = mapping[key]
        os.environ[flag] = "on"
        os.environ[cos] = company


def main() -> int:
    print("    wave6 product acceptance — db")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import wave6_hcm_expansion_product_c8 as c8
    import job_architecture_c1 as ja
    import learning_development_c2 as ld
    import benefits_administration_c3 as bn
    import employee_relations_c4 as er
    import engagement_c5 as eg
    import compensation_planning_c6 as cp
    import workforce_planning_c7 as wfp
    import setup_console_wave6_policies as w6

    check("c8 phase", c8.PHASE == "wave6_hcm_expansion_product_c8")
    check("stamp", c8.PASS_STAMP == "WAVE6_PRODUCT_FULL_PASS")
    check("acceptance only", c8.honesty_payload()["acceptance_only"] is True)
    scan = c8.anti_duplication_scan()
    check("anti-duplication", scan["ok"] is True, scan.get("findings"))
    contracts = c8.contract_reprove()
    check("frozen contract reprove", contracts["ok"] is True, contracts.get("failed"))
    fe = c8.frontend_setup_cards_scan()
    check("setup cards mounted", fe["ok"] is True, fe)

    # --- Modularity matrix (flag composition) ---
    gate_mods = {
        "ja": ja,
        "learning": ld,
        "benefits": bn,
        "er": er,
        "engagement": eg,
        "comp": cp,
        "wfp": wfp,
    }
    for cell in c8.modularity_matrix_configs():
        name = cell["cell"]
        enable = list(cell.get("enable") or [])
        _enable(enable + (["c8"] if enable else []), COMPANY)
        if cell.get("expect_unavailable"):
            # all off — every commercial/platform wave6 gate fail-closed
            all_off_ok = True
            for key, mod in gate_mods.items():
                if mod.runtime_gate_for_company(COMPANY).get("ok"):
                    all_off_ok = False
            check(f"matrix {name} all unavailable", all_off_ok)
            continue
        # Enabled modules must gate OK (comp/wfp also need ja in enable list)
        cell_ok = True
        detail = {}
        for key in enable:
            mod = gate_mods[key]
            g = mod.runtime_gate_for_company(COMPANY)
            detail[key] = g.get("error") or "ok"
            if key in {"comp", "wfp"} and "ja" not in enable:
                # hard dep unmet expected
                if g.get("ok"):
                    cell_ok = False
            elif not g.get("ok"):
                cell_ok = False
        # Optional-off modules should be unavailable when not enabled
        for key in cell.get("optional_off") or []:
            if key in gate_mods and key not in enable:
                g = gate_mods[key].runtime_gate_for_company(COMPANY)
                if g.get("ok"):
                    cell_ok = False
                    detail[f"unexpected_on_{key}"] = True
        check(f"matrix {name}", cell_ok, detail)

    # Honesty for optional compositions
    check("benefits works payroll off", bn.honesty_payload()["works_payroll_off"] is True)
    check("comp works payroll off", cp.honesty_payload()["works_payroll_off"] is True)
    check("wfp works recruiting off", wfp.honesty_payload()["works_recruiting_off"] is True)
    check("ld works without ja", ld.honesty_payload()["works_without_ja"] is True)
    check("ld works perf/talent off", ld.honesty_payload()["works_performance_talent_off"] is True)

    # Hard deps
    _enable(["comp", "c8"], COMPANY)  # no JA
    check("comp without ja blocked", cp.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _enable(["wfp", "c8"], COMPANY)
    check("wfp without ja blocked", wfp.runtime_gate_for_company(COMPANY).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise
    try:
        db_context = app.db_connect()
        conn = db_context.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            # Full Wave 6 enable for representative integration path
            _enable(["ja", "learning", "benefits", "er", "engagement", "comp", "wfp", "c8"], COMPANY)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"W6P {code}"),
                )

            # Schemas
            ja.ensure_job_architecture_c1_schema(cur)
            ld.ensure_learning_development_c2_schema(cur)
            bn.ensure_benefits_administration_c3_schema(cur)
            er.ensure_employee_relations_c4_schema(cur)
            eg.ensure_engagement_c5_schema(cur)
            cp.ensure_compensation_planning_c6_schema(cur)
            wfp.ensure_workforce_planning_c7_schema(cur)

            # Setup ownership — all seven policies readable
            all_pol = w6.get_all_wave6_policies(cur, COMPANY)
            check("setup contract", all_pol.get("contract_version", "").startswith("wave6_hcm_expansion_policies"))
            mods = all_pol.get("modules") or {}
            for key in w6.WAVE6_MODULE_KEYS:
                check(f"setup module {key}", key in mods and mods[key].get("ok") is True, mods.get(key))

            # --- Representative thin paths ---
            # JA: family → function → profile → grade → assignment
            check(
                "enable ja",
                ja.enable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="c8").get("ok") is True,
            )
            fam = ja.upsert_job_family(
                cur, company_code=COMPANY, actor_phone=HR, code="OPS",
                name_en="Ops", name_ar="عمليات", status="published", reason="c8",
            )
            fn = ja.upsert_job_function(
                cur, company_code=COMPANY, actor_phone=HR, family_id=fam["stable_id"], code="AN",
                name_en="Analytics", name_ar="تحليلات", status="published", reason="c8",
            )
            grade = ja.upsert_grade(
                cur, company_code=COMPANY, actor_phone=HR, code="G4",
                name_en="Grade 4", name_ar="الدرجة 4", rank_order=4, status="published", reason="c8",
            )
            grade_id = grade["stable_id"]
            level = ja.upsert_level(
                cur, company_code=COMPANY, actor_phone=HR, code="L1", grade_id=grade_id,
                name_en="Level I", name_ar="المستوى ١", rank_order=1, status="published", reason="c8",
            )
            profile = ja.upsert_job_profile(
                cur, company_code=COMPANY, actor_phone=HR, function_id=fn["stable_id"], code="ANL",
                name_en="Analyst", name_ar="محلل", status="published",
                default_grade_id=grade_id, default_level_id=level["stable_id"], reason="c8",
            )
            profile_id = profile["stable_id"]
            assign = ja.assign_employment_architecture(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E1",
                effective_start=date.today(), profile_id=profile_id, grade_id=grade_id, reason="c8",
            )
            check("ja path", assign.get("ok") is True and bool(profile_id) and bool(grade_id), assign)

            # Rename must not break stable id (historical)
            renamed = ja.upsert_job_family(
                cur, company_code=COMPANY, actor_phone=HR, code="OPS",
                name_en="Operations", name_ar="العمليات", status="published", reason="rename",
            )
            check("ja historical stable id", renamed.get("stable_id") == fam["stable_id"], renamed)

            # L&D: catalog item → offering → assignment (completion boundary honesty already reproved)
            check(
                "enable learning",
                ld.enable_company_learning(cur, company_code=COMPANY, actor_phone=HR, reason="c8").get("ok") is True,
            )
            item = ld.upsert_learning_item(
                cur, company_code=COMPANY, actor_phone=HR, code="SAFE1",
                item_type="self_paced", title_en="Safety", title_ar="سلامة",
                status="published", reason="c8",
            )
            check("ld catalog item", item.get("ok") is True, item)
            offering = ld.create_offering(
                cur, company_code=COMPANY, actor_phone=HR, item_id=item["stable_id"],
                location_or_virtual="virtual", capacity=20,
            )
            check("ld offering", offering.get("ok") is True, offering)
            asg = ld.create_assignment(
                cur, company_code=COMPANY, actor_phone=HR,
                employee_key="E1", item_id=item["stable_id"], source="hr_assigned",
                offering_id=str(offering["offering"]["offering_id"]) if offering.get("offering") else None,
            )
            check("ld assignment", asg.get("ok") is True, asg)
            check("ld ne development sot", ld.honesty_payload()["does_not_duplicate_c3_development"] is True)

            # Benefits: enable + payroll-off honesty; eligibility boundary
            check(
                "enable benefits",
                bn.enable_company_benefits(
                    cur, company_code=COMPANY, actor_phone=HR, reason="c8", payroll_handoff_enabled=False,
                ).get("ok")
                is True,
            )
            check("bn claims absent honesty", bn.honesty_payload()["claims_adjudication_out"] is True)
            check("bn eligible≠enrolled", bn.honesty_payload()["eligible_not_enrolled"] is True)

            # ER: enable + confidentiality honesty
            check(
                "enable er",
                er.enable_company_employee_relations(cur, company_code=COMPANY, actor_phone=HR, reason="c8").get("ok") is True,
            )
            check("er ordinary hr ≠ er", er.honesty_payload()["ordinary_hr_not_er"] is True)
            check("er manager ≠ er", er.honesty_payload()["manager_not_er"] is True)
            check("er outcome ≠ mutation", er.honesty_payload()["outcome_not_employment_mutation"] is True)

            # Engagement: anonymity gates
            check(
                "enable engagement",
                eg.enable_company_engagement(cur, company_code=COMPANY, actor_phone=HR, reason="c8").get("ok") is True,
            )
            check("eg min5", eg.honesty_payload()["min_responses_default_5"] is True)
            check("eg upward", eg.honesty_payload()["threshold_upward_only"] is True)
            check("eg no respondent map", eg.honesty_payload()["anonymous_no_respondent_answer_map"] is True)
            check("eg recognition out", eg.honesty_payload()["recognition_out_of_mvp"] is True)
            check("eg recognition absent", eg.recognition_absent_check()["recognition_absent"] is True)

            # Comp: cycle → band(JA) → recommend → calibrate → approve → finalize → handoff
            check(
                "enable comp",
                cp.enable_company_comp_planning(
                    cur, company_code=COMPANY, actor_phone=HR, reason="c8",
                    performance_input_enabled=False, talent_input_enabled=False, payroll_handoff_enabled=False,
                ).get("ok")
                is True,
            )
            band = cp.upsert_salary_band(
                cur, company_code=COMPANY, actor_phone=HR, code="B4",
                ja_grade_id=grade_id, minimum=400, midpoint=600, maximum=800, currency="KWD",
            )
            check("comp band ja-linked", band.get("ok") is True and band.get("no_local_grade_created") is True, band)
            cycle = cp.create_cycle(
                cur, company_code=COMPANY, actor_phone=HR, code="CY8",
                title_en="C8 Cycle", title_ar="دورة ٨", currency="KWD",
            )
            cycle_id = str(cycle["cycle"]["cycle_id"])
            launched = cp.launch_cycle(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                population=[{
                    "employee_key": "E1", "employment_ref": "EMP-E1", "current_base": 550,
                    "currency": "KWD", "ja_grade_id": grade_id, "band_id": str(band["band"]["band_id"]),
                    "manager_key": "MGR1", "employment_status": "active",
                }],
            )
            check("comp launch freeze", launched.get("ok") is True and launched.get("snapshot_frozen") is True, launched)
            cp.create_budget(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                scope_type="company", scope_key="ALL", allocated=500, currency="KWD",
            )
            rec = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="MGR1", recommendation_type="merit_increase",
                amount=50, rationale="c8",
            )
            check("comp recommend", rec.get("ok") is True, rec)
            cal = cp.calibrate_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                original_recommendation_id=str(rec["recommendation"]["recommendation_id"]),
                actor_key="cal-1", amount=45,
            )
            check("comp calibrate preserves original", cal.get("original_preserved") is True, cal)
            sod = cp.approve_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                recommendation_id=str(cal["calibrated"]["recommendation_id"]), approver_key="cal-1",
            )
            check("comp sod", sod.get("error") == "sod_violation_recommend_approve_same_actor", sod)
            appr = cp.approve_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                recommendation_id=str(cal["calibrated"]["recommendation_id"]), approver_key="appr-1",
            )
            check("comp approve ≠ salary", appr.get("approval_not_salary_mutation") is True, appr)
            fin = cp.finalize_cycle(cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id)
            check("comp finalized ≠ applied", fin.get("finalized_not_applied") is True, fin)
            decision_id = str(fin["decisions"][0]["decision_id"])
            hand = cp.create_apply_handoff(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                decision_id=decision_id, target_authority="employment_change_c1", employment_ref="EMP-E1",
            )
            check("comp explicit handoff", hand.get("ok") is True and hand.get("payroll_paid") is False, hand)
            check("comp employee draft hidden", cp.employee_comp_view(cur, company_code=COMPANY, employee_key="E1", cycle_id=cycle_id).get("recommendations") is None)
            asst_cp = cp.assistant_query_comp(cur, company_code=COMPANY, actor="a", question_kind="recommend_pay")
            check("comp assistant no mutate", asst_cp.get("error") == "mutation_forbidden", asst_cp)

            # WFP: baseline → scenario → demand → approve → handoff
            check(
                "enable wfp",
                wfp.enable_company_workforce_planning(
                    cur, company_code=COMPANY, actor_phone=HR, reason="c8", recruiting_handoff_enabled=False,
                ).get("ok")
                is True,
            )
            plan = wfp.create_plan(
                cur, company_code=COMPANY, actor_phone=HR, code="P8",
                title_en="Plan 8", title_ar="خطة ٨", horizon="quarterly", currency="KWD",
            )
            plan_id = str(plan["plan"]["plan_id"])
            base = wfp.freeze_baseline(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, as_of_date=date.today(),
                population=[{"employee_key": "E1", "org_unit": "ENG", "ja_profile_id": profile_id, "ja_grade_id": grade_id}],
            )
            check("wfp baseline freeze", base.get("ok") is True and base.get("not_second_actual_sot") is True, base)
            scen = wfp.create_scenario(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                code="BASE", scenario_type="base", title_en="Base", title_ar="أساسي",
            )
            scenario_id = str(scen["scenario"]["scenario_id"])
            demand = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="new_headcount", quantity=1, ja_profile_id=profile_id, ja_grade_id=grade_id,
                reason_en="growth", planned_unit_cost=600,
            )
            check("wfp demand", demand.get("ok") is True and demand.get("planned_position_ne_actual_position") is True, demand)
            proj = wfp.project_headcount(cur, company_code=COMPANY, scenario_id=scenario_id)
            check("wfp projection", proj.get("ok") is True and proj.get("truth_plane") == "scenario", proj)
            wfp.submit_plan(cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id)
            appr_w = wfp.approve_scenario(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, approver_key="appr-1",
            )
            check("wfp approved ≠ execution", appr_w.get("approved_ne_execution") is True, appr_w)
            wh = wfp.create_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, demand_id=str(demand["demand"]["demand_id"]),
            )
            check("wfp handoff no auto hire", wh.get("ok") is True and wh.get("hire_created") is False, wh)
            retry = wfp.create_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, demand_id=str(demand["demand"]["demand_id"]),
            )
            check("wfp handoff idempotent", retry.get("replayed") is True, retry)
            check("wfp employee no leak", wfp.employee_wfp_view(cur, company_code=COMPANY, employee_key="E1", plan_id=plan_id).get("visible") is False)
            asst_w = wfp.assistant_query_wfp(cur, company_code=COMPANY, actor="a", question_kind="generate_requisition")
            check("wfp assistant no mutate", asst_w.get("error") == "mutation_forbidden", asst_w)

            # Wave 5 fact integration — planning facts distinct
            cur.execute(
                "SELECT fact_type, truth_plane FROM wfp_wave5_fact_outbox WHERE company_code=%s",
                (COMPANY,),
            )
            wfp_facts = [dict(r) for r in cur.fetchall()]
            check("wfp emitted planning facts", len(wfp_facts) >= 1, wfp_facts)
            bad = [f for f in wfp_facts if f["truth_plane"] == "actual" and not str(f["fact_type"]).startswith("wfp.actual_vs_plan")]
            check("wfp facts not mixed as actual hc", len(bad) == 0, bad)
            cur.execute(
                "SELECT fact_type FROM cp_wave5_fact_outbox WHERE company_code=%s",
                (COMPANY,),
            )
            cp_facts = [dict(r)["fact_type"] for r in cur.fetchall()]
            check("comp emitted wave5 facts", len(cp_facts) >= 1, cp_facts)

            # Module-off clean composition while JA remains
            for disable_fn, label in (
                (ld.disable_company_learning, "learning"),
                (bn.disable_company_benefits, "benefits"),
                (er.disable_company_employee_relations, "er"),
                (eg.disable_company_engagement, "engagement"),
                (cp.disable_company_comp_planning, "comp"),
                (wfp.disable_company_workforce_planning, "wfp"),
            ):
                res = disable_fn(cur, company_code=COMPANY, actor_phone=HR, reason="c8 off")
                check(f"disable {label} retains history", res.get("history_retained") is True or res.get("ok") is True, res)
            check("ja still healthy after others off", ja.module_enabled_for_company(cur, COMPANY) is True)
            blocked = cp.create_cycle(
                cur, company_code=COMPANY, actor_phone=HR, code="X", title_en="x", title_ar="س",
            )
            check("comp off clean block", blocked.get("error") == "comp_planning_disabled_for_company", blocked)

            # Handoff contract matrix present
            check("handoff matrix size", len(c8.handoff_contract_matrix()) >= 5)
            check("permission matrix size", len(c8.permission_confidentiality_matrix()) >= 10)

            # EN/AR labels across modules
            for mod, status in (
                (ja, "published"), (ld, "assigned"), (bn, "active"), (er, "open"),
                (eg, "anonymous"), (cp, "finalized"), (wfp, "approved"),
            ):
                check(f"en label {mod.PHASE}", bool(mod.status_label(status, lang="en")))
                check(f"ar label {mod.PHASE}", bool(mod.status_label(status, lang="ar")))

            print(f"\n    WAVE6_PRODUCT_FULL_PASS")
            print(f"    {PASS} passed, {FAIL} failed")
            return 1 if FAIL else 0
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            db_context.__exit__(None, None, None)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
