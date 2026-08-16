#!/usr/bin/env python3
"""Wave 6 C2 Learning & Development qualification prove."""
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
COMPANY = f"LD1{_N:05d}"[:12].upper()
OTHER = f"LD9{_N:05d}"[:12].upper()
HR = f"9656790{_N:05d}"


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
    os.environ["WATHEFNI_LEARNING_C2"] = on
    os.environ["WATHEFNI_LEARNING_COMPANIES"] = companies


def main() -> int:
    print("    learning development c2 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import learning_development_c2 as ld
    import setup_console_wave6_policies as w6

    check("phase", ld.PHASE == "learning_development_c2")
    check("stamp", ld.PASS_STAMP == "LEARNING_DEVELOPMENT_FULL_PASS")
    check("commercial key", ld.COMMERCIAL_MODULE_KEY == "learning")
    honesty = ld.honesty_payload()
    check("no employee ownership", honesty["does_not_own_employee_employment_org"] is True)
    check("no c3 duplicate", honesty["does_not_duplicate_c3_development"] is True)
    check("no silent c3 close", honesty["completion_does_not_silently_close_development_action"] is True)
    check("no auto skill verify", honesty["completion_does_not_auto_verify_skill_or_competency"] is True)
    check("ja optional", honesty["ja_optional"] is True)
    check("talent optional", honesty["talent_optional"] is True)
    check("works perf/talent off", honesty["works_performance_talent_off"] is True)
    check("no lms player", honesty["no_full_lms_player_in_c2"] is True)
    check("external provider", honesty["external_provider_supported"] is True)
    check("costs informational", honesty["costs_informational_only"] is True)
    check("no payroll side effects", honesty["no_payroll_side_effects"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    check("facts not analytics", honesty["emits_typed_facts_not_analytics_engine"] is True)
    check("setup wave6 learning", "learning" in w6.WAVE6_MODULE_KEYS)
    check("setup honesty", w6.honesty_payload()["learning_does_not_duplicate_c3"] is True)
    check("bilingual en", bool(ld.status_label("assigned", lang="en")))
    check("bilingual ar", bool(ld.status_label("assigned", lang="ar")))
    surf = ld.surface_composition_rules()
    check("hr web primary admin", surf["hr_web"]["primary_admin"] is True)
    check("employee no hr admin", surf["employee_app"]["no_hr_admin"] is True)
    check("hr mobile thin", surf["hr_mobile"]["no_full_catalog_authoring"] is True)
    check("assistant read only", surf["assistant"]["mutations"] is False)

    _flags(on="off", companies=COMPANY)
    check("gate off", ld.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist admits after R5E", ld.runtime_gate_for_company(COMPANY).get("ok") is True)
    _flags(companies=COMPANY)
    check("gate on", ld.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", ld.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(ld.__file__).read_text(encoding="utf-8")
    check("schema has catalog", "ld_learning_items" in source)
    check("schema has assignments", "ld_assignments" in source)
    check("schema has completions", "ld_completions" in source)
    check("schema has certifications", "ld_certifications" in source)
    check("c3 silent close check", "silently_closed_c3 = false" in source)
    check("no employee table ownership", "CREATE TABLE IF NOT EXISTS employees" not in source)
    check("no development plan table", "CREATE TABLE IF NOT EXISTS perf_development" not in source)

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
            ld.ensure_learning_development_c2_schema(cur)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"LD {code}"),
                )

            # Module off without enable
            disabled = ld.upsert_provider(
                cur, company_code=COMPANY, actor_phone=HR, code="INT", name_en="Internal", name_ar="داخلي"
            )
            check("disabled blocks ops", disabled.get("error") == "learning_disabled_for_company", disabled)

            enabled = ld.enable_company_learning(
                cur, company_code=COMPANY, actor_phone=HR, reason="c2 prove"
            )
            check("enable company", enabled.get("ok") is True, enabled)

            # Setup policy get
            pol = w6.get_wave6_module_policy(cur, COMPANY, "learning")
            check("setup policy get", pol.get("ok") is True and pol["policy"]["enabled"] is True, pol)

            # Catalog + provider
            prov = ld.upsert_provider(
                cur, company_code=COMPANY, actor_phone=HR, code="EXT", name_en="External LMS", name_ar="منصة خارجية"
            )
            check("provider", prov.get("ok") is True, prov)
            provider_id = str(prov["provider"]["provider_id"])

            course = ld.upsert_learning_item(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="SAFE-101",
                item_type="mandatory_compliance",
                title_en="Safety Basics",
                title_ar="أساسيات السلامة",
                status="published",
                category="compliance",
                provider_id=provider_id,
                delivery_mode="self_paced",
                duration_minutes=45,
                completion_requirements={"pass_score": 80},
                optional_refs={"skill_keys": ["workplace_safety"], "competency_keys": ["compliance"]},
                reason="seed course",
            )
            check("catalog item", course.get("ok") is True and course.get("stable_id"), course)
            item_id = course["stable_id"]
            v1 = int(course["item"]["effective_version"])

            renamed = ld.upsert_learning_item(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="SAFE-101",
                item_type="mandatory_compliance",
                title_en="Safety Basics v2",
                title_ar="أساسيات السلامة ٢",
                status="published",
                category="compliance",
                provider_id=provider_id,
                completion_requirements={"pass_score": 85},
                reason="revise meaning",
            )
            check(
                "stable id + version bump",
                renamed.get("stable_id") == item_id and int(renamed["item"]["effective_version"]) == v1 + 1,
                renamed,
            )
            v2 = int(renamed["item"]["effective_version"])

            # Program path
            child = ld.upsert_learning_item(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="SAFE-LAB",
                item_type="instructor_led",
                title_en="Safety Lab",
                title_ar="مختبر السلامة",
                status="published",
                reason="child",
            )
            prog = ld.upsert_learning_item(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="SAFE-PATH",
                item_type="program",
                title_en="Safety Path",
                title_ar="مسار السلامة",
                status="published",
                reason="program",
            )
            check("program item", prog.get("ok") is True, prog)
            pin_ver = int(prog["item"]["effective_version"])
            child_link = ld.add_program_child(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                program_item_id=prog["stable_id"],
                child_item_id=child["stable_id"],
                program_version=pin_ver,
                sequence_no=1,
                required=True,
            )
            check("program child pinned version", child_link.get("pinned_program_version") == pin_ver, child_link)

            # Offering distinct from catalog
            offering = ld.create_offering(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                item_id=child["stable_id"],
                starts_at=datetime.now(timezone.utc) + timedelta(days=7),
                location_or_virtual="virtual",
                instructor="Trainer A",
                capacity=20,
            )
            check(
                "session distinct from catalog",
                offering.get("ok") is True and offering.get("catalog_item_not_duplicated") is True,
                offering,
            )

            # Assignment provenance + pinned item version (historical)
            asn = ld.create_assignment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E1",
                item_id=item_id,
                item_version=v1,
                source="hr_assigned",
                required=True,
                due_date=today - timedelta(days=1),
                reason="legacy assign before catalog edit",
            )
            check("assignment created", asn.get("ok") is True and asn.get("created") is True, asn)
            check(
                "historical item version pinned",
                int(asn["assignment"]["item_version"]) == v1 and v1 != v2,
                asn,
            )
            derived = ld.assignment_derived_state(asn["assignment"], today=today)
            check("overdue derived not failure", derived["overdue"] is True and derived["failed"] is False, derived)
            check("due_date_passed_is_not_failure", derived["due_date_passed_is_not_failure"] is True, derived)

            bad_complete = ld.advance_assignment(
                cur, company_code=COMPANY, actor_phone=HR, assignment_id=asn["assignment"]["assignment_id"], to_status="completed"
            )
            check("cannot complete via status alone", bad_complete.get("error") == "use_record_completion_for_completed", bad_complete)

            no_evidence = ld.record_completion(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                assignment_id=str(asn["assignment"]["assignment_id"]),
                evidence_source="manual_authorized",
            )
            check("evidence required", no_evidence.get("error") == "evidence_required", no_evidence)

            # Request ≠ approval ≠ enrollment ≠ completion
            req = ld.create_learning_request(
                cur, company_code=COMPANY, employee_key="E2", item_id=item_id, reason="want training"
            )
            check(
                "request only",
                req.get("ok") is True
                and req.get("is_approval") is False
                and req.get("is_enrollment") is False
                and req.get("is_completion") is False,
                req,
            )
            decided = ld.decide_learning_request(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                request_id=str(req["request"]["request_id"]),
                approve=True,
            )
            check(
                "approve creates enrollment not completion",
                decided.get("approved") is True
                and decided.get("enrollment_created") is True
                and decided.get("completion_created") is False,
                decided,
            )

            # External completion evidence
            enroll_id = str(decided["request"]["assignment_id"])
            completed = ld.record_completion(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                assignment_id=enroll_id,
                evidence_source="external_provider",
                evidence_ref="EXT-CERT-9",
                evidence_payload={"provider": "External LMS"},
                provider_id=provider_id,
            )
            check(
                "evidence-backed completion",
                completed.get("ok") is True
                and completed.get("frontend_checkbox_not_authority") is True
                and completed.get("skill_auto_verified") is False
                and completed.get("competency_auto_verified") is False,
                completed,
            )

            # Certification ≠ course completion
            cert = ld.issue_certification(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E2",
                cert_type="safety",
                title_en="Safety Certificate",
                title_ar="شهادة سلامة",
                issued_on=today,
                expires_on=today + timedelta(days=20),
                issuer="External LMS",
                evidence_ref="CERT-DOC-1",
                linked_completion_id=None,
            )
            check(
                "cert without implying from course alone",
                cert.get("ok") is True and cert.get("course_completion_does_not_imply_certification") is True,
                cert,
            )
            cert_status = ld.certification_derived_status(cert["certification"], today=today, warning_days=30)
            check("expiring derived not stored", cert_status["expiring"] is True and cert_status.get("expiring_soon_not_stored_truth") is True, cert_status)
            renewal = ld.issue_certification(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E2",
                cert_type="safety",
                title_en="Safety Certificate Renewed",
                title_ar="شهادة سلامة مجددة",
                issued_on=today,
                expires_on=today + timedelta(days=365),
                renewal_of=str(cert["certification"]["certification_id"]),
            )
            check("renewal preserves history link", renewal.get("ok") is True and str(renewal["certification"]["renewal_of"]) == str(cert["certification"]["certification_id"]), renewal)

            # Mandatory policy + idempotency
            policy = ld.create_mandatory_policy(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="ALL-SAFE",
                title_en="All employees safety",
                title_ar="سلامة جميع الموظفين",
                item_id=item_id,
                population_rule={"scope": "all_employees", "snapshot": ["E1", "E3"]},
                due_offset_days=14,
                policy_version=1,
            )
            check("mandatory policy", policy.get("ok") is True, policy)
            policy_id = str(policy["policy"]["policy_id"])
            gen1 = ld.generate_mandatory_assignments(
                cur, company_code=COMPANY, actor_phone=HR, policy_id=policy_id, employee_keys=["E1", "E3"]
            )
            check("first generation", gen1.get("ok") is True and set(gen1.get("created") or []) == {"E1", "E3"}, gen1)
            gen2 = ld.generate_mandatory_assignments(
                cur, company_code=COMPANY, actor_phone=HR, policy_id=policy_id, employee_keys=["E1", "E3"]
            )
            check("replay idempotent", set(gen2.get("replayed") or []) == {"E1", "E3"} and not gen2.get("created"), gen2)
            gen3 = ld.generate_mandatory_assignments(
                cur, company_code=COMPANY, actor_phone=HR, policy_id=policy_id, employee_keys=["E4"]
            )
            check("newly eligible", gen3.get("created") == ["E4"], gen3)

            # Policy revision creates new obligation — does not rewrite v1
            policy_v2 = ld.create_mandatory_policy(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="ALL-SAFE",
                title_en="All employees safety",
                title_ar="سلامة جميع الموظفين",
                item_id=item_id,
                population_rule={"scope": "all_employees", "snapshot": ["E1", "E3", "E5"]},
                due_offset_days=14,
                policy_version=2,
            )
            check("policy revision row", policy_v2.get("ok") is True and int(policy_v2["policy"]["policy_version"]) == 2, policy_v2)
            gen_v2 = ld.generate_mandatory_assignments(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                policy_id=str(policy_v2["policy"]["policy_id"]),
                employee_keys=["E1"],
            )
            check("revision creates new obligation", gen_v2.get("created") == ["E1"], gen_v2)
            cur.execute(
                """
                SELECT COUNT(*) AS c FROM ld_assignments
                 WHERE company_code=%s AND employee_key='E1' AND source='mandatory_policy'
                """,
                (COMPANY,),
            )
            mcount = int(dict(cur.fetchone())["c"])
            check("policy revision history safe (v1+v2)", mcount >= 2, mcount)

            # C3 fulfillment link — no silent close
            fake_action = str(uuid.uuid4())
            link = ld.link_development_fulfillment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                development_action_id=fake_action,
                assignment_id=enroll_id,
                completion_id=str(completed["completion"]["completion_id"]),
                item_id=item_id,
            )
            check(
                "c3 link evidence only",
                link.get("ok") is True
                and link.get("silently_closed_c3") is False
                and link.get("c3_remains_sole_development_authority") is True,
                link,
            )

            # Manager / employee / assistant scopes
            emp = ld.employee_learning_view(cur, company_code=COMPANY, employee_key="E1")
            check("employee view", emp.get("ok") is True and emp.get("hr_admin_exposed") is False, emp)
            mgr = ld.manager_learning_view(cur, company_code=COMPANY, manager_scope_employee_keys=["E1", "E3"])
            check("manager scoped", mgr.get("ok") is True and mgr.get("uses_canonical_manager_scope") is True, mgr)
            asst = ld.assistant_query_learning(
                cur, company_code=COMPANY, actor=HR, question_kind="mandatory_remaining", employee_key="E1"
            )
            check("assistant read", asst.get("ok") is True and asst.get("mutations") is False, asst)
            asst_bad = ld.assistant_query_learning(
                cur, company_code=COMPANY, actor=HR, question_kind="invent_completion", employee_key="E1"
            )
            check("assistant mutation forbidden", asst_bad.get("error") == "mutation_forbidden", asst_bad)

            # Notification dedupe
            n1 = ld._notify_dedupe(cur, company=COMPANY, key="due:E1:x")
            n2 = ld._notify_dedupe(cur, company=COMPANY, key="due:E1:x")
            check("notify first", n1.get("sent") is True and n1.get("deduped") is False, n1)
            check("notify dedupe", n2.get("deduped") is True, n2)

            # Wave 5 facts emitted
            cur.execute(
                "SELECT COUNT(*) AS c FROM ld_wave5_fact_outbox WHERE company_code=%s",
                (COMPANY,),
            )
            facts = int(dict(cur.fetchone())["c"])
            check("typed facts emitted", facts >= 2, facts)

            # Tenant isolation
            other_gate = ld.upsert_learning_item(
                cur,
                company_code=OTHER,
                actor_phone=HR,
                code="X",
                item_type="self_paced",
                title_en="x",
                title_ar="س",
            )
            check("other company gated", other_gate.get("ok") is not True, other_gate)

            # Module disable retains history
            off = ld.disable_company_learning(cur, company_code=COMPANY, actor_phone=HR, reason="toggle off")
            check("disable retains history flag", off.get("history_retained") is True, off)
            blocked = ld.create_assignment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key="E9",
                item_id=item_id,
                source="hr_assigned",
            )
            check("ops blocked when off", blocked.get("error") == "learning_disabled_for_company", blocked)
            cur.execute(
                "SELECT COUNT(*) AS c FROM ld_assignments WHERE company_code=%s",
                (COMPANY,),
            )
            retained = int(dict(cur.fetchone())["c"])
            check("history retained after disable", retained >= 1, retained)

            # Re-enable for modularity matrix honesty markers
            ld.enable_company_learning(cur, company_code=COMPANY, actor_phone=HR, reason="re-enable")
            matrix = ld.honesty_payload(company_code=COMPANY)
            check("modularity L&D without JA", matrix["works_without_ja"] is True)
            check("modularity L&D without Talent hard dep", matrix["talent_optional"] is True)
            check("modularity Performance off ok", matrix["works_performance_talent_off"] is True)

            # Forbidden ownership on catalog refs
            bad_refs = ld.upsert_learning_item(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                code="BAD",
                item_type="self_paced",
                title_en="Bad",
                title_ar="سيء",
                optional_refs={"employee_key": "E1"},
            )
            check("must not own employee truth", bad_refs.get("error") == "must_not_own_external_truth", bad_refs)

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
    print("LEARNING_DEVELOPMENT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
