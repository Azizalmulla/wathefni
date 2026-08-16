#!/usr/bin/env bash
# Payroll Wave 4 — staging migrate for close + finance export schema.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import payroll_close_export_wave4 as w4
import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
import payroll_native_preview_wave2b as w2b
print("wave4", w4.PAYROLL_WAVE4_VERSION)
h = w4.honesty_payload()
assert h["payment_processing"] == "disabled"
assert h["posts_payment"] is False
assert h["bank_files"] is False
assert h["bank_connection"] is False
assert h["wps"] is False
assert h["ashal"] is False
assert h["journals"] is False
assert h["journal_drafts"] is True
assert h["bank_export_contract"] is True
assert h["pifss"] is False
assert h["eos"] is False
assert h["ai_calculations"] is False
assert h["native_results_authoritative"] is False
assert h["external_payroll_authority"] == "external"
assert h["wave1_contracts_unchanged"] is True
assert h["wave2a_flows_unchanged"] is True
assert h["wave2b_flows_unchanged"] is True
assert h["wave3_flows_unchanged"] is True
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db != "wathefni" or os.environ.get("ACK_PRODUCTION_PAYROLL_W4") == "YES"
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        w2a.ensure_payroll_wave2a_schema(cur, force=True)
        w2b.ensure_payroll_wave2b_schema(cur, force=True)
        w4.ensure_payroll_wave4_schema(cur, force=True)
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public' AND (
              tablename LIKE 'payroll_close_%'
              OR tablename LIKE 'payroll_account_%'
              OR tablename LIKE 'payroll_journal_%'
              OR tablename LIKE 'payroll_bank_export_%'
              OR tablename LIKE 'payroll_finance_exports'
            )
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("wave4_tables", tables)
        required = {
            "payroll_close_runs",
            "payroll_close_run_events",
            "payroll_close_dual_control",
            "payroll_account_mappings",
            "payroll_journal_drafts",
            "payroll_journal_lines",
            "payroll_bank_export_drafts",
            "payroll_finance_exports",
        }
        assert required <= set(tables), tables
    conn.commit()
print("MIGRATE_OK payroll_close_export_wave4")
PY
