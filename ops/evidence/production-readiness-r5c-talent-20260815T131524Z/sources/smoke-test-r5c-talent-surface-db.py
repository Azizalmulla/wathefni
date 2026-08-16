#!/usr/bin/env python3
"""Production Readiness R5C — staging DB Talent surface journeys A–F."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5C{SUFFIX}"[:12]
COMPANY_B = f"R5Y{SUFFIX}"[:12]
HR = f"9656012{SUFFIX[:5]}"
EMP = f"emp-{SUFFIX.lower()}"
EMP2 = f"em2-{SUFFIX.lower()}"
MGR = f"mgr-{SUFFIX.lower()}"
EMP_PHONE = f"9656021{SUFFIX[:5]}"
MGR_PHONE = f"9656022{SUFFIX[:5]}"


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
        "talent_successor_nominations",
        "talent_succession_coverage_facts",
        "talent_succession_plans",
        "talent_critical_roles",
        "talent_hipo_designations",
        "talent_review_population",
        "talent_review_participants",
        "talent_reviews",
        "talent_nine_box_configs",
        "talent_performance_evidence_links",
        "talent_readiness_observations",
        "talent_potential_assessments",
        "talent_potential_frameworks",
        "talent_skill_history",
        "talent_skills",
        "talent_dimension_facts",
        "talent_profiles",
        "talent_profile_c5_audit",
        "talent_succession_c6_audit",
        "talent_profile_c5_company_settings",
        "talent_succession_c6_company_settings",
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


def run_http_security_tests(app, employee_key: str) -> None:
    from fastapi.testclient import TestClient

    hr_perms = ["talent.read", "talent.manage", "talent.sensitive", "talent.review", "talent.succession"]
    mgr_perms = ["talent.read", "talent.manage"]
    client = TestClient(app.app)
    registered = any(
        str(getattr(route, "path", "")).startswith("/dashboard/posthire/talent") for route in app.app.routes
    )
    check("talent HTTP routes registered", registered is True)

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
        bare = unauth.get("/dashboard/posthire/talent/workspace")
        check("unauthenticated dashboard not public", bare.status_code in {401, 403}, bare.status_code)
        bare_app = unauth.get("/app/talent")
        check("unauthenticated employee not public", bare_app.status_code in {401, 403, 503}, bare_app.status_code)

        use(_ctx(COMPANY, role="owner", perms=hr_perms, phone=HR, user_id="r5c-hr"))
        ws = client.get("/dashboard/posthire/talent/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        alias = client.get("/dashboard/talent/workspace")
        check("alias /dashboard/talent works", alias.status_code == 200, alias.status_code)
        people = client.get("/dashboard/posthire/talent/profiles")
        check("HR lists profiles", people.status_code == 200, people.text[:300])

        use(_ctx(COMPANY_B, role="owner", perms=hr_perms, phone=HR, user_id="r5c-hr-b"))
        cross = client.get(f"/dashboard/posthire/talent/profiles/{employee_key}")
        check("tenant isolation 404", cross.status_code == 404, cross.status_code)

        use(_ctx(COMPANY, role="manager", perms=mgr_perms, phone=MGR_PHONE, user_id="r5c-mgr"))
        scoped = client.get("/dashboard/posthire/talent/profiles")
        check(
            "manager empty scope fail-closed",
            scoped.status_code == 200 and int(scoped.json().get("total") or 0) == 0,
            scoped.text[:300],
        )
        hipo = client.post(
            "/dashboard/posthire/talent/hipo",
            json={"employee_key": employee_key, "status": "designated", "rationale": "nope", "reason": "nope"},
        )
        check("manager HiPo without sensitive forbidden", hipo.status_code == 403, hipo.status_code)
        succ = client.get("/dashboard/posthire/talent/succession")
        check("manager succession without perm forbidden", succ.status_code == 403, succ.status_code)

        use(_ctx(COMPANY, role="owner", perms=["talent.read"], phone=HR, user_id="r5c-hr-ro"))
        write = client.post(
            "/dashboard/posthire/talent/profiles",
            json={"employee_key": "x", "reason": "nope"},
        )
        check("HR without manage denied write", write.status_code == 403, write.status_code)

        emp(COMPANY, employee_key, EMP_PHONE)
        mine = client.get("/app/talent")
        check("employee sees own workspace", mine.status_code == 200, mine.status_code)
        body = mine.json() if mine.status_code == 200 else {}
        check("employee cannot see potential", "potential" not in body, list(body.keys())[:12])
        check("employee cannot see hipo", "hipo" not in body)
        check("employee cannot see succession", "succession" not in body and "nominations" not in body)
        emp(COMPANY, "someone-else", EMP_PHONE)
        stolen = client.get("/app/talent/profile")
        check("employee IDOR stays self or empty", stolen.status_code in {200, 404}, stolen.status_code)
        if stolen.status_code == 200:
            stolen_key = (stolen.json().get("profile") or {}).get("employee_key")
            check("employee IDOR does not return other key", stolen_key != employee_key, stolen_key)
    finally:
        app.app.dependency_overrides.clear()


def _env_on() -> None:
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = f"{COMPANY},{COMPANY_B}"
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = f"{COMPANY},{COMPANY_B}"
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_REVIEWS_C2"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_C4"] = "off"


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5C — talent surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import talent_profile_c5 as c5
        import talent_succession_c6 as c6
        import talent_surfaces as surfaces
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

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for code, name in ((COMPANY, f"R5C {COMPANY}"), (COMPANY_B, f"R5C {COMPANY_B}")):
                    cur.execute(
                        """
                        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                        ON CONFLICT (company_code) DO NOTHING
                        """,
                        (code, name),
                    )
                for code in (COMPANY, COMPANY_B):
                    cur.execute(
                        """
                        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                        VALUES (%s,'talent',true,'r5c','{}'::jsonb,now())
                        ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true
                        """,
                        (code,),
                    )
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY_B, actor_phone=HR, enabled=True, reason="r5c enable b"
                )
                surfaces.ensure_all_schemas(cur)
                synced = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5c enable"
                )
                check("sync catalog entitlement", synced.get("ok") is True, synced)
                check("no master score", synced.get("no_master_talent_score") is True)
                check("JA not required", synced.get("job_architecture_required") is False)
                check("learning not required", synced.get("learning_required") is False)

                # A — Talent without Performance
                prof = c5.ensure_talent_profile(cur, company_code=COMPANY, employee_key=EMP, actor_phone=HR)
                check("profile created", prof.get("ok") is True, prof)
                check("profile has no score", prof.get("master_talent_score") is None)
                fact = c5.add_dimension_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    dimension_kind="strength",
                    title_en="Systems thinking",
                    source="hr_assessed",
                    reason="add evidence",
                )
                check("explicit evidence", fact.get("ok") is True, fact)
                fw = c5.create_potential_framework(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    name_en="Potential v1",
                    dimensions=[{"id": "learning", "name_en": "Learning"}],
                    scale_points=[{"id": "high", "label_en": "High"}],
                    reason="framework",
                )
                check("potential framework", fw.get("ok") is True, fw)
                pot = c5.submit_potential_assessment(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    framework_id=str(fw["framework"]["framework_id"]),
                    rationale="Explicit potential — not from Performance",
                    dimension_scores={"learning": "high"},
                    resulting_level="high",
                    has_sensitive_permission=True,
                    reason="potential decision",
                )
                check("potential explicit", pot.get("ok") is True and pot.get("performance_equals_potential") is False, pot)
                review = c6.create_talent_review(
                    cur, company_code=COMPANY, actor_phone=HR, name_en="Q1 Talent", reason="create review"
                )
                check("talent review created", review.get("ok") is True, review)
                prepared = c6.prepare_talent_review(
                    cur,
                    company_code=COMPANY,
                    review_id=str(review["review"]["review_id"]),
                    actor_phone=HR,
                    population=[{"employee_key": EMP, "frozen_potential_level": "high"}],
                    reason="prepare",
                )
                check("review prepared", prepared.get("ok") is True, prepared)
                hist = c5.list_dimension_facts(
                    cur, company_code=COMPANY, employee_key=EMP, include_history=True, viewer_role="hr",
                    has_sensitive_permission=True,
                )
                check("history intact", bool(hist.get("facts")), hist)

                # B — Performance optional: consume does not auto-set HiPo
                consume = c5.enable_company_talent_profile(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="allow optional perf evidence",
                    performance_evidence_consume=True,
                )
                check("perf consume enabled", consume.get("ok") is True, consume)
                link = c5.link_performance_evidence(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    performance_subject_type="review",
                    performance_subject_id="sealed-demo",
                    reason="optional sealed evidence",
                )
                check("perf evidence linked", link.get("ok") is True and link.get("becomes_potential") is False, link)
                hipo_before = c6.get_hipo_for_viewer(
                    cur, company_code=COMPANY, employee_key=EMP, viewer_role="hr", has_sensitive_permission=True
                )
                check("high performer did not auto HiPo", not any(
                    str(d.get("status")) == "designated" for d in (hipo_before.get("designations") or [])
                ), hipo_before)
                pot2 = c5.get_potential_for_viewer(
                    cur, company_code=COMPANY, employee_key=EMP, viewer_role="hr", has_sensitive_permission=True
                )
                check("potential still explicit", bool(pot2.get("assessments")), pot2)

                # C — Succession multi-successor target-specific readiness
                role = c6.designate_critical_role(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    canonical_role_key="head-ops",
                    title_en="Head of Ops",
                    reason="critical role",
                )
                check("critical role", role.get("ok") is True, role)
                plan = c6.create_succession_plan(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    critical_role_id=str(role["critical_role"]["critical_role_id"]),
                    reason="plan",
                )
                check("succession plan", plan.get("ok") is True, plan)
                n1 = c6.nominate_successor(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    plan_id=str(plan["plan"]["plan_id"]),
                    employee_key=EMP,
                    rationale="Ready now",
                    readiness="ready_now",
                    has_sensitive_permission=True,
                    reason="nominate 1",
                )
                check("successor 1", n1.get("ok") is True and n1.get("global_readiness_score") is None, n1)
                n2 = c6.nominate_successor(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    plan_id=str(plan["plan"]["plan_id"]),
                    employee_key=EMP2,
                    rationale="Near term",
                    readiness="ready_lt_1y",
                    has_sensitive_permission=True,
                    reason="nominate 2",
                )
                check("successor 2 different readiness", n2.get("ok") is True, n2)
                slate = surfaces.get_slate(cur, company_code=COMPANY, plan_id=str(plan["plan"]["plan_id"]))
                check("multi successor slate", len(slate.get("nominations") or []) >= 2, slate)
                check("no universal readiness", slate.get("global_readiness_score") is None)

                # D — 9-box derived only
                c6.enable_company_talent_succession(
                    cur, company_code=COMPANY, actor_phone=HR, reason="nine box on", nine_box_enabled=True
                )
                cfg = c6.create_nine_box_config(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    name_en="Box",
                    performance_axis={"kind": "numeric"},
                    potential_axis={"kind": "level"},
                    thresholds={
                        "performance": {"low": {"min": 0, "max": 2.9}, "high": {"min": 3, "max": 5}},
                        "potential": {"high": "high", "low": "low"},
                    },
                    labels={"highxhigh": {"en": "Star", "ar": "نجم"}},
                    reason="nine box config",
                )
                check("nine-box config", cfg.get("ok") is True and cfg.get("canonical_employee_box") is False, cfg)
                proj = c6.project_nine_box(
                    config=cfg["config"], performance_value=4, potential_level="high"
                )
                check("nine-box derived", proj.get("available") is True and proj.get("is_canonical_employee_state") is False, proj)
                check("nine-box does not imply HiPo", proj.get("does_not_imply_hipo") is True)
                hipo = c6.decide_hipo(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    status="designated",
                    rationale="Explicit — not from 9-box",
                    nine_box_cell=proj.get("cell"),
                    has_sensitive_permission=True,
                    reason="explicit hipo",
                )
                check("HiPo explicit", hipo.get("ok") is True and hipo.get("auto_inferred") is False, hipo)
                check("top right not HiPo", hipo.get("top_right_implies_hipo") is False)
                pot_after = c5.get_potential_for_viewer(
                    cur, company_code=COMPANY, employee_key=EMP, viewer_role="hr", has_sensitive_permission=True
                )
                check("potential preserved after 9-box", bool(pot_after.get("assessments")), pot_after)

                # E — Employee self
                asp = c5.update_employee_aspiration(
                    cur,
                    company_code=COMPANY,
                    employee_phone=EMP_PHONE,
                    employee_key=EMP,
                    title_en="Want product ops",
                    reason="self aspiration",
                )
                check("employee aspiration", asp.get("ok") is True, asp)
                emp_ws = surfaces.employee_workspace(cur, company_code=COMPANY, employee_key=EMP)
                check("employee workspace ok", emp_ws.get("ok") is True, emp_ws)
                check("employee potential hidden", emp_ws.get("potential_hidden") is True)
                check("employee hipo hidden", emp_ws.get("hipo_hidden") is True)
                check("employee no hipo key", "hipo" not in emp_ws)
                check("employee no potential key", "potential" not in emp_ws)
                hidden = c5.get_potential_for_viewer(
                    cur, company_code=COMPANY, employee_key=EMP, viewer_role="employee"
                )
                check("employee potential API hidden", hidden.get("error") == "potential_hidden_from_employee", hidden)

                # F — Recruiting optional
                mob = surfaces.mobility_surface(
                    cur, company_code=COMPANY, employee_key=EMP, actor_role="hr"
                )
                check("recruiting off talent works", mob.get("ok") is True and mob.get("recruiting_enabled") is False, mob)
                check("no silent candidate", mob.get("silent_candidate_creation") is False)
                check("interest not application", mob.get("interest_is_not_application") is True)
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s,'pre_hiring',true,'r5c','{}'::jsonb,now())
                    ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=true
                    """,
                    (COMPANY,),
                )
                mob2 = surfaces.mobility_surface(
                    cur, company_code=COMPANY, employee_key=EMP, actor_role="hr"
                )
                check("recruiting on explicit handoff", mob2.get("handoff_available") is True, mob2)
                check("handoff does not write pool", (mob2.get("handoff") or {}).get("writes_talent_pool") is False, mob2)

                ws = surfaces.workspace_summary(
                    cur, company_code=COMPANY, actor_role="hr", can_see_sensitive=True, can_see_succession=True
                )
                check("HR workspace summary", ws.get("ok") is True and ws.get("master_talent_score") is None, ws)
                mgr = surfaces.workspace_summary(
                    cur, company_code=COMPANY, actor_role="manager", manager_scope_keys=[]
                )
                check("manager empty scope fail-closed", (mgr.get("counts") or {}).get("profiles") == 0, mgr)
                check("talent catalog enableable", ready.catalog_module_customer_enableable("talent") is True)
                check("JA still not enableable", ready.customer_enableable("job_architecture") is False)
            conn.commit()

        run_http_security_tests(app, EMP)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="disable after use"
                )
                still = c5.get_talent_profile(cur, company_code=COMPANY, employee_key=EMP)
                check("history preserved after disable", still is not None)
                blocked = c5.add_dimension_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    dimension_kind="strength",
                    title_en="blocked",
                    source="hr_assessed",
                    reason="after disable",
                )
                check("new work blocked when disabled", blocked.get("ok") is not True, blocked)
            conn.commit()
    finally:
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5C_TALENT_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
