#!/usr/bin/env python3
"""Production Readiness R5E — staging DB Learning surface journeys A–F."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5E{SUFFIX}"[:12]
COMPANY_B = f"R5X{SUFFIX}"[:12]
HR = f"9656212{SUFFIX[:5]}"
EMP = f"emp-{SUFFIX.lower()}"
EMP2 = f"em2-{SUFFIX.lower()}"
EMP_PHONE = f"9656221{SUFFIX[:5]}"
MGR_PHONE = f"9656222{SUFFIX[:5]}"


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
        "ld_notification_dedupe",
        "ld_audit_events",
        "ld_wave5_fact_outbox",
        "ld_development_fulfillment_links",
        "ld_certifications",
        "ld_completions",
        "ld_learning_requests",
        "ld_assignments",
        "ld_offerings",
        "ld_program_items",
        "ld_item_versions",
        "ld_mandatory_policies",
        "ld_learning_items",
        "ld_providers",
        "ld_company_settings",
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


def run_http_security_tests(app, employee_key: str, item_id: str) -> None:
    from fastapi.testclient import TestClient

    hr_perms = ["learning.read", "learning.manage", "learning.assign", "learning.approve"]
    mgr_perms = ["learning.read", "learning.assign", "learning.approve"]
    client = TestClient(app.app)
    registered = any(str(getattr(route, "path", "")).startswith("/dashboard/learning") for route in app.app.routes)
    check("learning HTTP routes registered", registered is True)

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
        bare = unauth.get("/dashboard/learning/workspace")
        check("unauthenticated dashboard not public", bare.status_code in {401, 403}, bare.status_code)
        bare_app = unauth.get("/app/learning")
        check("unauthenticated employee not public", bare_app.status_code in {401, 403, 503}, bare_app.status_code)

        use(_ctx(COMPANY, role="owner", perms=hr_perms, phone=HR, user_id="r5e-hr"))
        ws = client.get("/dashboard/learning/workspace")
        check("HR workspace HTTP", ws.status_code == 200 and ws.json().get("ok") is True, ws.text[:300])
        catalog = client.get("/dashboard/learning/catalog")
        check("HR lists catalog", catalog.status_code == 200, catalog.text[:300])
        assigns = client.get("/dashboard/learning/assignments")
        check("HR lists assignments", assigns.status_code == 200, assigns.text[:300])
        if assigns.status_code == 200:
            rows = assigns.json().get("assignments") or []
            check("Web assignment present", any(r.get("employee_key") == employee_key for r in rows), len(rows))

        use(_ctx(COMPANY_B, role="owner", perms=hr_perms, phone=HR, user_id="r5e-hr-b"))
        cross = client.get("/dashboard/learning/assignments")
        check("tenant isolation empty or self-only", cross.status_code == 200, cross.status_code)
        if cross.status_code == 200:
            foreign = [r for r in (cross.json().get("assignments") or []) if r.get("employee_key") == employee_key]
            check("tenant isolation no foreign assignments", foreign == [], foreign)

        use(_ctx(COMPANY, role="manager", perms=mgr_perms, phone=MGR_PHONE, user_id="r5e-mgr"))
        scoped = client.get("/dashboard/learning/assignments")
        check(
            "manager empty scope fail-closed",
            scoped.status_code == 200 and int(scoped.json().get("total") or 0) == 0,
            scoped.text[:300],
        )
        catalog_write = client.post(
            "/dashboard/learning/catalog",
            json={
                "code": "MGR",
                "item_type": "self_paced",
                "title_en": "Nope",
                "title_ar": "لا",
                "reason": "manager catalog",
            },
        )
        check("manager cannot catalog-author", catalog_write.status_code == 403, catalog_write.status_code)

        use(_ctx(COMPANY, role="owner", perms=["learning.read"], phone=HR, user_id="r5e-hr-ro"))
        write = client.post(
            "/dashboard/learning/catalog",
            json={
                "code": "RO",
                "item_type": "self_paced",
                "title_en": "Nope",
                "title_ar": "لا",
                "reason": "readonly",
            },
        )
        check("HR without manage denied catalog write", write.status_code == 403, write.status_code)

        emp(COMPANY, employee_key, EMP_PHONE)
        mine = client.get("/app/learning")
        check("employee sees own workspace", mine.status_code == 200, mine.status_code)
        body = mine.json() if mine.status_code == 200 else {}
        check("employee no HR admin", body.get("hr_admin_exposed") is False, list(body.keys())[:12])
        emp_assigns = (body.get("assignments") or []) if mine.status_code == 200 else []
        check("employee sees assignment", any(r.get("employee_key") == employee_key for r in emp_assigns), len(emp_assigns))
        emp(COMPANY, "someone-else", EMP_PHONE)
        stolen = client.get("/app/learning")
        check("employee IDOR stays self", stolen.status_code in {200, 403, 404}, stolen.status_code)
        if stolen.status_code == 200:
            stolen_key = stolen.json().get("employee_key")
            check("employee IDOR does not return other key", stolen_key != employee_key, stolen_key)
            stolen_rows = stolen.json().get("assignments") or []
            check("employee cannot enumerate another history", not any(r.get("employee_key") == employee_key for r in stolen_rows))
        emp(COMPANY, employee_key, EMP_PHONE)
        mandatory_complete = client.post(
            "/app/learning/completions",
            json={"assignment_id": str(uuid.uuid4()), "evidence_source": "manual_authorized", "evidence_ref": "self"},
        )
        check(
            "employee mandatory/self complete fail-closed or not-found",
            mandatory_complete.status_code in {403, 404, 422},
            mandatory_complete.status_code,
        )
    finally:
        app.app.dependency_overrides.clear()


def _env_on() -> None:
    os.environ["WATHEFNI_LEARNING_C2"] = "on"
    os.environ["WATHEFNI_LEARNING_COMPANIES"] = ""
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_REVIEWS_C2"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = "off"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "off"
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5E — learning surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import learning_development_c2 as c2
        import learning_surfaces as surfaces
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

    item_id = ""
    assignment_id = ""
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for code, name in ((COMPANY, f"R5E {COMPANY}"), (COMPANY_B, f"R5E {COMPANY_B}")):
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
                    cur, company_code=COMPANY_B, actor_phone=HR, enabled=True, reason="r5e enable b"
                )
                synced = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5e enable"
                )
                check("sync catalog entitlement", synced.get("ok") is True, synced)
                check("performance optional", synced.get("performance_optional") is True)
                check("talent optional", synced.get("talent_optional") is True)
                check("JA optional", synced.get("job_architecture_optional") is True)

                # F prelude — Learning usable with Performance/Talent/JA OFF
                check("learning enableable", ready.customer_enableable("learning") is True)
                ws_off = surfaces.workspace_summary(cur, company_code=COMPANY, actor_role="hr")
                check("workspace ready without optional modules", ws_off.get("ok") is True and ws_off.get("counts") is not None, ws_off)
                check("performance off", ws_off.get("performance_on") is False, ws_off)
                check("talent off", ws_off.get("talent_on") is False, ws_off)

                # A — Assignment
                item = c2.upsert_learning_item(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="SAFE",
                    item_type="self_paced",
                    title_en="Safety",
                    title_ar="السلامة",
                    status="published",
                    reason="catalog",
                )
                check("catalog item created", item.get("ok") is True, item)
                item_id = str((item.get("item") or {}).get("item_id") or "")
                assigned = c2.create_assignment(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    item_id=item_id,
                    source="hr_assigned",
                    required=True,
                    due_date=date.today() + timedelta(days=7),
                    reason="assign employee",
                )
                check("assignment created", assigned.get("ok") is True, assigned)
                assignment_id = str((assigned.get("assignment") or {}).get("assignment_id") or "")
                derived = c2.assignment_derived_state(assigned.get("assignment") or {})
                check("assigned is not completed", (assigned.get("assignment") or {}).get("status") == "assigned")
                check("overdue is not failure", derived.get("failed") is False and derived.get("due_date_passed_is_not_failure") is True)
                emp_view = surfaces.employee_workspace(cur, company_code=COMPANY, employee_key=EMP)
                check("employee sees assignment", any(a.get("assignment_id") == assignment_id for a in (emp_view.get("assignments") or [])), emp_view.get("resource_state"))
                web = surfaces.list_assignments(cur, company_code=COMPANY)
                check("web assignment converges", any(a.get("assignment_id") == assignment_id for a in (web.get("assignments") or [])))
                check("assignment ≠ enrollment on row", any(a.get("assignment_id") == assignment_id and a.get("enrolled") is False for a in (web.get("assignments") or [])))

                # B — Employee request
                req_item = c2.upsert_learning_item(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="OPT",
                    item_type="self_paced",
                    title_en="Optional course",
                    title_ar="دورة اختيارية",
                    status="published",
                    reason="optional catalog",
                )
                req_item_id = str((req_item.get("item") or {}).get("item_id") or "")
                request = c2.create_learning_request(
                    cur, company_code=COMPANY, employee_key=EMP, item_id=req_item_id, reason="want this"
                )
                check("request created", request.get("ok") is True and request.get("is_enrollment") is False, request)
                request_id = str((request.get("request") or {}).get("request_id") or "")
                reject = surfaces.decide_request(
                    cur, company_code=COMPANY, actor_phone=HR, request_id=request_id, approve=False, reason=""
                )
                check("rejection requires reason", reject.get("error") == "rejection_reason_required", reject)
                request2 = c2.create_learning_request(
                    cur, company_code=COMPANY, employee_key=EMP, item_id=req_item_id, reason="want this again"
                )
                request2_id = str((request2.get("request") or {}).get("request_id") or "")
                decided = surfaces.decide_request(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    request_id=request2_id,
                    approve=True,
                    reason="approved",
                )
                check("approved request", decided.get("ok") is True and decided.get("enrollment_created") is True, decided)
                check("approval is not completion", decided.get("completion_created") is False)
                check("request ≠ approval ≠ enrollment", decided.get("request_is_not_approval") is True)

                # C — Session
                offering = c2.create_offering(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    item_id=item_id,
                    capacity=1,
                    location_or_virtual="virtual",
                )
                check("session created", offering.get("ok") is True, offering)
                offering_id = str((offering.get("offering") or {}).get("offering_id") or "")
                enroll = surfaces.enroll_in_session(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    offering_id=offering_id,
                    employee_key=EMP2,
                    source="hr_assigned",
                    reason="enroll",
                )
                check("enrolled", enroll.get("ok") is True and enroll.get("enrollment_is_not_completion") is True, enroll)
                enroll_id = str((enroll.get("assignment") or {}).get("assignment_id") or "")
                overflow = surfaces.enroll_in_session(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    offering_id=offering_id,
                    employee_key=EMP,
                    source="hr_assigned",
                    reason="over capacity",
                )
                check("capacity is server-authoritative", overflow.get("error") == "session_capacity_exceeded", overflow)
                attended = surfaces.record_session_attendance(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    offering_id=offering_id,
                    assignment_id=enroll_id,
                    evidence_ref="roster-1",
                )
                check("attendance recorded", attended.get("ok") is True and attended.get("attended") is True, attended)
                check("attendance ≠ completion", attended.get("completed") is False and attended.get("attendance_is_not_completion") is True)
                complete = surfaces.record_completion_guarded(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    assignment_id=enroll_id,
                    evidence_source="internal_session",
                    evidence_ref="roster-1",
                    actor_role="hr",
                )
                check("completion evidence-backed", complete.get("ok") is True, complete)
                check("completion ≠ competency", complete.get("competency_auto_verified") is False)
                check("completion ≠ certification", complete.get("completion_is_not_certification") is True)

                # Employee cannot self-complete mandatory
                blocked_self = surfaces.record_completion_guarded(
                    cur,
                    company_code=COMPANY,
                    actor_phone=EMP_PHONE,
                    assignment_id=assignment_id,
                    evidence_source="manual_authorized",
                    evidence_ref="I finished",
                    actor_role="employee",
                )
                check("employee mandatory self-complete forbidden", blocked_self.get("error") == "employee_self_completion_forbidden", blocked_self)

                # D — Certification
                hr_complete = surfaces.record_completion_guarded(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    assignment_id=assignment_id,
                    evidence_source="manual_authorized",
                    evidence_ref="verifier-1",
                    actor_role="hr",
                )
                check("HR completion for cert", hr_complete.get("ok") is True, hr_complete)
                completion_id = str((hr_complete.get("completion") or {}).get("completion_id") or "")
                cert = c2.issue_certification(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    cert_type="internal",
                    title_en="Safety cert",
                    title_ar="شهادة السلامة",
                    issued_on=date.today() - timedelta(days=40),
                    expires_on=date.today() + timedelta(days=5),
                    evidence_ref="verifier-1",
                    linked_completion_id=completion_id,
                )
                check("cert issued", cert.get("ok") is True, cert)
                cert_id = str((cert.get("certification") or {}).get("certification_id") or "")
                derived_cert = c2.certification_derived_status(cert.get("certification") or {}, warning_days=30)
                check("expiry approaching is derived", derived_cert.get("expiring") is True, derived_cert)
                renewal = c2.issue_certification(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=EMP,
                    cert_type="internal",
                    title_en="Safety cert renewed",
                    title_ar="شهادة السلامة مجددة",
                    issued_on=date.today(),
                    expires_on=date.today() + timedelta(days=365),
                    evidence_ref="renewal-1",
                    linked_completion_id=completion_id,
                    renewal_of=cert_id,
                )
                check("renewal issued", renewal.get("ok") is True, renewal)
                certs = surfaces.list_certificates(cur, company_code=COMPANY, employee_key=EMP)
                check("prior certificate remains historical", len(certs.get("certificates") or []) >= 2, certs.get("total"))
                check("expiry does not erase history", certs.get("expiry_does_not_erase_history") is True)

                # Mandatory idempotent
                policy = c2.create_mandatory_policy(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="MAND1",
                    title_en="Mandatory safety",
                    title_ar="سلامة إلزامية",
                    item_id=item_id,
                    population_rule={"keys": [EMP]},
                )
                check("mandatory policy", policy.get("ok") is True, policy)
                policy_id = str((policy.get("policy") or {}).get("policy_id") or "")
                gen1 = c2.generate_mandatory_assignments(
                    cur, company_code=COMPANY, actor_phone=HR, policy_id=policy_id, employee_keys=[EMP]
                )
                gen2 = c2.generate_mandatory_assignments(
                    cur, company_code=COMPANY, actor_phone=HR, policy_id=policy_id, employee_keys=[EMP]
                )
                check("mandatory first generate", gen1.get("ok") is True, gen1)
                check("mandatory replay idempotent", EMP in (gen2.get("replayed") or []), gen2)

                # E — Performance integration does not silently close C3
                action_id = str(uuid.uuid4())
                link = c2.link_development_fulfillment(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    development_action_id=action_id,
                    assignment_id=assignment_id,
                    completion_id=completion_id,
                    item_id=item_id,
                )
                check("fulfillment link", link.get("ok") is True, link)
                check("did not silently close C3", link.get("silently_closed_c3") is False)
                check("C3 remains authority", link.get("c3_remains_sole_development_authority") is True)
                cur.execute("SELECT to_regclass('perf_development_actions') AS t")
                if dict(cur.fetchone() or {}).get("t"):
                    cur.execute(
                        "SELECT status FROM perf_development_actions WHERE company_code=%s AND action_id=%s",
                        (COMPANY, action_id),
                    )
                    row = cur.fetchone()
                    check("C3 row unchanged or absent", row is None or dict(row).get("status") != "done", row)

                # History reconstruction
                history = surfaces.list_history(cur, company_code=COMPANY, employee_key=EMP)
                check("history has completions", bool(history.get("completions")), history.get("ok"))
                check("history has certificates", bool(history.get("certificates")))
                check("later policy does not rewrite history", history.get("later_policy_does_not_rewrite_history") is True)

                mgr = surfaces.workspace_summary(
                    cur, company_code=COMPANY, actor_role="manager", manager_scope_keys=[]
                )
                check("manager empty scope fail-closed", (mgr.get("counts") or {}).get("active_assignments") == 0, mgr)
                check("manager not company-wide", mgr.get("company_wide") is False)

                ctx = surfaces.optional_context(cur, company_code=COMPANY, employee_key=EMP)
                check("no auto hipo in context", ctx.get("no_auto_hipo") is True)
                check("no learning talent score", ctx.get("no_learning_talent_score") is True)
            conn.commit()

        run_http_security_tests(app, EMP, item_id)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="disable after use"
                )
                cur.execute("SELECT COUNT(*) AS n FROM ld_assignments WHERE company_code=%s", (COMPANY,))
                retained = int(dict(cur.fetchone() or {}).get("n") or 0)
                check("history retained after disable", retained >= 1, retained)
                blocked = c2.upsert_learning_item(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="NEW",
                    item_type="self_paced",
                    title_en="Blocked",
                    title_ar="محظور",
                    reason="after disable",
                )
                check("new work blocked when disabled", blocked.get("error") == "learning_disabled_for_company", blocked)
                unavailable = surfaces.workspace_summary(cur, company_code=COMPANY, actor_role="hr")
                check("disabled workspace unavailable", unavailable.get("resource_state") == "unavailable", unavailable)
                check("disabled counts are not fake zeros", unavailable.get("counts") is None, unavailable)
                cur.execute(
                    "SELECT enabled FROM company_modules WHERE company_code=%s AND module_key='learning'",
                    (COMPANY,),
                )
                module_row = dict(cur.fetchone() or {})
                check("company_modules learning off", module_row.get("enabled") is False, module_row)
            conn.commit()

        if hasattr(app, "notification_source_module_enabled"):
            check(
                "notifications suppressed when module off",
                app.notification_source_module_enabled(COMPANY, "learning") is False,
            )
    finally:
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5E_LEARNING_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
