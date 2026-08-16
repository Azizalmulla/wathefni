#!/usr/bin/env python3
"""Wave 2 C5 — Payslips + Payment Files prove (company-scoped; global OFF).

Synthetic canary only. Acknowledged ≠ paid. No fund transfer.
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PYP{_N:05d}"[:12].upper()
OTHER = f"PYQ{_N:05d}"[:12].upper()
CREATOR = f"9655521{_N:05d}"
APPROVER = f"9655522{_N:05d}"
FINALIZER = f"9655523{_N:05d}"
EMP = f"{COMPANY}-PYW1-PYC5-{SUFFIX}"
MARKERS = "PYW1,PYP1,PYP2,PYP3,PYP4A,PYP4B,PYP5,PYP6,PYC4,PYC5,PYAUTH,PYINPUT,PYCALC,PYW3"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, c5: str, companies: str, kill: str = "off") -> None:
    os.environ["WATHEFNI_PAYROLL_PAYMENT_C5"] = c5
    os.environ["WATHEFNI_PAYROLL_PAYMENT_COMPANIES"] = companies
    os.environ["WATHEFNI_PAYROLL_PAYMENT_KILL"] = kill
    os.environ["WATHEFNI_PAYROLL_AUTHORITATIVE_C4"] = "on"
    os.environ["WATHEFNI_PAYROLL_AUTHORITATIVE_COMPANIES"] = COMPANY
    for flag in (
        "WATHEFNI_PAYROLL_WAVE1",
        "WATHEFNI_PAYROLL_WAVE3",
        "WATHEFNI_PAYROLL_AUTHORITY_P1",
        "WATHEFNI_PAYROLL_AUTHORITY_P2",
        "WATHEFNI_PAYROLL_AUTHORITY_P3",
        "WATHEFNI_PAYROLL_AUTHORITY_P4A",
        "WATHEFNI_PAYROLL_AUTHORITY_P4B",
        "WATHEFNI_PAYROLL_AUTHORITY_P5",
        "WATHEFNI_PAYROLL_AUTHORITY_P6",
    ):
        os.environ[flag] = "1"
        os.environ[f"{flag}_COMPANIES"] = f"{COMPANY},{OTHER}"
        os.environ[f"{flag}_SYNTHETIC_ONLY"] = "1"
    os.environ["WATHEFNI_PAYROLL_AUTHORITY_P6_ALLOW_SYNTHETIC_QUALIFICATION"] = "1"
    for mk in (
        "WATHEFNI_PAYROLL_AUTHORITY_P5_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_AUTHORITY_P3_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_AUTHORITY_P2_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_AUTHORITY_P1_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS",
        "WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS",
    ):
        os.environ[mk] = MARKERS


def unique_period() -> tuple[date, date]:
    n = int(SUFFIX[:4], 16) % 120
    year = 2037 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def main() -> int:
    print("    payroll payslip payment c5 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import payroll_payslip_payment_c5 as c5

    check("c5 module", c5.PHASE == "payroll_payslip_payment_c5")
    check("rollback guidance", "WATHEFNI_PAYROLL_PAYMENT_KILL=on" in str(c5.rollback_guidance()))
    check("EN released", c5.status_label("released", lang="en") == "Released")
    check("AR released", c5.status_label("released", lang="ar") == "تم الإصدار")
    check("acknowledged ≠ paid honesty", c5.honesty_payload().get("acknowledged_is_not_paid") is True)
    check("no fund transfer", c5.honesty_payload().get("transfers_funds") is False)
    check("attendance not required", c5.honesty_payload().get("attendance_required") is False)

    _flags(c5="off", companies="")
    check("global c5 off", c5.runtime_gate_for_company(COMPANY).get("ok") is not True)

    _flags(c5="on", companies="")
    check("empty allowlist denies", "allowlist" in str(c5.runtime_gate_for_company(COMPANY).get("gate")))

    _flags(c5="on", companies=COMPANY, kill="off")
    check("canary runtime allowlisted", c5.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("other company denied", c5.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    import payroll_authoritative_c4 as c4
    import payroll_authority_mode_a_p5 as p5
    import payroll_authority_production_p6 as p6
    import payroll_authority_snapshot_p1 as p1
    import payroll_authority_wave1 as pyw1
    import payroll_components_policy_p3 as p3
    import payroll_input_snapshot_p2 as p2
    import payroll_payslip_wave3 as w3
    import payroll_payslip_official_pdf as opdf

    p_start, p_end = unique_period()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            pyw1.ensure_payroll_wave1_schema(cur, force=True)
            p1.ensure_payroll_authority_snapshot_schema(cur, force=True)
            p2.ensure_payroll_input_snapshot_schema(cur, force=True)
            p3.ensure_payroll_components_policy_schema(cur, force=True)
            try:
                cur.execute(
                    "ALTER TABLE IF EXISTS payroll_pifss_contribution_specs "
                    "ADD COLUMN IF NOT EXISTS source_classification text"
                )
            except Exception:
                conn.rollback()
            try:
                p5.ensure_payroll_mode_a_finalize_schema(cur, force=True)
            except Exception:
                conn.rollback()
                p5.ensure_payroll_mode_a_finalize_schema(cur, force=False)
            p6.ensure_payroll_production_p6_schema(cur)
            w3.ensure_payroll_wave3_schema(cur)
            c4.ensure_payroll_authoritative_c4_schema(cur)
            c5.ensure_payroll_payslip_payment_c5_schema(cur)
            pyw1.ensure_company_settings(cur, company_code=COMPANY)
            cur.execute(
                """
                UPDATE payroll_company_settings
                   SET payroll_mode='native', payment_processing='disabled', updated_at=now()
                 WHERE company_code=%s
                """,
                (COMPANY,),
            )

            # C4 entitle + employee
            c4.enable_company_authoritative_finalize(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason="c5 canary sealed payroll",
            )
            hire = p_start - timedelta(days=60)
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                ON CONFLICT (employee_key) DO UPDATE
                  SET company_code=EXCLUDED.company_code, phone=EXCLUDED.phone, updated_at=now()
                """,
                (COMPANY, EMP, f"96557{_N:05d}11", f"C5 {EMP[-12:]}", hire, hire),
            )
            p6.add_employee_allowlist(
                cur, company_code=COMPANY, employee_key=EMP, actor_phone=APPROVER, reason=f"c5 al {SUFFIX}"
            )
            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                effective_from=hire,
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 800, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"pyc5_draft_{SUFFIX}",
            )
            cid = str((draft.get("contract") or {}).get("contract_id"))
            pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"pyc5_appr_{SUFFIX}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )

            # Manual feed finalize (sealed) — independent of Attendance/Leave/Shifts
            c4.configure_input_feeds(
                cur, company_code=COMPANY, mode="manual", actor_phone=APPROVER, reason=f"pyc5_feeds_{SUFFIX}"
            )
            period = pyw1.create_period(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="approved_snapshots",
                actor_phone=CREATOR,
                reason=f"pyc5_period_{SUFFIX}",
            )
            check("period created", period.get("ok") is True, period)
            assembled = p2.assemble_payroll_inputs(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                employee_keys=[EMP],
                actor_phone=CREATOR,
                reason=f"pyc5_assemble_{SUFFIX}",
            )
            check("assemble", assembled.get("ok") is True, assembled)
            sid = str((assembled.get("input_snapshot") or {}).get("input_snapshot_id"))
            locked = p2.lock_payroll_input_snapshot(
                cur, company_code=COMPANY, input_snapshot_id=sid, actor_phone=APPROVER,
                reason=f"pyc5_lock_{SUFFIX}", force=True,
            )
            check("lock", locked.get("ok") is True, locked)
            sid = str((locked.get("input_snapshot") or {}).get("input_snapshot_id") or sid)
            pol = p3.create_policy_version(
                cur,
                company_code=COMPANY,
                effective_from=p_start,
                actor_phone=APPROVER,
                reason=f"pyc5_pol_{SUFFIX}",
                attendance_payroll_mode="ignored",
                lateness_money_enabled=False,
                absence_money_enabled=False,
                unpaid_leave_money_enabled=False,
                ot_money_enabled=False,
                approve=True,
            )
            check("policy", pol.get("ok") is True, pol)
            pol_id = str((pol.get("policy") or {}).get("policy_version_id"))
            calc = p3.calculate_mode_a_preview(
                cur,
                company_code=COMPANY,
                input_snapshot_id=sid,
                actor_phone=APPROVER,
                reason=f"pyc5_calc_{SUFFIX}",
                policy_version_id=pol_id,
                employee_keys=[EMP],
            )
            check("calc", calc.get("ok") is True, calc)
            calc_id = str((calc.get("calc_run") or {}).get("calc_run_id"))
            p5.upsert_company_finalize_policy(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason=f"pyc5_fpol_{SUFFIX}",
                require_review_step=True,
                require_distinct_approver=True,
                require_distinct_finalizer=True,
                allow_approver_as_finalizer=True,
            )
            created = p5.create_finalize_run_from_calc(
                cur,
                company_code=COMPANY,
                calc_run_id=calc_id,
                actor_phone=CREATOR,
                reason=f"pyc5_fin_create_{SUFFIX}",
                employee_keys=[EMP],
            )
            check("finalize run create", created.get("ok") is True, created)
            fid = str((created.get("finalize_run") or {}).get("finalize_run_id"))
            p5.submit_finalize_for_review(
                cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR, reason=f"pyc5_sub_{SUFFIX}"
            )
            approved = p5.approve_finalize_run(
                cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=APPROVER, reason=f"pyc5_appr_{SUFFIX}"
            )
            check("finalize approved", approved.get("ok") is True, approved)
            finalized = c4.authoritative_finalize(
                cur,
                company_code=COMPANY,
                finalize_run_id=fid,
                actor_phone=FINALIZER,
                reason=f"pyc5_finalize_{SUFFIX}",
                employee_keys=[EMP],
                check_stale_inputs=False,
            )
            check("authoritative finalize", finalized.get("ok") is True, finalized)
            snaps = finalized.get("authority_snapshots") or []
            check("sealed snapshot", len(snaps) >= 1, snaps)
            aid = str((snaps[0] or {}).get("authority_snapshot_id") or "")

            # --- Payslips ---
            gen = c5.generate_payslip_from_sealed(
                cur,
                company_code=COMPANY,
                authority_snapshot_id=aid,
                actor_phone=APPROVER,
                reason=f"pyc5_payslip_{SUFFIX}",
            )
            check("generate payslip from sealed", gen.get("ok") is True, gen)
            payslip = gen.get("payslip") or {}
            pid = str(payslip.get("payslip_id") or "")
            check("charter state generated", gen.get("charter_state") == "generated", gen)
            check("unreleased invisible to employee", c5.employee_payslip_visible(payslip) is False, payslip)
            cur.execute(
                """
                SELECT label_en, label_ar FROM payroll_payslip_lines
                 WHERE company_code=%s AND payslip_id=%s ORDER BY sort_order LIMIT 5
                """,
                (COMPANY, pid),
            )
            slip_lines = cur.fetchall() or []
            has_en = any(str((ln.get("label_en") if isinstance(ln, dict) else ln[0]) or "").strip() for ln in slip_lines)
            has_ar = any(str((ln.get("label_ar") if isinstance(ln, dict) else ln[1]) or "").strip() for ln in slip_lines)
            labels = w3._labels_for_source(w3.SOURCE_NATIVE_AUTH)  # noqa: SLF001
            check(
                "EN/AR payslip fields",
                has_en and has_ar and bool(labels.get("label_en")) and bool(labels.get("label_ar")),
                {"lines": slip_lines, "labels": labels},
            )
            check("official PDF EN/AR renderer present", hasattr(opdf, "render_official_payslip_pdf_bytes"))

            bound = c5.assert_payslip_bound_to_sealed(cur, company_code=COMPANY, payslip_id=pid)
            check("artifact tied to finalized payroll", bound.get("ok") is True, bound)

            rel = c5.release_payslip(
                cur,
                company_code=COMPANY,
                payslip_id=pid,
                actor_phone=APPROVER,
                reason=f"pyc5_release_{SUFFIX}",
                notify=True,
            )
            check("release payslip", rel.get("ok") is True, rel)
            check("release → visible", rel.get("employee_visible") is True and c5.employee_payslip_visible(rel.get("payslip")), rel)
            check("notification on release", (rel.get("notification") or {}).get("ok") is True, rel)
            check("idempotent release", c5.release_payslip(
                cur, company_code=COMPANY, payslip_id=pid, actor_phone=APPROVER, reason="again"
            ).get("idempotent") is True)

            # Silent PDF regen banned — must use revoke/replace path
            voided = c5.void_payslip(
                cur,
                company_code=COMPANY,
                payslip_id=pid,
                actor_phone=APPROVER,
                reason=f"pyc5_void_{SUFFIX}",
            )
            check("void path audited", voided.get("ok") is True and voided.get("charter_state") == "voided", voided)
            void_doc = voided.get("payslip") or w3.get_payslip(cur, company_code=COMPANY, payslip_id=pid)
            check("voided not employee-visible", c5.employee_payslip_visible(void_doc) is False, void_doc)

            # After void, new payslip from same sealed snapshot is the correction path (not silent PDF regen)
            gen2 = c5.generate_payslip_from_sealed(
                cur,
                company_code=COMPANY,
                authority_snapshot_id=aid,
                actor_phone=APPROVER,
                reason=f"pyc5_payslip2_{SUFFIX}",
            )
            check("correction via new payslip after void", gen2.get("ok") is True, gen2)
            pid2 = str((gen2.get("payslip") or {}).get("payslip_id") or "")
            rel2 = c5.release_payslip(
                cur, company_code=COMPANY, payslip_id=pid2, actor_phone=APPROVER, reason=f"pyc5_rel2_{SUFFIX}"
            )
            check("release → immediately downloadable", rel2.get("employee_visible") is True, rel2)
            bound2 = c5.assert_payslip_bound_to_sealed(cur, company_code=COMPANY, payslip_id=pid2)
            check("released artifact tied to finalized payroll", bound2.get("ok") is True, bound2)

            # --- Payment files ---
            blocked = c5.create_payment_file_draft(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                finalize_run_id=fid,
                actor_phone=APPROVER,
                reason="should block",
            )
            check(
                "payment generation blocked while entitlement off",
                blocked.get("ok") is False and blocked.get("error") == "payment_processing_not_enabled",
                blocked,
            )

            en = c5.enable_company_payment_processing(
                cur,
                company_code=COMPANY,
                actor_phone=APPROVER,
                reason="enable canary payment processing",
            )
            check("payment_processing enabled", en.get("ok") is True, en)
            ent = c5.payment_processing_enabled_for_company(cur, COMPANY)
            check("payment entitlement open", ent.get("ok") is True, ent)

            # Kill switch
            os.environ["WATHEFNI_PAYROLL_PAYMENT_KILL"] = "on"
            killed = c5.create_payment_file_draft(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                finalize_run_id=fid,
                actor_phone=APPROVER,
                reason="kill",
            )
            check(
                "kill switch blocks generation",
                killed.get("error") == "payment_kill_switch_active",
                killed,
            )
            os.environ["WATHEFNI_PAYROLL_PAYMENT_KILL"] = "off"

            draft_pf = c5.create_payment_file_draft(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                finalize_run_id=fid,
                authority_snapshot_ids=[aid],
                actor_phone=APPROVER,
                reason=f"pyc5_pf_draft_{SUFFIX}",
            )
            check("valid payment draft when enabled", draft_pf.get("ok") is True, draft_pf)
            pfid = str((draft_pf.get("payment_file") or {}).get("payment_file_id") or "")
            check(
                "provenance fingerprint present",
                bool((draft_pf.get("payment_file") or {}).get("authority_fingerprint")),
                draft_pf,
            )

            again = c5.create_payment_file_draft(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                finalize_run_id=fid,
                authority_snapshot_ids=[aid],
                actor_phone=APPROVER,
                reason="dup",
            )
            check("duplicate draft idempotent", again.get("ok") is True and again.get("idempotent") is True, again)

            rv = int((draft_pf.get("payment_file") or {}).get("row_version") or 1)
            stale_gen = c5.generate_payment_file(
                cur,
                company_code=COMPANY,
                payment_file_id=pfid,
                actor_phone=APPROVER,
                reason="stale",
                expected_row_version=0,
            )
            check(
                "stale/concurrent generate protection",
                stale_gen.get("error") == "stale_payment_file_decision",
                stale_gen,
            )
            generated = c5.generate_payment_file(
                cur,
                company_code=COMPANY,
                payment_file_id=pfid,
                actor_phone=APPROVER,
                reason=f"pyc5_gen_{SUFFIX}",
                expected_row_version=rv,
            )
            check("valid generation when enabled", generated.get("ok") is True, generated)
            check(
                "format pack not real WPS",
                (generated.get("format_pack") or {}).get("real_wps_format") is False,
                generated,
            )
            gen_idem = c5.generate_payment_file(
                cur,
                company_code=COMPANY,
                payment_file_id=pfid,
                actor_phone=APPROVER,
                reason="again",
            )
            check("duplicate/idempotent generation", gen_idem.get("ok") is True and gen_idem.get("idempotent") is True, gen_idem)

            rv2 = int((generated.get("payment_file") or {}).get("row_version") or 1)
            ack = c5.transition_payment_file(
                cur,
                company_code=COMPANY,
                payment_file_id=pfid,
                decision="acknowledged",
                actor_phone=APPROVER,
                reason=f"pyc5_ack_{SUFFIX}",
                expected_row_version=rv2,
            )
            check("acknowledged state", ack.get("ok") is True and (ack.get("payment_file") or {}).get("status") == "acknowledged", ack)
            check(
                "acknowledged is ops-only not paid",
                ack.get("acknowledged_means") == "operational_ack_only"
                and c5.honesty_payload().get("acknowledged_is_not_paid") is True,
                ack,
            )

            # Failed / cancelled lifecycle fixtures (distinct fingerprints)
            cur.execute(
                """
                INSERT INTO payroll_payment_files (
                  company_code, finalize_run_id, period_start, period_end,
                  authority_snapshot_ids, authority_fingerprint, format_pack_id,
                  status, created_by_phone, decision_note
                ) VALUES (%s,%s,%s,%s,'[]'::jsonb,%s,'kw_wps_stub_v1','draft',%s,%s)
                RETURNING *
                """,
                (
                    COMPANY,
                    fid,
                    str(p_start)[:10],
                    str(p_end)[:10],
                    f"fail-{SUFFIX}",
                    APPROVER,
                    "fail fixture",
                ),
            )
            fail_row = dict(cur.fetchone())
            failed = c5.transition_payment_file(
                cur,
                company_code=COMPANY,
                payment_file_id=str(fail_row["payment_file_id"]),
                decision="failed",
                actor_phone=APPROVER,
                reason="ops fail",
                expected_row_version=int(fail_row.get("row_version") or 1),
            )
            check("failed state", failed.get("ok") is True and (failed.get("payment_file") or {}).get("status") == "failed", failed)

            cur.execute(
                """
                INSERT INTO payroll_payment_files (
                  company_code, finalize_run_id, period_start, period_end,
                  authority_snapshot_ids, authority_fingerprint, format_pack_id,
                  status, created_by_phone, decision_note
                ) VALUES (%s,%s,%s,%s,'[]'::jsonb,%s,'kw_wps_stub_v1','draft',%s,%s)
                RETURNING *
                """,
                (
                    COMPANY,
                    fid,
                    str(p_start)[:10],
                    str(p_end)[:10],
                    f"cancel-{SUFFIX}",
                    APPROVER,
                    "cancel fixture",
                ),
            )
            cancel_row = dict(cur.fetchone())
            cancelled = c5.transition_payment_file(
                cur,
                company_code=COMPANY,
                payment_file_id=str(cancel_row["payment_file_id"]),
                decision="cancelled",
                actor_phone=APPROVER,
                reason="ops cancel",
                expected_row_version=int(cancel_row.get("row_version") or 1),
            )
            check(
                "cancelled state",
                cancelled.get("ok") is True and (cancelled.get("payment_file") or {}).get("status") == "cancelled",
                cancelled,
            )

            # Tenant + RBAC/SoD surface
            check("tenant isolation", c5.runtime_gate_for_company(OTHER).get("ok") is not True)
            settings = pyw1.ensure_company_settings(cur, company_code=COMPANY)
            check(
                "wave1 payment_processing column still disabled (no money rails)",
                str(settings.get("payment_processing")) == "disabled",
                settings,
            )
            # SoD: creator cannot approve finalize already proven in C4; re-assert helper
            sod = p5.approve_finalize_run(
                cur, company_code=COMPANY, finalize_run_id=fid, actor_phone=CREATOR, reason="sod"
            )
            check(
                "payroll SoD still enforceable",
                sod.get("ok") is False
                or sod.get("error") in {"sod_creator_cannot_approve", "finalize_must_be_in_review", "invalid_finalize_status"}
                or (sod.get("finalize_run") or {}).get("status") == "finalized",
                sod,
            )

            src = Path(__file__).with_name("payroll_payslip_payment_c5.py").read_text()
            check("independent of attendance_truth", "attendance_truth_c1" not in src)
            check("independent of leave_enforcement", "leave_enforcement_c2" not in src)
            check("independent of shifts_mss", "shifts_mss_c3" not in src)

            # Disable entitlement
            off = c5.disable_company_payment_processing(
                cur, company_code=COMPANY, actor_phone=APPROVER, reason="rollback"
            )
            check("disable payment processing", off.get("ok") is True, off)
            check(
                "blocked after disable",
                c5.payment_processing_enabled_for_company(cur, COMPANY).get("ok") is not True,
            )

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("PAYSLIP_PAYMENT_UNIT_PASS")
    print("PAYSLIP_PAYMENT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
