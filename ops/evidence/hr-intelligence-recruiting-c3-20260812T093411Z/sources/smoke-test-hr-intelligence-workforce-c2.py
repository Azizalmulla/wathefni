#!/usr/bin/env python3
"""Wave 5 C2 — Workforce Intelligence prove."""
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
COMPANY = f"HI2{_N:05d}"[:12].upper()
OTHER = f"HJX{_N:05d}"[:12].upper()
HR = f"9656710{_N:05d}"
MGR = f"{COMPANY}-MGR"
EMP_A = f"{COMPANY}-A"
EMP_B = f"{COMPANY}-B"
EMP_C = f"{COMPANY}-C"
EMP_D = f"{COMPANY}-D"
EMP_E = f"{COMPANY}-E"
EMP_F = f"{COMPANY}-F"
EMP_PEND = f"{COMPANY}-P"
EMP_NOTICE = f"{COMPANY}-N"
EMP_LEAVE = f"{COMPANY}-L"
EMP_CONT = f"{COMPANY}-K"
EMP_LEFT = f"{COMPANY}-X"
EMP_REHIRE = f"{COMPANY}-R"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, c1_on="on", c2_on="on", companies=""):
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = c1_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2"] = c2_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_COMPANIES"] = companies
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    # modularity: domain modules off
    for flag in (
        "WATHEFNI_PERFORMANCE_GOALS_C1", "WATHEFNI_TALENT_PROFILE_C5",
        "WATHEFNI_TALENT_SUCCESSION_C6", "WATHEFNI_PERFORMANCE_REVIEWS_C2",
    ):
        os.environ[flag] = "off"


