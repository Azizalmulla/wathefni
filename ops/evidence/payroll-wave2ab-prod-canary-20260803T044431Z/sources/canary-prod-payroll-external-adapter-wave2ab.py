#!/usr/bin/env python3
"""Payroll Wave 2A-B — production synthetic external-adapter canary.

Synthetic subjects only (PYW1-W2AB / 965540*).
Proves: clean export/import, idempotency, unmatched quarantine, fingerprint drift,
reconciliation diffs, malformed quarantine, export rollback, residual cleanup.

Does NOT: real vendor connection, bank files, native G2N, real employee/compensation
mutation beyond temporary synthetic rows that are cleaned up.
money_authority=external; payment_processing=disabled; vendor_claimed=false.
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

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS", "PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES", "965540,965539")

import app  # noqa: E402
import payroll_authority_wave1 as pyw1  # noqa: E402
import payroll_external_adapter_wave2a as w2a  # noqa: E402

COMPANY = "WATHEFNI"
TAG = os.environ.get("PYW2AB_TAG") or uuid.uuid4().hex[:8]
TAG_DIGITS = ("".join(ch for ch in TAG if ch.isdigit()) + "00000")[:5]
EMP_KEY = f"WATHEFNI-PYW1-W2AB-{TAG}"
REAL_KEY = "WATHEFNI-96566363363"
CREATOR = f"9655401{TAG_DIGITS}"
APPROVER = f"9655402{TAG_DIGITS}"

PASS = FAIL = 0
RESULTS: list[dict[str, Any]] = []
EVID = Path(os.environ.get("PYW2AB_EVID") or f"/tmp/payroll-w2ab-{TAG}")
EVID.mkdir(parents=True, exist_ok=True)
IDS: dict[str, Any] = {
    "tag": TAG,
    "employee_key": EMP_KEY,
    "phones": {"creator": CREATOR, "approver": APPROVER},
    "export_run_ids": [],
    "import_run_ids": [],
    "period_ids": [],
    "contract_ids": [],
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


def _payload(cur, export_run_id: str) -> dict[str, Any]:
    cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (export_run_id,))
    row = dict(cur.fetchone())
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload


def cleanup(cur) -> dict[str, Any]:
    deleted: dict[str, int] = {}
    # Adapter imports/exports for this tag (via decision_note / external_run_id / employee)
    cur.execute(
        """
        SELECT import_run_id::text FROM payroll_adapter_import_runs
        WHERE company_code=%s AND (decision_note LIKE %s OR external_run_id LIKE %s OR artifact_csv LIKE %s)
        """,
        (COMPANY, f"%{TAG}%", f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    iids = [dict(r)["import_run_id"] for r in cur.fetchall()]
    if iids:
        cur.execute("DELETE FROM payroll_adapter_import_lines WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["import_lines"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["reconciliations"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_events WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["events_import"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_import_runs WHERE import_run_id::text = ANY(%s)", (iids,))
        deleted["imports"] = cur.rowcount or 0
    cur.execute(
        """
        SELECT export_run_id::text FROM payroll_adapter_export_runs
        WHERE company_code=%s AND (decision_note LIKE %s OR external_run_id LIKE %s OR artifact_csv LIKE %s)
        """,
        (COMPANY, f"%{TAG}%", f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    eids = [dict(r)["export_run_id"] for r in cur.fetchall()]
    if eids:
        cur.execute("DELETE FROM payroll_adapter_reconciliations WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["recon_export"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_events WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["events_export"] = cur.rowcount or 0
        cur.execute("DELETE FROM payroll_adapter_export_runs WHERE export_run_id::text = ANY(%s)", (eids,))
        deleted["exports"] = cur.rowcount or 0
    cur.execute(
        "DELETE FROM payroll_adapter_quarantine WHERE company_code=%s AND (reason LIKE %s OR artifact_excerpt LIKE %s)",
        (COMPANY, f"%{TAG}%", f"%{EMP_KEY}%"),
    )
    deleted["quarantine"] = cur.rowcount or 0

    # Synthetic wave1 contracts/periods for this EMP_KEY
    cur.execute(
        "SELECT contract_id::text FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
        (COMPANY, EMP_KEY),
    )
    cids = [dict(r)["contract_id"] for r in cur.fetchall()]
    if cids:
        cur.execute("DELETE FROM payroll_compensation_events WHERE company_code=%s AND contract_id::text = ANY(%s)", (COMPANY, cids))
        cur.execute("DELETE FROM payroll_compensation_components WHERE company_code=%s AND contract_id::text = ANY(%s)", (COMPANY, cids))
        cur.execute("DELETE FROM payroll_compensation_contracts WHERE company_code=%s AND contract_id::text = ANY(%s)", (COMPANY, cids))
        deleted["contracts"] = cur.rowcount or 0
    cur.execute(
        """
        SELECT period_id::text FROM payroll_periods
        WHERE company_code=%s AND (decision_note LIKE %s OR created_by_phone = ANY(%s))
        """,
        (COMPANY, f"%{TAG}%", [CREATOR, APPROVER]),
    )
    pids = [dict(r)["period_id"] for r in cur.fetchall()]
    if pids:
        cur.execute("DELETE FROM payroll_period_events WHERE company_code=%s AND period_id::text = ANY(%s)", (COMPANY, pids))
        cur.execute("DELETE FROM payroll_periods WHERE company_code=%s AND period_id::text = ANY(%s)", (COMPANY, pids))
        deleted["periods"] = cur.rowcount or 0
    return deleted


def residual(cur) -> int:
    n = 0
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_compensation_contracts WHERE company_code=%s AND employee_key=%s",
        (COMPANY, EMP_KEY),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_adapter_export_runs WHERE company_code=%s AND artifact_csv LIKE %s",
        (COMPANY, f"%{EMP_KEY}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_adapter_import_runs WHERE company_code=%s AND (artifact_csv LIKE %s OR external_run_id LIKE %s)",
        (COMPANY, f"%{EMP_KEY}%", f"%{TAG}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    cur.execute(
        "SELECT COUNT(*) AS n FROM payroll_periods WHERE company_code=%s AND decision_note LIKE %s",
        (COMPANY, f"%{TAG}%"),
    )
    n += int(dict(cur.fetchone())["n"])
    return n


def main() -> int:
    print(f"payroll wave2ab prod synthetic canary tag={TAG}")
    check("wave2a enabled", w2a.payroll_wave2a_enabled())
    check("wave2a company", w2a.payroll_wave2a_enabled_for_company(COMPANY))
    check("synthetic_only on", w2a.payroll_wave2a_synthetic_only())
    honesty = w2a.honesty_payload()
    check("payment disabled", honesty.get("payment_processing") == "disabled")
    check("money authority external", honesty.get("money_authority") == "external")
    check("wathefni not money authority", honesty.get("wathefni_money_authority") is False)
    check("vendor unclaimed", honesty.get("vendor_claimed") is False)
    check("no bank files", honesty.get("bank_files") is False)
    check("no native g2n", honesty.get("native_gross_to_net") is False)
    check("no posts_payment", honesty.get("posts_payment") is False)
    check("wave1 contracts unchanged flag", honesty.get("wave1_contracts_unchanged") is True)
    check("wave1 still enabled", pyw1.payroll_wave1_enabled())

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
            check("db is wathefni", db == "wathefni", db)

            pyw1.ensure_payroll_wave1_schema(cur)
            w2a.ensure_payroll_wave2a_schema(cur)
            pyw1.set_payroll_mode(
                cur, company_code=COMPANY, mode="external", actor_phone=APPROVER, reason=f"w2ab_mode_{TAG}"
            )

            # Refuse real employee export subject
            real_deny = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period={
                    "period_id": str(uuid.uuid4()),
                    "period_start": "2026-12-01",
                    "period_end": "2026-12-07",
                    "attendance_input_source": "legacy_records",
                    "status": "open",
                    "payroll_mode": "external",
                },
                employees=[{"employee_key": REAL_KEY}],
                contracts=[],
                actor_phone=CREATOR,
                reason=f"w2ab_real_deny_{TAG}",
            )
            check("real employee export refused", real_deny.get("error") == "payroll_wave2a_synthetic_only", real_deny)

            # Synthetic contract (temporary) via Wave 1
            draft = pyw1.create_contract_draft(
                cur,
                company_code=COMPANY,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 500, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"w2ab_draft_{TAG}",
            )
            check("synth contract draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            IDS["contract_ids"].append(cid)
            approved = pyw1.approve_contract(
                cur,
                company_code=COMPANY,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w2ab_approve_{TAG}",
                expected_row_version=int((draft.get("contract") or {}).get("row_version") or 1),
            )
            check("synth contract approve", approved.get("ok") is True, approved)
            contract = approved.get("contract") or {}

            p_start = date(2027, 1, 1) + timedelta(days=(int(TAG[:2], 16) % 10))
            p_end = p_start + timedelta(days=6)
            period = pyw1.create_period(
                cur,
                company_code=COMPANY,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="legacy_records",
                actor_phone=CREATOR,
                reason=f"w2ab_period_{TAG}",
            )
            check("period create", period.get("ok") is True, period)
            period_row = period.get("period") or {}
            IDS["period_ids"].append(str(period_row.get("period_id") or ""))

            employees = [{"employee_key": EMP_KEY}]
            attendance = [{"employee_key": EMP_KEY, "worked_minutes": 2400}]
            leave = [{"employee_key": EMP_KEY, "leave_type": "annual", "classification": "paid"}]

            exported = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period=period_row,
                employees=employees,
                contracts=[contract],
                attendance=attendance,
                leave_classifications=leave,
                actor_phone=CREATOR,
                reason=f"w2ab_export_{TAG}",
            )
            check("clean export", exported.get("ok") is True and not exported.get("idempotent"), exported)
            eid = str((exported.get("export_run") or {}).get("export_run_id"))
            IDS["export_run_ids"].append(eid)
            fp1 = exported.get("input_fingerprint")

            exported_idem = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period=period_row,
                employees=employees,
                contracts=[contract],
                attendance=attendance,
                leave_classifications=leave,
                actor_phone=CREATOR,
                reason=f"w2ab_export_idem_{TAG}",
            )
            check("idempotent export", exported_idem.get("ok") is True and exported_idem.get("idempotent") is True, exported_idem)

            payload = _payload(cur, eid)
            ext_run = f"EXT-W2AB-{TAG}"
            result_csv = w2a.build_synthetic_result_csv(export_payload=payload, external_run_id=ext_run)
            imported = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2ab_import_{TAG}",
            )
            check("clean import", imported.get("ok") is True and not imported.get("idempotent"), imported)
            iid = str((imported.get("import_run") or {}).get("import_run_id"))
            IDS["import_run_ids"].append(iid)
            check("import mirror_only", (imported.get("import_run") or {}).get("mirror_only") is True)

            imported_idem = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2ab_import_idem_{TAG}",
            )
            check("idempotent import", imported_idem.get("ok") is True and imported_idem.get("idempotent") is True, imported_idem)

            recon = w2a.reconcile_export_import(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                import_run_id=iid,
                actor_phone=APPROVER,
                reason=f"w2ab_recon_{TAG}",
            )
            check("reconcile clean", recon.get("ok") is True and recon.get("has_differences") is False, recon)

            # Unmatched employee quarantine
            unmatched_csv = (
                "employee_key,component_code,opaque_amount,currency,external_run_id\n"
                f"WATHEFNI-UNKNOWN-{TAG},BASIC,100.000,KWD,EXT-UNMATCH-{TAG}\n"
            )
            unmatched = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=unmatched_csv,
                actor_phone=APPROVER,
                reason=f"w2ab_unmatch_{TAG}",
            )
            check("unmatched handled", unmatched.get("ok") is True and int(unmatched.get("quarantined_count") or 0) >= 1, unmatched)
            if unmatched.get("ok"):
                IDS["import_run_ids"].append(str((unmatched.get("import_run") or {}).get("import_run_id")))

            # Malformed quarantine
            malformed = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text="garbage\n",
                actor_phone=APPROVER,
                reason=f"w2ab_malformed_{TAG}",
            )
            check("malformed quarantined", malformed.get("error") == "malformed_csv" and bool(malformed.get("quarantine")), malformed)

            # Fingerprint drift blocks import
            fp_block = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                csv_text=result_csv.replace(ext_run, f"EXT-FP-{TAG}"),
                actor_phone=APPROVER,
                reason=f"w2ab_fpblock_{TAG}",
                expected_input_fingerprint="0" * 64,
            )
            check("fingerprint drift blocked", fp_block.get("error") == "input_fingerprint_changed", fp_block)

            # Changed input fingerprint on re-export
            exported_changed = w2a.create_external_export(
                cur,
                company_code=COMPANY,
                period=period_row,
                employees=employees,
                contracts=[contract],
                attendance=[{"employee_key": EMP_KEY, "worked_minutes": 3000}],
                leave_classifications=leave,
                actor_phone=CREATOR,
                reason=f"w2ab_export_changed_{TAG}",
            )
            check("fingerprint drift on export", exported_changed.get("fingerprint_changed") is True, exported_changed)
            eid2 = str((exported_changed.get("export_run") or {}).get("export_run_id"))
            IDS["export_run_ids"].append(eid2)

            # Reconciliation differences
            payload2 = _payload(cur, eid2)
            diff_csv = w2a.build_synthetic_result_csv(
                export_payload=payload2,
                external_run_id=f"EXT-DIFF-{TAG}",
                amount_fn=lambda _k, _c, base: base + 25,
            )
            imported_diff = w2a.import_external_results(
                cur,
                company_code=COMPANY,
                export_run_id=eid2,
                csv_text=diff_csv,
                actor_phone=APPROVER,
                reason=f"w2ab_import_diff_{TAG}",
            )
            check("diff import", imported_diff.get("ok") is True, imported_diff)
            iid2 = str((imported_diff.get("import_run") or {}).get("import_run_id"))
            IDS["import_run_ids"].append(iid2)
            recon_diff = w2a.reconcile_export_import(
                cur,
                company_code=COMPANY,
                export_run_id=eid2,
                import_run_id=iid2,
                actor_phone=APPROVER,
                reason=f"w2ab_recon_diff_{TAG}",
            )
            check("reconcile differences", recon_diff.get("has_differences") is True, recon_diff)

            # Rollback first export
            cur.execute("SELECT row_version FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            erv = int(dict(cur.fetchone())["row_version"])
            rolled = w2a.rollback_export_run(
                cur,
                company_code=COMPANY,
                export_run_id=eid,
                actor_phone=APPROVER,
                reason=f"w2ab_rollback_{TAG}",
                expected_row_version=erv,
            )
            check("export rollback", rolled.get("ok") is True and (rolled.get("export_run") or {}).get("status") == "rolled_back", rolled)

            deleted = cleanup(cur)
            res = residual(cur)
            check("residual zero", res == 0, {"deleted": deleted, "residual": res})
            IDS["cleanup"] = deleted
            IDS["residual_total"] = res

            # Restore mode external (no money)
            settings = pyw1.ensure_company_settings(cur, company_code=COMPANY)
            check("final payment disabled", settings.get("payment_processing") == "disabled")

        conn.commit()

    qual = {
        "stamp_tag": TAG,
        "passed": PASS,
        "failed": FAIL,
        "ids": IDS,
        "honesty": honesty,
        "cleanup": {"residual_total": IDS.get("residual_total"), **(IDS.get("cleanup") or {})},
        "payment_processing": "disabled",
        "money_authority": "external",
        "vendor_claimed": False,
        "wave": "payroll_wave2ab_prod_synthetic",
    }
    (EVID / "qualification.json").write_text(json.dumps(qual, indent=2, default=str))
    (EVID / "ids.json").write_text(json.dumps(IDS, indent=2, default=str))
    (EVID / "results.json").write_text(json.dumps(RESULTS, indent=2, default=str))
    print(json.dumps({"passed": PASS, "failed": FAIL, "evid": str(EVID)}, indent=2))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
