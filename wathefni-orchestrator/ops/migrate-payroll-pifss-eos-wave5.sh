#!/usr/bin/env bash
# Payroll Wave 5 — staging migrate for PIFSS/EOS review worksheet schema.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import payroll_pifss_eos_wave5 as w5
import payroll_authority_wave1 as pyw1
print("wave5", w5.PAYROLL_WAVE5_VERSION)
h = w5.honesty_payload()
assert h["payment_processing"] == "disabled"
assert h["posts_payment"] is False
assert h["remittance"] is False
assert h["statutory_filing"] is False
assert h["automatic_legal_compliance_claim"] is False
assert h["pifss_worksheets"] is True and h["pifss_remittance"] is False
assert h["eos_worksheets"] is True and h["eos_auto_payable"] is False
assert h["bank_files"] is False and h["wps"] is False and h["ashal"] is False
assert h["ai_calculations"] is False
assert h["native_results_authoritative"] is False
assert h["external_payroll_authority"] == "external"
inv = w5.freeze_invariants()
assert inv["missing_rule_fail_closed"] and inv["approved_history_immutable"]
assert inv["no_remittance"] and inv["no_auto_payable"]
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db != "wathefni" or os.environ.get("ACK_PRODUCTION_PAYROLL_W5") == "YES"
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        w5.ensure_payroll_wave5_schema(cur, force=True)
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public' AND (
              tablename LIKE 'payroll_statutory_%'
              OR tablename LIKE 'payroll_pifss_%'
              OR tablename LIKE 'payroll_eos_%'
            )
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("wave5_tables", tables)
        required = {
            "payroll_statutory_rule_tables",
            "payroll_pifss_worksheets",
            "payroll_eos_worksheets",
            "payroll_statutory_worksheet_events",
            "payroll_statutory_dual_control",
        }
        assert required <= set(tables), tables
    conn.commit()
print("MIGRATE_OK payroll_pifss_eos_wave5")
PY
