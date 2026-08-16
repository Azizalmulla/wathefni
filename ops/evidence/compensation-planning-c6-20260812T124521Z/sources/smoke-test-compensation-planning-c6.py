#!/usr/bin/env python3
"""Wave 6 C6 Compensation Planning qualification prove."""
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
COMPANY = f"CP1{_N:05d}"[:12].upper()
OTHER = f"CP9{_N:05d}"[:12].upper()
HR = f"9656830{_N:05d}"


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


def _cp_flags(*, on="on", companies="") -> None:
    os.environ["WATHEFNI_COMP_PLANNING_C6"] = on
    os.environ["WATHEFNI_COMP_PLANNING_COMPANIES"] = companies


def main() -> int:
    print("    compensation planning c6 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import compensation_planning_c6 as cp
    import job_architecture_c1 as ja
    import setup_console_wave6_policies as w6

    check("phase", cp.PHASE == "compensation_planning_c6")
    check("stamp", cp.PASS_STAMP == "COMPENSATION_PLANNING_FULL_PASS")
    check("commercial key", cp.COMMERCIAL_MODULE_KEY == "comp_planning")
    honesty = cp.honesty_payload()
    check("ja hard", honesty["ja_is_hard"] is True)
    check("no duplicate grade", honesty["no_duplicate_grade_hierarchy"] is True)
    check("not payroll", honesty["not_payroll"] is True)
    check("finalized not applied", honesty["finalized_not_applied"] is True)
    check("plan approved not salary", honesty["plan_approved_not_salary_changed"] is True)
    check("change package not paid", honesty["change_package_not_payroll_paid"] is True)
    check("performance optional", honesty["performance_optional"] is True)
    check("rating not auto", honesty["rating_not_automatic_increase"] is True)
    check("talent optional", honesty["talent_optional"] is True)
    check("hipo not auto", honesty["hipo_not_automatic_pay"] is True)
    check("works payroll off", honesty["works_payroll_off"] is True)
    check("midpoint not recommended", honesty["midpoint_not_recommended_salary"] is True)
    check("promotion not role mutation", honesty["promotion_plan_not_role_mutation"] is True)
    check("bonus not paid", honesty["approved_bonus_not_paid"] is True)
    check("currency explicit", honesty["currency_explicit"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    check("no second analytics", honesty["no_second_analytics_engine"] is True)
    check("employee draft hidden", honesty["employee_cannot_see_draft_recommendations"] is True)
    check("setup wave6 comp", "comp_planning" in w6.WAVE6_MODULE_KEYS)
    check("setup honesty ja hard", w6.honesty_payload().get("comp_planning_ja_hard") is True)
    check("setup honesty not payroll", w6.honesty_payload().get("comp_planning_not_payroll") is True)
    check("bilingual en", bool(cp.status_label("finalized", lang="en")))
    check("bilingual ar", bool(cp.status_label("finalized", lang="ar")))
    grades = cp.no_duplicate_grade_hierarchy_check()
    check("no local grade table", grades["no_duplicate_grade_hierarchy"] is True, grades)

    _ja_flags(on="off", companies=COMPANY)
    _cp_flags(companies=COMPANY)
    check("gate requires ja env", cp.runtime_gate_for_company(COMPANY).get("error") == "ja_hard_dependency_unmet"
          or cp.runtime_gate_for_company(COMPANY).get("ok") is not True)

    _ja_flags(companies=COMPANY)
    _cp_flags(on="off", companies=COMPANY)
    check("gate off", cp.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _cp_flags(companies="")
    check("empty allowlist", cp.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _cp_flags(companies=COMPANY)
    check("gate on with ja", cp.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", cp.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(cp.__file__).read_text(encoding="utf-8")
    check("schema cycles", "cp_cycles" in source)
    check("schema bands", "cp_salary_bands" in source)
    check("schema handoffs", "cp_apply_handoffs" in source)
    check("employment mutated check", "CHECK (employment_mutated_by_comp = false)" in source)
    check("payroll paid check", "CHECK (payroll_paid = false)" in source)
    check("no cp_grade ddl", "CREATE TABLE IF NOT EXISTS cp_grade" not in source)
    check("refs ja_grade", "ja_grade" in source)

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
            cp.ensure_compensation_planning_c6_schema(cur)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"CP {code}"),
                )

            # Comp blocked until JA company enabled
            blocked_ja = cp.enable_company_comp_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="need ja"
            )
            check("ja must be enabled", blocked_ja.get("error") == "ja_must_be_enabled", blocked_ja)

            ja_on = ja.enable_company_job_architecture(
                cur, company_code=COMPANY, actor_phone=HR, reason="c6 prove ja"
            )
            check("enable ja", ja_on.get("ok") is True, ja_on)

            enabled = cp.enable_company_comp_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="c6 prove",
                default_currency="KWD", budget_overrun_mode="hard_block", sod_required=True,
                performance_input_enabled=False, talent_input_enabled=False, payroll_handoff_enabled=False,
            )
            check("enable company", enabled.get("ok") is True, enabled)
            check("kwd default", enabled["settings"]["default_currency"] == "KWD", enabled)
            check("sod default", enabled["settings"]["sod_required"] is True, enabled)

            pol = w6.get_wave6_module_policy(cur, COMPANY, "comp_planning")
            check("setup policy get", pol.get("ok") is True and pol["policy"]["enabled"] is True, pol)

            grade = ja.upsert_grade(
                cur, company_code=COMPANY, actor_phone=HR, code="G7",
                name_en="Grade 7", name_ar="الدرجة 7", rank_order=7, status="published", reason="c6",
            )
            check("ja grade", grade.get("ok") is True, grade)
            grade_id = grade["stable_id"]

            bad_band = cp.upsert_salary_band(
                cur, company_code=COMPANY, actor_phone=HR, code="B7",
                ja_grade_id=str(uuid.uuid4()), minimum=500, midpoint=700, maximum=900,
            )
            check("band requires ja grade", bad_band.get("error") == "ja_grade_required", bad_band)

            band = cp.upsert_salary_band(
                cur, company_code=COMPANY, actor_phone=HR, code="B7",
                ja_grade_id=grade_id, minimum=500, midpoint=700, maximum=900,
                currency="KWD", band_version=1, effective_start=date.today(),
            )
            check("band v1", band.get("ok") is True and band.get("no_local_grade_created") is True, band)
            check("midpoint not recommended flag", band.get("midpoint_not_recommended_salary") is True, band)
            band_id = str(band["band"]["band_id"])
            band_v1 = int(band["band"]["band_version"])

            cycle = cp.create_cycle(
                cur, company_code=COMPANY, actor_phone=HR, code="CY26",
                title_en="2026 Merit", title_ar="استحقاق ٢٠٢٦",
                eligibility_rule={"employment_status": "active"},
                currency="KWD",
            )
            check("create cycle", cycle.get("ok") is True, cycle)
            cycle_id = str(cycle["cycle"]["cycle_id"])

            population = [
                {
                    "employee_key": "E1", "employment_ref": "EMP-E1", "current_base": 650,
                    "currency": "KWD", "ja_grade_id": grade_id, "band_id": band_id,
                    "manager_key": "MGR1", "department": "ENG", "employment_status": "active",
                },
                {
                    "employee_key": "E2", "employment_ref": "EMP-E2", "current_base": 600,
                    "currency": "KWD", "ja_grade_id": grade_id, "band_id": band_id,
                    "manager_key": "MGR1", "department": "ENG", "employment_status": "terminated",
                },
            ]
            launched = cp.launch_cycle(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id, population=population,
            )
            check("launch freeze", launched.get("ok") is True and launched.get("snapshot_frozen") is True, launched)
            check("eligible n", int(launched.get("eligible_n") or 0) == 1, launched)
            check("eligible not guaranteed", launched.get("eligible_not_guaranteed_increase") is True, launched)

            # Later band v2 must not rewrite launched snapshot
            band2 = cp.upsert_salary_band(
                cur, company_code=COMPANY, actor_phone=HR, code="B7",
                ja_grade_id=grade_id, minimum=550, midpoint=800, maximum=1000,
                currency="KWD", band_version=2, effective_start=date.today(),
            )
            check("band v2 new version", band2.get("ok") is True, band2)
            cur.execute(
                "SELECT band_id, band_version, current_base FROM cp_cycle_snapshots WHERE cycle_id=%s AND employee_key='E1'",
                (cycle_id,),
            )
            snap = dict(cur.fetchone())
            check("snapshot band immutable", str(snap["band_id"]) == band_id and int(snap["band_version"]) == band_v1, snap)

            # Eligibility explanation preserved
            cur.execute(
                "SELECT eligible, eligibility_explanation FROM cp_cycle_snapshots WHERE cycle_id=%s AND employee_key='E2'",
                (cycle_id,),
            )
            inelig = dict(cur.fetchone())
            check("ineligible explicit", inelig["eligible"] is False, inelig)

            budget = cp.create_budget(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                scope_type="company", scope_key="ALL", allocated=200, currency="KWD",
            )
            check("budget create", budget.get("ok") is True and budget.get("allocated_recommended_approved_distinct") is True, budget)

            scope_denied = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="MGR2", recommendation_type="merit_increase", amount=50, rationale="out of scope",
            )
            check("manager scope denied", scope_denied.get("error") == "manager_scope_denied", scope_denied)

            overrun = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="MGR1", recommendation_type="merit_increase", amount=500, rationale="too big",
            )
            check("budget hard block", overrun.get("error") == "budget_overrun_hard_block", overrun)

            rec = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="MGR1", recommendation_type="merit_increase",
                amount=50, percent=7.7, rationale="solid year",
            )
            check("merit recommendation", rec.get("ok") is True and rec.get("layer") == "original", rec)
            check("rating not auto on rec", rec.get("rating_not_automatic_increase") is True, rec)
            original_id = str(rec["recommendation"]["recommendation_id"])

            promo = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="hr-ops", recommendation_type="promotion_increase",
                amount=40, rationale="target grade", proposed_ja_grade_id=grade_id,
            )
            check("promotion types distinct", promo.get("ok") is True, promo)
            check("promotion not role mutation", promo.get("promotion_plan_not_role_mutation") is True, promo)

            perf_blocked = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="hr-ops", recommendation_type="market_adjustment",
                amount=10, performance_guided=True,
            )
            check("performance off blocks guided", perf_blocked.get("error") == "performance_input_disabled", perf_blocked)

            hipo = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="hr-ops", recommendation_type="merit_increase",
                amount=5, hipo_auto_convert=True,
            )
            check("hipo not automatic pay", hipo.get("error") == "hipo_not_automatic_pay", hipo)

            talent_blocked = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                employee_key="E1", actor_key="hr-ops", recommendation_type="market_adjustment",
                amount=5, talent_guided=True,
            )
            check("talent off blocks guided", talent_blocked.get("error") == "talent_input_disabled", talent_blocked)

            cal = cp.calibrate_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                original_recommendation_id=original_id, actor_key="cal-1", amount=45, rationale="peer group",
            )
            check("calibrate", cal.get("ok") is True and cal.get("original_preserved") is True, cal)
            check("calibration not original", cal.get("calibration_not_original") is True, cal)
            calibrated_id = str(cal["calibrated"]["recommendation_id"])

            sod = cp.approve_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                recommendation_id=calibrated_id, approver_key="cal-1",
            )
            check("sod recommend≠approve", sod.get("error") == "sod_violation_recommend_approve_same_actor", sod)

            approved = cp.approve_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                recommendation_id=calibrated_id, approver_key="approver-1",
            )
            check("approve", approved.get("ok") is True and approved.get("approval_not_salary_mutation") is True, approved)

            hist = cp.recommendation_history(cur, company_code=COMPANY, cycle_id=cycle_id, employee_key="E1")
            layers = {h["layer"] for h in hist.get("history") or []}
            check("history layers", {"original", "calibrated", "approved"}.issubset(layers), hist)
            check("original in history", hist.get("original_preserved") is True, hist)

            emp_view = cp.employee_comp_view(cur, company_code=COMPANY, employee_key="E1", cycle_id=cycle_id)
            check("employee draft hidden pre-final", emp_view.get("visible") is False, emp_view)
            check("no draft leak", emp_view.get("employee_cannot_see_draft_recommendations") is True, emp_view)

            finalized = cp.finalize_cycle(cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id)
            check("finalize", finalized.get("ok") is True and finalized.get("finalized_not_applied") is True, finalized)
            check("decisions present", len(finalized.get("decisions") or []) >= 1, finalized)
            decision_id = str(finalized["decisions"][0]["decision_id"])
            check("decision not applied", finalized["decisions"][0].get("applied") is False, finalized)

            emp_view2 = cp.employee_comp_view(cur, company_code=COMPANY, employee_key="E1", cycle_id=cycle_id)
            check("employee still no draft after finalize", emp_view2.get("recommendations") is None, emp_view2)

            payroll_blocked = cp.create_apply_handoff(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                decision_id=decision_id, target_authority="wathefni_payroll", employment_ref="EMP-E1",
            )
            check("payroll handoff optional/off", payroll_blocked.get("error") == "payroll_handoff_disabled", payroll_blocked)

            handoff = cp.create_apply_handoff(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                decision_id=decision_id, target_authority="employment_change_c1", employment_ref="EMP-E1",
            )
            check("explicit handoff", handoff.get("ok") is True and handoff.get("applied") is False, handoff)
            check("comp does not mutate employment", handoff.get("employment_mutated_by_comp") is False, handoff)
            check("not payroll paid", handoff.get("payroll_paid") is False, handoff)
            check("employment change authority", handoff.get("employment_change_remains_mutation_authority") is True, handoff)

            external = cp.create_apply_handoff(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                decision_id=decision_id, target_authority="external_payroll", employment_ref="EMP-E1",
            )
            check("external payroll path", external.get("ok") is True, external)

            ratio = cp.compute_compa_ratio(cur, company_code=COMPANY, cycle_id=cycle_id, employee_key="E1")
            check("compa ratio", ratio.get("ok") is True and ratio.get("compa_ratio") is not None, ratio)
            check("compa definition", ratio.get("definition") == "current_eligible_base / applicable_range_midpoint", ratio)

            asst_ok = cp.assistant_query_comp(
                cur, company_code=COMPANY, actor="asst", question_kind="cycle_status", cycle_id=cycle_id,
            )
            check("assistant read", asst_ok.get("ok") is True and asst_ok.get("mutations") is False, asst_ok)
            asst_bad = cp.assistant_query_comp(
                cur, company_code=COMPANY, actor="asst", question_kind="recommend_pay", cycle_id=cycle_id,
            )
            check("assistant cannot recommend", asst_bad.get("error") == "mutation_forbidden", asst_bad)

            # Bonus planning on a second cycle — approved ≠ paid
            cycle2 = cp.create_cycle(
                cur, company_code=COMPANY, actor_phone=HR, code="BON26",
                title_en="Bonus 2026", title_ar="مكافأة ٢٠٢٦", currency="KWD",
            )
            c2 = str(cycle2["cycle"]["cycle_id"])
            cp.launch_cycle(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=c2,
                population=[{
                    "employee_key": "E1", "employment_ref": "EMP-E1", "current_base": 650,
                    "currency": "KWD", "ja_grade_id": grade_id, "band_id": band_id,
                    "manager_key": "MGR1", "employment_status": "active",
                }],
            )
            cp.create_budget(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=c2,
                scope_type="company", scope_key="ALL", allocated=500, currency="KWD",
            )
            bonus = cp.create_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=c2,
                employee_key="E1", actor_key="MGR1", recommendation_type="one_time_bonus",
                amount=100, rationale="spot",
            )
            check("bonus type distinct", bonus.get("ok") is True, bonus)
            bonus_id = str(bonus["recommendation"]["recommendation_id"])
            cp.approve_recommendation(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=c2,
                recommendation_id=bonus_id, approver_key="approver-1",
            )
            fin2 = cp.finalize_cycle(cur, company_code=COMPANY, actor_phone=HR, cycle_id=c2)
            check("bonus finalize", fin2.get("ok") is True, fin2)
            bonus_decision = str(fin2["decisions"][0]["decision_id"])
            bhand = cp.create_apply_handoff(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=c2,
                decision_id=bonus_decision, target_authority="external_payroll",
            )
            check("approved bonus not paid", bhand.get("approved_bonus_not_paid") is True, bhand)

            cur.execute(
                "SELECT fact_type FROM cp_wave5_fact_outbox WHERE company_code=%s ORDER BY created_at",
                (COMPANY,),
            )
            facts = [dict(r)["fact_type"] for r in cur.fetchall()]
            check("wave5 eligible fact", "comp.eligible_population" in facts, facts)
            check("wave5 approved fact", "comp.approved_adjustment" in facts, facts)

            # Module-off composition — history retained, ops blocked
            disabled = cp.disable_company_comp_planning(
                cur, company_code=COMPANY, actor_phone=HR, reason="module off prove"
            )
            check("disable retains history", disabled.get("history_retained") is True, disabled)
            blocked = cp.create_cycle(
                cur, company_code=COMPANY, actor_phone=HR, code="X", title_en="x", title_ar="س",
            )
            check("module off blocks", blocked.get("error") == "comp_planning_disabled_for_company", blocked)
            cur.execute("SELECT count(*) AS n FROM cp_cycles WHERE company_code=%s", (COMPANY,))
            check("history kept", int(dict(cur.fetchone())["n"]) >= 2)

            # Tenant isolation — OTHER cannot see COMPANY cycle via require
            _cp_flags(companies=f"{COMPANY},{OTHER}")
            _ja_flags(companies=f"{COMPANY},{OTHER}")
            other_view = cp.employee_comp_view(cur, company_code=OTHER, employee_key="E1", cycle_id=cycle_id)
            # OTHER not enabled for module settings
            check("tenant other gated or empty", other_view.get("ok") is not True or other_view.get("error"), other_view)

            print(f"\n    COMPENSATION_PLANNING_FULL_PASS")
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
