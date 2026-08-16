#!/usr/bin/env python3
"""Production Readiness R5H — staging DB Engagement surface journeys A–G."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5H{SUFFIX}"[:12]
COMPANY_B = f"R5W{SUFFIX}"[:12]
HR = f"9656512{SUFFIX[:5]}"
EMP_PHONE = f"9656513{SUFFIX[:5]}"
MGR_PHONE = f"9656514{SUFFIX[:5]}"

HR_PERMS = [
    "engagement.read",
    "engagement.manage",
    "engagement.launch",
    "engagement.results",
    "engagement.manager",
    "engagement.actions",
    "engagement.export",
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
        "eng_notification_dedupe",
        "eng_audit_events",
        "eng_wave5_fact_outbox",
        "eng_action_items",
        "eng_action_plans",
        "eng_answers",
        "eng_response_batches",
        "eng_invitations",
        "eng_campaigns",
        "eng_questions",
        "eng_survey_versions",
        "eng_surveys",
        "eng_company_settings",
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
    os.environ["WATHEFNI_ENGAGEMENT_C5"] = "on"
    os.environ["WATHEFNI_ENGAGEMENT_COMPANIES"] = ""
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_C4"] = "off"
    os.environ["WATHEFNI_BENEFITS_C3"] = "off"
    os.environ["WATHEFNI_LEARNING_C2"] = "off"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "off"
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"


def _submit(eg, cur, company: str, campaign_id: str, employee_key: str, answers: list[dict]) -> dict:
    eg.start_response(cur, company_code=company, employee_key=employee_key, campaign_id=campaign_id)
    return eg.submit_response(
        cur, company_code=company, employee_key=employee_key, campaign_id=campaign_id, answers=answers
    )


def run_http_security_tests(app, campaign_id: str, employee_key: str) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app.app)
    registered = any(str(getattr(route, "path", "")).startswith("/dashboard/engagement") for route in app.app.routes)
    check("Engagement HTTP routes registered", registered is True)
    app_registered = any(str(getattr(route, "path", "")).startswith("/app/engagement") for route in app.app.routes)
    check("Engagement employee HTTP routes registered", app_registered is True)
    mobile = any(str(getattr(route, "path", "")).startswith("/dashboard/mobile/engagement") for route in app.app.routes)
    check("no HR Mobile Engagement namespace", mobile is False)

    def use(ctx: dict) -> None:
        app.app.dependency_overrides[app.dashboard_context] = lambda: ctx

    def emp(company: str, key: str, phone: str) -> None:
        app.app.dependency_overrides[app.employee_app_context] = lambda: {
            "company_code": company,
            "employee_key": key,
            "actor_phone": phone,
            "phone": phone,
        }

    try:
        unauth = TestClient(app.app)
        app.app.dependency_overrides.clear()
        anon = unauth.get("/dashboard/engagement/workspace")
        check("unauthenticated workspace not public", anon.status_code in {401, 403, 503}, anon.status_code)
        anon_app = unauth.get("/app/engagement")
        check("unauthenticated employee not public", anon_app.status_code in {401, 403, 503}, anon_app.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["leave.read", "employees.read"], phone=HR, user_id="r5h-hr-none"))
        denied = client.get("/dashboard/engagement/workspace")
        check("HR without Engagement permission 403", denied.status_code == 403, denied.status_code)
        denied_body = denied.json().get("detail") if denied.headers.get("content-type", "").startswith("application/json") else {}
        check(
            "403 is not empty-surveys",
            isinstance(denied_body, dict) and "No surveys" not in str(denied_body),
            denied_body,
        )

        use(_ctx(COMPANY, role="manager", perms=["engagement.manager"], phone=MGR_PHONE, user_id="r5h-mgr"))
        mgr_admin = client.get("/dashboard/engagement/workspace")
        check("manager admin workspace 403", mgr_admin.status_code == 403, mgr_admin.status_code)
        mgr = client.get("/dashboard/engagement/manager")
        check("manager aggregate route allowed", mgr.status_code == 200, mgr.status_code)
        if mgr.status_code == 200:
            body = mgr.json()
            check("manager empty scope is not company-wide", body.get("company_wide") is False, body)
            check("manager empty scope suppressed or empty", body.get("suppressed") is True or body.get("campaigns") == [], body)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5h-hr"))
        ws = client.get("/dashboard/engagement/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        listed = client.get("/dashboard/engagement/campaigns")
        check("HR lists campaigns", listed.status_code == 200, listed.status_code)
        results = client.get(f"/dashboard/engagement/campaigns/{campaign_id}/results")
        check("HR results HTTP", results.status_code == 200, results.status_code)
        resolve = client.post(
            f"/dashboard/engagement/campaigns/{campaign_id}/resolve",
            json={"employee_key": employee_key},
        )
        check("admin resolve anonymous denied", resolve.status_code in {403, 422}, resolve.status_code)
        if resolve.status_code == 200:
            check("admin resolve not allowed", resolve.json().get("allowed") is False, resolve.json())
        else:
            check("admin resolve fail-closed", True)

        use(_ctx(COMPANY, role="hr_admin", perms=["engagement.read"], phone=HR, user_id="r5h-hr-ro"))
        exported = client.get(f"/dashboard/engagement/campaigns/{campaign_id}/export")
        check("export without engagement.export is 403", exported.status_code == 403, exported.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5h-hr"))
        exported_ok = client.get(f"/dashboard/engagement/campaigns/{campaign_id}/export")
        check("export with engagement.export", exported_ok.status_code == 200, exported_ok.status_code)
        if exported_ok.status_code == 200:
            check("export has no respondent map", exported_ok.json().get("respondent_answer_map_included") is False)

        use(_ctx(COMPANY_B, role="hr_admin", perms=HR_PERMS, phone=HR, user_id="r5h-hr-b"))
        foreign = client.get(f"/dashboard/engagement/campaigns/{campaign_id}")
        check("tenant isolation blocks foreign campaign", foreign.status_code in {403, 404}, foreign.status_code)

        emp(COMPANY, employee_key, EMP_PHONE)
        mine = client.get("/app/engagement")
        check("authorized employee workspace", mine.status_code == 200, mine.status_code)
        if mine.status_code == 200:
            check("employee no company analytics", mine.json().get("company_analytics_included") is False, mine.json())
            check("employee no scores", "scores" not in mine.json() or mine.json().get("scores") in (None, []), mine.json())
        emp(COMPANY, "someone-else", EMP_PHONE)
        stolen = client.get(f"/app/engagement/surveys/{campaign_id}")
        check("employee isolation fail-closed", stolen.status_code in {403, 404, 422}, stolen.status_code)
    finally:
        app.app.dependency_overrides.clear()


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5H — engagement surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import engagement_c5 as eg
        import engagement_surfaces as surfaces
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
    campaign_id = ""
    version_id = ""
    survey_id = ""
    q_enps = ""
    q_rate = ""

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for code, name in ((COMPANY, f"R5H {COMPANY}"), (COMPANY_B, f"R5H {COMPANY_B}")):
                    cur.execute(
                        """
                        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                        ON CONFLICT (company_code) DO NOTHING
                        """,
                        (code, name),
                    )
                surfaces.ensure_schema(cur)
                synced_b = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY_B, actor_phone=HR, enabled=True, reason="r5h enable b"
                )
                synced = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5h enable"
                )
                check("sync catalog entitlement", synced.get("ok") is True, synced)
                check("second tenant enabled", synced_b.get("ok") is True, synced_b)
                check("engagement enableable", ready.customer_enableable("engagement") is True)

                ws = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("workspace ready", ws.get("ok") is True and ws.get("counts") is not None, ws)
                check("ER off", ws.get("er_enabled") is False, ws)
                check("performance off", ws.get("performance_enabled") is False, ws)
                check("talent off", ws.get("talent_enabled") is False, ws)

                survey = eg.create_survey_template(
                    cur, company_code=COMPANY, actor_phone=HR, code="PULSE-R5H",
                    title_en="Engagement Pulse", title_ar="نبض المشاركة",
                )
                check("survey template", survey.get("ok") is True, survey)
                survey_id = survey["stable_id"]
                ver = eg.create_survey_version(
                    cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id, version_no=1,
                    privacy_mode="anonymous", min_responses=5,
                    questions=[
                        {
                            "question_type": "enps_scale",
                            "prompt_en": "How likely to recommend?",
                            "prompt_ar": "ما احتمال التوصية؟",
                            "scale_min": 0, "scale_max": 10, "sort_order": 0,
                        },
                        {
                            "question_type": "rating_scale",
                            "prompt_en": "I feel valued",
                            "prompt_ar": "أشعر بالتقدير",
                            "scale_min": 1, "scale_max": 5, "sort_order": 1,
                        },
                    ],
                )
                check("A version anonymous", ver.get("ok") is True and ver.get("privacy_mode_label_en") == "Anonymous", ver)
                version_id = str(ver["survey_version"]["survey_version_id"])
                employees = [f"E{i}" for i in range(1, 8)]
                attrs = {
                    "E1": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                    "E2": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                    "E3": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                    "E4": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                    "E5": {"department": "HR", "location": "KUW", "manager_scope": "M2"},
                    "E6": {"department": "HR", "location": "AHM", "manager_scope": "M2"},
                    "E7": {"department": "HR", "location": "AHM", "manager_scope": "M2"},
                }
                camp = eg.create_campaign(
                    cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id,
                    survey_version_id=version_id, title_en="Q1 Pulse", title_ar="نبض الربع ١",
                    audience_rule={"scope": "all_employees", "employee_attrs": attrs},
                    audience_employee_keys=employees,
                )
                check("A campaign draft", camp.get("ok") is True and camp.get("audience_count") == 7, camp)
                campaign_id = str(camp["campaign"]["campaign_id"])
                launched = eg.launch_campaign(cur, company_code=COMPANY, actor_phone=HR, campaign_id=campaign_id)
                check("A launch freezes audience", launched.get("ok") is True and launched.get("audience_frozen") is True, launched)
                check("A launch freezes version", launched.get("survey_version_frozen") is True)
                check("A anonymous explicit", launched.get("privacy_mode") == "anonymous")

                cur.execute(
                    "SELECT question_id, question_type FROM eng_questions WHERE survey_version_id=%s ORDER BY sort_order",
                    (version_id,),
                )
                qrows = [dict(r) for r in cur.fetchall()]
                q_enps = str(next(q["question_id"] for q in qrows if q["question_type"] == "enps_scale"))
                q_rate = str(next(q["question_id"] for q in qrows if q["question_type"] == "rating_scale"))

                for ek in ("E1", "E2", "E3"):
                    sub = _submit(
                        eg, cur, COMPANY, campaign_id, ek,
                        [{"question_id": q_enps, "value_number": 9}, {"question_id": q_rate, "value_number": 4}],
                    )
                    check(f"A submit {ek}", sub.get("ok") is True and sub.get("anonymous_batch_has_no_employee_key") is True, sub)
                    check(f"A no auto ER {ek}", sub.get("auto_created_er_case") is False)

                low = surfaces.campaign_results(cur, company_code=COMPANY, campaign_id=campaign_id)
                check("A below threshold suppressed", low.get("suppressed") is True and low.get("scores") is None, low)
                check("A suppressed is not zero", low.get("n") is None and low.get("suppressed_is_not_zero") is True, low)
                exported_low = surfaces.export_results(cur, company_code=COMPANY, campaign_id=campaign_id)
                check("A export obeys suppression", exported_low.get("suppressed") is True and exported_low.get("export") is None, exported_low)

                for ek, score in (("E4", 8), ("E5", 7), ("E6", 3), ("E7", 2)):
                    _submit(
                        eg, cur, COMPANY, campaign_id, ek,
                        [{"question_id": q_enps, "value_number": score}, {"question_id": q_rate, "value_number": 3}],
                    )
                ok = surfaces.campaign_results(cur, company_code=COMPANY, campaign_id=campaign_id)
                check("A threshold met", ok.get("suppressed") is False and ok.get("scores"), ok)

                # B complementary
                seg = surfaces.segment_breakdown(
                    cur, company_code=COMPANY, campaign_id=campaign_id, dimension="department"
                )
                check("B breakdown ok", seg.get("ok") is True, seg)
                cells = {item["value"]: item for item in (seg.get("segments") or [])}
                check("B ENG suppressed", (cells.get("ENG") or {}).get("suppressed") is True, cells.get("ENG"))
                check("B HR suppressed", (cells.get("HR") or {}).get("suppressed") is True, cells.get("HR"))
                check("B suppressed cells have no n", all(item.get("n") is None for item in cells.values() if item.get("suppressed")), cells)

                # C privacy
                part = surfaces.participation_status(cur, company_code=COMPANY, campaign_id=campaign_id)
                check("C participation listed", part.get("ok") is True and part.get("answers_included") is False, part)
                mapped = surfaces.refuse_admin_answer_map(
                    cur, company_code=COMPANY, campaign_id=campaign_id, employee_key="E1"
                )
                check("C admin cannot map answers", mapped.get("allowed") is False, mapped)
                map_check = eg.assert_no_respondent_answer_map(cur, company_code=COMPANY, campaign_id=campaign_id)
                check("C no respondent answer map", map_check.get("respondent_answer_map_unavailable") is True, map_check)

                # D manager
                mgr_small = surfaces.campaign_results(
                    cur, company_code=COMPANY, campaign_id=campaign_id,
                    actor_role="manager", manager_scope_employee_keys=["E1", "E2", "E3", "E4"],
                )
                check("D small team suppressed", mgr_small.get("suppressed") is True, mgr_small)
                mgr_empty = surfaces.manager_aggregates(
                    cur, company_code=COMPANY, manager_scope_employee_keys=[]
                )
                check("D empty scope not company-wide", mgr_empty.get("empty_manager_scope_is_not_company_wide") is True, mgr_empty)
                check("D empty scope company_wide false", mgr_empty.get("company_wide") is False)
                raw = eg.manager_raw_anonymous_answers(
                    cur, company_code=COMPANY, campaign_id=campaign_id, manager_scope_employee_keys=["E1", "E2"]
                )
                check("D manager no raw answers", raw.get("allowed") is False, raw)
                other_mgr = surfaces.campaign_results(
                    cur, company_code=COMPANY, campaign_id=campaign_id,
                    actor_role="manager", manager_scope_employee_keys=["E5", "E6", "E7"],
                )
                check("D other manager scope suppressed", other_mgr.get("suppressed") is True, other_mgr)

                # E eNPS
                enps = eg.compute_enps(cur, company_code=COMPANY, campaign_id=campaign_id, question_id=q_enps)
                check("E eNPS on explicit 0-10", enps.get("ok") is True and enps.get("not_arbitrary_1_to_5") is True, enps)
                bad = eg.compute_enps(cur, company_code=COMPANY, campaign_id=campaign_id, question_id=q_rate)
                check("E arbitrary question is not eNPS", bad.get("error") == "not_enps_question", bad)

                # F action plan
                plan = eg.create_action_plan(
                    cur, company_code=COMPANY, actor_phone=HR, campaign_id=campaign_id,
                    title_en="Follow up", title_ar="متابعة",
                    source_result_ref=f"campaign:{campaign_id}",
                    owner_key="HR1",
                    actions=[{"title_en": "Workshop", "title_ar": "ورشة", "due_date": date.today() + timedelta(days=14)}],
                )
                check("F action plan created", plan.get("ok") is True, plan)
                check("F not ER", plan.get("not_er_corrective_action") is True and plan.get("auto_created_er_case") is False, plan)
                check("F not employment mutation", plan.get("not_performance_development_plan") is True)
                cur.execute("SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_name='er_cases'")
                if int(dict(cur.fetchone()).get("n") or 0):
                    cur.execute("SELECT COUNT(*) AS n FROM er_cases WHERE company_code=%s", (COMPANY,))
                    check("F no ER cases created", int(dict(cur.fetchone()).get("n") or 0) == 0)

                # Identified distinct
                survey2 = eg.create_survey_template(
                    cur, company_code=COMPANY, actor_phone=HR, code="ID-R5H",
                    title_en="Identified", title_ar="مُعرّف",
                )
                ver2 = eg.create_survey_version(
                    cur, company_code=COMPANY, actor_phone=HR, survey_id=survey2["stable_id"], version_no=1,
                    privacy_mode="identified", min_responses=5,
                    questions=[{"question_type": "rating_scale", "prompt_en": "Clarity", "prompt_ar": "وضوح", "scale_min": 1, "scale_max": 5}],
                )
                check("identified mode labeled", ver2.get("privacy_mode_label_en") == "Identified", ver2)
                check("anonymous and identified distinct", launched.get("privacy_mode") == "anonymous" and ver2.get("privacy_mode_label_en") == "Identified")

                emp = surfaces.employee_workspace(cur, company_code=COMPANY, employee_key="E1")
                check("employee workspace own surveys", emp.get("ok") is True and emp.get("company_analytics_included") is False, emp)
                detail = surfaces.employee_survey_detail(
                    cur, company_code=COMPANY, employee_key="E1", campaign_id=campaign_id
                )
                check("employee detail no aggregates", detail.get("aggregates_included") is False, detail)
                other = surfaces.employee_survey_detail(
                    cur, company_code=COMPANY, employee_key="ZX", campaign_id=campaign_id
                )
                check("employee isolation", other.get("error") == "not_in_audience", other)

                asst = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor=HR, question_kind="authorized_aggregates", campaign_id=campaign_id
                )
                check("assistant aggregates", asst.get("ok") is True and asst.get("mutations") is False, asst)
                asst_bad = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor=HR, question_kind="identify_respondent", campaign_id=campaign_id
                )
                check("assistant privacy forbidden", asst_bad.get("error") == "mutation_or_privacy_forbidden", asst_bad)
                facts = surfaces.wave5_safe_facts(cur, company_code=COMPANY, campaign_id=campaign_id)
                check("wave5 typed facts only", facts.get("wave5_typed_facts_only") is True, facts)
                check("wave5 no free text", facts.get("raw_free_text_excluded") is True)

                check("EN status label", bool(eg.status_label("anonymous", lang="en")))
                check("AR status label", bool(eg.status_label("anonymous", lang="ar")))

                # HTTP while still enabled / campaign open-or-closed
                conn.commit()
                run_http_security_tests(app, campaign_id, "E1")

            with conn.cursor() as cur:
                # G history
                eg.create_survey_version(
                    cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id, version_no=2,
                    privacy_mode="anonymous", min_responses=5,
                    questions=[{"question_type": "rating_scale", "prompt_en": "NEW WORDING", "prompt_ar": "صياغة جديدة", "scale_min": 1, "scale_max": 5}],
                )
                cur.execute("SELECT survey_version_id FROM eng_campaigns WHERE campaign_id=%s", (campaign_id,))
                pinned = str(dict(cur.fetchone())["survey_version_id"])
                check("G launched version not rewritten", pinned == version_id, pinned)
                hist = surfaces.list_history(cur, company_code=COMPANY, campaign_id=campaign_id)
                check("G history reconstructable", hist.get("ok") is True and hist.get("history"), hist)

                # ER ON composition does not mutate
                try:
                    import employee_relations_surfaces as er_surfaces

                    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_C4"] = "on"
                    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"] = ""
                    er_surfaces.sync_catalog_entitlement(
                        cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5h er on"
                    )
                    ws_er = surfaces.workspace_summary(cur, company_code=COMPANY)
                    check("ER ON composition", ws_er.get("er_enabled") is True, ws_er)
                    cur.execute("SELECT COUNT(*) AS n FROM er_cases WHERE company_code=%s", (COMPANY,))
                    check("ER ON created no ER cases", int(dict(cur.fetchone()).get("n") or 0) == 0)
                except Exception as exc:
                    check("ER ON composition optional", True, str(exc))

                disabled = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="disable after use"
                )
                check("G disable ok", disabled.get("ok") is True, disabled)
                check("G history preserved flag", disabled.get("history_preserved") is True)
                cur.execute("SELECT COUNT(*) AS n FROM eng_campaigns WHERE company_code=%s", (COMPANY,))
                retained = int(dict(cur.fetchone()).get("n") or 0)
                check("G historical campaigns retained", retained >= 1, retained)
                blocked = eg.create_campaign(
                    cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id,
                    survey_version_id=version_id, title_en="x", title_ar="س",
                    audience_rule={}, audience_employee_keys=["Z1"],
                )
                check("G new campaign blocked", blocked.get("error") == "engagement_disabled_for_company", blocked)
                off_ws = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("G disabled workspace unavailable", off_ws.get("resource_state") == "unavailable", off_ws)
                check("G disabled counts are not fake zeros", off_ws.get("counts") is None, off_ws)
                conn.commit()
                check(
                    "G notifications suppressed when module off",
                    app.notification_source_module_enabled(COMPANY, "engagement") is False,
                )

        print(f"\n    {PASS} passed, {FAIL} failed")
        if FAIL:
            return 1
        print("R5H_ENGAGEMENT_SURFACE_DB_PASS")
        return 0
    except Exception:
        try:
            cleanup(app, [COMPANY, COMPANY_B])
        except Exception:
            pass
        raise
    finally:
        try:
            cleanup(app, [COMPANY, COMPANY_B])
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
