#!/usr/bin/env python3
"""Wave 5 C4 — Time/Leave/Payroll Intelligence comprehensive prove."""
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
COMPANY = f"HI4{_N:05d}"[:12].upper()
EMPTY = f"H4E{_N:05d}"[:12].upper()
SMALL = f"H4S{_N:05d}"[:12].upper()
OTHER = f"H4X{_N:05d}"[:12].upper()
HR = f"9656730{_N:05d}"
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


def _flags(*, c1_on: str = "on", c4_on: str = "on", companies: str = "") -> None:
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"] = c1_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES"] = companies
    os.environ["WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4"] = c4_on
    os.environ["WATHEFNI_HR_INTELLIGENCE_TIME_PAY_COMPANIES"] = companies
    os.environ["WATHEFNI_ANALYTICS_KILL"] = "off"
    for flag in (
        "WATHEFNI_HR_INTELLIGENCE_RECRUITING_C3",
        "WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2",
        "WATHEFNI_PERFORMANCE_GOALS_C1",
        "WATHEFNI_TALENT_PROFILE_C5",
        "WATHEFNI_TALENT_SUCCESSION_C6",
        "WATHEFNI_PERFORMANCE_REVIEWS_C2",
    ):
        os.environ[flag] = "off"


def main() -> int:
    print("    hr intelligence time pay c4 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hr_intelligence_registry_c1 as c1
    import hr_intelligence_recruiting_c3 as c3
    import hr_intelligence_time_pay_c4 as c4

    check("c4 module", c4.PHASE == "hr_intelligence_time_pay_c4")
    check("c4 contract", c4.CONTRACT_VERSION == "hr_intelligence_time_pay_c4_v1")
    check("c4 stamp", c4.PASS_STAMP == "HR_INTELLIGENCE_TIME_PAY_FULL_PASS")
    check("commercial analytics", c4.COMMERCIAL_MODULE_KEY == "analytics")
    check("c3 import regression", c3.PASS_STAMP == "HR_INTELLIGENCE_RECRUITING_FULL_PASS")
    honesty = c4.honesty_payload()
    check("uses c1 evaluator", honesty.get("uses_c1_registry_evaluator") is True)
    check("projection not SoT", honesty.get("projections_are_not_alternate_sot") is True)
    check("no fx", honesty.get("fx_conversion") is False and honesty.get("currency") == "KWD")
    check("EN status", c4.status_label("finalized", lang="en") == "Finalized")
    check("AR status", bool(c4.status_label("approved_leave", lang="ar")))
    check("all semantic keys", len(c4.ALL_SEMANTIC_KEYS) == 18, c4.ALL_SEMANTIC_KEYS)

    _flags(c4_on="off", companies="")
    check("c4 global off", c4.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist", c4.runtime_gate_for_company(COMPANY).get("gate") == "company_allowlist")
    _flags(companies=COMPANY)
    check("canary gate", c4.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant runtime isolation", c4.runtime_gate_for_company(OTHER).get("ok") is not True)

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
            c4.ensure_hr_intelligence_time_pay_c4_schema(cur)
            for code in (COMPANY, EMPTY, SMALL, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"C4 prove {code}"),
                )

            enabled = c4.enable_company_time_pay_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable c4"
            )
            check("enable c4", enabled.get("ok") is True, enabled)
            published = c4.publish_time_pay_kpis_for_company(
                cur, company_code=COMPANY, actor_phone=HR, reason="publish c4"
            )
            check(
                "publish all c4 kpis",
                published.get("ok") is True
                and set(published.get("published") or []) == set(c4.ALL_SEMANTIC_KEYS),
                published,
            )

            today = date.today()
            start = today - timedelta(days=60)
            window = {"period_start": str(start), "period_end": str(today)}

            def evaluate(key: str, **kwargs):
                return c1.evaluate_kpi(
                    cur, company_code=COMPANY, actor_phone=HR,
                    semantic_key=key, time_window=window, **kwargs
                )

            # Raw punch first, then the authoritative projection replaces the same
            # employee/day unique key. Only raw_punch_only=false rows are metric input.
            raw_day = today - timedelta(days=12)
            c4.upsert_attendance_day(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E0",
                work_date=raw_day, status="absent", reason="raw device event",
                expected_work=True, scheduled=True, raw_punch_only=True,
                source_authority="raw_punch_device",
            )
            c4.upsert_attendance_day(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E0",
                work_date=raw_day, status="present", reason="authoritative day projection",
                expected_work=True, scheduled=True, raw_punch_only=False,
                source_authority="attendance_day_projection",
            )
            cur.execute(
                """
                SELECT status, raw_punch_only, source_authority
                  FROM hr_intelligence_attendance_days
                 WHERE company_code=%s AND employee_key='E0' AND work_date=%s
                """,
                (COMPANY, raw_day),
            )
            projection = dict(cur.fetchone())
            check(
                "raw punch is not authority",
                projection["status"] == "present"
                and projection["raw_punch_only"] is False
                and projection["source_authority"] == "attendance_day_projection",
                projection,
            )

            attendance_rows = [
                ("E1", today - timedelta(days=11), "late", 10, 5, MANAGER),
                ("E1", today - timedelta(days=10), "late", 20, 0, MANAGER),
                ("E2", today - timedelta(days=9), "absent", 0, 0, "M2"),
                ("E3", today - timedelta(days=8), "approved_leave", 0, 0, "M2"),
                ("E4", today - timedelta(days=7), "present", 0, 0, "M2"),
                ("E5", today - timedelta(days=6), "completed", 0, 0, "M2"),
            ]
            for employee, work_day, status, late, early, manager_key in attendance_rows:
                c4.upsert_attendance_day(
                    cur, company_code=COMPANY, actor_phone=HR, employee_key=employee,
                    work_date=work_day, status=status, reason="attendance seed",
                    late_minutes=late, early_leave_minutes=early,
                    expected_work=True, scheduled=True, manager_employee_key=manager_key,
                    source_authority="attendance_day_projection",
                )
            correction_day = today - timedelta(days=5)
            c4.upsert_attendance_day(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E6",
                work_date=correction_day, status="absent", reason="pre-correction",
                expected_work=True, scheduled=True, source_authority="attendance_day_projection",
            )
            corrected = c4.apply_attendance_correction(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E6",
                work_date=correction_day, status="present", reason="approved correction"
            )
            check(
                "correction reconciles without audit rewrite",
                corrected.get("ok") is True
                and corrected.get("domain_audit_rewritten") is False
                and corrected["attendance_day"]["correction_applied"] is True,
                corrected,
            )

            attendance = evaluate(c4.ATTENDANCE_RATE_KEY)
            check(
                "attendance uses expected work",
                attendance.get("status") == "ok"
                and float(attendance.get("denominator_value") or 0) == 8.0
                and abs(float(attendance.get("value") or 0) - 75.0) < 0.001,
                attendance,
            )
            check(
                "attendance ignores raw punches",
                (attendance.get("explain") or {}).get("raw_punch_rows_ignored") is True,
                attendance,
            )
            absenteeism = evaluate(c4.ABSENTEEISM_RATE_KEY)
            check(
                "approved leave not absenteeism",
                absenteeism.get("status") == "ok"
                and float(absenteeism.get("numerator_value") or 0) == 1.0
                and (absenteeism.get("explain") or {}).get("approved_leave_excluded") is True,
                absenteeism,
            )
            late_employees = evaluate(c4.LATENESS_EMPLOYEES_KEY)
            late_occurrences = evaluate(c4.LATENESS_OCCURRENCES_KEY)
            late_minutes = evaluate(c4.LATENESS_MINUTES_KEY)
            check(
                "lateness measures are distinct",
                float(late_employees.get("value") or 0) == 1.0
                and float(late_occurrences.get("value") or 0) == 2.0
                and float(late_minutes.get("value") or 0) == 30.0,
                (late_employees, late_occurrences, late_minutes),
            )
            early = evaluate(c4.EARLY_LEAVE_OCCURRENCES_KEY)
            check("early leave occurrences", float(early.get("value") or 0) == 1.0, early)

            c4.upsert_attendance_day(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E7",
                work_date=today - timedelta(days=4), status="incomplete",
                reason="missing punch", expected_work=False, scheduled=True,
                exception_state="missing_out_punch",
            )
            missing = evaluate(c4.MISSING_PUNCHES_KEY)
            check("missing punches", float(missing.get("value") or 0) == 1.0, missing)

            manager_time = evaluate(
                c4.ATTENDANCE_RATE_KEY, actor_role="manager",
                filters={"manager_scope_keys": [MANAGER]}
            )
            check(
                "manager time allowed and scoped",
                manager_time.get("status") == "ok"
                and float(manager_time.get("denominator_value") or 0) == 2.0,
                manager_time,
            )

            # Leave ledger math: 5 consumed - 1 reversal; rejected 10 excluded.
            c4.upsert_leave_ledger_entry(
                cur, company_code=COMPANY, actor_phone=HR, entry_id="L1",
                employee_key="E1", leave_type="annual", entry_kind="consume",
                days=5, effective_date=today - timedelta(days=20),
                request_status="approved", reason="leave consume",
            )
            c4.upsert_leave_ledger_entry(
                cur, company_code=COMPANY, actor_phone=HR, entry_id="L2",
                employee_key="E1", leave_type="annual", entry_kind="reversal",
                days=1, effective_date=today - timedelta(days=19),
                request_status="approved", reason="leave reversal",
            )
            c4.upsert_leave_ledger_entry(
                cur, company_code=COMPANY, actor_phone=HR, entry_id="L3",
                employee_key="E1", leave_type="annual", entry_kind="consume",
                days=10, effective_date=today - timedelta(days=18),
                request_status="rejected", reason="rejected leave",
            )
            c4.upsert_leave_entitlement(
                cur, company_code=COMPANY, actor_phone=HR, employee_key="E1",
                leave_type="annual", period_year=today.year,
                entitlement_days=20, reason="annual entitlement",
            )
            leave_days = evaluate(c4.LEAVE_TAKEN_DAYS_KEY, filters={"leave_type": "annual"})
            leave_rate = evaluate(c4.LEAVE_UTILIZATION_RATE_KEY, filters={"leave_type": "annual"})
            check(
                "leave ledger rejected excluded",
                float(leave_days.get("value") or 0) == 4.0
                and float(leave_rate.get("numerator_value") or 0) == 4.0,
                (leave_days, leave_rate),
            )
            check(
                "leave utilization entitlement",
                leave_rate.get("status") == "ok"
                and float(leave_rate.get("denominator_value") or 0) == 20.0
                and abs(float(leave_rate.get("value") or 0) - 20.0) < 0.001,
                leave_rate,
            )

            c4.upsert_shift_assignment(
                cur, company_code=COMPANY, actor_phone=HR, assignment_key="S1",
                employee_key="E1", work_date=today - timedelta(days=3),
                scheduled_hours=8, status="scheduled", reason="shift seed",
                manager_employee_key=MANAGER,
            )
            shifts = evaluate(c4.SHIFTS_SCHEDULED_HOURS_KEY)
            check("shifts optional enabled path", float(shifts.get("value") or 0) == 8.0, shifts)
            c4.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR, reason="shifts optional off",
                shifts_module_enabled=False,
            )
            shifts_off = evaluate(c4.SHIFTS_SCHEDULED_HOURS_KEY)
            check(
                "shifts optional off unavailable",
                shifts_off.get("status") == "unavailable" and shifts_off.get("value") is None,
                shifts_off,
            )
            c4.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR, reason="restore shifts",
                shifts_module_enabled=True,
            )

            # OT state separation.
            for key, employee, status, paid in (
                ("OT1", "E1", "approved", False),
                ("OT4", "E4", "approved", False),
                ("OT5", "E5", "approved", False),
                ("OT2", "E2", "payroll_exported", False),
                ("OT3", "E3", "payroll_exported", True),
            ):
                c4.upsert_ot_request(
                    cur, company_code=COMPANY, actor_phone=HR, ot_key=key,
                    employee_key=employee, status=status, hours=2,
                    ot_date=today - timedelta(days=2), paid_in_payroll=paid,
                    reason="ot seed",
                )
            ot_approved = evaluate(c4.OT_APPROVED_KEY)
            ot_exported = evaluate(c4.OT_PAYROLL_EXPORTED_KEY)
            ot_paid_before_seal = evaluate(c4.OT_PAID_KEY)
            check(
                "approved OT differs from export and paid",
                float(ot_approved.get("value") or 0) == 3.0
                and float(ot_exported.get("value") or 0) == 2.0
                and float(ot_paid_before_seal.get("value") or 0) == 0.0,
                (ot_approved, ot_exported, ot_paid_before_seal),
            )
            check("OT not paid without sealed proof", float(ot_paid_before_seal.get("value") or 0) == 0.0, ot_paid_before_seal)

            prior_start, prior_end = today - timedelta(days=59), today - timedelta(days=31)
            current_start, current_end = today - timedelta(days=30), today
            c4.upsert_payroll_period(
                cur, company_code=COMPANY, actor_phone=HR, period_key="P2",
                period_start=current_start, period_end=current_end,
                authoritative_finalized=False, money_authority="wathefni",
                status="draft", totals_gross=600, totals_net=540,
                reason="draft payroll",
            )
            blocked_cost = evaluate(c4.PAYROLL_WORKFORCE_COST_KEY)
            check(
                "payroll money blocked before finalize",
                blocked_cost.get("status") == "unavailable" and blocked_cost.get("value") is None,
                blocked_cost,
            )

            # Five employees in both periods satisfy the C1 payroll-money cohort.
            for period, amount in (("P1", 100), ("P2", 120)):
                for index in range(1, 6):
                    c4.upsert_payroll_line(
                        cur, company_code=COMPANY, actor_phone=HR, period_key=period,
                        line_key=f"{period}-B{index}", employee_key=f"E{index}",
                        component_key="BASIC", component_class="earning",
                        display_label="Basic salary" if period == "P1" else "Base salary renamed",
                        amount=amount, currency="KWD", reason="payroll line",
                    )
            c4.upsert_payroll_line(
                cur, company_code=COMPANY, actor_phone=HR, period_key="P2",
                line_key="P2-OT3", employee_key="E3", component_key="OT_APPROVED",
                component_class="ot", display_label="Paid overtime",
                amount=10, currency="KWD", reason="sealed OT component",
            )
            c4.upsert_payroll_period(
                cur, company_code=COMPANY, actor_phone=HR, period_key="P1",
                period_start=prior_start, period_end=prior_end,
                authoritative_finalized=True, money_authority="wathefni",
                status="finalized", totals_gross=500, totals_net=450,
                sealed_at=datetime.now(timezone.utc), watermark="seal-p1",
                reason="seal prior",
            )
            c4.upsert_payroll_period(
                cur, company_code=COMPANY, actor_phone=HR, period_key="P2",
                period_start=current_start, period_end=current_end,
                authoritative_finalized=True, money_authority="wathefni",
                status="finalized", totals_gross=600, totals_net=540,
                sealed_at=datetime.now(timezone.utc), watermark="seal-p2",
                reason="seal current",
            )

            cost = evaluate(c4.PAYROLL_WORKFORCE_COST_KEY)
            movement = evaluate(c4.PAYROLL_MOVEMENT_KEY)
            components = evaluate(
                c4.PAYROLL_COMPONENT_MOVEMENT_KEY,
                filters={"component_key": "BASIC"},
            )
            check(
                "sealed payroll produces cost",
                cost.get("status") == "ok"
                and float(cost.get("value") or 0) == 600.0
                and (cost.get("explain") or {}).get("currency") == "KWD",
                cost,
            )
            check(
                "sealed period movement",
                movement.get("status") == "ok"
                and float(movement.get("value") or 0) == 100.0
                and (movement.get("explain") or {}).get("sealed_periods_only") is True,
                movement,
            )
            check(
                "stable component drill",
                components.get("status") == "ok"
                and float(components.get("value") or 0) == 100.0
                and (components.get("explain") or {}).get("stable_grouping_identity") == "component_key"
                and (components.get("explain") or {}).get("display_label_drives_grouping") is False,
                components,
            )
            paid_ot = evaluate(c4.OT_PAID_KEY)
            check(
                "OT paid only with sealed component",
                float(paid_ot.get("value") or 0) == 1.0
                and paid_ot.get("population_ids") == ["OT3"],
                paid_ot,
            )

            c4.upsert_settlement(
                cur, company_code=COMPANY, actor_phone=HR, settlement_key="SET1",
                status="finalized", amount=250, currency="KWD", paid=False,
                effective_date=today, employee_key="E1", reason="finalized not paid",
            )
            settlement = evaluate(c4.SETTLEMENT_FINALIZED_KEY)
            check(
                "settlement finalized is not paid",
                float(settlement.get("value") or 0) == 1.0
                and (settlement.get("explain") or {}).get("paid_count") == 0
                and (settlement.get("explain") or {}).get("finalized_does_not_mean_paid") is True,
                settlement,
            )
            c4.upsert_payment_file(
                cur, company_code=COMPANY, actor_phone=HR, file_key="PAYFILE1",
                status="acknowledged", effective_date=today, reason="bank ack",
            )
            payment_ack = evaluate(c4.PAYMENT_ACK_KEY)
            check(
                "payment acknowledgement is not paid",
                float(payment_ack.get("value") or 0) == 1.0
                and (payment_ack.get("explain") or {}).get("acknowledged_does_not_mean_paid") is True,
                payment_ack,
            )

            payroll_manager = evaluate(
                c4.PAYROLL_WORKFORCE_COST_KEY, actor_role="manager",
                filters={"manager_scope_keys": [MANAGER], "has_payroll_permission": False},
            )
            check("manager payroll forbidden", payroll_manager.get("status") == "forbidden", payroll_manager)

            # Payroll remains available when unrelated modules are off.
            c4.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR, reason="time modules off",
                attendance_module_enabled=False, leave_module_enabled=False,
                shifts_module_enabled=False, payroll_module_enabled=True,
            )
            payroll_independent = evaluate(c4.PAYROLL_WORKFORCE_COST_KEY)
            attendance_off = evaluate(c4.ATTENDANCE_RATE_KEY)
            leave_off = evaluate(c4.LEAVE_TAKEN_DAYS_KEY)
            check("payroll independent of time modules", payroll_independent.get("status") == "ok", payroll_independent)
            check(
                "module off unavailable not zero",
                attendance_off.get("status") == "unavailable"
                and attendance_off.get("value") is None
                and leave_off.get("status") == "unavailable"
                and leave_off.get("value") is None,
                (attendance_off, leave_off),
            )
            c4.set_module_flags(
                cur, company_code=COMPANY, actor_phone=HR, reason="restore modules",
                attendance_module_enabled=True, leave_module_enabled=True,
                shifts_module_enabled=True,
            )

            reconciliation = c4.reconcile_populations(
                cur, company_code=COMPANY, period_start=start, period_end=today
            )
            check(
                "population reconciliation explains differences",
                reconciliation.get("ok") is True
                and "scheduled" in reconciliation.get("populations", {})
                and "payroll" in reconciliation.get("populations", {})
                and bool((reconciliation.get("explain") or {}).get("differences_expected")),
                reconciliation,
            )

            first_rebuild = c4.rebuild_time_pay_facts(
                cur, company_code=COMPANY, actor_phone=HR, reason="rebuild one"
            )
            second_rebuild = c4.rebuild_time_pay_facts(
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
                SELECT name_en, name_ar, time_semantics, permission_class
                  FROM hr_kpi_definitions
                 WHERE semantic_key=%s
                 ORDER BY effective_version DESC LIMIT 1
                """,
                (c4.ATTENDANCE_RATE_KEY,),
            )
            bilingual = dict(cur.fetchone())
            check(
                "bilingual governed definition",
                bool(bilingual.get("name_en")) and bool(bilingual.get("name_ar"))
                and bilingual.get("time_semantics") in c1.TIME_SEMANTICS
                and bilingual.get("permission_class") == "time_leave",
                bilingual,
            )
            cur.execute(
                """
                SELECT permission_class FROM hr_kpi_definitions
                 WHERE semantic_key=%s ORDER BY effective_version DESC LIMIT 1
                """,
                (c4.PAYROLL_WORKFORCE_COST_KEY,),
            )
            check("payroll money permission class", dict(cur.fetchone()).get("permission_class") == "payroll_money")

            # Additional companies prove missing expected work, zero entitlement,
            # and payroll-money suppression below C1 min_cohort_n.
            allowed = f"{COMPANY},{EMPTY},{SMALL}"
            _flags(companies=allowed)
            for code in (EMPTY, SMALL):
                result = c4.enable_company_time_pay_intelligence(
                    cur, company_code=code, actor_phone=HR, reason=f"enable {code}"
                )
                check(f"enable {code}", result.get("ok") is True, result)
                result = c4.publish_time_pay_kpis_for_company(
                    cur, company_code=code, actor_phone=HR, reason=f"publish {code}"
                )
                check(f"publish {code}", result.get("ok") is True, result)

            no_expected = c1.evaluate_kpi(
                cur, company_code=EMPTY, actor_phone=HR,
                semantic_key=c4.ATTENDANCE_RATE_KEY, time_window=window,
            )
            check(
                "attendance without expected work insufficient",
                no_expected.get("status") == "insufficient_data"
                and no_expected.get("value") is None
                and (no_expected.get("explain") or {}).get("headcount_denominator_forbidden") is True,
                no_expected,
            )
            c4.upsert_leave_entitlement(
                cur, company_code=EMPTY, actor_phone=HR, employee_key="E0",
                leave_type="annual", period_year=today.year,
                entitlement_days=0, reason="zero entitlement",
            )
            zero_entitlement = c1.evaluate_kpi(
                cur, company_code=EMPTY, actor_phone=HR,
                semantic_key=c4.LEAVE_UTILIZATION_RATE_KEY, time_window=window,
                filters={"leave_type": "annual"},
            )
            check(
                "zero entitlement not applicable",
                zero_entitlement.get("status") == "not_applicable"
                and zero_entitlement.get("value") is None,
                zero_entitlement,
            )

            c4.upsert_payroll_period(
                cur, company_code=SMALL, actor_phone=HR, period_key="SP1",
                period_start=current_start, period_end=current_end,
                authoritative_finalized=True, money_authority="wathefni",
                status="finalized", totals_gross=100, totals_net=90,
                sealed_at=datetime.now(timezone.utc), watermark="small-seal",
                reason="small payroll",
            )
            c4.upsert_payroll_line(
                cur, company_code=SMALL, actor_phone=HR, period_key="SP1",
                line_key="SP1-L1", employee_key="ONLY1", component_key="BASIC",
                component_class="earning", amount=100, reason="small payroll line",
            )
            suppressed = c1.evaluate_kpi(
                cur, company_code=SMALL, actor_phone=HR,
                semantic_key=c4.PAYROLL_WORKFORCE_COST_KEY, time_window=window,
            )
            check(
                "small monetary cohort suppressed",
                suppressed.get("status") == "suppressed"
                and suppressed.get("value") is None
                and suppressed.get("permission_class") == "payroll_money",
                suppressed,
            )

            _flags(companies=COMPANY)
            tenant_write = c4.upsert_attendance_day(
                cur, company_code=OTHER, actor_phone=HR, employee_key="LEAK",
                work_date=today, status="present", expected_work=True,
                reason="must fail tenant gate",
            )
            check("tenant write isolation", tenant_write.get("ok") is not True, tenant_write)

            disabled = c4.disable_company_time_pay_intelligence(
                cur, company_code=COMPANY, actor_phone=HR, reason="disable prove"
            )
            check("disable preserves history", disabled.get("preserves_history") is True, disabled)
            cur.execute(
                "SELECT count(*) AS n FROM hr_intelligence_payroll_lines WHERE company_code=%s",
                (COMPANY,),
            )
            check("disable retains payroll projections", int(dict(cur.fetchone())["n"]) >= 11)
            blocked_after_disable = c1.evaluate_kpi(
                cur, company_code=COMPANY, actor_phone=HR,
                semantic_key=c4.PAYROLL_WORKFORCE_COST_KEY, time_window=window,
            )
            check(
                "disabled evaluation unavailable",
                blocked_after_disable.get("status") == "unavailable",
                blocked_after_disable,
            )

            _flags(c4_on="off", companies="")
            check("all c4 gates off", c4.runtime_gate_for_company(COMPANY).get("ok") is not True)
            conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print(c4.PASS_STAMP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

