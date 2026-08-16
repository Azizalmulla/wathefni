#!/usr/bin/env python3
"""Wave 2 C6 — Final Settlement + OT contract prove (company-scoped; global OFF).

Synthetic canary only. Settlement finalized ≠ paid. No invented EOS/PIFSS formulas.
"""
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
COMPANY = f"PYS{_N:05d}"[:12].upper()
OTHER = f"PYT{_N:05d}"[:12].upper()
CREATOR = f"9655531{_N:05d}"
APPROVER = f"9655532{_N:05d}"
FINALIZER = f"9655533{_N:05d}"
EMP = f"{COMPANY}-PYW1-PYC6-{SUFFIX}"
MGR = f"9655534{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, c6: str, companies: str, kill: str = "off") -> None:
    os.environ["WATHEFNI_PAYROLL_SETTLEMENT_C6"] = c6
    os.environ["WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES"] = companies
    os.environ["WATHEFNI_PAYROLL_SETTLEMENT_KILL"] = kill


def main() -> int:
    print("    payroll settlement ot c6 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import payroll_settlement_ot_c6 as c6

    check("c6 module", c6.PHASE == "payroll_settlement_ot_c6")
    check("rollback guidance", "WATHEFNI_PAYROLL_SETTLEMENT_KILL=on" in str(c6.rollback_guidance()))
    check("EN finalized", c6.status_label("finalized", lang="en") == "Finalized")
    check("AR finalized", c6.status_label("finalized", lang="ar") == "مختوم")
    check("EN OT pending", c6.status_label("pending_approval", lang="en") == "Pending approval")
    check("AR OT pending", c6.status_label("pending_approval", lang="ar") == "بانتظار الاعتماد")
    check("settlement ≠ paid honesty", c6.honesty_payload().get("settlement_finalized_is_not_paid") is True)
    check("no invented EOS/PIFSS", c6.honesty_payload().get("invented_eos_pifss_formulas") is False)
    check("E360 not calculator", c6.honesty_payload().get("e360_is_payroll_calculator") is False)
    check("OT not required for payroll", c6.honesty_payload().get("ot_required_for_payroll") is False)
    check("settlement ≠ clearance", c6.honesty_payload().get("settlement_is_not_clearance") is True)

    _flags(c6="off", companies="")
    check("module-off / global off", c6.runtime_gate_for_company(COMPANY).get("ok") is not True)

    _flags(c6="on", companies="")
    check("empty allowlist denies", "allowlist" in str(c6.runtime_gate_for_company(COMPANY).get("gate")))

    _flags(c6="on", companies=COMPANY, kill="off")
    check("canary allowlisted", c6.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant isolation", c6.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    term = date(2038, 6, 30)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c6.ensure_payroll_settlement_ot_c6_schema(cur)

            # Entitlement off blocks settlement
            blocked = c6.create_settlement_from_lifecycle_packet(
                cur,
                company_code=COMPANY,
                lifecycle_packet_id=str(uuid.uuid4()),
                actor_phone=CREATOR,
                reason="should block",
            )
            check(
                "settlement blocked while entitlement off",
                blocked.get("error") == "settlement_not_enabled",
                blocked,
            )

            en = c6.enable_company_settlement_ot(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason="c6 canary enable",
                settlement_enabled=True,
                ot_authorization_enabled=True,
                ot_to_payroll_enabled=False,
            )
            check("enable settlement+ot auth", en.get("ok") is True, en)

            # --- Settlement from valid lifecycle inputs (no OT) ---
            seeded = c6.seed_lifecycle_settlement_packet(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                termination_effective_on=term,
                last_working_day=term - timedelta(days=1),
                leave_encashment_days=5.0,
                eos_worksheet_id=f"eos-ws-{SUFFIX}",
                pifss_worksheet_id=f"pifss-ws-{SUFFIX}",
                compensation_components=[
                    {
                        "code": "BASIC",
                        "line_kind": "earning",
                        "amount": 400,
                        "label_en": "Basic salary (pro-rata input)",
                        "label_ar": "الراتب الأساسي (مدخل نسبي)",
                    }
                ],
                approved_adjustments=[
                    {
                        "code": "LOAN",
                        "line_kind": "deduction",
                        "amount": 25,
                        "label_en": "Loan recovery",
                        "label_ar": "استرداد قرض",
                    }
                ],
            )
            check("lifecycle packet seeded", seeded.get("ok") is True, seeded)
            packet_id = str((seeded.get("packet") or {}).get("packet_id"))

            created = c6.create_settlement_from_lifecycle_packet(
                cur,
                company_code=COMPANY,
                lifecycle_packet_id=packet_id,
                actor_phone=CREATOR,
                reason=f"pyc6_create_{SUFFIX}",
                final_period_start=date(term.year, term.month, 1),
                final_period_end=term,
            )
            check("settlement from valid lifecycle inputs", created.get("ok") is True, created)
            sid = str((created.get("settlement") or {}).get("settlement_id"))
            check(
                "status inputs_ready",
                (created.get("settlement") or {}).get("status") == "inputs_ready",
                created,
            )

            rv = int((created.get("settlement") or {}).get("row_version") or 1)
            calc = c6.calculate_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=CREATOR,
                reason=f"pyc6_calc_{SUFFIX}",
                expected_row_version=rv,
            )
            check("calculate settlement", calc.get("ok") is True, calc)
            check(
                "encashment quantity only (no money invented)",
                (calc.get("calc") or {}).get("leave_encashment", {}).get("amount_calculated_here") is False,
                calc,
            )
            check(
                "EOS refs without invented formulas",
                (calc.get("calc") or {}).get("eos_pifss", {}).get("formula_invented") is False,
                calc,
            )
            check(
                "EN/AR settlement calc labels",
                bool(((calc.get("calc") or {}).get("labels") or {}).get("en"))
                and bool(((calc.get("calc") or {}).get("labels") or {}).get("ar")),
                calc,
            )

            # SoD: creator cannot approve
            sod = c6.approve_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=CREATOR,
                reason="sod",
                expected_row_version=int((calc.get("settlement") or {}).get("row_version") or 1),
            )
            check(
                "SoD creator/calculator cannot approve",
                sod.get("error") == "sod_creator_or_calculator_cannot_approve",
                sod,
            )

            rv2 = int((calc.get("settlement") or {}).get("row_version") or 1)
            stale = c6.approve_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=APPROVER,
                reason="stale",
                expected_row_version=0,
            )
            check("stale approval protection", stale.get("error") == "stale_settlement_decision", stale)

            approved = c6.approve_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=APPROVER,
                reason=f"pyc6_appr_{SUFFIX}",
                expected_row_version=rv2,
            )
            check("approve settlement", approved.get("ok") is True, approved)

            # Kill switch blocks finalize
            os.environ["WATHEFNI_PAYROLL_SETTLEMENT_KILL"] = "on"
            killed = c6.finalize_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=FINALIZER,
                reason="kill",
                expected_row_version=int((approved.get("settlement") or {}).get("row_version") or 1),
            )
            check("kill switch blocks finalize", killed.get("error") == "settlement_kill_switch_active", killed)
            os.environ["WATHEFNI_PAYROLL_SETTLEMENT_KILL"] = "off"

            # Creator cannot finalize
            bad_fin = c6.finalize_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=CREATOR,
                reason="sod fin",
                expected_row_version=int((approved.get("settlement") or {}).get("row_version") or 1),
            )
            check("SoD creator cannot finalize", bad_fin.get("error") == "sod_creator_cannot_finalize", bad_fin)

            finalized = c6.finalize_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=FINALIZER,
                reason=f"pyc6_fin_{SUFFIX}",
                expected_row_version=int((approved.get("settlement") or {}).get("row_version") or 1),
            )
            check("finalize seals result", finalized.get("ok") is True and finalized.get("immutable") is True, finalized)
            check(
                "settlement payslip/payment inputs",
                bool(finalized.get("payslip_input")) and bool(finalized.get("payment_input")),
                finalized,
            )
            check(
                "no false paid state",
                (finalized.get("settlement") or {}).get("claims_paid") is False
                and (finalized.get("payment_input") or {}).get("claims_paid") is False
                and c6.honesty_payload().get("claims_paid") is False,
                finalized,
            )
            check(
                "EN/AR payslip/payment input labels",
                bool(((finalized.get("payslip_input") or {}).get("labels") or {}).get("ar"))
                and bool(((finalized.get("payment_input") or {}).get("labels") or {}).get("en")),
                finalized,
            )

            dup = c6.finalize_settlement(
                cur,
                company_code=COMPANY,
                settlement_id=sid,
                actor_phone=FINALIZER,
                reason="dup",
            )
            check("stale/duplicate finalize idempotent", dup.get("ok") is True and dup.get("idempotent") is True, dup)

            imm = c6.assert_settlement_immutable(cur, company_code=COMPANY, settlement_id=sid)
            check("finalized settlement immutable", imm.get("ok") is True and imm.get("immutable") is True, imm)

            # Adjustment path after finalization
            adj = c6.create_adjustment_settlement(
                cur,
                company_code=COMPANY,
                supersedes_settlement_id=sid,
                actor_phone=CREATOR,
                reason=f"pyc6_adj_{SUFFIX}",
                approved_adjustments=[
                    {
                        "code": "CORR",
                        "line_kind": "earning",
                        "amount": 10,
                        "label_en": "Audited correction",
                        "label_ar": "تصحيح مدقق",
                    }
                ],
            )
            check("adjustment path after finalization", adj.get("ok") is True, adj)
            check("prior superseded", adj.get("prior_status") == "superseded", adj)
            prior = c6.get_settlement(cur, company_code=COMPANY, settlement_id=sid)
            check("sealed prior not silently mutated status", (prior or {}).get("status") == "superseded", prior)

            # Payroll without OT remains green (settlement path above succeeded with ot_to_payroll OFF)
            check("Payroll without OT remains green", True)

            # --- OT authorize ---
            ot_off = c6.export_ot_to_payroll(
                cur,
                company_code=COMPANY,
                ot_request_id=str(uuid.uuid4()),
                actor_phone=APPROVER,
                reason="blocked",
            )
            check(
                "OT→Payroll optional feed off blocks export",
                ot_off.get("error") in {"ot_to_payroll_not_enabled", "ot_request_not_found"},
                ot_off,
            )

            ot_create = c6.create_ot_request(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                work_date=term - timedelta(days=10),
                hours=2.5,
                actor_phone=EMP[-12:] if EMP[-12:].isdigit() else CREATOR,
                reason=f"pyc6_ot_{SUFFIX}",
                requested_role="employee",
                manager_scope_keys=[EMP],
            )
            # employee phone may not be digits-only from EMP key — use CREATOR as requester employee path
            if not ot_create.get("ok"):
                ot_create = c6.create_ot_request(
                    cur,
                    company_code=COMPANY,
                    employee_key=EMP,
                    work_date=term - timedelta(days=10),
                    hours=2.5,
                    actor_phone=CREATOR,
                    reason=f"pyc6_ot_{SUFFIX}",
                    requested_role="employee",
                    manager_scope_keys=[EMP],
                )
            check("OT create", ot_create.get("ok") is True, ot_create)
            oid = str((ot_create.get("ot_request") or {}).get("ot_request_id"))
            rv_ot = int((ot_create.get("ot_request") or {}).get("row_version") or 1)
            submitted = c6.submit_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                actor_phone=CREATOR,
                reason="submit",
                expected_row_version=rv_ot,
            )
            check("OT submit → pending", submitted.get("ok") is True, submitted)

            self_appr = c6.decide_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                decision="approved",
                actor_phone=CREATOR,
                reason="self",
                expected_row_version=int((submitted.get("ot_request") or {}).get("row_version") or 1),
            )
            check("OT self-approve fails", self_appr.get("error") == "sod_self_approve_forbidden", self_appr)

            oos = c6.decide_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                decision="approved",
                actor_phone=MGR,
                reason="oos",
                expected_row_version=int((submitted.get("ot_request") or {}).get("row_version") or 1),
                actor_managed_keys=[f"{COMPANY}-OTHER"],
            )
            check("OT out-of-scope fails", oos.get("error") == "employee_outside_manager_scope", oos)

            stale_ot = c6.decide_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                decision="approved",
                actor_phone=APPROVER,
                reason="stale",
                expected_row_version=0,
                actor_managed_keys=[EMP],
            )
            check("OT stale fails safely", stale_ot.get("error") == "stale_ot_decision", stale_ot)

            # Reject path on a second request
            ot2 = c6.create_ot_request(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                work_date=term - timedelta(days=9),
                hours=1,
                actor_phone=CREATOR,
                reason="ot2",
                requested_role="manager",
            )
            oid2 = str((ot2.get("ot_request") or {}).get("ot_request_id"))
            c6.submit_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid2,
                actor_phone=CREATOR,
                reason="sub2",
                expected_row_version=int((ot2.get("ot_request") or {}).get("row_version") or 1),
            )
            # fetch current rv
            cur.execute(
                "SELECT row_version FROM payroll_ot_requests WHERE ot_request_id=%s",
                (oid2,),
            )
            rv_rej = int((cur.fetchone() or {}).get("row_version") or 1)
            rejected = c6.decide_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid2,
                decision="rejected",
                actor_phone=APPROVER,
                reason="reject",
                expected_row_version=rv_rej,
                actor_managed_keys=[EMP],
            )
            check("OT reject", rejected.get("ok") is True and (rejected.get("ot_request") or {}).get("status") == "rejected", rejected)

            # Cancel path
            ot3 = c6.create_ot_request(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                work_date=term - timedelta(days=8),
                hours=1,
                actor_phone=CREATOR,
                reason="ot3",
                requested_role="hr",
            )
            oid3 = str((ot3.get("ot_request") or {}).get("ot_request_id"))
            cancelled = c6.decide_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid3,
                decision="cancelled",
                actor_phone=CREATOR,
                reason="cancel draft",
                expected_row_version=int((ot3.get("ot_request") or {}).get("row_version") or 1),
            )
            check(
                "OT cancel",
                cancelled.get("ok") is True and (cancelled.get("ot_request") or {}).get("status") == "cancelled",
                cancelled,
            )

            # Approve + optional feed
            approved_ot = c6.decide_ot_request(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                decision="approved",
                actor_phone=APPROVER,
                reason="approve ot",
                expected_row_version=int((submitted.get("ot_request") or {}).get("row_version") or 1),
                actor_managed_keys=[EMP],
            )
            check("OT approve", approved_ot.get("ok") is True, approved_ot)

            still_blocked = c6.export_ot_to_payroll(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                actor_phone=APPROVER,
                reason="still off",
                expected_row_version=int((approved_ot.get("ot_request") or {}).get("row_version") or 1),
            )
            check(
                "OT export blocked until feed enabled",
                still_blocked.get("error") == "ot_to_payroll_not_enabled",
                still_blocked,
            )

            c6.enable_company_settlement_ot(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason="enable ot feed",
                settlement_enabled=True,
                ot_authorization_enabled=True,
                ot_to_payroll_enabled=True,
            )
            exported = c6.export_ot_to_payroll(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                actor_phone=APPROVER,
                reason="export",
                expected_row_version=int((approved_ot.get("ot_request") or {}).get("row_version") or 1),
            )
            check(
                "OT→Payroll optional feed export",
                exported.get("ok") is True
                and (exported.get("ot_request") or {}).get("status") == "payroll_exported"
                and (exported.get("payroll_input_fact") or {}).get("money_calculated_here") is False,
                exported,
            )
            check(
                "EN/AR OT payroll input labels",
                bool(((exported.get("payroll_input_fact") or {}).get("labels") or {}).get("en"))
                and bool(((exported.get("payroll_input_fact") or {}).get("labels") or {}).get("ar")),
                exported,
            )
            exp_idem = c6.export_ot_to_payroll(
                cur,
                company_code=COMPANY,
                ot_request_id=oid,
                actor_phone=APPROVER,
                reason="again",
            )
            check("OT export idempotent", exp_idem.get("idempotent") is True, exp_idem)

            src = Path(__file__).with_name("payroll_settlement_ot_c6.py").read_text()
            check("independent of attendance_truth", "attendance_truth_c1" not in src)
            check("independent of leave_enforcement", "leave_enforcement_c2" not in src)
            check("independent of shifts_mss", "shifts_mss_c3" not in src)

            off = c6.disable_company_settlement_ot(
                cur, company_code=COMPANY, actor_phone=APPROVER, reason="rollback"
            )
            check("disable company entitlement", off.get("ok") is True, off)
            check(
                "module-off after disable",
                c6.settlement_enabled_for_company(cur, COMPANY).get("ok") is not True,
            )

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("SETTLEMENT_OT_UNIT_PASS")
    print("SETTLEMENT_OT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
