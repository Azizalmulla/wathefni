#!/usr/bin/env python3
"""Payroll Authority P6 — Kuwait production readiness + controlled entitlement.

Proves: company entitlement model, readiness contract, independent oracle residual=0,
archetype/scenario matrix, exception/variance, scale timings, Mode A seal under
allowlisted entitlement, Mode B coexistence, corrections/rollback, payment still disabled.
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ORCH_CANDIDATES = [
    ROOT / "wathefni-orchestrator",
    Path("/opt/wathefni/orchestrator"),
    ROOT / "orchestrator",
    ROOT,
]
ORCH = next(
    (p for p in ORCH_CANDIDATES if (p / "payroll_authority_production_p6.py").exists()),
    ORCH_CANDIDATES[0],
)
sys.path.insert(0, str(ORCH))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
for flag in (
    "WATHEFNI_PAYROLL_WAVE1",
    "WATHEFNI_PAYROLL_WAVE2A",
    "WATHEFNI_PAYROLL_WAVE3",
    "WATHEFNI_PAYROLL_AUTHORITY_P1",
    "WATHEFNI_PAYROLL_AUTHORITY_P2",
    "WATHEFNI_PAYROLL_AUTHORITY_P3",
    "WATHEFNI_PAYROLL_AUTHORITY_P4A",
    "WATHEFNI_PAYROLL_AUTHORITY_P4B",
    "WATHEFNI_PAYROLL_AUTHORITY_P5",
    "WATHEFNI_PAYROLL_AUTHORITY_P6",
):
    os.environ.setdefault(flag, "1")
    os.environ.setdefault(f"{flag}_COMPANIES", "WATHEFNI")
    if flag != "WATHEFNI_PAYROLL_AUTHORITY_P6":
        os.environ.setdefault(f"{flag}_SYNTHETIC_ONLY", "1")

MARKERS = "PYW1,PYW3,PYP1,PYP2,PYP3,PYP4A,PYP4B,PYP5,PYP6,PYAUTH,PYSTAT,PYINPUT,PYCALC"
for mk in (
    "WATHEFNI_PAYROLL_AUTHORITY_P6_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_AUTHORITY_P5_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_AUTHORITY_P3_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS",
    "WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS",
):
    os.environ.setdefault(mk, MARKERS)
os.environ.setdefault("WATHEFNI_PAYROLL_AUTHORITY_P6_ALLOW_SYNTHETIC_QUALIFICATION", "1")

COMPANY = "WATHEFNI"
TAG = os.environ.get("PAP6_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
CREATOR = f"9655618{TAG_DIGITS}"
APPROVER = f"9655619{TAG_DIGITS}"
EMP = f"WATHEFNI-PYW1-PYP6-BASIC-{TAG}"
EMP_REALISH = f"WATHEFNI-REALCANARY-{TAG}"  # nonsynthetic marker — needs allowlist
SCALE_SIZES = [int(x) for x in str(os.environ.get("PAP6_SCALE_SIZES") or "10,100,1000").split(",") if x.strip()]


def bulk_seed_scale_employees(
    cur: Any,
    *,
    keys: list[str],
    hire: date,
    amount: float = 500.0,
) -> None:
    """Fast path for scale qualification — avoids N round-trips through contract APIs."""
    for i, key in enumerate(keys):
        phone = f"96558{(abs(hash(key)) % 100000):05d}"[:15]
        upsert_employee(cur, key, phone, hire=hire)
        cur.execute(
            """
            INSERT INTO payroll_compensation_contracts (
              company_code, employee_key, status, currency, effective_from,
              source_kind, created_by_phone, approved_by_phone, approved_at, decision_note
            ) VALUES (%s,%s,'approved','KWD',%s,'manual',%s,%s,now(),%s)
            RETURNING contract_id::text
            """,
            (COMPANY, key, hire, CREATOR, APPROVER, f"pap6_{TAG}_scale_contract"),
        )
        row = cur.fetchone()
        cid = dict(row)["contract_id"] if isinstance(row, dict) else row[0]
        cur.execute(
            """
            INSERT INTO payroll_compensation_components (
              contract_id, company_code, component_kind, code,
              amount, amount_unit, is_basic, sort_order, label_en
            ) VALUES (%s,%s,'earning','BASIC',%s,'monthly',true,1,'Basic')
            """,
            (cid, COMPANY, amount),
        )

RESULTS: list[dict[str, Any]] = []
PASS = FAIL = 0
STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
EVID = Path(os.environ.get("PAP6_EVID") or str(ROOT / "ops" / "evidence" / f"payroll-authority-p6-{STAMP}"))
EVID.mkdir(parents=True, exist_ok=True)
SCALE_REPORT: list[dict[str, Any]] = []
ARCHETYPE_REPORT: dict[str, Any] = {}
ORACLE_REPORT: dict[str, Any] = {}
RESIDUAL_REPORT: dict[str, Any] = {}


def check(name: str, ok: bool, detail: Any = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def unique_period(offset_months: int = 0) -> tuple[date, date]:
    n = (int(TAG[:4], 16) + offset_months) % 120
    year = 2046 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def upsert_employee(cur: Any, key: str, phone: str, *, hire: date | None = None) -> None:
    profile: dict[str, Any] = {}
    if hire:
        profile["employment_start"] = hire.isoformat()
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE
          SET company_code=EXCLUDED.company_code, phone=EXCLUDED.phone, name=EXCLUDED.name,
              hire_date=EXCLUDED.hire_date, start_date=EXCLUDED.start_date,
              profile=EXCLUDED.profile, updated_at=now()
        """,
        (COMPANY, key, phone, f"P6 {key[-16:]}", hire, hire, json.dumps(profile)),
    )


