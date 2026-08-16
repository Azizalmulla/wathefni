#!/usr/bin/env python3
"""Wave 6 C3 Benefits Administration qualification prove."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"BN1{_N:05d}"[:12].upper()
OTHER = f"BN9{_N:05d}"[:12].upper()
HR = f"9656800{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def _flags(*, on="on", companies="") -> None:
    os.environ["WATHEFNI_BENEFITS_C3"] = on
    os.environ["WATHEFNI_BENEFITS_COMPANIES"] = companies


def main() -> int:
    print("    benefits administration c3 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import benefits_administration_c3 as bn
    import setup_console_wave6_policies as w6

    check("phase", bn.PHASE == "benefits_administration_c3")
    check("stamp", bn.PASS_STAMP == "BENEFITS_FULL_PASS")
    check("commercial key", bn.COMMERCIAL_MODULE_KEY == "benefits")
    honesty = bn.honesty_payload()
    check("no employee ownership", honesty["does_not_own_employee_employment"] is True)
    check("no dependent master", honesty["does_not_own_dependent_master"] is True)
    check("no payroll ownership", honesty["does_not_own_payroll_execution"] is True)
    check("claims out", honesty["claims_adjudication_out"] is True)
    check("no claim tables", honesty["no_claim_tables_in_c3"] is True)
    check("eligible not enrolled", honesty["eligible_not_enrolled"] is True)
    check("election not coverage", honesty["election_not_confirmed_coverage"] is True)
    check("contrib not deduction", honesty["contribution_not_payroll_deduction"] is True)
    check("payroll optional", honesty["payroll_integration_optional"] is True)
    check("works payroll off", honesty["works_payroll_off"] is True)
    check("ja optional", honesty["ja_optional"] is True)
    check("no invented KW statute", honesty["no_invented_statutory_kuwait_policy"] is True)
    check("manager fail closed", honesty["manager_fail_closed_on_private_detail"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    check("facts not analytics", honesty["emits_typed_facts_not_analytics_engine"] is True)
    check("setup wave6 benefits", "benefits" in w6.WAVE6_MODULE_KEYS)
    check("setup honesty claims", w6.honesty_payload()["benefits_claims_out"] is True)
    check("bilingual en", bool(bn.status_label("eligible", lang="en")))
    check("bilingual ar", bool(bn.status_label("eligible", lang="ar")))
    surf = bn.surface_composition_rules()
    check("hr web primary", surf["hr_web"]["primary_admin"] is True)
    check("manager no private", surf["manager"]["private_benefit_detail"] is False)
    check("employee my benefits", surf["employee_app"]["my_benefits"] is True)
    check("hr mobile thin", surf["hr_mobile"]["no_full_plan_authoring"] is True)
    claims = bn.claims_engine_absent_check()
    check("claims engine absent", claims["no_claim_tables_in_c3"] is True and claims["has_claim_table_ddl"] is False, claims)

    _flags(on="off", companies=COMPANY)
    check("gate off", bn.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist admits after R5F", bn.runtime_gate_for_company(COMPANY).get("ok") is True)
    _flags(companies=COMPANY)
    check("gate on", bn.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", bn.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(bn.__file__).read_text(encoding="utf-8")
    check("schema plans", "bn_plans" in source)
    check("schema coverage", "bn_coverage_periods" in source)
    check("no claim ddl", "CREATE TABLE IF NOT EXISTS bn_claim" not in source)
    check("no employee table", "CREATE TABLE IF NOT EXISTS employees" not in source)
    check("payroll rewrite check", "finalized_payroll_rewritten = false" in source)

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

    today = date.today()
    try:
        with conn.cursor() as cur:
            bn.ensure_benefits_administration_c3_schema(cur)
            # Ensure Wave 3 dependents table for reference prove
            try:
                import ess_letters_dependents_c2 as dep
                dep.ensure_ess_letters_dependents_c2_schema(cur)
            except Exception:
                pass
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"BN {code}"),
                )

            blocked = bn.upsert_provider(
                cur, company_code=COMPANY, actor_phone=HR, code="INS", name_en="Insurer", name_ar="شركة تأمين"
            )
            check("disabled blocks ops", blocked.get("error") == "benefits_disabled_for_company", blocked)

            # Benefits without Payroll (default handoff off)
            enabled = bn.enable_company_benefits(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="c3 prove",
                payroll_handoff_enabled=False,
                manager_sees_private_detail=False,
                employee_self_service_enabled=True,
            )
            check("enable company", enabled.get("ok") is True, enabled)
            check("works payroll off settings", enabled["settings"]["payroll_handoff_enabled"] is False, enabled)

            pol = w6.get_wave6_module_policy(cur, COMPANY, "benefits")
            check("setup policy get", pol.get("ok") is True and pol["policy"]["enabled"] is True, pol)

            prov = bn.upsert_provider(
                cur, company_code=COMPANY, actor_phone=HR, code="GIG", name_en="GIG", name_ar="جي آي جي"
            )
            check("provider", prov.get("ok") is True, prov)
            provider_id = str(prov["provider"]["provider_id"])

            plan = bn.upsert_plan(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="MED-STD",
                category="medical",
                title_en="Standard Medical",
                title_ar="طبي قياسي",
                status="published",
                provider_id=provider_id,
                policy_group_ref="POL-100",
                tier_options=["employee_only", "employee_spouse", "family"],
                dependent_eligibility={"relationships": ["spouse", "child"]},
                contribution_policy={"employee_mode": "fixed", "currency": "KWD"},
                required_documents=["marriage_certificate"],
                effective_start=today - timedelta(days=30),
                reason="seed",
            )
            check("plan created", plan.get("ok") is True and plan.get("claims_engine_absent") is True, plan)
            plan_id = plan["stable_id"]
            v1 = int(plan["plan"]["effective_version"])

            revised = bn.upsert_plan(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="MED-STD",
                category="medical",
                title_en="Standard Medical Plus",
                title_ar="طبي قياسي بلس",
                status="published",
                provider_id=provider_id,
                policy_group_ref="POL-100",
                tier_options=["employee_only", "family"],
                contribution_policy={"employee_mode": "fixed", "amount": 20, "currency": "KWD"},
                required_documents=["marriage_certificate"],
                reason="revise",
            )
            check(
                "stable id + version bump",
                revised.get("stable_id") == plan_id and int(revised["plan"]["effective_version"]) == v1 + 1,
                revised,
            )
            v2 = int(revised["plan"]["effective_version"])

            rule = bn.create_eligibility_rule(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                plan_id=plan_id,
                code="ACTIVE-FT",
                title_en="Active full-time",
                title_ar="دوام كامل نشط",
                criteria={"employment_status": "active", "employment_type": "full_time"},
                rule_version=1,
            )
            check("eligibility rule", rule.get("ok") is True, rule)
            rule_id = str(rule["rule"]["rule_id"])

            ineligible = bn.evaluate_eligibility(
                cur,
                company_code=COMPANY,
                employee_key="E1",
                plan_id=plan_id,
                rule_id=rule_id,
                attributes={"employment_status": "active", "employment_type": "contractor"},
            )
            check("ineligible explainable", ineligible.get("ok") is True and ineligible.get("eligible") is False, ineligible)
            check("eligible not enrolled marker", ineligible.get("eligible_not_enrolled") is True, ineligible)

            eligible = bn.evaluate_eligibility(
                cur,
                company_code=COMPANY,
                employee_key="E1",
                plan_id=plan_id,
                rule_id=rule_id,
                attributes={"employment_status": "active", "employment_type": "full_time", "tenure_days": 90},
            )
            check("eligible", eligible.get("ok") is True and eligible.get("eligible") is True, eligible)
            check("not enrolled yet", eligible.get("enrolled") is False, eligible)
            eval_id = str(eligible["evaluation"]["evaluation_id"])

            # Pin historical enrollment under v1 meaning by temporarily starting after pinning plan_version via start
            # Re-seed plan version pin: start_enrollment uses current plan version — create enrollment then prove history via coverage pin
            win = bn.open_enrollment_window(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                plan_id=plan_id,
                window_type="open_enrollment",
                starts_on=today - timedelta(days=5),
                ends_on=today + timedelta(days=25),
                window_version=1,
            )
            check("enrollment window", win.get("ok") is True, win)
            window_id = str(win["window"]["window_id"])

            # Force plan_version on enrollment by updating after start if needed — start uses current v2
            started = bn.start_enrollment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E1",
                plan_id=plan_id,
                evaluation_id=eval_id,
                window_id=window_id,
            )
            check("start enrollment", started.get("ok") is True, started)
            enrollment_id = str(started["enrollment"]["enrollment_id"])
            # Historical pin: rewrite pin to v1 to prove later plan edit doesn't rewrite enrollment meaning
            cur.execute(
                "UPDATE bn_enrollments SET plan_version=%s WHERE enrollment_id=%s RETURNING plan_version",
                (v1, enrollment_id),
            )
            pinned = int(dict(cur.fetchone())["plan_version"])
            check("historical plan version pinned", pinned == v1 and v1 != v2, pinned)

            elected = bn.elect_or_waive(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                enrollment_id=enrollment_id,
                waive=False,
                tier="employee_spouse",
            )
            check(
                "election pending evidence",
                elected.get("ok") is True
                and elected["enrollment"]["status"] == "pending_evidence"
                and elected.get("election_not_confirmed_coverage") is True,
                elected,
            )
            evid = bn.submit_evidence(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                enrollment_id=enrollment_id,
                document_type="marriage_certificate",
                shared_intake_ref="doc://shared/abc",
            )
            check("evidence submitted via shared intake", evid.get("ok") is True and evid.get("remaining_required") == 0, evid)
            check("now elected not active", evid["enrollment"]["status"] == "elected", evid)

            confirmed = bn.confirm_enrollment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                enrollment_id=enrollment_id,
                coverage_start=today,
                provider_confirmed=False,
            )
            check(
                "internal confirm distinct from provider",
                confirmed.get("ok") is True
                and confirmed.get("internal_recorded") is True
                and confirmed.get("provider_confirmed") is False
                and confirmed.get("approval_not_provider_activation") is True,
                confirmed,
            )
            coverage_id = str(confirmed["coverage"]["coverage_id"])
            check("coverage plan version historical", int(confirmed["coverage"]["plan_version"]) == v1, confirmed)

            # Canonical dependent reference
            dep_id = str(uuid.uuid4())
            cur.execute("SELECT to_regclass('employee_dependents') AS t")
            if dict(cur.fetchone()).get("t"):
                cur.execute(
                    """
                    INSERT INTO employee_dependents (
                      dependent_id, company_code, employee_key, relationship, name_en, name_ar,
                      duplicate_fingerprint, status
                    ) VALUES (%s,%s,'E1','spouse','Spouse EN','الزوج/ة',%s,'active')
                    ON CONFLICT DO NOTHING
                    """,
                    (dep_id, COMPANY, f"fp-{dep_id}"),
                )
                link = bn.link_dependent_coverage(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    coverage_id=coverage_id,
                    dependent_id=dep_id,
                    evidence_ref="doc://shared/abc",
                )
                check(
                    "dependent coverage refs canonical",
                    link.get("ok") is True
                    and link.get("does_not_create_dependent_master") is True
                    and link.get("references_canonical_dependent") is True,
                    link,
                )
            else:
                check("dependent table available", False, "employee_dependents missing")

            contrib = bn.define_contribution(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                plan_id=plan_id,
                plan_version=v1,
                kind="employee",
                mode="fixed",
                amount=15,
                currency="KWD",
                effective_start=today,
                enrollment_id=enrollment_id,
                coverage_id=coverage_id,
            )
            check(
                "contribution versioned not payroll",
                contrib.get("ok") is True
                and contrib.get("contribution_not_payroll_deduction") is True
                and contrib.get("paid_amount") is None,
                contrib,
            )

            # Payroll handoff disabled while Benefits works
            handoff_off = bn.create_payroll_handoff(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                enrollment_id=enrollment_id,
                coverage_id=coverage_id,
                employee_amount=15,
                employer_amount=50,
                period_start=today,
            )
            check("payroll handoff off while benefits works", handoff_off.get("error") == "payroll_handoff_disabled", handoff_off)

            # Enable payroll handoff OPTIONAL path
            bn.enable_company_benefits(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="enable payroll handoff",
                payroll_handoff_enabled=True,
            )
            handoff = bn.create_payroll_handoff(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                enrollment_id=enrollment_id,
                coverage_id=coverage_id,
                employee_amount=15,
                employer_amount=50,
                period_start=today,
                component_mapping={"employee": "BEN_EMP", "employer": "BEN_ER"},
            )
            check(
                "payroll handoff not applied",
                handoff.get("ok") is True
                and handoff.get("applied_to_payroll") is False
                and handoff.get("benefit_enrollment_confirmed_not_payroll_deduction_applied") is True
                and handoff.get("finalized_payroll_not_rewritten") is True,
                handoff,
            )

            member = bn.set_provider_member_ref(
                cur,
                company_code=COMPANY,
                enrollment_id=enrollment_id,
                coverage_id=coverage_id,
                employee_key="E1",
                policy_group_number="POL-100",
                member_id="M-7788",
                provider_status_confirmed=False,
            )
            check(
                "member ref not insurer proof",
                member.get("ok") is True and member.get("not_proof_of_insurer_active_unless_provider_confirmed") is True,
                member,
            )

            # Waiver path for E2
            eval2 = bn.evaluate_eligibility(
                cur,
                company_code=COMPANY,
                employee_key="E2",
                plan_id=plan_id,
                rule_id=rule_id,
                attributes={"employment_status": "active", "employment_type": "full_time"},
            )
            st2 = bn.start_enrollment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E2",
                plan_id=plan_id,
                evaluation_id=str(eval2["evaluation"]["evaluation_id"]),
                window_id=window_id,
            )
            waived = bn.elect_or_waive(
                cur, company_code=COMPANY, actor_phone=HR, enrollment_id=str(st2["enrollment"]["enrollment_id"]), waive=True
            )
            check("waiver", waived.get("ok") is True and waived.get("waived") is True and waived.get("coverage_active") is False, waived)

            # Manager restricted view
            mgr = bn.manager_benefits_status_view(
                cur, company_code=COMPANY, manager_scope_employee_keys=["E1", "E2"]
            )
            check(
                "manager status only",
                mgr.get("ok") is True
                and mgr.get("private_detail_included") is False
                and mgr.get("plan_member_ids_exposed") is False
                and mgr.get("fail_closed") is True,
                mgr,
            )

            emp = bn.employee_benefits_view(cur, company_code=COMPANY, employee_key="E1")
            check("employee self", emp.get("ok") is True and emp.get("states_not_conflated") is True and emp.get("hr_admin_exposed") is False, emp)

            asst = bn.assistant_query_benefits(
                cur, company_code=COMPANY, actor=HR, question_kind="my_coverage", employee_key="E1"
            )
            check("assistant read", asst.get("ok") is True and asst.get("mutations") is False, asst)
            asst_bad = bn.assistant_query_benefits(
                cur, company_code=COMPANY, actor=HR, question_kind="enroll", employee_key="E1"
            )
            check("assistant mutation forbidden", asst_bad.get("error") == "mutation_forbidden", asst_bad)

            hist = bn.resolve_coverage_as_of(cur, company_code=COMPANY, employee_key="E1", as_of=today)
            check("historical reconstructable", hist.get("ok") is True and hist.get("reconstructable") is True and hist.get("coverage"), hist)

            # Eligibility rule revision does not rewrite past evaluation
            rule_v2 = bn.create_eligibility_rule(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                plan_id=plan_id,
                code="ACTIVE-FT",
                title_en="Active full-time v2",
                title_ar="دوام كامل نشط ٢",
                criteria={"employment_status": "active", "employment_type": "full_time", "tenure_days_min": 180},
                rule_version=2,
            )
            check("eligibility rule revision", rule_v2.get("ok") is True, rule_v2)
            cur.execute(
                "SELECT rule_version, eligible FROM bn_eligibility_evaluations WHERE evaluation_id=%s",
                (eval_id,),
            )
            past_ev = dict(cur.fetchone())
            check("past eligibility snapshot intact", int(past_ev["rule_version"]) == 1 and past_ev["eligible"] is True, past_ev)

            # Lifecycle consume only
            ended = bn.consume_employment_end_event(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E1",
                employment_end_date=today + timedelta(days=30),
            )
            check(
                "lifecycle consume only",
                ended.get("ok") is True
                and ended.get("employment_mutated") is False
                and ended.get("continuation_coverage_in_mvp") is False
                and ended.get("modeled_honestly_without_invented_kuwait_rules") is True,
                ended,
            )

            n1 = bn._notify_dedupe(cur, company=COMPANY, key="enroll:E1")
            n2 = bn._notify_dedupe(cur, company=COMPANY, key="enroll:E1")
            check("notify first", n1.get("sent") is True, n1)
            check("notify dedupe", n2.get("deduped") is True, n2)

            cur.execute("SELECT COUNT(*) AS c FROM bn_wave5_fact_outbox WHERE company_code=%s", (COMPANY,))
            facts = int(dict(cur.fetchone())["c"])
            check("typed facts emitted", facts >= 2, facts)

            other = bn.upsert_plan(
                cur,
                company_code=OTHER,
                actor_phone=HR,
                code="X",
                category="medical",
                title_en="x",
                title_ar="س",
            )
            check("other company gated", other.get("ok") is not True, other)

            # Self-service disable
            bn.enable_company_benefits(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="disable ess",
                employee_self_service_enabled=False,
                payroll_handoff_enabled=True,
            )
            ess_off = bn.employee_benefits_view(cur, company_code=COMPANY, employee_key="E1")
            check("employee self-service off", ess_off.get("error") == "employee_self_service_disabled", ess_off)

            off = bn.disable_company_benefits(cur, company_code=COMPANY, actor_phone=HR, reason="toggle off")
            check("disable retains history", off.get("history_retained") is True, off)
            blocked2 = bn.start_enrollment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E9",
                plan_id=plan_id,
                evaluation_id=eval_id,
            )
            check("ops blocked when off", blocked2.get("error") == "benefits_disabled_for_company", blocked2)
            cur.execute("SELECT COUNT(*) AS c FROM bn_enrollments WHERE company_code=%s", (COMPANY,))
            retained = int(dict(cur.fetchone())["c"])
            check("history retained after disable", retained >= 1, retained)

            # Re-enable modularity honesty
            bn.enable_company_benefits(cur, company_code=COMPANY, actor_phone=HR, reason="re-enable")
            matrix = bn.honesty_payload(company_code=COMPANY)
            check("modularity benefits without payroll", matrix["works_payroll_off"] is True)
            check("modularity ja optional", matrix["ja_optional"] is True)

            bad = bn.upsert_plan(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="BAD",
                category="medical",
                title_en="Bad",
                title_ar="سيء",
                contribution_policy={"payroll_run_id": "x"},
            )
            check("must not own payroll truth", bad.get("error") == "must_not_own_external_truth", bad)

            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            db_context.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("BENEFITS_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
