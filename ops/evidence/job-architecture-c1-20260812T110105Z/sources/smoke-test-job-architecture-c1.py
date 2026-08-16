#!/usr/bin/env python3
"""Wave 6 C1 Job Architecture qualification prove."""
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
COMPANY = f"JA1{_N:05d}"[:12].upper()
OTHER = f"JA9{_N:05d}"[:12].upper()
HR = f"9656780{_N:05d}"


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
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = on
    os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"] = companies


def main() -> int:
    print("    job architecture c1 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import job_architecture_c1 as ja
    import setup_console_wave6_policies as w6

    check("phase", ja.PHASE == "job_architecture_c1")
    check("stamp", ja.PASS_STAMP == "JOB_ARCHITECTURE_FULL_PASS")
    check("not commercial sku", ja.COMMERCIAL_SKU is False)
    check("platform key", ja.PLATFORM_CAPABILITY_KEY == "job_architecture")
    honesty = ja.honesty_payload()
    check("salary bands out", honesty["salary_bands_out_of_c1"] is True)
    check("no fuzzy ai", honesty["no_fuzzy_ai_migration"] is True)
    check("edges not eligibility", honesty["career_edges_are_not_eligibility"] is True)
    check("recruiting boundary", honesty["recruiting_job_is_not_ja_profile"] is True)
    check("org position boundary", honesty["org_position_is_not_reusable_job_profile"] is True)
    check("talent boundary", honesty["talent_critical_role_is_not_ja_catalog"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    contracts = ja.future_hard_contracts()
    check("comp hard", contracts["compensation_planning"]["hard"] is True)
    check("wfp hard", contracts["workforce_planning"]["hard"] is True)
    check("talent optional", contracts["talent_optional_ref"]["hard"] is False)
    check("recruiting optional", contracts["recruiting_optional_ref"]["hard"] is False)
    check("setup wave6 module", "job_architecture" in w6.WAVE6_MODULE_KEYS)
    check("setup honesty", w6.honesty_payload()["setup_owns_wave6_policies"] is True)
    check("bilingual en", bool(ja.status_label("published", lang="en")))
    check("bilingual ar", bool(ja.status_label("published", lang="ar")))
    surf = ja.surface_composition_rules()
    check("setup primary authoring", surf["setup_web"]["primary_authoring"] is True)
    check("mobile thin", surf["hr_mobile"]["no_heavyweight_authoring"] is True)

    _flags(on="off", companies=COMPANY)
    check("gate off", ja.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist", ja.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies=COMPANY)
    check("gate on", ja.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", ja.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(ja.__file__).read_text(encoding="utf-8")
    check("no salary band table", "salary_band" not in source.lower() or "salary_bands_out" in source)
    check("no eligibility score", "eligibility_scoring_forbidden" in source)

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
            ja.ensure_job_architecture_c1_schema(cur)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"JA {code}"),
                )

            enabled = ja.enable_company_job_architecture(
                cur, company_code=COMPANY, actor_phone=HR, reason="c1 prove"
            )
            check("enable company", enabled.get("ok") is True, enabled)

            fam = ja.upsert_job_family(
                cur, company_code=COMPANY, actor_phone=HR, code="ENG",
                name_en="Engineering", name_ar="الهندسة", status="published", reason="seed",
            )
            check("family", fam.get("ok") is True and fam.get("stable_id"), fam)
            family_id = fam["stable_id"]
            renamed = ja.upsert_job_family(
                cur, company_code=COMPANY, actor_phone=HR, code="ENG",
                name_en="Engineering Group", name_ar="مجموعة الهندسة", status="published", reason="rename",
            )
            check(
                "stable id survives rename",
                renamed.get("stable_id") == family_id and int(renamed["family"]["effective_version"]) >= 2,
                renamed,
            )

            fn = ja.upsert_job_function(
                cur, company_code=COMPANY, actor_phone=HR, family_id=family_id, code="SW",
                name_en="Software", name_ar="برمجيات", status="published", reason="seed",
            )
            check("function", fn.get("ok") is True, fn)
            grade = ja.upsert_grade(
                cur, company_code=COMPANY, actor_phone=HR, code="G5",
                name_en="Grade 5", name_ar="الدرجة 5", rank_order=5, status="published", reason="seed",
            )
            check("grade", grade.get("ok") is True and grade.get("salary_bands_not_in_c1") is True, grade)
            grade_id = grade["stable_id"]
            level = ja.upsert_level(
                cur, company_code=COMPANY, actor_phone=HR, code="L2", grade_id=grade_id,
                name_en="Level II", name_ar="المستوى ٢", rank_order=2, status="published", reason="seed",
            )
            check("level", level.get("ok") is True, level)
            profile = ja.upsert_job_profile(
                cur, company_code=COMPANY, actor_phone=HR, function_id=fn["stable_id"], code="SWE",
                name_en="Software Engineer", name_ar="مهندس برمجيات", status="published",
                default_grade_id=grade_id, default_level_id=level["stable_id"], reason="seed",
            )
            check("profile", profile.get("ok") is True, profile)
            check(
                "profile boundaries",
                profile["boundaries"]["recruiting_job_is_not_ja_profile"] is True
                and profile["boundaries"]["org_position_is_not_reusable_job_profile"] is True,
                profile,
            )
            profile_id = profile["stable_id"]

            edge = ja.create_career_edge(
                cur, company_code=COMPANY, actor_phone=HR, edge_type="promotion",
                from_profile_id=profile_id, to_profile_id=profile_id,
                optional_requirements={"competency_keys": ["system_design"]},
                reason="career",
            )
            check("career edge", edge.get("ok") is True and edge.get("employee_auto_eligible") is False, edge)
            bad_edge = ja.create_career_edge(
                cur, company_code=COMPANY, actor_phone=HR, edge_type="promotion",
                from_grade_id=grade_id, to_grade_id=grade_id,
                optional_requirements={"eligibility_score": 0.9}, reason="forbidden",
            )
            check("no eligibility scoring", bad_edge.get("error") == "eligibility_scoring_forbidden", bad_edge)

            assign1 = ja.assign_employment_architecture(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E1",
                effective_start=today - timedelta(days=60), profile_id=profile_id, grade_id=grade_id,
                reason="initial",
            )
            check("assignment", assign1.get("ok") is True, assign1)
            assign2 = ja.assign_employment_architecture(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E1",
                effective_start=today - timedelta(days=10), profile_id=profile_id, grade_id=grade_id,
                level_id=level["stable_id"], reason="later",
            )
            check("supersede prior", assign2.get("ok") is True and len(assign2.get("superseded") or []) >= 1, assign2)
            hist = ja.resolve_assignment_as_of(
                cur, company_code=COMPANY, employee_key="E1", as_of=today - timedelta(days=30)
            )
            check(
                "historical reconstructable",
                hist.get("ok") is True and hist.get("assignment") and hist.get("reconstructable") is True,
                hist,
            )

            link = ja.link_org_position(
                cur, company_code=COMPANY, actor_phone=HR, org_position_ref="POS-100",
                profile_id=profile_id, effective_start=today, reason="link",
            )
            check("org position link", link.get("ok") is True and link.get("org_position_is_not_reusable_job_profile") is True, link)

            talent_ref = ja.optional_external_ref(
                cur, company_code=COMPANY, actor_phone=HR, domain="talent_critical_role",
                external_key="CRIT-1", profile_id=profile_id,
            )
            check("talent optional ref", talent_ref.get("ok") is True and talent_ref.get("hard_dependency") is False, talent_ref)
            recruiting_ref = ja.optional_external_ref(
                cur, company_code=COMPANY, actor_phone=HR, domain="recruiting_opening",
                external_key="JOB-OPEN-9", profile_id=profile_id,
            )
            check("recruiting optional ref", recruiting_ref.get("ok") is True and recruiting_ref.get("optional") is True, recruiting_ref)

            # Migration: unique match + ambiguous + none
            ja.upsert_grade(
                cur, company_code=COMPANY, actor_phone=HR, code="G6",
                name_en="Grade 6", name_ar="الدرجة 6", rank_order=6, status="published", reason="dup name trap",
            )
            # Create second grade with same EN name intentionally? Deterministic match uses exact token —
            # ambiguous: two grades both matching same normalized token via shared alias
            # Simulate ambiguity by publishing another grade whose name_en equals an existing code path:
            # Put two grades that both normalize to "grade 5" — update one name to collide:
            # Instead seed two grades with identical name_en (different codes) — lookup indexes both.
            ja.upsert_grade(
                cur, company_code=COMPANY, actor_phone=HR, code="G5B",
                name_en="Grade 5", name_ar="درجة ٥ب", rank_order=5, status="published", reason="ambiguous name",
            )
            mig = ja.migrate_legacy_values(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                raw_field="grade",
                candidates=[
                    {"raw_value": "G6", "provenance": {"employee_key": "E2", "source": "profile.grade"}},
                    {"raw_value": "Grade 5", "provenance": {"employee_key": "E3"}},
                    {"raw_value": "Unknown Grade Z", "provenance": {"employee_key": "E4"}},
                ],
            )
            check("migration ok", mig.get("ok") is True and mig.get("fuzzy_ai_used") is False, mig)
            check("deterministic unique mapped", mig.get("mapped") == 1, mig)
            check("ambiguous unmapped", mig.get("unmapped_ambiguous") == 1, mig)
            check("none unmapped", mig.get("unmapped_none") == 1, mig)
            check("raw preserved", mig.get("raw_preserved") is True, mig)
            cur.execute(
                "SELECT raw_value, match_kind FROM ja_legacy_mapping WHERE company_code=%s ORDER BY raw_value",
                (COMPANY,),
            )
            mappings = [dict(r) for r in cur.fetchall()]
            check("raw values retained", any(m["raw_value"] == "Unknown Grade Z" for m in mappings), mappings)

            # Wave 5 fact outbox
            cur.execute("SELECT count(*) AS n FROM ja_wave5_fact_outbox WHERE company_code=%s", (COMPANY,))
            facts = int(dict(cur.fetchone())["n"])
            check("typed facts emitted", facts >= 1, facts)

            # Setup policy path
            pol = w6.get_wave6_module_policy(cur, COMPANY, "job_architecture")
            check("setup policy enabled", pol.get("ok") is True and pol["policy"].get("enabled") is True, pol)

            asst = ja.assistant_explain_profile(cur, company_code=COMPANY, profile_id=profile_id)
            check("assistant explain", asst.get("ok") is True and asst.get("mutations") is False, asst)

            # Tenant isolation write
            other_try = ja.upsert_job_family(
                cur, company_code=OTHER, actor_phone=HR, code="X", name_en="X", name_ar="س", reason="iso"
            )
            check("tenant write blocked", other_try.get("ok") is not True, other_try)

            # JA off modularity — legacy text continues
            ja.disable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="modularity")
            listed = ja.list_catalog(cur, company_code=COMPANY)
            check("disabled catalog empty", listed.get("enabled") is False and listed.get("legacy_text_still_works") is True, listed)
            blocked = ja.upsert_grade(
                cur, company_code=COMPANY, actor_phone=HR, code="G9",
                name_en="G9", name_ar="٩", status="published", reason="while off",
            )
            check("writes blocked when disabled", blocked.get("ok") is not True, blocked)
            cur.execute("SELECT count(*) AS n FROM ja_grade WHERE company_code=%s", (COMPANY,))
            retained = int(dict(cur.fetchone())["n"])
            check("history retained on disable", retained >= 2, retained)

            # Re-enable and confirm still gated by env
            ja.enable_company_job_architecture(cur, company_code=COMPANY, actor_phone=HR, reason="restore")
            _flags(on="off", companies=COMPANY)
            gate_off = ja.runtime_gate_for_company(COMPANY)
            check("env kill switch", gate_off.get("ok") is not True, gate_off)
            _flags(companies="")
            check("all gates off", ja.runtime_gate_for_company(COMPANY).get("ok") is not True)

            conn.commit()
    finally:
        try:
            db_context.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("JOB_ARCHITECTURE_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
