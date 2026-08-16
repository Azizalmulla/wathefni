#!/usr/bin/env bash
# Payroll Wave 2B — staging migrate for native preview schema.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import payroll_native_preview_wave2b as w2b
import payroll_authority_wave1 as pyw1
print("wave2b", w2b.PAYROLL_WAVE2B_VERSION)
print("policy", w2b.PREVIEW_POLICY_VERSION)
h = w2b.honesty_payload()
assert h["payment_processing"] == "disabled"
assert h["authoritative"] is False
assert h["preview_only"] is True
assert h["ai_calculations"] is False
assert h["external_flows_unchanged"] is True
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db != "wathefni" or os.environ.get("ACK_PRODUCTION_PAYROLL_W2B") == "YES"
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        w2b.ensure_payroll_wave2b_schema(cur, force=True)
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public' AND tablename LIKE 'payroll_preview_%'
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("preview_tables", tables)
        required = {
            "payroll_preview_policies",
            "payroll_preview_adjustments",
            "payroll_preview_runs",
            "payroll_preview_employee_results",
            "payroll_preview_lines",
            "payroll_preview_events",
        }
        assert required <= set(tables), tables
    conn.commit()
print("MIGRATE_OK payroll_native_preview_wave2b")
PY
