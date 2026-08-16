#!/usr/bin/env bash
# Payroll Wave 3 — staging migrate for payslip schema.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import payroll_payslip_wave3 as w3
import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
import payroll_native_preview_wave2b as w2b
print("wave3", w3.PAYROLL_WAVE3_VERSION)
h = w3.honesty_payload()
assert h["payment_processing"] == "disabled"
assert h["payslips_as_money"] is False
assert h["native_payslips_authoritative"] is False
assert h["external_payslips_authority"] == "external"
assert h["ai_calculations"] is False
assert h["wave1_contracts_unchanged"] is True
assert h["wave2a_flows_unchanged"] is True
assert h["wave2b_flows_unchanged"] is True
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db != "wathefni" or os.environ.get("ACK_PRODUCTION_PAYROLL_W3") == "YES"
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        w2a.ensure_payroll_wave2a_schema(cur, force=True)
        w2b.ensure_payroll_wave2b_schema(cur, force=True)
        w3.ensure_payroll_wave3_schema(cur, force=True)
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public' AND tablename LIKE 'payroll_payslip_%'
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("payslip_tables", tables)
        required = {"payroll_payslip_documents", "payroll_payslip_lines", "payroll_payslip_events"}
        assert required <= set(tables), tables
    conn.commit()
print("MIGRATE_OK payroll_payslip_wave3")
PY
