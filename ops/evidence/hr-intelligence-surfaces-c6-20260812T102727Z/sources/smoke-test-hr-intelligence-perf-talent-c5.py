#!/usr/bin/env python3
"""Wave 5 C5 — Performance + Talent Intelligence comprehensive prove."""
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
COMPANY = f"HI5{_N:05d}"[:12].upper()
SMALL = f"H5S{_N:05d}"[:12].upper()
OTHER = f"H5X{_N:05d}"[:12].upper()
HR = f"9656750{_N:05d}"
MANAGER = f"{COMPANY}-M1"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, c1_on: str = "on", c5_on: str = "on", companies: str = "") -> None:
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = c1_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_C5"] = c5_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_COMPANIES"] = companies
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    for flag in (
        "WATHEFNI_HR_INTELLIGENCE_RECRUITING_C3",
        "WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4",
        "WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2",
        "WATHEFNI_PERFORMANCE_GOALS_C1",
        "WATHEFNI_TALENT_PROFILE_C5",
        "WATHEFNI_TALENT_SUCCESSION_C6",
        "WATHEFNI_PERFORMANCE_REVIEWS_C2",
    ):
        os.environ[flag] = "off"


def main() -> int:
    print("    hr intelligence performance talent c5 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_time_pay_c4 as c4
    import hr_intelligence_perf_talent_c5 as c5

    check("c5 module", c5.PHASE == "hr_intelligence_perf_talent_c5")
    check("c5 contract", c5.CONTRACT_VERSION == "hr_intelligence_perf_talent_c5_v1")
    check("c5 stamp", c5.PASS_STAMP == "HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS")
    check("c4 stamp regression", c4.PASS_STAMP == "HR_INTELLIGENCE_TIME_PAY_FULL_PASS")
    check("commercial analytics", c5.COMMERCIAL_MODULE_KEY == "analytics")
    check("all semantic keys", len(c5.ALL_SEMANTIC_KEYS) == 19, c5.ALL_SEMANTIC_KEYS)
    honesty = c5.honesty_payload()
    check("uses C1 evaluator", honesty.get("uses_c1_registry_evaluator") is True)
    check("projection not SoT", honesty.get("projections_are_not_alternate_sot") is True)
    check(
        "recruiting pool isolation honesty",
        honesty.get("recruiting_pool_queried") is False
        and honesty.get("post_hire_talent_only") is True
        and c5.RECRUITING_POOL_QUERIED is False,
        honesty,
    )
    check(
        "forbidden scores declared",
        honesty.get("no_employee_score") is True
        and honesty.get("no_talent_score") is True
        and honesty.get("no_global_readiness_score") is True,
        honesty,
    )
    check("EN label", c5.status_label("designated", lang="en") == "Designated")
    check("AR label", bool(c5.status_label("accepted", lang="ar")))

    _flags(c5_on="off", companies="")
    check("c5 global off", c5.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist", c5.runtime_gate_for_company(COMPANY).get("gate") == "company_allowlist")
    _flags(companies=COMPANY)
    check("canary gate", c5.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant runtime isolation", c5.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise
    try:
        manager = app.db_connect()
        conn = manager.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            c5.ensure_hr_intelligence_perf_talent_c5_schema(cur)
            for code in (COMPANY, SMALL, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"C5 prove {code}"),
                )

            enabled = c5.enable_company_perf_talent_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable c5",
                nine_box_module_enabled=False, min_respondent_threshold=3,
            )
            check("enable c5", enabled.get("ok") is True, enabled)
            check(
                "nine-box defaults off",
                enabled.get("settings", {}).get("nine_box_module_enabled") is False,
                enabled,
            )
            published = c5.publish_perf_talent_kpis_for_company(
                cur, company_code=COMPANY, actor_phone=HR, reason="publish c5"
            )
            check(
                "publish all C5 KPIs",
                published.get("ok") is True
                and set(published.get("published") or []) == set(c5.ALL_SEMANTIC_KEYS),
                published,
            )

            today = date.today()
            window = {
                "period_start": str(today - timedelta(days=365)),
                "period_end": str(today),
            }

            def evaluate(key: str, **kwargs):
                return c1.evaluate_kpi(
                    cur, company_code=COMPANY, actor_phone=HR,
                    semantic_key=key, time_window=window, **kwargs
                )

            # Canonical objective progress: O2 says 100%, but has no current value
            # and therefore must not contribute to attainment.
            c5.upsert_objective(
                cur, company_code=COMPANY, actor_phone=HR, objective_key="O1",
                employee_key="E1", status="active", progress_pct=50,
                direction="increase", baseline=0, target=100, current=50,
                target_version=1, period_start=today - timedelta(days=90),
                period_end=today, department="D1", manager_employee_key=MANAGER,
                reason="objective canonical progress",
            )
            c5.upsert_objective(
                cur, company_code=COMPANY, actor_phone=HR, objective_key="O2",
                employee_key="E2", status="completed", progress_pct=100,
                direction="increase", baseline=0, target=100, current=None,
                target_version=1, period_start=today - timedelta(days=90),
                period_end=today, department="D2", manager_employee_key="M2",
                reason="objective missing current",
            )
            goal = evaluate(c5.GOAL_ATTAINMENT_KEY)
            check(
                "goal attainment canonical progress",
                goal.get("status") == "ok"
                and float(goal.get("value") or 0) == 50.0
                and goal.get("population_ids") == ["O1"],
                goal,
            )
            check(
                "missing current never invents 100%",
                (goal.get("explain") or {}).get("missing_current_excluded") is True
                and (goal.get("explain") or {}).get("progress_invented") is False,
                goal,
            )

            corrected = c5.apply_objective_target_correction(
                cur, company_code=COMPANY, actor_phone=HR, objective_key="O1",
                target=120, reason="approved target correction",
            )
            cur.execute(
                """
                SELECT version, target, superseded_at
                  FROM hr_intelligence_perf_target_versions
                 WHERE company_code=%s AND entity_type='objective' AND entity_key='O1'
                 ORDER BY version
                """,
                (COMPANY,),
            )
            versions = [dict(row) for row in cur.fetchall()]
            check(
                "historical target version preserved",
                corrected.get("ok") is True
                and corrected.get("historical_versions_preserved") is True
                and len(versions) == 2
                and int(versions[0]["version"]) == 1
                and float(versions[0]["target"]) == 100.0
                and versions[0]["superseded_at"] is not None
                and int(versions[1]["version"]) == 2
                and float(versions[1]["target"]) == 120.0,
                (corrected, versions),
            )

            c5.upsert_kr(
                cur, company_code=COMPANY, actor_phone=HR, kr_key="KR1",
                objective_key="O1", employee_key="E1", status="active",
                progress_pct=40, baseline=0, target=10, current=4,
                target_version=1, reason="KR canonical progress",
            )
            kr = evaluate(c5.KR_ATTAINMENT_KEY)
            check("KR attainment", kr.get("status") == "ok" and float(kr.get("value") or 0) == 40.0, kr)

            c5.upsert_review_cycle(
                cur, company_code=COMPANY, actor_phone=HR, cycle_key="CYCLE-DRAFT",
                status="in_progress", scale_key="FIVE", scale_version="v1",
                scale_type="numeric", reason="review cycle",
            )
            review_states = [
                ("E1", "submitted", "submitted", True, MANAGER),
                ("E2", "submitted", "draft", False, MANAGER),
                ("E3", "submitted", "submitted", False, "M2"),
                ("E4", "draft", "draft", False, "M2"),
                ("E5", "draft", "draft", False, "M2"),
            ]
            for employee, self_status, manager_status, full, manager_key in review_states:
                c5.upsert_review_population(
                    cur, company_code=COMPANY, actor_phone=HR,
                    cycle_key="CYCLE-DRAFT", employee_key=employee,
                    self_status=self_status, manager_status=manager_status,
                    fully_completed=full, layer_submitted_rating="5" if employee == "E1" else None,
                    layer_pre_calibration_rating="5" if employee == "E1" else None,
                    final_locked=False, manager_employee_key=manager_key,
                    reason="review population",
                )
            self_completion = evaluate(
                c5.REVIEW_SELF_COMPLETION_KEY, filters={"cycle_key": "CYCLE-DRAFT"}
            )
            manager_completion = evaluate(
                c5.REVIEW_MANAGER_COMPLETION_KEY, filters={"cycle_key": "CYCLE-DRAFT"}
            )
            full_completion = evaluate(
                c5.REVIEW_FULL_COMPLETION_KEY, filters={"cycle_key": "CYCLE-DRAFT"}
            )
            check(
                "self manager full completion distinct",
                float(self_completion.get("value") or 0) == 60.0
                and float(manager_completion.get("value") or 0) == 40.0
                and float(full_completion.get("value") or 0) == 20.0,
                (self_completion, manager_completion, full_completion),
            )

            incomplete = evaluate(
                c5.OUTCOME_DISTRIBUTION_KEY, filters={"cycle_key": "CYCLE-DRAFT"}
            )
            check(
                "incomplete cycle fabricates no final",
                incomplete.get("status") == "insufficient_data"
                and incomplete.get("value") is None
                and (incomplete.get("explain") or {}).get("fake_finals") is False,
                incomplete,
            )
            c5.upsert_review_population(
                cur, company_code=COMPANY, actor_phone=HR,
                cycle_key="CYCLE-DRAFT", employee_key="E1",
                self_status="submitted", manager_status="submitted",
                fully_completed=True, layer_submitted_rating="5",
                layer_pre_calibration_rating="5", layer_final_rating="5",
                final_locked=True, manager_employee_key=MANAGER,
                reason="lock approved final",
            )
            locked = evaluate(
                c5.OUTCOME_DISTRIBUTION_KEY, filters={"cycle_key": "CYCLE-DRAFT"}
            )
            check(
                "locked final drives distribution",
                locked.get("status") == "ok"
                and float(locked.get("value") or 0) == 1.0
                and (locked.get("explain") or {}).get("distribution") == {"5": 1}
                and (locked.get("explain") or {}).get("final_locked_only") is True,
                locked,
            )
            c5.upsert_review_cycle(
                cur, company_code=COMPANY, actor_phone=HR, cycle_key="CYCLE-V2",
                status="closed", scale_key="FIVE", scale_version="v2",
                scale_type="numeric", reason="incompatible scale prove",
            )
            c5.upsert_review_population(
                cur, company_code=COMPANY, actor_phone=HR,
                cycle_key="CYCLE-V2", employee_key="E6",
                self_status="submitted", manager_status="submitted",
                fully_completed=True, layer_final_rating="4", final_locked=True,
                manager_employee_key="M2", reason="incompatible scale population",
            )
            incompatible = evaluate(
                c5.OUTCOME_DISTRIBUTION_KEY,
                filters={"require_compatible_scale": True},
            )
            check(
                "cross-scale outcomes fail closed",
                incompatible.get("status") == "insufficient_data"
                and incompatible.get("value") is None
                and set(incompatible.get("explain", {}).get("incompatible_scale_versions") or [])
                == {"v1", "v2"},
                incompatible,
            )
            no_policy = evaluate(
                c5.HIGH_PERFORMER_COUNT_KEY, filters={"cycle_key": "CYCLE-DRAFT"}
            )
            high_performer = evaluate(
                c5.HIGH_PERFORMER_COUNT_KEY,
                filters={"cycle_key": "CYCLE-DRAFT", "qualifying_final_ratings": ["5"]},
            )
            check(
                "high performer requires explicit policy",
                no_policy.get("status") == "unavailable"
                and no_policy.get("value") is None
                and (no_policy.get("explain") or {}).get("registry_policy_required")
                == "filters.qualifying_final_ratings",
                no_policy,
            )
            check(
                "high performer is not HiPo",
                high_performer.get("status") == "ok"
                and float(high_performer.get("value") or 0) == 1.0
                and (high_performer.get("explain") or {}).get("hipo_not_used") is True,
                high_performer,
            )

            aggregate = c5.upsert_360_aggregate(
                cur, company_code=COMPANY, actor_phone=HR, cycle_key="CYCLE-DRAFT",
                employee_key="E1", respondent_count=2, aggregate_value=4.8,
                reason="below anonymity threshold",
            )
            hidden_360 = c5.get_360_aggregate(
                cur, company_code=COMPANY, cycle_key="CYCLE-DRAFT", employee_key="E1"
            )
            check(
                "360 anonymity fails closed",
                aggregate.get("aggregate", {}).get("anonymity_ok") is False
                and aggregate.get("aggregate", {}).get("aggregate_value") is None
                and hidden_360.get("status") == "suppressed"
                and hidden_360.get("value") is None
                and hidden_360.get("respondent_identities") == [],
                (aggregate, hidden_360),
            )

            c5.upsert_competency(
                cur, company_code=COMPANY, actor_phone=HR, assessment_key="A1",
                employee_key="E1", framework_version="CF-2026.2",
                competency_key="LEAD", source_role="manager", score=4,
                status="completed", reason="competency assessment",
            )
            competency = evaluate(
                c5.COMPETENCY_ASSESSED_KEY, filters={"framework_version": "CF-2026.2"}
            )
            check(
                "competency framework version preserved",
                float(competency.get("value") or 0) == 1.0
                and (competency.get("explain") or {}).get("framework_versions") == ["CF-2026.2"],
                competency,
            )

            c5.upsert_dev_action(
                cur, company_code=COMPANY, actor_phone=HR, action_key="DA1",
                employee_key="E1", status="in_progress", source="check_in",
                category="leadership", reason="C3-like development projection",
            )
            c5.upsert_dev_action(
                cur, company_code=COMPANY, actor_phone=HR, action_key="DA2",
                employee_key="E2", status="done", source="competency_gap",
                category="technical", reason="C3-like development projection",
            )
            dev_active = evaluate(c5.DEV_ACTIONS_ACTIVE_KEY)
            dev_done = evaluate(c5.DEV_ACTIONS_COMPLETED_KEY)
            check(
                "development C3-like projection",
                float(dev_active.get("value") or 0) == 1.0
                and float(dev_done.get("value") or 0) == 1.0
                and (dev_active.get("explain") or {}).get("c3_like_projection") is True,
                (dev_active, dev_done),
            )

            for index in range(1, 6):
                c5.upsert_talent_profile(
                    cur, company_code=COMPANY, actor_phone=HR,
                    employee_key=f"E{index}", active=True, reason="post-hire talent profile",
                )
                c5.upsert_potential(
                    cur, company_code=COMPANY, actor_phone=HR,
                    assessment_key=f"PA{index}", employee_key=f"E{index}",
                    framework_version="PF-2", status="accepted", level="high",
                    reason="explicit accepted potential",
                )
                c5.upsert_hipo(
                    cur, company_code=COMPANY, actor_phone=HR,
                    designation_key=f"H{index}", employee_key=f"E{index}",
                    status="designated", inferred_from_nine_box=False,
                    reason="explicit HiPo designation",
                )
            c5.upsert_potential(
                cur, company_code=COMPANY, actor_phone=HR,
                assessment_key="PA-SUBMITTED", employee_key="E6",
                framework_version="PF-2", status="submitted", level="medium",
                reason="unaccepted potential",
            )
            c5.upsert_hipo(
                cur, company_code=COMPANY, actor_phone=HR,
                designation_key="H-NOM", employee_key="E6", status="nominated",
                reason="not designated",
            )
            inferred = c5.upsert_hipo(
                cur, company_code=COMPANY, actor_phone=HR,
                designation_key="H-BAD", employee_key="E7", status="designated",
                inferred_from_nine_box=True, reason="must reject inferred HiPo",
            )
            check(
                "reject inferred nine-box HiPo",
                inferred.get("ok") is False
                and inferred.get("error") == "hipo_inference_forbidden",
                inferred,
            )

            potential = evaluate(c5.POTENTIAL_ASSESSED_KEY)
            hipo = evaluate(c5.HIPO_COUNT_KEY)
            check(
                "potential accepted explicit only",
                potential.get("status") == "ok"
                and float(potential.get("value") or 0) == 5.0
                and (potential.get("explain") or {}).get("accepted_only") is True,
                potential,
            )
            check(
                "HiPo designated only",
                hipo.get("status") == "ok"
                and float(hipo.get("value") or 0) == 5.0
                and (hipo.get("explain") or {}).get("designated_only") is True,
                hipo,
            )
            reconciliation = c5.reconcile_perf_talent_populations(cur, company_code=COMPANY)
            check(
                "performance never becomes potential",
                reconciliation.get("explain", {}).get("performance_never_becomes_potential") is True
                and reconciliation.get("explain", {}).get("performance_outcome_is_not_hipo") is True,
                reconciliation,
            )

            for index in range(1, 6):
                c5.upsert_critical_role(
                    cur, company_code=COMPANY, actor_phone=HR, role_key=f"R{index}",
                    title=f"Critical role {index}", active=True, reason="critical role",
                )
            nominations = [
                ("N1", "R1", "E1", "ready_now"),
                ("N2", "R2", "E1", "ready_lt_1y"),
                ("N3", "R3", "E3", "unassessed"),
                ("N4", "R1", "E4", "ready_lt_1y"),
                ("N5", "R2", "E5", "ready_1_2y"),
                ("N6", "R1", "E6", "ready_1_2y"),
                ("N7", "R1", "E7", "longer_term"),
                ("N8", "R1", "E8", "not_ready"),
            ]
            for nomination, role, employee, readiness in nominations:
                c5.upsert_nomination(
                    cur, company_code=COMPANY, actor_phone=HR,
                    nomination_key=nomination, role_key=role, employee_key=employee,
                    readiness=readiness, status="active", reason="successor nomination",
                )
            succession = evaluate(c5.SUCCESSION_COVERAGE_KEY)
            ready_now = evaluate(c5.READY_NOW_COVERAGE_KEY)
            uncovered = evaluate(c5.UNCOVERED_ROLES_KEY)
            readiness = evaluate(c5.READINESS_DISTRIBUTION_KEY)
            successors_r1 = evaluate(
                c5.SUCCESSORS_PER_ROLE_KEY, filters={"role_key": "R1"}
            )
            check(
                "succession and ready-now coverage distinct",
                succession.get("status") == "ok"
                and ready_now.get("status") == "ok"
                and float(succession.get("value") or 0) == 60.0
                and float(ready_now.get("value") or 0) == 20.0,
                (succession, ready_now),
            )
            check(
                "uncovered critical roles",
                uncovered.get("status") == "ok"
                and float(uncovered.get("value") or 0) == 2.0
                and set(uncovered.get("explain", {}).get("uncovered_role_keys") or []) == {"R4", "R5"},
                uncovered,
            )
            check(
                "readiness is target-specific",
                readiness.get("status") == "ok"
                and float(readiness.get("value") or 0) == 8.0
                and readiness.get("explain", {}).get("same_employee_multiple_roles_allowed") is True
                and successors_r1.get("status") == "ok"
                and float(successors_r1.get("value") or 0) == 5.0,
                (readiness, successors_r1),
            )
            bench = evaluate(c5.BENCH_STRENGTH_KEY)
            check(
                "bench strength unavailable without black-box",
                bench.get("status") in {"unavailable", "blocked"}
                and bench.get("value") is None
                and bench.get("explain", {}).get("black_box_score") is False,
                bench,
            )

            manager_perf = evaluate(
                c5.GOAL_ATTAINMENT_KEY, actor_role="manager",
                filters={"manager_scope_keys": [MANAGER]},
            )
            manager_talent = evaluate(
                c5.POTENTIAL_ASSESSED_KEY, actor_role="manager",
                filters={"manager_scope_keys": [MANAGER], "has_talent_permission": False},
            )
            check(
                "manager performance aggregate allowed scoped",
                manager_perf.get("status") == "ok"
                and manager_perf.get("population_ids") == ["O1"],
                manager_perf,
            )
            check(
                "manager talent forbidden without permission",
                manager_talent.get("status") == "forbidden"
                and manager_talent.get("value") is None,
                manager_talent,
            )

            # Performance modules off must not disable talent.
            c5.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR,
                goals_module_enabled=False, reviews_module_enabled=False,
                calibration_module_enabled=False, feedback_module_enabled=False,
                talent_profile_module_enabled=True,
                succession_module_enabled=True, hipo_module_enabled=True,
                reason="performance off talent on",
            )
            talent_independent = evaluate(c5.TALENT_POPULATION_KEY)
            goals_off = evaluate(c5.GOAL_ATTAINMENT_KEY)
            check(
                "talent works with performance off",
                talent_independent.get("status") == "ok"
                and float(talent_independent.get("value") or 0) == 5.0
                and goals_off.get("status") == "unavailable"
                and goals_off.get("value") is None,
                (talent_independent, goals_off),
            )

            # Talent modules off must not disable performance.
            c5.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR,
                goals_module_enabled=True, reviews_module_enabled=True,
                calibration_module_enabled=True, feedback_module_enabled=True,
                talent_profile_module_enabled=False,
                succession_module_enabled=False, hipo_module_enabled=False,
                reason="talent off performance on",
            )
            performance_independent = evaluate(c5.GOAL_ATTAINMENT_KEY)
            talent_off = evaluate(c5.TALENT_POPULATION_KEY)
            check(
                "performance works with talent off",
                performance_independent.get("status") == "ok"
                and talent_off.get("status") == "unavailable"
                and talent_off.get("value") is None,
                (performance_independent, talent_off),
            )
            c5.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR,
                talent_profile_module_enabled=True, succession_module_enabled=True,
                hipo_module_enabled=True, nine_box_module_enabled=False,
                reason="restore talent modules",
            )
            nine_box_related = evaluate(
                c5.TALENT_POPULATION_KEY, filters={"nine_box_related": True}
            )
            talent_without_nine_box = evaluate(c5.TALENT_POPULATION_KEY)
            check(
                "nine-box disabled while talent works",
                nine_box_related.get("status") == "unavailable"
                and nine_box_related.get("explain", {}).get("nine_box_module_off") is True
                and talent_without_nine_box.get("status") == "ok",
                (nine_box_related, talent_without_nine_box),
            )
            snapshot = c5.upsert_nine_box_snapshot(
                cur, company_code=COMPANY, actor_phone=HR, review_key="NB1",
                employee_key="E1", box_label="top_right", config_version="NB-v1",
                is_canonical=True, reason="optional noncanonical projection",
            )
            check(
                "nine-box snapshot remains noncanonical",
                snapshot.get("ok") is True
                and snapshot.get("is_canonical") is False
                and snapshot.get("nine_box_snapshot", {}).get("is_canonical") is False,
                snapshot,
            )

            first_rebuild = c5.rebuild_perf_talent_facts(
                cur, company_code=COMPANY, actor_phone=HR, reason="rebuild one"
            )
            second_rebuild = c5.rebuild_perf_talent_facts(
                cur, company_code=COMPANY, actor_phone=HR, reason="rebuild two"
            )
            check(
                "rebuild idempotent",
                first_rebuild.get("ok") is True
                and second_rebuild.get("ok") is True
                and first_rebuild.get("counts") == second_rebuild.get("counts")
                and int(second_rebuild.get("idempotent_updates") or 0) > 0,
                (first_rebuild, second_rebuild),
            )

            cur.execute(
                """
                SELECT semantic_key, name_en, name_ar, time_semantics, permission_class
                  FROM hr_kpi_definitions
                 WHERE semantic_key IN (%s,%s)
                   AND effective_version = (
                     SELECT MAX(d2.effective_version) FROM hr_kpi_definitions d2
                      WHERE d2.semantic_key=hr_kpi_definitions.semantic_key
                   )
                 ORDER BY semantic_key
                """,
                (c5.GOAL_ATTAINMENT_KEY, c5.HIPO_COUNT_KEY),
            )
            governed = [dict(row) for row in cur.fetchall()]
            by_key = {row["semantic_key"]: row for row in governed}
            check(
                "bilingual valid C1 definitions",
                len(governed) == 2
                and all(row.get("name_en") and row.get("name_ar") for row in governed)
                and all(row.get("time_semantics") in c1.TIME_SEMANTICS for row in governed)
                and by_key[c5.GOAL_ATTAINMENT_KEY]["permission_class"] == "performance_aggregate"
                and by_key[c5.HIPO_COUNT_KEY]["permission_class"] == "talent_sensitive",
                governed,
            )

            assistant_refusal = c5.assistant_explain_metric(
                cur, company_code=COMPANY, semantic_key="talent_score", actor_phone=HR
            )
            check(
                "assistant refuses invented metric",
                assistant_refusal.get("ok") is False
                and assistant_refusal.get("invented") is False,
                assistant_refusal,
            )

            # A separate one-person company proves C1 talent-sensitive suppression.
            _flags(companies=f"{COMPANY},{SMALL}")
            small_enabled = c5.enable_company_perf_talent_intelligence(
                cur, company_code=SMALL, actor_phone=HR, reason="enable small"
            )
            small_published = c5.publish_perf_talent_kpis_for_company(
                cur, company_code=SMALL, actor_phone=HR, reason="publish small"
            )
            c5.upsert_talent_profile(
                cur, company_code=SMALL, actor_phone=HR,
                employee_key="ONLY1", active=True, reason="small cohort",
            )
            small_talent = c1.evaluate_kpi(
                cur, company_code=SMALL, actor_phone=HR,
                semantic_key=c5.TALENT_POPULATION_KEY, time_window=window,
            )
            check(
                "small talent cohort suppressed",
                small_enabled.get("ok") is True
                and small_published.get("ok") is True
                and small_talent.get("status") == "suppressed"
                and small_talent.get("value") is None
                and small_talent.get("permission_class") == "talent_sensitive"
                and int(small_talent.get("population_count") or 0) == 1,
                small_talent,
            )

            _flags(companies=COMPANY)
            tenant_write = c5.upsert_talent_profile(
                cur, company_code=OTHER, actor_phone=HR,
                employee_key="LEAK", active=True, reason="must fail tenant gate",
            )
            check("tenant write isolation", tenant_write.get("ok") is not True, tenant_write)

            disabled = c5.disable_company_perf_talent_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="disable prove"
            )
            cur.execute(
                "SELECT count(*) AS n FROM hr_intelligence_talent_profiles WHERE company_code=%s",
                (COMPANY,),
            )
            preserved_count = int(dict(cur.fetchone())["n"])
            blocked_after_disable = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR,
                semantic_key=c5.TALENT_POPULATION_KEY, time_window=window,
            )
            check(
                "disable preserves projections",
                disabled.get("preserves_history") is True and preserved_count == 5,
                (disabled, preserved_count),
            )
            check(
                "disabled evaluation unavailable",
                blocked_after_disable.get("status") == "unavailable",
                blocked_after_disable,
            )

            _flags(c5_on="off", companies="")
            check("all C5 gates off", c5.runtime_gate_for_company(COMPANY).get("ok") is not True)
            conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print(c5.PASS_STAMP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
