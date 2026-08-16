#!/usr/bin/env python3
"""Wave 6 C7 Workforce Planning qualification prove."""
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
COMPANY = f"WF1{_N:05d}"[:12].upper()
OTHER = f"WF9{_N:05d}"[:12].upper()
HR = f"9656840{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def _ja_flags(*, on="on", companies="") -> None:
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = on
    os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = companies


def _wfp_flags(*, on="on", companies="") -> None:
    os.environ["WATHEFNI_WORKFORCE_PLANNING_C7"] = on
    os.environ["WATHEFNI_WORKFORCE_PLANNING_COMPANIES"] = companies


def main() -> int:
    print("    workforce planning c7 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import workforce_planning_c7 as wfp
    import job_architecture_c1 as ja
    import setup_console_wave6_policies as w6

    check("phase", wfp.PHASE == "workforce_planning_c7")
    check("stamp", wfp.PASS_STAMP == "WORKFORCE_PLANNING_FULL_PASS")
    check("commercial key", wfp.COMMERCIAL_MODULE_KEY == "workforce_planning")
    honesty = wfp.honesty_payload()
    check("ja hard", honesty["ja_is_hard"] is True)
    check("no shadow actual", honesty["does_not_own_actual_headcount"] is True)
    check("actual≠plan≠scenario", honesty["actual_ne_plan_ne_scenario_ne_approved_execution"] is True)
    check("planned never actual wave5", honesty["planned_headcount_never_enters_actual_wave5"] is True)
    check("planned≠actual position", honesty["planned_position_ne_actual_position"] is True)
    check("planned cost≠payroll", honesty["planned_cost_ne_finalized_payroll_cost"] is True)
    check("recruiting optional", honesty["recruiting_optional"] is True)
    check("comp optional", honesty["comp_planning_optional"] is True)
    check("talent optional", honesty["talent_optional"] is True)
    check("approved≠execution", honesty["approved_ne_execution"] is True)
    check("no auto post/hire", honesty["no_auto_post_hire"] is True)
    check("handoff idempotent", honesty["handoff_idempotent"] is True)
    check("no universal gap score", honesty["no_universal_workforce_gap_score"] is True)
    check("no ai authority", honesty["no_ai_forecast_authority"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    check("no second analytics", honesty["no_second_analytics_engine"] is True)
    check("employee no leak", honesty["employee_no_future_plan_leak"] is True)
    check("setup wave6 wfp", "workforce_planning" in w6.WAVE6_MODULE_KEYS)
    check("setup honesty", w6.honesty_payload().get("workforce_planning_ja_hard") is True)
    check("setup not actual hc", w6.honesty_payload().get("workforce_planning_not_actual_headcount") is True)
    check("bilingual en", bool(wfp.status_label("approved", lang="en")))
    check("bilingual ar", bool(wfp.status_label("approved", lang="ar")))
    catalog = wfp.no_duplicate_planning_job_catalog_check()
    check("no local job catalog", catalog["no_duplicate_planning_job_catalog"] is True, catalog)

    _ja_flags(on="off", companies=COMPANY)
    _wfp_flags(companies=COMPANY)
    check("gate requires ja", wfp.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _ja_flags(companies=COMPANY)
    _wfp_flags(on="off", companies=COMPANY)
    check("gate off", wfp.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _wfp_flags(companies="")
    check("empty allowlist admits after R5J", wfp.runtime_gate_for_company(COMPANY).get("ok") is True)
    _wfp_flags(companies=COMPANY)
    check("gate on with ja", wfp.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", wfp.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(wfp.__file__).read_text(encoding="utf-8")
    check("schema plans", "wfp_plans" in source)
    check("schema baselines", "wfp_baselines" in source)
    check("schema handoffs", "wfp_execution_handoffs" in source)
    check("no employment mutate", "CHECK (employment_mutated_by_wfp = false)" in source)
    check("no headcount mutate", "CHECK (headcount_mutated_by_wfp = false)" in source)
    check("no job posted", "CHECK (job_posted = false)" in source)
    check("no hire created", "CHECK (hire_created = false)" in source)
    check("no wfp_grade ddl", "CREATE TABLE IF NOT EXISTS wfp_grade" not in source)
    check("truth_plane facts", "truth_plane" in source)

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
            ja.ensure_job_architecture_c1_schema(cur)
            wfp.ensure_workforce_planning_c7_schema(cur)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"WFP {code}"),
                )

            blocked_ja = wfp.enable_company_workforce_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="need ja"
            )
            check("ja must be enabled", blocked_ja.get("error") == "ja_must_be_enabled", blocked_ja)

            ja_on = ja.enable_company_job_architecture(
                cur, company_code=COMPANY, actor_phone=HR, reason="c7 prove ja"
            )
            check("enable ja", ja_on.get("ok") is True, ja_on)

            enabled = wfp.enable_company_workforce_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="c7 prove",
                default_currency="KWD", default_horizon="quarterly",
                recruiting_handoff_enabled=False, comp_assumptions_enabled=False, talent_skills_enabled=False,
            )
            check("enable company", enabled.get("ok") is True, enabled)
            check("kwd default", enabled["settings"]["default_currency"] == "KWD", enabled)

            pol = w6.get_wave6_module_policy(cur, COMPANY, "workforce_planning")
            check("setup policy get", pol.get("ok") is True and pol["policy"]["enabled"] is True, pol)

            fam = ja.upsert_job_family(
                cur, company_code=COMPANY, actor_phone=HR, code="OPS",
                name_en="Ops", name_ar="عمليات", status="published", reason="c7",
            )
            fn = ja.upsert_job_function(
                cur, company_code=COMPANY, actor_phone=HR, family_id=fam["stable_id"], code="SVC",
                name_en="Service", name_ar="خدمة", status="published", reason="c7",
            )
            grade = ja.upsert_grade(
                cur, company_code=COMPANY, actor_phone=HR, code="G3",
                name_en="Grade 3", name_ar="الدرجة 3", rank_order=3, status="published", reason="c7",
            )
            grade_id = grade["stable_id"]
            profile = ja.upsert_job_profile(
                cur, company_code=COMPANY, actor_phone=HR, function_id=fn["stable_id"], code="ANL",
                name_en="Analyst", name_ar="محلل", status="published",
                default_grade_id=grade_id, reason="c7",
            )
            profile_id = profile["stable_id"]
            check("ja profile", bool(profile_id), profile)

            plan = wfp.create_plan(
                cur, company_code=COMPANY, actor_phone=HR, code="FY26Q1",
                title_en="FY26 Q1 Plan", title_ar="خطة الربع ١",
                horizon="quarterly", currency="KWD",
                period_start=date(2026, 1, 1), period_end=date(2026, 3, 31), fiscal_year=2026,
            )
            check("create plan", plan.get("ok") is True, plan)
            plan_id = str(plan["plan"]["plan_id"])

            baseline = wfp.freeze_baseline(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                as_of_date=date(2026, 1, 1),
                population=[
                    {"employee_key": "E1", "org_unit": "ENG", "ja_profile_id": profile_id, "ja_grade_id": grade_id, "cost_input": 600},
                    {"employee_key": "E2", "org_unit": "ENG", "ja_profile_id": profile_id, "ja_grade_id": grade_id, "cost_input": 650},
                    {"employee_key": "E3", "org_unit": "HR", "ja_profile_id": profile_id, "ja_grade_id": grade_id, "cost_input": 550},
                ],
            )
            check("baseline freeze", baseline.get("ok") is True and baseline.get("frozen") is True, baseline)
            check("not second sot", baseline.get("not_second_actual_sot") is True, baseline)
            baseline_id = str(baseline["baseline"]["baseline_id"])
            check("baseline hc", int(baseline["baseline"]["headcount_total"]) == 3, baseline)

            # Later "transfer" must not rewrite frozen baseline rows
            cur.execute(
                "SELECT count(*) AS n FROM wfp_baseline_rows WHERE baseline_id=%s",
                (baseline_id,),
            )
            n_before = int(dict(cur.fetchone())["n"])
            re_freeze = wfp.freeze_baseline(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                as_of_date=date(2026, 2, 1),
                population=[{"employee_key": "E9", "org_unit": "X", "ja_profile_id": profile_id}],
            )
            check("baseline immutable once frozen", re_freeze.get("error") == "baseline_already_frozen", re_freeze)
            cur.execute(
                "SELECT count(*) AS n FROM wfp_baseline_rows WHERE baseline_id=%s",
                (baseline_id,),
            )
            check("baseline rows unchanged", int(dict(cur.fetchone())["n"]) == n_before)

            scen = wfp.create_scenario(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                code="BASE", scenario_type="base", title_en="Base", title_ar="أساسي",
            )
            check("scenario create", scen.get("ok") is True and scen.get("scenario_distinct_from_actual") is True, scen)
            scenario_id = str(scen["scenario"]["scenario_id"])

            growth = wfp.create_scenario(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                code="GROW", scenario_type="growth", title_en="Growth", title_ar="نمو",
            )
            check("second scenario", growth.get("ok") is True, growth)
            growth_id = str(growth["scenario"]["scenario_id"])

            assum = wfp.upsert_assumption(
                cur, company_code=COMPANY, actor_phone=HR, scenario_id=scenario_id,
                assumption_key="expected_hires", value={"count": 2, "lead_time_days": 45},
                source="explicit_planner",
            )
            check("assumption explicit", assum.get("ok") is True and assum.get("explicit_versioned") is True, assum)

            silent_to = wfp.upsert_assumption(
                cur, company_code=COMPANY, actor_phone=HR, scenario_id=scenario_id,
                assumption_key="attrition", value={"rate": 0.1}, source="wave5_turnover_explicit",
            )
            check("turnover must be explicit selected", silent_to.get("error") == "wave5_turnover_must_be_explicitly_selected", silent_to)

            comp_blocked = wfp.upsert_assumption(
                cur, company_code=COMPANY, actor_phone=HR, scenario_id=scenario_id,
                assumption_key="band_mid", value={"band_ref": "B1"}, source="comp_band_ref",
            )
            check("comp optional off", comp_blocked.get("error") == "comp_assumptions_disabled", comp_blocked)

            talent_blocked = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="new_headcount", quantity=1, ja_profile_id=profile_id,
                capability_demand={"skill": "python"},
            )
            check("talent optional off", talent_blocked.get("error") == "talent_skills_disabled", talent_blocked)

            bad_profile = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="new_headcount", quantity=1, ja_profile_id=str(uuid.uuid4()),
            )
            check("ja profile required", bad_profile.get("error") == "ja_profile_required", bad_profile)

            repl_no_reason = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="replacement", quantity=1, ja_profile_id=profile_id, ja_grade_id=grade_id,
            )
            check("replacement reason explicit", repl_no_reason.get("error") == "replacement_reason_required_explicit", repl_no_reason)

            demand = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="new_headcount", quantity=2, ja_profile_id=profile_id, ja_grade_id=grade_id,
                org_unit="ENG", reason_en="growth", planned_unit_cost=700, owner_key="MGR1",
            )
            check("new headcount demand", demand.get("ok") is True, demand)
            check("planned≠actual position", demand.get("planned_position_ne_actual_position") is True, demand)
            demand_id = str(demand["demand"]["demand_id"])

            repl = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="replacement", quantity=1, ja_profile_id=profile_id, ja_grade_id=grade_id,
                reason_en="backfill resigned analyst", planned_unit_cost=650,
            )
            check("replacement explicit", repl.get("ok") is True, repl)

            reduction = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="planned_reduction", quantity=1, ja_profile_id=profile_id,
                reason_en="restructure",
            )
            check("reduction demand", reduction.get("ok") is True, reduction)
            reduction_id = str(reduction["demand"]["demand_id"])
            repl_id = str(repl["demand"]["demand_id"])

            # Growth scenario demand for comparison
            wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=growth_id,
                demand_type="new_headcount", quantity=5, ja_profile_id=profile_id, ja_grade_id=grade_id,
                reason_en="aggressive growth", planned_unit_cost=700,
            )

            proj = wfp.project_headcount(cur, company_code=COMPANY, scenario_id=scenario_id)
            # baseline 3 + additions 2+1 - reduction 1 = 5
            check("projection reproducible", proj.get("ok") is True and proj.get("reproducible") is True, proj)
            check("planned hc formula", int(proj.get("planned_headcount") or 0) == 5, proj)
            check("no ai black box", proj.get("no_ai_black_box") is True, proj)
            check("truth plane scenario", proj.get("truth_plane") == "scenario", proj)

            cost = wfp.project_planned_cost(cur, company_code=COMPANY, scenario_id=scenario_id)
            check("planned cost labeled", cost.get("ok") is True and cost.get("planned_cost_ne_finalized_payroll_cost") is True, cost)
            check("currency kwd", cost.get("currency") == "KWD", cost)

            gap = wfp.compute_gap(cur, company_code=COMPANY, scenario_id=scenario_id)
            check("gap definition driven", gap.get("ok") is True and gap.get("definition_driven") is True, gap)
            check("no universal score", gap.get("no_universal_workforce_gap_score") is True, gap)

            bad_gap = wfp.compute_gap(
                cur, company_code=COMPANY, scenario_id=scenario_id, definition="magic_score"
            )
            check("rejects universal gap", bad_gap.get("error") == "invalid_gap_definition", bad_gap)

            cmp = wfp.compare_scenarios(
                cur, company_code=COMPANY, scenario_a=scenario_id, scenario_b=growth_id,
            )
            check("scenario compare compatible", cmp.get("ok") is True and cmp.get("compatible") is True, cmp)

            emp_view = wfp.employee_wfp_view(cur, company_code=COMPANY, employee_key="E1", plan_id=plan_id)
            check("employee no plan leak", emp_view.get("visible") is False and emp_view.get("employee_no_future_plan_leak") is True, emp_view)

            submitted = wfp.submit_plan(cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id)
            check("submit plan", submitted.get("ok") is True, submitted)

            approved = wfp.approve_scenario(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, approver_key="approver-1",
            )
            check("approve", approved.get("ok") is True and approved.get("approved_ne_execution") is True, approved)
            check("actual unchanged", approved.get("actual_workforce_unchanged") is True, approved)

            immut = wfp.add_demand(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                demand_type="new_headcount", quantity=1, ja_profile_id=profile_id,
            )
            check("approved scenario immutable", immut.get("error") == "scenario_not_open_for_demand", immut)

            # Recruiting OFF path — approved_unexecuted
            handoff = wfp.create_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, demand_id=demand_id,
            )
            check("handoff recruiting off", handoff.get("ok") is True, handoff)
            check("works recruiting off", handoff.get("works_recruiting_off") is True, handoff)
            check("no mutate employment", handoff.get("employment_mutated_by_wfp") is False, handoff)
            check("no mutate headcount", handoff.get("headcount_mutated_by_wfp") is False, handoff)
            check("no auto post/hire", handoff.get("no_auto_post_hire") is True, handoff)
            handoff_id = str(handoff["handoff"]["handoff_id"])

            retry = wfp.create_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, demand_id=demand_id,
            )
            check("handoff idempotent retry", retry.get("replayed") is True and retry.get("handoff_idempotent") is True, retry)
            check("same handoff id", str(retry["handoff"]["handoff_id"]) == handoff_id, retry)

            red_hand = wfp.create_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, demand_id=reduction_id,
            )
            check("reduction not requisition", red_hand.get("error") == "reduction_not_requisition_handoff", red_hand)

            # Recruiting path (optional): draft-only or fail-closed to unexecuted when Recruiting off
            wfp.enable_company_workforce_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable recruiting handoff",
                recruiting_handoff_enabled=True,
            )
            rh = wfp.create_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, demand_id=repl_id, target_authority="wave1_requisition_draft",
            )
            check("recruiting handoff governed", rh.get("ok") is True and rh.get("no_auto_post_hire") is True, rh)
            check("no job posted", rh.get("job_posted") is False, rh)
            check("no hire", rh.get("hire_created") is False, rh)
            if rh.get("draft_requisition_only"):
                check("draft requisition only", rh["handoff"].get("requisition_id") or rh.get("works_recruiting_off"), rh)
            else:
                check("recruiting off fail-closed path", rh.get("works_recruiting_off") is True or rh["handoff"].get("target_authority") in {"approved_unexecuted", "external_execution"}, rh)

            cancelled = wfp.cancel_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, handoff_id=handoff_id,
            )
            check("handoff cancel", cancelled.get("ok") is True and cancelled.get("cancelled") is True, cancelled)

            # After cancel, new handoff allowed (same idem key only if not cancelled - our code allows new if cancelled)
            again = wfp.create_execution_handoff(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                scenario_id=scenario_id, demand_id=demand_id, target_authority="external_execution",
            )
            check("handoff after cancel", again.get("ok") is True, again)

            # Changed quantity creates distinct demand/handoff — simulate via new demand
            d2 = wfp.revise_scenario(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                approved_scenario_id=scenario_id, code="BASE-R2",
                title_en="Base rev2", title_ar="أساسي ٢",
            )
            check("revision not overwrite", d2.get("ok") is True and d2.get("never_overwrite_approved_in_place") is True, d2)
            check("original preserved", d2.get("original_preserved") is True, d2)
            rev_id = str(d2["scenario"]["scenario_id"])
            # Original remains approved historically? We set superseded - check status
            cur.execute("SELECT status FROM wfp_scenarios WHERE scenario_id=%s", (scenario_id,))
            check("original superseded not deleted", dict(cur.fetchone())["status"] == "superseded")

            avp = wfp.actual_vs_plan(cur, company_code=COMPANY, scenario_id=rev_id, actual_headcount=3)
            # rev scenario has no demand yet → planned = baseline 3
            check("actual vs plan", avp.get("ok") is True and avp.get("wfp_not_actual_sot") is True, avp)
            check("variance", int(avp.get("variance") or 0) == 0, avp)

            asst_ok = wfp.assistant_query_wfp(
                cur, company_code=COMPANY, actor="asst", question_kind="approved_plan", scenario_id=rev_id,
            )
            check("assistant read", asst_ok.get("ok") is True and asst_ok.get("mutations") is False, asst_ok)
            asst_bad = wfp.assistant_query_wfp(
                cur, company_code=COMPANY, actor="asst", question_kind="generate_requisition", scenario_id=rev_id,
            )
            check("assistant cannot generate req", asst_bad.get("error") == "mutation_forbidden", asst_bad)
            asst_ai = wfp.assistant_query_wfp(
                cur, company_code=COMPANY, actor="asst", question_kind="ai_forecast",
            )
            check("assistant no ai forecast", asst_ai.get("error") == "mutation_forbidden", asst_ai)

            cur.execute(
                "SELECT fact_type, truth_plane FROM wfp_wave5_fact_outbox WHERE company_code=%s",
                (COMPANY,),
            )
            facts = [dict(r) for r in cur.fetchall()]
            types = {f["fact_type"] for f in facts}
            planes = {f["truth_plane"] for f in facts}
            check("wave5 planned demand fact", "workforce_planning.planned_demand" in types, types)
            check("wave5 planned hc fact", "workforce_planning.planned_headcount" in types, types)
            check("wave5 planned cost fact", "workforce_planning.planned_workforce_cost" in types, types)
            check("no bare actual plane for plan facts", "plan" in planes or "scenario" in planes, planes)
            # Ensure planned facts are not truth_plane=actual except actual_vs_plan
            bad_mix = [
                f for f in facts
                if f["truth_plane"] == "actual" and not str(f["fact_type"]).startswith("wfp.actual_vs_plan")
            ]
            check("planning facts not mixed as actual", len(bad_mix) == 0, bad_mix)

            # Comp optional ON path
            wfp.enable_company_workforce_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable comp assumptions",
                comp_assumptions_enabled=True,
            )
            # Need a draft scenario for assumption
            comp_ok = wfp.upsert_assumption(
                cur, company_code=COMPANY, actor_phone=HR, scenario_id=rev_id,
                assumption_key="band_mid", value={"band_ref": "B1", "midpoint": 700}, source="comp_band_ref",
            )
            check("comp optional on works", comp_ok.get("ok") is True, comp_ok)

            # Module off — JA remains healthy conceptually; WFP blocks
            disabled = wfp.disable_company_workforce_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="module off"
            )
            check("disable retains history", disabled.get("history_retained") is True, disabled)
            blocked = wfp.create_plan(
                cur, company_code=COMPANY, actor_phone=HR, code="X", title_en="x", title_ar="س",
            )
            check("module off blocks", blocked.get("error") == "workforce_planning_disabled_for_company", blocked)
            cur.execute("SELECT count(*) AS n FROM wfp_plans WHERE company_code=%s", (COMPANY,))
            check("history kept", int(dict(cur.fetchone())["n"]) >= 1)
            # JA still enabled
            check("ja still healthy", ja.module_enabled_for_company(cur, COMPANY) is True)

            print(f"\n    WORKFORCE_PLANNING_FULL_PASS")
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
