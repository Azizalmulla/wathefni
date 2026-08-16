#!/usr/bin/env python3
"""Production Readiness R5G — staging DB Employee Relations surface journeys A–G."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0

SUFFIX = uuid.uuid4().hex[:6].upper()
COMPANY = f"R5G{SUFFIX}"[:12]
COMPANY_B = f"R5Z{SUFFIX}"[:12]
HR = f"9656412{SUFFIX[:5]}"
ADMIN = f"er-admin-{SUFFIX.lower()}"
INV_A = f"inv-a-{SUFFIX.lower()}"
INV_B = f"inv-b-{SUFFIX.lower()}"
ORD_HR = f"hr-ord-{SUFFIX.lower()}"
MGR = f"mgr-{SUFFIX.lower()}"
EMP = f"emp-{SUFFIX.lower()}"
RAW_REF = "s3://secret-bucket/er-raw-file"

ER_PERMS = ["er.read", "er.manage", "er.investigate", "er.decide", "er.sensitive", "er.export"]
HR_NO_ER = ["leave.read", "employees.read", "payroll.read", "talent.read", "benefits.read"]


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
        "er_notification_dedupe",
        "er_audit_events",
        "er_wave5_fact_outbox",
        "er_task_links",
        "er_employment_handoffs",
        "er_outcomes",
        "er_safe_messages",
        "er_evidence_refs",
        "er_findings",
        "er_investigation_notes",
        "er_access_grants",
        "er_allegations",
        "er_case_parties",
        "er_cases",
        "er_case_types",
        "er_company_settings",
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


def run_http_security_tests(app, case_a: str, case_b: str, evidence_id: str) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(app.app)
    registered = any(
        str(getattr(route, "path", "")).startswith("/dashboard/employee-relations") for route in app.app.routes
    )
    check("ER HTTP routes registered", registered is True)
    mobile_registered = any(
        str(getattr(route, "path", "")).startswith("/dashboard/mobile/employee-relations") for route in app.app.routes
    )
    check("ER mobile HTTP routes registered", mobile_registered is True)

    def use(ctx: dict) -> None:
        app.app.dependency_overrides[app.dashboard_context] = lambda: ctx

    try:
        unauth = TestClient(app.app)
        anon = unauth.get("/dashboard/employee-relations/workspace")
        check("unauthenticated workspace not public", anon.status_code in {401, 403, 503}, anon.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=HR_NO_ER, phone=HR, user_id=ORD_HR))
        denied = client.get("/dashboard/employee-relations/workspace")
        check("HR without ER authority workspace 403", denied.status_code == 403, denied.status_code)
        denied_body = denied.json().get("detail") if denied.headers.get("content-type", "").startswith("application/json") else {}
        check(
            "403 is not empty-cases",
            isinstance(denied_body, dict)
            and denied_body.get("resource_state") == "forbidden"
            and "No employee relations cases" not in str(denied_body),
            denied_body,
        )
        denied_case = client.get(f"/dashboard/employee-relations/cases/{case_a}")
        check("HR without ER authority cannot read case", denied_case.status_code == 403, denied_case.status_code)

        use(_ctx(COMPANY, role="manager", perms=["leave.read", "employees.read"], phone=HR, user_id=MGR))
        mgr = client.get("/dashboard/employee-relations/workspace")
        check("manager workspace 403", mgr.status_code == 403, mgr.status_code)
        mgr_case = client.get(f"/dashboard/employee-relations/cases/{case_a}")
        check("manager case detail 403", mgr_case.status_code == 403, mgr_case.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["er.read", "er.investigate"], phone=HR, user_id=INV_A))
        listed = client.get("/dashboard/employee-relations/cases")
        check("investigator A can list", listed.status_code == 200, listed.status_code)
        ids = [str(item.get("case_id")) for item in (listed.json().get("cases") or [])]
        check("investigator A sees case A", case_a in ids, ids)
        check("investigator A does not see case B", case_b not in ids, ids)
        other = client.get(f"/dashboard/employee-relations/cases/{case_b}")
        check("investigator A IDOR on case B blocked", other.status_code == 403, other.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=["er.read", "er.investigate", "er.sensitive"], phone=HR, user_id=INV_A))
        evid = client.get(f"/dashboard/employee-relations/evidence/{evidence_id}/content")
        check("authorized evidence retrieve", evid.status_code == 200, evid.status_code)
        evid_text = evid.text
        check("authorized evidence hides raw URL", RAW_REF not in evid_text, evid_text[:300])
        check("authorized evidence sealed", evid.json().get("sealed") is True or evid.json().get("raw_provider_url") is None, evid.json())

        use(_ctx(COMPANY, role="hr_admin", perms=["er.read"], phone=HR, user_id=INV_B))
        blocked_evid = client.get(f"/dashboard/employee-relations/evidence/{evidence_id}/content")
        check("unauthorized evidence 403", blocked_evid.status_code == 403, blocked_evid.status_code)
        check("unauthorized evidence hides raw URL", RAW_REF not in blocked_evid.text)

        use(_ctx(COMPANY, role="hr_admin", perms=["er.read"], phone=HR, user_id=INV_A))
        exported = client.get("/dashboard/employee-relations/export")
        check("export without er.export is 403", exported.status_code == 403, exported.status_code)

        use(_ctx(COMPANY, role="hr_admin", perms=ER_PERMS, phone=HR, user_id=ADMIN))
        exported_ok = client.get("/dashboard/employee-relations/export")
        check("export with er.export", exported_ok.status_code == 200, exported_ok.status_code)
        check("export hides raw URL", RAW_REF not in exported_ok.text)

        use(_ctx(COMPANY, role="hr_admin", perms=ER_PERMS, phone=HR, user_id=INV_A))
        mobile = client.get("/dashboard/mobile/employee-relations")
        check("authorized mobile queue", mobile.status_code == 200, mobile.status_code)
        mobile_text = mobile.text
        check("mobile queue privacy-safe", "allegation" not in mobile_text.lower() and RAW_REF not in mobile_text)
        check(
            "mobile queue generic copy",
            "Employee Relations action requires your attention" in mobile_text,
            mobile_text[:400],
        )
        mobile_case = client.get(f"/dashboard/mobile/employee-relations/cases/{case_a}")
        check("authorized mobile summary", mobile_case.status_code == 200, mobile_case.status_code)
        check("mobile summary has no notes", mobile_case.json().get("notes_included") is False, mobile_case.json())

        use(_ctx(COMPANY, role="hr_admin", perms=HR_NO_ER, phone=HR, user_id=ORD_HR))
        mobile_denied = client.get("/dashboard/mobile/employee-relations")
        check("unauthorized mobile fail-closed", mobile_denied.status_code == 403, mobile_denied.status_code)

        use(_ctx(COMPANY_B, role="hr_admin", perms=ER_PERMS, phone=HR, user_id=ADMIN))
        cross = client.get(f"/dashboard/employee-relations/cases/{case_a}")
        check("tenant isolation blocks foreign case", cross.status_code in {403, 404}, cross.status_code)
    finally:
        app.app.dependency_overrides.clear()


def _env_on() -> None:
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_C4"] = "on"
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"] = ""
    os.environ["WATHEFNI_BENEFITS_C3"] = "off"
    os.environ["WATHEFNI_LEARNING_C2"] = "off"
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_ENGAGEMENT_C5"] = "off"


def main() -> int:
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    print("    PRODUCTION READINESS R5G — employee relations surface (staging DB)")
    print(f"    tenant: {COMPANY}")
    os.environ.setdefault("WATHEFNI_DATA_SAFETY_ACK", "non-production")

    try:
        import app
        import production_data_safety as pds
        import capability_readiness as ready
        import employee_relations_c4 as c4
        import employee_relations_surfaces as surfaces
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
    case_a = ""
    case_b = ""
    evidence_id = ""
    outcome_id = ""
    type_id = ""

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for code, name in ((COMPANY, f"R5G {COMPANY}"), (COMPANY_B, f"R5G {COMPANY_B}")):
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
                    cur, company_code=COMPANY_B, actor_phone=HR, enabled=True, reason="r5g enable b"
                )
                synced = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=True, reason="r5g enable"
                )
                check("sync catalog entitlement", synced.get("ok") is True, synced)
                check("second tenant enabled", synced_b.get("ok") is True, synced_b)
                check("ER enableable", ready.customer_enableable("employee_relations") is True)

                empty = surfaces.workspace_summary(
                    cur, company_code=COMPANY, actor_key=ADMIN, actor_role="er_admin"
                )
                check("empty assignment is empty not company-wide", empty.get("resource_state") == "empty", empty)
                check("empty counts are zeros", (empty.get("counts") or {}).get("assigned_open") == 0, empty)
                check("performance off", empty.get("performance_on") is False, empty)
                check("talent off", empty.get("talent_on") is False, empty)
                check("payroll off", empty.get("payroll_on") is False, empty)
                check("benefits off", empty.get("benefits_on") is False, empty)
                check("engagement off", empty.get("engagement_on") is False, empty)

                ctype = c4.upsert_case_type(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    code="grievance",
                    title_en="Grievance",
                    title_ar="تظلم",
                )
                check("case type created", ctype.get("ok") is True, ctype)
                type_id = str((ctype.get("case_type") or {}).get("case_type_id") or ctype.get("stable_id") or "")

                opened = surfaces.intake_case(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_type_id=type_id,
                    subject_employee_key=EMP,
                    intake_source="hr_created",
                    summary_en="Intake narrative stays internal",
                    allegation_en="Allegation is not proven",
                    due_date=(date.today() - timedelta(days=1)).isoformat(),
                )
                check("A intake", opened.get("ok") is True, opened)
                check("intake is not finding", opened.get("intake_is_not_finding") is True)
                case_a = str((opened.get("case") or {}).get("case_id") or "")

                other = surfaces.intake_case(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_type_id=type_id,
                    subject_employee_key=f"{EMP}-b",
                    intake_source="hr_created",
                    summary_en="Case B",
                )
                check("case B opened", other.get("ok") is True, other)
                case_b = str((other.get("case") or {}).get("case_id") or "")

                triaged = surfaces.triage_case(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_id=case_a,
                    reason="triage",
                )
                check("A triage", triaged.get("ok") is True, triaged)

                assigned = surfaces.assign_investigator(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_id=case_a,
                    investigator_key=INV_A,
                )
                check("A assign investigator", assigned.get("ok") is True, assigned)
                grant_sens = surfaces.grant_access(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    case_id=case_a,
                    target_actor_key=INV_A,
                    target_actor_role="investigator",
                    permissions=["view", "investigate", "sensitive_evidence"],
                )
                check("grant sensitive evidence to INV_A", grant_sens.get("ok") is True, grant_sens)
                surfaces.grant_access(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    case_id=case_a,
                    target_actor_key=INV_B,
                    target_actor_role="investigator",
                    permissions=["view"],
                )

                note = surfaces.add_note(
                    cur,
                    company_code=COMPANY,
                    actor_key=INV_A,
                    actor_role="investigator",
                    case_id=case_a,
                    body_en="Investigator-only note must stay hidden",
                    body_ar="ملاحظة للمحقق فقط",
                )
                check("A investigation note", note.get("ok") is True, note)
                check("note metadata only", "Investigator-only note" not in str(note.get("note") or {}))

                evid = surfaces.attach_evidence(
                    cur,
                    company_code=COMPANY,
                    actor_key=INV_A,
                    actor_role="investigator",
                    case_id=case_a,
                    shared_document_ref=RAW_REF,
                    label_en="Sensitive file",
                    label_ar="ملف حساس",
                    sensitive=True,
                )
                check("A evidence attached", evid.get("ok") is True, evid)
                evidence_id = str((evid.get("evidence") or {}).get("evidence_id") or "")
                check("attach response hides raw URL", RAW_REF not in str(evid))

                retrieved = surfaces.retrieve_evidence(
                    cur,
                    company_code=COMPANY,
                    actor_key=INV_A,
                    actor_role="investigator",
                    evidence_id=evidence_id,
                )
                check("C authorized evidence", retrieved.get("allowed") is True, retrieved)
                check("C raw URL stripped", RAW_REF not in str(retrieved))
                denied_evid = surfaces.retrieve_evidence(
                    cur,
                    company_code=COMPANY,
                    actor_key=INV_B,
                    actor_role="investigator",
                    evidence_id=evidence_id,
                )
                check("C unauthorized evidence denied", denied_evid.get("allowed") is False, denied_evid)
                check("C unauthorized hides raw URL", RAW_REF not in str(denied_evid))

                finding = surfaces.submit_finding(
                    cur,
                    company_code=COMPANY,
                    actor_key=INV_A,
                    actor_role="investigator",
                    case_id=case_a,
                    findings_en="Finding is not an outcome",
                )
                check("A finding", finding.get("ok") is True, finding)
                check("investigation is not finding/outcome", finding.get("finding_is_not_outcome") is True)

            conn.commit()

        run_http_security_tests(app, case_a, case_b, evidence_id)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.grant_access(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    case_id=case_a,
                    target_actor_key=ADMIN,
                    target_actor_role="er_admin",
                    permissions=["view", "manage", "investigate", "decide", "sensitive_evidence"],
                )
                outcome = surfaces.record_outcome(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_id=case_a,
                    outcome_code="referral",
                    summary_en="Referral only",
                )
                check("A outcome", outcome.get("ok") is True, outcome)
                check("outcome does not mutate employment", outcome.get("employment_mutated") is False)
                outcome_id = str((outcome.get("outcome") or {}).get("outcome_id") or "")

                handoff = surfaces.create_handoff_idempotent(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_id=case_a,
                    outcome_id=outcome_id,
                    handoff_payload={"requested_change": "review_only"},
                )
                check("E handoff created", handoff.get("ok") is True, handoff)
                check("E handoff not applied", handoff.get("applied") is False or (handoff.get("handoff") or {}).get("applied") is False)
                check("E ER did not mutate employment", handoff.get("employment_mutated_by_er") is False)
                replay = surfaces.create_handoff_idempotent(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_id=case_a,
                    outcome_id=outcome_id,
                )
                check("E handoff idempotent", replay.get("idempotent_replay") is True, replay)

                history = surfaces.case_history(cur, company_code=COMPANY, actor_key=ADMIN, case_id=case_a)
                actions = {str(event.get("action")) for event in (history.get("events") or [])}
                check("A history preserved", history.get("ok") is True and len(history.get("events") or []) >= 1, history)
                check("history reconstructable", history.get("historically_reconstructable") is True)

                listed_a = surfaces.list_cases(
                    cur, company_code=COMPANY, actor_key=INV_A, actor_role="investigator"
                )
                ids_a = [str(item.get("case_id")) for item in (listed_a.get("cases") or [])]
                check("B INV_A lists case A", case_a in ids_a, ids_a)
                check("B INV_A cannot list case B", case_b not in ids_a, ids_a)
                denied_b = surfaces.case_detail(
                    cur, company_code=COMPANY, actor_key=INV_A, actor_role="investigator", case_id=case_b
                )
                check("B INV_A cannot read case B", denied_b.get("error") == "er_access_denied", denied_b)

                ordinary = surfaces.list_cases(
                    cur, company_code=COMPANY, actor_key=ORD_HR, actor_role="ordinary_hr"
                )
                check("B ordinary HR empty assignment", ordinary.get("total") == 0, ordinary)

                mgr_list = surfaces.list_cases(
                    cur, company_code=COMPANY, actor_key=MGR, actor_role="manager"
                )
                check("D manager has zero cases", mgr_list.get("total") == 0, mgr_list)
                mgr_detail = surfaces.case_detail(
                    cur, company_code=COMPANY, actor_key=MGR, actor_role="manager", case_id=case_a
                )
                check("D manager cannot read case", mgr_detail.get("error") == "er_access_denied", mgr_detail)
                mgr_contrib_denied = surfaces.scoped_contribution(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=MGR,
                    actor_role="manager",
                    case_id=case_a,
                    body_en="should fail",
                )
                check("D manager contribution without grant denied", mgr_contrib_denied.get("ok") is False)
                surfaces.grant_access(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    case_id=case_a,
                    target_actor_key=MGR,
                    target_actor_role="manager",
                    permissions=["view"],
                )
                mgr_contrib = surfaces.scoped_contribution(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=MGR,
                    actor_role="manager",
                    case_id=case_a,
                    body_en="scoped only",
                )
                check("D scoped contribution allowed", mgr_contrib.get("ok") is True and mgr_contrib.get("scoped_only") is True, mgr_contrib)
                check("D contribution is not full case access", mgr_contrib.get("full_case_access") is False)

                detail_b = surfaces.case_detail(
                    cur, company_code=COMPANY, actor_key=INV_B, actor_role="investigator", case_id=case_a
                )
                check("B INV_B can see granted case header", detail_b.get("ok") is True, detail_b)
                notes = ((detail_b.get("investigation") or {}).get("notes") or [])
                check("investigator notes hidden from view-only", all(item.get("body_redacted") is True for item in notes) or not notes, notes)

                asst_denied = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor_key=ORD_HR, question_kind="process_metadata", case_id=case_a
                )
                check("assistant unauthorized denied", asst_denied.get("error") == "er_access_denied", asst_denied)
                asst_mutate = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor_key=ADMIN, question_kind="mutate_case", case_id=case_a
                )
                check("assistant mutation forbidden", asst_mutate.get("error") == "mutation_forbidden", asst_mutate)
                asst_ok = surfaces.assistant_query(
                    cur, company_code=COMPANY, actor_key=ADMIN, question_kind="process_metadata", case_id=case_a
                )
                check("assistant authorized metadata only", asst_ok.get("ok") is True and asst_ok.get("mutations") is False, asst_ok)
                check("wave5 forbids allegation text", c4.wave5_payload_is_safe({"allegation_text": "x"}) is False)
                check("wave5 allows typed fact", c4.wave5_payload_is_safe({"status": "closed", "case_type_code": "grievance"}) is True)

                check("EN status label", bool(c4.status_label("investigating", lang="en")))
                check("AR status label", bool(c4.status_label("investigating", lang="ar")))

                disabled = surfaces.sync_catalog_entitlement(
                    cur, company_code=COMPANY, actor_phone=HR, enabled=False, reason="disable after use"
                )
                check("G disable ok", disabled.get("ok") is True, disabled)
                check("G history preserved flag", disabled.get("history_preserved") is True)
                cur.execute("SELECT COUNT(*) AS n FROM er_cases WHERE company_code=%s", (COMPANY,))
                retained = int(dict(cur.fetchone()).get("n") or 0)
                check("G historical cases retained", retained >= 2, retained)
                blocked = surfaces.intake_case(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    actor_key=ADMIN,
                    actor_role="er_admin",
                    case_type_id=type_id,
                    subject_employee_key=EMP,
                    intake_source="hr_created",
                )
                check("G new intake blocked", blocked.get("error") == "employee_relations_disabled_for_company", blocked)
                unavailable = surfaces.workspace_summary(
                    cur, company_code=COMPANY, actor_key=ADMIN, actor_role="er_admin"
                )
                check("G disabled workspace unavailable", unavailable.get("resource_state") == "unavailable", unavailable)
                check("G disabled counts are not fake zeros", unavailable.get("counts") is None, unavailable)
            conn.commit()

        if hasattr(app, "notification_source_module_enabled"):
            check(
                "G notifications suppressed when module off",
                app.notification_source_module_enabled(COMPANY, "employee_relations") is False,
            )
    finally:
        cleanup(app, [COMPANY, COMPANY_B])

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("R5G_EMPLOYEE_RELATIONS_SURFACE_DB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
