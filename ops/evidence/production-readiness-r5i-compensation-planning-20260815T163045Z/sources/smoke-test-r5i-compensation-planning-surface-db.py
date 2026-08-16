#!/usr/bin/env python3
"""Production Readiness R5I — staging DB Compensation Planning surface journeys A–G."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5I{SUFFIX}"[:12]
COMPANY_B = f"R5X{SUFFIX}"[:12]
HR = f"9656512{SUFFIX[:5]}"
MGR_PHONE = f"9656514{SUFFIX[:5]}"

HR_PERMS = [
    "comp_planning.read",
    "comp_planning.manage",
    "comp_planning.recommend",
    "comp_planning.calibrate",
    "comp_planning.approve",
    "comp_planning.finalize",
    "comp_planning.export",
    "comp_planning.manager",
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
        "cp_notification_dedupe",
        "cp_audit_events",
        "cp_wave5_fact_outbox",
        "cp_apply_handoffs",
        "cp_final_decisions",
        "cp_approvals",
        "cp_recommendations",
        "cp_budgets",
        "cp_cycle_snapshots",
        "cp_cycles",
        "cp_salary_bands",
        "cp_company_settings",
        "ja_career_edge",
        "ja_assignment",
        "ja_mapping",
        "ja_profile",
        "ja_level",
        "ja_grade",
        "ja_function",
        "ja_family",
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
    os.environ["WATHEFNI_COMP_PLANNING_C6"] = "on"
    os.environ["WATHEFNI_COMP_PLANNING_COMPANIES"] = ""
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "on"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = ""
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "off"
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "off"
    os.environ["WATHEFNI_ENGAGEMENT_C5"] = "off"
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_C4"] = "off"
    os.environ["WATHEFNI_BENEFITS_C3"] = "off"
    os.environ["WATHEFNI_LEARNING_C2"] = "off"


def _enable_pair(cur, ja, surfaces, company: str) -> dict:
    ja_on = ja.enable_company_job_architecture(
        cur, company_code=company, actor_phone=HR, reason="r5i ja"
    )
    synced = surfaces.sync_catalog_entitlement(
        cur, company_code=company, actor_phone=HR, enabled=True, reason="r5i enable"
    )
    return {"ja": ja_on, "cp": synced}


def run_http_security_tests(app, cycle_id: str) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app.app)
    registered = any(str(getattr(route, "path", "")).startswith("/dashboard/compensation-planning") for route in app.app.routes)
    check("Compensation Planning HTTP routes registered", registered is True)
    app_registered = any(str(getattr(route, "path", "")).startswith("/app/compensation-planning") for route in app.app.routes)
    check("no Employee App Compensation namespace", app_registered is False)
    mobile = any(str(getattr(route, "path", "")).startswith("/dashboard/mobile/compensation-planning") for route in app.app.routes)
    check("no HR Mobile Compensation namespace", mobile is False)

    def use(ctx: dict) -> None:
        app.app.dependency_overrides[app.dashboard_context] = lambda: ctx

    try:
        unauth = TestClient(app.app)
        app.app.dependency_overrides.clear()
        anon = unauth.get("/dashboard/compensation-planning/workspace")
        check("unauthenticated workspace not public", anon.status_code in {401, 403, 503}, anon.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["leave.read", "employees.read"], phone=HR, user_id="r5i-hr-none"))
        denied = client.get("/dashboard/compensation-planning/workspace")
        check("HR without Compensation permission 403", denied.status_code == 403, denied.status_code)
        denied_body = denied.json().get("detail") if denied.headers.get("content-type", "").startswith("application/json") else {}
        check(
            "403 is not empty-cycles",
            isinstance(denied_body, dict) and "No compensation changes" not in str(denied_body),
            denied_body,
        )

        use(_ctx(COMPANY, role="manager", perms=["comp_planning.manager"], phone=MGR_PHONE, user_id="r5i-mgr"))
        mgr_admin = client.get("/dashboard/compensation-planning/workspace")
        check("manager admin workspace 403", mgr_admin.status_code == 403, mgr_admin.status_code)
        mgr = client.get("/dashboard/compensation-planning/manager")
        check("manager worksheet route allowed", mgr.status_code == 200, mgr.status_code)
        if mgr.status_code == 200:
            body = mgr.json()
            check("manager empty scope is not company-wide", body.get("company_wide") is False, body)
            check("manager empty scope is zero rows", body.get("rows") == [], body)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5i-hr"))
        ws = client.get("/dashboard/compensation-planning/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        listed = client.get("/dashboard/compensation-planning/cycles")
        check("HR lists cycles", listed.status_code == 200, listed.status_code)
        sheet = client.get(f"/dashboard/compensation-planning/cycles/{cycle_id}/worksheet")
        check("HR worksheet HTTP", sheet.status_code == 200, sheet.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["comp_planning.read"], phone=HR, user_id="r5i-hr-ro"))
        exported = client.get(f"/dashboard/compensation-planning/cycles/{cycle_id}/export")
        check("export without comp_planning.export is 403", exported.status_code == 403, exported.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5i-hr"))
        exported_ok = client.get(f"/dashboard/compensation-planning/cycles/{cycle_id}/export")
        check("export with comp_planning.export", exported_ok.status_code == 200, exported_ok.status_code)
        if exported_ok.status_code == 200:
            check("export has no hidden rows", exported_ok.json().get("hidden_rows_included") is False)

        use(_ctx(COMPANY, role="hr_admin", perms=["comp_planning.read", "comp_planning.recommend"], phone=HR, user_id="r5i-hr-rec"))
        approve_denied = client.post(
            "/dashboard/compensation-planning/approve",
            json={"cycle_id": cycle_id, "recommendation_id": str(uuid.uuid4()), "decision": "approved"},
        )
        check("recommend-only cannot approve", approve_denied.status_code == 403, approve_denied.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5i-hr"))
        usd = client.post(
            "/dashboard/compensation-planning/cycles",
            json={"code": "USD1", "title_en": "USD", "title_ar": "دولار", "currency": "USD"},
        )
        check("non-KWD create is 422", usd.status_code == 422, usd.status_code)
        usd_detail = usd.json().get("detail") if usd.headers.get("content-type", "").startswith("application/json") else {}
        check(
            "non-KWD names no FX",
            isinstance(usd_detail, dict) and usd_detail.get("error") == "currency_unsupported_no_fx",
            usd_detail,
        )

        use(_ctx(COMPANY_B, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5i-hr-b"))
        foreign = client.get(f"/dashboard/compensation-planning/cycles/{cycle_id}")
        check("tenant isolation blocks foreign cycle", foreign.status_code in {403, 404}, foreign.status_code)
    finally:
        app.app.dependency_overrides.clear()


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5I — compensation planning surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import compensation_planning_c6 as c6
        import compensation_surfaces as surfaces
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
    cycle_id = ""
    decision_id = ""
    original_id = ""
    calibrated_id = ""
    band_id = ""
    grade_id = ""
    snap_base = None
    snap_band_version = None

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for code, name in ((COMPANY, f"R5I {COMPANY}"), (COMPANY_B, f"R5I {COMPANY_B}")):
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
                check("comp planning enableable", ready.customer_enableable("comp_planning") is True)

                blocked = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="need ja first"
                )
                check("JA hard blocks enable", blocked.get("ok") is False and (blocked.get("result") or {}).get("error") == "ja_must_be_enabled", blocked)

                enabled_b = _enable_pair(cur, ja, surfaces, COMPANY_B)
                enabled = _enable_pair(cur, ja, surfaces, COMPANY)
                check("enable JA+Comp A", enabled["ja"].get("ok") is True and enabled["cp"].get("ok") is True, enabled)
                check("enable JA+Comp B", enabled_b["ja"].get("ok") is True and enabled_b["cp"].get("ok") is True, enabled_b)

                ws = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("A workspace ready", ws.get("ok") is True and ws.get("counts") is not None, ws)
                check("A performance off", ws.get("performance_enabled") is False, ws)
                check("A talent off", ws.get("talent_enabled") is False, ws)
                check("A payroll off", ws.get("payroll_enabled") is False, ws)
                check("A workforce planning off", ws.get("workforce_planning_enabled") is False, ws)

                grade = ja.upsert_grade(
                    cur, company_code=COMPANY, actor_phone=HR, code="G7",
                    name_en="Grade 7", name_ar="الدرجة 7", rank_order=7, status="published", reason="r5i",
                )
                check("A JA grade", grade.get("ok") is True, grade)
                grade_id = grade["stable_id"]

                band = surfaces.upsert_salary_band(
                    cur, company_code=COMPANY, actor_phone=HR, code="B7",
                    ja_grade_id=grade_id, minimum=500, midpoint=700, maximum=900,
                    currency="KWD", band_version=1, effective_start=date.today(),
                )
                check("A band belongs to Comp not JA", band.get("ok") is True and band.get("belongs_to_compensation_not_ja") is True, band)
                band_id = str(band["band"]["band_id"])

                usd = surfaces.create_cycle(
                    cur, company_code=COMPANY, actor_phone=HR, code="USD",
                    title_en="USD", title_ar="دولار", currency="USD",
                )
                check("A non-KWD rejected", usd.get("error") == "currency_unsupported_no_fx", usd)

                cycle = surfaces.create_cycle(
                    cur, company_code=COMPANY, actor_phone=HR, code="CY26",
                    title_en="2026 Merit", title_ar="استحقاق ٢٠٢٦",
                    eligibility_rule={"employment_status": "active"},
                    currency="KWD",
                )
                check("A create cycle", cycle.get("ok") is True, cycle)
                cycle_id = str(cycle["cycle"]["cycle_id"])

                launched = surfaces.launch_cycle(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    population=[
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
                    ],
                )
                check("A freeze eligible population", launched.get("ok") is True and launched.get("snapshot_frozen") is True, launched)
                check("A eligible ≠ increase", launched.get("eligible_is_not_increase") is True, launched)
                check("A eligible n", int(launched.get("eligible_n") or 0) == 1, launched)

                snap = surfaces.eligibility_snapshot(cur, company_code=COMPANY, cycle_id=cycle_id)
                e1 = next(item for item in (snap.get("population") or []) if item["employee_key"] == "E1")
                snap_base = e1.get("current_base")
                snap_band_version = e1.get("band_version")
                check("A snapshot frozen JA+band", e1.get("ja_grade_id") == grade_id and e1.get("band_id") == band_id, e1)

                budget = surfaces.create_budget(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    scope_type="company", scope_key="ALL", allocated=200, currency="KWD",
                )
                check("A budget", budget.get("ok") is True, budget)

                overrun = surfaces.create_recommendation(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    employee_key="E1", actor_key="hr-ops", recommendation_type="merit_increase",
                    amount=500, rationale="too big",
                )
                check("A over-budget hard block", overrun.get("error") == "budget_overrun_hard_block", overrun)

                rec = surfaces.create_recommendation(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    employee_key="E1", actor_key="hr-ops", recommendation_type="merit_increase",
                    amount=50, percent=7.7, rationale="solid year",
                )
                check("A recommendation", rec.get("ok") is True and rec.get("recommendation_is_not_approval") is True, rec)
                original_id = str(rec["recommendation"]["recommendation_id"])

                budgets = surfaces.list_budgets(cur, company_code=COMPANY, cycle_id=cycle_id)
                company_budget = (budgets.get("budgets") or [{}])[0]
                check("A budget math converges", company_budget.get("recommended") == 50 and company_budget.get("allocated") == 200, company_budget)

                empty_mgr = surfaces.manager_worksheet(
                    cur, company_code=COMPANY, manager_scope_employee_keys=[], cycle_id=cycle_id,
                )
                check("A empty manager is zero rows", empty_mgr.get("rows") == [] and empty_mgr.get("company_wide") is False, empty_mgr)

                scoped = surfaces.manager_worksheet(
                    cur, company_code=COMPANY, manager_scope_employee_keys=["E1"], cycle_id=cycle_id,
                )
                check("A scoped manager sees report", len(scoped.get("rows") or []) == 1, scoped)
                check("A scoped manager not company-wide", scoped.get("company_wide") is False, scoped)

                # B calibration
                cal = surfaces.calibrate_recommendation(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    original_recommendation_id=original_id, actor_key="hr-cal", amount=45, rationale="peer group",
                )
                check("B calibrate", cal.get("ok") is True and cal.get("original_preserved") is True, cal)
                calibrated_id = str(cal["calibrated"]["recommendation_id"])
                hist = c6.recommendation_history(cur, company_code=COMPANY, cycle_id=cycle_id, employee_key="E1")
                layers = {item["layer"] for item in (hist.get("history") or [])}
                check("B original remains", "original" in layers and hist.get("original_preserved") is True, hist)
                check("B calibrated distinct", "calibrated" in layers and calibrated_id != original_id, hist)

                # C approval + finalize, no salary mutation
                sod = surfaces.approve_recommendation(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    recommendation_id=calibrated_id, approver_key="hr-cal",
                )
                check("C SOD same actor blocked", sod.get("error") == "sod_violation_recommend_approve_same_actor", sod)

                approved = surfaces.approve_recommendation(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    recommendation_id=calibrated_id, approver_key="hr-approver",
                )
                check("C approve", approved.get("ok") is True, approved)

                finalized = surfaces.finalize_cycle(cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id)
                check("C finalize", finalized.get("ok") is True and finalized.get("finalized_is_not_applied") is True, finalized)
                decision_id = str(finalized["decisions"][0]["decision_id"])
                check("C decision not applied", finalized["decisions"][0].get("applied") is False, finalized)
                cur.execute("SELECT applied FROM cp_final_decisions WHERE decision_id=%s", (decision_id,))
                applied_row = dict(cur.fetchone() or {})
                check("C salary/payroll not mutated", applied_row.get("applied") is False, applied_row)

                # D handoff
                payroll_off = surfaces.create_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    decision_id=decision_id, target_authority="wathefni_payroll",
                )
                check("F payroll OFF blocks wathefni_payroll", payroll_off.get("error") == "payroll_handoff_disabled", payroll_off)

                handoff = surfaces.create_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    decision_id=decision_id, target_authority="employment_change_c1",
                )
                check("D explicit package", handoff.get("ok") is True and handoff.get("handoff_created_is_not_salary_changed") is True, handoff)
                check("D not applied", handoff.get("applied") is False or (handoff.get("handoff") or {}).get("applied") is False, handoff)
                replay = surfaces.create_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    decision_id=decision_id, target_authority="employment_change_c1",
                )
                check("D handoff idempotent", replay.get("idempotent_replay") is True, replay)
                exec_status = surfaces.execution_status(cur, company_code=COMPANY, cycle_id=cycle_id)
                check("D handoff ≠ execution", exec_status.get("any_applied") is False and exec_status.get("any_payroll_paid") is False, exec_status)

                c6.enable_company_comp_planning(
                    cur, company_code=COMPANY, actor_phone=HR, reason="r5i payroll on",
                    payroll_handoff_enabled=True, performance_input_enabled=True, talent_input_enabled=True,
                )
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'payroll',true,'r5i','{}'::jsonb,now()),
                           (%s,'performance',true,'r5i','{}'::jsonb,now()),
                           (%s,'talent',true,'r5i','{}'::jsonb,now())
                    ON CONFLICT (company_code, module_key)
                    DO UPDATE SET enabled=true, updated_at=now()
                    """,
                    (COMPANY, COMPANY, COMPANY),
                )
                pay_on = surfaces.create_handoff(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle_id,
                    decision_id=decision_id, target_authority="wathefni_payroll",
                )
                check("D payroll ON uses explicit handoff", pay_on.get("ok") is True, pay_on)
                check("D payroll handoff not paid", pay_on.get("payroll_paid") is False or (pay_on.get("handoff") or {}).get("payroll_paid") is False, pay_on)

                # E Performance/Talent context does not auto-calculate
                cycle2 = surfaces.create_cycle(
                    cur, company_code=COMPANY, actor_phone=HR, code="CY26B",
                    title_en="Context cycle", title_ar="دورة السياق", currency="KWD",
                )
                check("E second cycle", cycle2.get("ok") is True, cycle2)
                cycle2_id = str(cycle2["cycle"]["cycle_id"])
                launched2 = surfaces.launch_cycle(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle2_id,
                    population=[{
                        "employee_key": "E1", "employment_ref": "EMP-E1", "current_base": 650,
                        "currency": "KWD", "ja_grade_id": grade_id, "band_id": band_id,
                        "manager_key": "MGR1", "department": "ENG", "employment_status": "active",
                        "performance_rating": "exceeds", "talent_context": "hipo",
                    }],
                )
                check("E launch with advisory context", launched2.get("ok") is True, launched2)
                surfaces.create_budget(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle2_id,
                    scope_type="company", scope_key="ALL", allocated=100, currency="KWD",
                )
                hipo = surfaces.create_recommendation(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle2_id,
                    employee_key="E1", actor_key="hr-ops", recommendation_type="merit_increase",
                    amount=10, hipo_auto_convert=True,
                )
                check("E HiPo ≠ automatic raise", hipo.get("error") == "hipo_not_automatic_pay", hipo)
                guided = surfaces.create_recommendation(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cycle2_id,
                    employee_key="E1", actor_key="hr-ops", recommendation_type="merit_increase",
                    amount=10, performance_guided=True, talent_guided=True, rationale="advisory only",
                )
                check("E guided context allowed without auto formula", guided.get("ok") is True and guided.get("rating_not_automatic_increase") is True, guided)

                # G historical reconstruction
                band2 = surfaces.upsert_salary_band(
                    cur, company_code=COMPANY, actor_phone=HR, code="B7",
                    ja_grade_id=grade_id, minimum=550, midpoint=800, maximum=1000,
                    currency="KWD", band_version=2, effective_start=date.today(),
                )
                check("G later band v2", band2.get("ok") is True, band2)
                later = surfaces.eligibility_snapshot(cur, company_code=COMPANY, cycle_id=cycle_id)
                later_e1 = next(item for item in (later.get("population") or []) if item["employee_key"] == "E1")
                check("G snapshot base immutable", later_e1.get("current_base") == snap_base, later_e1)
                check("G snapshot band version immutable", later_e1.get("band_version") == snap_band_version, later_e1)
                hist1 = surfaces.list_history(cur, company_code=COMPANY, cycle_id=cycle_id)
                check("G history reconstructable", hist1.get("historically_reconstructable") is True, hist1)

            conn.commit()

        run_http_security_tests(app, cycle_id)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                disabled = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="r5i disable"
                )
                check("G disable ok", disabled.get("ok") is True and disabled.get("history_preserved") is True, disabled)
                after = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("G disable hides workspace", after.get("counts") is None and after.get("resource_state") == "unavailable", after)
                cur.execute("SELECT COUNT(*) AS n FROM cp_cycles WHERE company_code=%s AND cycle_id=%s", (COMPANY, cycle_id))
                kept = dict(cur.fetchone() or {})
                check("G historical cycle preserved", int(kept.get("n") or 0) == 1, kept)
                hist_off = surfaces.list_history(cur, company_code=COMPANY, cycle_id=cycle_id)
                check("G history still reconstructable after disable", bool(hist_off.get("history")), hist_off)

                ja.disable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="r5i ja off")
                ja_off = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("JA off → Comp unavailable", ja_off.get("resource_state") == "unavailable" and ja_off.get("ja_hard_unmet") is True, ja_off)
                check("JA off does not guess worksheet", ja_off.get("counts") is None, ja_off)

                ja.enable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="restore ja")
                surfaces.sync_catalog_entitlement(cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="restore cp")
                assistant = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor=HR, question_kind="change_salary", cycle_id=cycle_id
                )
                check("assistant mutation forbidden", assistant.get("error") == "mutation_forbidden", assistant)

            conn.commit()

    finally:
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5I_COMPENSATION_PLANNING_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
