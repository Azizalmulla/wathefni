#!/usr/bin/env python3
"""Wave 5 C3 — Recruiting + Hire→Ready Intelligence prove."""
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
COMPANY = f"HI3{_N:05d}"[:12].upper()
OTHER = f"HKX{_N:05d}"[:12].upper()
HR = f"9656720{_N:05d}"
HM = f"{COMPANY}-HM"
REC = f"{COMPANY}-REC"
PERSON_A = f"{COMPANY}-PA"
PERSON_B = f"{COMPANY}-PB"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, c1_on="on", c3_on="on", companies="", c2_on="off"):
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = c1_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_RECRUITING_C3"] = c3_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_RECRUITING_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2"] = c2_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES"] = companies if c2_on == "on" else ""
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    for flag in (
        "WATHEFNI_PERFORMANCE_GOALS_C1",
        "WATHEFNI_TALENT_PROFILE_C5",
        "WATHEFNI_TALENT_SUCCESSION_C6",
        "WATHEFNI_PERFORMANCE_REVIEWS_C2",
    ):
        os.environ[flag] = "off"


def main() -> int:
    print("    hr intelligence recruiting c3 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_recruiting_c3 as c3

    check("c3 module", c3.PHASE == "hr_intelligence_recruiting_c3")
    check("stamp", c3.PASS_STAMP == "HR_INTELLIGENCE_RECRUITING_FULL_PASS")
    check("commercial analytics", c3.COMMERCIAL_MODULE_KEY == "analytics")
    h = c3.honesty_payload()
    check("uses c1 evaluator", h.get("uses_c1_registry_evaluator") is True)
    check("no second math engine", h.get("no_second_analytics_math_engine") is True)
    check("ttf distinct tth", h.get("ttf_distinct_from_tth") is True)
    check("no universal source score", h.get("no_universal_source_effectiveness_score") is True)
    check("unknown stays unknown", h.get("unknown_source_stays_unknown") is True)
    check("canonical hire bridge", h.get("canonical_hire_bridge") is True)
    check("EN open", c3.status_label("open", lang="en") == "Open")
    check("AR filled", bool(c3.status_label("filled", lang="ar")))
    check("source unknown en", c3.source_label("gibberish_campaign_xyz", lang="en") == "Unknown")
    check("source referral", c3.normalize_source("employee_referral") == "referral")

    _flags(c3_on="off", companies="")
    check("c3 global off", c3.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist admits after R6", c3.runtime_gate_for_company(COMPANY).get("ok") is True)
    _flags(companies=COMPANY)
    check("canary ok", c3.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c3.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise
    try:
        _db = app.db_connect()
        conn = _db.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            c3.ensure_hr_intelligence_recruiting_c3_schema(cur)
            for code, name in ((COMPANY, f"HI3 {COMPANY}"), (OTHER, f"HKX {OTHER}")):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, name),
                )

            en = c3.enable_company_recruiting_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable c3"
            )
            check("enable c3", en.get("ok") is True, en)
            pubs = c3.publish_recruiting_kpis_for_company(
                cur, company_code=COMPANY, actor_phone=HR, reason="publish"
            )
            check("publish recruiting kpis", pubs.get("ok") is True, pubs)
            check("universal score blocked", pubs.get("universal_score_blocked") is True, pubs)

            today = date.today()
            period_start = today - timedelta(days=90)
            window = {"period_start": str(period_start), "period_end": str(today)}

            # Requisitions: filled, cancelled, reopened cycle
            r1 = c3.upsert_requisition(
                cur, company_code=COMPANY, actor_phone=HR, requisition_key="REQ1", status="filled",
                reason="seed", opened_at=period_start + timedelta(days=1),
                filled_at=period_start + timedelta(days=31), department="Ops", job_role="Analyst",
                hiring_manager_key=HM, recruiter_key=REC, fill_type="external",
                dims_effective_from=period_start + timedelta(days=1),
            )
            check("req filled", r1.get("ok") is True, r1)
            # Later job title edit must not rewrite historical dims (COALESCE preserves first)
            c3.upsert_requisition(
                cur, company_code=COMPANY, actor_phone=HR, requisition_key="REQ1", status="filled",
                reason="title edit", opened_at=period_start + timedelta(days=1),
                filled_at=period_start + timedelta(days=31), department="Finance", job_role="Senior Analyst",
                hiring_manager_key=HM, recruiter_key=REC,
            )
            cur.execute(
                "SELECT department, job_role FROM hr_intelligence_recruiting_requisitions WHERE company_code=%s AND requisition_key='REQ1'",
                (COMPANY,),
            )
            dims = dict(cur.fetchone())
            check("historical dept preserved", dims.get("department") == "Ops", dims)

            c3.upsert_requisition(
                cur, company_code=COMPANY, actor_phone=HR, requisition_key="REQ_CANCEL", status="cancelled",
                reason="cancel", opened_at=period_start + timedelta(days=5),
                cancelled_at=period_start + timedelta(days=10), department="Ops",
                hiring_manager_key=HM, recruiter_key=REC,
            )
            # Reopened cycle — new open_cycle_id
            c3.upsert_requisition(
                cur, company_code=COMPANY, actor_phone=HR, requisition_key="REQ_REOPEN", status="filled",
                reason="reopen fill", opened_at=period_start + timedelta(days=40),
                filled_at=period_start + timedelta(days=50), reopened_at=period_start + timedelta(days=40),
                open_cycle_id="2", department="Sales", hiring_manager_key=HM, recruiter_key=REC,
            )

            ttf = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.TTF_KEY, time_window=window
            )
            check("ttf ok", ttf.get("status") == "ok" and ttf.get("value") is not None, ttf)
            check("ttf milestones pinned", (ttf.get("explain") or {}).get("milestones", {}).get("start_milestone") == "requisition_opened", ttf)
            check("ttf cancelled excluded", "REQ_CANCEL" not in str(ttf.get("population_ids")), ttf)
            check("ttf includes reopen cycle", any("REQ_REOPEN" in str(x) for x in (ttf.get("population_ids") or [])), ttf)
            check("ttf pins definition", ttf.get("kpi_definition_id") and ttf.get("effective_version"))

            # Applications: multi-app same person, rejected, hire, merge
            c3.upsert_application(
                cur, company_code=COMPANY, actor_phone=HR, application_key="APP1", status="hired",
                reason="seed", person_key=PERSON_A, requisition_key="REQ1", job_key="JOB1",
                source_raw="referral", received_at=period_start + timedelta(days=5),
                hired_at=period_start + timedelta(days=28), hiring_manager_key=HM, recruiter_key=REC,
                department="Ops",
            )
            c3.upsert_application(
                cur, company_code=COMPANY, actor_phone=HR, application_key="APP2", status="rejected",
                reason="seed", person_key=PERSON_A, requisition_key="REQ1", job_key="JOB1",
                source_raw="unknown_campaign_xyz", received_at=period_start + timedelta(days=6),
                rejected_at=period_start + timedelta(days=12), hiring_manager_key=HM, recruiter_key=REC,
            )
            check("unknown source preserved", c3.normalize_source("unknown_campaign_xyz") == "unknown")
            c3.upsert_application(
                cur, company_code=COMPANY, actor_phone=HR, application_key="APP3", status="hired",
                reason="seed", person_key=PERSON_B, requisition_key="REQ_REOPEN", job_key="JOB2",
                source_raw="careers_site", received_at=period_start + timedelta(days=41),
                hired_at=period_start + timedelta(days=48), hiring_manager_key=HM, recruiter_key=REC,
                department="Sales",
            )
            # Duplicate merge candidate
            c3.upsert_application(
                cur, company_code=COMPANY, actor_phone=HR, application_key="APP_DUP", status="ready_for_review",
                reason="dup", person_key=PERSON_B, source_raw="careers_site",
                received_at=period_start + timedelta(days=42), hiring_manager_key=HM, recruiter_key=REC,
            )
            merge = c3.merge_applications(
                cur, company_code=COMPANY, actor_phone=HR,
                survivor_application_key="APP3", merged_application_key="APP_DUP", reason="merge persons",
            )
            check("merge ok", merge.get("ok") is True and merge.get("domain_audit_rewritten") is False, merge)

            # Offers: version supersession
            c3.upsert_offer(
                cur, company_code=COMPANY, actor_phone=HR, business_offer_key="OFF1", status="issued",
                reason="v1", offer_version=1, application_key="APP1", person_key=PERSON_A,
                issued_at=period_start + timedelta(days=20), source_raw="referral",
                hiring_manager_key=HM, is_current_business_offer=False, superseded_by_version=2,
            )
            c3.upsert_offer(
                cur, company_code=COMPANY, actor_phone=HR, business_offer_key="OFF1", status="accepted",
                reason="v2 accept", offer_version=2, application_key="APP1", person_key=PERSON_A,
                issued_at=period_start + timedelta(days=22), accepted_at=period_start + timedelta(days=25),
                source_raw="referral", hiring_manager_key=HM, is_current_business_offer=True,
            )
            c3.upsert_offer(
                cur, company_code=COMPANY, actor_phone=HR, business_offer_key="OFF2", status="declined",
                reason="decline", offer_version=1, application_key="APP2", person_key=PERSON_A,
                issued_at=period_start + timedelta(days=15), declined_at=period_start + timedelta(days=18),
                source_raw="recruiter_manual", hiring_manager_key=HM,
            )
            c3.upsert_offer(
                cur, company_code=COMPANY, actor_phone=HR, business_offer_key="OFF3", status="accepted",
                reason="accept b", offer_version=1, application_key="APP3", person_key=PERSON_B,
                issued_at=period_start + timedelta(days=45), accepted_at=period_start + timedelta(days=46),
                source_raw="careers_site", hiring_manager_key=HM,
            )

            issued = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.OFFER_ISSUED_KEY, time_window=window)
            check("offers issued", issued.get("status") == "ok" and float(issued["value"]) == 3.0, issued)
            check("offer versions not multiplied", "OFF1" in (issued.get("population_ids") or []) and float(issued["value"]) == 3.0, issued)
            accepted = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.OFFER_ACCEPTED_KEY, time_window=window)
            check("offers accepted", accepted.get("status") == "ok" and float(accepted["value"]) == 2.0, accepted)
            declined = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.OFFER_DECLINED_KEY, time_window=window)
            check("offers declined", declined.get("status") == "ok" and float(declined["value"]) == 1.0, declined)
            rate = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.OFFER_ACCEPT_RATE_KEY, time_window=window)
            check("accept rate", rate.get("status") == "ok" and abs(float(rate["value"]) - (2 / 3 * 100)) < 0.01, rate)
            check("accept denom reproducible", float(rate.get("denominator_value") or 0) == 3.0, rate)

            # Canonical hires (bridge) — same employment_period_key as C2
            h1 = c3.upsert_hire(
                cur, company_code=COMPANY, actor_phone=HR, hire_operation_key="HOP1",
                employment_period_key="EP_A1", hire_completed_at=period_start + timedelta(days=28),
                reason="hire a", application_key="APP1", person_key=PERSON_A, requisition_key="REQ1",
                source_raw="referral", department="Ops", hiring_manager_key=HM, recruiter_key=REC,
            )
            check("hire bridge a", h1.get("ok") is True, h1)
            c3.upsert_hire(
                cur, company_code=COMPANY, actor_phone=HR, hire_operation_key="HOP2",
                employment_period_key="EP_B1", hire_completed_at=period_start + timedelta(days=48),
                reason="hire b", application_key="APP3", person_key=PERSON_B, requisition_key="REQ_REOPEN",
                source_raw="careers_site", department="Sales", hiring_manager_key=HM, recruiter_key=REC,
            )

            tth = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.TTH_KEY, time_window=window)
            check("tth ok", tth.get("status") == "ok", tth)
            check("tth distinct milestones", (tth.get("explain") or {}).get("milestones", {}).get("start_milestone") == "application_received", tth)
            check("tth excludes rejected", "APP2" not in (tth.get("population_ids") or []), tth)
            check("tth multi-app person", "APP1" in (tth.get("population_ids") or []), tth)
            # merge must not add APP_DUP as second TTH
            check("merge no double tth", "APP_DUP" not in (tth.get("population_ids") or []), tth)

            rh = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.RECRUITING_HIRES_KEY, time_window=window)
            check("recruiting hires", rh.get("status") == "ok" and float(rh["value"]) == 2.0, rh)
            check("hire uses employment keys", "EP_A1" in (rh.get("population_ids") or []) and "EP_B1" in (rh.get("population_ids") or []), rh)

            # C2 reconciliation path
            import hr_intelligence_workforce_c2 as c2
            _flags(companies=COMPANY, c2_on="on", c3_on="on")
            c2.enable_company_workforce_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c3 reconcile")
            c2.upsert_employment_period(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=f"{COMPANY}-EA",
                employment_period_key="EP_A1", status="active",
                effective_start=period_start + timedelta(days=28),
                hire_event_date=period_start + timedelta(days=28), department="Ops", reason="c2 mirror",
            )
            c2.upsert_employment_period(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=f"{COMPANY}-EB",
                employment_period_key="EP_B1", status="active",
                effective_start=period_start + timedelta(days=48),
                hire_event_date=period_start + timedelta(days=48), department="Sales", reason="c2 mirror",
            )
            recon = c3.reconcile_hires_with_c2(
                cur, company_code=COMPANY, period_start=period_start, period_end=today
            )
            check("c3/c2 reconcile shared", recon.get("shared_count") == 2 and recon.get("c3_count") == 2, recon)
            check("shared authority key", recon.get("shared_authority") == "employment_period_key", recon)

            # Source metrics
            apps_src = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.APPS_BY_SOURCE_KEY,
                time_window=window, filters={"source_bucket": "referral", "has_recruiting_candidate_access": True},
            )
            check("apps by source referral", apps_src.get("status") == "ok" and float(apps_src["value"]) >= 1.0, apps_src)
            unk = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.APPS_BY_SOURCE_KEY,
                time_window=window, filters={"source_bucket": "unknown", "has_recruiting_candidate_access": True},
            )
            check("unknown source apps", unk.get("status") == "ok" and float(unk["value"]) >= 1.0, unk)
            hs = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.HIRES_BY_SOURCE_KEY, time_window=window)
            check("hires by source", hs.get("status") == "ok" and float(hs["value"]) == 2.0, hs)
            check("observed not causal", (hs.get("explain") or {}).get("observed_outcome_not_causal") is True, hs)
            conv = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.APP_HIRE_CONV_KEY,
                time_window=window, filters={"source_bucket": "referral"},
            )
            check("source conversion", conv.get("status") == "ok" and conv.get("denominator_value"), conv)
            check("no magical score flag", (conv.get("explain") or {}).get("no_universal_effectiveness_score") is True, conv)

            # Funnel events
            c3.record_funnel_event(
                cur, company_code=COMPANY, actor_phone=HR, application_key="APP1",
                from_stage="shortlisted", to_stage="interview", event_at=period_start + timedelta(days=10), reason="funnel",
            )
            c3.record_funnel_event(
                cur, company_code=COMPANY, actor_phone=HR, application_key="APP1",
                from_stage="interview", to_stage="offer_sent", event_at=period_start + timedelta(days=18), reason="funnel",
            )
            funnel = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.FUNNEL_KEY,
                time_window=window, filters={"has_recruiting_candidate_access": True},
            )
            check("funnel events", funnel.get("status") == "ok" and float(funnel["value"]) >= 2.0, funnel)
            check("funnel event based", (funnel.get("explain") or {}).get("event_based_not_current_state_only") is True, funnel)

            # Manager scope — hiring manager only their reqs
            ttf_hm = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.TTF_KEY,
                time_window=window, actor_role="hiring_manager",
                filters={"hiring_manager_scope_keys": [HM]},
            )
            check("hm scope ttf", ttf_hm.get("status") == "ok", ttf_hm)
            ttf_other = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.TTF_KEY,
                time_window=window, actor_role="hiring_manager",
                filters={"hiring_manager_scope_keys": ["NOBODY"]},
            )
            check(
                "hm no leak",
                ttf_other.get("status") == "insufficient_data" or float(ttf_other.get("value") or 0) == 0,
                ttf_other,
            )

            # Candidate drill protection
            apps_no_drill = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.APPS_BY_SOURCE_KEY,
                time_window=window, actor_role="hiring_manager",
                filters={"hiring_manager_scope_keys": [HM], "has_recruiting_candidate_access": False},
            )
            check("candidate ids withheld", apps_no_drill.get("status") == "ok" and apps_no_drill.get("population_ids") == [], apps_no_drill)

            # Hire→Ready
            c3.upsert_hire_ready_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type="preboarding", case_key="PB1",
                status="ready", reason="pb", application_key="APP1", employment_period_key="EP_A1",
                started_at=period_start + timedelta(days=26), completed_at=period_start + timedelta(days=27),
            )
            c3.upsert_hire_ready_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type="preboarding", case_key="PB2",
                status="in_progress", reason="pb2", application_key="APP3",
                started_at=period_start + timedelta(days=46),
            )
            pb = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.PREBOARD_RATE_KEY, time_window=window)
            check("preboard rate", pb.get("status") == "ok" and float(pb.get("denominator_value") or 0) == 2.0, pb)

            c3.upsert_hire_ready_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type="onboarding", case_key="OB1",
                status="completed", reason="ob", employment_period_key="EP_A1",
                started_at=period_start + timedelta(days=28), completed_at=period_start + timedelta(days=40),
                template_version="tmpl_v1",
            )
            # Later template edit must not change historical case template_version (COALESCE)
            c3.upsert_hire_ready_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type="onboarding", case_key="OB1",
                status="completed", reason="tmpl edit attempt", employment_period_key="EP_A1",
                started_at=period_start + timedelta(days=28), completed_at=period_start + timedelta(days=40),
                template_version="tmpl_v2_should_not_overwrite",
            )
            cur.execute(
                "SELECT template_version FROM hr_intelligence_hire_ready_cases WHERE company_code=%s AND case_key='OB1'",
                (COMPANY,),
            )
            check("onboard template historical", dict(cur.fetchone()).get("template_version") == "tmpl_v1")
            ob = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.ONBOARD_RATE_KEY, time_window=window)
            check("onboard rate", ob.get("status") == "ok", ob)
            obt = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.ONBOARD_TIME_KEY, time_window=window)
            check("onboard time", obt.get("status") == "ok" and float(obt["value"]) == 12.0, obt)

            c3.upsert_hire_ready_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type="probation", case_key="PR1",
                status="confirmed", reason="decision", employment_period_key="EP_A1",
                started_at=period_start + timedelta(days=28), completed_at=today - timedelta(days=1),
                outcome="confirmed",
            )
            c3.upsert_hire_ready_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type="probation", case_key="PR2",
                status="failed", reason="decision", employment_period_key="EP_B1",
                started_at=period_start + timedelta(days=48), completed_at=today - timedelta(days=2),
                outcome="failed",
            )
            bad_out = c3.upsert_hire_ready_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type="probation", case_key="PR_BAD",
                status="failed", reason="infer", outcome="probably_failed_from_due_date",
            )
            check("probation no freetext outcome", bad_out.get("ok") is not True, bad_out)
            pr = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.PROBATION_KEY, time_window=window)
            check("probation outcomes", pr.get("status") == "ok" and float(pr["value"]) == 2.0, pr)
            check("probation governed", (pr.get("explain") or {}).get("governed_decision_only") is True, pr)

            # Correction + rebuild
            corr = c3.correct_requisition_dates(
                cur, company_code=COMPANY, actor_phone=HR, requisition_key="REQ1", reason="correct open date",
                opened_at=period_start + timedelta(days=2),
            )
            check("correction", corr.get("ok") is True and corr.get("domain_audit_rewritten") is False, corr)
            rb1 = c3.rebuild_recruiting_facts(cur, company_code=COMPANY, actor_phone=HR, reason="rebuild1")
            rb2 = c3.rebuild_recruiting_facts(cur, company_code=COMPANY, actor_phone=HR, reason="rebuild2")
            check("idempotent rebuild", rb1.get("ok") and rb2.get("ok") and rb1.get("counts") == rb2.get("counts"), (rb1, rb2))
            rh2 = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.RECRUITING_HIRES_KEY, time_window=window)
            check("no double hire count", float(rh2["value"]) == 2.0, rh2)

            # Definition pinning
            ver = c1.version_kpi_definition(
                cur, actor_phone=HR, semantic_key=c3.TTF_KEY, reason="pin prove",
                updates={
                    "business_meaning": "TTF v2 wording",
                    "status": "published",
                    "formula_contract": {"kind": "recruiting_time_to_fill", **c3.TTF_MILESTONES, "note": "v2"},
                },
            )
            check("definition versioned", ver.get("ok") is True and ver.get("prior_preserved") is True, ver)
            pinned_v = int(ttf.get("effective_version") or 0)
            check("pinned historical eval version", pinned_v >= 1, ttf)

            # Module-off → unavailable not fake zero
            c3.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR, reason="disable preboard",
                preboarding_module_enabled=False, probation_module_enabled=False,
            )
            pb_off = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.PREBOARD_RATE_KEY, time_window=window)
            check("preboard unavailable not zero", pb_off.get("status") == "unavailable" and pb_off.get("value") is None, pb_off)
            pr_off = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.PROBATION_KEY, time_window=window)
            check("probation unavailable not zero", pr_off.get("status") == "unavailable" and pr_off.get("value") is None, pr_off)
            # recruiting still works
            issued2 = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.OFFER_ISSUED_KEY, time_window=window)
            check("recruiting without preboard/probation", issued2.get("status") == "ok", issued2)

            c3.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR, reason="disable onboarding",
                preboarding_module_enabled=True, onboarding_module_enabled=False, probation_module_enabled=True,
            )
            ob_off = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.ONBOARD_RATE_KEY, time_window=window)
            check("onboarding unavailable", ob_off.get("status") == "unavailable", ob_off)

            # Zero denom accept rate
            empty_co = f"HI3E{_N:04d}"[:12].upper()
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now()) ON CONFLICT DO NOTHING
                """,
                (empty_co, empty_co),
            )
            os.environ["WATHEFNI_HR_INTELLIGENCE_RECRUITING_COMPANIES"] = f"{COMPANY},{empty_co}"
            os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = f"{COMPANY},{empty_co}"
            c3.enable_company_recruiting_intelligence(cur, company_code=empty_co, actor_phone=HR, reason="empty")
            c3.publish_recruiting_kpis_for_company(cur, company_code=empty_co, actor_phone=HR, reason="pub empty")
            rate0 = c1.evaluate_kpi(cur, company_code=empty_co, actor_phone=HR, semantic_key=c3.OFFER_ACCEPT_RATE_KEY, time_window=window)
            check("zero denom not_applicable", rate0.get("status") == "not_applicable" and rate0.get("value") is None, rate0)
            ttf0 = c1.evaluate_kpi(cur, company_code=empty_co, actor_phone=HR, semantic_key=c3.TTF_KEY, time_window=window)
            check("ttf insufficient_data", ttf0.get("status") == "insufficient_data", ttf0)

            # Bilingual
            cur.execute(
                "SELECT name_en, name_ar FROM hr_kpi_definitions WHERE semantic_key=%s ORDER BY effective_version DESC LIMIT 1",
                (c3.TTF_KEY,),
            )
            names = dict(cur.fetchone())
            check("bilingual ttf", bool(names.get("name_en")) and bool(names.get("name_ar")), names)

            # Disable preserves history
            dis = c3.disable_company_recruiting_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="disable")
            check("disable preserves", dis.get("preserves_history") is True, dis)
            cur.execute(
                "SELECT count(*) AS n FROM hr_intelligence_recruiting_hires WHERE company_code=%s",
                (COMPANY,),
            )
            check("hires survive disable", int(dict(cur.fetchone())["n"]) >= 2)
            blocked = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c3.TTF_KEY, time_window=window)
            check("eval blocked when disabled", blocked.get("ok") is not True or blocked.get("status") == "unavailable", blocked)

            _flags(c3_on="off", c2_on="off", companies="")
            check("all off after prove", c3.runtime_gate_for_company(COMPANY).get("ok") is not True)

            conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print(c3.PASS_STAMP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
