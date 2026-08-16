#!/usr/bin/env python3
"""Payroll Wave 2A-C — external ops workflow smoke (local/staging).

Pins HR workflow helpers around frozen Wave 2A adapter:
  - workspace bootstrap + period readiness
  - generate/download path assembly
  - duplicate upload idempotency
  - stale fingerprint quarantine
  - replace-import flow
  - quarantine + events lists
  - imported result never authoritative in Wathefni
  - honesty: payment_processing=disabled, vendor_claimed=false

Does NOT start Wave 2B. Does NOT alter Wave 1/2A contracts.
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
EMP_KEY = f"WATHEFNI-PYW1-W2AC-{SUFFIX}"
CREATOR = "965539100021"
APPROVER = "965539100022"


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
    print("    payroll external ops wave2ac — workflow helpers")
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
    check("payment disabled", honesty.get("payment_processing") == "disabled")
    check("money authority external", honesty.get("money_authority") == "external")
    check("vendor unclaimed", honesty.get("vendor_claimed") is False)
    check("wave1 contracts unchanged", honesty.get("wave1_contracts_unchanged") is True)

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
                reason=f"w2ac_mode_external_{SUFFIX}",
            )

            draft = pyw1.create_contract_draft(
                cur,
                company_code=company,
                employee_key=EMP_KEY,
                effective_from=date(2026, 8, 1),
                components=[{"component_kind": "earning", "code": "BASIC", "amount": 450, "is_basic": True}],
                actor_phone=CREATOR,
                reason=f"w2ac_draft_{SUFFIX}",
            )
            check("contract draft", draft.get("ok") is True, draft)
            cid = str((draft.get("contract") or {}).get("contract_id"))
            rv = int((draft.get("contract") or {}).get("row_version") or 1)
            approved = pyw1.approve_contract(
                cur,
                company_code=company,
                contract_id=cid,
                actor_phone=APPROVER,
                reason=f"w2ac_approve_{SUFFIX}",
                expected_row_version=rv,
            )
            check("contract approve", approved.get("ok") is True, approved)
            contract = approved.get("contract") or {}

            p_start = date(2027, 1, 1) + timedelta(days=(int(SUFFIX[:2], 16) % 8))
            p_end = p_start + timedelta(days=6)
            period = pyw1.create_period(
                cur,
                company_code=company,
                period_start=p_start,
                period_end=p_end,
                attendance_input_source="legacy_records",
                actor_phone=CREATOR,
                reason=f"w2ac_period_{SUFFIX}",
            )
            check("period create", period.get("ok") is True, period)
            period_row = period.get("period") or {}

            ready = w2a.period_readiness(
                cur,
                company_code=company,
                period_start=str(p_start),
                period_end=str(p_end),
            )
            check("readiness ready", ready.get("ready") is True, ready)
            check("readiness not authoritative", ready.get("authoritative_in_wathefni") is False)

            boot = w2a.workspace_bootstrap(cur, company_code=company)
            check("bootstrap ok", boot.get("ok") is True, boot)
            check("bootstrap enabled", boot.get("enabled") is True)
            check("bootstrap payment disabled", boot.get("settings", {}).get("payment_processing") == "disabled")
            check("bootstrap not authoritative", boot.get("authoritative_in_wathefni") is False)

            assembled = w2a.assemble_period_export_inputs(
                cur,
                company_code=company,
                period_start=str(p_start),
                period_end=str(p_end),
                period_id=str(period_row.get("period_id") or "") or None,
            )
            check("assemble has employee", any(e.get("employee_key") == EMP_KEY for e in assembled.get("employees") or []), assembled)

            # Manager scope empty set → no employees
            empty_scope = w2a.assemble_period_export_inputs(
                cur,
                company_code=company,
                period_start=str(p_start),
                period_end=str(p_end),
                allowed_employee_keys=set(),
            )
            check("manager empty scope blocks", len(empty_scope.get("employees") or []) == 0)

            exported = w2a.create_external_export(
                cur,
                company_code=company,
                period=assembled["period"],
                employees=assembled["employees"],
                contracts=assembled["contracts"],
                actor_phone=CREATOR,
                reason=f"w2ac_export_{SUFFIX}",
            )
            check("export ok", exported.get("ok") is True, exported)
            if not exported.get("ok"):
                conn.rollback()
                print(f"\n    {PASS} passed, {FAIL} failed")
                return 1
            export_run = exported.get("export_run") or {}
            eid = str(export_run.get("export_run_id"))
            fp = str(exported.get("input_fingerprint") or export_run.get("input_fingerprint") or "")

            exports = w2a.list_export_runs(cur, company_code=company, limit=10)
            check("list exports", any(str(r.get("export_run_id")) == eid for r in exports))

            cur.execute("SELECT payload FROM payroll_adapter_export_runs WHERE export_run_id=%s", (eid,))
            payload_row = dict(cur.fetchone())
            payload = payload_row["payload"]
            if isinstance(payload, str):
                import json as _json

                payload = _json.loads(payload)

            result_csv = w2a.build_synthetic_result_csv(
                export_payload=payload,
                external_run_id=f"EXT-IMP-W2AC-{SUFFIX}",
            )
            imported = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2ac_import_{SUFFIX}",
                expected_input_fingerprint=fp,
            )
            check("import ok", imported.get("ok") is True, imported)
            check("import not money authority", imported.get("money_authority") == "external")
            iid = str((imported.get("import_run") or {}).get("import_run_id"))

            replay = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2ac_import_replay_{SUFFIX}",
                expected_input_fingerprint=fp,
            )
            check("duplicate upload idempotent", replay.get("idempotent") is True, replay)

            stale = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=result_csv,
                actor_phone=APPROVER,
                reason=f"w2ac_stale_fp_{SUFFIX}",
                expected_input_fingerprint="deadbeef" * 4,
            )
            check("stale fingerprint blocked", stale.get("error") == "input_fingerprint_changed", stale)
            check("stale fingerprint quarantined", bool(stale.get("quarantine")), stale)

            bad = w2a.import_external_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text="not,valid\n1,2",
                actor_phone=APPROVER,
                reason=f"w2ac_malformed_{SUFFIX}",
            )
            check("malformed quarantined", bad.get("ok") is False and bool(bad.get("quarantine")), bad)

            q = w2a.list_quarantine(cur, company_code=company, limit=50)
            check("quarantine list non-empty", len(q) >= 1)

            recon = w2a.reconcile_export_import(
                cur,
                company_code=company,
                export_run_id=eid,
                import_run_id=iid,
                actor_phone=APPROVER,
                reason=f"w2ac_recon_{SUFFIX}",
            )
            check("reconcile ok", recon.get("ok") is True, recon)
            stored = w2a.get_reconciliation(cur, company_code=company, export_run_id=eid, import_run_id=iid)
            check("reconciliation stored", bool(stored), stored)

            lines = w2a.list_import_lines(cur, company_code=company, import_run_id=iid)
            check("import lines present", len(lines) >= 1, lines)

            # Replace import with new external_run_id
            replace_csv = w2a.build_synthetic_result_csv(
                export_payload=payload,
                external_run_id=f"EXT-IMP-W2AC-RPL-{SUFFIX}",
            )
            replaced = w2a.replace_import_results(
                cur,
                company_code=company,
                export_run_id=eid,
                csv_text=replace_csv,
                actor_phone=APPROVER,
                reason=f"w2ac_replace_{SUFFIX}",
                expected_input_fingerprint=fp,
            )
            check("replace import ok", replaced.get("ok") is True, replaced)
            check("replace flagged", replaced.get("replace") is True)
            check("replace not authoritative", replaced.get("authoritative_in_wathefni") is False)
            check("replace money external", replaced.get("money_authority") == "external")

            events = w2a.list_events(cur, company_code=company, export_run_id=eid, limit=50)
            check("events timeline", len(events) >= 2, len(events))
            check("replace event present", any(e.get("event_type") == "import_replace_initiated" for e in events), events)

            # Native mode readiness blocker
            pyw1.set_payroll_mode(
                cur,
                company_code=company,
                mode="native",
                actor_phone=APPROVER,
                reason=f"w2ac_mode_native_{SUFFIX}",
            )
            blocked = w2a.period_readiness(cur, company_code=company, period_start=str(p_start), period_end=str(p_end))
            check("native mode blocks readiness", blocked.get("ready") is False, blocked)
            pyw1.set_payroll_mode(
                cur,
                company_code=company,
                mode="external",
                actor_phone=APPROVER,
                reason=f"w2ac_mode_restore_{SUFFIX}",
            )

            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
