#!/usr/bin/env python3
"""Payroll Wave 1B — production synthetic foundation canary (WATHEFNI only).

Synthetic subjects only (PYW1 / 965539*). No real compensation changes.
payment_processing stays disabled. No G2N / PIFSS / WPS / EOS / payslips / journals / XBRL.
Cleans up synthetic contracts/periods after proof. Never deletes smoke timesheets.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS", "PYW1,PYW1-SYNTH|")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES", "965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import tenant_control_roles as roles  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYW1B_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW1-{TAG}"
REAL_KEY = "WATHEFNI-96566363363"  # known real — must be refused
CREATOR = f"9655391{TAG_DIGITS}"
APPROVER = f"9655392{TAG_DIGITS}"
SUBJECT = f"9655393{TAG_DIGITS}"

SMOKE_IDS = list(pyw1.SMOKE_TIMESHEET_IDS)

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYW1B_EVID") or f"/tmp/payroll-w1b-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {"creator": CREATOR, "approver": APPROVER, "subject": SUBJECT},
    "contract_ids": [],
    "period_ids": [],
}


def check(name: str, ok: bool, detail: object = None) -> None:
    global PASS, FAIL
    RESULTS.append({"name": name, "ok": bool(ok), "detail": None if ok else detail})
    if ok:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} :: {detail}")


def smoke_snapshot(cur) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT timesheet_id::text, employee_key, status, payroll_status, quarantine_status
        FROM payroll_timesheets
        WHERE company_code=%s AND timesheet_id::text = ANY(%s)
        ORDER BY 1
        """,
        (COMPANY, SMOKE_IDS),
    )
    return [dict(r) for r in cur.fetchall()]


def cleanup_synthetic(cur) -> dict[str, Any]:
    """Remove only PYW1 synthetic contracts/periods/events created by this canary."""
    deleted = {"contracts": 0, "periods": 0, "components": 0, "events": 0}
    # Contracts for EMP_KEY and EMP_KEY-OFFER
    cur.execute(
        """
        SELECT contract_id::text FROM payroll_compensation_contracts
        WHERE company_code=%s AND (employee_key=%s OR employee_key=%s OR employee_key LIKE %s)
        """,
        (COMPANY, EMP_KEY, f"{EMP_KEY}-OFFER", f"%PYW1-{TAG}%"),
    )
    cids = [dict(r)["contract_id"] for r in cur.fetchall()]
    if cids:
        cur.execute(
            "DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["events"] += cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["components"] += cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["contracts"] += cur.rowcount or 0
    # Periods tagged in decision_note / metadata via created_by synthetic phones, or decision_note contains tag
    cur.execute(
        """
        SELECT period_id::text FROM payroll_periods
        WHERE company_code=%s
          AND (
            decision_note LIKE %s
            OR created_by_phone = ANY(%s)
            OR reopen_reason LIKE %s
          )
        """,
        (COMPANY, f"%{TAG}%", [CREATOR, APPROVER], f"%{TAG}%"),
    )
    pids = [dict(r)["period_id"] for r in cur.fetchall()]
    if pids:
        cur.execute(
            "DELETE FROM payroll_period_events WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, pids),
        )
        deleted["events"] += cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_periods WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, pids),
        )
        deleted["periods"] += cur.rowcount or 0
    return deleted


def residual_synthetic(cur) -> int:
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM payroll_compensation_contracts
        WHERE company_code=%s AND (employee_key LIKE %s OR employee_key LIKE %s)
        """,
        (COMPANY, f"%PYW1-{TAG}%", f"%PYW1-SYNTH|%{TAG}%"),
    )
    n = int(dict(cur.fetchone())["n"])
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM payroll_periods
        WHERE company_code=%s AND (decision_note LIKE %s OR created_by_phone = ANY(%s))
        """,
        (COMPANY, f"%{TAG}%", [CREATOR, APPROVER]),
    )
    n += int(dict(cur.fetchone())["n"])
    return n


