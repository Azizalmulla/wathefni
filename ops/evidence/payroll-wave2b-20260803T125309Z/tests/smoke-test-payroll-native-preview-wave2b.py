#!/usr/bin/env python3
"""Payroll Wave 2B — native preview engine smoke (local/staging).

Proves:
  full-month salary, mid-month join/exit, unpaid leave,
  fixed allowance + deduction, overlapping/missing contract denial,
  duplicate/idempotent calculation, recalculation after input change,
  rounding/currency precision, unsupported statutory blocked,
  rollback, honesty (non-authoritative, payment disabled, no AI).

Does NOT start payslips or payment execution. Does NOT alter Wave 1/2A.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
EMP = f"WATHEFNI-PYW1-W2B-{SUFFIX}"
EMP_B = f"WATHEFNI-PYW1-W2B-B-{SUFFIX}"
CREATOR = "965541100011"
APPROVER = "965541100012"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    print("    payroll native preview wave2b")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY", "1")

    import payroll_authority_wave1 as pyw1
    import payroll_native_preview_wave2b as w2b

    h = w2b.honesty_payload()
    check("version", w2b.PAYROLL_WAVE2B_VERSION == "1.0.0")
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("not authoritative", h.get("authoritative") is False)
    check("preview only", h.get("preview_only") is True)
    check("no AI", h.get("ai_calculations") is False)
    check("external unchanged", h.get("external_flows_unchanged") is True)
    check("no pifss", h.get("pifss") is False)
    check("no bank", h.get("bank_files") is False)
    inv = w2b.freeze_invariants()
    check("deterministic", inv.get("deterministic_only") is True)

    # Pure unit: rounding
    check("money round half up", w2b.money("1.2345") == Decimal("1.235"))
    check("money 3dp", w2b.money("100") == Decimal("100.000"))

    # Pure unit: full month
    p_start, p_end = date(2026, 8, 1), date(2026, 8, 31)
    contract = {
        "contract_id": "c1",
        "employee_key": EMP,
        "status": "approved",
        "effective_from": "2026-01-01",
        "effective_to": None,
        "components": [
            {"component_kind": "earning", "code": "BASIC", "amount": 500, "amount_unit": "monthly", "is_basic": True},
            {"component_kind": "allowance", "code": "TRANSPORT", "amount": 50, "amount_unit": "monthly"},
            {"component_kind": "deduction", "code": "LOAN", "amount": 20, "amount_unit": "monthly"},
        ],
    }
    full = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP},
        contracts=[contract],
    )
    check("full-month ok", full.get("ok") is True, full)
    check("full-month earnings 550", abs(float(full.get("totals_earnings") or 0) - 550.0) < 0.001, full)
    check("full-month deductions 20", abs(float(full.get("totals_deductions") or 0) - 20.0) < 0.001, full)
    check("full-month net 530", abs(float(full.get("totals_net_preview") or 0) - 530.0) < 0.001, full)

    # Mid-month join (16 Aug → 16 days of 31)
    join = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP, "employment_start": "2026-08-16"},
        contracts=[contract],
    )
    expected_earn = w2b.money(Decimal("550") * 16 / 31)
    check("mid join ok", join.get("ok") is True, join)
    check("mid join active 16", join.get("active_days") == 16, join)
    check("mid join earnings prorated", abs(float(join.get("totals_earnings") or 0) - float(expected_earn)) < 0.001, join)

    # Mid-month exit (through 15 Aug → 15 days)
    exit_r = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP, "employment_end": "2026-08-15"},
        contracts=[contract],
    )
    expected_exit = w2b.money(Decimal("550") * 15 / 31)
    check("mid exit ok", exit_r.get("ok") is True, exit_r)
    check("mid exit active 15", exit_r.get("active_days") == 15, exit_r)
    check("mid exit earnings prorated", abs(float(exit_r.get("totals_earnings") or 0) - float(expected_exit)) < 0.001, exit_r)

    # Unpaid leave 2 days on full month: deduct 550*2/31
    unpaid = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP},
        contracts=[contract],
        unpaid_leaves=[{"employee_key": EMP, "classification": "unpaid_leave", "chargeable_days": 2}],
    )
    unpaid_ded = w2b.money(Decimal("550") * 2 / 31)
    check("unpaid ok", unpaid.get("ok") is True, unpaid)
    check(
        "unpaid deduction applied",
        abs(float(unpaid.get("totals_deductions") or 0) - float(w2b.money(20) + unpaid_ded)) < 0.001,
        unpaid,
    )

    # One-time earning + deduction via adjustments
    adj = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP},
        contracts=[contract],
        adjustments=[
            {"employee_key": EMP, "component_kind": "earning", "code": "BONUS", "amount": 100},
            {"employee_key": EMP, "component_kind": "deduction", "code": "FINE", "amount": 5.555},
        ],
    )
    check("adjustment ok", adj.get("ok") is True, adj)
    check("bonus included", abs(float(adj.get("totals_earnings") or 0) - 650.0) < 0.001, adj)
    check("fine rounded 3dp", abs(float(adj.get("totals_deductions") or 0) - 25.555) < 0.001, adj)

    # Missing contract
    missing = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP},
        contracts=[],
    )
    check("missing contract blocked", missing.get("ok") is False, missing)
    check(
        "missing contract code",
        any(b.get("code") == "missing_approved_contract" for b in (missing.get("blockers") or [])),
        missing,
    )

    # Overlapping contracts
    c2 = {
        **contract,
        "contract_id": "c2",
        "effective_from": "2026-08-01",
        "components": [{"component_kind": "earning", "code": "BASIC", "amount": 600, "amount_unit": "monthly", "is_basic": True}],
    }
    overlap = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP},
        contracts=[contract, c2],
    )
    check("overlap blocked", overlap.get("ok") is False, overlap)
    check(
        "overlap code",
        any(b.get("code") == "overlapping_approved_contracts" for b in (overlap.get("blockers") or [])),
        overlap,
    )

    # Unsupported PIFSS requested
    blocked_stat = w2b.calculate_employee_preview(
        period_start=p_start,
        period_end=p_end,
        employee={"employee_key": EMP},
        contracts=[contract],
        requested_unsupported=["pifss"],
    )
    check("pifss blocked", blocked_stat.get("ok") is False, blocked_stat)
    check(
        "pifss review_only",
        any(b.get("posture") == "review_only" for b in (blocked_stat.get("blockers") or [])),
        blocked_stat,
    )

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit+pure)")
            return 1 if FAIL else 0
        raise

    company = "WATHEFNI"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            print("connected_db", db)
            if db == "wathefni":
                print("REFUSE production database in staging smoke")
                return 2

            pyw1.ensure_payroll_wave1_schema(cur, force=True)
            w2b.ensure_payroll_wave2b_schema(cur, force=True)
            pyw1.set_payroll_mode(
                cur, company_code=company, mode="native", actor_phone=APPROVER, reason=f"w2b_mode_{SUFFIX}"
            )

            draft = pyw1.create_contract_draft(
                cur,
                company_code=company,
                employee_key=EMP,
                effective_from=date(2026, 1, 1),
                components=[
                    {"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True},
                    {"component_kind": "allowance", "code": "TRANSPORT", "amount": 50},
                    {"component_kind": "deduction", "code": "LOAN", "amount": 20},
                ],
                actor_phone=CREATOR,
                reason=f"w2b_draft_{SUFFIX}",
            )
            check("db draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            approved = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w2b_approve_{SUFFIX}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("db approve", approved.get("ok") is True, approved)
            contract_row = approved.get("contract") or {}

            period = pyw1.create_period(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="legacy_records",
                actor_phone=CREATOR,
                reason=f"w2b_period_{SUFFIX}",
            )
            check("period", period.get("ok") is True, period)
            period_row = period.get("period") or {}

            run1 = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                period_id=str(period_row.get("period_id") or "") or None,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w2b_calc1_{SUFFIX}",
            )
            check("preview run ok", run1.get("ok") is True, run1)
            check("preview not authoritative", run1.get("authoritative") is False)
            rid = str((run1.get("preview_run") or {}).get("preview_run_id"))
            fp1 = run1.get("input_fingerprint")

            run_idem = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w2b_calc_idem_{SUFFIX}",
            )
            check("idempotent replay", run_idem.get("idempotent") is True, run_idem)

            # Recalc after input change (unpaid leave)
            run2 = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                unpaid_leaves=[{"employee_key": EMP, "classification": "unpaid", "chargeable_days": 1, "leave_id": f"L-{SUFFIX}"}],
                actor_phone=CREATOR,
                reason=f"w2b_calc2_{SUFFIX}",
            )
            check("recalc after input change", run2.get("ok") is True and not run2.get("idempotent"), run2)
            check("fingerprint changed", run2.get("input_fingerprint") != fp1, run2)
            check("prior superseded", bool(run2.get("superseded_run_ids")), run2)

            # Unsupported statutory via run API
            run_bad = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                requested_unsupported=["eos", "overtime_premiums"],
                actor_phone=CREATOR,
                reason=f"w2b_unsupported_{SUFFIX}",
            )
            check("unsupported run failed closed", run_bad.get("ok") is False, run_bad)

            # External mode blocks native preview
            pyw1.set_payroll_mode(
                cur, company_code=company, mode="external", actor_phone=APPROVER, reason=f"w2b_ext_{SUFFIX}"
            )
            blocked_mode = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w2b_mode_block_{SUFFIX}",
            )
            check("external mode blocks preview", blocked_mode.get("error") == "mode_not_native_preview", blocked_mode)
            pyw1.set_payroll_mode(
                cur, company_code=company, mode="native", actor_phone=APPROVER, reason=f"w2b_restore_{SUFFIX}"
            )

            # Rollback
            rb = w2b.rollback_preview_run(
                cur,
                company_code=company,
                preview_run_id=str((run2.get("preview_run") or {}).get("preview_run_id")),
                actor_phone=APPROVER,
                reason=f"w2b_rollback_{SUFFIX}",
            )
            check("rollback ok", rb.get("ok") is True, rb)
            check("rollback status", (rb.get("preview_run") or {}).get("status") == "rolled_back", rb)

            events = w2b.list_preview_events(cur, company_code=company, limit=20)
            check("audit events present", len(events) >= 1, len(events))

            # Real employee refused under synthetic_only
            real = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": "WATHEFNI-96566363363"}],
                contracts=[],
                actor_phone=CREATOR,
                reason=f"w2b_real_{SUFFIX}",
            )
            check("real employee refused", real.get("error") == "payroll_wave2b_synthetic_only", real)

            # Wave 1 still works (contracts untouched)
            check("wave1 still enabled", pyw1.payroll_wave1_enabled())

            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
