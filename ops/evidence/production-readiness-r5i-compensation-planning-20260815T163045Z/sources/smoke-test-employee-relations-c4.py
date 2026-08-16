#!/usr/bin/env python3
"""Wave 6 C4 Employee Relations qualification prove."""
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
COMPANY = f"ER1{_N:05d}"[:12].upper()
OTHER = f"ER9{_N:05d}"[:12].upper()
HR = f"9656810{_N:05d}"
ADMIN = "er-admin-1"
INV = "investigator-1"
ORD_HR = "ordinary-hr-1"
MGR = "manager-1"
EMP = "E1"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def _flags(*, on="on", companies="") -> None:
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_C4"] = on
    os.environ["WATHEFNI_EMPLOYEE_RELATIONS_COMPANIES"] = companies


def main() -> int:
    print("    employee relations c4 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import employee_relations_c4 as er
    import setup_console_wave6_policies as w6

    check("phase", er.PHASE == "employee_relations_c4")
    check("stamp", er.PASS_STAMP == "EMPLOYEE_RELATIONS_FULL_PASS")
    check("commercial key", er.COMMERCIAL_MODULE_KEY == "employee_relations")
    honesty = er.honesty_payload()
    check("no employee ownership", honesty["does_not_own_employee_employment_org"] is True)
    check("case-level need-to-know", honesty["case_level_need_to_know"] is True)
    check("ordinary hr not er", honesty["ordinary_hr_not_er"] is True)
    check("manager not er", honesty["manager_not_er"] is True)
    check("submission not finding", honesty["employee_submission_not_finding"] is True)
    check("investigation not outcome", honesty["investigation_not_outcome"] is True)
    check("outcome not employment", honesty["outcome_not_employment_mutation"] is True)
    check("no invented KW legal", honesty["no_invented_kuwait_legal_outcomes"] is True)
    check("wave5 excludes free text", honesty["wave5_excludes_sensitive_free_text"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    check("works without engagement", honesty["works_without_engagement"] is True)
    check("works without payroll", honesty["works_without_payroll"] is True)
    check("works without talent/perf", honesty["works_without_talent_performance"] is True)
    check("setup wave6 er", "employee_relations" in w6.WAVE6_MODULE_KEYS)
    check("setup honesty er", w6.honesty_payload()["er_case_level_need_to_know"] is True)
    check("bilingual en", bool(er.status_label("investigating", lang="en")))
    check("bilingual ar", bool(er.status_label("investigating", lang="ar")))
    surf = er.surface_composition_rules()
    check("hr web sealed", surf["hr_web"]["primary_sealed_workspace"] is True)
    check("manager no er by line", surf["manager"]["no_er_by_reporting_line"] is True)
    check("employee safe only", surf["employee_app"]["safe_status_only"] is True)
    check("assistant no narrative dump", surf["assistant"]["no_case_narrative_dump"] is True)

    _flags(on="off", companies=COMPANY)
    check("gate off", er.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist admits after R5G", er.runtime_gate_for_company(COMPANY).get("ok") is True)
    _flags(companies=COMPANY)
    check("gate on", er.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", er.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(er.__file__).read_text(encoding="utf-8")
    check("schema cases", "er_cases" in source)
    check("schema access grants", "er_access_grants" in source)
    check("employment mutate check", "employment_mutated = false" in source)
    check("no employee table", "CREATE TABLE IF NOT EXISTS employees" not in source)
    check("payload safe notify", "payload_safe = true" in source)

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
    try:
        with conn.cursor() as cur:
            er.ensure_employee_relations_c4_schema(cur)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"ER {code}"),
                )

            blocked = er.upsert_case_type(
                cur, company_code=COMPANY, actor_phone=HR, code="grievance",
                title_en="Grievance", title_ar="تظلم",
            )
            check("disabled blocks ops", blocked.get("error") == "employee_relations_disabled_for_company", blocked)

            enabled = er.enable_company_employee_relations(
                cur, company_code=COMPANY, actor_phone=HR, reason="c4 prove",
                employee_submission_enabled=True, manager_referral_enabled=True,
            )
            check("enable company", enabled.get("ok") is True, enabled)

            pol = w6.get_wave6_module_policy(cur, COMPANY, "employee_relations")
            check("setup policy get", pol.get("ok") is True and pol["policy"]["enabled"] is True, pol)

            ctype = er.upsert_case_type(
                cur, company_code=COMPANY, actor_phone=HR, code="grievance",
                title_en="Grievance", title_ar="تظلم", type_version=1,
                allowed_outcomes=["no_action", "warning_corrective", "investigation_closed", "referral"],
            )
            check("case type v1", ctype.get("ok") is True, ctype)
            type_id_v1 = ctype["stable_id"]

            ctype_v2 = er.upsert_case_type(
                cur, company_code=COMPANY, actor_phone=HR, code="grievance",
                title_en="Grievance v2", title_ar="تظلم ٢", type_version=2,
                allowed_outcomes=["no_action", "investigation_closed"],
            )
            check("case type version history", ctype_v2.get("ok") is True and int(ctype_v2["case_type"]["type_version"]) == 2, ctype_v2)

            # Employee-submitted case (not a finding)
            opened = er.open_case(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                case_type_id=type_id_v1,
                subject_employee_key=EMP,
                reporter_employee_key=EMP,
                intake_source="employee_submitted",
                actor_role="er_admin",
                actor_key=ADMIN,
                summary_en="Workplace concern",
                summary_ar="قلق في مكان العمل",
                due_date=today - timedelta(days=1),
                allegation_en="Sensitive allegation text must not enter Wave5",
                allegation_ar="نص ادعاء حساس",
            )
            check("open case", opened.get("ok") is True, opened)
            check("submission not finding", opened.get("employee_submission_not_finding") is True, opened)
            case_id = str(opened["case"]["case_id"])
            check("pinned type version", int(opened["case"]["case_type_version"]) == 1, opened)

            sla = er.case_derived_sla(opened["case"], today=today)
            check("due overdue not outcome", sla["overdue"] is True and sla["outcome_changed"] is False, sla)

            # Ordinary HR denied
            ord_denied = er.check_case_permission(
                cur, company_code=COMPANY, case_id=case_id, actor_key=ORD_HR, actor_role="ordinary_hr", permission="view"
            )
            check("ordinary HR denied", ord_denied.get("allowed") is False and ord_denied.get("ordinary_hr_not_er") is True, ord_denied)

            # Manager denied by default
            mgr_denied = er.check_case_permission(
                cur, company_code=COMPANY, case_id=case_id, actor_key=MGR, actor_role="manager", permission="view"
            )
            check("manager denied by default", mgr_denied.get("allowed") is False and mgr_denied.get("manager_not_er") is True, mgr_denied)

            detail_denied = er.er_case_detail(
                cur, company_code=COMPANY, actor_key=ORD_HR, actor_role="ordinary_hr", case_id=case_id
            )
            check("ordinary HR detail denied", detail_denied.get("error") == "er_access_denied", detail_denied)

            # Manager referral — no content access
            mgr_case = er.open_case(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                case_type_id=type_id_v1,
                subject_employee_key="E2",
                reporter_employee_key=MGR,
                intake_source="manager_referred",
                actor_role="manager",
                actor_key=MGR,
                summary_en="Referral",
                summary_ar="إحالة",
            )
            check("manager referral opens", mgr_case.get("ok") is True and mgr_case.get("manager_gains_no_content_by_referral") is True, mgr_case)
            mgr_case_id = str(mgr_case["case"]["case_id"])
            # Grant er admin on referral case for cleanup path
            er.grant_case_access(
                cur, company_code=COMPANY, actor_phone=HR, case_id=mgr_case_id,
                actor_key=ADMIN, actor_role="er_admin", permissions=list(er.ACCESS_PERMS),
            )
            mgr_view = er.check_case_permission(
                cur, company_code=COMPANY, case_id=mgr_case_id, actor_key=MGR, actor_role="manager", permission="view"
            )
            check("manager referral no content", mgr_view.get("allowed") is False, mgr_view)

            # Assign investigator
            assigned = er.assign_investigator(
                cur, company_code=COMPANY, actor_phone=HR, actor_key=ADMIN, actor_role="er_admin",
                case_id=case_id, investigator_key=INV,
            )
            check("assign investigator", assigned.get("ok") is True and assigned.get("shared_task_reused") is True, assigned)

            inv_view = er.check_case_permission(
                cur, company_code=COMPANY, case_id=case_id, actor_key=INV, actor_role="investigator", permission="investigate"
            )
            check("investigator scoped", inv_view.get("allowed") is True, inv_view)

            er.transition_case(
                cur, company_code=COMPANY, actor_phone=HR, actor_key=ADMIN, actor_role="er_admin",
                case_id=case_id, to_status="investigating",
            )

            note = er.add_investigation_note(
                cur, company_code=COMPANY, actor_key=INV, actor_role="investigator",
                case_id=case_id, body_en="Confidential investigator note", body_ar="ملاحظة سرية",
            )
            check("investigation note confidential", note.get("ok") is True and note.get("hidden_from_employee") is True, note)

            finding = er.submit_finding(
                cur, company_code=COMPANY, actor_key=INV, actor_role="investigator",
                case_id=case_id, findings_en="Locked findings text", findings_ar="نتائج", lock=True,
            )
            check("finding locked", finding.get("ok") is True and finding.get("investigation_not_outcome") is True, finding)
            overwrite = er.submit_finding(
                cur, company_code=COMPANY, actor_key=INV, actor_role="investigator",
                case_id=case_id, findings_en="Attempt overwrite", lock=True,
            )
            check("locked findings not overwritten", overwrite.get("error") == "locked_findings_not_silently_overwritten", overwrite)

            evid = er.attach_evidence(
                cur, company_code=COMPANY, actor_key=INV, actor_role="investigator",
                case_id=case_id, shared_document_ref="doc://er/ev-1", label_en="Doc", sensitive=True,
            )
            check("evidence attached", evid.get("ok") is True, evid)
            evidence_id = str(evid["evidence"]["evidence_id"])

            # Sensitive evidence denied without grant
            for channel in ("api", "direct_url", "export", "assistant"):
                denied = er.access_evidence(
                    cur, company_code=COMPANY, actor_key=ORD_HR, actor_role="ordinary_hr",
                    evidence_id=evidence_id, access_channel=channel,
                )
                check(f"evidence deny {channel}", denied.get("allowed") is False and denied.get("fail_closed") is True, denied)

            inv_evid_denied = er.access_evidence(
                cur, company_code=COMPANY, actor_key=INV, actor_role="investigator",
                evidence_id=evidence_id, access_channel="api",
            )
            check("investigator needs sensitive grant", inv_evid_denied.get("allowed") is False, inv_evid_denied)

            er.grant_case_access(
                cur, company_code=COMPANY, actor_phone=HR, case_id=case_id,
                actor_key=INV, actor_role="investigator",
                permissions=["view", "investigate", "sensitive_evidence"],
            )
            inv_evid_ok = er.access_evidence(
                cur, company_code=COMPANY, actor_key=INV, actor_role="investigator",
                evidence_id=evidence_id, access_channel="api",
            )
            check("investigator sensitive ok", inv_evid_ok.get("allowed") is True, inv_evid_ok)

            asst_evid = er.access_evidence(
                cur, company_code=COMPANY, actor_key="assistant", actor_role="assistant",
                evidence_id=evidence_id, access_channel="assistant",
            )
            check("assistant evidence denied", asst_evid.get("allowed") is False, asst_evid)

            # Employee safe view
            emp_view = er.employee_safe_case_view(cur, company_code=COMPANY, employee_key=EMP, case_id=case_id)
            check(
                "employee safe view",
                emp_view.get("ok") is True
                and emp_view.get("internal_notes_included") is False
                and emp_view.get("witness_statements_included") is False
                and emp_view.get("investigation_detail_included") is False
                and emp_view.get("evidence_detail_included") is False,
                emp_view,
            )

            msg = er.post_safe_employee_message(
                cur, company_code=COMPANY, actor_phone=HR, actor_key=ADMIN, actor_role="er_admin",
                case_id=case_id, body_en="We received your case.", body_ar="استلمنا قضيتك.",
            )
            check("safe message", msg.get("ok") is True, msg)
            unsafe = er.post_safe_employee_message(
                cur, company_code=COMPANY, actor_phone=HR, actor_key=ADMIN, actor_role="er_admin",
                case_id=case_id, body_en="Witness: secret", body_ar="شاهد",
            )
            check("unsafe message blocked", unsafe.get("error") == "unsafe_employee_message_content", unsafe)

            # Decide permission for outcome
            er.grant_case_access(
                cur, company_code=COMPANY, actor_phone=HR, case_id=case_id,
                actor_key=ADMIN, actor_role="er_admin",
                permissions=list(er.ACCESS_PERMS),
            )
            outcome = er.record_outcome(
                cur, company_code=COMPANY, actor_phone=HR, actor_key=ADMIN, actor_role="er_admin",
                case_id=case_id, outcome_code="warning_corrective",
                summary_en="Corrective coaching", summary_ar="توجيه تصحيحي",
            )
            check(
                "outcome not employment mutation",
                outcome.get("ok") is True
                and outcome.get("outcome_not_employment_mutation") is True
                and outcome.get("employment_mutated") is False,
                outcome,
            )
            outcome_id = str(outcome["outcome"]["outcome_id"])

            handoff = er.create_employment_change_handoff(
                cur, company_code=COMPANY, actor_phone=HR, actor_key=ADMIN, actor_role="er_admin",
                case_id=case_id, outcome_id=outcome_id,
                handoff_payload={"suggested": "performance_warning_case", "not_applied": True},
            )
            check(
                "employment handoff explicit",
                handoff.get("ok") is True
                and handoff.get("employment_mutated_by_er") is False
                and handoff.get("wave3_employment_change_remains_authority") is True,
                handoff,
            )

            # Wave 5 facts exclude sensitive free text
            cur.execute("SELECT payload FROM er_wave5_fact_outbox WHERE company_code=%s", (COMPANY,))
            payloads = [dict(r)["payload"] for r in cur.fetchall()]
            if payloads and isinstance(payloads[0], str):
                import json
                payloads = [json.loads(p) if isinstance(p, str) else p for p in payloads]
            safe = all(er.wave5_payload_is_safe(dict(p)) for p in payloads)
            check("wave5 facts safe", safe and len(payloads) >= 1, payloads[:3])
            check(
                "no allegation text in facts",
                not any("Sensitive allegation" in str(p) for p in payloads),
                payloads[:3],
            )

            asst = er.assistant_query_er(
                cur, company_code=COMPANY, actor=HR, question_kind="process_metadata", case_id=case_id
            )
            check("assistant read metadata", asst.get("ok") is True and asst.get("mutations") is False and asst.get("no_case_narrative_dump") is True, asst)
            asst_bad = er.assistant_query_er(
                cur, company_code=COMPANY, actor=HR, question_kind="mutate_case", case_id=case_id
            )
            check("assistant mutation forbidden", asst_bad.get("error") == "mutation_forbidden", asst_bad)

            n1 = er._notify_dedupe(cur, company=COMPANY, key="triage:x")
            n2 = er._notify_dedupe(cur, company=COMPANY, key="triage:x")
            check("notify safe first", n1.get("payload_safe") is True and n1.get("sent") is True, n1)
            check("notify dedupe", n2.get("deduped") is True, n2)

            # Historical type version preserved after Setup type v2 exists
            cur.execute("SELECT case_type_version FROM er_cases WHERE case_id=%s", (case_id,))
            pinned = int(dict(cur.fetchone())["case_type_version"])
            check("closed case type version intact", pinned == 1, pinned)

            # Governed reopen
            reopened = er.reopen_case(
                cur, company_code=COMPANY, actor_phone=HR, actor_key=ADMIN, actor_role="er_admin",
                case_id=case_id, reason="new evidence",
            )
            check("governed reopen", reopened.get("ok") is True and reopened.get("governed_reopen") is True, reopened)

            # Policy toggles
            er.enable_company_employee_relations(
                cur, company_code=COMPANY, actor_phone=HR, reason="disable submission",
                employee_submission_enabled=False, manager_referral_enabled=False,
            )
            no_sub = er.open_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type_id=type_id_v1,
                subject_employee_key="E3", intake_source="employee_submitted",
                actor_role="employee", actor_key="E3",
            )
            check("employee submission off", no_sub.get("error") == "employee_submission_disabled", no_sub)
            no_mgr = er.open_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type_id=type_id_v1,
                subject_employee_key="E3", intake_source="manager_referred",
                actor_role="manager", actor_key=MGR,
            )
            check("manager referral off", no_mgr.get("error") == "manager_referral_disabled", no_mgr)

            other = er.upsert_case_type(
                cur, company_code=OTHER, actor_phone=HR, code="complaint",
                title_en="x", title_ar="س",
            )
            check("other company gated", other.get("ok") is not True, other)

            off = er.disable_company_employee_relations(cur, company_code=COMPANY, actor_phone=HR, reason="toggle off")
            check("disable retains history", off.get("history_retained") is True, off)
            blocked2 = er.open_case(
                cur, company_code=COMPANY, actor_phone=HR, case_type_id=type_id_v1,
                subject_employee_key="E9", intake_source="hr_created",
                actor_role="er_admin", actor_key=ADMIN,
            )
            check("ops blocked when off", blocked2.get("error") == "employee_relations_disabled_for_company", blocked2)
            cur.execute("SELECT COUNT(*) AS c FROM er_cases WHERE company_code=%s", (COMPANY,))
            retained = int(dict(cur.fetchone())["c"])
            check("history retained after disable", retained >= 1, retained)

            er.enable_company_employee_relations(cur, company_code=COMPANY, actor_phone=HR, reason="re-enable")
            matrix = er.honesty_payload(company_code=COMPANY)
            check("modularity without engagement", matrix["works_without_engagement"] is True)
            check("modularity without payroll", matrix["works_without_payroll"] is True)

            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            db_context.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("EMPLOYEE_RELATIONS_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
