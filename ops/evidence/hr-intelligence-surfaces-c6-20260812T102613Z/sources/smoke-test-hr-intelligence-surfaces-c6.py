#!/usr/bin/env python3
"""Wave 5 C6 HR Intelligence surfaces qualification prove."""
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
COMPANY = f"HI6{_N:05d}"[:12].upper()
OTHER = f"HZ6{_N:05d}"[:12].upper()
HR = f"9656760{_N:05d}"
EMP_A = f"{COMPANY}-A"
EMP_B = f"{COMPANY}-B"
SENSITIVE_KEY = f"intelligence.c6.sensitive_{SUFFIX}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def _flags(*, c1="on", c2="on", c6="on", companies="") -> None:
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = c1
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2"] = c2
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_C6"] = c6
    os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_COMPANIES"] = companies


def main() -> int:
    print("    hr intelligence surfaces c6 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_surfaces_c6 as c6
    import hr_intelligence_workforce_c2 as c2

    check("phase", c6.PHASE == "hr_intelligence_surfaces_c6")
    check("stamp", c6.PASS_STAMP == "HR_INTELLIGENCE_SURFACES_FULL_PASS")
    check("commercial analytics", c6.COMMERCIAL_MODULE_KEY == "analytics")
    check("family order", c6.FAMILY_ORDER[0] == "workforce" and c6.FAMILY_ORDER[-1] == "hr_ops")
    check("family mapping", c6.family_for_semantic_key(c2.HEADCOUNT_KEY) == "workforce")
    honesty = c6.honesty_payload()
    check("c1 evaluator only", honesty["uses_c1_evaluator_only"] is True)
    check("no frontend formulas", honesty["no_frontend_formulas"] is True)
    check("attention separate", honesty["attention_is_not_intelligence"] is True)
    check("scheduled delivery debt", honesty["scheduled_delivery_safe_debt"] is True)
    check("no employee company intelligence", honesty["employee_app_no_company_intelligence"] is True)
    check("bilingual ok", c6.status_label("ok") and c6.status_label("ok", lang="ar"))
    check("bilingual states", all(c6.status_label(s, lang="ar") for s in ("unavailable", "insufficient_data", "not_applicable", "suppressed", "blocked", "stale", "refreshing")))

    _flags(c6="off", companies=COMPANY)
    check("gate off", c6.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist", c6.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies=COMPANY)
    check("gate on", c6.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", c6.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(c6.__file__).read_text(encoding="utf-8")
    check("surface calls c1 evaluator", "c1.evaluate_kpi(" in source)
    check("no turnover formula", "turnover =" not in source and "/ headcount" not in source)
    check("no fact math query", "FROM hr_intelligence_facts" not in source)

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
            c6.ensure_schema(cur)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"C6 {code}"),
                )

            denied = c6.enable_company(
                cur, company_code=COMPANY, actor_phone=HR, reason="must require c1"
            )
            check("requires c1 entitlement", denied.get("ok") is not True, denied)

            c1_enabled = c1.enable_company_hr_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="c6 prove"
            )
            check("enable c1", c1_enabled.get("ok") is True, c1_enabled)
            c2.seed_workforce_definitions(cur, actor_phone=HR)
            c2_enabled = c2.enable_company_workforce_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="c6 prove"
            )
            check("enable c2", c2_enabled.get("ok") is True, c2_enabled)
            pubs = c2.publish_workforce_kpis_for_company(
                cur, company_code=COMPANY, actor_phone=HR, reason="c6 prove"
            )
            check("publish workforce", pubs.get("ok") is True, pubs)
            c6_enabled = c6.enable_company(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="c6 prove",
                manager_analytics_enabled=True,
            )
            check("enable c6", c6_enabled.get("ok") is True, c6_enabled)

            for employee, period, department in (
                (EMP_A, "A1", "Ops"),
                (EMP_B, "B1", "Finance"),
            ):
                seeded = c2.upsert_employment_period(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    employee_key=employee,
                    employment_period_key=period,
                    status="active",
                    effective_start=today - timedelta(days=100),
                    hire_event_date=today - timedelta(days=100),
                    department=department,
                    reason="c6 seed",
                )
                check(f"seed {period}", seeded.get("ok") is True, seeded)

            listed = c6.list_published_kpis(cur, COMPANY, HR)
            check("list published", listed.get("ok") is True and listed.get("count", 0) >= 1, listed)
            check("headcount published", c2.HEADCOUNT_KEY in {m["semantic_key"] for m in listed["kpis"]})

            window = {"as_of": today.isoformat()}
            overview = c6.compose_overview(cur, COMPANY, HR, window, {}, "en")
            overview_keys = {
                item["semantic_key"]
                for family in overview.get("families") or []
                for item in family.get("metrics") or []
            }
            check("overview includes headcount", c2.HEADCOUNT_KEY in overview_keys, overview)
            headcount = c6.evaluate_metric(
                cur, company=COMPANY, actor=HR, semantic_key=c2.HEADCOUNT_KEY, time_window=window
            )
            check("headcount genuine value", headcount.get("status") == "ok" and float(headcount["value"]) == 2.0, headcount)

            unpublished = c6.evaluate_metric(
                cur, company=COMPANY, actor=HR, semantic_key="workforce.not_published"
            )
            check("unpublished unavailable", unpublished.get("status") == "unavailable", unpublished)

            zero_hires = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HIRES_KEY,
                time_window={
                    "period_start": (today + timedelta(days=30)).isoformat(),
                    "period_end": (today + timedelta(days=60)).isoformat(),
                },
            )
            check("genuine zero stays zero", zero_hires.get("status") == "ok" and float(zero_hires["value"]) == 0.0, zero_hires)

            c2.disable_company_workforce_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="module off prove"
            )
            module_off = c6.compose_overview(cur, COMPANY, HR, window, {}, "en")
            module_off_keys = {
                item["semantic_key"]
                for family in module_off.get("families") or []
                for item in family.get("metrics") or []
            }
            check("module-off omitted", c2.HEADCOUNT_KEY not in module_off_keys, module_off)
            c2.enable_company_workforce_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="continue prove"
            )

            about = c6.about_metric(cur, c2.HEADCOUNT_KEY, COMPANY)
            check("about version", about.get("ok") is True and about["about_metric"].get("effective_version"), about)
            check("about bilingual", bool(about["about_metric"].get("name_en")) and bool(about["about_metric"].get("name_ar")))

            trend = c6.trend_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window={
                    "period_start": (today - timedelta(days=90)).isoformat(),
                    "period_end": today.isoformat(),
                },
                bucket="monthly",
            )
            check("monthly trend", trend.get("ok") is True and len(trend.get("series") or []) >= 2, trend)
            bad_bucket = c6.trend_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.RETENTION_KEY,
                bucket="daily",
            )
            check("cohort daily rejected", bad_bucket.get("error") == "trend_bucket_not_allowed", bad_bucket)

            bad_dimension = c6.segment_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                dimension="favorite_color",
                dimension_value="blue",
            )
            check("invalid dimension rejected", bad_dimension.get("error") == "dimension_not_supported", bad_dimension)

            definition = c1.create_kpi_definition(
                cur,
                actor_phone=HR,
                semantic_key=SENSITIVE_KEY,
                name_en="C6 suppression prove",
                name_ar="إثبات الحجب",
                description_en="Synthetic qualification metric.",
                description_ar="مؤشر تأهيل اصطناعي.",
                business_meaning="Suppression contract only.",
                formula_contract={"kind": "count_facts", "fact_type": f"c6_sensitive_{SUFFIX}"},
                unit="count",
                time_semantics="event_count",
                permission_class="workforce_sensitive_demo",
                status="published",
                reason="c6 suppression prove",
            )
            check("sensitive definition", definition.get("ok") is True, definition)
            c1.publish_kpi_for_company(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                semantic_key=SENSITIVE_KEY,
                reason="c6 suppression prove",
            )
            c1.ingest_fact(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                fact_type=f"c6_sensitive_{SUFFIX}",
                entity_type="employee",
                entity_id=EMP_A,
                source_authority="c6_smoke",
                is_synthetic=True,
                reason="c6 suppression prove",
            )
            suppressed = c6.evaluate_metric(
                cur, company=COMPANY, actor=HR, semantic_key=SENSITIVE_KEY
            )
            check("suppressed has no value", suppressed.get("status") == "suppressed" and suppressed.get("value") is None, suppressed)
            check("suppressed has no population", suppressed.get("population_ids") == [] and suppressed.get("population_count") is None, suppressed)

            comparison = c6.compare_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=SENSITIVE_KEY,
                current_time_window={"period_start": (today - timedelta(days=5)).isoformat(), "period_end": today.isoformat()},
            )
            check("compare suppressed fail closed", comparison.get("comparable") is False, comparison)

            drill = c6.drill_population(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window=window,
            )
            check("drill reauthorized", drill.get("reauthorized") is True, drill)
            check("drill aggregate match", drill.get("total") == int(headcount["value"]), drill)
            suppressed_drill = c6.drill_population(
                cur, company=COMPANY, actor=HR, semantic_key=SENSITIVE_KEY
            )
            check("suppressed drill empty", suppressed_drill.get("rows") == [] and suppressed_drill.get("total") is None, suppressed_drill)

            manager = c6.evaluate_metric(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window=window,
                filters={"manager_scope_employee_keys": [EMP_A]},
                actor_role="manager",
            )
            check("manager scope", manager.get("status") == "ok" and float(manager["value"]) == 1.0, manager)

            live = c6.create_saved_view(
                cur,
                company=COMPANY,
                owner_phone=HR,
                name_en=f"Live {SUFFIX}",
                mode="live",
                query_config={"semantic_key": c2.HEADCOUNT_KEY, "time_window": window},
            )
            check("save live", live.get("ok") is True, live)
            opened = c6.get_saved_view(
                cur,
                company=COMPANY,
                owner_phone=HR,
                view_id=live["saved_view"]["view_id"],
            )
            check("live re-evaluates", opened.get("saved_view", {}).get("opened_by_re_evaluation") is True, opened)
            pinned = c6.create_saved_view(
                cur,
                company=COMPANY,
                owner_phone=HR,
                name_en=f"Pinned {SUFFIX}",
                mode="pinned",
                query_config={"semantic_key": c2.HEADCOUNT_KEY, "time_window": window},
            )
            pinned_versions = pinned.get("saved_view", {}).get("pinned_definition_versions") or {}
            check("pinned stores version", bool(pinned_versions.get(c2.HEADCOUNT_KEY)), pinned)
            check("pinned snapshot honest", pinned["saved_view"]["query_config"]["_pinned_snapshot"]["is_snapshot"] is True)

            exported = c6.create_export_csv(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=c2.HEADCOUNT_KEY,
                time_window=window,
            )
            check("aggregate export", exported.get("ok") is True and exported["export"]["row_count"] == 1, exported)
            export_detail = c6.get_export(
                cur,
                company=COMPANY,
                actor=HR,
                export_id=exported["export"]["export_id"],
                include_csv=True,
            )
            csv_text = export_detail.get("export", {}).get("csv_text") or ""
            check("export equals evaluation", str(headcount["value"]) in csv_text, csv_text)
            check("export metadata", "# semantic_key:" in csv_text and "# effective_version:" in csv_text, csv_text)

            suppressed_export = c6.create_export_csv(
                cur,
                company=COMPANY,
                actor=HR,
                semantic_key=SENSITIVE_KEY,
                person_level=True,
                has_export_person_permission=True,
            )
            check("suppressed export no people", suppressed_export.get("ok") is True and suppressed_export["export"]["row_count"] == 0, suppressed_export)

            invented = c6.assistant_query_metric(
                cur, company=COMPANY, actor=HR, semantic_key=f"invented.{SUFFIX}"
            )
            check("assistant refuses invented", invented.get("ok") is not True and invented.get("invented") is False, invented)

            c6.disable_company(
                cur, company_code=COMPANY, actor_phone=HR, reason="end prove"
            )
            disabled = c6.list_published_kpis(cur, COMPANY, HR)
            check("company disable fail closed", disabled.get("ok") is not True, disabled)
            conn.commit()
    finally:
        try:
            db_context.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("HR_INTELLIGENCE_SURFACES_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

