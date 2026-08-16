#!/usr/bin/env python3
"""Payroll Authority Wave 1 — foundation smoke (local/staging).

Pins:
  - honesty: payment_processing=disabled, no money authority
  - modes native|external|parallel_shadow
  - contract draft → approve → replace; self-approve + overlap denial
  - period open → lock → close → reopen
  - SOD approve×export; payroll_operator lacks export
  - attendance input-source mix ban
  - PayrollInputExport / PayrollResultImport schema stubs
  - Art.70 = 6 months
  - May smoke quarantine (soft)
  - sibling freeze regressions remain callable

Does NOT enable real money. Does NOT deploy production.
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
EMP_KEY = f"WATHEFNI-PYW1-{SUFFIX}"
CREATOR = "965539100001"
APPROVER = "965539100002"
SUBJECT = "965539100003"


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
    print("    payroll authority wave1 — foundation + gates + adapters")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")

    import payroll_authority_wave1 as pyw1
    import tenant_control_roles as roles

    # --- Pure unit -----------------------------------------------------------
    honesty = pyw1.honesty_payload()
    check("version pinned", pyw1.PAYROLL_WAVE1_VERSION == "1.0.0")
    check("payment_processing disabled", honesty.get("payment_processing") == "disabled")
    check("money_authority false", honesty.get("money_authority") is False)
    check("no g2n", honesty.get("gross_to_net") is False)
    check("no pifss", honesty.get("pifss") is False)
    check("no bank_wps", honesty.get("bank_wps") is False)
    check("no eos_auto", honesty.get("eos_auto") is False)
    check("art70=6", honesty.get("annual_leave_eligibility_months") == 6)
    check("modes present", set(pyw1.PAYROLL_MODES) == {"native", "external", "parallel_shadow"})

    inv = pyw1.freeze_invariants()
    check("freeze no money", inv.get("payment_processing_hard_disabled") is True)
    check("freeze self-approval", inv.get("self_approval_forbidden") is True)

    check("reason required", (pyw1.require_audit_reason("") or {}).get("error") == "audit_reason_required")
    check("concurrency required", (pyw1.require_concurrency(expected_row_version=None, actual_row_version=1) or {}).get("error") == "concurrency_token_required")
    check("stale version", (pyw1.require_concurrency(expected_row_version=1, actual_row_version=2) or {}).get("error") == "stale_row_version")
    check("self ban", (pyw1.self_decision_denied(subject_phone=SUBJECT, actor_phone=SUBJECT, action="x") or {}).get("error") == "self_approval_forbidden")
    check("creator ban", (pyw1.creator_self_approve_denied(created_by_phone=CREATOR, actor_phone=CREATOR, action="x") or {}).get("error") == "self_approval_forbidden")
    check("sod detect", pyw1.sod_holds_approve_and_export(["payroll.approve", "payroll.export"]) is True)
    check("sod clear", pyw1.sod_holds_approve_and_export(["payroll.approve"]) is False)

    warnings = roles.sod_warnings(["payroll.approve", "payroll.export"])
    check("sod warnings fire", any("payroll.approve" in str(w) and "payroll.export" in str(w) for w in warnings) or len(warnings) >= 1)

    mix = pyw1.assert_period_attendance_source(
        period={"attendance_input_source": "legacy_records"},
        requested_source="approved_snapshots",
    )
    check("source mix forbidden", bool(mix) and mix.get("error") == "attendance_source_mix_forbidden")

    bad_export = pyw1.validate_input_export_schema(
        {
            "schema": pyw1.PAYROLL_INPUT_EXPORT_SCHEMA,
            "payment_processing": "enabled",
            "money_fields": None,
            "period": {"attendance_input_source": "legacy_records"},
            "employees": [],
            "compensation_contracts": [],
            "shifts": [],
            "attendance": [],
            "leave_classifications": [],
        }
    )
    check("export rejects enabled payment", bad_export.get("error") == "payment_processing_must_be_disabled")

    good_export = pyw1.build_input_export(
        company_code="WATHEFNI",
        period={
            "period_id": str(uuid.uuid4()),
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "attendance_input_source": "legacy_records",
            "status": "open",
            "payroll_mode": "external",
        },
        employees=[{"employee_key": EMP_KEY}],
        contracts=[],
        shifts=[],
        attendance=[],
        leave_classifications=[{"leave_type": "annual", "classification": "paid"}],
    )
    check("input export ok", good_export.get("ok") is True, good_export)

    money_leave = pyw1.build_input_export(
        company_code="WATHEFNI",
        period={
            "period_id": str(uuid.uuid4()),
            "period_start": "2026-08-01",
            "period_end": "2026-08-31",
            "attendance_input_source": "legacy_records",
            "status": "open",
            "payroll_mode": "native",
        },
        employees=[],
        contracts=[],
        shifts=[],
        attendance=[],
        leave_classifications=[{"leave_type": "annual", "salary_deduction": 10}],
    )
    check("leave money fields forbidden", money_leave.get("error") == "leave_money_fields_forbidden")

    result_ok = pyw1.validate_result_import_schema(
        {
            "schema": pyw1.PAYROLL_RESULT_IMPORT_SCHEMA,
            "payment_processing": "disabled",
            "posts_payment": False,
            "money_authority": False,
            "lines": [],
        }
    )
    check("result import stub ok", result_ok.get("ok") is True)
    result_bad = pyw1.validate_result_import_schema(
        {
            "schema": pyw1.PAYROLL_RESULT_IMPORT_SCHEMA,
            "payment_processing": "disabled",
            "posts_payment": True,
            "money_authority": False,
            "lines": [],
        }
    )
    check("result import bans posts_payment", result_bad.get("error") == "posts_payment_forbidden_in_wave1")

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    payroll_ops = set(app.hr_role_permissions("payroll_operator"))
    mgr = set(app.hr_role_permissions("manager"))
    check("payroll_operator has approve", "payroll.approve" in payroll_ops)
    check("payroll_operator lacks export", "payroll.export" not in payroll_ops)
    check("manager has payroll.approve", "payroll.approve" in mgr)
    check("manager lacks payroll.export", "payroll.export" not in mgr)
    check("payroll.approve known", "payroll.approve" in app.KNOWN_DASHBOARD_PERMISSIONS)

    import tool_call_orchestrator as tco

    perm_map = getattr(tco, "TOOL_PERMISSION_MAP", None) or getattr(tco, "POSTHIRE_TOOL_PERMISSIONS", None)
    if perm_map is None:
        # fall back: inspect module dicts
        for name in dir(tco):
            obj = getattr(tco, name)
            if isinstance(obj, dict) and obj.get("approve_timesheet"):
                perm_map = obj
                break
    check("approve tool → payroll.approve", bool(perm_map) and perm_map.get("approve_timesheet") == "payroll.approve", perm_map)
    check("export tool → payroll.export", bool(perm_map) and perm_map.get("export_payroll") == "payroll.export")

    # --- DB path -------------------------------------------------------------
    company = "WATHEFNI"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            print("connected_db", db)
            if db == "wathefni":
                print("REFUSE production database in smoke")
                return 2

            pyw1.ensure_payroll_wave1_schema(cur, force=True)
            for mode in ("native", "external", "parallel_shadow"):
                mode_res = pyw1.set_payroll_mode(
                    cur,
                    company_code=company,
                    mode=mode,
                    actor_phone=APPROVER,
                    reason=f"wave1_mode_{mode}_{SUFFIX}",
                )
                check(f"set mode {mode}", mode_res.get("ok") is True, mode_res)
            settings = pyw1.ensure_company_settings(cur, company_code=company)
            check("settings payment disabled", settings.get("payment_processing") == "disabled")
            check("settings art70=6", int(settings.get("annual_leave_eligibility_months") or 0) == 6)

            # Contract draft → approve → replace
            draft = pyw1.create_contract_draft(
                cur,
                company_code=company,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 1),
                components=[
                    {
                        "component_kind": "earning",
                        "code": "BASIC",
                        "label_en": "Basic",
                        "amount": 500,
                        "is_basic": True,
                    }
                ],
                actor_phone=CREATOR,
                reason=f"wave1_draft_{SUFFIX}",
            )
            check("contract draft ok", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            rv = int((draft.get("contract") or {}).get("row_version") or 1)

            self_deny = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=CREATOR,
                reason="should_fail_creator",
                expected_row_version=rv,
                subject_phone=None,
            )
            check("creator self-approve denied", self_deny.get("error") == "self_approval_forbidden", self_deny)

            subj_deny = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=SUBJECT,
                reason="should_fail_subject",
                expected_row_version=rv,
                subject_phone=SUBJECT,
            )
            check("subject self-approve denied", subj_deny.get("error") == "self_approval_forbidden", subj_deny)

            approved = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"wave1_approve_{SUFFIX}",
                expected_row_version=rv,
            )
            check("contract approve ok", approved.get("ok") is True, approved)
            approved_rv = int((approved.get("contract") or {}).get("row_version") or 0)

            # Overlap denial: second approved overlapping draft
            draft2 = pyw1.create_contract_draft(
                cur,
                company_code=company,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 15),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"wave1_overlap_draft_{SUFFIX}",
            )
            cid2 = str((draft2.get("contract") or {}).get("contract_id"))
            rv2 = int((draft2.get("contract") or {}).get("row_version") or 1)
            overlap = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid2,
                actor_phone=APPROVER,
                reason=f"wave1_overlap_try_{SUFFIX}",
                expected_row_version=rv2,
            )
            check("overlap approve denied", overlap.get("error") == "overlapping_approved_contract", overlap)

            replaced = pyw1.replace_contract(
                cur,
                company_code=company,
                previous_contract_id=cid,
                effective_from=date(2026, 9, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 550, "is_basic": True}],
                actor_phone=APPROVER,
                reason=f"wave1_replace_{SUFFIX}",
                expected_row_version=approved_rv,
            )
            check("contract replace ok", replaced.get("ok") is True, replaced)

            # Offer seeds draft only
            seed = pyw1.seed_contract_from_offer(
                cur,
                company_code=company,
                employee_key=f"{EMP_KEY}-OFFER",
                offer={
                    "status": "accepted",
                    "base_salary": 400,
                    "currency": "KWD",
                    "proposed_start_date": "2026-10-01",
                    "offer_id": f"offer-{SUFFIX}",
                },
                actor_phone=CREATOR,
                reason=f"wave1_offer_seed_{SUFFIX}",
            )
            check("offer seeds draft", seed.get("ok") is True and (seed.get("contract") or {}).get("status") == "draft", seed)

            # Period lifecycle
            p_start = date(2026, 8, 1) + timedelta(days=(int(SUFFIX[:2], 16) % 20))
            p_end = p_start + timedelta(days=6)
            period = pyw1.create_period(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="legacy_records",
                actor_phone=CREATOR,
                reason=f"wave1_period_{SUFFIX}",
            )
            check("period create open", period.get("ok") is True and (period.get("period") or {}).get("status") == "open", period)
            pid = str((period.get("period") or {}).get("period_id"))
            prv = int((period.get("period") or {}).get("row_version") or 1)

            locked = pyw1.lock_period(
                cur,
                company_code=company,
                period_id=pid,
                actor_phone=APPROVER,
                reason=f"wave1_lock_{SUFFIX}",
                expected_row_version=prv,
            )
            check("period lock", locked.get("ok") is True and (locked.get("period") or {}).get("status") == "locked", locked)
            prv = int((locked.get("period") or {}).get("row_version") or 1)

            closed = pyw1.close_period(
                cur,
                company_code=company,
                period_id=pid,
                actor_phone=APPROVER,
                reason=f"wave1_close_{SUFFIX}",
                expected_row_version=prv,
            )
            check("period close", closed.get("ok") is True and (closed.get("period") or {}).get("status") == "closed", closed)
            prv = int((closed.get("period") or {}).get("row_version") or 1)

            reopened = pyw1.reopen_period(
                cur,
                company_code=company,
                period_id=pid,
                actor_phone=APPROVER,
                reason=f"wave1_reopen_{SUFFIX}",
                expected_row_version=prv,
            )
            check("period reopen", reopened.get("ok") is True and (reopened.get("period") or {}).get("status") == "open", reopened)

            # Snapshot period + mix enforcement via assert
            snap_period = {
                "attendance_input_source": "approved_snapshots",
                "period_id": str(uuid.uuid4()),
                "period_start": "2026-07-01",
                "period_end": "2026-07-07",
                "status": "open",
                "payroll_mode": "native",
            }
            mix2 = pyw1.assert_period_attendance_source(period=snap_period, requested_source="legacy_records")
            check("authoritative source enforcement", mix2.get("error") == "attendance_source_mix_forbidden")

            q = pyw1.quarantine_smoke_timesheets(cur, company_code=company)
            check("quarantine soft", q.get("ok") is True and q.get("hard_deleted") is False, q)
            # If smoke rows exist on this DB, they must be marked quarantined.
            if q.get("count", 0) > 0:
                check("quarantine marked rows", all(r.get("quarantine_status") == "wave0_smoke_quarantined" for r in (q.get("quarantined") or [])))
            else:
                check("quarantine no-op ok on empty", True)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
