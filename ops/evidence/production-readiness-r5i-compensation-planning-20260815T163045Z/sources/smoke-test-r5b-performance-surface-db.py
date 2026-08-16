#!/usr/bin/env python3
"""Production Readiness R5B — staging DB Performance surface journeys A–F."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5B{SUFFIX}"[:12]
COMPANY_B = f"R5X{SUFFIX}"[:12]
HR = f"9655012{SUFFIX[:5]}"
EMP = f"emp-{SUFFIX.lower()}"
MGR = f"mgr-{SUFFIX.lower()}"
PEER1 = f"p1-{SUFFIX.lower()}"
PEER2 = f"p2-{SUFFIX.lower()}"
PEER3 = f"p3-{SUFFIX.lower()}"
EMP_PHONE = f"9655021{SUFFIX[:5]}"
MGR_PHONE = f"9655022{SUFFIX[:5]}"
PEER1_PHONE = f"9655023{SUFFIX[:5]}"
PEER2_PHONE = f"9655024{SUFFIX[:5]}"
PEER3_PHONE = f"9655025{SUFFIX[:5]}"


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
        "perf_calibrated_results",
        "perf_calibration_adjustments",
        "perf_calibration_population",
        "perf_calibration_participants",
        "perf_calibration_sessions",
        "perf_pre_calibration_results",
        "perf_development_actions",
        "perf_development_plans",
        "perf_check_ins",
        "perf_c3_competencies",
        "perf_c3_competency_frameworks",
        "perf_review_final_ratings",
        "perf_reviews",
        "perf_cycle_reviewer_assignments",
        "perf_cycle_participants",
        "perf_review_cycles",
        "perf_progress_entries",
        "perf_target_versions",
        "perf_alignment_links",
        "perf_key_results",
        "perf_objectives",
        "perf_measure_definitions",
        "perf_review_templates",
        "perf_rating_scales",
        "performance_goals_c1_company_settings",
        "performance_reviews_c2_company_settings",
        "performance_feedback_c3_company_settings",
        "performance_calibration_c4_company_settings",
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


def run_http_security_tests(app, objective_id: str, cycle_id: str) -> None:
    from fastapi.testclient import TestClient

    hr_perms = ["performance.read", "performance.manage", "performance.calibrate", "performance.sensitive"]
    mgr_perms = ["performance.read", "performance.manage"]
    client = TestClient(app.app)
    registered = any(
        str(getattr(route, "path", "")).startswith("/dashboard/performance") for route in app.app.routes
    )
    check("performance HTTP routes registered", registered is True)

    def use(ctx: dict) -> None:
        app.app.dependency_overrides[app.dashboard_context] = lambda: ctx

    def emp(company: str, employee_key: str, phone: str) -> None:
        app.app.dependency_overrides[app.employee_app_context] = lambda: {
            "company_code": company,
            "employee_key": employee_key,
            "actor_phone": phone,
            "phone": phone,
        }

    try:
        unauth = TestClient(app.app)
        app.app.dependency_overrides.clear()
        bare = unauth.get("/dashboard/performance/workspace")
        check("unauthenticated dashboard not public", bare.status_code in {401, 403}, bare.status_code)
        bare_app = unauth.get("/app/performance")
        check("unauthenticated employee not public", bare_app.status_code in {401, 403, 503}, bare_app.status_code)

        use(_ctx(COMPANY, role="owner", perms=hr_perms, phone=HR, user_id="r5b-hr"))
        ws = client.get("/dashboard/performance/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        objs = client.get("/dashboard/performance/objectives")
        check("HR lists objectives", objs.status_code == 200 and int(objs.json().get("total") or 0) >= 1, objs.text[:300])
        other = client.get(f"/dashboard/performance/objectives/{objective_id}")
        check("HR objective detail", other.status_code == 200, other.status_code)

        use(_ctx(COMPANY_B, role="owner", perms=hr_perms, phone=HR, user_id="r5b-hr-b"))
        cross = client.get(f"/dashboard/performance/objectives/{objective_id}")
        check("tenant isolation 404", cross.status_code == 404, cross.status_code)

        use(_ctx(COMPANY, role="manager", perms=mgr_perms, phone=MGR_PHONE, user_id="r5b-mgr"))
        scoped = client.get("/dashboard/performance/objectives")
        check("manager empty scope fail-closed", scoped.status_code == 200 and int(scoped.json().get("total") or 0) == 0, scoped.text[:300])
        cal = client.get("/dashboard/performance/calibration")
        check("manager calibration forbidden", cal.status_code == 403, cal.status_code)
        launch = client.post(f"/dashboard/performance/cycles/{cycle_id}/launch", json={"reason": "nope"})
        check("manager cannot launch cycle", launch.status_code == 403, launch.status_code)

        use(_ctx(COMPANY, role="owner", perms=["performance.read"], phone=HR, user_id="r5b-hr"))
        raw360 = client.get(f"/dashboard/performance/360?cycle_id={cycle_id}&subject_employee_key={EMP}&raw=true")
        check("raw 360 without sensitive forbidden", raw360.status_code in {403, 422}, raw360.status_code)

        emp(COMPANY, EMP, EMP_PHONE)
        mine = client.get("/app/performance/objectives")
        check("employee sees own goals", mine.status_code == 200, mine.status_code)
        emp(COMPANY, "someone-else", EMP_PHONE)
        stolen = client.get(f"/app/performance/objectives/{objective_id}")
        check("employee IDOR 404", stolen.status_code == 404, stolen.status_code)
        progress = client.post(
            "/app/performance/progress",
            json={"subject_type": "objective", "subject_id": objective_id, "current_value": 1},
        )
        check("employee cannot update others progress", progress.status_code in {403, 404}, progress.status_code)
    finally:
        app.app.dependency_overrides.clear()


def _env_on() -> None:
    for name in (
        "WATHEFNI_PERFORMANCE_GOALS_C1",
        "WATHEFNI_PERFORMANCE_REVIEWS_C2",
        "WATHEFNI_PERFORMANCE_FEEDBACK_C3",
        "WATHEFNI_PERFORMANCE_CALIBRATION_C4",
    ):
        os.environ[name] = "on"
    for name in (
        "WATHEFNI_PERFORMANCE_GOALS_COMPANIES",
        "WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES",
        "WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES",
        "WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES",
    ):
        os.environ[name] = f"{COMPANY},{COMPANY_B}"
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5B — performance surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import performance_goals_c1 as c1
        import performance_reviews_c2 as c2
        import performance_feedback_c3 as c3
        import performance_calibration_c4 as c4
        import performance_surfaces as surfaces
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
    oid = ""
    cid = ""

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (COMPANY, f"R5B {COMPANY}"),
                )
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'performance',true,'r5b','{}'::jsonb,now())
                    ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true
                    """,
                    (COMPANY,),
                )
                surfaces.ensure_all_schemas(cur)
                synced = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5b enable"
                )
                check("sync catalog entitlement", synced.get("ok") is True, synced)
                check("talent still not required", synced.get("talent_required") is False)
                c2.enable_company_performance_reviews(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="r5b 360 on competencies off",
                    review_360_enabled=True,
                    competencies_enabled=False,
                    anonymity_default=True,
                    min_respondent_threshold=3,
                )
                c3.enable_company_performance_feedback(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="r5b competencies off",
                    competencies_enabled=False,
                )
                comps = surfaces.list_competencies(cur, company_code=COMPANY)
                check("competencies optional off", comps.get("enabled") is False, comps)
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (COMPANY_B, f"R5B {COMPANY_B}"),
                )
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'performance',true,'r5b','{}'::jsonb,now())
                    ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true
                    """,
                    (COMPANY_B,),
                )
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY_B, actor_phone=HR, enabled=True, reason="r5b tenant b"
                )

                # A — Goals
                measure = c1.create_measure_definition(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    name_en="Revenue",
                    unit="KWD",
                    direction="higher_is_better",
                    baseline=0,
                    target=100,
                )
                check("measure created", measure.get("ok") is True, measure)
                mid = str(measure["measure"]["measure_id"])
                obj = c1.create_objective(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    title_en="Grow pipeline",
                    title_ar="تنمية الخط",
                    scope="individual",
                    owner_employee_key=EMP,
                )
                check("objective created", obj.get("ok") is True and obj.get("not_generic_goal") is True, obj)
                oid = str(obj["objective"]["objective_id"])
                kr1 = c1.add_key_result(
                    cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, title_en="KR A", measure_id=mid, weight=1
                )
                kr2 = c1.add_key_result(
                    cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, title_en="KR B", measure_id=mid, weight=1
                )
                check("two KRs", kr1.get("ok") is True and kr2.get("ok") is True)
                c1.activate_objective(cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, reason="activate")
                p1 = c1.record_progress(
                    cur,
                    company_code=COMPANY,
                    subject_type="key_result",
                    subject_id=str(kr1["key_result"]["key_result_id"]),
                    actor_phone=EMP_PHONE,
                    current_value=80,
                )
                p2 = c1.record_progress(
                    cur,
                    company_code=COMPANY,
                    subject_type="key_result",
                    subject_id=str(kr2["key_result"]["key_result_id"]),
                    actor_phone=EMP_PHONE,
                    current_value=40,
                )
                check("progress recorded", p1.get("ok") is True and p2.get("ok") is True)
                decorative = c1.record_progress(
                    cur,
                    company_code=COMPANY,
                    subject_type="key_result",
                    subject_id=str(kr1["key_result"]["key_result_id"]),
                    actor_phone=EMP_PHONE,
                    current_value=90,
                    progress_pct=99,
                )
                check("decorative pct rejected", decorative.get("ok") is not True, decorative)
                rollup = c1.objective_rollup(cur, company_code=COMPANY, objective_id=oid)
                check("backend rollup ok", rollup.get("ok") is True, rollup)
                listed = surfaces.list_objectives(cur, company_code=COMPANY, owner_employee_key=EMP)
                check("employee sees own objective", listed.get("total") == 1, listed)
                check(
                    "surface rollup matches authority",
                    (listed["objectives"][0].get("rollup") or {}).get("progress_pct") == rollup.get("progress_pct"),
                    listed,
                )
                other = surfaces.list_objectives(cur, company_code=COMPANY, owner_employee_key="someone-else")
                check("other employee empty not error", other.get("ok") is True and other.get("total") == 0, other)
                scoped = surfaces.list_objectives(cur, company_code=COMPANY, manager_scope_keys=[])
                check("manager empty scope fail-closed empty", scoped.get("total") == 0, scoped)
                mgr_ok = surfaces.list_objectives(cur, company_code=COMPANY, manager_scope_keys=[EMP])
                check("manager in-scope sees goal", mgr_ok.get("total") == 1, mgr_ok)

                # B — Review cycle
                period_start = date.today() - timedelta(days=30)
                period_end = date.today() + timedelta(days=30)
                due = date.today() + timedelta(days=7)
                scale = c2.create_rating_scale(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    name_en="4pt",
                    points=[{"value": 1}, {"value": 2}, {"value": 3}, {"value": 4}],
                )
                tmpl = c2.create_review_template(
                    cur, company_code=COMPANY, actor_phone=HR, name_en="Annual", include_competencies=False
                )
                cycle = c2.create_cycle(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    name_en="FY",
                    period_start=period_start,
                    period_end=period_end,
                    template_id=str(tmpl["template"]["template_id"]),
                    scale_id=str(scale["scale"]["scale_id"]),
                    goals_integration=True,
                    competencies_enabled=False,
                    review_360_enabled=True,
                    anonymity_enabled=True,
                    min_respondent_threshold=3,
                    due_self=due,
                    due_manager=due,
                    due_360=due,
                )
                cid = str(cycle["cycle"]["cycle_id"])
                cfg = c2.configure_cycle(
                    cur,
                    company_code=COMPANY,
                    cycle_id=cid,
                    actor_phone=HR,
                    participants=[
                        {
                            "employee_key": EMP,
                            "employee_phone": EMP_PHONE,
                            "manager_employee_key": MGR,
                            "manager_phone": MGR_PHONE,
                        }
                    ],
                    peer_assignments=[
                        {"subject_employee_key": EMP, "reviewer_role": "peer", "reviewer_employee_key": PEER1, "reviewer_phone": PEER1_PHONE},
                        {"subject_employee_key": EMP, "reviewer_role": "peer", "reviewer_employee_key": PEER2, "reviewer_phone": PEER2_PHONE},
                        {"subject_employee_key": EMP, "reviewer_role": "peer", "reviewer_employee_key": PEER3, "reviewer_phone": PEER3_PHONE},
                    ],
                )
                check("cycle configured", cfg.get("ok") is True, cfg)
                launched = c2.launch_cycle(cur, company_code=COMPANY, cycle_id=cid, actor_phone=HR, reason="launch")
                check("cycle snapshot frozen", launched.get("ok") is True and launched.get("snapshot_frozen") is True, launched)
                mutated = c2.attempt_mutate_launched_setup(
                    cur, company_code=COMPANY, cycle_id=cid, new_name_en="rewritten"
                )
                check("launched cycle immutable", mutated.get("error") == "launched_cycle_immutable", mutated)
                hist = surfaces.get_objective_detail(cur, company_code=COMPANY, objective_id=oid)
                check("objective history present", isinstance(hist.get("history"), list), hist)
                check("objective KRs reconstructable", len(hist.get("key_results") or []) >= 2, hist)
                cur.execute(
                    "SELECT assignment_id, reviewer_role FROM perf_cycle_reviewer_assignments WHERE cycle_id=%s",
                    (cid,),
                )
                asns = {str(r["reviewer_role"]): str(r["assignment_id"]) for r in (cur.fetchall() or [])}
                self_sub = c2.submit_review(
                    cur,
                    company_code=COMPANY,
                    cycle_id=cid,
                    assignment_id=asns["self"],
                    actor_phone=EMP_PHONE,
                    actor_employee_key=EMP,
                    overall_rating_value=4,
                    rationale="self strong",
                )
                mgr_sub = c2.submit_review(
                    cur,
                    company_code=COMPANY,
                    cycle_id=cid,
                    assignment_id=asns["manager"],
                    actor_phone=MGR_PHONE,
                    actor_employee_key=MGR,
                    overall_rating_value=3,
                    rationale="manager solid",
                    confidential_comment="private",
                )
                check("self review submitted", self_sub.get("ok") is True, self_sub)
                check("manager review submitted", mgr_sub.get("ok") is True, mgr_sub)
                layers = c2.get_layer_ratings(cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP)
                check("layers not collapsed", layers.get("collapsed") is False, layers)
                check("self preserved separately", (layers.get("layers") or {}).get("self") is not None, layers)
                check("manager preserved separately", (layers.get("layers") or {}).get("manager") is not None, layers)

                # C — 360
                for role_phone, key in ((PEER1_PHONE, PEER1), (PEER2_PHONE, PEER2)):
                    cur.execute(
                        """
                        SELECT assignment_id FROM perf_cycle_reviewer_assignments
                         WHERE cycle_id=%s AND reviewer_employee_key=%s
                        """,
                        (cid, key),
                    )
                    asn = cur.fetchone()
                    c2.submit_review(
                        cur,
                        company_code=COMPANY,
                        cycle_id=cid,
                        assignment_id=str(asn["assignment_id"]),
                        actor_phone=role_phone,
                        actor_employee_key=key,
                        overall_rating_value=4,
                        rationale="peer",
                    )
                below = c2.get_360_aggregate(
                    cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP, actor_role="employee"
                )
                check("360 fail-closed below threshold", below.get("error") == "anonymity_threshold_not_met", below)
                cur.execute(
                    """
                    SELECT assignment_id FROM perf_cycle_reviewer_assignments
                     WHERE cycle_id=%s AND reviewer_employee_key=%s
                    """,
                    (cid, PEER3),
                )
                asn3 = cur.fetchone()
                c2.submit_review(
                    cur,
                    company_code=COMPANY,
                    cycle_id=cid,
                    assignment_id=str(asn3["assignment_id"]),
                    actor_phone=PEER3_PHONE,
                    actor_employee_key=PEER3,
                    overall_rating_value=5,
                    rationale="peer3",
                )
                agg = c2.get_360_aggregate(
                    cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP, actor_role="manager"
                )
                check("360 aggregate after threshold", agg.get("ok") is True and agg.get("identities_redacted") is True, agg)
                emp_reviews = surfaces.list_reviews(
                    cur, company_code=COMPANY, actor_role="employee", actor_employee_key=EMP
                )
                leaked = any(
                    r.get("reviewer_employee_key") in {PEER1, PEER2, PEER3}
                    for r in (emp_reviews.get("reviews") or [])
                    if r.get("reviewer_role") in {"peer", "subordinate", "stakeholder"}
                )
                check("employee does not see 360 identities", leaked is False, emp_reviews)

                closed = c2.close_cycle(cur, company_code=COMPANY, cycle_id=cid, actor_phone=HR, reason="close")
                check("cycle closed", closed.get("ok") is True, closed)
                layers2 = c2.get_layer_ratings(cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP)
                check("final exists after close", (layers2.get("layers") or {}).get("final") is not None, layers2)
                check("self still distinct after close", (layers2.get("layers") or {}).get("self") is not None, layers2)

                # D — Calibration authorized
                sess = c4.create_calibration_session(
                    cur, company_code=COMPANY, actor_phone=HR, cycle_id=cid, name_en="Cal", reason="create cal"
                )
                check("calibration session", sess.get("ok") is True, sess)
                sid = str((sess.get("session") or {}).get("session_id") or "")
                listed_cal = surfaces.list_calibration_sessions(cur, company_code=COMPANY, actor_phone=HR)
                check("authorized facilitator sees session", any(str(s.get("session_id")) == sid for s in listed_cal.get("sessions") or []), listed_cal)
                forbidden = surfaces.get_calibration_detail(
                    cur, company_code=COMPANY, session_id=sid, actor_phone="96559999999", can_calibrate=False
                )
                check("unauthorized calibration forbidden", forbidden.get("error") == "calibration_forbidden", forbidden)

                # E — Development without Learning
                plan = c3.create_development_plan(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    title_en="Grow writing",
                    reason="dev plan",
                )
                check("development plan Learning-off", plan.get("ok") is True, plan)
                action = c3.create_development_action(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    plan_id=str(plan["plan"]["plan_id"]),
                    title_en="Write weekly",
                    reason="dev action",
                )
                check("development action", action.get("ok") is True, action)
                dev = surfaces.list_development(cur, company_code=COMPANY, employee_key=EMP, actor_role="employee")
                check("employee sees development", bool(dev.get("items")), dev)
                check("learning completion not development", dev.get("learning_completion_is_not_development_completion") is True)

                # F — Talent OFF / high performer ≠ HiPo
                emp_ws = surfaces.employee_workspace(cur, company_code=COMPANY, employee_key=EMP)
                check("employee workspace ok", emp_ws.get("ok") is True, emp_ws)
                check("employee workspace hides calibration", emp_ws.get("calibration_hidden") is True)
                check("employee workspace talent off", emp_ws.get("talent_visible") is False)
                check("no hipo key", "hipo" not in emp_ws)
                summary = surfaces.workspace_summary(cur, company_code=COMPANY, actor_role="hr")
                check("HR workspace summary", summary.get("ok") is True, summary)
                check("HR talent_visible false", summary.get("talent_visible") is False)
                check("performance still catalog enableable", ready.catalog_module_customer_enableable("performance") is True)
                check("talent enableable after R5C does not leak into Performance", ready.customer_enableable("talent") is True)
                check("performance workspace still hides talent", emp_ws.get("talent_visible") is False)
            conn.commit()

        run_http_security_tests(app, oid, cid)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="disable after use"
                )
                cur.execute("SELECT COUNT(*) AS n FROM perf_objectives WHERE company_code=%s", (COMPANY,))
                check("history preserved after disable", int((cur.fetchone() or {}).get("n") or 0) >= 1)
                gated = c1.module_enabled_for_company(cur, COMPANY)
                check("new work blocked when disabled", gated.get("ok") is not True, gated)
            conn.commit()
    finally:
        for name in (
            "WATHEFNI_PERFORMANCE_GOALS_C1",
            "WATHEFNI_PERFORMANCE_REVIEWS_C2",
            "WATHEFNI_PERFORMANCE_FEEDBACK_C3",
            "WATHEFNI_PERFORMANCE_CALIBRATION_C4",
            "WATHEFNI_PERFORMANCE_GOALS_COMPANIES",
            "WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES",
            "WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES",
            "WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES",
        ):
            os.environ[name] = "off" if name.endswith("_C1") or name.endswith("_C2") or name.endswith("_C3") or name.endswith("_C4") else ""
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5B_PERFORMANCE_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
