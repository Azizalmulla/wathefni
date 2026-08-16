#!/usr/bin/env bash
# Payroll Wave 2A-C-B — production ACK for external ops workflow.
# Re-ensures Wave 2A adapter schema (additive, unchanged DDL) and verifies
# Wave 2A-C ops helpers are importable. Does NOT alter Wave 1/2A contracts.
# Does NOT enable money / bank / vendor / native G2N / Wave 2B.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PAYROLL_W2ACB:?Set ACK_PRODUCTION_PAYROLL_W2ACB=YES to migrate/ACK production}"
if [[ "${ACK_PRODUCTION_PAYROLL_W2ACB}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PAYROLL_W2ACB must be YES"
  exit 2
fi

: "${WATHEFNI_ENV:?}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os
import sys

sys.path.insert(0, ".")
import app
import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("wave2a_version", w2a.PAYROLL_WAVE2A_VERSION)
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)

# Ops helpers required by Wave 2A-C workflow
for name in (
    "workspace_bootstrap",
    "period_readiness",
    "assemble_period_export_inputs",
    "list_export_runs",
    "list_import_runs",
    "list_quarantine",
    "list_events",
    "list_import_lines",
    "get_reconciliation",
    "replace_import_results",
):
    assert callable(getattr(w2a, name, None)), name
print("ops_helpers_ok")

honesty = w2a.honesty_payload()
assert honesty.get("payment_processing") == "disabled"
assert honesty.get("money_authority") == "external"
assert honesty.get("wathefni_money_authority") is False
assert honesty.get("posts_payment") is False
assert honesty.get("vendor_claimed") is False
assert honesty.get("bank_files") is False
assert honesty.get("native_gross_to_net") is False
assert honesty.get("wave1_contracts_unchanged") is True
print("honesty_ok", {k: honesty[k] for k in ("payment_processing", "money_authority", "vendor_claimed", "adapter_kind")})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni", db
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        settings = pyw1.ensure_company_settings(cur, company_code="WATHEFNI")
        assert settings.get("payment_processing") == "disabled"
        w2a.ensure_payroll_wave2a_schema(cur, force=True)
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public' AND tablename LIKE 'payroll_adapter_%'
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("adapter_tables", tables)
        required = {
            "payroll_adapter_export_runs",
            "payroll_adapter_import_runs",
            "payroll_adapter_import_lines",
            "payroll_adapter_quarantine",
            "payroll_adapter_reconciliations",
            "payroll_adapter_events",
        }
        assert required <= set(tables), tables
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='payroll_compensation_contracts'
              AND column_name IN ('contract_id','row_version','status')
            ORDER BY 1
            """
        )
        cols = [dict(r)["column_name"] for r in cur.fetchall()]
        assert set(cols) >= {"contract_id", "row_version", "status"}, cols
        print("wave1_contract_cols_ok", cols)
    conn.commit()

# Dashboard routes for external ops must be registered
paths = {getattr(r, "path", None) for r in app.app.routes}
needed = {
    "/dashboard/posthire/payroll/external",
    "/dashboard/posthire/payroll/external/readiness",
    "/dashboard/posthire/payroll/external/exports",
    "/dashboard/posthire/payroll/external/quarantine",
    "/dashboard/posthire/payroll/external/events",
}
missing = sorted(needed - paths)
print("routes_present", sorted(needed & paths))
assert not missing, missing
print("MIGRATE_OK payroll_external_ops_wave2ac_prod")
print("ACK_PRODUCTION_PAYROLL_W2ACB=YES")
PY