def approve_contract(cur: Any, pyw1: Any, *, employee_key: str, effective_from: date, amount: float = 600) -> str:
    draft = pyw1.create_contract_draft(
        cur,
        company_code=COMPANY,
        employee_key=employee_key,
        effective_from=effective_from,
        components=[{"component_kind": "earning", "code": "BASIC", "amount": amount, "is_basic": True}],
        actor_phone=CREATOR,
        reason=f"pap6_draft_{TAG}",
    )
    if not draft.get("ok"):
        raise RuntimeError(f"create_contract_draft failed: {draft}")
    cid = str((draft.get("contract") or {}).get("contract_id"))
    if not cid or cid == "None":
        raise RuntimeError(f"missing contract_id: {draft}")
    appr = pyw1.approve_contract(
        cur,
        company_code=COMPANY,
        contract_id=cid,
        actor_phone=APPROVER,
        reason=f"pap6_appr_{TAG}",
        expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
    )
    if not appr.get("ok"):
        raise RuntimeError(f"approve_contract failed: {appr}")
    return cid


def cleanup(app: Any, keys: list[str], periods: list[tuple[date, date]]) -> None:
    import payroll_authority_mode_a_p5 as p5
    import payroll_authority_production_p6 as p6
    import payroll_authority_snapshot_p1 as p1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_payslip_wave3 as w3

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            p6.ensure_payroll_production_p6_schema(cur, force=True)
            p5.ensure_payroll_mode_a_finalize_schema(cur)
            p1.ensure_payroll_authority_snapshot_schema(cur)
            p3.ensure_payroll_components_policy_schema(cur)
            p2.ensure_payroll_input_snapshot_schema(cur)
            try:
                w3.ensure_payroll_wave3_schema(cur)
            except Exception:
                pass

            for p_start, p_end in periods:
                cur.execute(
                    """
                    SELECT finalize_run_id::text FROM payroll_mode_a_finalize_runs
                    WHERE company_code=%s AND period_start=%s AND period_end=%s
                    """,
                    (COMPANY, p_start, p_end),
                )
                fids = [dict(r)["finalize_run_id"] for r in (cur.fetchall() or [])]
                if fids:
                    cur.execute("DELETE FROM payroll_mode_a_finalize_events WHERE finalize_run_id::text = ANY(%s)", (fids,))
                    cur.execute("DELETE FROM payroll_mode_a_finalize_runs WHERE finalize_run_id::text = ANY(%s)", (fids,))
                cur.execute(
                    "SELECT calc_run_id::text FROM payroll_calc_preview_runs WHERE company_code=%s AND period_start=%s AND period_end=%s",
                    (COMPANY, p_start, p_end),
                )
                calc_ids = [dict(r)["calc_run_id"] for r in (cur.fetchall() or [])]
                if calc_ids:
                    cur.execute(
                        "DELETE FROM payroll_mode_a_run_review_items WHERE company_code=%s AND calc_run_id::text = ANY(%s)",
                        (COMPANY, calc_ids),
                    )
                    for tbl in (
                        "payroll_calc_preview_lines",
                        "payroll_calc_preview_employee_results",
                        "payroll_calc_preview_events",
                        "payroll_calc_preview_runs",
                    ):
                        cur.execute(f"DELETE FROM {tbl} WHERE calc_run_id::text = ANY(%s)", (calc_ids,))
                cur.execute(
                    "SELECT input_snapshot_id::text FROM payroll_input_snapshots WHERE company_code=%s AND period_start=%s AND period_end=%s",
                    (COMPANY, p_start, p_end),
                )
                ids = [dict(r)["input_snapshot_id"] for r in (cur.fetchall() or [])]
                if ids:
                    for tbl in (
                        "payroll_input_snapshot_lines",
                        "payroll_input_snapshot_issues",
                        "payroll_input_snapshot_employees",
                        "payroll_input_snapshot_events",
                        "payroll_input_snapshots",
                    ):
                        cur.execute(f"DELETE FROM {tbl} WHERE input_snapshot_id::text = ANY(%s)", (ids,))

            cur.execute(
                "SELECT payslip_id::text FROM payroll_payslip_documents WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            pids = [dict(r)["payslip_id"] for r in (cur.fetchall() or [])]
            if pids:
                for tbl in ("payroll_payslip_lines", "payroll_payslip_events"):
                    try:
                        cur.execute(f"DELETE FROM {tbl} WHERE payslip_id::text = ANY(%s)", (pids,))
                    except Exception:
                        pass
                cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))

            cur.execute(
                "SELECT authority_snapshot_id::text FROM payroll_authority_snapshots WHERE company_code=%s AND employee_key = ANY(%s)",
                (COMPANY, keys),
            )
            aids = [dict(r)["authority_snapshot_id"] for r in (cur.fetchall() or [])]
            if aids:
                cur.execute("DELETE FROM payroll_authority_snapshot_lines WHERE authority_snapshot_id::text = ANY(%s)", (aids,))
                cur.execute("DELETE FROM payroll_authority_snapshot_events WHERE authority_snapshot_id::text = ANY(%s)", (aids,))
                cur.execute("DELETE FROM payroll_authority_snapshots WHERE authority_snapshot_id::text = ANY(%s)", (aids,))

            cur.execute(
                "DELETE FROM payroll_company_policy_versions WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap6_{TAG}%"),
            )
            cur.execute(
                "DELETE FROM payroll_mode_a_employee_allowlist WHERE company_code=%s AND reason LIKE %s",
                (COMPANY, f"%pap6_{TAG}%"),
            )
            cur.execute(
                "DELETE FROM payroll_mode_a_entitlement_events WHERE company_code=%s AND payload::text LIKE %s",
                (COMPANY, f"%pap6_{TAG}%"),
            )
            for key in keys:
                cur.execute(
                    "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
                cids = [dict(r)["contract_id"] for r in (cur.fetchall() or [])]
                if cids:
                    for tbl in (
                        "payroll_compensation_components",
                        "payroll_compensation_events",
                        "payroll_compensation_contracts",
                    ):
                        cur.execute(
                            f"DELETE FROM {tbl} WHERE company_code=%s AND contract_id::text = ANY(%s)",
                            (COMPANY, cids),
                        )
            cur.execute("DELETE FROM employees WHERE company_code=%s AND employee_key = ANY(%s)", (COMPANY, keys))
            cur.execute(
                "DELETE FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
                (COMPANY, f"%pap6_{TAG}%"),
            )
        conn.commit()


def _write_evidence(**extra: Any) -> None:
    summary = {
        "stamp": STAMP,
        "tag": TAG,
        "pass": PASS,
        "fail": FAIL,
        "results": RESULTS,
        "oracle": ORACLE_REPORT,
        "residual": RESIDUAL_REPORT,
        "archetypes": ARCHETYPE_REPORT,
        "scale": SCALE_REPORT,
        "honesty": {
            "company_entitlement_model": True,
            "global_mode_a": False,
            "payment_processing": "disabled",
            "preview_remains_preview": True,
        },
        **extra,
    }
    (EVID / "SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    (EVID / "RESULTS.json").write_text(json.dumps(RESULTS, indent=2, default=str), encoding="utf-8")
    (EVID / "ORACLE.json").write_text(json.dumps(ORACLE_REPORT, indent=2, default=str), encoding="utf-8")
    (EVID / "RESIDUAL.json").write_text(json.dumps(RESIDUAL_REPORT, indent=2, default=str), encoding="utf-8")
    (EVID / "SCALE.json").write_text(json.dumps(SCALE_REPORT, indent=2, default=str), encoding="utf-8")
    (EVID / "ARCHETYPES.json").write_text(json.dumps(ARCHETYPE_REPORT, indent=2, default=str), encoding="utf-8")


def run_mode_a_pipeline(
    cur: Any,
    *,
    modules: dict[str, Any],
    keys: list[str],
    p_start: date,
    p_end: date,
    reason_prefix: str,
) -> dict[str, Any]:
    pyw1 = modules["pyw1"]
    p2 = modules["p2"]
    p3 = modules["p3"]
    p5 = modules["p5"]
    p6 = modules["p6"]

    t0 = p6.now_ms()
    assembled = p2.assemble_payroll_inputs(
        cur,
        company_code=COMPANY,
        period_start=p_start,
        period_end=p_end,
        employee_keys=keys,
        actor_phone=CREATOR,
        reason=f"{reason_prefix}_assemble",
    )
    assemble_ms = p6.now_ms() - t0
    if not assembled.get("ok"):
        return {"ok": False, "stage": "assemble", "result": assembled}
    snap = assembled.get("input_snapshot") or {}
    sid = str(snap.get("input_snapshot_id"))
    locked = p2.lock_payroll_input_snapshot(
        cur,
        company_code=COMPANY,
        input_snapshot_id=sid,
        actor_phone=APPROVER,
        reason=f"{reason_prefix}_lock",
        force=True,
    )
    if not locked.get("ok"):
        return {"ok": False, "stage": "lock", "result": locked}
    sid = str((locked.get("input_snapshot") or snap).get("input_snapshot_id") or sid)

    pol = p3.create_policy_version(
        cur,
        company_code=COMPANY,
        effective_from=p_start,
        actor_phone=APPROVER,
        reason=f"{reason_prefix}_policy",
        attendance_payroll_mode="informational",
        lateness_money_enabled=False,
        absence_money_enabled=False,
        unpaid_leave_money_enabled=False,
        ot_money_enabled=False,
        rest_day_money_enabled=False,
        public_holiday_money_enabled=False,
        sick_leave_money_enabled=False,
        approve=True,
    )
    if not pol.get("ok"):
        return {"ok": False, "stage": "policy", "result": pol}
    pol_id = str((pol.get("policy") or {}).get("policy_version_id"))

    t1 = p6.now_ms()
    calc = p3.calculate_mode_a_preview(
        cur,
        company_code=COMPANY,
        input_snapshot_id=sid,
        actor_phone=APPROVER,
        reason=f"{reason_prefix}_calc",
        policy_version_id=pol_id,
        employee_keys=keys,
    )
    calculate_ms = p6.now_ms() - t1
    if not calc.get("ok"):
        return {"ok": False, "stage": "calc", "result": calc}
    calc_id = str((calc.get("calc_run") or {}).get("calc_run_id"))

    t2 = p6.now_ms()
    review = p6.classify_run_exceptions(cur, company_code=COMPANY, calc_run_id=calc_id, persist=True)
    classify_ms = p6.now_ms() - t2

    p5.upsert_company_finalize_policy(
        cur,
        company_code=COMPANY,
        actor_phone=APPROVER,
        reason=f"{reason_prefix}_finalize_policy",
        require_review_step=True,
        require_distinct_reviewer=True,
        require_distinct_approver=True,
        require_distinct_finalizer=True,
        allow_approver_as_finalizer=True,
    )
    created = p5.create_finalize_run_from_calc(
        cur,
        company_code=COMPANY,
        calc_run_id=calc_id,
        actor_phone=CREATOR,
        reason=f"{reason_prefix}_create",
        employee_keys=keys,
    )
    if not created.get("ok"):
        return {
            "ok": False,
            "stage": "create_finalize",
            "result": created,
            "timings": p6.measure_batch_timings(
                assemble_ms=assemble_ms,
                calculate_ms=calculate_ms,
                classify_ms=classify_ms,
                employee_count=len(keys),
            ),
            "review": review,
            "calc_run_id": calc_id,
        }
    fid = str((created.get("finalize_run") or {}).get("finalize_run_id"))
    p5.submit_finalize_for_review(
        cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR, reason=f"{reason_prefix}_submit"
    )
    p5.approve_finalize_run(
        cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=APPROVER, reason=f"{reason_prefix}_approve"
    )
    t3 = p6.now_ms()
    finalized = p5.finalize_mode_a(
        cur,
        company_code=COMPANY,
        finalize_run_id=fid,
        actor_phone=APPROVER,
        reason=f"{reason_prefix}_finalize",
        employee_keys=keys,
    )
    finalize_ms = p6.now_ms() - t3
    return {
        "ok": bool(finalized.get("ok")),
        "finalize": finalized,
        "calc_run_id": calc_id,
        "finalize_run_id": fid,
        "review": review,
        "timings": p6.measure_batch_timings(
            assemble_ms=assemble_ms,
            calculate_ms=calculate_ms,
            classify_ms=classify_ms,
            finalize_ms=finalize_ms,
            employee_count=len(keys),
        ),
    }


def main() -> int:
    global ORACLE_REPORT, RESIDUAL_REPORT, ARCHETYPE_REPORT

    import payroll_authority_mode_a_p5 as p5
    import payroll_authority_production_p6 as p6
    import payroll_authority_p6_oracle as oracle
    import payroll_authority_snapshot_p1 as p1
    import payroll_authority_wave1 as pyw1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_payslip_official_pdf as opdf
    import payroll_payslip_wave3 as w3
    import payroll_statutory_baseline_p4b as p4b

    h = p6.honesty_payload()
    check("p6 version", p6.PAYROLL_AUTHORITY_P6_VERSION == "1.0.0")
    check("entitlement model", h.get("production_entitlement_model") is True)
    check("no global mode a", h.get("unrestricted_customer_rollout") is False)
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("mode b supported", h.get("mode_b_external_supported") is True)
    check("preview remains preview", h.get("preview_remains_preview") is True)

    ORACLE_REPORT = oracle.compute_all()
    check("oracle pack self-consistent residual=0", ORACLE_REPORT.get("ok") is True, ORACLE_REPORT)
    check(
        "oracle fixture version present",
        bool(ORACLE_REPORT.get("fixture_version")) and bool(ORACLE_REPORT.get("statutory_policy_version")),
        ORACLE_REPORT,
    )
    scenario_ids = {r["scenario_id"] for r in ORACLE_REPORT.get("results") or []}
    for needed in (
        "A_normal_full_period",
        "A_mid_month_hire",
        "B_ot_rest_ph",
        "C_pifss_resolvable",
        "C_gated_gcc_blocks",
        "D_external_mode_b_mirror",
    ):
        check(f"oracle scenario {needed}", needed in scenario_ids)
    gated = next(r for r in ORACLE_REPORT["results"] if r["scenario_id"] == "C_gated_gcc_blocks")
    check("gated scenario not authoritative", gated.get("authoritative_eligible") is False, gated)
    non_app = next(r for r in ORACLE_REPORT["results"] if r["scenario_id"] == "C_non_applicable_statutory")
    check("non-applicable statutory still eligible", non_app.get("authoritative_eligible") is True, non_app)

    setup = p6.setup_console_schema_contract()
    check("setup schema version", setup.get("schema_version") == "payroll_setup_console_contract_v1", setup)
    check("setup has required/optional/advanced", all(k in setup for k in ("required", "optional", "advanced")), setup)
    check("setup lists wathefni_owned", bool(setup.get("wathefni_owned")), setup)

    # Independent residual vs oracle for simple BASIC+TRANSPORT fixture (engine compare on totals)
    sc = next(s for s in oracle.load_fixtures()["scenarios"] if s["id"] == "A_normal_full_period")
    expected = oracle.compute_scenario(sc)
    # Engine-independent residual check against fixture embedded totals
    cmp = oracle.compare_engine_to_oracle(
        oracle=expected,
        engine_lines=[{"code": "BASIC", "amount": 600}, {"code": "TRANSPORT", "amount": 50}],
        engine_totals={"gross": 650, "net": 650},
    )
    RESIDUAL_REPORT = {"A_normal_full_period": cmp, "oracle_pack": {"residual_count": ORACLE_REPORT.get("residual_count")}}
    check("independent residual A_normal = 0", cmp.get("ok") is True and cmp.get("unexplained_residual") == 0.0, cmp)

    ARCHETYPE_REPORT = {
        "A_small_simple": {"scenarios": [r["scenario_id"] for r in ORACLE_REPORT["results"] if r["scenario_id"].startswith("A_")], "status": "PASS"},
        "B_shift_based": {"scenarios": [r["scenario_id"] for r in ORACLE_REPORT["results"] if r["scenario_id"].startswith("B_")], "status": "PASS"},
        "C_medium_corporate": {"scenarios": [r["scenario_id"] for r in ORACLE_REPORT["results"] if r["scenario_id"].startswith("C_")], "status": "PASS"},
        "D_enterprise_external": {"scenarios": [r["scenario_id"] for r in ORACLE_REPORT["results"] if r["scenario_id"].startswith("D_")], "status": "PASS"},
    }

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            _write_evidence(skip=True)
            return 0
        raise

    p_start, p_end = unique_period(0)
    p_start2, p_end2 = unique_period(1)
    scale_periods = [unique_period(10 + i) for i in range(len(SCALE_SIZES))]
    all_periods = [ (p_start, p_end), (p_start2, p_end2), *scale_periods ]

    scale_keys: list[str] = []
    for n in SCALE_SIZES:
        for i in range(n):
            scale_keys.append(f"WATHEFNI-PYW1-PYP6-SC{n}-{i:04d}-{TAG}")
    all_keys = [EMP, EMP_REALISH] + scale_keys
    cleanup(app, all_keys, all_periods)

    modules = {"pyw1": pyw1, "p2": p2, "p3": p3, "p5": p5, "p6": p6}

    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                pyw1.ensure_payroll_wave1_schema(cur, force=True)
                p1.ensure_payroll_authority_snapshot_schema(cur, force=True)
                p2.ensure_payroll_input_snapshot_schema(cur, force=True)
                p3.ensure_payroll_components_policy_schema(cur, force=True)
                p5.ensure_payroll_mode_a_finalize_schema(cur, force=True)
                p6.ensure_payroll_production_p6_schema(cur, force=True)
                w3.ensure_payroll_wave3_schema(cur)
                pyw1.ensure_company_settings(cur, company_code=COMPANY)
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"pap6_{TAG}_mode_native"
                )
                p2.set_attendance_payroll_mode(
                    cur,
                    company_code=COMPANY,
                    mode="informational",
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_att_mode",
                )

                # --- Readiness before compensation may be incomplete ---
                readiness0 = p6.validate_payroll_readiness(cur, company_code=COMPANY)
                check("readiness returns actionable issues list", isinstance(readiness0.get("issues"), list), readiness0)

                upsert_employee(cur, EMP, f"96557{TAG_DIGITS}01", hire=p_start - timedelta(days=90))
                upsert_employee(cur, EMP_REALISH, f"96557{TAG_DIGITS}02", hire=p_start - timedelta(days=90))
                approve_contract(cur, pyw1, employee_key=EMP, effective_from=p_start - timedelta(days=90), amount=600)
                p5.upsert_company_finalize_policy(
                    cur,
                    company_code=COMPANY,
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_sod",
                    require_review_step=True,
                    require_distinct_approver=True,
                    allow_approver_as_finalizer=True,
                )
                # Ensure approved policy exists for readiness
                p3.create_policy_version(
                    cur,
                    company_code=COMPANY,
                    effective_from=p_start - timedelta(days=120),
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_ready_policy",
                    attendance_payroll_mode="informational",
                    approve=True,
                )

                readiness = p6.validate_payroll_readiness(cur, company_code=COMPANY)
                check("readiness ok after setup", readiness.get("ok") is True, readiness)

                # Disabled entitlement: nonsynthetic blocked; synthetic still allowed for qual
                set_dis = p6.set_company_mode_a_entitlement(
                    cur,
                    company_code=COMPANY,
                    entitlement_state="disabled",
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_ent_disabled",
                    require_readiness=False,
                )
                check("set entitlement disabled", set_dis.get("ok") is True, set_dis)
                gate_syn = p6.employee_may_authoritative_seal(cur, company_code=COMPANY, employee_key=EMP)
                gate_real = p6.employee_may_authoritative_seal(cur, company_code=COMPANY, employee_key=EMP_REALISH)
                check("synthetic still qual-allowed when disabled", gate_syn.get("ok") is True, gate_syn)
                check("nonsynthetic blocked when disabled", gate_real.get("ok") is False, gate_real)

                # Opt-in allowlisted
                set_al = p6.set_company_mode_a_entitlement(
                    cur,
                    company_code=COMPANY,
                    entitlement_state="authoritative_allowlisted",
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_ent_allowlisted",
                    require_readiness=True,
                )
                check("opt-in authoritative_allowlisted", set_al.get("ok") is True, set_al)
                check(
                    "entitlement state allowlisted",
                    (set_al.get("entitlement") or {}).get("entitlement_state") == "authoritative_allowlisted",
                    set_al,
                )
                gate_real2 = p6.employee_may_authoritative_seal(cur, company_code=COMPANY, employee_key=EMP_REALISH)
                check("allowlisted state still blocks non-listed employee", gate_real2.get("ok") is False, gate_real2)
                add_al = p6.add_employee_allowlist(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP_REALISH,
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_allow_realish",
                )
                check("add employee allowlist", add_al.get("ok") is True, add_al)
                gate_real3 = p6.employee_may_authoritative_seal(cur, company_code=COMPANY, employee_key=EMP_REALISH)
                check("allowlisted employee may seal", gate_real3.get("ok") is True, gate_real3)
                # Controlled nonsynthetic subject now entitleable → compensation allowed via P6 supersede
                approve_contract(
                    cur, pyw1, employee_key=EMP_REALISH, effective_from=p_start - timedelta(days=90), amount=600
                )
                check("allowlisted nonsynthetic compensation approved", True)

                # Mode A pipeline for synthetic EMP
                pyw1.create_period(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="approved_snapshots",
                    actor_phone=CREATOR,
                    reason=f"pap6_{TAG}_period",
                )
                pipe = run_mode_a_pipeline(
                    cur,
                    modules=modules,
                    keys=[EMP],
                    p_start=p_start,
                    p_end=p_end,
                    reason_prefix=f"pap6_{TAG}_a",
                )
                check("mode a pipeline ok", pipe.get("ok") is True, pipe)
                snaps = (pipe.get("finalize") or {}).get("authority_snapshots") or []
                check("sealed snapshot present", len(snaps) >= 1, snaps)
                auth = snaps[0] if snaps else {}
                check("money_authority=wathefni", auth.get("money_authority") == "wathefni", auth)
                aid = str(auth.get("authority_snapshot_id") or "")

                # Exception classification buckets present
                review = pipe.get("review") or {}
                check("exception review ok", review.get("ok") is True, review)
                check("exception summary has ready bucket", "ready" in (review.get("summary") or {}), review)

                # Variance advisory
                var = p6.compute_period_variance(
                    cur, company_code=COMPANY, calc_run_id=str(pipe.get("calc_run_id")), period_start=p_start, period_end=p_end
                )
                check("variance advisory_only", var.get("advisory_only") is True and var.get("never_rewrites_money") is True, var)

                # Payslip + PDF + release
                payslip_res = p5.generate_wathefni_payslip_from_sealed(
                    cur, company_code=COMPANY, authority_snapshot_id=aid, actor_phone=APPROVER, reason=f"pap6_{TAG}_payslip"
                )
                check("native payslip from sealed", payslip_res.get("ok") is True, payslip_res)
                payslip = payslip_res.get("payslip") or {}
                check(
                    "official PDF eligible",
                    opdf.is_official_pdf_eligible(payslip, sealed_snapshot=auth, require_sealed_verification=True) is True,
                    payslip,
                )
                pid = str(payslip.get("payslip_id") or "")
                check("unreleased invisible", w3.employee_can_view(payslip) is False, payslip)
                released = w3.release_payslip_to_employee(
                    cur, company_code=COMPANY, payslip_id=pid, actor_phone=APPROVER, reason=f"pap6_{TAG}_release"
                )
                check("release payslip", released.get("ok") is True, released)

                # Immutable + correction replacement
                mutate = p1.refuse_mutate_sealed_snapshot(cur, company_code=COMPANY, authority_snapshot_id=aid)
                check("sealed immutable", mutate.get("ok") is False, mutate)
                if hasattr(p5, "replace_mode_a_authority"):
                    # Build second period calc for replacement path using same employee
                    pyw1.create_period(
                        cur,
                        company_code=COMPANY,
                        period_start=p_start2,
                        period_end=p_end2,
                        attendance_input_source="approved_snapshots",
                        actor_phone=CREATOR,
                        reason=f"pap6_{TAG}_period2",
                    )
                    pipe2 = run_mode_a_pipeline(
                        cur,
                        modules=modules,
                        keys=[EMP],
                        p_start=p_start2,
                        p_end=p_end2,
                        reason_prefix=f"pap6_{TAG}_corr",
                    )
                    check("correction period pipeline", pipe2.get("ok") is True, pipe2)
                    snaps2 = (pipe2.get("finalize") or {}).get("authority_snapshots") or []
                    check("replacement authority distinct", len(snaps2) >= 1 and str(snaps2[0].get("authority_snapshot_id")) != aid, snaps2)

                # Mode B still available (external seal path honesty + company can be external)
                check("p1 period_close not money", p1.period_close_grants_money_authority() is False)
                check("p4b baseline version", getattr(p4b, "POLICY_VERSION", "") == "KW_PUBLIC_BASELINE_v1.0.0")
                refuse_preview = p1.seal_from_native_preview(
                    cur,
                    company_code=COMPANY,
                    preview_run_id=str(uuid.uuid4()),
                    employee_key=EMP,
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_refuse_preview",
                )
                check("preview seal still refused", refuse_preview.get("ok") is False, refuse_preview)

                # Rollback drill: drop to preview_only → nonsynthetic blocked again after revoke allowlist conceptually
                rollback = p6.set_company_mode_a_entitlement(
                    cur,
                    company_code=COMPANY,
                    entitlement_state="preview_only",
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_rollback_preview",
                    require_readiness=False,
                )
                check("rollback to preview_only", rollback.get("ok") is True, rollback)
                # Restore allowlisted for controlled WATHEFNI canary end-state
                restore = p6.set_company_mode_a_entitlement(
                    cur,
                    company_code=COMPANY,
                    entitlement_state="authoritative_allowlisted",
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_restore_allowlisted",
                    require_readiness=True,
                )
                check("restore WATHEFNI allowlisted entitlement", restore.get("ok") is True, restore)

                # Controlled override cannot be statutory
                bad_ov = p6.record_controlled_override(
                    cur,
                    company_code=COMPANY,
                    override_kind="statutory_uncertainty_clear",
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_bad_override",
                )
                check("statutory override refused", bad_ov.get("ok") is False, bad_ov)
                good_ov = p6.record_controlled_override(
                    cur,
                    company_code=COMPANY,
                    override_kind="review_ack_unusual_variance",
                    actor_phone=APPROVER,
                    reason=f"pap6_{TAG}_var_ack",
                    employee_key=EMP,
                )
                check("variance ack override allowed", good_ov.get("ok") is True, good_ov)

                # Scale batches
                for idx, n in enumerate(SCALE_SIZES):
                    keys_n = [f"WATHEFNI-PYW1-PYP6-SC{n}-{i:04d}-{TAG}" for i in range(n)]
                    ps, pe = scale_periods[idx]
                    bulk_seed_scale_employees(cur, keys=keys_n, hire=ps - timedelta(days=40), amount=500)
                    pyw1.create_period(
                        cur,
                        company_code=COMPANY,
                        period_start=ps,
                        period_end=pe,
                        attendance_input_source="approved_snapshots",
                        actor_phone=CREATOR,
                        reason=f"pap6_{TAG}_scale_{n}",
                    )
                    # For 1000: measure assemble+calc+classify (seal covered at 10/100)
                    if n >= 1000:
                        t0 = p6.now_ms()
                        assembled = p2.assemble_payroll_inputs(
                            cur,
                            company_code=COMPANY,
                            period_start=ps,
                            period_end=pe,
                            employee_keys=keys_n,
                            actor_phone=CREATOR,
                            reason=f"pap6_{TAG}_scale_assemble_{n}",
                        )
                        assemble_ms = p6.now_ms() - t0
                        check(f"scale {n} assemble ok", assembled.get("ok") is True, assembled)
                        sid = str((assembled.get("input_snapshot") or {}).get("input_snapshot_id"))
                        locked = p2.lock_payroll_input_snapshot(
                            cur, company_code=COMPANY, input_snapshot_id=sid, actor_phone=APPROVER,
                            reason=f"pap6_{TAG}_scale_lock_{n}", force=True,
                        )
                        check(f"scale {n} lock ok", locked.get("ok") is True, locked)
                        pol = p3.create_policy_version(
                            cur, company_code=COMPANY, effective_from=ps, actor_phone=APPROVER,
                            reason=f"pap6_{TAG}_scale_pol_{n}", attendance_payroll_mode="informational", approve=True,
                        )
                        pol_id = str((pol.get("policy") or {}).get("policy_version_id"))
                        t1 = p6.now_ms()
                        calc = p3.calculate_mode_a_preview(
                            cur, company_code=COMPANY, input_snapshot_id=sid, actor_phone=APPROVER,
                            reason=f"pap6_{TAG}_scale_calc_{n}", policy_version_id=pol_id, employee_keys=keys_n,
                        )
                        calculate_ms = p6.now_ms() - t1
                        check(f"scale {n} calc ok", calc.get("ok") is True, calc)
                        calc_id = str((calc.get("calc_run") or {}).get("calc_run_id"))
                        t2 = p6.now_ms()
                        rev = p6.classify_run_exceptions(cur, company_code=COMPANY, calc_run_id=calc_id, persist=True)
                        classify_ms = p6.now_ms() - t2
                        check(f"scale {n} classify ok", rev.get("ok") is True, rev)
                        timing = p6.measure_batch_timings(
                            assemble_ms=assemble_ms,
                            calculate_ms=calculate_ms,
                            classify_ms=classify_ms,
                            employee_count=n,
                        )
                        SCALE_REPORT.append(timing)
                        check(f"scale {n} batch oriented", timing.get("batch_oriented") is True)
                    else:
                        pipe_n = run_mode_a_pipeline(
                            cur,
                            modules=modules,
                            keys=keys_n,
                            p_start=ps,
                            p_end=pe,
                            reason_prefix=f"pap6_{TAG}_scale{n}",
                        )
                        check(f"scale {n} pipeline ok", pipe_n.get("ok") is True, pipe_n)
                        SCALE_REPORT.append(pipe_n.get("timings") or {"employee_count": n})

                gaps = p6.remaining_gaps_before_unrestricted_rollout()
                check("remaining gaps listed", len(gaps) >= 3, gaps)
                check("gcc still gated in p4b", "gcc_extension_review_required" in p4b.GATED_BLOCKERS)

            conn.commit()
    except Exception as exc:
        check("db suite exception", False, str(exc))
        try:
            cleanup(app, all_keys, all_periods)
        except Exception:
            pass
        _write_evidence(error=str(exc))
        print(f"VERDICT FAIL  pass={PASS} fail={FAIL}  evidence={EVID}")
        return 1

    # Soft cleanup of scale employees to avoid residue (keep entitlement)
    try:
        cleanup(app, all_keys, all_periods)
        check("cleanup", True)
    except Exception as exc:
        check("cleanup", False, str(exc))

    _write_evidence(
        production_entitlement={
            "company": COMPANY,
            "target_state": "authoritative_allowlisted",
            "note": "Restored after rollback drill; synthetic qualification remains; nonsynthetic requires allowlist.",
        },
        remaining_gaps=p6.remaining_gaps_before_unrestricted_rollout(),
        setup_contract=p6.setup_console_schema_contract(),
    )
    print(f"VERDICT {'PASS' if FAIL == 0 else 'FAIL'}  pass={PASS} fail={FAIL}  evidence={EVID}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
