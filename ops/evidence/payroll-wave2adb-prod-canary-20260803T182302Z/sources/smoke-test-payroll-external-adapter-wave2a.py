#!/usr/bin/env python3
"""Payroll Wave 2A — external adapter foundation smoke (local/staging).

Pins:
  - honesty: payment_processing=disabled, money_authority=external, no vendor claim
  - clean export + clean import
  - duplicate/idempotent replay
  - unmatched employee handling
  - changed input fingerprint detection
  - reconciliation differences
  - malformed file quarantine
  - export rollback
  - Wave 1 contracts untouched

Does NOT enable bank files / native G2N / real money.
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
EMP_KEY = f"WATHEFNI-PYW1-W2A-{SUFFIX}"
EMP_KEY_B = f"WATHEFNI-PYW1-W2A-B-{SUFFIX}"
CREATOR = "965539100011"
APPROVER = "965539100012"


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
    print("    payroll external adapter wave2a — export/import/reconcile")
    orch = Path(__file__).resolve().parent
    sys.path.insert(0, str(orch))

    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
    os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY", "1")

    import payroll_authority_wave1 as pyw1
    import payroll_external_adapter_wave2a as w2a

    honesty = w2a.honesty_payload()
    check("version pinned", w2a.PAYROLL_WAVE2A_VERSION == "1.0.0")
    check("payment disabled", honesty.get("payment_processing") == "disabled")
    check("money authority external", honesty.get("money_authority") == "external")
    check("wathefni not money authority", honesty.get("wathefni_money_authority") is False)
    check("no posts_payment", honesty.get("posts_payment") is False)
    check("no bank files", honesty.get("bank_files") is False)
    check("no native g2n", honesty.get("native_gross_to_net") is False)
    check("vendor unclaimed", honesty.get("vendor_claimed") is False)
    check("wave1 contracts unchanged flag", honesty.get("wave1_contracts_unchanged") is True)
    check("uses input schema 1.0.0", honesty.get("input_export_schema") == pyw1.PAYROLL_INPUT_EXPORT_SCHEMA)
    check("uses result schema 1.0.0", honesty.get("result_import_schema") == pyw1.PAYROLL_RESULT_IMPORT_SCHEMA)

    inv = w2a.freeze_invariants()
    check("freeze mirror only", inv.get("mirror_only_imports") is True)
    check("freeze wave1 ddl untouched", inv.get("wave1_ddl_untouched") is True)

    # Unit: malformed CSV
    bad = w2a.decode_import_csv("not,a,valid\n1,2")
    check("malformed csv rejected", bad.get("error") == "malformed_csv", bad)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
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
            w2a.ensure_payroll_wave2a_schema(cur, force=True)
            pyw1.set_payroll_mode(
                cur,
                company_code=company,
                mode="external",
                actor_phone=APPROVER,
                reason=f"w2a_mode_external_{SUFFIX}",
            )

            # Seed draft+approve synthetic contract via Wave 1 APIs
            draft = pyw1.create_contract_draft(
                cur,
                company_code=company,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"w2a_draft_{SUFFIX}",
            )
            check("wave1 draft still works", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            rv = int((draft.get("contract") or {}).get("row_version") or 1)
            approved = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w2a_approve_{SUFFIX}",
                expected_row_version=rv,
            )
            check("wave1 approve still works", approved.get("ok") is True, approved)
            contract = approved.get("contract") or {}

            p_start = date(2026, 12, 1) + timedelta(days=(int(SUFFIX[:2], 16) % 10))
            p_end = p_start + timedelta(days=6)
            period = pyw1.create_period(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="legacy_records",
                actor_phone=CREATOR,
                reason=f"w2a_period_{SUFFIX}",
            )
            check("period create", period.get("ok") is True, period)
            period_row = period.get("period") or {}

            employees = [{"employee_key": EMP_KEY}]
            contracts = [contract]
            attendance = [{"employee_key": EMP_KEY, "worked_minutes": 2400}]
            leave = [{"employee_key": EMP_KEY, "leave_type": "annual", "classification": "paid"}]

            # Clean export
            exported = w2a.create_external_export(
                cur,
                company_code=company,
                period=period_row,
                employees=employees,
                contracts=contracts,
                attendance=attendance,
                leave_classifications=leave,
                actor_phone=CREATOR,
                reason=f"w2a_export_{SUFFIX}",
            )
            check("clean export", exported.get("ok") is True and not exported.get("idempotent"), exported)
            export_run = exported.get("export_run") or {}
            eid = str(export_run.get("export_run_id"))
            fp1 = exported.get("input_fingerprint")
            check("export fingerprint present", bool(fp1))
            check("export money authority external", export_run.get("money_authority") == "external")
            check("export payment disabled", export_run.get("payment_processing") == "disabled")
            check("export posts_payment false", export_run.get("posts_payment") is False)

            # Idempotent identical re-export
            exported2 = w2a.create_external_export(
                cur,
                company_code=company,
                period=period_row,
                employees=employees,
                contracts=contracts,
                attendance=attendance,
                leave_classifications=leave,
                actor_phone=CREATOR,
                reason=f"w2a_export_again_{SUFFIX}",
            )
            check("idempotent export replay", exported2.get("ok") is True and exported2.get("idempotent") is True, exported2)

            # Clean import
            ext_run = f"EXT-IMP-{SUFFIX}"
            result_csv = w2a.build_synthetic_result_csv(
                export_payload=export_run.get("payload") if isinstance(export_run.get("payload"), dict) else exported.get("export_run", {}).get("payload") or {},
                external_run_id=ext_run,
            )
            # payload may be string from DB — rebuild from export artifact path
            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            payload_row = dict(cur.fetchone())
            payload = payload_row["payload"]
            if isinstance(payload, str):
                import json as _json

                payload = _json.loads(payload)
            result_csv = w2a.build_synthetic_result_csv(export_payload=payload, external_run_id=ext_run)

            imported = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2a_import_{SUFFIX}",
            )
            check("clean import", imported.get("ok") is True and not imported.get("idempotent"), imported)
            import_run = imported.get("import_run") or {}
            iid = str(import_run.get("import_run_id"))
            check("import mirror_only", import_run.get("mirror_only") is True)
            check("import external authority", import_run.get("money_authority") == "external")
            check("import matched", int(imported.get("matched_count") or 0) >= 1, imported)

            # Duplicate/idempotent replay
            imported_replay = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2a_import_replay_{SUFFIX}",
            )
            check("idempotent import replay", imported_replay.get("ok") is True and imported_replay.get("idempotent") is True, imported_replay)

            # Reconcile clean
            recon = w2a.reconcile_export_import(
                cur,
                company_code=company,
                export_run_id=eid,
                import_run_id=iid,
                actor_phone=APPROVER,
                reason=f"w2a_recon_{SUFFIX}",
            )
            check("reconcile clean", recon.get("ok") is True and recon.get("has_differences") is False, recon)

            # Unmatched employee
            unmatched_csv = (
                "employee_key,component_code,opaque_amount,currency,external_run_id\n"
                f"WATHEFNI-UNKNOWN-{SUFFIX},BASIC,100.000,KWD,EXT-UNMATCH-{SUFFIX}\n"
            )
            unmatched = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=unmatched_csv,
                actor_phone=APPROVER,
                reason=f"w2a_unmatched_{SUFFIX}",
            )
            check("unmatched import accepted/partial", unmatched.get("ok") is True, unmatched)
            check("unmatched quarantined count", int(unmatched.get("quarantined_count") or 0) >= 1, unmatched)

            # Malformed quarantine
            malformed = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text="garbage\nline",
                actor_phone=APPROVER,
                reason=f"w2a_malformed_{SUFFIX}",
            )
            check("malformed quarantined", malformed.get("ok") is False and malformed.get("error") == "malformed_csv", malformed)
            check("malformed has quarantine row", bool((malformed.get("quarantine") or {}).get("quarantine_id")), malformed)

            # Fingerprint change detection on import
            fp_block = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv.replace(ext_run, f"EXT-FPBLOCK-{SUFFIX}"),
                actor_phone=APPROVER,
                reason=f"w2a_fpblock_{SUFFIX}",
                expected_input_fingerprint="deadbeef" + ("0" * 56),
            )
            check("fingerprint change blocks import", fp_block.get("error") == "input_fingerprint_changed", fp_block)

            # Changed input fingerprint on re-export (attendance minutes change)
            exported_changed = w2a.create_external_export(
                cur,
                company_code=company,
                period=period_row,
                employees=employees,
                contracts=contracts,
                attendance=[{"employee_key": EMP_KEY, "worked_minutes": 3000}],
                leave_classifications=leave,
                actor_phone=CREATOR,
                reason=f"w2a_export_changed_{SUFFIX}",
            )
            check("changed fingerprint detected", exported_changed.get("ok") is True and exported_changed.get("fingerprint_changed") is True, exported_changed)
            check("new export not idempotent", exported_changed.get("idempotent") is False)

            # Reconciliation differences (amount mismatch)
            eid2 = str((exported_changed.get("export_run") or {}).get("export_run_id"))
            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid2,))
            payload2 = dict(cur.fetchone())["payload"]
            if isinstance(payload2, str):
                import json as _json

                payload2 = _json.loads(payload2)
            diff_csv = w2a.build_synthetic_result_csv(
                export_payload=payload2,
                external_run_id=f"EXT-DIFF-{SUFFIX}",
                amount_fn=lambda _k, _c, base: base + 25,
            )
            imported_diff = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid2,
                csv_text=diff_csv,
                actor_phone=APPROVER,
                reason=f"w2a_import_diff_{SUFFIX}",
            )
            check("diff import ok", imported_diff.get("ok") is True, imported_diff)
            iid2 = str((imported_diff.get("import_run") or {}).get("import_run_id"))
            recon_diff = w2a.reconcile_export_import(
                cur,
                company_code=company,
                export_run_id=eid2,
                import_run_id=iid2,
                actor_phone=APPROVER,
                reason=f"w2a_recon_diff_{SUFFIX}",
            )
            check("reconcile differences flagged", recon_diff.get("ok") is True and recon_diff.get("has_differences") is True, recon_diff)
            check(
                "component diffs present",
                (recon_diff.get("reconciliation") or {}).get("status") == "differences",
                recon_diff,
            )

            # Rollback first export
            cur.execute("SELECT row_version FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            erv = int(dict(cur.fetchone())["row_version"])
            rolled = w2a.rollback_export_run(
                cur,
                company_code=company,
                export_run_id=eid,
                actor_phone=APPROVER,
                reason=f"w2a_rollback_{SUFFIX}",
                expected_row_version=erv,
            )
            check("export rollback", rolled.get("ok") is True and (rolled.get("export_run") or {}).get("status") == "rolled_back", rolled)

            # Soft quarantine rows never hard-deleted
            cur.execute(
                "SELECT COUNT(*) AS n, BOOL_OR(hard_deleted) AS any_hard FROM payroll_adapter_quarantine WHERE company_code=%s AND reason LIKE %s",
                (company, f"%{SUFFIX}%"),
            )
            qstats = dict(cur.fetchone())
            check("quarantine soft only", int(qstats["n"]) >= 1 and qstats["any_hard"] is False, qstats)

            # Cleanup synthetic wave1 period/contracts for this tag (adapter rows can remain as evidence)
            cur.execute(
                "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id IN (SELECT contract_id FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key LIKE %s)",
                (company, company, f"%PYW1-W2A-{SUFFIX}%"),
            )
            cur.execute(
                "DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id IN (SELECT contract_id FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key LIKE %s)",
                (company, company, f"%PYW1-W2A-{SUFFIX}%"),
            )
            cur.execute(
                "DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key LIKE %s",
                (company, f"%PYW1-W2A-{SUFFIX}%"),
            )
            # Also EMP_KEY exact
            cur.execute(
                "DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id IN (SELECT contract_id FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s)",
                (company, company, EMP_KEY),
            )
            cur.execute(
                "DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id IN (SELECT contract_id FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s)",
                (company, company, EMP_KEY),
            )
            cur.execute(
                "DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
                (company, EMP_KEY),
            )
            pid = str(period_row.get("period_id") or "")
            if pid:
                cur.execute("DELETE FROM payroll_period_events WHERE company_code=%s AND period_id=%s", (company, pid))
                cur.execute("DELETE FROM payroll_periods WHERE company_code=%s AND period_id=%s", (company, pid))

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
