#!/usr/bin/env python3
"""Production Readiness R5F — staging DB Benefits surface journeys A–F."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5F{SUFFIX}"[:12]
COMPANY_B = f"R5Y{SUFFIX}"[:12]
HR = f"9656312{SUFFIX[:5]}"
EMP = f"emp-{SUFFIX.lower()}"
EMP2 = f"em2-{SUFFIX.lower()}"
EMP_PHONE = f"9656321{SUFFIX[:5]}"
MGR_PHONE = f"9656322{SUFFIX[:5]}"


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
        "bn_notification_dedupe",
        "bn_audit_events",
        "bn_wave5_fact_outbox",
        "bn_provider_member_refs",
        "bn_payroll_handoffs",
        "bn_contributions",
        "bn_dependent_coverage_links",
        "bn_evidence_requests",
        "bn_coverage_periods",
        "bn_enrollments",
        "bn_eligibility_evaluations",
        "bn_enrollment_windows",
        "bn_eligibility_rules",
        "bn_plan_versions",
        "bn_plans",
        "bn_providers",
        "bn_company_settings",
        "employee_dependents",
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


def run_http_security_tests(app, employee_key: str, plan_id: str) -> None:
    from fastapi.testclient import TestClient

    hr_perms = [
        "benefits.read",
        "benefits.manage",
        "benefits.eligibility",
        "benefits.enroll",
        "benefits.sensitive",
    ]
    client = TestClient(app.app)
    registered = any(str(getattr(route, "path", "")).startswith("/dashboard/benefits") for route in app.app.routes)
    check("benefits HTTP routes registered", registered is True)

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
        bare = unauth.get("/dashboard/benefits/workspace")
        check("unauthenticated dashboard not public", bare.status_code in {401, 403}, bare.status_code)
        bare_app = unauth.get("/app/benefits")
        check("unauthenticated employee not public", bare_app.status_code in {401, 403, 503}, bare_app.status_code)

        use(_ctx(COMPANY, role="owner", perms=hr_perms, phone=HR, user_id="r5f-hr"))
        ws = client.get("/dashboard/benefits/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        plans = client.get("/dashboard/benefits/plans")
        check("HR lists plans", plans.status_code == 200, plans.text[:300])
        enrolls = client.get("/dashboard/benefits/enrollments")
        check("HR lists enrollments", enrolls.status_code == 200, enrolls.text[:300])
        if enrolls.status_code == 200:
            rows = enrolls.json().get("enrollments") or []
            check("Web enrollment present", any(r.get("employee_key") == employee_key for r in rows), len(rows))

        use(_ctx(COMPANY_B, role="owner", perms=hr_perms, phone=HR, user_id="r5f-hr-b"))
        cross = client.get("/dashboard/benefits/enrollments")
        check("tenant isolation empty or self-only", cross.status_code == 200, cross.status_code)
        if cross.status_code == 200:
            foreign = [r for r in (cross.json().get("enrollments") or []) if r.get("employee_key") == employee_key]
            check("tenant isolation no foreign enrollments", foreign == [], foreign)

        use(_ctx(COMPANY, role="manager", perms=["leave.read"], phone=MGR_PHONE, user_id="r5f-mgr"))
        mgr = client.get("/dashboard/benefits/workspace")
        check("manager Benefits workspace forbidden", mgr.status_code == 403, mgr.status_code)
        mgr_enroll = client.get("/dashboard/benefits/enrollments")
        check("manager cannot list elections", mgr_enroll.status_code == 403, mgr_enroll.status_code)

        use(_ctx(COMPANY, role="owner", perms=["leave.read"], phone=HR, user_id="r5f-hr-none"))
        denied = client.get("/dashboard/benefits/workspace")
        check("HR without Benefits permission fail-closed", denied.status_code == 403, denied.status_code)

        use(_ctx(COMPANY, role="owner", perms=["benefits.read"], phone=HR, user_id="r5f-hr-ro"))
        write = client.post(
            "/dashboard/benefits/plans",
            json={
                "code": "RO",
                "category": "medical",
                "title_en": "Nope",
                "title_ar": "لا",
                "reason": "readonly",
            },
        )
        check("HR without manage denied plan write", write.status_code == 403, write.status_code)
        sensitive = client.get("/dashboard/benefits/contributions")
        check("HR without sensitive denied contributions", sensitive.status_code == 403, sensitive.status_code)

        emp(COMPANY, employee_key, EMP_PHONE)
        mine = client.get("/app/benefits")
        check("employee sees own workspace", mine.status_code == 200, mine.status_code)
        body = mine.json() if mine.status_code == 200 else {}
        check("employee no HR admin", body.get("hr_admin_exposed") is False, list(body.keys())[:12])
        check("employee self key", body.get("employee_key") == employee_key, body.get("employee_key"))
        emp(COMPANY, "someone-else", EMP_PHONE)
        stolen = client.get("/app/benefits")
        check("employee IDOR stays self", stolen.status_code in {200, 403, 404}, stolen.status_code)
        if stolen.status_code == 200:
            stolen_key = stolen.json().get("employee_key")
            check("employee IDOR does not return other key", stolen_key != employee_key, stolen_key)
            stolen_rows = stolen.json().get("enrollments") or []
            check("employee cannot enumerate another history", not any(r.get("employee_key") == employee_key for r in stolen_rows))
        emp(COMPANY, employee_key, EMP_PHONE)
        confirm = client.post(
            f"/dashboard/benefits/enrollments/{uuid.uuid4()}/confirm",
            json={"coverage_start": date.today().isoformat(), "provider_confirmed": False},
        )
        check("employee cannot confirm coverage via dashboard", confirm.status_code in {401, 403, 404}, confirm.status_code)
        detail = client.get(f"/app/benefits/plans/{plan_id}")
        check("employee plan detail", detail.status_code in {200, 404}, detail.status_code)
    finally:
        app.app.dependency_overrides.clear()


def _env_on() -> None:
    os.environ["WATHEFNI_BENEFITS_C3"] = "on"
    os.environ["WATHEFNI_BENEFITS_COMPANIES"] = ""
    os.environ["WATHEFNI_LEARNING_C2"] = "off"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "off"
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5F — benefits surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import benefits_administration_c3 as c3
        import benefits_surfaces as surfaces
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
    today = date.today()
    plan_id = ""
    enrollment_id = ""
    coverage_id = ""
    v1 = 0

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                try:
                    import ess_letters_dependents_c2 as dep

                    dep.ensure_ess_letters_dependents_c2_schema(cur)
                except Exception:
                    pass
                for code, name in ((COMPANY, f"R5F {COMPANY}"), (COMPANY_B, f"R5F {COMPANY_B}")):
                    cur.execute(
                        """
                        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                        ON CONFLICT (company_code) DO NOTHING
                        """,
                        (code, name),
                    )
                surfaces.ensure_schema(cur)
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY_B, actor_phone=HR, enabled=True, reason="r5f enable b"
                )
                synced = surfaces.sync_catalog_entitlement(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    enabled=True,
                    reason="r5f enable",
                    payroll_handoff_enabled=False,
                )
                check("sync catalog entitlement", synced.get("ok") is True, synced)
                check("payroll optional", synced.get("payroll_optional") is True)
                check("benefits enableable", ready.customer_enableable("benefits") is True)

                ws_off = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("workspace ready without optional modules", ws_off.get("ok") is True and ws_off.get("counts") is not None, ws_off)
                check("learning off", ws_off.get("learning_on") is False, ws_off)
                check("talent off", ws_off.get("talent_on") is False, ws_off)
                check("JA off", ws_off.get("job_architecture_on") is False, ws_off)
                check("payroll off", ws_off.get("payroll_on") is False, ws_off)

                # A — Eligibility + enrollment
                plan = c3.upsert_plan(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="MED-R5F",
                    category="medical",
                    title_en="Medical",
                    title_ar="طبي",
                    status="published",
                    tier_options=["employee_only", "employee_spouse", "family"],
                    required_documents=[],
                    effective_start=today - timedelta(days=10),
                    reason="r5f plan",
                )
                check("plan created", plan.get("ok") is True, plan)
                plan_id = str(plan.get("stable_id") or "")
                v1 = int((plan.get("plan") or {}).get("effective_version") or 1)
                rule = c3.create_eligibility_rule(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    plan_id=plan_id,
                    code="OPEN",
                    title_en="Open",
                    title_ar="مفتوح",
                    criteria={},
                )
                check("eligibility rule", rule.get("ok") is True, rule)
                prepared = surfaces.prepare_enrollment(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    plan_id=plan_id,
                )
                check("eligible then started", prepared.get("ok") is True and prepared.get("eligible") is True, prepared)
                check("eligibility is not enrollment", prepared.get("eligible_is_not_enrolled") is True)
                check("prepare did not create coverage", prepared.get("coverage_created") is False)
                elected = surfaces.employee_elect_or_waive(
                    cur,
                    company_code=COMPANY,
                    actor_phone=EMP_PHONE,
                    employee_key=EMP,
                    plan_id=plan_id,
                    waive=False,
                    tier="employee_only",
                    enrollment_id=str((prepared.get("enrollment") or {}).get("enrollment_id") or ""),
                )
                check("election recorded", elected.get("ok") is True, elected)
                check("election is not coverage", elected.get("election_not_confirmed_coverage") is True or (elected.get("enrollment") or {}).get("status") != "coverage_active")
                enrollment_id = str((elected.get("enrollment") or {}).get("enrollment_id") or "")
                check("status elected not active", (elected.get("enrollment") or {}).get("status") == "elected", elected)
                confirmed = c3.confirm_enrollment(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    enrollment_id=enrollment_id,
                    coverage_start=today,
                    provider_confirmed=False,
                )
                check("coverage via canonical confirm", confirmed.get("ok") is True, confirmed)
                check("provider not fabricated", confirmed.get("provider_confirmed") is False)
                check("internal recorded distinct", confirmed.get("internal_recorded") is True)
                coverage_id = str((confirmed.get("coverage") or {}).get("coverage_id") or "")
                check("coverage plan version pinned", int((confirmed.get("coverage") or {}).get("plan_version") or 0) == v1)

                # B — Waiver
                prepared2 = surfaces.prepare_enrollment(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP2,
                    plan_id=plan_id,
                )
                waived = surfaces.employee_elect_or_waive(
                    cur,
                    company_code=COMPANY,
                    actor_phone=EMP_PHONE,
                    employee_key=EMP2,
                    plan_id=plan_id,
                    waive=True,
                    reason="does not want medical",
                    enrollment_id=str((prepared2.get("enrollment") or {}).get("enrollment_id") or ""),
                )
                check("waiver recorded", waived.get("ok") is True and waived.get("waived") is True, waived)
                check("waiver is not coverage", waived.get("coverage_active") is False)
                check("waiver is not ineligibility", waived.get("election_not_confirmed_coverage") is True)
                eval_again = c3.evaluate_eligibility(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP2,
                    plan_id=plan_id,
                    rule_id=str((rule.get("rule") or {}).get("rule_id") or ""),
                    attributes={},
                )
                check("waived employee remains eligible", eval_again.get("eligible") is True and eval_again.get("enrolled") is False, eval_again)
                waivers = surfaces.list_waivers(cur, company_code=COMPANY, employee_key=EMP2)
                check("waiver list explicit", waivers.get("waiver_is_not_ineligibility") is True and int(waivers.get("total") or 0) >= 1)

                # C — Canonical dependents
                dep_id = str(uuid.uuid4())
                cur.execute("SELECT to_regclass('employee_dependents') AS t")
                if dict(cur.fetchone() or {}).get("t"):
                    cur.execute(
                        """
                        INSERT INTO employee_dependents (
                          dependent_id, company_code, employee_key, relationship, name_en, name_ar,
                          duplicate_fingerprint, status
                        ) VALUES (%s,%s,%s,'spouse','Spouse EN','الزوج/ة',%s,'active')
                        ON CONFLICT DO NOTHING
                        """,
                        (dep_id, COMPANY, EMP, f"fp-{dep_id}"),
                    )
                    deps = surfaces.list_dependents_for_coverage(cur, company_code=COMPANY, employee_key=EMP)
                    check("canonical dependent exists", any(str(d.get("dependent_id")) == dep_id for d in (deps.get("dependents") or [])), deps.get("total"))
                    check("dependent exists is not covered", any(d.get("dependent_exists_is_not_covered") is True for d in (deps.get("dependents") or [])))
                    link = c3.link_dependent_coverage(
                        cur,
                        company_code=COMPANY,
                        actor_phone=HR,
                        coverage_id=coverage_id,
                        dependent_id=dep_id,
                    )
                    check("dependent coverage refs canonical", link.get("ok") is True and link.get("does_not_create_dependent_master") is True, link)
                    deps2 = surfaces.list_dependents_for_coverage(cur, company_code=COMPANY, employee_key=EMP)
                    check("dependent now covered via relationship", any(d.get("covered") is True for d in (deps2.get("dependents") or [])))
                else:
                    check("dependent table available", False, "employee_dependents missing")

                # D — Payroll OFF contribution truth
                contrib = c3.define_contribution(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    plan_id=plan_id,
                    plan_version=v1,
                    kind="employee",
                    mode="fixed",
                    amount=12.5,
                    currency="KWD",
                    effective_start=today,
                    enrollment_id=enrollment_id,
                    coverage_id=coverage_id,
                )
                check("contribution truth with payroll off", contrib.get("ok") is True and contrib.get("paid_amount") is None, contrib)
                check("contribution is not deduction", contrib.get("contribution_not_payroll_deduction") is True)
                blocked_handoff = c3.create_payroll_handoff(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    enrollment_id=enrollment_id,
                    coverage_id=coverage_id,
                    employee_amount=12.5,
                    employer_amount=20,
                    period_start=today,
                )
                check("handoff blocked when payroll option off", blocked_handoff.get("error") == "payroll_handoff_disabled", blocked_handoff)

                # E — Payroll ON explicit handoff
                cur.execute(
                    """
                    INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
                    VALUES (%s, 'payroll', true, 'r5f', '{}'::jsonb, now())
                    ON CONFLICT (company_code, module_key)
                    DO UPDATE SET enabled=true, updated_at=now()
                    """,
                    (COMPANY,),
                )
                enabled_pay = c3.enable_company_benefits(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="enable payroll handoff",
                    payroll_handoff_enabled=True,
                )
                check("handoff setting on", enabled_pay.get("ok") is True and (enabled_pay.get("settings") or {}).get("payroll_handoff_enabled") is True, enabled_pay)
                handoff = c3.create_payroll_handoff(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    enrollment_id=enrollment_id,
                    coverage_id=coverage_id,
                    employee_amount=12.5,
                    employer_amount=20,
                    period_start=today,
                )
                check("handoff created", handoff.get("ok") is True, handoff)
                check("handoff not applied", handoff.get("applied_to_payroll") is False)
                check("payroll remains authority", handoff.get("payroll_remains_execution_authority") is True)
                check("finalized payroll not rewritten", handoff.get("finalized_payroll_not_rewritten") is True)

                # F — History / version pin
                revised = c3.upsert_plan(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="MED-R5F",
                    category="medical",
                    title_en="Medical Plus",
                    title_ar="طبي بلس",
                    status="published",
                    tier_options=["employee_only", "family"],
                    required_documents=[],
                    reason="version bump",
                )
                check("plan version bumped", revised.get("ok") is True and int((revised.get("plan") or {}).get("effective_version") or 0) == v1 + 1, revised)
                cur.execute(
                    "SELECT plan_version FROM bn_coverage_periods WHERE coverage_id=%s",
                    (coverage_id,),
                )
                pinned = int(dict(cur.fetchone() or {}).get("plan_version") or 0)
                check("prior coverage retains original version", pinned == v1, pinned)
                history = surfaces.list_history(cur, company_code=COMPANY, employee_key=EMP)
                check("history reconstructable", bool(history.get("enrollments")) and bool(history.get("coverage")), history.get("ok"))
                check("later policy does not rewrite history", history.get("later_policy_does_not_rewrite_history") is True)

                emp_view = surfaces.employee_workspace(cur, company_code=COMPANY, employee_key=EMP)
                check("employee workspace ready", emp_view.get("resource_state") == "ready", emp_view.get("resource_state"))
                check("employee sees coverage", any(c.get("coverage_id") == coverage_id for c in (emp_view.get("coverage") or [])))
                check("employee no HR admin keys", emp_view.get("hr_admin_exposed") is False)

                claims = c3.claims_engine_absent_check()
                check("no claims engine", claims.get("no_claim_tables_in_c3") is True and claims.get("has_claim_table_ddl") is False, claims)
            conn.commit()

        run_http_security_tests(app, EMP, plan_id)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="disable after use"
                )
                cur.execute("SELECT COUNT(*) AS n FROM bn_coverage_periods WHERE company_code=%s", (COMPANY,))
                retained = int(dict(cur.fetchone() or {}).get("n") or 0)
                check("history retained after disable", retained >= 1, retained)
                blocked = c3.upsert_plan(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="NEW",
                    category="medical",
                    title_en="Blocked",
                    title_ar="محظور",
                    reason="after disable",
                )
                check("new work blocked when disabled", blocked.get("error") == "benefits_disabled_for_company", blocked)
                unavailable = surfaces.workspace_summary(cur, company_code=COMPANY)
                check("disabled workspace unavailable", unavailable.get("resource_state") == "unavailable", unavailable)
                check("disabled counts are not fake zeros", unavailable.get("counts") is None, unavailable)
                emp_off = surfaces.employee_workspace(cur, company_code=COMPANY, employee_key=EMP)
                check("disabled employee unavailable not empty", emp_off.get("resource_state") == "unavailable", emp_off)
                check("disabled employee plans are not fake empty", emp_off.get("plans") is None, emp_off)
                cur.execute(
                    "SELECT enabled FROM company_modules WHERE company_code=%s AND module_key='benefits'",
                    (COMPANY,),
                )
                module_row = dict(cur.fetchone() or {})
                check("company_modules benefits off", module_row.get("enabled") is False, module_row)
            conn.commit()

        if hasattr(app, "notification_source_module_enabled"):
            check(
                "notifications suppressed when module off",
                app.notification_source_module_enabled(COMPANY, "benefits") is False,
            )
    finally:
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5F_BENEFITS_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
