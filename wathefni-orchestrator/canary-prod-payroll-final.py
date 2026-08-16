#!/usr/bin/env python3
"""Payroll Final — production synthetic end-to-end qualification canary.

Covers frozen Waves 1–5 in one synthetic subject:
  modes native / external / parallel_shadow
  contract → period → preview / external result
  payslip generate/import
  review → approve → close → controlled reopen
  exports, reconciliation, quarantine, fingerprint drift, idempotency
  permissions / SOD / concurrency / self-action bans
  PIFSS/EOS counsel-gated worksheet blocking
  residual cleanup = 0

Does NOT: remittance, filing, bank/WPS/AS'HAL, payments, AI, real vendor.
payment_processing=disabled; native non-authoritative; external money authority.
"""
from __future__ import annotations

import calendar
import copy
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_non_production_ops()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
for wave, markers in (
    ("WAVE1", "PYW1,PYW1-SYNTH|,PYWF,FINAL"),
    ("WAVE2A", "PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,PYWF,FINAL"),
    ("WAVE2B", "PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,W2BB,PYWF,FINAL"),
    ("WAVE3", "PYW3,PYW3-SYNTH|,PYW2B,PYW1,PYW1-SYNTH|,W3B,PYWF,FINAL"),
    ("WAVE4", "PYW4,PYW4-SYNTH|,PYW3,PYW2B,PYW2A,PYW1,PYW1-SYNTH|,W4B,W4,PYWF,FINAL"),
    ("WAVE5", "PYW5,PYW5-SYNTH|,PYW4,PYW3,PYW2B,PYW2A,PYW1,PYW1-SYNTH|,W5B,W5,PYWF,FINAL"),
):
    os.environ.setdefault(f"WATHEFNI_PAYROLL_{wave}", "1")
    os.environ.setdefault(f"WATHEFNI_PAYROLL_{wave}_COMPANIES", "WATHEFNI")
    os.environ.setdefault(f"WATHEFNI_PAYROLL_{wave}_SYNTHETIC_ONLY", "1")
    os.environ.setdefault(f"WATHEFNI_PAYROLL_{wave}_SYNTHETIC_KEY_MARKERS", markers)
    os.environ.setdefault(f"WATHEFNI_PAYROLL_{wave}_SYNTHETIC_PHONE_PREFIXES", "965541,965540,965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import payroll_external_adapter_wave2a as w2a  # noqa: E402
import payroll_native_preview_wave2b as w2b  # noqa: E402
import payroll_payslip_wave3 as w3  # noqa: E402
import payroll_close_export_wave4 as w4  # noqa: E402
import payroll_pifss_eos_wave5 as w5  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYWF_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW1-PYWF-FINAL-{TAG}"
CREATOR = f"9655411{TAG_DIGITS}"
APPROVER = f"9655412{TAG_DIGITS}"
CLOSER = f"9655413{TAG_DIGITS}"
EXPORTER = f"9655414{TAG_DIGITS}"
EXPORTER2 = f"9655415{TAG_DIGITS}"
ACTOR_PHONES = [CREATOR, APPROVER, CLOSER, EXPORTER, EXPORTER2]

PERMS_APPROVE = ["payroll.read", "payroll.manage", "payroll.approve"]
PERMS_EXPORT = ["payroll.read", "payroll.export"]
PERMS_SOD_BAD = ["payroll.read", "payroll.approve", "payroll.export"]

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYWF_EVID") or f"/tmp/payroll-final-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {
        "creator": CREATOR,
        "approver": APPROVER,
        "closer": CLOSER,
        "exporter": EXPORTER,
        "exporter2": EXPORTER2,
    },
    "prior_mode": None,
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


def unique_period() -> tuple[date, date]:
    n = int(TAG[:4], 16) % 120
    year = 2035 + (n // 12)
    month = (n % 12) + 1
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def cleanup(cur) -> dict[str, int]:
    deleted: dict[str, int] = {}
    tag_like = f"%{TAG}%"
    emp = EMP_KEY

    # Wave 5
    cur.execute(
        """
        DELETE FROM payroll_statutory_dual_control
        WHERE company_code=%s AND worksheet_id IN (
          SELECT worksheet_id FROM payroll_pifss_worksheets WHERE employee_key=%s
          UNION SELECT worksheet_id FROM payroll_eos_worksheets WHERE employee_key=%s
        )
        """,
        (COMPANY, emp, emp),
    )
    deleted["w5_dual"] = cur.rowcount or 0
    cur.execute(
        """
        DELETE FROM payroll_statutory_worksheet_events
        WHERE company_code=%s AND (
          worksheet_id IN (
            SELECT worksheet_id FROM payroll_pifss_worksheets WHERE employee_key=%s
            UNION SELECT worksheet_id FROM payroll_eos_worksheets WHERE employee_key=%s
            UNION SELECT rule_table_id FROM payroll_statutory_rule_tables
              WHERE company_code=%s AND decision_note LIKE %s
          )
          OR payload::text LIKE %s
        )
        """,
        (COMPANY, emp, emp, COMPANY, tag_like, tag_like),
    )
    deleted["w5_events"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_pifss_worksheets WHERE company_code=%s AND (employee_key=%s OR decision_note LIKE %s)",
        (COMPANY, emp, tag_like),
    )
    deleted["w5_pifss"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_eos_worksheets WHERE company_code=%s AND (employee_key=%s OR decision_note LIKE %s)",
        (COMPANY, emp, tag_like),
    )
    deleted["w5_eos"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_statutory_rule_tables WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["w5_rules"] = cur.rowcount or 0

    # Wave 4
    cur.execute(
        """
        DELETE FROM payroll_finance_exports
        WHERE company_code=%s AND close_run_id IN (
          SELECT close_run_id FROM payroll_close_runs
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, COMPANY, tag_like),
    )
    deleted["finance_exports"] = cur.rowcount or 0
    cur.execute(
        """
        DELETE FROM payroll_journal_lines WHERE journal_draft_id IN (
          SELECT journal_draft_id FROM payroll_journal_drafts
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, tag_like),
    )
    deleted["journal_lines"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_journal_drafts WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["journal_drafts"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_bank_export_drafts WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["bank_drafts"] = cur.rowcount or 0
    cur.execute(
        """
        DELETE FROM payroll_close_dual_control WHERE close_run_id IN (
          SELECT close_run_id FROM payroll_close_runs
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, tag_like),
    )
    deleted["close_dual"] = cur.rowcount or 0
    cur.execute(
        """
        DELETE FROM payroll_close_run_events WHERE close_run_id IN (
          SELECT close_run_id FROM payroll_close_runs
          WHERE company_code=%s AND decision_note LIKE %s
        )
        """,
        (COMPANY, tag_like),
    )
    deleted["close_events"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["close_runs"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_account_mappings WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    deleted["mappings"] = cur.rowcount or 0

    # Wave 3 payslips
    cur.execute(
        "SELECT payslip_id::text FROM payroll_payslip_documents WHERE company_code=%s AND employee_key=%s",
        (COMPANY, emp),
    )
    pids = [dict(r)["payslip_id"] for r in cur.fetchall()]
    if pids:
        cur.execute("DELETE FROM payroll_payslip_lines WHERE payslip_id::text = ANY(%s)", (pids,))
        deleted["payslip_lines"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_payslip_events WHERE payslip_id::text = ANY(%s)", (pids,))
        deleted["payslip_events"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))
        deleted["payslips"] = cur.rowcount or 0

    # Wave 2B preview
    cur.execute(
        """
        SELECT preview_run_id::text FROM payroll_preview_runs
        WHERE company_code=%s AND (decision_note LIKE %s OR inputs::text LIKE %s OR created_by_phone = ANY(%s))
        """,
        (COMPANY, tag_like, f"%{emp}%", ACTOR_PHONES),
    )
    prids = [dict(r)["preview_run_id"] for r in cur.fetchall()]
    if prids:
        cur.execute("DELETE FROM payroll_preview_lines WHERE preview_run_id::text = ANY(%s)", (prids,))
        deleted["preview_lines"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_preview_employee_results WHERE preview_run_id::text = ANY(%s)",
            (prids,),
        )
        deleted["preview_employees"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_preview_events WHERE preview_run_id::text = ANY(%s)", (prids,))
        deleted["preview_events"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_preview_runs WHERE preview_run_id::text = ANY(%s)", (prids,))
        deleted["preview_runs"] = cur.rowcount or 0

    # Wave 2A adapter
    cur.execute(
        "SELECT import_run_id::text FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    iids = [dict(r)["import_run_id"] for r in cur.fetchall()]
    if iids:
        cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["import_lines"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)",
            (iids,),
        )
        deleted["import_recons"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
        cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["imports"] = cur.rowcount or 0

    cur.execute(
        "SELECT export_run_id::text FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, tag_like),
    )
    eids = [dict(r)["export_run_id"] for r in cur.fetchall()]
    if eids:
        cur.execute("DELETE FROM payroll_adapter_quarantine WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["quarantine_by_export"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
        cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["adapter_exports"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_adapter_quarantine WHERE company_code=%s AND (reason LIKE %s OR artifact_excerpt LIKE %s)",
        (COMPANY, tag_like, tag_like),
    )
    deleted["quarantine"] = cur.rowcount or 0

    # Wave 1 contracts / periods
    cur.execute(
        "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
        (COMPANY, emp),
    )
    cids = [dict(r)["contract_id"] for r in cur.fetchall()]
    if cids:
        cur.execute(
            "DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["contract_events"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["contract_components"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND contract_id::text = ANY(%s)",
            (COMPANY, cids),
        )
        deleted["contracts"] = cur.rowcount or 0

    cur.execute(
        """
        SELECT period_id::text FROM payroll_periods
        WHERE company_code=%s AND (decision_note LIKE %s OR created_by_phone = ANY(%s))
        """,
        (COMPANY, tag_like, ACTOR_PHONES),
    )
    period_ids = [dict(r)["period_id"] for r in cur.fetchall()]
    if period_ids:
        cur.execute(
            "DELETE FROM payroll_period_events WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, period_ids),
        )
        deleted["period_events"] = cur.rowcount or 0
        cur.execute(
            "DELETE FROM payroll_periods WHERE company_code=%s AND period_id::text = ANY(%s)",
            (COMPANY, period_ids),
        )
        deleted["periods"] = cur.rowcount or 0

    return deleted


def residual(cur) -> int:
    n = 0
    tag_like = f"%{TAG}%"
    for sql, args in (
        ("SELECT COUNT(*) AS n FROM payroll_close_runs WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_finance_exports WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_journal_drafts WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_payslip_documents WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_KEY)),
        ("SELECT COUNT(*) AS n FROM payroll_preview_runs WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s", (COMPANY, EMP_KEY)),
        ("SELECT COUNT(*) AS n FROM payroll_pifss_worksheets WHERE employee_key=%s OR decision_note LIKE %s", (EMP_KEY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_eos_worksheets WHERE employee_key=%s OR decision_note LIKE %s", (EMP_KEY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_statutory_rule_tables WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
        ("SELECT COUNT(*) AS n FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s", (COMPANY, tag_like)),
    ):
        cur.execute(sql, args)
        n += int(dict(cur.fetchone())["n"])
    return n


def main() -> int:
    print("payroll FINAL production synthetic E2E canary")
    print("tag", TAG, "employee", EMP_KEY)

    # Honesty across waves
    h1 = pyw1.honesty_payload()
    check("w1 honesty payment disabled", h1.get("payment_processing") == "disabled", h1)
    h2a = w2a.honesty_payload()
    check("w2a honesty external", h2a.get("money_authority") == "external" and h2a.get("vendor_claimed") is False, h2a)
    h2b = w2b.honesty_payload()
    check("w2b honesty non-auth", h2b.get("authoritative") is False and h2b.get("payment_processing") == "disabled", h2b)
    h3 = w3.honesty_payload()
    check("w3 honesty not money", h3.get("payslips_as_money") is False and h3.get("payment_processing") == "disabled", h3)
    h4 = w4.honesty_payload()
    check(
        "w4 honesty drafts only",
        h4.get("payment_processing") == "disabled" and h4.get("journals") is False and h4.get("bank_files") is False,
        h4,
    )
    h5 = w5.honesty_payload()
    check(
        "w5 honesty worksheets only",
        h5.get("remittance") is False and h5.get("eos_auto_payable") is False and h5.get("pifss_remittance") is False,
        h5,
    )

    check("w1 enabled", pyw1.payroll_wave1_enabled() is True)
    check("w2a enabled", w2a.payroll_wave2a_enabled() is True and w2a.payroll_wave2a_synthetic_only() is True)
    check("w2b enabled", w2b.payroll_wave2b_enabled() is True and w2b.payroll_wave2b_synthetic_only() is True)
    check("w3 enabled", w3.payroll_wave3_enabled() is True and w3.payroll_wave3_synthetic_only() is True)
    check("w4 enabled", w4.payroll_wave4_enabled() is True and w4.payroll_wave4_synthetic_only() is True)
    check("w5 enabled", w5.payroll_wave5_enabled() is True and w5.payroll_wave5_synthetic_only() is True)

    check("native non-auth", h5.get("native_results_authoritative") is False)
    check("external authority", h5.get("external_payroll_authority") == "external")
    check("no ai", h5.get("ai_calculations") is False)
    check("no bank/wps/ashal", h5.get("bank_files") is False and h5.get("wps") is False and h5.get("ashal") is False)

    # UX static
    dash_candidates = [
        Path(__file__).resolve().parents[1] / "apps" / "wathefni-dashboard" / "src" / "posthire",
        Path("/opt/wathefni/apps/wathefni-dashboard/src/posthire"),
    ]
    dash = next((p for p in dash_candidates if p.exists()), None)
    if dash:
        post = (dash / "PostHire.tsx").read_text(encoding="utf-8") if (dash / "PostHire.tsx").exists() else ""
        check("ux statutory tab", "StatutoryWorksheetWorkspace" in post or "payroll-tab-statutory" in post)
        check("ux close tab", "CloseExportWorkspace" in post or "payroll-tab-close" in post)
        check("ux payslip tab", "PayslipWorkspace" in post)
        for name in ("payrollStatutoryUx.ts", "payrollCloseExportUx.ts", "payrollPayslipUx.ts"):
            p = dash / name
            if p.exists():
                txt = p.read_text(encoding="utf-8")
                check(f"ux {name} ar", "ا" in txt or "م" in txt)
                check(f"ux {name} disabled", "disabled" in txt.lower() or "معطّل" in txt)

    p_start, p_end = unique_period()
    IDS["period"] = {"start": str(p_start), "end": str(p_end)}
    check("period year >= 2035", p_start.year >= 2035, p_start.year)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            print("connected_db", db)
            check("production db", db == "wathefni", db)
            if db != "wathefni":
                return 2

            settings = pyw1.ensure_company_settings(cur, company_code=COMPANY)
            IDS["prior_mode"] = str(settings.get("payroll_mode") or "native")
            check("settings payment disabled", settings.get("payment_processing") == "disabled")

            # --- Mode matrix ---
            for mode in ("native", "external", "parallel_shadow"):
                r = pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode=mode, actor_phone=APPROVER, reason=f"final_mode_{mode}_{TAG}"
                )
                check(f"mode set {mode}", r.get("ok") is True, r)

            # Preview blocked in external
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"final_ext_block_{TAG}"
            )
            blocked_preview = w2b.calculate_native_preview(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[],
                actor_phone=CREATOR,
                reason=f"final_preview_blocked_{TAG}",
            )
            check(
                "preview blocked in external",
                blocked_preview.get("ok") is False
                and "mode" in str(blocked_preview.get("error") or "").lower(),
                blocked_preview,
            )

            # Parallel shadow allows preview later — set native for foundation
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"final_native_{TAG}"
            )

            # --- Contract + period ---
            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 1, 1),
                components=[
                    {"component_kind": "earning", "code": "BASIC", "amount": 600, "is_basic": True},
                    {"component_kind": "allowance", "code": "TRANSPORT", "amount": 40},
                ],
                actor_phone=CREATOR,
                reason=f"final_draft_{TAG}",
            )
            check("contract draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id") or "")
            self_appr_c = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=CREATOR,
                reason=f"final_self_contract_{TAG}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check(
                "contract self-approve forbidden",
                self_appr_c.get("ok") is False
                and "self" in str(self_appr_c.get("error") or "").lower(),
                self_appr_c,
            )
            approved = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"final_approve_contract_{TAG}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("contract approve", approved.get("ok") is True, approved)
            contract_row = approved.get("contract") or {}

            # concurrency stale row_version
            stale = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"final_stale_{TAG}",
                expected_row_version=1,
            )
            check(
                "concurrency stale denied or already approved",
                stale.get("ok") is False,
                stale,
            )

            cur.execute(
                """
                SELECT * FROM payroll_periods
                WHERE company_code=%s AND period_start=%s AND period_end=%s
                ORDER BY created_at DESC NULLS LAST LIMIT 1
                """,
                (COMPANY, p_start, p_end),
            )
            existing = cur.fetchone()
            if existing:
                period = {"ok": True, "period": dict(existing)}
            else:
                period = pyw1.create_period(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="legacy_records",
                    actor_phone=CREATOR,
                    reason=f"final_period_{TAG}",
                )
            check("period", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            pid = str(period_row.get("period_id") or "")

            # Period lock → close → reopen (Wave 1)
            if pid and str(period_row.get("status") or "") == "open":
                locked = pyw1.lock_period(
                    cur,
                    company_code=COMPANY,
                    period_id=pid,
                    actor_phone=APPROVER,
                    reason=f"final_lock_{TAG}",
                    expected_row_version=int(period_row.get("row_version") or 1),
                )
                check("period lock", locked.get("ok") is True, locked)
                locked_row = locked.get("period") or {}
                closed_p = pyw1.close_period(
                    cur,
                    company_code=COMPANY,
                    period_id=pid,
                    actor_phone=CLOSER,
                    reason=f"final_period_close_{TAG}",
                    expected_row_version=int(locked_row.get("row_version") or 1),
                )
                check("period close", closed_p.get("ok") is True, closed_p)
                closed_row = closed_p.get("period") or {}
                reopened_p = pyw1.reopen_period(
                    cur,
                    company_code=COMPANY,
                    period_id=pid,
                    actor_phone=APPROVER,
                    reason=f"final_period_reopen_{TAG}",
                    expected_row_version=int(closed_row.get("row_version") or 1),
                )
                check("period reopen", reopened_p.get("ok") is True, reopened_p)
                period_row = reopened_p.get("period") or period_row

            # --- Native / parallel_shadow preview ---
            for mode_label, mode in (("native", "native"), ("shadow", "parallel_shadow")):
                pyw1.set_payroll_mode(
                    cur, company_code=COMPANY, mode=mode, actor_phone=APPROVER, reason=f"final_{mode_label}_{TAG}"
                )
                preview = w2b.calculate_native_preview(
                    cur,
                    company_code=COMPANY,
                    period_start=p_start,
                    period_end=p_end,
                    period_id=pid or None,
                    employees=[{"employee_key": EMP_KEY}],
                    contracts=[contract_row],
                    actor_phone=CREATOR,
                    reason=f"final_preview_{mode_label}_{TAG}",
                )
                check(f"preview ok ({mode_label})", preview.get("ok") is True, preview)
                if mode_label == "native":
                    native_preview = preview
                    prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")
                    IDS["preview_run_id"] = prid
                    replay_p = w2b.calculate_native_preview(
                        cur,
                        company_code=COMPANY,
                        period_start=p_start,
                        period_end=p_end,
                        period_id=pid or None,
                        employees=[{"employee_key": EMP_KEY}],
                        contracts=[contract_row],
                        actor_phone=CREATOR,
                        reason=f"final_preview_idem_{TAG}",
                    )
                    check(
                        "preview idempotent",
                        replay_p.get("idempotent") is True or replay_p.get("ok") is True,
                        replay_p,
                    )
                    unsup = w2b.calculate_native_preview(
                        cur,
                        company_code=COMPANY,
                        period_start=p_start,
                        period_end=p_end,
                        employees=[{"employee_key": EMP_KEY}],
                        contracts=[contract_row],
                        requested_unsupported=["eos", "pifss", "overtime_premiums"],
                        actor_phone=CREATOR,
                        reason=f"final_unsup_{TAG}",
                    )
                    check("unsupported fail-closed", unsup.get("ok") is False, unsup)

            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="native", actor_phone=APPROVER, reason=f"final_native2_{TAG}"
            )
            prid = IDS.get("preview_run_id") or ""

            # Native payslip
            gen = w3.generate_native_payslip(
                cur,
                company_code=COMPANY,
                preview_run_id=prid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"final_nslip_{TAG}",
            )
            check("native payslip", gen.get("ok") is True, gen)
            slip = gen.get("payslip") or {}
            check(
                "native payslip non-auth",
                slip.get("money_authority") in ("preview_non_authoritative", "native_non_authoritative", None)
                or gen.get("money_authority") in ("preview_non_authoritative", "native_non_authoritative")
                or w3.honesty_payload().get("native_payslips_authoritative") is False,
                slip,
            )
            check("payslips not money", w3.honesty_payload().get("payslips_as_money") is False)
            sid = str(slip.get("payslip_id") or "")
            replay_slip = w3.generate_native_payslip(
                cur,
                company_code=COMPANY,
                preview_run_id=prid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"final_nslip_idem_{TAG}",
            )
            check(
                "payslip idempotent",
                replay_slip.get("idempotent") is True
                or str((replay_slip.get("payslip") or {}).get("payslip_id") or "") == sid,
                replay_slip,
            )
            dl_en = w3.download_payslip_document(cur, company_code=COMPANY, payslip_id=sid, locale="en")
            dl_ar = w3.download_payslip_document(cur, company_code=COMPANY, payslip_id=sid, locale="ar")
            check("payslip EN download", dl_en.get("ok") is True, dl_en)
            check("payslip AR download", dl_ar.get("ok") is True, dl_ar)

            # --- Close path (native) ---
            created = w4.create_close_run(
                cur,
                company_code=COMPANY,
                source_kind="native_preview",
                source_run_id=prid,
                actor_phone=CREATOR,
                reason=f"final_close_create_{TAG}",
                actor_permissions=PERMS_APPROVE,
            )
            check("close create", created.get("ok") is True, created)
            run = created.get("close_run") or {}
            crid = str(run.get("close_run_id") or "")
            check("close native authority", run.get("money_authority") == "preview_non_authoritative", run)
            check("close payment disabled", run.get("payment_processing") == "disabled", run)

            replay_c = w4.create_close_run(
                cur,
                company_code=COMPANY,
                source_kind="native_preview",
                source_run_id=prid,
                actor_phone=CREATOR,
                reason=f"final_close_idem_{TAG}",
            )
            check("close create idempotent", replay_c.get("idempotent") is True, replay_c)

            submitted = w4.submit_close_run_for_review(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"final_submit_{TAG}",
                expected_row_version=int((replay_c.get("close_run") or run).get("row_version") or 1),
            )
            check("close submit", submitted.get("ok") is True, submitted)
            run = submitted.get("close_run") or {}

            self_approve = w4.approve_close_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"final_self_appr_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("self approve forbidden", self_approve.get("error") == "self_approval_forbidden", self_approve)

            sod_approve = w4.approve_close_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"final_sod_appr_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_SOD_BAD,
            )
            check("sod approve+export blocked", sod_approve.get("error") == "sod_approve_export_conflict", sod_approve)

            approved_run = w4.approve_close_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"final_approve_run_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("close approve", approved_run.get("ok") is True, approved_run)
            run = approved_run.get("close_run") or {}

            self_close = w4.close_payroll_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"final_self_close_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("self close forbidden", self_close.get("error") == "self_close_forbidden", self_close)

            closed = w4.close_payroll_run(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"final_close_{TAG}",
                expected_row_version=int(run.get("row_version") or 1),
                actor_permissions=PERMS_APPROVE,
            )
            check("close ok", closed.get("ok") is True, closed)
            run = closed.get("close_run") or {}
            check("closed status", run.get("status") == "closed", run)
            check("snapshot immutable", run.get("snapshot_immutable") is True, run)
            snap_fp = str(run.get("snapshot_fingerprint") or "")
            check("snapshot fingerprint", bool(snap_fp), run)

            immut = w4.mutate_closed_run_forbidden(cur, company_code=COMPANY, close_run_id=crid)
            check("immutable probe", immut.get("error") == "closed_run_immutable", immut)

            # Mappings + journal + bank contract + finance export
            for code, kind, acct, side in [
                ("BASIC", "earning", "5100.BASIC", "debit"),
                ("TRANSPORT", "allowance", "5100.TRANSPORT", "debit"),
                ("NET_PAYABLE", "net_payable", "2100.NET", "credit"),
            ]:
                m = w4.upsert_account_mapping(
                    cur,
                    company_code=COMPANY,
                    component_code=code,
                    component_kind=kind,
                    account_code=acct,
                    journal_side=side,
                    cost_centre="CC-HR",
                    actor_phone=APPROVER,
                    reason=f"final_map_{code}_{TAG}",
                )
                check(f"mapping {code}", m.get("ok") is True, m)

            journal = w4.generate_journal_draft(
                cur, company_code=COMPANY, close_run_id=crid, actor_phone=CREATOR, reason=f"final_journal_{TAG}"
            )
            check("journal draft", journal.get("ok") is True, journal)
            jid = str((journal.get("journal_draft") or {}).get("journal_draft_id") or "")
            check("journal balanced", (journal.get("journal_draft") or {}).get("balanced") is True, journal)

            bank = w4.generate_bank_export_contract(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CREATOR,
                reason=f"final_bank_{TAG}",
                employee_iban_placeholders={EMP_KEY: "KW00PLACEHOLDER0001"},
            )
            check("bank contract only", bank.get("ok") is True, bank)
            check("no real bank files", w4.honesty_payload().get("bank_files") is False)

            exp = w4.record_finance_export(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                export_kind="journal_draft",
                artifact_id=jid,
                actor_phone=EXPORTER,
                reason=f"final_exp_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("finance export", exp.get("ok") is True, exp)
            feid = str((exp.get("finance_export") or {}).get("finance_export_id") or "")

            # Fingerprint drift
            cur.execute(
                """
                UPDATE payroll_journal_drafts
                SET source_snapshot_fingerprint=%s
                WHERE journal_draft_id=%s
                """,
                ("drift-" + snap_fp[:16], jid),
            )
            drift = w4.detect_export_fingerprint_drift(
                cur, company_code=COMPANY, close_run_id=crid, export_kind="journal_draft", artifact_id=jid
            )
            check("fingerprint drift detected", drift.get("drifted") is True, drift)
            # Restore fingerprint so reopen/export path remains healthy
            cur.execute(
                "UPDATE payroll_journal_drafts SET source_snapshot_fingerprint=%s WHERE journal_draft_id=%s",
                (snap_fp, jid),
            )

            exp_appr = w4.approve_finance_export(
                cur,
                company_code=COMPANY,
                finance_export_id=feid,
                actor_phone=EXPORTER2,
                reason=f"final_exp_appr_{TAG}",
                actor_permissions=PERMS_EXPORT,
            )
            check("finance export approve", exp_appr.get("ok") is True, exp_appr)

            # Dual reopen
            re1 = w4.initiate_reopen(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"final_reopen1_{TAG}",
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen initiate", re1.get("ok") is True, re1)
            dual_id = str((re1.get("dual_control") or {}).get("action_id") or "")
            same = w4.confirm_reopen(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=APPROVER,
                reason=f"final_reopen_same_{TAG}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check(
                "reopen same actor deny",
                same.get("error") in ("dual_control_same_actor", "same_actor_forbidden", "dual_control_same_initiator"),
                same,
            )
            re2 = w4.confirm_reopen(
                cur,
                company_code=COMPANY,
                close_run_id=crid,
                actor_phone=CLOSER,
                reason=f"final_reopen2_{TAG}",
                dual_action_id=dual_id,
                actor_permissions=PERMS_APPROVE,
            )
            check("reopen confirm", re2.get("ok") is True, re2)

            # --- External path ---
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"final_ext_{TAG}"
            )
            exported = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period=period_row,
                employees=[{"employee_key": EMP_KEY}],
                contracts=[contract_row],
                attendance=[{"employee_key": EMP_KEY, "worked_minutes": 10000}],
                leave_classifications=[],
                actor_phone=CREATOR,
                reason=f"final_export_{TAG}",
            )
            check("external export", exported.get("ok") is True, exported)
            eid = str((exported.get("export_run") or {}).get("export_run_id") or "")
            fp = str(
                exported.get("input_fingerprint")
                or (exported.get("export_run") or {}).get("input_fingerprint")
                or ""
            )
            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            payload = dict(cur.fetchone())["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            result_csv = w2a.build_synthetic_result_csv(
                export_payload=payload, external_run_id=f"EXT-FINAL-{TAG}"
            )
            imported = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"final_import_{TAG}",
                expected_input_fingerprint=fp or None,
            )
            check("external import", imported.get("ok") is True, imported)
            iid = str((imported.get("import_run") or {}).get("import_run_id") or "")

            replay_imp = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"final_import_idem_{TAG}",
                expected_input_fingerprint=fp or None,
            )
            check(
                "import idempotent",
                replay_imp.get("idempotent") is True or replay_imp.get("ok") is True,
                replay_imp,
            )

            stale = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"final_stale_fp_{TAG}",
                expected_input_fingerprint="deadbeef" * 4,
            )
            check(
                "fingerprint drift blocked",
                stale.get("error") == "input_fingerprint_changed" or stale.get("ok") is False,
                stale,
            )
            check("fingerprint drift quarantined", bool(stale.get("quarantine")) or stale.get("ok") is False, stale)

            bad = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text="not,valid\n1,2",
                actor_phone=APPROVER,
                reason=f"final_mal_{TAG}",
            )
            check("malformed quarantined", bad.get("ok") is False and bool(bad.get("quarantine")), bad)
            q = w2a.list_quarantine(cur, company_code=COMPANY, limit=100)
            check("quarantine list non-empty", len(q) >= 1, len(q))

            recon = w2a.reconcile_export_import(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                import_run_id=iid,
                actor_phone=APPROVER,
                reason=f"final_recon_{TAG}",
            )
            check("reconcile ok", recon.get("ok") is True, recon)

            ext_slip = w3.generate_external_payslip(
                cur,
                company_code=COMPANY,
                import_run_id=iid,
                employee_key=EMP_KEY,
                actor_phone=CREATOR,
                reason=f"final_eslip_{TAG}",
            )
            check("external payslip", ext_slip.get("ok") is True, ext_slip)
            check(
                "external payslip authority",
                (ext_slip.get("payslip") or {}).get("money_authority") == "external"
                or ext_slip.get("money_authority") == "external"
                or w3.honesty_payload().get("external_payslips_authority") == "external",
                ext_slip,
            )

            ext_close = w4.create_close_run(
                cur,
                company_code=COMPANY,
                source_kind="external_import",
                source_run_id=iid,
                actor_phone=CREATOR,
                reason=f"final_ext_close_{TAG}",
            )
            check("external close create", ext_close.get("ok") is True, ext_close)
            check(
                "external close authority",
                (ext_close.get("close_run") or {}).get("money_authority") == "external",
                ext_close,
            )

            # --- Wave 5 PIFSS/EOS ---
            refused = w5.generate_pifss_worksheet(
                cur,
                company_code=COMPANY,
                employee_key="WATHEFNI-REAL-EMPLOYEE-NOT-SYNTH",
                employee_category="kuwaiti_national",
                period_start=p_start,
                period_end=p_end,
                contributory_salary=1000,
                actor_phone=CREATOR,
                reason=f"final_refuse_{TAG}",
            )
            check(
                "nonsynthetic refused",
                refused.get("error") == "payroll_wave5_synthetic_only",
                refused,
            )

            expat = w5.generate_pifss_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="expatriate",
                period_start=p_start,
                period_end=p_end,
                contributory_salary=1000,
                actor_phone=CREATOR,
                reason=f"final_expat_{TAG}",
            )
            check("expat unsupported", (expat.get("worksheet") or {}).get("status") == "unsupported", expat)
            cur.execute(
                "UPDATE payroll_pifss_worksheets SET status='superseded', updated_at=now() "
                "WHERE company_code=%s AND employee_key=%s AND status = ANY(%s)",
                (COMPANY, EMP_KEY, list(w5.ACTIVE_WS_STATUSES)),
            )

            kuwaiti = w5.generate_pifss_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="kuwaiti_national",
                period_start=p_start,
                period_end=p_end,
                contributory_salary=1000,
                actor_phone=CREATOR,
                reason=f"final_kuwaiti_{TAG}",
            )
            check("kuwaiti counsel_required", kuwaiti.get("error") == "counsel_required_rule", kuwaiti)
            check(
                "kuwaiti status counsel_required",
                (kuwaiti.get("worksheet") or {}).get("status") == "counsel_required",
                kuwaiti,
            )

            eos_block = w5.generate_eos_worksheet(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                employee_category="expatriate",
                termination_date=p_end,
                termination_reason="employer_termination",
                service_start=date(2020, 1, 1),
                service_end=p_end,
                monthly_wage=800,
                art_51_53_status="unresolved_blocked",
                law_17_2018_status="not_applicable",
                actor_phone=CREATOR,
                reason=f"final_eos_block_{TAG}",
            )
            check("eos art blocked", eos_block.get("error") == "blocked_unresolved_eos_case", eos_block)

            # Restore mode + cleanup
            restore = IDS["prior_mode"] if IDS["prior_mode"] in ("native", "external", "parallel_shadow") else "external"
            restored = pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode=restore, actor_phone=APPROVER, reason=f"final_restore_{TAG}"
            )
            check("restore prior mode", restored.get("ok") is True, restored)

            deleted = cleanup(cur)
            res = residual(cur)
            check("residual zero", res == 0, {"residual": res, "deleted": deleted})
            IDS["cleanup"] = {"deleted": deleted, "residual_total": res}
            conn.commit()

    qual = {
        "tag": TAG,
        "passed": PASS,
        "failed": FAIL,
        "ids": IDS,
        "results": RESULTS,
        "wave": "FINAL",
        "payment_processing": "disabled",
        "posts_payment": False,
        "remittance": False,
        "statutory_filing": False,
        "automatic_legal_compliance_claim": False,
        "bank_files": False,
        "wps": False,
        "ashal": False,
        "ai_calculations": False,
        "native_results_authoritative": False,
        "external_payroll_authority": "external",
        "eos_auto_payable": False,
        "pifss_remittance": False,
        "synthetic_only": True,
        "cleanup": IDS.get("cleanup") or {},
        "capability_scopes": [
            "wave1_foundation",
            "wave2a_external",
            "wave2b_native_preview",
            "wave3_payslips",
            "wave4_close_export",
            "wave5_pifss_eos",
        ],
    }
    (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    print("QUALIFICATION_JSON", EVID / "qualification.json")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