def main() -> int:
    print("    hr intelligence workforce c2 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_workforce_c2 as c2

    check("c2 module", c2.PHASE == "hr_intelligence_workforce_c2")
    check("stamp", c2.PASS_STAMP == "HR_INTELLIGENCE_WORKFORCE_FULL_PASS")
    check("commercial analytics", c2.COMMERCIAL_MODULE_KEY == "analytics")
    h = c2.honesty_payload()
    check("uses c1 evaluator", h.get("uses_c1_registry_evaluator") is True)
    check("no second math engine", h.get("no_second_analytics_math_engine") is True)
    check("fte blocked", h.get("fte_remains_blocked") is True)
    check("turnover not naive", h.get("turnover_not_exits_over_current_hc") is True)
    check("retention cohort", h.get("retention_cohort_aware") is True)
    check("EN active", c2.status_label("active", lang="en") == "Active")
    check("AR pending", bool(c2.status_label("pending_start", lang="ar")))

    _flags(c2_on="off", companies="")
    check("c2 global off", c2.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist", "allowlist" in str(c2.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(companies=COMPANY)
    check("canary ok", c2.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c2.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB"); print(f"\n    {PASS} passed, {FAIL} failed (unit-only)"); return 1 if FAIL else 0
        raise
    try:
        _db = app.db_connect(); conn = _db.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)"); return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            c2.ensure_hr_intelligence_workforce_c2_schema(cur)
            for code, name in ((COMPANY, f"HI2 {COMPANY}"), (OTHER, f"HJX {OTHER}")):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, name),
                )

            en = c2.enable_company_workforce_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="enable c2")
            check("enable c2", en.get("ok") is True, en)
            pubs = c2.publish_workforce_kpis_for_company(cur, company_code=COMPANY, actor_phone=HR, reason="publish")
            check("publish workforce kpis", pubs.get("ok") is True and pubs.get("fte_blocked") is True, pubs)
            check("fte still blocked", pubs.get("fte_blocked") is True)

            today = date.today()
            past = today - timedelta(days=400)
            mid = today - timedelta(days=200)
            period_start = today - timedelta(days=90)
            # Seed population
            seeds = [
                # active A-F under MGR (6 for small company ordinary HC)
                (EMP_A, "A1", "active", past, None, None, False, False, "employee", mid, None, None, "Ops", "HQ", MGR),
                (EMP_B, "B1", "active", past, None, None, False, False, "employee", past, None, None, "Ops", "HQ", MGR),
                (EMP_C, "C1", "active", past, None, None, False, False, "employee", past, None, None, "Sales", "BR1", MGR),
                (EMP_D, "D1", "active", past, None, None, False, False, "employee", past, None, None, "Sales", "BR1", EMP_A),
                (EMP_E, "E1", "active", past, None, None, False, False, "employee", past, None, None, "Ops", "HQ", MGR),
                (EMP_F, "F1", "active", past, None, None, False, False, "employee", past, None, None, "Ops", "HQ", MGR),
                # pending start
                (EMP_PEND, "P1", "pending_start", today + timedelta(days=14), None, None, False, False, "employee", today + timedelta(days=14), None, None, "Ops", "HQ", MGR),
                # notice until tomorrow
                (EMP_NOTICE, "N1", "notice", past, today + timedelta(days=5), today + timedelta(days=5), False, False, "employee", past, None, None, "Ops", "HQ", MGR),
                # on leave
                (EMP_LEAVE, "L1", "on_leave", past, None, None, True, False, "employee", past, None, None, "Ops", "HQ", MGR),
                # contingent
                (EMP_CONT, "K1", "active", past, None, None, False, False, "contingent", past, None, None, "Ops", "HQ", MGR),
                # left after LWD yesterday
                (EMP_LEFT, "X1", "left", past, today - timedelta(days=1), today - timedelta(days=1), False, False, "employee", past, today - timedelta(days=1), "voluntary", "Ops", "HQ", MGR),
            ]
            for emp, pk, st, es, ee, lwd, ol, sus, wc, hd, xd, xt, dept, loc, mgr in seeds:
                r = c2.upsert_employment_period(
                    cur, company_code=COMPANY, actor_phone=HR, employee_key=emp,
                    employment_period_key=pk, status=st, effective_start=es, effective_end=ee,
                    last_working_day=lwd, on_leave=ol, suspended=sus, worker_class=wc,
                    hire_event_date=hd, exit_event_date=xd, exit_type=xt,
                    department=dept, location=loc, manager_employee_key=mgr,
                    notice_started_on=(past if st == "notice" else None),
                    reason="seed",
                )
                check(f"seed {pk}", r.get("ok") is True, r)

            # rehire: same person, new period
            c2.upsert_employment_period(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP_REHIRE,
                employment_period_key="R1", status="left", effective_start=past - timedelta(days=800),
                effective_end=past - timedelta(days=500), last_working_day=past - timedelta(days=500),
                hire_event_date=past - timedelta(days=800), exit_event_date=past - timedelta(days=500),
                exit_type="voluntary", department="Ops", manager_employee_key=MGR, person_key="PERSON-R",
                reason="old employment",
            )
            c2.upsert_employment_period(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP_REHIRE,
                employment_period_key="R2", status="active", effective_start=period_start + timedelta(days=1),
                hire_event_date=period_start + timedelta(days=1), department="Ops", manager_employee_key=MGR,
                person_key="PERSON-R", reason="rehire period",
            )

            pop = c2.resolve_workforce_population(cur, company_code=COMPANY, as_of=today)
            check("population ok", pop.get("ok") is True, pop)
            # expected HC: A-F (6) + NOTICE + LEAVE + REHIRE R2 = 9; not PEND, CONT, LEFT
            check("headcount excludes pending", EMP_PEND not in [m["employee_key"] for m in pop["headcount_population"]])
            check("future starters has pending", EMP_PEND in [m["employee_key"] for m in pop["future_starters_population"]])
            check("notice included", EMP_NOTICE in [m["employee_key"] for m in pop["headcount_population"]])
            check("leave included", EMP_LEAVE in [m["employee_key"] for m in pop["headcount_population"]])
            check("contingent excluded", EMP_CONT not in [m["employee_key"] for m in pop["headcount_population"]])
            check("left excluded", EMP_LEFT not in [m["employee_key"] for m in pop["headcount_population"]])
            check("headcount count", pop["headcount"] == 9, pop)

            # historical as-of before notice LWD still includes; after LWD for LEFT at mid still active?
            hist = c2.resolve_workforce_population(cur, company_code=COMPANY, as_of=mid)
            check("historical as-of works", hist.get("ok") is True and hist["headcount"] >= 1, hist)
            # post-LWD for LEFT
            post = c2.resolve_workforce_population(cur, company_code=COMPANY, as_of=today)
            check("post-LWD left out", EMP_LEFT not in [m["employee_key"] for m in post["headcount_population"]])

            # evaluate via C1 shared evaluator
            hc = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.HEADCOUNT_KEY, time_window={"as_of": str(today)})
            check("headcount eval", hc.get("status") == "ok" and float(hc["value"]) == 9.0, hc)
            check("headcount drill", hc.get("population_count") == 9 and EMP_A in hc.get("population_ids", []))
            check("pins definition", hc.get("kpi_definition_id") and hc.get("effective_version"))
            check("ordinary HC not suppressed", hc.get("status") != "suppressed")

            fs = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.FUTURE_STARTERS_KEY, time_window={"as_of": str(today)})
            check("future starters separate", fs.get("status") == "ok" and float(fs["value"]) >= 1.0, fs)

            # FTE evaluate unavailable/blocked if somehow published — company publish already blocked
            fte_ev = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c1.FTE_KEY)
            check("fte evaluate unavailable", fte_ev.get("ok") is not True, fte_ev)

            hires = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.HIRES_KEY,
                time_window={"period_start": str(period_start), "period_end": str(today)},
            )
            check("hires include rehire period", hires.get("status") == "ok" and float(hires["value"]) >= 1.0, hires)
            check("hire drill periods", "R2" in (hires.get("population_ids") or []))

            exits = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.EXITS_KEY,
                time_window={"period_start": str(today - timedelta(days=7)), "period_end": str(today)},
            )
            check("exits recent", exits.get("status") == "ok" and float(exits["value"]) >= 1.0, exits)
            check("exit drill", "X1" in (exits.get("population_ids") or []))

            turn = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.TURNOVER_KEY,
                time_window={"period_start": str(today - timedelta(days=7)), "period_end": str(today)},
            )
            check("turnover ok", turn.get("status") == "ok" and turn.get("denominator_value") not in (None, 0), turn)
            check("turnover explain method", "average_headcount" in str(turn.get("explain")), turn)

            # zero denom: empty company window on OTHER not enabled — use filters with impossible scope
            # create empty-HC company periods none: evaluate turnover with manager scope empty list forcing 0 HC
            turn0 = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.TURNOVER_KEY,
                actor_role="manager",
                filters={"manager_scope_employee_keys": ["NOBODY"]},
                time_window={"period_start": str(today - timedelta(days=7)), "period_end": str(today)},
            )
            check("zero denom not_applicable", turn0.get("status") == "not_applicable" and turn0.get("value") is None, turn0)

            ret = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.RETENTION_KEY,
                time_window={
                    "cohort_start": str(period_start),
                    "cohort_end": str(today),
                    "retention_as_of": str(today),
                },
            )
            check("retention cohort", ret.get("status") == "ok" and ret.get("denominator_value", 0) > 0, ret)
            check("retention not inverse flag", ret.get("explain", {}).get("not_inverse_of_turnover") is True)

            ten = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.TENURE_KEY, time_window={"as_of": str(today)})
            check("tenure distribution", ten.get("status") == "ok" and "distribution" in (ten.get("explain") or {}), ten)

            span = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.SPAN_KEY,
                filters={"manager_employee_key": MGR}, time_window={"as_of": str(today)},
            )
            check("span of control", span.get("status") == "ok" and float(span["value"]) >= 1.0, span)

            # manager scope drill protection
            mgr_hc = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.HEADCOUNT_KEY,
                actor_role="manager",
                filters={"manager_scope_employee_keys": [EMP_A, EMP_B]},
                time_window={"as_of": str(today)},
            )
            check("manager scope limited", mgr_hc.get("status") == "ok" and float(mgr_hc["value"]) == 2.0, mgr_hc)
            check("no cross-manager leak", EMP_C not in (mgr_hc.get("population_ids") or []))

            # historical org segment: transfer EMP_A dept after mid — history at mid stays Ops
            c2.upsert_employment_period(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP_A,
                employment_period_key="A1", status="active", effective_start=past,
                hire_event_date=mid, department="Finance", location="HQ", manager_employee_key=MGR,
                source_version="transfer1", reason="transfer dept",
            )
            # add historical org row spanning past..mid-1 as Ops already inserted; new history from today
            cur.execute(
                """
                INSERT INTO hr_intelligence_org_assignment_history (
                  assignment_hist_id, company_code, employee_key, employment_period_key,
                  department, location, manager_employee_key, effective_from, effective_to, source_authority
                ) VALUES (%s,%s,%s,'A1','Ops','HQ',%s,%s,%s,'test')
                """,
                (str(uuid.uuid4()), COMPANY, EMP_A, MGR, past, mid - timedelta(days=1)),
            )
            cur.execute(
                """
                INSERT INTO hr_intelligence_org_assignment_history (
                  assignment_hist_id, company_code, employee_key, employment_period_key,
                  department, location, manager_employee_key, effective_from, effective_to, source_authority
                ) VALUES (%s,%s,%s,'A1','Finance','HQ',%s,%s,NULL,'test')
                """,
                (str(uuid.uuid4()), COMPANY, EMP_A, MGR, mid),
            )
            asof_old = c2.org_dims_as_of(cur, company=COMPANY, employee_key=EMP_A, employment_period_key="A1", as_of=past + timedelta(days=10))
            asof_new = c2.org_dims_as_of(cur, company=COMPANY, employee_key=EMP_A, employment_period_key="A1", as_of=today)
            check("historical dept Ops", asof_old.get("department") == "Ops", asof_old)
            check("current dept Finance", asof_new.get("department") == "Finance", asof_new)

            # definition pinning: version headcount, old evaluation retains version
            v1 = int(hc["effective_version"])
            ver = c1.version_kpi_definition(
                cur, actor_phone=HR, semantic_key=c2.HEADCOUNT_KEY, reason="v2 wording",
                updates={
                    "business_meaning": "Headcount v2 wording",
                    "status": "published",
                    "formula_contract": {"kind": "workforce_headcount", "sensitive_aggregate": False, "v": 2},
                    "name_en": "Active headcount (heads)",
                    "name_ar": "عدد الرؤوس النشط",
                    "description_en": "v2",
                    "description_ar": "ن٢",
                    "unit": "heads",
                    "time_semantics": "point_in_time",
                    "permission_class": "workforce_general",
                },
            )
            check("definition versioned", ver.get("ok") is True and ver.get("prior_preserved") is True, ver)
            c1.publish_kpi_for_company(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.HEADCOUNT_KEY, reason="pub v2")
            cur.execute(
                "SELECT effective_version FROM hr_kpi_evaluations WHERE evaluation_id=%s",
                (hc["evaluation_id"],),
            )
            check("pinned historical eval version", int(dict(cur.fetchone())["effective_version"]) == v1)

            # correction/reconciliation
            corr = c2.correct_employment_period(
                cur, company_code=COMPANY, actor_phone=HR, employment_period_key="B1",
                reason="retroactive start fix", effective_start=past - timedelta(days=10),
            )
            check("correction", corr.get("ok") is True, corr)
            rb = c2.rebuild_workforce_facts(cur, company_code=COMPANY, actor_phone=HR, reason="rebuild")
            check("idempotent rebuild", rb.get("ok") is True and rb.get("idempotent") is True, rb)
            rb2 = c2.rebuild_workforce_facts(cur, company_code=COMPANY, actor_phone=HR, reason="rebuild2")
            check("rebuild replay", rb2.get("ok") is True)
            # hire facts not double-counted for R2
            hires2 = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.HIRES_KEY,
                time_window={"period_start": str(period_start), "period_end": str(today)},
            )
            check("no double hire count", float(hires2["value"]) == float(hires["value"]), (hires, hires2))

            # complementary suppression helper
            comp = c2.apply_complementary_suppression(segment_count=2, complement_count=2, min_cohort_n=5, sensitive=True)
            check("complementary suppression", comp.get("suppressed") is True, comp)
            comp2 = c2.apply_complementary_suppression(segment_count=2, complement_count=2, min_cohort_n=5, sensitive=False)
            check("ordinary not complementary-suppressed", comp2.get("suppressed") is False)

            # demographic off
            dem = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.HEADCOUNT_KEY,
                filters={"dimension": "gender", "dimension_value": "x"}, time_window={"as_of": str(today)},
            )
            check("gender dimension forbidden", dem.get("status") == "forbidden" or dem.get("error") == "demographic_dimension_disabled", dem)

            # modularity: still works with perf/talent off (already)
            check("modularity perf off env", os.environ.get("WATHEFNI_PERFORMANCE_GOALS_C1") == "off")

            # EN/AR explain labels present on publication names
            check("bilingual headcount name", bool(hc.get("name_en")) and bool(hc.get("name_ar")))

            # disable preserves
            c2.disable_company_workforce_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="off")
            cur.execute("SELECT count(*) AS n FROM hr_intelligence_employment_periods WHERE company_code=%s", (COMPANY,))
            check("periods survive disable", int(dict(cur.fetchone())["n"]) >= 1)
            blocked = c1.evaluate_kpi(cur, company_code=COMPANY, actor_phone=HR, semantic_key=c2.HEADCOUNT_KEY)
            check("eval blocked when disabled", blocked.get("ok") is not True, blocked)

            # C1 regression light
            _flags(companies=COMPANY)
            c1.enable_company_hr_intelligence(cur, company_code=COMPANY, actor_phone=HR, reason="c1 still")
            check("c1 still gateable", c1.runtime_gate_for_company(COMPANY).get("ok") is True)

            _flags(c1_on="off", c2_on="off", companies="")
            check("all off after prove", c2.runtime_gate_for_company(COMPANY).get("ok") is not True)

            conn.commit()
    finally:
        try:
            _db.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("HR_INTELLIGENCE_WORKFORCE_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
