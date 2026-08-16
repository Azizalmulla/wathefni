#!/usr/bin/env python3
"""Wave 4 C5 — Talent Profile / Dimensions synthetic prove."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"TP5{_N:05d}"[:12].upper()
OTHER = f"TPX{_N:05d}"[:12].upper()
HR = f"9656600{_N:05d}"
EMP = f"{COMPANY}-W4C5-{SUFFIX}"
EMP_PHONE = f"9656601{_N:05d}"
MGR_PHONE = f"9656602{_N:05d}"
OUT_PHONE = f"9656699{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, on: str, companies: str) -> None:
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = on
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = companies
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    # Performance OFF by default for modularity prove
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_REVIEWS_C2"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_C4"] = "off"


def main() -> int:
    print("    talent profile c5 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import talent_profile_c5 as c5

    check("c5 module", c5.PHASE == "talent_profile_c5")
    check("charter stamp", c5.PASS_STAMP == "TALENT_PROFILE_FULL_PASS")
    check("module key talent", c5.COMMERCIAL_MODULE_KEY == "talent")
    h = c5.honesty_payload()
    check("canonical identity", h.get("uses_canonical_employee_identity") is True)
    check("no shadow person", h.get("no_shadow_talent_person_table") is True)
    check("no master score", h.get("no_master_talent_score") is True)
    check("perf optional", h.get("performance_optional_not_hard_dependency") is True)
    check("talent w/o perf", h.get("talent_works_when_performance_off") is True)
    check("no hipo/9box", h.get("no_hipo_9box_succession_writes_in_c5") is True)
    check("perf ≠ potential", h.get("performance_is_not_potential") is True)
    check("c3 dev canonical", h.get("c3_development_remains_canonical") is True)
    check("pool isolated", h.get("recruiting_talent_pool_isolated") is True)
    check("assistant out", h.get("assistant_mutations") is False)
    check("EN claimed", c5.status_label("claimed", lang="en") == "Claimed")
    check("AR claimed", c5.status_label("claimed", lang="ar") == "مُدَّعى")
    check("rollback", "WATHEFNI_TALENT_PROFILE_C5=off" in str(c5.rollback_guidance()))
    forbid = c5.assert_no_forbidden_c5_writes()
    check("no forbidden writes", forbid.get("hipo_writes") is False and forbid.get("nine_box_writes") is False)

    _flags(on="off", companies="")
    check("global off", c5.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist", "allowlist" in str(c5.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary ok", c5.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c5.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    try:
        _db = app.db_connect()
        conn = _db.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            c5.ensure_talent_profile_c5_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"TP5 {COMPANY}"),
            )

            # Talent with Performance OFF — consume disabled
            en = c5.enable_company_talent_profile(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="c5 canary — performance off",
                performance_evidence_consume=False,
            )
            check("enable talent", en.get("ok") is True, en)
            check("perf consume off", en.get("settings", {}).get("performance_evidence_consume") is False)

            prof = c5.ensure_talent_profile(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=HR
            )
            check("canonical profile", prof.get("ok") is True, prof)
            check("identity employee_key", prof.get("identity", {}).get("employee_key") == EMP)
            check("no master score on profile", prof.get("master_talent_score") is None)
            check("no shadow person", prof.get("shadow_person_table") is False)

            # Employee aspiration with provenance
            asp = c5.update_employee_aspiration(
                cur,
                company_code=COMPANY,
                employee_phone=EMP_PHONE,
                employee_key=EMP,
                title_en="Lead platform engineering",
                title_ar="قيادة هندسة المنصة",
                detail_en="Prefer staff+ IC track",
            )
            check("employee aspiration", asp.get("ok") is True, asp)
            check("aspiration source employee", asp["fact"].get("source") == "employee_declared")

            # Manager assessed aspiration coexists — does not rewrite employee row
            mgr_asp = c5.forbid_silent_rewrite_employee_aspiration(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                employee_key=EMP,
                title_en="Manager sees people-leadership track",
                as_source="manager_assessed",
            )
            check("manager aspiration separate", mgr_asp.get("ok") is True, mgr_asp)
            listed = c5.list_dimension_facts(
                cur, company_code=COMPANY, employee_key=EMP,
                dimension_kind="career_aspiration", include_history=True, viewer_role="hr",
            )
            sources = {f.get("source") for f in listed.get("facts") or []}
            check("contradictory aspirations coexist", sources >= {"employee_declared", "manager_assessed"}, sources)
            emp_active = [
                f for f in (listed.get("facts") or [])
                if f.get("source") == "employee_declared" and f.get("status") == "active"
            ]
            check("employee aspiration intact", len(emp_active) == 1 and "Lead platform" in emp_active[0]["title_en"])

            # Strengths / development with provenance
            st = c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=MGR_PHONE, employee_key=EMP,
                dimension_kind="strength", title_en="Systems thinking",
                source="manager_assessed", visibility="manager_visible",
                reason="manager strength",
            )
            check("strength with provenance", st.get("ok") is True and st["fact"]["source"] == "manager_assessed")
            da = c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                dimension_kind="development_area", title_en="Executive presence",
                source="hr_assessed", visibility="hr_confidential",
                reason="hr development area",
            )
            check("dev area confidential", da.get("ok") is True and da["fact"]["visibility"] == "hr_confidential")

            emp_view = c5.list_dimension_facts(
                cur, company_code=COMPANY, employee_key=EMP, viewer_role="employee"
            )
            emp_kinds = {f.get("dimension_kind") for f in emp_view.get("facts") or []}
            check("employee cannot see hr_confidential", "development_area" not in emp_kinds, emp_kinds)

            # Skills: claim vs verified
            sk = c5.claim_skill(
                cur, company_code=COMPANY, actor_phone=EMP_PHONE, employee_key=EMP,
                skill_code="python", name_en="Python", name_ar="بايثون",
                proficiency_level="advanced",
            )
            check("skill claimed", sk.get("ok") is True and sk["skill"]["state"] == "claimed", sk)
            skill_id = str(sk["skill"]["skill_id"])
            ver = c5.verify_skill(
                cur, company_code=COMPANY, actor_phone=HR, skill_id=skill_id,
                reason="HR verified via work sample", proficiency_level="advanced",
            )
            check("skill verified distinct", ver.get("ok") is True and ver["skill"]["state"] == "verified", ver)
            cur.execute(
                "SELECT count(*) AS n FROM talent_skill_history WHERE skill_id=%s", (skill_id,)
            )
            check("skill history retained", int(dict(cur.fetchone())["n"]) >= 1)

            # Competency → Talent explicit contract
            bad_map = c5.create_competency_talent_mapping(
                cur, company_code=COMPANY, actor_phone=HR,
                competency_id="COMP-COLLAB", target_kind="skill", reason="missing code",
            )
            check("map without skill code rejected", bad_map.get("error") == "target_skill_code_required_for_skill_map")
            cmap = c5.create_competency_talent_mapping(
                cur, company_code=COMPANY, actor_phone=HR,
                competency_id="COMP-COLLAB", target_kind="skill",
                target_skill_code="collaboration", reason="explicit competency→skill contract",
                competency_framework_version=1,
            )
            check("explicit competency map", cmap.get("ok") is True, cmap)
            applied = c5.apply_competency_evidence(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                mapping_id=str(cmap["mapping"]["mapping_id"]),
                title_en="Collaboration",
            )
            check("competency evidence applied", applied.get("ok") is True, applied)
            check("skill ≠ auto competency object", applied["skill"]["source"] == "competency_evidence")

            q = c5.query_employees_with_skill(cur, company_code=COMPANY, skill_code="python", min_state="verified")
            check("mapping query by skill", any(m["employee_key"] == EMP for m in q.get("matches") or []), q)
            check("not 9-box precompute", q.get("nine_box_precomputed") is False)

            # Potential without Performance
            fw = c5.create_potential_framework(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Growth capacity framework",
                name_ar="إطار القدرة على النمو",
                dimensions=[
                    {"key": "learning_agility", "label_en": "Learning agility", "label_ar": "مرونة التعلم"},
                    {"key": "scope_expansion", "label_en": "Scope expansion", "label_ar": "توسيع النطاق"},
                ],
                scale_points=[
                    {"code": "emerging", "label_en": "Emerging", "label_ar": "ناشئ"},
                    {"code": "expanding", "label_en": "Expanding", "label_ar": "متوسع"},
                    {"code": "enterprise", "label_en": "Enterprise", "label_ar": "مؤسسي"},
                ],
                reason="configurable potential — not L/M/H hardcoded",
            )
            check("potential framework", fw.get("ok") is True, fw)
            framework_id = str(fw["framework"]["framework_id"])

            nosens = c5.submit_potential_assessment(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                framework_id=framework_id, rationale="Strong learning agility",
                dimension_scores={"learning_agility": "expanding", "scope_expansion": "emerging"},
                resulting_level="expanding", has_sensitive_permission=False,
            )
            check("potential needs sensitive", nosens.get("error") == "sensitive_permission_required", nosens)

            pot = c5.submit_potential_assessment(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                framework_id=framework_id, rationale="Strong learning agility evidenced in stretch projects",
                dimension_scores={"learning_agility": "expanding", "scope_expansion": "emerging"},
                resulting_level="expanding", has_sensitive_permission=True,
                reason="HR potential without performance",
            )
            check("potential without performance", pot.get("ok") is True, pot)
            check("perf ≠ potential flag", pot.get("performance_equals_potential") is False)
            check("not AI assigned", pot.get("ai_assigned") is False)
            assessment_id = str(pot["assessment"]["assessment_id"])
            acc = c5.accept_potential_assessment(
                cur, company_code=COMPANY, assessment_id=assessment_id,
                actor_phone=HR, reason="accept", has_sensitive_permission=True,
            )
            check("potential accepted", acc.get("ok") is True, acc)

            # Historical version survives later edit
            pot2 = c5.submit_potential_assessment(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                framework_id=framework_id, rationale="Updated after year of scope growth",
                dimension_scores={"learning_agility": "enterprise", "scope_expansion": "expanding"},
                resulting_level="enterprise", has_sensitive_permission=True,
                reason="new potential version",
            )
            check("potential new version", pot2.get("ok") is True and int(pot2["assessment"]["version"]) >= 2, pot2)
            cur.execute(
                """
                SELECT count(*) AS n, count(*) FILTER (WHERE status='withdrawn') AS w
                FROM talent_potential_assessments
                WHERE company_code=%s AND employee_key=%s
                """,
                (COMPANY, EMP),
            )
            hist = dict(cur.fetchone())
            check("potential history retained", int(hist["n"]) >= 2 and int(hist["w"]) >= 1, hist)

            emp_pot = c5.get_potential_for_viewer(
                cur, company_code=COMPANY, employee_key=EMP, viewer_role="employee"
            )
            check("potential hidden from employee", emp_pot.get("ok") is not True, emp_pot)
            hr_pot = c5.get_potential_for_viewer(
                cur, company_code=COMPANY, employee_key=EMP, viewer_role="hr",
                has_sensitive_permission=True,
            )
            check("hr sees potential history", hr_pot.get("ok") is True and len(hr_pot.get("assessments") or []) >= 2)

            # Performance evidence consume still blocked while consume=false
            blocked_link = c5.link_performance_evidence(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                performance_subject_type="calibrated_result", performance_subject_id=str(uuid.uuid4()),
                reason="should fail",
            )
            check("perf link blocked when consume off", blocked_link.get("error") == "performance_evidence_consume_disabled")

            # Enable optional Performance evidence (still optional — Talent works either way)
            c5.enable_company_talent_profile(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable optional perf consume",
                performance_evidence_consume=True,
            )
            link = c5.link_performance_evidence(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                performance_subject_type="calibrated_result",
                performance_subject_id=str(uuid.uuid4()),
                reason="optional performance evidence",
            )
            check("optional perf evidence", link.get("ok") is True and link.get("becomes_potential") is False, link)

            pot_with_perf = c5.submit_potential_assessment(
                cur, company_code=COMPANY, actor_phone=MGR_PHONE, employee_key=EMP,
                framework_id=framework_id,
                rationale="Manager assessment; performance linked only as optional evidence",
                dimension_scores={"learning_agility": "expanding", "scope_expansion": "expanding"},
                resulting_level="expanding", assessor_role="manager",
                performance_evidence_optional={"calibrated_result_id": "demo", "note": "optional"},
                has_sensitive_permission=True,
                reason="potential with optional perf evidence",
            )
            check("potential with optional perf", pot_with_perf.get("ok") is True, pot_with_perf)
            check("still not equals potential", pot_with_perf.get("performance_equals_potential") is False)
            pe = pot_with_perf["assessment"].get("performance_evidence_optional")
            if isinstance(pe, str):
                import json as _json
                pe = _json.loads(pe)
            check("perf evidence marked not potential", pe and pe.get("performance_equals_potential") is False, pe)

            # Readiness primitive — no succession
            ready = c5.add_readiness_observation(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                title_en="Ready for broader scope generally",
                source="hr_assessed", scope="general",
            )
            check("readiness primitive", ready.get("ok") is True and ready.get("successor_nominated") is False)

            # Mobility preference employee-declared
            mob = c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=EMP_PHONE, employee_key=EMP,
                dimension_kind="mobility_preference",
                title_en="Open to GCC relocation",
                source="employee_declared", visibility="employee_visible",
            )
            check("mobility preference", mob.get("ok") is True)

            # Temporal as-of
            asof = c5.talent_as_of(
                cur, company_code=COMPANY, employee_key=EMP,
                as_of=datetime.utcnow() + timedelta(seconds=1),
            )
            check("as-of query", asof.get("ok") is True and asof.get("master_talent_score") is None)
            check("as-of has facts", len(asof.get("dimension_facts") or []) >= 2)
            check("as-of why trackable", asof.get("why_trackable_via_source_and_version") is True)

            # Historical dimension versions survive edits
            asp2 = c5.update_employee_aspiration(
                cur, company_code=COMPANY, employee_phone=EMP_PHONE, employee_key=EMP,
                title_en="Staff engineer then principal",
            )
            check("aspiration versioned update", asp2.get("ok") is True)
            hist_asp = c5.list_dimension_facts(
                cur, company_code=COMPANY, employee_key=EMP,
                dimension_kind="career_aspiration", include_history=True, viewer_role="hr",
            )
            emp_versions = [
                f for f in (hist_asp.get("facts") or []) if f.get("source") == "employee_declared"
            ]
            check("aspiration history survives", len(emp_versions) >= 2, len(emp_versions))

            # Recruiting isolation
            iso = c5.prove_recruiting_talent_pool_isolated(cur)
            check("recruiting pool isolated", iso.get("isolated") is True and iso.get("c5_writes_to_recruiting_talent_pool") is False)

            # Cross-tenant
            xt = c5.ensure_talent_profile(cur, company_code=OTHER, employee_key=EMP, actor_phone=HR)
            check("cross-tenant denied", xt.get("ok") is not True, xt)

            # Disable preserves Talent history; Performance untouched
            dis = c5.disable_company_talent_profile(
                cur, company_code=COMPANY, actor_phone=HR, reason="module off"
            )
            check("disable preserves history", dis.get("preserves_history") is True, dis)
            check("perf history untouched flag", dis.get("performance_history_untouched") is True)
            cur.execute(
                "SELECT count(*) AS n FROM talent_dimension_facts WHERE company_code=%s", (COMPANY,)
            )
            check("facts remain after disable", int(dict(cur.fetchone())["n"]) >= 4)
            cur.execute(
                "SELECT count(*) AS n FROM talent_potential_assessments WHERE company_code=%s", (COMPANY,)
            )
            check("potential remains after disable", int(dict(cur.fetchone())["n"]) >= 2)
            blocked = c5.claim_skill(
                cur, company_code=COMPANY, actor_phone=EMP_PHONE, employee_key=EMP,
                skill_code="go", name_en="Go",
            )
            check("module-off blocks writes", blocked.get("ok") is not True, blocked)

            # Re-enable briefly to prove Talent still independent of Performance flags (still off)
            c5.enable_company_talent_profile(
                cur, company_code=COMPANY, actor_phone=HR, reason="re-enable",
                performance_evidence_consume=False,
            )
            check(
                "talent functional perf flags off",
                os.environ.get("WATHEFNI_PERFORMANCE_CALIBRATION_C4", "off") == "off"
                and c5.runtime_gate_for_company(COMPANY).get("ok") is True,
            )
            again = c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                dimension_kind="observation", title_en="Post re-enable note",
                source="hr_assessed", visibility="hr_confidential",
            )
            check("write after re-enable", again.get("ok") is True, again)

            conn.commit()
    finally:
        try:
            _db.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print(f"    {c5.PASS_STAMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