def main() -> int:
    print(f"payroll wave1b prod synthetic canary tag={TAG}")
    check("wave1 enabled", pyw1.payroll_wave1_enabled())
    check("wave1 company", pyw1.payroll_wave1_enabled_for_company(COMPANY))
    check("synthetic_only on", pyw1.payroll_wave1_synthetic_only())
    honesty = pyw1.honesty_payload()
    check("payment_processing disabled", honesty.get("payment_processing") == "disabled")
    check("money_authority false", honesty.get("money_authority") is False)
    check("no g2n", honesty.get("gross_to_net") is False)
    check("art70=6", honesty.get("annual_leave_eligibility_months") == 6)
    check("sod pair warns", len(roles.sod_warnings(["payroll.approve", "payroll.export"])) >= 1)

    payroll_ops = set(app.hr_role_permissions("payroll_operator"))
    check("operator has approve", "payroll.approve" in payroll_ops)
    check("operator lacks export", "payroll.export" not in payroll_ops)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("db is wathefni", db == "wathefni", db)

            smoke_before = smoke_snapshot(cur)
            check("smoke rows exist (2)", len(smoke_before) == 2, smoke_before)
            check(
                "smoke quarantined",
                all(r.get("quarantine_status") == "wave0_smoke_quarantined" for r in smoke_before),
                smoke_before,
            )
            check(
                "smoke not hard-deleted",
                all(r.get("timesheet_id") for r in smoke_before),
                smoke_before,
            )

            # Refuse real employee mutation under SYNTHETIC_ONLY
            real_deny = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=REAL_KEY,
                effective_from=date(2026, 8, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 1, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"pyw1b_real_deny_{TAG}",
            )
            check("real employee contract refused", real_deny.get("error") == "payroll_synthetic_only", real_deny)

            # Modes
            for mode in ("native", "external", "parallel_shadow"):
                mode_res = pyw1.set_payroll_mode(
                    cur,
                    company_code=COMPANY,
                    mode=mode,
                    actor_phone=APPROVER,
                    reason=f"pyw1b_mode_{mode}_{TAG}",
                )
                check(f"mode {mode}", mode_res.get("ok") is True, mode_res)
            settings = pyw1.ensure_company_settings(cur, company_code=COMPANY)
            check("settings payment disabled", settings.get("payment_processing") == "disabled")

            # Contract lifecycle
            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"pyw1b_draft_{TAG}",
            )
            check("contract draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id") or "")
            IDS["contract_ids"].append(cid)
            rv = int((draft.get("contract") or {}).get("row_version") or 1)

            self_deny = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=CREATOR,
                reason=f"pyw1b_self_{TAG}",
                expected_row_version=rv,
            )
            check("creator self-approve denied", self_deny.get("error") == "self_approval_forbidden", self_deny)

            approved = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"pyw1b_approve_{TAG}",
                expected_row_version=rv,
            )
            check("contract approve", approved.get("ok") is True, approved)
            approved_rv = int((approved.get("contract") or {}).get("row_version") or 0)

            draft2 = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 15),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"pyw1b_overlap_{TAG}",
            )
            cid2 = str((draft2.get("contract") or {}).get("contract_id") or "")
            IDS["contract_ids"].append(cid2)
            overlap = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid2,
                actor_phone=APPROVER,
                reason=f"pyw1b_overlap_try_{TAG}",
                expected_row_version=int((draft2.get("contract") or {}).get("row_version") or 1),
            )
            check("overlap denied", overlap.get("error") == "overlapping_approved_contract", overlap)

            replaced = pyw1.replace_contract(
                cur,
                company_code=COMPANY,
                previous_contract_id=cid,
                effective_from=date(2026, 9, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 550, "is_basic": True}],
                actor_phone=APPROVER,
                reason=f"pyw1b_replace_{TAG}",
                expected_row_version=approved_rv,
            )
            check("contract replace", replaced.get("ok") is True, replaced)
            if replaced.get("ok"):
                IDS["contract_ids"].append(str((replaced.get("contract") or {}).get("contract_id") or ""))

            seed = pyw1.seed_contract_from_offer(
                cur,
                company_code=COMPANY,
                employee_key=f"{EMP_KEY}-OFFER",
                offer={
                    "status": "accepted",
                    "base_salary": 400,
                    "currency": "KWD",
                    "proposed_start_date": "2026-10-01",
                    "offer_id": f"offer-pyw1b-{TAG}",
                },
                actor_phone=CREATOR,
                reason=f"pyw1b_offer_{TAG}",
            )
            check("offer seeds draft only", seed.get("ok") is True and (seed.get("contract") or {}).get("status") == "draft", seed)
            if seed.get("ok"):
                IDS["contract_ids"].append(str((seed.get("contract") or {}).get("contract_id") or ""))

            # Period lifecycle
            p_start = date(2026, 11, 1) + timedelta(days=(int(TAG[:2], 16) % 10))
            p_end = p_start + timedelta(days=6)
            period = pyw1.create_period(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="legacy_records",
                actor_phone=CREATOR,
                reason=f"pyw1b_period_{TAG}",
            )
            check("period open", period.get("ok") is True and (period.get("period") or {}).get("status") == "open", period)
            pid = str((period.get("period") or {}).get("period_id") or "")
            IDS["period_ids"].append(pid)
            prv = int((period.get("period") or {}).get("row_version") or 1)

            locked = pyw1.lock_period(
                cur, company_code=COMPANY, period_id=pid, actor_phone=APPROVER, reason=f"pyw1b_lock_{TAG}", expected_row_version=prv
            )
            check("period lock", locked.get("ok") is True, locked)
            prv = int((locked.get("period") or {}).get("row_version") or 1)
            closed = pyw1.close_period(
                cur, company_code=COMPANY, period_id=pid, actor_phone=APPROVER, reason=f"pyw1b_close_{TAG}", expected_row_version=prv
            )
            check("period close", closed.get("ok") is True, closed)
            prv = int((closed.get("period") or {}).get("row_version") or 1)
            reopened = pyw1.reopen_period(
                cur, company_code=COMPANY, period_id=pid, actor_phone=APPROVER, reason=f"pyw1b_reopen_{TAG}", expected_row_version=prv
            )
            check("period reopen", reopened.get("ok") is True and (reopened.get("period") or {}).get("status") == "open", reopened)

            mix = pyw1.assert_period_attendance_source(
                period={"attendance_input_source": "legacy_records"},
                requested_source="approved_snapshots",
            )
            check("source mix forbidden", mix.get("error") == "attendance_source_mix_forbidden")

            export = pyw1.build_input_export(
                company_code=COMPANY,
                period={
                    "period_id": pid,
                    "period_start": str(p_start),
                    "period_end": str(p_end),
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
            check("input export stub", export.get("ok") is True, export)
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

            smoke_mid = smoke_snapshot(cur)
            check("smoke still quarantined mid-run", all(r.get("quarantine_status") == "wave0_smoke_quarantined" for r in smoke_mid), smoke_mid)

            deleted = cleanup_synthetic(cur)
            residual = residual_synthetic(cur)
            check("cleanup residual zero", residual == 0, {"deleted": deleted, "residual": residual})
            IDS["cleanup"] = deleted
            IDS["residual_total"] = residual

            smoke_after = smoke_snapshot(cur)
            check("smoke still present after cleanup", len(smoke_after) == 2, smoke_after)
            check(
                "smoke still quarantined after cleanup",
                all(r.get("quarantine_status") == "wave0_smoke_quarantined" for r in smoke_after),
                smoke_after,
            )

            # Restore mode to external (safe default when customer may have external engine) — still no money
            pyw1.set_payroll_mode(
                cur,
                company_code=COMPANY,
                mode="external",
                actor_phone=APPROVER,
                reason=f"pyw1b_restore_external_{TAG}",
            )
            final_settings = pyw1.ensure_company_settings(cur, company_code=COMPANY)
            check("final payment disabled", final_settings.get("payment_processing") == "disabled")

        conn.commit()

    qual = {
        "stamp_tag": TAG,
        "passed": PASS,
        "failed": FAIL,
        "ids": IDS,
        "honesty": honesty,
        "cleanup": {"residual_total": IDS.get("residual_total"), **(IDS.get("cleanup") or {})},
        "smoke_ids": SMOKE_IDS,
        "payment_processing": "disabled",
        "money_authority": False,
        "wave": "payroll_wave1b_prod_synthetic",
    }
    (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(json.dumps({"passed": PASS, "failed": FAIL, "evid": str(EVID)}, indent=2))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
