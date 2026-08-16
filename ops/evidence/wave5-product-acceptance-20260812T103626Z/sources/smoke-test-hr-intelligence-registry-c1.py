#!/usr/bin/env python3
"""Wave 5 C1 — KPI Registry + fact/query spine prove."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"HI1{_N:05d}"[:12].upper()
OTHER = f"HIX{_N:05d}"[:12].upper()
HR = f"9656700{_N:05d}"


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
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = on
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = companies
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"


def main() -> int:
    print("    hr intelligence registry c1 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_registry_c1 as c1

    check("c1 module", c1.PHASE == "hr_intelligence_registry_c1")
    check("stamp", c1.PASS_STAMP == "HR_INTELLIGENCE_REGISTRY_FULL_PASS")
    check("commercial analytics", c1.COMMERCIAL_MODULE_KEY == "analytics")
    check("internal namespace", c1.INTERNAL_NAMESPACE == "hr_intelligence")
    h = c1.honesty_payload()
    check("registry authority", h.get("registry_is_authority") is True)
    check("no duplicate commercial", h.get("no_duplicate_commercial_module") is True)
    check("assistant out", h.get("assistant_mutations") is False)
    check("no universal score", h.get("no_universal_employee_score") is True)
    check("min cohort 5", h.get("min_cohort_n_default") == 5)
    check("cohort upward only", h.get("min_cohort_n_upward_only") is True)
    check("fte blocked honesty", h.get("fte_blocked_until_authoritative_inputs") is True)
    check("pending_start out", h.get("pending_start_excluded_from_headcount") is True)
    check("EN published", c1.status_label("published", lang="en") == "Published")
    check("AR published", bool(c1.status_label("published", lang="ar")))
    check("rollback", "WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1=off" in str(c1.rollback_guidance()))
    hp = c1.HEADCOUNT_POLICY
    check("notice in until LWD", hp.get("notice_period_in_headcount_until_effective_lwd_or_end") is True)
    check("leave in", hp.get("active_on_leave_or_suspension_in_headcount") is True)
    check("contingent not mixed", hp.get("contingent_mixed_into_employee_headcount") is False)
    check("fte not publishable", hp.get("fte_publishable") is False)

    _flags(on="off", companies="")
    check("global off", c1.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist", "allowlist" in str(c1.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary ok", c1.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c1.runtime_gate_for_company(OTHER).get("ok") is not True)

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
            c1.ensure_hr_intelligence_registry_c1_schema(cur)
            for code, name in ((COMPANY, f"HI1 {COMPANY}"), (OTHER, f"HIX {OTHER}")):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, name),
                )

            bad_floor = c1.enable_company_hr_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="too low", min_cohort_n=3
            )
            check("min_cohort floor 5", bad_floor.get("error") == "min_cohort_n_below_floor", bad_floor)

            en = c1.enable_company_hr_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable c1", min_cohort_n=5
            )
            check("enable company", en.get("ok") is True, en)
            check("demographics default off", en["settings"].get("nationality_dimension_enabled") is False)

            same = c1.set_min_cohort_n(
                cur, company_code=COMPANY, actor_phone=HR, min_cohort_n=5, reason="same"
            )
            check("raise to same ok", same.get("ok") is True, same)

            seed = c1.seed_platform_spine_definitions(cur, actor_phone=HR)
            check("seed defs", seed.get("ok") is True, seed)
            cur.execute("SELECT status FROM hr_kpi_definitions WHERE semantic_key=%s", (c1.FTE_KEY,))
            check("fte blocked status", dict(cur.fetchone())["status"] == "blocked")
            fte_pub = c1.publish_kpi_for_company(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.FTE_KEY, reason="try fte"
            )
            check("fte not company-publishable", fte_pub.get("ok") is not True, fte_pub)

            forbid = c1.create_kpi_definition(
                cur,
                actor_phone=HR,
                semantic_key="employee_score",
                name_en="Bad",
                name_ar="سيء",
                description_en="x",
                description_ar="س",
                business_meaning="x",
                formula_contract={"kind": "count_facts", "fact_type": "x"},
                unit="score",
                time_semantics="event_count",
                permission_class="intelligence_spine",
                reason="forbid",
            )
            check("universal score rejected", forbid.get("error") == "universal_score_forbidden", forbid)

            # Publish spine KPIs to company
            for key in (c1.SPINE_FACT_COUNT_KEY, c1.SPINE_RATE_KEY):
                pub = c1.publish_kpi_for_company(
                    cur, company_code=COMPANY, actor_phone=HR, semantic_key=key, reason="publish spine"
                )
                check(f"publish {key}", pub.get("ok") is True, pub)

            # Versioning preserves history (ephemeral key so re-runs are not polluted by prior C1/C2 qualifies)
            ver_key = f"intelligence.spine.version_prove_{SUFFIX}"
            created_v1 = c1.create_kpi_definition(
                cur,
                actor_phone=HR,
                semantic_key=ver_key,
                name_en="Version prove",
                name_ar="إثبات الإصدار",
                description_en="Ephemeral C1 versioning prove metric.",
                description_ar="مؤشر إثبات إصدارات C1 المؤقت.",
                business_meaning="v1 meaning",
                formula_contract={
                    "kind": "count_facts",
                    "fact_type": "spine_demo_entity",
                    "require_facts": False,
                    "note": "v1",
                },
                unit="count",
                time_semantics="event_count",
                permission_class="intelligence_spine",
                status="published",
                reason="create v1 for version prove",
            )
            check("version prove v1", created_v1.get("ok") is True, created_v1)
            if created_v1.get("ok"):
                c1.publish_kpi_definition(
                    cur,
                    actor_phone=HR,
                    kpi_definition_id=str(created_v1["definition"]["kpi_definition_id"]),
                    reason="publish v1 prove",
                )
            ver = c1.version_kpi_definition(
                cur,
                actor_phone=HR,
                semantic_key=ver_key,
                reason="change formula wording",
                updates={
                    "business_meaning": "Updated meaning v2",
                    "status": "published",
                    "formula_contract": {
                        "kind": "count_facts",
                        "fact_type": "spine_demo_entity",
                        "require_facts": False,
                        "note": "v2",
                    },
                },
            )
            check("versioned definition", ver.get("ok") is True and ver.get("prior_preserved") is True, ver)
            check("prior version 1", ver.get("prior_version") == 1, ver)
            # Re-publish latest spine fact_count to company (evaluation path) + prove key
            pub2 = c1.publish_kpi_for_company(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                semantic_key=c1.SPINE_FACT_COUNT_KEY,
                reason="publish spine after version prove",
            )
            check("company on published spine", pub2.get("ok") is True and int(pub2["publication"]["effective_version"]) >= 1)
            if ver.get("ok"):
                pub_prove = c1.publish_kpi_for_company(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    semantic_key=ver_key,
                    reason="publish v2 prove",
                )
                check(
                    "company on v2",
                    pub_prove.get("ok") is True and int(pub_prove["publication"]["effective_version"]) >= 2,
                    pub_prove,
                )

            # Facts + evaluation
            for i in range(3):
                ing = c1.ingest_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    fact_type="spine_demo_entity",
                    entity_type="demo",
                    entity_id=f"E{i}",
                    source_authority="c1_smoke",
                    measures={"n": 1},
                    reason="ingest",
                )
                check(f"ingest {i}", ing.get("ok") is True, ing)

            ev = c1.evaluate_kpi(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                semantic_key=c1.SPINE_FACT_COUNT_KEY,
            )
            check("evaluate count", ev.get("status") == "ok" and float(ev["value"]) == 3.0, ev)
            check("drill population", ev.get("population_count") == 3 and "E0" in ev.get("population_ids", []))
            check("pins definition version", int(ev.get("effective_version") or 0) >= 1)
            ev_pin = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=ver_key
            )
            check(
                "pins versioned definition",
                ev_pin.get("status") == "ok" and int(ev_pin.get("effective_version") or 0) >= 2,
                ev_pin,
            )
            check("same export authority", ev.get("same_authority_as_export") is True)

            # Correction path
            prior_id = None
            cur.execute(
                "SELECT fact_id FROM hr_intelligence_facts WHERE company_code=%s AND entity_id='E0' AND superseded_by IS NULL",
                (COMPANY,),
            )
            prior_id = str(dict(cur.fetchone())["fact_id"])
            corr = c1.correct_fact(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                prior_fact_id=prior_id,
                measures={"n": 2},
                reason="correct",
            )
            check("correction", corr.get("ok") is True and corr.get("domain_audit_rewritten") is False, corr)
            ev2 = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.SPINE_FACT_COUNT_KEY
            )
            check("count after correction still 3", float(ev2["value"]) == 3.0, ev2)

            # Zero denominator → not_applicable (not silent 0%)
            rate0 = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.SPINE_RATE_KEY
            )
            check("zero denom not_applicable", rate0.get("status") == "not_applicable" and rate0.get("value") is None, rate0)

            # Add dens but below cohort → suppressed
            for i in range(3):
                c1.ingest_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    fact_type="spine_demo_den",
                    entity_type="demo",
                    entity_id=f"D{i}",
                    source_authority="c1_smoke",
                    reason="den",
                )
                c1.ingest_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    fact_type="spine_demo_num",
                    entity_type="demo",
                    entity_id=f"N{i}",
                    source_authority="c1_smoke",
                    reason="num",
                )
            rate_s = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.SPINE_RATE_KEY
            )
            check("small cohort suppressed", rate_s.get("status") == "suppressed" and rate_s.get("value") is None, rate_s)

            for i in range(3, 5):
                c1.ingest_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    fact_type="spine_demo_den",
                    entity_type="demo",
                    entity_id=f"D{i}",
                    source_authority="c1_smoke",
                    reason="den",
                )
                c1.ingest_fact(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    fact_type="spine_demo_num",
                    entity_type="demo",
                    entity_id=f"N{i}",
                    source_authority="c1_smoke",
                    reason="num",
                )
            rate_ok = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.SPINE_RATE_KEY
            )
            check("rate ok at cohort 5", rate_ok.get("status") == "ok" and float(rate_ok["value"]) == 100.0, rate_ok)

            # Cohort upward-only (after suppression prove at floor 5)
            up = c1.set_min_cohort_n(
                cur, company_code=COMPANY, actor_phone=HR, min_cohort_n=8, reason="up"
            )
            check("upward cohort ok", up.get("ok") is True and int(up["settings"]["min_cohort_n"]) == 8, up)
            lower = c1.set_min_cohort_n(
                cur, company_code=COMPANY, actor_phone=HR, min_cohort_n=6, reason="down"
            )
            check("downward cohort forbidden", lower.get("error") == "min_cohort_n_downward_forbidden", lower)

            # Unpublished headcount unavailable
            hc = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.HEADCOUNT_KEY
            )
            check("headcount unpublished unavailable", hc.get("error") == "kpi_not_published_for_company", hc)

            # Historical eval pins version — prior evaluation rows remain
            cur.execute(
                "SELECT count(*) AS n, min(effective_version) AS vmin FROM hr_kpi_evaluations WHERE company_code=%s AND semantic_key=%s",
                (COMPANY, c1.SPINE_FACT_COUNT_KEY),
            )
            hist = dict(cur.fetchone())
            check("evaluation history retained", int(hist["n"]) >= 2)

            # Assistant refuse invent
            asst = c1.assistant_resolve_metric(cur, company_code=COMPANY, semantic_key="made_up.magic_kpi")
            check("assistant refuses invent", asst.get("error") == "metric_not_in_registry" and asst.get("invented") is False, asst)
            asst2 = c1.assistant_resolve_metric(cur, company_code=COMPANY, semantic_key="employee_score")
            check("assistant refuses universal score", asst2.get("error") == "universal_score_forbidden", asst2)
            asst3 = c1.assistant_resolve_metric(cur, company_code=COMPANY, semantic_key=c1.SPINE_FACT_COUNT_KEY)
            check("assistant resolves published", asst3.get("ok") is True and asst3.get("invented") is False, asst3)

            # Cross-tenant
            other_en = c1.enable_company_hr_intelligence(
                cur, company_code=OTHER, actor_phone=HR, reason="other"
            )
            check("other company gate denied without allowlist", other_en.get("ok") is not True)

            # Module off preserves history
            c1.disable_company_hr_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="off")
            cur.execute("SELECT count(*) AS n FROM hr_kpi_evaluations WHERE company_code=%s", (COMPANY,))
            check("evals survive disable", int(dict(cur.fetchone())["n"]) >= 1)
            cur.execute("SELECT count(*) AS n FROM hr_kpi_definitions WHERE semantic_key=%s", (c1.SPINE_FACT_COUNT_KEY,))
            check("definitions survive", int(dict(cur.fetchone())["n"]) >= 2)
            blocked = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.SPINE_FACT_COUNT_KEY
            )
            check("writes blocked when disabled", blocked.get("ok") is not True, blocked)

            _flags(on="off", companies="")
            check("global off after prove", c1.runtime_gate_for_company(COMPANY).get("ok") is not True)

            conn.commit()
    finally:
        try:
            _db.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("HR_INTELLIGENCE_REGISTRY_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
