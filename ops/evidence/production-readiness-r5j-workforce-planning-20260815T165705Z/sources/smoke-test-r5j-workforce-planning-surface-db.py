#!/usr/bin/env python3
"""Production Readiness R5J — staging DB Workforce Planning surface journeys A–I."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5J{SUFFIX}"[:12]
COMPANY_B = f"R5Y{SUFFIX}"[:12]
HR = f"9656513{SUFFIX[:5]}"
MGR_PHONE = f"9656515{SUFFIX[:5]}"

HR_PERMS = [
    "workforce_planning.read",
    "workforce_planning.manage",
    "workforce_planning.plan",
    "workforce_planning.cost",
    "workforce_planning.approve",
    "workforce_planning.execute",
    "workforce_planning.export",
    "workforce_planning.manager",
]


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def cleanup(app, companies: list[str]) -> None:
    import production_data_safety as pds

    pds.require_destructive_scope(companies)
    tables = [
        "wfp_audit_events",
        "wfp_wave5_fact_outbox",
        "wfp_execution_handoffs",
        "wfp_approvals",
        "wfp_gaps",
        "wfp_assumptions",
        "wfp_demand_items",
        "wfp_scenarios",
        "wfp_baseline_rows",
        "wfp_baselines",
        "wfp_plans",
        "wfp_company_settings",
        "requisition_events",
        "requisitions",
        "requisition_settings",
        "ja_career_edge",
        "ja_employment_assignment",
        "ja_org_position_link",
        "ja_optional_external_ref",
        "ja_legacy_mapping",
        "ja_job_profile",
        "ja_level",
        "ja_grade",
        "ja_job_function",
        "ja_job_family",
        "ja_company_settings",
        "company_modules",
        "companies",
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE company_code = ANY(%s)", (companies,))
                except Exception:
                    conn.rollback()
        conn.commit()


def _ctx(company: str, *, role: str, perms: list[str], phone: str, user_id: str) -> dict:
    return {
        "company_code": company,
        "actor_user_id": user_id,
        "actor_phone": phone,
        "hr_phone": phone,
        "phone": phone,
        "actor_role": role,
        "permission_authority": "backend_current",
        "permission_subject_user_id": user_id,
        "permission_subject_company": company,
        "permissions": perms,
        "hr_user": {"status": "active", "role": role},
        "access": {
            "role": role,
            "permissions": perms,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": company,
        },
    }


def _env_on() -> None:
    os.environ["WATHEFNI_WORKFORCE_PLANNING_C7"] = "on"
    os.environ["WATHEFNI_WORKFORCE_PLANNING_COMPANIES"] = ""
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "on"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = ""
    os.environ["WATHEFNI_COMP_PLANNING_C6"] = "off"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "off"
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_ENGAGEMENT_C5"] = "off"
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_C4"] = "off"
    os.environ["WATHEFNI_BENEFITS_C3"] = "off"
    os.environ["WATHEFNI_LEARNING_C2"] = "off"
    os.environ["WATHEFNI_REQUISITIONS"] = "off"
    os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = ""


def _enable_pair(cur, ja, surfaces, company: str, **wfp_kwargs) -> dict:
    ja_on = ja.enable_company_job_architecture(
        cur, company_code=company, actor_phone=HR, reason="r5j ja"
    )
    synced = surfaces.sync_catalog_entitlement(
        cur, company_code=company, actor_phone=HR, enabled=True, reason="r5j enable"
    )
    if wfp_kwargs:
        import workforce_planning_c7 as c7

        c7.enable_company_workforce_planning(
            cur, company_code=company, actor_phone=HR, reason="r5j flags", **wfp_kwargs
        )
    return {"ja": ja_on, "wfp": synced}


def _seed_ja(cur, ja, company: str) -> tuple[str, str]:
    fam = ja.upsert_job_family(
        cur, company_code=company, actor_phone=HR, code="OPS",
        name_en="Ops", name_ar="عمليات", status="published", reason="r5j",
    )
    fn = ja.upsert_job_function(
        cur, company_code=company, actor_phone=HR, family_id=fam["stable_id"], code="SVC",
        name_en="Service", name_ar="خدمة", status="published", reason="r5j",
    )
    grade = ja.upsert_grade(
        cur, company_code=company, actor_phone=HR, code="G3",
        name_en="Grade 3", name_ar="الدرجة 3", rank_order=3, status="published", reason="r5j",
    )
    profile = ja.upsert_job_profile(
        cur, company_code=company, actor_phone=HR, function_id=fn["stable_id"], code="ANL",
        name_en="Analyst", name_ar="محلل", status="published",
        default_grade_id=grade["stable_id"], reason="r5j",
    )
    return str(profile["stable_id"]), str(grade["stable_id"])


def run_http_security_tests(app, plan_id: str) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app.app)
    registered = any(str(getattr(route, "path", "")).startswith("/dashboard/workforce-planning") for route in app.app.routes)
    check("Workforce Planning HTTP routes registered", registered is True)
    app_registered = any(str(getattr(route, "path", "")).startswith("/app/workforce-planning") for route in app.app.routes)
    check("no Employee App Workforce Planning namespace", app_registered is False)
    mobile = any(str(getattr(route, "path", "")).startswith("/dashboard/mobile/workforce-planning") for route in app.app.routes)
    check("no HR Mobile Workforce Planning namespace", mobile is False)

    def use(ctx: dict) -> None:
        app.app.dependency_overrides[app.dashboard_context] = lambda: ctx

    try:
        unauth = TestClient(app.app)
        app.app.dependency_overrides.clear()
        anon = unauth.get("/dashboard/workforce-planning/workspace")
        check("unauthenticated workspace not public", anon.status_code in {401, 403, 503}, anon.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["leave.read", "employees.read"], phone=HR, user_id="r5j-hr-none"))
        denied = client.get("/dashboard/workforce-planning/workspace")
        check("HR without Workforce Planning permission 403", denied.status_code == 403, denied.status_code)
        denied_body = denied.json().get("detail") if denied.headers.get("content-type", "").startswith("application/json") else {}
        check(
            "403 is not empty-plans / not 0 planned hires",
            isinstance(denied_body, dict)
            and "No workforce gap" not in str(denied_body)
            and "0 planned hires" not in str(denied_body)
            and "empty" not in str(denied_body.get("resource_state") or ""),
            denied_body,
        )

        use(_ctx(COMPANY, role="manager", perms=["workforce_planning.manager"], phone=MGR_PHONE, user_id="r5j-mgr"))
        mgr_admin = client.get("/dashboard/workforce-planning/workspace")
        check("manager admin workspace 403", mgr_admin.status_code == 403, mgr_admin.status_code)
        mgr = client.get("/dashboard/workforce-planning/manager")
        check("manager workspace route allowed", mgr.status_code == 200, mgr.status_code)
        if mgr.status_code == 200:
            body = mgr.json()
            check("manager empty scope is not company-wide", body.get("company_wide") is False, body)
            check("manager empty scope is zero demand", body.get("demand") == [], body)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5j-hr"))
        ws = client.get("/dashboard/workforce-planning/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        listed = client.get("/dashboard/workforce-planning/plans")
        check("HR lists plans", listed.status_code == 200, listed.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["workforce_planning.read"], phone=HR, user_id="r5j-hr-ro"))
        exported = client.get(f"/dashboard/workforce-planning/plans/{plan_id}/export")
        check("export without workforce_planning.export is 403", exported.status_code == 403, exported.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5j-hr"))
        exported_ok = client.get(f"/dashboard/workforce-planning/plans/{plan_id}/export")
        check("export with workforce_planning.export", exported_ok.status_code == 200, exported_ok.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["workforce_planning.read", "workforce_planning.plan"], phone=HR, user_id="r5j-hr-plan"))
        approve_denied = client.post(
            "/dashboard/workforce-planning/approve",
            json={"plan_id": plan_id, "scenario_id": str(uuid.uuid4()), "decision": "approved"},
        )
        check("planner-only cannot approve", approve_denied.status_code == 403, approve_denied.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5j-hr"))
        usd = client.post(
            "/dashboard/workforce-planning/plans",
            json={"code": "USD1", "title_en": "USD", "title_ar": "دولار", "currency": "USD"},
        )
        check("non-KWD create is 422", usd.status_code == 422, usd.status_code)
        usd_detail = usd.json().get("detail") if usd.headers.get("content-type", "").startswith("application/json") else {}
        check(
            "non-KWD names no FX",
            isinstance(usd_detail, dict) and usd_detail.get("error") == "currency_unsupported_no_fx",
            usd_detail,
        )

        use(_ctx(COMPANY_B, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5j-hr-b"))
        foreign = client.get(f"/dashboard/workforce-planning/plans/{plan_id}")
        check("tenant isolation blocks foreign plan", foreign.status_code in {403, 404}, foreign.status_code)
    finally:
        app.app.dependency_overrides.clear()


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5J — workforce planning surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import workforce_planning_c7 as c7
        import workforce_planning_surfaces as surfaces
        import job_architecture_c1 as ja
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("      SKIP  psycopg2 unavailable")
            return 1
        raise

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"      SKIP  database unavailable ({type(exc).__name__}: {exc})")
        return 1

    pds.require_non_production_target()
    app.ensure_schema()
    cleanup(app, [COMPANY, COMPANY_B])
    _env_on()
    plan_id = ""
    baseline_id = ""
    scenario_id = ""
    growth_id = ""
    demand_id = ""
    profile_id = ""
    grade_id = ""
    baseline_hc = 0

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for code, name in ((COMPANY, f"R5J {COMPANY}"), (COMPANY_B, f"R5J {COMPANY_B}")):
                    cur.execute(
                        """
                        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                        ON CONFLICT (company_code) DO NOTHING
                        """,
                        (code, name),
                    )
                ja.ensure_job_architecture_c1_schema(cur)
                surfaces.ensure_schema(cur)
                check("workforce planning enableable", ready.customer_enableable("workforce_planning") is True)

                blocked = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="need ja first"
                )
                check("JA hard blocks enable", blocked.get("ok") is False and (blocked.get("result") or {}).get("error") == "ja_must_be_enabled", blocked)

                enabled_b = _enable_pair(cur, ja, surfaces, COMPANY_B)
                enabled = _enable_pair(cur, ja, surfaces, COMPANY)
                check("enable JA+WFP A", enabled["ja"].get("ok") is True and enabled["wfp"].get("ok") is True, enabled)
                check("enable JA+WFP B", enabled_b["ja"].get("ok") is True and enabled_b["wfp"].get("ok") is True, enabled_b)

                ws = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("A workspace ready", ws.get("ok") is True and ws.get("counts") is not None, ws)
                check("I recruiting off", ws.get("recruiting_enabled") is False, ws)
                check("I comp off", ws.get("comp_planning_enabled") is False, ws)
                check("I talent off", ws.get("talent_enabled") is False, ws)
                check("I payroll off", ws.get("payroll_enabled") is False, ws)
                check("I performance off", ws.get("performance_enabled") is False, ws)

                profile_id, grade_id = _seed_ja(cur, ja, COMPANY)
                check("A JA profile", bool(profile_id), profile_id)

                ja.assign_employment_architecture(
                    cur, company_code=COMPANY, actor_phone=HR, employee_key="E1",
                    effective_start=date(2026, 1, 1), profile_id=profile_id, grade_id=grade_id, reason="actual e1",
                )
                ja.assign_employment_architecture(
                    cur, company_code=COMPANY, actor_phone=HR, employee_key="E2",
                    effective_start=date(2026, 1, 1), profile_id=profile_id, grade_id=grade_id, reason="actual e2",
                )
                actual_before = surfaces.canonical_actual_headcount(cur, company_code=COMPANY)
                check("A actual workforce exists", actual_before == 2, actual_before)

                usd = surfaces.create_plan(
                    cur, company_code=COMPANY, actor_phone=HR, code="USD",
                    title_en="USD", title_ar="دولار", currency="USD",
                )
                check("D non-KWD rejected", usd.get("error") == "currency_unsupported_no_fx", usd)

                plan = surfaces.create_plan(
                    cur, company_code=COMPANY, actor_phone=HR, code="FY26Q1",
                    title_en="FY26 Q1", title_ar="الربع ١",
                    horizon="quarterly", currency="KWD",
                    period_start=date(2026, 1, 1), period_end=date(2026, 3, 31), fiscal_year=2026,
                )
                check("A create plan", plan.get("ok") is True, plan)
                plan_id = str(plan["plan"]["plan_id"])

                baseline = surfaces.freeze_baseline(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, as_of_date=date(2026, 1, 1),
                )
                check("A freeze baseline from actual", baseline.get("ok") is True and baseline.get("frozen") is True, baseline)
                check("A not second SoT", baseline.get("not_second_actual_sot") is True, baseline)
                baseline_id = str(baseline["baseline"]["baseline_id"])
                baseline_hc = int(baseline["baseline"]["headcount_total"])
                check("A baseline hc = actual at freeze", baseline_hc == 2, baseline)

                ja.assign_employment_architecture(
                    cur, company_code=COMPANY, actor_phone=HR, employee_key="E3",
                    effective_start=date(2026, 2, 1), profile_id=profile_id, grade_id=grade_id, reason="later actual",
                )
                actual_after = surfaces.canonical_actual_headcount(cur, company_code=COMPANY)
                check("A later actual changed", actual_after == 3, actual_after)
                frozen = surfaces.get_baseline(cur, company_code=COMPANY, plan_id=plan_id)
                check("A baseline unchanged after actual change", int((frozen.get("baseline") or {}).get("headcount_total") or 0) == baseline_hc, frozen)
                check("A baseline rows still 2", len(frozen.get("rows") or []) == 2, frozen)
                re_freeze = surfaces.freeze_baseline(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, as_of_date=date(2026, 2, 1),
                )
                check("A baseline immutable once frozen", re_freeze.get("error") == "baseline_already_frozen", re_freeze)

                base = surfaces.create_scenario(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                    code="BASE", scenario_type="base", title_en="Base", title_ar="أساسي",
                )
                growth = surfaces.create_scenario(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                    code="GROW", scenario_type="growth", title_en="Growth", title_ar="نمو",
                )
                check("B base scenario", base.get("ok") is True and base.get("scenario_distinct_from_actual") is True, base)
                check("B growth scenario", growth.get("ok") is True, growth)
                scenario_id = str(base["scenario"]["scenario_id"])
                growth_id = str(growth["scenario"]["scenario_id"])

                assum = surfaces.upsert_assumption(
                    cur, company_code=COMPANY, actor_phone=HR, scenario_id=scenario_id,
                    assumption_key="expected_hires", value={"count": 2, "lead_time_days": 45},
                    source="explicit_planner",
                )
                check("C assumption versioned", assum.get("ok") is True and assum.get("explicit_versioned") is True, assum)
                silent = surfaces.upsert_assumption(
                    cur, company_code=COMPANY, actor_phone=HR, scenario_id=scenario_id,
                    assumption_key="attrition", value={"rate": 0.1}, source="wave5_turnover_explicit",
                )
                check("C no silent Wave 5 forecast", silent.get("error") == "wave5_turnover_must_be_explicitly_selected", silent)

                d_new = surfaces.add_demand(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                    demand_type="new_headcount", quantity=2, ja_profile_id=profile_id, ja_grade_id=grade_id,
                    org_unit="ENG", reason_en="growth", planned_unit_cost=700, owner_key="MGR1",
                )
                check("B/C new headcount explicit", d_new.get("ok") is True and d_new.get("planned_position_ne_actual_position") is True, d_new)
                demand_id = str(d_new["demand"]["demand_id"])
                repl = surfaces.add_demand(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                    demand_type="replacement", quantity=1, ja_profile_id=profile_id, ja_grade_id=grade_id,
                    reason_en="backfill resigned analyst", planned_unit_cost=650,
                )
                check("C replacement explicit", repl.get("ok") is True, repl)
                red = surfaces.add_demand(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                    demand_type="planned_reduction", quantity=1, ja_profile_id=profile_id,
                    reason_en="restructure",
                )
                check("C reduction explicit", red.get("ok") is True, red)
                surfaces.add_demand(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=growth_id,
                    demand_type="new_headcount", quantity=5, ja_profile_id=profile_id, ja_grade_id=grade_id,
                    reason_en="aggressive growth", planned_unit_cost=700,
                )
                growth_demand = surfaces.list_demand(cur, company_code=COMPANY, scenario_id=growth_id)
                base_demand = surfaces.list_demand(cur, company_code=COMPANY, scenario_id=scenario_id)
                check("B growth did not mutate base demand", len(base_demand.get("demand") or []) == 3, base_demand)
                check("B base did not mutate growth demand", len(growth_demand.get("demand") or []) == 1, growth_demand)
                check("B actual still 3", surfaces.canonical_actual_headcount(cur, company_code=COMPANY) == 3)

                proj = surfaces.project_headcount(cur, company_code=COMPANY, scenario_id=scenario_id)
                check("C projection reproducible", proj.get("ok") is True and proj.get("reproducible") is True, proj)
                check("C planned hc = 4", int(proj.get("planned_headcount") or 0) == 4, proj)
                check("C no AI black box", proj.get("no_ai_black_box") is True, proj)
                proj2 = surfaces.project_headcount(cur, company_code=COMPANY, scenario_id=scenario_id)
                check("C same inputs same result", proj2.get("planned_headcount") == proj.get("planned_headcount"), proj2)

                cost = surfaces.project_planned_cost(cur, company_code=COMPANY, scenario_id=scenario_id)
                check("D planned cost labeled", cost.get("ok") is True and cost.get("planned_cost_ne_finalized_payroll_cost") is True, cost)
                check("D currency KWD", cost.get("currency") == "KWD", cost)
                check("D not payroll", cost.get("not_finalized_payroll_cost") is True, cost)

                gap = surfaces.compute_gap(cur, company_code=COMPANY, scenario_id=scenario_id)
                check("gap definition driven", gap.get("ok") is True and gap.get("no_universal_workforce_gap_score") is True, gap)
                cmp = surfaces.compare_scenarios(
                    cur, company_code=COMPANY, scenario_a=scenario_id, scenario_b=growth_id,
                )
                check("compare compatible", cmp.get("ok") is True and cmp.get("compatible") is True, cmp)

                empty_mgr = surfaces.manager_workspace(cur, company_code=COMPANY, manager_scope_employee_keys=[])
                check("manager empty scope zero rows", empty_mgr.get("demand") == [] and empty_mgr.get("company_wide") is False, empty_mgr)

                submitted = surfaces.submit_plan(cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id)
                check("E submit", submitted.get("ok") is True, submitted)
                approved = surfaces.approve_scenario(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                    scenario_id=scenario_id, approver_key="approver-1",
                )
                check("E approve", approved.get("ok") is True and approved.get("approved_ne_execution") is True, approved)
                check("E actual unchanged", approved.get("actual_workforce_unchanged") is True, approved)
                check("E actual still 3 after approve", surfaces.canonical_actual_headcount(cur, company_code=COMPANY) == 3)
                immut = surfaces.add_demand(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id, scenario_id=scenario_id,
                    demand_type="new_headcount", quantity=1, ja_profile_id=profile_id,
                )
                check("E approved scenario immutable", immut.get("error") == "scenario_not_open_for_demand", immut)

                handoff = surfaces.create_execution_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                    scenario_id=scenario_id, demand_id=demand_id,
                )
                check("F recruiting OFF handoff", handoff.get("ok") is True, handoff)
                check("F works recruiting off", handoff.get("works_recruiting_off") is True, handoff)
                check("F no employment mutate", handoff.get("employment_mutated_by_wfp") is False, handoff)
                check("F no auto post/hire", handoff.get("no_auto_post_hire") is True, handoff)
                retry = surfaces.create_execution_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                    scenario_id=scenario_id, demand_id=demand_id,
                )
                check("F/G handoff idempotent", retry.get("replayed") is True and retry.get("handoff_idempotent") is True, retry)

                avp = surfaces.actual_vs_plan(cur, company_code=COMPANY, scenario_id=scenario_id)
                check("H actual vs plan uses canonical actual", avp.get("ok") is True and avp.get("wfp_not_actual_sot") is True, avp)
                check("H actual is 3 not baseline 2", int(avp.get("actual_from_canonical") or 0) == 3, avp)
                check("H planned is governed 4", int(avp.get("planned") or 0) == 4, avp)

                cur.execute(
                    "SELECT fact_type, truth_plane FROM wfp_wave5_fact_outbox WHERE company_code=%s",
                    (COMPANY,),
                )
                facts = [dict(r) for r in cur.fetchall()]
                types = {item["fact_type"] for item in facts}
                check("Wave 5 planned demand fact", "workforce_planning.planned_demand" in types, types)
                check("Wave 5 planned hc fact", "workforce_planning.planned_headcount" in types, types)
                check("no actual-plane planning contamination", all(item["truth_plane"] != "actual" or str(item["fact_type"]).startswith("wfp.actual_vs_plan") for item in facts), facts)

                hist = surfaces.list_history(cur, company_code=COMPANY, plan_id=plan_id)
                check("history reconstructable", hist.get("historically_reconstructable") is True, hist)

                os.environ["WATHEFNI_REQUISITIONS"] = "on"
                os.environ["WATHEFNI_REQUISITIONS_COMPANIES"] = COMPANY
                import requisitions as rq

                rq.seed_settings(cur, COMPANY)
                rq.set_settings(cur, COMPANY, enabled=True)
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'requisitions',true,'r5j','{}'::jsonb,now())
                    ON CONFLICT (company_code, module_key)
                    DO UPDATE SET enabled=true, updated_at=now()
                    """,
                    (COMPANY,),
                )
                c7.enable_company_workforce_planning(
                    cur, company_code=COMPANY, actor_phone=HR, reason="enable recruiting handoff",
                    recruiting_handoff_enabled=True,
                )
                repl_id = str(repl["demand"]["demand_id"])
                rh = surfaces.create_execution_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                    scenario_id=scenario_id, demand_id=repl_id, target_authority="wave1_requisition_draft",
                )
                check("G recruiting ON handoff", rh.get("ok") is True and rh.get("no_auto_post_hire") is True, rh)
                check("G draft only or fail-closed", rh.get("draft_requisition_only") is True or rh.get("works_recruiting_off") is True, rh)
                check("G no job posted", rh.get("job_posted") is False, rh)
                check("G no hire", rh.get("hire_created") is False, rh)
                req_id = (rh.get("handoff") or {}).get("requisition_id")
                retry_g = surfaces.create_execution_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, plan_id=plan_id,
                    scenario_id=scenario_id, demand_id=repl_id, target_authority="wave1_requisition_draft",
                )
                check("G retry does not duplicate", retry_g.get("replayed") is True or retry_g.get("handoff_idempotent") is True, retry_g)
                if req_id:
                    cur.execute(
                        "SELECT COUNT(*) AS n FROM requisitions WHERE company_code=%s AND requisition_id=%s",
                        (COMPANY, req_id),
                    )
                    check("G exactly one linked requisition row", int(dict(cur.fetchone() or {}).get("n") or 0) == 1)
                    cur.execute("SELECT status FROM requisitions WHERE requisition_id=%s", (req_id,))
                    st = dict(cur.fetchone() or {}).get("status")
                    check("G linked requisition is draft", st == "draft", st)

                assistant = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor=HR, question_kind="generate_requisition", scenario_id=scenario_id
                )
                check("assistant mutation forbidden", assistant.get("error") == "mutation_forbidden", assistant)
                asst_ai = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor=HR, question_kind="ai_forecast"
                )
                check("assistant no AI forecast", asst_ai.get("error") == "mutation_forbidden", asst_ai)

            conn.commit()

        run_http_security_tests(app, plan_id)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                disabled = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="r5j disable"
                )
                check("disable ok", disabled.get("ok") is True and disabled.get("history_preserved") is True, disabled)
                check("disable does not delete requisitions", disabled.get("linked_requisitions_not_deleted") is True, disabled)
            conn.commit()
            if hasattr(app, "notification_source_module_enabled"):
                check(
                    "disable suppresses new notifications",
                    app.notification_source_module_enabled(COMPANY, "workforce_planning") is False,
                )
            with conn.cursor() as cur:
                after = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("disable hides workspace", after.get("counts") is None and after.get("resource_state") == "unavailable", after)
                cur.execute("SELECT COUNT(*) AS n FROM wfp_plans WHERE company_code=%s AND plan_id=%s", (COMPANY, plan_id))
                kept = dict(cur.fetchone() or {})
                check("historical plan preserved", int(kept.get("n") or 0) == 1, kept)
                hist_off = surfaces.list_history(cur, company_code=COMPANY, plan_id=plan_id)
                check("history still reconstructable after disable", bool(hist_off.get("history")), hist_off)
                cur.execute("SELECT COUNT(*) AS n FROM wfp_execution_handoffs WHERE company_code=%s", (COMPANY,))
                check("handoffs retained after disable", int(dict(cur.fetchone() or {}).get("n") or 0) >= 1)

                ja.disable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="r5j ja off")
                ja_off = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("JA off → WFP unavailable", ja_off.get("resource_state") == "unavailable" and ja_off.get("ja_hard_unmet") is True, ja_off)
                check("JA off does not guess plans", ja_off.get("counts") is None, ja_off)

            conn.commit()

    finally:
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5J_WORKFORCE_PLANNING_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
