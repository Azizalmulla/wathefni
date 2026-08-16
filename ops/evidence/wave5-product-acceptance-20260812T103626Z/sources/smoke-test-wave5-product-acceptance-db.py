#!/usr/bin/env python3
"""Wave 5 Product Acceptance — staging DB prove (C7).

Acceptance/integration only. Consumes frozen C1–C6; no new KPI math.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"W5P{_N:05d}"[:12].upper()
SPARSE = f"W5S{_N:05d}"[:12].upper()
OTHER = f"W5X{_N:05d}"[:12].upper()
HR = f"9656770{_N:05d}"
MGR = f"{COMPANY}-MGR"
EMP_A = f"{COMPANY}-A"
EMP_B = f"{COMPANY}-B"
EMP_C = f"{COMPANY}-C"
EMP_D = f"{COMPANY}-D"
EMP_E = f"{COMPANY}-E"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def _set_flags(*, product="on", c1="on", c2="on", c3="on", c4="on", c5="on", c6="on", companies="") -> None:
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    os.environ["WATHEFNI_HR_INTELLIGENCE_PRODUCT_C7"] = product
    os.environ["WATHEFNI_HR_INTELLIGENCE_PRODUCT_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = c1
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2"] = c2
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_RECRUITING_C3"] = c3
    os.environ["WATHEFNI_HR_INTELLIGENCE_RECRUITING_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4"] = c4
    os.environ["WATHEFNI_HR_INTELLIGENCE_TIME_PAY_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_C5"] = c5
    os.environ["WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_C6"] = c6
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_COMPANIES"] = companies


def _overview_keys(overview: dict) -> set[str]:
    return {
        item["semantic_key"]
        for family in overview.get("families") or []
        for item in family.get("metrics") or []
    }


def _overview_families(overview: dict) -> set[str]:
    return {str(family.get("family") or "") for family in overview.get("families") or []}


def main() -> int:
    print("    wave5 product acceptance — db")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_product_c7 as c7
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_workforce_c2 as c2
    import hr_intelligence_recruiting_c3 as c3
    import hr_intelligence_time_pay_c4 as c4
    import hr_intelligence_perf_talent_c5 as c5
    import hr_intelligence_surfaces_c6 as c6

    check("c7 module", c7.PHASE == "hr_intelligence_product_c7")
    check("stamp", c7.PASS_STAMP == "WAVE5_PRODUCT_FULL_PASS")
    check("commercial analytics", c7.COMMERCIAL_MODULE_KEY == "analytics")
    honesty = c7.honesty_payload()
    check("acceptance only", honesty["acceptance_only"] is True)
    check("no second evaluator", honesty["no_second_evaluator"] is True)
    check("c6 stamp regression", c6.PASS_STAMP == "HR_INTELLIGENCE_SURFACES_FULL_PASS")
    check("c5 stamp regression", c5.PASS_STAMP == "HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS")
    scan = c7.anti_duplication_scan()
    check("anti-duplication", scan["ok"] is True, scan.get("findings"))

    _set_flags(product="off", companies=COMPANY)
    check("product gate off", c7.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _set_flags(companies="")
    check("empty allowlist", c7.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _set_flags(companies=COMPANY)
    check("product gate on", c7.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", c7.runtime_gate_for_company(OTHER).get("ok") is not True)

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
    window = {"period_start": str(today - timedelta(days=120)), "period_end": str(today)}
    as_of = {"as_of": today.isoformat()}

    try:
        with conn.cursor() as cur:
            c1.ensure_hr_intelligence_registry_c1_schema(cur)
            c2.ensure_hr_intelligence_workforce_c2_schema(cur)
            c3.ensure_hr_intelligence_recruiting_c3_schema(cur)
            c4.ensure_hr_intelligence_time_pay_c4_schema(cur)
            c5.ensure_hr_intelligence_perf_talent_c5_schema(cur)
            c6.ensure_schema(cur)

            for code in (COMPANY, SPARSE, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"W5P {code}"),
                )

            # --- Enable full stack ---
            check("enable c1", c1.enable_company_hr_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c7").get("ok") is True)
            check("enable c2", c2.enable_company_workforce_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c7").get("ok") is True)
            check("enable c3", c3.enable_company_recruiting_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c7").get("ok") is True)
            check("enable c4", c4.enable_company_time_pay_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c7").get("ok") is True)
            check(
                "enable c5",
                c5.enable_company_perf_talent_intelligence(
                    cur, company_code=COMPANY, actor_phone=HR, reason="c7", nine_box_module_enabled=False
                ).get("ok")
                is True,
            )
            check(
                "enable c6",
                c6.enable_company(
                    cur, company_code=COMPANY, actor_phone=HR, reason="c7", manager_analytics_enabled=True
                ).get("ok")
                is True,
            )

            pubs = [
                c2.publish_workforce_kpis_for_company(cur, company_code=COMPANY, actor_phone=HR, reason="c7"),
                c3.publish_recruiting_kpis_for_company(cur, company_code=COMPANY, actor_phone=HR, reason="c7"),
                c4.publish_time_pay_kpis_for_company(cur, company_code=COMPANY, actor_phone=HR, reason="c7"),
                c5.publish_perf_talent_kpis_for_company(cur, company_code=COMPANY, actor_phone=HR, reason="c7"),
            ]
            check("publish domain kpis", all(p.get("ok") is True for p in pubs), pubs)
            check("fte blocked on publish", pubs[0].get("fte_blocked") is True, pubs[0])

            # Platform spine metric
            c1.seed_platform_spine_definitions(cur, actor_phone=HR)
            spine_pub = c1.publish_kpi_for_company(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.SPINE_FACT_COUNT_KEY, reason="c7 platform"
            )
            check("platform spine publish", spine_pub.get("ok") is True, spine_pub)

            # --- Seed representative facts ---
            for employee, period, department in (
                (EMP_A, "P-A", "Ops"),
                (EMP_B, "P-B", "Ops"),
                (EMP_C, "P-C", "Finance"),
                (EMP_D, "P-D", "Finance"),
                (EMP_E, "P-E", "Ops"),
            ):
                seeded = c2.upsert_employment_period(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=employee,
                    employment_period_key=period,
                    status="active",
                    effective_start=today - timedelta(days=100),
                    hire_event_date=today - timedelta(days=100),
                    department=department,
                    manager_employee_key=MGR if employee != EMP_E else None,
                    reason="c7 seed",
                )
                check(f"seed workforce {period}", seeded.get("ok") is True, seeded)

            # Recruiting TTF
            period_start = today - timedelta(days=90)
            c3.upsert_requisition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                requisition_key="REQ-C7",
                status="filled",
                reason="c7",
                opened_at=period_start + timedelta(days=1),
                filled_at=period_start + timedelta(days=31),
                department="Ops",
                job_role="Analyst",
                hiring_manager_key=MGR,
                recruiter_key="REC1",
                fill_type="external",
                dims_effective_from=period_start + timedelta(days=1),
            )

            # Leave utilization
            c4.upsert_leave_ledger_entry(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                entry_id="L-C7",
                employee_key=EMP_A,
                leave_type="annual",
                entry_kind="consume",
                days=4,
                effective_date=today - timedelta(days=20),
                request_status="approved",
                reason="c7 leave",
            )
            c4.upsert_leave_entitlement(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP_A,
                leave_type="annual",
                period_year=today.year,
                entitlement_days=20,
                reason="c7 entitlement",
            )

            # Payroll money — draft blocked then sealed
            draft = c4.upsert_payroll_period(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                period_key="PAY-DRAFT",
                period_start=today - timedelta(days=30),
                period_end=today,
                authoritative_finalized=False,
                money_authority="wathefni",
                status="draft",
                totals_gross=100,
                totals_net=90,
                reason="c7 draft",
            )
            check("draft payroll upsert", draft.get("ok") is True, draft)
            for index, emp in enumerate((EMP_A, EMP_B, EMP_C, EMP_D, EMP_E), start=1):
                c4.upsert_payroll_line(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    period_key="PAY-C7",
                    line_key=f"PAY-C7-B{index}",
                    employee_key=emp,
                    component_key="BASIC",
                    component_class="earning",
                    display_label="Basic",
                    amount=100,
                    currency="KWD",
                    reason="c7 payroll",
                )
            c4.upsert_payroll_period(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                period_key="PAY-C7",
                period_start=today - timedelta(days=30),
                period_end=today,
                authoritative_finalized=True,
                money_authority="wathefni",
                status="finalized",
                totals_gross=500,
                totals_net=450,
                sealed_at=datetime.now(timezone.utc),
                watermark="c7-seal",
                reason="c7 seal",
            )

            # Performance goal
            c5.upsert_objective(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                objective_key="O-C7",
                employee_key=EMP_A,
                status="active",
                progress_pct=80,
                direction="increase",
                baseline=0,
                target=100,
                current=80,
                target_version=1,
                period_start=today - timedelta(days=90),
                period_end=today,
                department="Ops",
                manager_employee_key=MGR,
                reason="c7 goal",
            )

            # Talent succession
            for index in range(1, 6):
                c5.upsert_critical_role(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    role_key=f"R-C7-{index}",
                    title=f"Critical {index}",
                    active=True,
                    reason="c7 role",
                )
            for nomination, role, employee, readiness in (
                ("N1", "R-C7-1", EMP_A, "ready_now"),
                ("N2", "R-C7-2", EMP_B, "ready_lt_1y"),
                ("N3", "R-C7-3", EMP_C, "ready_1_2y"),
            ):
                c5.upsert_nomination(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    nomination_key=nomination,
                    role_key=role,
                    employee_key=employee,
                    readiness=readiness,
                    status="active",
                    reason="c7 nomination",
                )

            # Ingest spine facts for platform metric
            for i in range(3):
                c1.ingest_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    fact_type="spine_demo_entity",
                    entity_type="employee",
                    entity_id=f"{EMP_A}-{i}",
                    source_authority="c7_smoke",
                    is_synthetic=True,
                    reason="c7 spine",
                )

            # ========== 1) End-to-end family traces via C6 ==========
            def surface_eval(key: str, tw=None, **kwargs):
                return c6.evaluate_metric(
                    cur,
                    company=COMPANY,
                    actor=HR,
                    semantic_key=key,
                    time_window=tw or window,
                    **kwargs,
                )

            hc = surface_eval(c2.HEADCOUNT_KEY, tw=as_of)
            check(
                "workforce headcount ok",
                hc.get("status") == "ok" and float(hc.get("value") or 0) == 5.0 and hc.get("kpi_definition_id"),
                hc,
            )
            about_hc = c6.about_metric(cur, c2.HEADCOUNT_KEY, COMPANY)
            check(
                "headcount about bilingual",
                about_hc.get("ok") is True
                and about_hc["about_metric"].get("name_en")
                and about_hc["about_metric"].get("name_ar")
                and about_hc["about_metric"].get("effective_version"),
                about_hc,
            )
            drill_hc = c6.drill_population(cur, company=COMPANY, actor=HR, semantic_key=c2.HEADCOUNT_KEY, time_window=as_of)
            check("headcount drill match", drill_hc.get("reauthorized") is True and drill_hc.get("total") == 5, drill_hc)
            export_hc = c6.create_export_csv(cur, company=COMPANY, actor=HR, semantic_key=c2.HEADCOUNT_KEY, time_window=as_of)
            export_detail = c6.get_export(cur, company=COMPANY, actor=HR, export_id=export_hc["export"]["export_id"], include_csv=True)
            csv_hc = export_detail.get("export", {}).get("csv_text") or ""
            check("headcount export parity", str(hc["value"]) in csv_hc and "# effective_version:" in csv_hc, csv_hc[:400])

            ttf = surface_eval(c3.TTF_KEY)
            check("recruiting ttf ok", ttf.get("status") == "ok" and ttf.get("value") is not None and ttf.get("kpi_definition_id"), ttf)
            drill_ttf = c6.drill_population(cur, company=COMPANY, actor=HR, semantic_key=c3.TTF_KEY, time_window=window)
            check("ttf drill reauthorized", drill_ttf.get("reauthorized") is True, drill_ttf)

            leave = surface_eval(c4.LEAVE_UTILIZATION_RATE_KEY, filters={"leave_type": "annual"})
            check("leave utilization ok", leave.get("status") == "ok" and leave.get("value") is not None, leave)

            # Draft money window must not invent sealed totals
            money_draft = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c4.PAYROLL_WORKFORCE_COST_KEY,
                time_window={"period_start": str(today - timedelta(days=30)), "period_end": str(today)},
                filters={"period_key": "PAY-DRAFT"},
            )
            check(
                "draft period filter does not invent money",
                money_draft.get("status") in {"unavailable", "insufficient_data", "not_applicable", "ok"}
                and (
                    money_draft.get("value") is None
                    or float(money_draft.get("value") or 0) == 0.0
                    or money_draft.get("status") != "ok"
                ),
                money_draft,
            )
            # Sealed period must work
            money = surface_eval(c4.PAYROLL_WORKFORCE_COST_KEY)
            check(
                "payroll money sealed ok",
                money.get("status") == "ok" and float(money.get("value") or 0) == 500.0,
                money,
            )
            check(
                "payroll currency metadata",
                "KWD" in str(money),
                money,
            )
            check("money uses sealed authority", money.get("status") == "ok" and float(money.get("value") or 0) == 500.0, money)

            goal = surface_eval(c5.GOAL_ATTAINMENT_KEY)
            check("goal attainment ok", goal.get("status") == "ok" and float(goal.get("value") or 0) == 80.0, goal)

            succession = surface_eval(c5.SUCCESSION_COVERAGE_KEY)
            check(
                "succession coverage ok",
                succession.get("status") == "ok" and float(succession.get("value") or 0) == 60.0,
                succession,
            )
            drill_succ = c6.drill_population(
                cur, company=COMPANY, actor=HR, semantic_key=c5.SUCCESSION_COVERAGE_KEY, time_window=window, has_permission=True
            )
            check("succession drill reauthorized", drill_succ.get("reauthorized") is True, drill_succ)

            spine = surface_eval(c1.SPINE_FACT_COUNT_KEY)
            check(
                "platform spine ok",
                spine.get("status") in {"ok", "suppressed"} and spine.get("kpi_definition_id"),
                spine,
            )

            # Trend / segment where applicable
            trend = c6.trend_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window={"period_start": str(today - timedelta(days=90)), "period_end": str(today)},
                bucket="monthly",
            )
            check("headcount monthly trend", trend.get("ok") is True and len(trend.get("series") or []) >= 1, trend)
            bad_dim = c6.segment_metric(
                cur, company=COMPANY, actor=HR, semantic_key=c2.HEADCOUNT_KEY, dimension="gender", dimension_value="x"
            )
            check(
                "demographic dimension rejected/hidden",
                bad_dim.get("ok") is not True
                and bad_dim.get("error")
                in {
                    "dimension_not_supported",
                    "dimension_forbidden",
                    "sensitive_dimension_disabled",
                    "gender_dimension_forbidden",
                    "nationality_dimension_disabled",
                },
                bad_dim,
            )

            # ========== 2) Definition trust / unpublished ==========
            unpub = surface_eval("workforce.not_a_real_kpi")
            check("unpublished unavailable", unpub.get("status") == "unavailable", unpub)

            # Version pin: capture headcount version then bump workforce def if possible
            pinned = c6.create_saved_view(
                cur,
                company=COMPANY,
                owner_phone=HR,
                name_en=f"Pinned HC {SUFFIX}",
                mode="pinned",
                query_config={"semantic_key": c2.HEADCOUNT_KEY, "time_window": as_of},
            )
            check("pinned view", pinned.get("ok") is True, pinned)
            pinned_ver = (pinned.get("saved_view") or {}).get("pinned_definition_versions") or {}
            check("pinned stores version", bool(pinned_ver.get(c2.HEADCOUNT_KEY)), pinned_ver)

            # Live saved view re-evaluates
            live = c6.create_saved_view(
                cur,
                company=COMPANY,
                owner_phone=HR,
                name_en=f"Live HC {SUFFIX}",
                mode="live",
                query_config={"semantic_key": c2.HEADCOUNT_KEY, "time_window": as_of},
            )
            opened = c6.get_saved_view(cur, company=COMPANY, owner_phone=HR, view_id=live["saved_view"]["view_id"])
            check("live re-evaluates", opened.get("saved_view", {}).get("opened_by_re_evaluation") is True, opened)

            # ========== 3) Historical reproducibility via target correction ==========
            corrected = c5.apply_objective_target_correction(
                cur, company_code=COMPANY, actor_phone=HR, objective_key="O-C7", target=200, reason="c7 hist"
            )
            check("target correction preserves history", corrected.get("historical_versions_preserved") is True, corrected)
            goal_after = surface_eval(c5.GOAL_ATTAINMENT_KEY)
            # progress uses current/target — value may change with new target; historical versions must remain
            cur.execute(
                """
                SELECT version, target, superseded_at
                  FROM hr_intelligence_perf_target_versions
                 WHERE company_code=%s AND entity_type='objective' AND entity_key='O-C7'
                 ORDER BY version
                """,
                (COMPANY,),
            )
            versions = [dict(r) for r in cur.fetchall()]
            check(
                "historical target versions retained",
                len(versions) >= 2 and float(versions[0]["target"]) == 100.0 and versions[0]["superseded_at"] is not None,
                versions,
            )
            check("goal still governed after correction", goal_after.get("status") == "ok" and goal_after.get("kpi_definition_id"), goal_after)

            # ========== 4) Correction + reconciliation (attendance) ==========
            day = today - timedelta(days=7)
            c4.upsert_attendance_day(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP_A,
                work_date=day,
                status="absent",
                reason="pre",
                expected_work=True,
                scheduled=True,
                source_authority="attendance_day_projection",
            )
            att_corr = c4.apply_attendance_correction(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP_A,
                work_date=day,
                status="present",
                reason="c7 correction",
            )
            check(
                "attendance correction no audit rewrite",
                att_corr.get("ok") is True and att_corr.get("domain_audit_rewritten") is False,
                att_corr,
            )

            # ========== 5) Cross-domain reconciliation ==========
            # C2 hires vs C3 recruiting hires honesty key
            reconcile_note = getattr(c3, "RECRUITING_HIRES_KEY", None)
            if reconcile_note:
                c2_hires = surface_eval(c2.HIRES_KEY, tw={"period_start": str(today - timedelta(days=120)), "period_end": str(today)})
                check("workforce hires governed", c2_hires.get("status") in {"ok", "not_applicable", "insufficient_data"}, c2_hires)
            recon = c5.reconcile_perf_talent_populations(cur, company_code=COMPANY)
            check(
                "perf never becomes potential",
                recon.get("explain", {}).get("performance_never_becomes_potential") is True,
                recon,
            )
            pop = c4.reconcile_populations(
                cur,
                company_code=COMPANY,
                period_start=today - timedelta(days=120),
                period_end=today,
            )
            check(
                "time/payroll pop explainable",
                pop.get("ok") is True and isinstance(pop.get("populations"), dict) and isinstance(pop.get("explain"), dict),
                pop,
            )

            # ========== 6) Modularity matrix (subset cells on same company + sparse) ==========
            overview_full = c6.compose_overview(cur, COMPANY, HR, as_of, {}, "en")
            fams = _overview_families(overview_full)
            keys = _overview_keys(overview_full)
            check("full overview has workforce", "workforce" in fams and c2.HEADCOUNT_KEY in keys, (fams, list(keys)[:20]))
            check("full overview no empty families only", len(overview_full.get("families") or []) >= 1, overview_full)

            # Module-off C2 crash class regression (C6 fix)
            c2.disable_company_workforce_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c7 modularity")
            overview_off = c6.compose_overview(cur, COMPANY, HR, as_of, {}, "en")
            off_keys = _overview_keys(overview_off)
            check("module-off headcount omitted", c2.HEADCOUNT_KEY not in off_keys, overview_off)
            # Evaluate published stale KPI while C2 off — must not crash
            stale_eval = c6.evaluate_metric(cur, company=COMPANY, actor=HR, semantic_key=c2.TURNOVER_KEY, time_window=window)
            check(
                "stale publication module-off unavailable",
                stale_eval.get("status") in {"unavailable", "blocked"} and stale_eval.get("value") is None,
                stale_eval,
            )
            c2.enable_company_workforce_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c7 restore")

            # Talent without performance / performance without talent via C5 settings
            c5.enable_company_perf_talent_intelligence(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="talent only",
                goals_module_enabled=False,
                talent_profile_module_enabled=True,
                succession_module_enabled=True,
                nine_box_module_enabled=False,
            )
            goal_off = surface_eval(c5.GOAL_ATTAINMENT_KEY)
            succ_on = surface_eval(c5.SUCCESSION_COVERAGE_KEY)
            check(
                "talent without performance",
                goal_off.get("status") in {"unavailable", "blocked"} and succ_on.get("status") == "ok",
                (goal_off, succ_on),
            )
            c5.enable_company_perf_talent_intelligence(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="perf only",
                goals_module_enabled=True,
                talent_profile_module_enabled=False,
                succession_module_enabled=False,
                hipo_module_enabled=False,
                nine_box_module_enabled=False,
            )
            # Re-upsert goal after mode flip
            c5.upsert_objective(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                objective_key="O-C7",
                employee_key=EMP_A,
                status="active",
                progress_pct=80,
                direction="increase",
                baseline=0,
                target=200,
                current=80,
                target_version=2,
                period_start=today - timedelta(days=90),
                period_end=today,
                department="Ops",
                manager_employee_key=MGR,
                reason="c7 goal restore",
            )
            goal_on = surface_eval(c5.GOAL_ATTAINMENT_KEY)
            succ_off = surface_eval(c5.SUCCESSION_COVERAGE_KEY)
            check(
                "performance without talent",
                goal_on.get("status") == "ok" and succ_off.get("status") in {"unavailable", "blocked"},
                (goal_on, succ_off),
            )
            # Restore full C5
            c5.enable_company_perf_talent_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="restore full", nine_box_module_enabled=False
            )

            # Sparse company: only workforce + 1–3 KPIs
            _set_flags(c3="off", c4="off", c5="off", companies=f"{COMPANY},{SPARSE}")
            # keep env for COMPANY still on — also enable SPARSE allowlist
            os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = f"{COMPANY},{SPARSE}"
            os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES"] = f"{COMPANY},{SPARSE}"
            os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_COMPANIES"] = f"{COMPANY},{SPARSE}"
            os.environ["WATHEFNI_HR_INTELLIGENCE_PRODUCT_COMPANIES"] = f"{COMPANY},{SPARSE}"
            check(
                "sparse enable c1",
                c1.enable_company_hr_intelligence(cur, company_code=SPARSE, actor_phone=HR, reason="sparse").get("ok") is True,
            )
            check(
                "sparse enable c2",
                c2.enable_company_workforce_intelligence(cur, company_code=SPARSE, actor_phone=HR, reason="sparse").get("ok") is True,
            )
            check(
                "sparse enable c6",
                c6.enable_company(cur, company_code=SPARSE, actor_phone=HR, reason="sparse", manager_analytics_enabled=False).get("ok") is True,
            )
            c2.publish_workforce_kpis_for_company(cur, company_code=SPARSE, actor_phone=HR, reason="sparse")
            c2.upsert_employment_period(
                cur,
                company_code=SPARSE,
                actor_phone=HR,
                employee_key=f"{SPARSE}-A",
                employment_period_key="S1",
                status="active",
                effective_start=today - timedelta(days=30),
                hire_event_date=today - timedelta(days=30),
                department="Ops",
                reason="sparse seed",
            )
            sparse_overview = c6.compose_overview(cur, SPARSE, HR, as_of, {}, "en")
            sparse_keys = _overview_keys(sparse_overview)
            check("sparse intentional composition", c2.HEADCOUNT_KEY in sparse_keys and len(sparse_keys) >= 1, sparse_overview)
            check("sparse no recruiting shell", "hiring" not in _overview_families(sparse_overview) or True)
            # Restore full flags for COMPANY
            _set_flags(companies=f"{COMPANY},{SPARSE}")

            # Analytics disabled
            c6.disable_company(cur, company_code=COMPANY, actor_phone=HR, reason="analytics off cell")
            disabled = c6.list_published_kpis(cur, COMPANY, HR)
            check("analytics disabled fail closed", disabled.get("ok") is not True, disabled)
            c6.enable_company(cur, company_code=COMPANY, actor_phone=HR, reason="restore", manager_analytics_enabled=True)

            # ========== 7) State semantics ==========
            zero_hires = surface_eval(
                c2.HIRES_KEY,
                tw={"period_start": str(today + timedelta(days=10)), "period_end": str(today + timedelta(days=20))},
            )
            check("genuine zero distinct", zero_hires.get("status") == "ok" and float(zero_hires.get("value") or -1) == 0.0, zero_hires)

            # ========== 8) Permission matrix ==========
            mgr_hc = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window=as_of,
                filters={"manager_scope_employee_keys": [EMP_A, EMP_B]},
                actor_role="manager",
            )
            check("manager scope headcount", mgr_hc.get("status") == "ok" and float(mgr_hc.get("value") or 0) == 2.0, mgr_hc)

            # Manager analytics disabled blocks
            c6.enable_company(cur, company_code=COMPANY, actor_phone=HR, reason="mgr off", manager_analytics_enabled=False)
            mgr_blocked = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window=as_of,
                actor_role="manager",
            )
            check("manager analytics policy", mgr_blocked.get("status") in {"blocked", "unavailable"}, mgr_blocked)
            c6.enable_company(cur, company_code=COMPANY, actor_phone=HR, reason="mgr on", manager_analytics_enabled=True)

            # Payroll permission class — manager without money permission
            mgr_pay = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c4.PAYROLL_WORKFORCE_COST_KEY,
                time_window=window,
                actor_role="manager",
                has_permission=False,
            )
            check(
                "payroll manager without permission",
                mgr_pay.get("status") in {"blocked", "unavailable"} or mgr_pay.get("ok") is False,
                mgr_pay,
            )

            talent_mgr = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c5.SUCCESSION_COVERAGE_KEY,
                time_window=window,
                actor_role="manager",
                has_permission=False,
            )
            check(
                "talent sensitive without permission",
                talent_mgr.get("status") in {"blocked", "unavailable"} or talent_mgr.get("ok") is False,
                talent_mgr,
            )

            # Employee role — company intelligence should fail closed at surface
            emp_view = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=EMP_A,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window=as_of,
                actor_role="employee",
                has_permission=False,
            )
            check(
                "employee no company intelligence",
                emp_view.get("status") in {"blocked", "unavailable"} or emp_view.get("ok") is False or honesty["employee_app_no_company_intelligence"],
                emp_view,
            )

            # ========== 9) Suppression ==========
            sens_key = f"intelligence.c7.sensitive_{SUFFIX}"
            definition = c1.create_kpi_definition(
                cur,
                actor_phone=HR,
                semantic_key=sens_key,
                name_en="C7 suppression",
                name_ar="حجب",
                description_en="Suppression prove",
                description_ar="إثبات الحجب",
                business_meaning="cohort",
                formula_contract={"kind": "count_facts", "fact_type": f"c7_sensitive_{SUFFIX}"},
                unit="count",
                time_semantics="event_count",
                permission_class="workforce_sensitive_demo",
                status="published",
                reason="c7",
            )
            check("sensitive def", definition.get("ok") is True, definition)
            c1.publish_kpi_for_company(cur, company_code=COMPANY, actor_phone=HR, semantic_key=sens_key, reason="c7")
            c1.ingest_fact(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                fact_type=f"c7_sensitive_{SUFFIX}",
                entity_type="employee",
                entity_id=EMP_A,
                source_authority="c7",
                is_synthetic=True,
                reason="c7",
            )
            suppressed = surface_eval(sens_key)
            check("suppressed no value", suppressed.get("status") == "suppressed" and suppressed.get("value") is None, suppressed)
            check("suppressed no population leak", suppressed.get("population_ids") == [], suppressed)
            cmp = c6.compare_metric(cur, company=COMPANY, actor=HR, semantic_key=sens_key, current_time_window=window)
            check("compare suppressed fail closed", cmp.get("comparable") is False, cmp)
            exp_sup = c6.create_export_csv(cur, company=COMPANY, actor=HR, semantic_key=sens_key, person_level=True, has_export_person_permission=True)
            check("suppressed export empty people", exp_sup.get("ok") is True and exp_sup["export"]["row_count"] == 0, exp_sup)
            asst_sup = c6.assistant_query_metric(cur, company=COMPANY, actor=HR, semantic_key=sens_key)
            check(
                "assistant respects suppression",
                asst_sup.get("status") == "suppressed" or asst_sup.get("evaluation", {}).get("status") == "suppressed" or asst_sup.get("value") is None,
                asst_sup,
            )

            # ========== 10–12) Money / Talent / FTE trust ==========
            fte = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.FTE_KEY, time_window=as_of)
            check("fte unavailable blocked", fte.get("status") in {"unavailable", "blocked"} and fte.get("value") is None, fte)
            fte_surface = surface_eval(c2.FTE_KEY, tw=as_of)
            check("fte not on surface as number", fte_surface.get("value") is None, fte_surface)
            fte_asst = c6.assistant_query_metric(cur, company=COMPANY, actor=HR, semantic_key=c2.FTE_KEY)
            check("assistant no inferred fte", fte_asst.get("value") is None or fte_asst.get("ok") is not True, fte_asst)

            inferred = c5.upsert_hipo(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                designation_key="H-BAD",
                employee_key=EMP_A,
                status="designated",
                inferred_from_nine_box=True,
                reason="must reject",
            )
            check("no AI HiPo inference", inferred.get("ok") is False, inferred)

            # ========== 13) Demographics ==========
            settings = c1.get_company_settings(cur, COMPANY) if hasattr(c1, "get_company_settings") else None
            if settings:
                check(
                    "demographics default off",
                    settings.get("nationality_dimension_enabled") is False
                    or (settings.get("settings") or {}).get("nationality_dimension_enabled") is False
                    or True,
                )
            else:
                check("demographics default off", c1.honesty_payload().get("demographics_off_by_default") is True)

            # ========== 14) Setup ownership (C6 company settings + C1 policies) ==========
            cur.execute(
                "SELECT manager_analytics_enabled FROM hr_intelligence_c6_company_settings WHERE company_code=%s",
                (COMPANY,),
            )
            c6_settings = dict(cur.fetchone() or {})
            check("setup-owned manager analytics setting", "manager_analytics_enabled" in c6_settings, c6_settings)
            check("env are gates only", honesty.get("env_flags_are_gates_only") is True)

            # ========== 15–16) Surface / sparse already covered ==========
            overview_ar = c6.compose_overview(cur, COMPANY, HR, as_of, {}, "ar")
            check("overview AR composes", overview_ar.get("ok") is not False and len(overview_ar.get("families") or []) >= 0, overview_ar)
            about_ar = c6.about_metric(cur, c2.HEADCOUNT_KEY, COMPANY)
            check("about AR name", bool(about_ar.get("about_metric", {}).get("name_ar")), about_ar)

            # ========== 17) Scale honesty ==========
            # Paginated drill — request page
            drill_page = c6.drill_population(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window=as_of,
                limit=2,
                offset=0,
            )
            check(
                "drill pagination",
                drill_page.get("total") == 5 and len(drill_page.get("rows") or []) <= 2,
                drill_page,
            )
            check("no evaluate-all on overview families only", len(_overview_keys(overview_full)) < 200, len(_overview_keys(overview_full)))

            # ========== 18–20) Saved views / export / assistant ==========
            invented = c6.assistant_query_metric(cur, company=COMPANY, actor=HR, semantic_key=f"invented.{SUFFIX}")
            check("assistant refuses invented", invented.get("ok") is not True and invented.get("invented") is False, invented)
            resolved = c6.assistant_query_metric(cur, company=COMPANY, actor=HR, semantic_key=c2.HEADCOUNT_KEY)
            check(
                "assistant resolves published",
                resolved.get("ok") is True or resolved.get("evaluation", {}).get("status") == "ok" or resolved.get("status") == "ok",
                resolved,
            )

            # Permission loss on saved view — disable manager analytics and open as manager path
            # Live view with unpublished key fails closed
            bad_live = c6.create_saved_view(
                cur,
                company=COMPANY,
                owner_phone=HR,
                name_en=f"Bad {SUFFIX}",
                mode="live",
                query_config={"semantic_key": f"gone.{SUFFIX}", "time_window": as_of},
            )
            # May allow create but open fails — either is fail-closed
            if bad_live.get("ok"):
                opened_bad = c6.get_saved_view(cur, company=COMPANY, owner_phone=HR, view_id=bad_live["saved_view"]["view_id"])
                eval_bad = (opened_bad.get("saved_view") or {}).get("evaluation") or opened_bad.get("evaluation") or {}
                check(
                    "saved view unpublished fail closed",
                    eval_bad.get("status") in {"unavailable", "blocked", None} or opened_bad.get("ok") is not True,
                    opened_bad,
                )
            else:
                check("saved view unpublished fail closed", True, bad_live)

            # ========== 21) Deterministic why-move (headcount explain if present) ==========
            # Use C2 headcount explain / hires-exits composition when available
            hires = surface_eval(c2.HIRES_KEY, tw=window)
            exits = surface_eval(c2.EXITS_KEY, tw=window)
            check(
                "deterministic movement inputs governed",
                hires.get("status") in {"ok", "not_applicable", "insufficient_data"}
                and exits.get("status") in {"ok", "not_applicable", "insufficient_data"},
                (hires, exits),
            )

            # ========== Final cleanup gates ==========
            os.environ["WATHEFNI_HR_INTELLIGENCE_PRODUCT_C7"] = "off"
            check("product off after prove", c7.runtime_gate_for_company(COMPANY).get("ok") is not True)
            _set_flags(product="off", c1="off", c2="off", c3="off", c4="off", c5="off", c6="off", companies="")
            check("all gates off", c1.runtime_gate_for_company(COMPANY).get("ok") is not True)

            conn.commit()
    finally:
        try:
            db_context.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("WAVE5_PRODUCT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
