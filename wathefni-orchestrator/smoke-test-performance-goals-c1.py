#!/usr/bin/env python3
"""Wave 4 C1 — Performance Goals / OKR / KPI synthetic prove."""
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
COMPANY = f"PG1{_N:05d}"[:12].upper()
OTHER = f"PGX{_N:05d}"[:12].upper()
HR = f"9656200{_N:05d}"
EMP = f"{COMPANY}-W4C1-{SUFFIX}"
EMP_PHONE = f"9656201{_N:05d}"


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
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = on
    os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = companies
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"


def main() -> int:
    print("    performance goals c1 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import performance_goals_c1 as c1

    check("c1 module", c1.PHASE == "performance_goals_c1")
    check("charter stamp", c1.PASS_STAMP == "PERFORMANCE_GOALS_FULL_PASS")
    check("commercial performance", c1.COMMERCIAL_MODULE_KEY == "performance")
    check("OKRs first-class honesty", c1.honesty_payload().get("okrs_first_class") is True)
    check("decorative % forbidden", c1.honesty_payload().get("decorative_progress_pct_forbidden") is True)
    check("talent not required", c1.honesty_payload().get("talent_required") is False)
    check("cycles not required", c1.honesty_payload().get("review_cycle_required") is False)
    check("assistant out", c1.honesty_payload().get("assistant_mutations") is False)
    check("rollback", "WATHEFNI_PERFORMANCE_GOALS_C1=off" in str(c1.rollback_guidance()))
    check("EN objective", c1.status_label("objective", lang="en") == "Objective")
    check("AR key result", "نتيجة" in c1.status_label("key_result", lang="ar"))

    # Measure engine unit
    hib = c1.compute_progress(direction="higher_is_better", baseline=0, target=100, current=40)
    check("higher_is_better 40%", hib.get("progress_pct") == 40.0, hib)
    lib = c1.compute_progress(direction="lower_is_better", baseline=100, target=40, current=70)
    check("lower_is_better math", abs(float(lib.get("progress_pct") or 0) - 50.0) < 0.01, lib)
    miss = c1.compute_progress(direction="higher_is_better", baseline=0, target=100, current=None)
    check("missing current ≠ 100%", miss.get("progress_pct") is None and miss.get("status") == "not_started", miss)
    rng = c1.compute_progress(
        direction="target_range", baseline=10, target=20, current=15, range_low=10, range_high=20
    )
    check("target_range in bounds", rng.get("progress_pct") == 100.0, rng)
    dec = c1.reject_decorative_progress_pct(progress_pct=87)
    check("reject free-typed %", dec.get("error") == "decorative_progress_pct_forbidden", dec)

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

    period_start = date(2036, 1, 1)
    period_end = date(2036, 12, 31)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c1.ensure_performance_goals_c1_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PG1 {COMPANY}"),
            )
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
                """,
                (COMPANY, EMP, EMP_PHONE, "W4C1 Emp", period_start, period_start),
            )

            blocked = c1.create_objective(
                cur, company_code=COMPANY, actor_phone=HR, title_en="x", scope="individual"
            )
            check("blocked while entitlement off", blocked.get("ok") is not True, blocked)

            en = c1.enable_company_performance_goals(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable c1"
            )
            check("enable company", en.get("ok") is True, en)
            vis = c1.feature_visibility(cur, COMPANY)
            check("OKRs visible", vis.get("okrs_visible") is True, vis)
            check("cycles hidden in C1", vis.get("review_cycles_visible") is False, vis)
            check("talent hidden in C1", vis.get("talent_visible") is False, vis)

            # Measures
            m_rev = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Revenue",
                name_ar="إيرادات",
                unit="KWD",
                direction="higher_is_better",
                source="manual",
                baseline=0,
                target=1000,
                period_start=period_start,
                period_end=period_end,
                owner_employee_key=EMP,
            )
            check("measure contract created", m_rev.get("ok") is True, m_rev)
            mid_rev = str(m_rev["measure"]["measure_id"])

            m_nps = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Support tickets",
                unit="count",
                direction="lower_is_better",
                baseline=100,
                target=40,
                period_start=period_start,
                period_end=period_end,
                owner_employee_key=EMP,
            )
            mid_nps = str(m_nps["measure"]["measure_id"])

            # Versioned target change
            ch = c1.change_measure_targets(
                cur,
                company_code=COMPANY,
                measure_id=mid_rev,
                actor_phone=HR,
                reason="raise annual target",
                target=1200,
            )
            check("versioned target change", ch.get("ok") is True and int(ch["measure"]["version"]) >= 2, ch)
            versions = c1.list_target_versions(
                cur, company_code=COMPANY, subject_type="measure", subject_id=mid_rev
            )
            check("target versions retained", len(versions) >= 2, len(versions))

            # OKR
            obj = c1.create_objective(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                title_en="Grow enterprise revenue",
                title_ar="نمو إيرادات المؤسسات",
                scope="individual",
                owner_employee_key=EMP,
                period_start=period_start,
                period_end=period_end,
            )
            check("objective created", obj.get("ok") is True and obj.get("not_generic_goal") is True, obj)
            oid = str(obj["objective"]["objective_id"])

            act_early = c1.activate_objective(
                cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, reason="early"
            )
            check("objective requires KR", act_early.get("error") == "objective_requires_at_least_one_key_result", act_early)

            kr1 = c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=oid,
                actor_phone=HR,
                title_en="Close 1000 KWD revenue",
                measure_id=mid_rev,
                weight=2,
            )
            check("KR created with measure", kr1.get("ok") is True and kr1.get("not_kpi_alias") is True, kr1)
            kr1_id = str(kr1["key_result"]["key_result_id"])

            kr2 = c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=oid,
                actor_phone=HR,
                title_en="Reduce support tickets",
                measure_id=mid_nps,
                weight=1,
            )
            check("second KR", kr2.get("ok") is True, kr2)
            kr2_id = str(kr2["key_result"]["key_result_id"])

            no_meas = c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=oid,
                actor_phone=HR,
                title_en="bad",
                measure_id=str(uuid.uuid4()),
            )
            check("KR without valid measure rejected", no_meas.get("ok") is not True, no_meas)

            act = c1.activate_objective(
                cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, reason="activate OKR"
            )
            check("objective activated", act.get("ok") is True, act)

            roll0 = c1.objective_rollup(cur, company_code=COMPANY, objective_id=oid)
            check(
                "OKR rollup unknown before progress",
                roll0.get("progress_pct") is None and roll0.get("status") == "not_started",
                roll0,
            )

            bad_pct = c1.record_progress(
                cur,
                company_code=COMPANY,
                subject_type="key_result",
                subject_id=kr1_id,
                actor_phone=EMP_PHONE,
                current_value=500,
                progress_pct=99,
            )
            check("refuse decorative progress_pct", bad_pct.get("error") == "decorative_progress_pct_forbidden", bad_pct)

            p1 = c1.record_progress(
                cur,
                company_code=COMPANY,
                subject_type="key_result",
                subject_id=kr1_id,
                actor_phone=EMP_PHONE,
                current_value=600,  # target now 1200 → 50%
                source="manual",
            )
            check("KR progress computed", p1.get("ok") is True and abs(float(p1["computed"]["progress_pct"]) - 50.0) < 0.1, p1)

            p2 = c1.record_progress(
                cur,
                company_code=COMPANY,
                subject_type="key_result",
                subject_id=kr2_id,
                actor_phone=EMP_PHONE,
                current_value=70,  # lower_is_better 100→40 at 70 = 50%
            )
            check("KR2 progress", p2.get("ok") is True, p2)

            roll = c1.objective_rollup(cur, company_code=COMPANY, objective_id=oid)
            # weights 2 and 1 both ~50% → ~50
            check(
                "KR progress → Objective roll-up",
                roll.get("ok") is True and abs(float(roll.get("progress_pct") or 0) - 50.0) < 1.0,
                roll,
            )

            # Coexist KPI / milestone / development goals
            m_kpi = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Utilization",
                unit="%",
                direction="higher_is_better",
                baseline=0,
                target=80,
                period_start=period_start,
                period_end=period_end,
            )
            g_kpi = c1.create_goal(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                goal_kind="kpi",
                title_en="Utilization KPI",
                scope="individual",
                measure_id=str(m_kpi["measure"]["measure_id"]),
                owner_employee_key=EMP,
            )
            check("KPI goal coexist", g_kpi.get("ok") is True, g_kpi)
            c1.activate_goal(
                cur, company_code=COMPANY, goal_id=str(g_kpi["goal"]["goal_id"]), actor_phone=HR, reason="a"
            )

            m_ms = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Cert complete",
                unit="flag",
                direction="milestone",
                baseline=0,
                target=1,
                period_start=period_start,
                period_end=period_end,
            )
            g_ms = c1.create_goal(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                goal_kind="milestone",
                title_en="Complete certification",
                scope="individual",
                measure_id=str(m_ms["measure"]["measure_id"]),
                owner_employee_key=EMP,
            )
            check("milestone goal", g_ms.get("ok") is True, g_ms)

            g_dev = c1.create_goal(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                goal_kind="development",
                title_en="Improve coaching skills",
                title_ar="تحسين مهارات التوجيه",
                scope="individual",
                owner_employee_key=EMP,
            )
            check("development goal without forcing OKR", g_dev.get("ok") is True, g_dev)

            # Reject OKR-as-goal-kind
            bad_kind = c1.create_goal(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                goal_kind="okr",
                title_en="fake",
                scope="individual",
            )
            check("OKR not stored as goal_kind", bad_kind.get("ok") is not True, bad_kind)

            # Alignment without cascade
            obj2 = c1.create_objective(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                title_en="Company growth",
                scope="company",
                period_start=period_start,
                period_end=period_end,
            )
            # need a KR for activate later not required for link
            m_co = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Company revenue",
                unit="KWD",
                direction="higher_is_better",
                baseline=0,
                target=10000,
                period_start=period_start,
                period_end=period_end,
            )
            c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=str(obj2["objective"]["objective_id"]),
                actor_phone=HR,
                title_en="Company KR",
                measure_id=str(m_co["measure"]["measure_id"]),
            )
            link = c1.create_alignment_link(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                from_type="objective",
                from_id=oid,
                to_type="objective",
                to_id=str(obj2["objective"]["objective_id"]),
                link_kind="contributes_to",
            )
            check("alignment without forced cascade", link.get("ok") is True and link.get("inherits_score") is False, link)

            # Scopes
            for sc in ("team", "department", "company"):
                o = c1.create_objective(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    title_en=f"{sc} obj",
                    scope=sc,
                    org_unit_id=f"OU-{sc}",
                    period_start=period_start,
                    period_end=period_end,
                )
                check(f"scope {sc}", o.get("ok") is True, o)

            # Disable preserves history
            off = c1.disable_company_performance_goals(
                cur, company_code=COMPANY, actor_phone=HR, reason="rollback"
            )
            check("disable preserves history", off.get("history_preserved") is True, off)
            cur.execute(
                "SELECT count(*) AS c FROM perf_objectives WHERE company_code=%s",
                (COMPANY,),
            )
            check("objectives intact after rollback", int((cur.fetchone() or {}).get("c") or 0) >= 2)
            cur.execute(
                "SELECT count(*) AS c FROM perf_progress_entries WHERE company_code=%s",
                (COMPANY,),
            )
            check("progress history intact", int((cur.fetchone() or {}).get("c") or 0) >= 2)
            check("module-off after disable", c1.module_enabled_for_company(cur, COMPANY).get("ok") is not True)

            src = Path(__file__).with_name("performance_goals_c1.py").read_text()
            check("EN/AR contracts", "status_label" in src and "هدف رئيسي" in src)
            check("conflation guards", "not_generic_goal" in src and "decorative_progress_pct_forbidden" in src)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("PERFORMANCE_GOALS_UNIT_PASS")
    print("PERFORMANCE_GOALS_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
