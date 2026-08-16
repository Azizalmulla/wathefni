#!/usr/bin/env python3
"""Payroll Wave 3 — payslip smoke (local/staging).

Proves:
  native preview payslip generation
  external import payslip generation
  permission/scope denial
  duplicate/idempotent generation
  replace + revoke with history retained
  EN/AR download labels
  honesty (non-money, payment disabled, no AI)

Does NOT: bank files, payments, mutate Wave 1/2A/2B contracts beyond temporary synthetic rows.
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
EMP = f"WATHEFNI-PYW1-PYW3-{SUFFIX}"
CREATOR = "965541100021"
APPROVER = "965541100022"
REAL = "WATHEFNI-96566363363"


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
    print("    payroll payslip wave3")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY", "1")

    import payroll_authority_wave1 as pyw1
    import payroll_external_adapter_wave2a as w2a
    import payroll_native_preview_wave2b as w2b
    import payroll_payslip_wave3 as w3

    h = w3.honesty_payload()
    check("version", w3.PAYROLL_WAVE3_VERSION == "1.0.0")
    check("payment disabled", h.get("payment_processing") == "disabled")
    check("not money", h.get("payslips_as_money") is False)
    check("native non-auth", h.get("native_payslips_authoritative") is False)
    check("external authority", h.get("external_payslips_authority") == "external")
    check("no AI", h.get("ai_calculations") is False)
    check("wave1 unchanged", h.get("wave1_contracts_unchanged") is True)
    check("wave2a unchanged", h.get("wave2a_flows_unchanged") is True)
    check("wave2b unchanged", h.get("wave2b_flows_unchanged") is True)
    inv = w3.freeze_invariants()
    check("history never deleted", inv.get("history_never_deleted") is True)

    # UX EN/AR presence
    dash = Path(__file__).resolve().parents[1] / "apps" / "wathefni-dashboard" / "src" / "posthire"
    ux = (dash / "payrollPayslipUx.ts").read_text(encoding="utf-8") if (dash / "payrollPayslipUx.ts").exists() else ""
    ws = (dash / "PayslipWorkspace.tsx").read_text(encoding="utf-8") if (dash / "PayslipWorkspace.tsx").exists() else ""
    check("ux en title", "Payslips" in ux)
    check("ux ar title", "قسائم الراتب" in ux)
    check("ux honesty native", "non-authoritative" in ux.lower() or "غير ملزمة" in ux)
    check("ux mobile hint", "mobileHint" in ux and "md:hidden" in ws)
    check("ux rtl", "rtl" in ws)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit+ux)")
            return 1 if FAIL else 0
        raise

    company = "WATHEFNI"
    p_start = date(2029, 3, 1)
    p_end = date(2029, 3, 31)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            print("connected_db", db)
            if db == "wathefni":
                print("REFUSE production database in staging smoke")
                return 2

            pyw1.ensure_payroll_wave1_schema(cur, force=True)
            w2a.ensure_payroll_wave2a_schema(cur, force=True)
            w2b.ensure_payroll_wave2b_schema(cur, force=True)
            w3.ensure_payroll_wave3_schema(cur, force=True)

            settings = pyw1.ensure_company_settings(cur, company_code=company)
            prior_mode = str(settings.get("payroll_mode") or "native")
            pyw1.set_payroll_mode(
                cur, company_code=company, mode="native", actor_phone=APPROVER, reason=f"w3_native_{SUFFIX}"
            )

            draft = pyw1.create_contract_draft(
                cur,
                company_code=company,
                employee_key=EMP,
                effective_from=date(2026, 1, 1),
                components=[
                    {"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True},
                    {"component_kind": "allowance", "code": "TRANSPORT", "amount": 50},
                ],
                actor_phone=CREATOR,
                reason=f"w3_draft_{SUFFIX}",
            )
            check("draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            approved = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w3_approve_{SUFFIX}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("approve", approved.get("ok") is True, approved)
            contract_row = approved.get("contract") or {}

            cur.execute(
                """
                SELECT * FROM payroll_periods
                WHERE company_code=%s AND period_start=%s AND period_end=%s
                ORDER BY created_at DESC NULLS LAST LIMIT 1
                """,
                (company, p_start, p_end),
            )
            existing = cur.fetchone()
            if existing:
                period = {"ok": True, "period": dict(existing)}
            else:
                period = pyw1.create_period(
                    cur,
                    company_code=company,
                    period_start=p_start,
                    period_end=p_end,
                    attendance_input_source="legacy_records",
                    actor_phone=CREATOR,
                    reason=f"w3_period_{SUFFIX}",
                )
            check("period", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            pid = str(period_row.get("period_id") or "")

            preview = w2b.calculate_native_preview(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                period_id=pid or None,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                actor_phone=CREATOR,
                reason=f"w3_preview_{SUFFIX}",
            )
            check("preview ok", preview.get("ok") is True, preview)
            prid = str((preview.get("preview_run") or {}).get("preview_run_id") or "")

            gen = w3.generate_native_payslip(
                cur,
                company_code=company,
                preview_run_id=prid,
                employee_key=EMP,
                actor_phone=CREATOR,
                reason=f"w3_payslip_native_{SUFFIX}",
            )
            check("native payslip ok", gen.get("ok") is True, gen)
            slip = gen.get("payslip") or {}
            check("native non-auth label", slip.get("money_authority") == "preview_non_authoritative", slip)
            check("native payment disabled", slip.get("payment_processing") == "disabled", slip)
            sid = str(slip.get("payslip_id") or "")

            replay = w3.generate_native_payslip(
                cur,
                company_code=company,
                preview_run_id=prid,
                employee_key=EMP,
                actor_phone=CREATOR,
                reason=f"w3_payslip_native_idem_{SUFFIX}",
            )
            check("native idempotent", replay.get("idempotent") is True, replay)

            scoped_denied = w3.generate_native_payslip(
                cur,
                company_code=company,
                preview_run_id=prid,
                employee_key=EMP,
                actor_phone=CREATOR,
                reason=f"w3_scope_{SUFFIX}",
                allowed_employee_keys={"OTHER-KEY"},
            )
            check("scope denied", scoped_denied.get("error") == "employee_outside_manager_scope", scoped_denied)

            real_denied = w3.generate_native_payslip(
                cur,
                company_code=company,
                preview_run_id=prid,
                employee_key=REAL,
                actor_phone=CREATOR,
                reason=f"w3_real_{SUFFIX}",
            )
            check("real refused", real_denied.get("error") == "payroll_wave3_synthetic_only", real_denied)

            replaced = w3.replace_payslip(
                cur,
                company_code=company,
                payslip_id=sid,
                actor_phone=APPROVER,
                reason=f"w3_replace_{SUFFIX}",
            )
            check("replace ok", replaced.get("ok") is True, replaced)
            new_id = str((replaced.get("payslip") or {}).get("payslip_id") or "")
            check("replace version 2", int((replaced.get("payslip") or {}).get("version_number") or 0) == 2, replaced)
            check("prior replaced status", (replaced.get("replaced_payslip") or {}).get("status") == "replaced", replaced)

            hist = w3.list_payslip_history(cur, company_code=company, employee_key=EMP)
            check("history retained after replace", len(hist) >= 2, len(hist))

            dl_en = w3.download_payslip_document(cur, company_code=company, payslip_id=new_id, locale="en")
            check("download en", dl_en.get("ok") is True and "Preview only" in str(dl_en.get("body") or ""), dl_en)
            dl_ar = w3.download_payslip_document(cur, company_code=company, payslip_id=new_id, locale="ar")
            check("download ar", dl_ar.get("ok") is True and "معاينة" in str(dl_ar.get("body") or ""), dl_ar)

            revoked = w3.revoke_payslip(
                cur,
                company_code=company,
                payslip_id=new_id,
                actor_phone=APPROVER,
                reason=f"w3_revoke_{SUFFIX}",
            )
            check("revoke ok", revoked.get("ok") is True, revoked)
            check("revoke status", (revoked.get("payslip") or {}).get("status") == "revoked", revoked)
            hist2 = w3.list_payslip_history(cur, company_code=company, employee_key=EMP)
            check("history retained after revoke", any(str(r.get("status")) == "revoked" for r in hist2), hist2)
            check("no hard delete", all(str(r.get("payslip_id") or "") for r in hist2))

            # External payslip path
            pyw1.set_payroll_mode(
                cur, company_code=company, mode="external", actor_phone=APPROVER, reason=f"w3_ext_mode_{SUFFIX}"
            )
            exported = w2a.create_external_export(
                cur,
                company_code=company,
                period=period_row,
                employees=[{"employee_key": EMP}],
                contracts=[contract_row],
                attendance=[{"employee_key": EMP, "worked_minutes": 10000}],
                leave_classifications=[],
                actor_phone=CREATOR,
                reason=f"w3_export_{SUFFIX}",
            )
            check("external export", exported.get("ok") is True, exported)
            eid = str((exported.get("export_run") or {}).get("export_run_id") or "")
            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            payload = dict(cur.fetchone())["payload"]
            if isinstance(payload, str):
                import json as _json

                payload = _json.loads(payload)
            result_csv = w2a.build_synthetic_result_csv(export_payload=payload, external_run_id=f"EXT-W3-{SUFFIX}")
            imported = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w3_import_{SUFFIX}",
            )
            check("external import", imported.get("ok") is True, imported)
            iid = str((imported.get("import_run") or {}).get("import_run_id") or "")

            ext = w3.generate_external_payslip(
                cur,
                company_code=company,
                import_run_id=iid,
                employee_key=EMP,
                actor_phone=CREATOR,
                reason=f"w3_payslip_ext_{SUFFIX}",
            )
            check("external payslip ok", ext.get("ok") is True, ext)
            eslip = ext.get("payslip") or {}
            check("external money authority", eslip.get("money_authority") == "external", eslip)
            check("external not wathefni auth", eslip.get("authoritative_label") == "external", eslip)

            ext_replay = w3.generate_external_payslip(
                cur,
                company_code=company,
                import_run_id=iid,
                employee_key=EMP,
                actor_phone=CREATOR,
                reason=f"w3_payslip_ext_idem_{SUFFIX}",
            )
            check("external idempotent", ext_replay.get("idempotent") is True, ext_replay)

            events = w3.list_payslip_events(cur, company_code=company, limit=20)
            check("audit events", len(events) >= 1, len(events))

            # Cleanup synthetic payslips + contracts/adapters for this EMP
            cur.execute(
                "SELECT payslip_id::text FROM payroll_payslip_documents WHERE company_code=%s AND employee_key=%s",
                (company, EMP),
            )
            pids = [dict(r)["payslip_id"] for r in cur.fetchall()]
            if pids:
                cur.execute("DELETE FROM payroll_payslip_lines WHERE payslip_id::text = ANY(%s)", (pids,))
                cur.execute("DELETE FROM payroll_payslip_events WHERE payslip_id::text = ANY(%s)", (pids,))
                cur.execute("DELETE FROM payroll_payslip_documents WHERE payslip_id::text = ANY(%s)", (pids,))
            cur.execute(
                "SELECT preview_run_id::text FROM payroll_preview_runs WHERE company_code=%s AND inputs::text LIKE %s",
                (company, f"%{EMP}%"),
            )
            prids = [dict(r)["preview_run_id"] for r in cur.fetchall()]
            if prids:
                cur.execute("DELETE FROM payroll_preview_lines WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_employee_results WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_events WHERE preview_run_id::text = ANY(%s)", (prids,))
                cur.execute("DELETE FROM payroll_preview_runs WHERE preview_run_id::text = ANY(%s)", (prids,))
            # adapter cleanup for this tag
            cur.execute(
                "SELECT import_run_id::text FROM payroll_adapter_import_runs WHERE company_code=%s AND decision_note LIKE %s",
                (company, f"%{SUFFIX}%"),
            )
            iids = [dict(r)["import_run_id"] for r in cur.fetchall()]
            if iids:
                cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
                cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
            cur.execute(
                "SELECT export_run_id::text FROM payroll_adapter_export_runs WHERE company_code=%s AND decision_note LIKE %s",
                (company, f"%{SUFFIX}%"),
            )
            eids = [dict(r)["export_run_id"] for r in cur.fetchall()]
            if eids:
                cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
                cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
            cur.execute(
                "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
                (company, EMP),
            )
            cids = [dict(r)["contract_id"] for r in cur.fetchall()]
            if cids:
                cur.execute(
                    "DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id::text = ANY(%s)",
                    (company, cids),
                )
                cur.execute(
                    "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id::text = ANY(%s)",
                    (company, cids),
                )
                cur.execute(
                    "DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND contract_id::text = ANY(%s)",
                    (company, cids),
                )
            cur.execute(
                "SELECT COUNT(*) AS n FROM payroll_payslip_documents WHERE company_code=%s AND employee_key=%s",
                (company, EMP),
            )
            residual = int(dict(cur.fetchone())["n"])
            check("residual payslips zero", residual == 0, residual)

            restore = prior_mode if prior_mode in ("native", "external", "parallel_shadow") else "native"
            pyw1.set_payroll_mode(
                cur, company_code=company, mode=restore, actor_phone=APPROVER, reason=f"w3_restore_{SUFFIX}"
            )
            check("wave1 still enabled", pyw1.payroll_wave1_enabled())
            check("wave2a still enabled", w2a.payroll_wave2a_enabled())
            check("wave2b still enabled", w2b.payroll_wave2b_enabled())

            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
