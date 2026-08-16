#!/usr/bin/env bash
# Payroll Wave 2B-B — production schema migrate (ACK required).
# Applies payroll_preview_* schema only. Does NOT alter Wave 1/2A DDL or external flows.
# payment_processing remains disabled; previews non-authoritative; no payslips/money.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PAYROLL_W2BB:?Set ACK_PRODUCTION_PAYROLL_W2BB=YES to migrate production}"
if [[ "${ACK_PRODUCTION_PAYROLL_W2BB}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PAYROLL_W2BB must be YES"
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
import payroll_native_preview_wave2b as w2b

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("wave2b_version", w2b.PAYROLL_WAVE2B_VERSION)
print("policy", w2b.PREVIEW_POLICY_VERSION)
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)
print("wave2a_version", w2a.PAYROLL_WAVE2A_VERSION)

h = w2b.honesty_payload()
assert h.get("payment_processing") == "disabled"
assert h.get("authoritative") is False
assert h.get("preview_only") is True
assert h.get("ai_calculations") is False
assert h.get("external_flows_unchanged") is True
assert h.get("bank_files") is False
assert h.get("pifss") is False
print("honesty_ok", {k: h[k] for k in (
    "payment_processing", "authoritative", "preview_only", "ai_calculations",
    "external_flows_unchanged", "synthetic_only",
)})

w2a_h = w2a.honesty_payload()
assert w2a_h.get("payment_processing") == "disabled"
assert w2a_h.get("money_authority") == "external"
assert w2a_h.get("vendor_claimed") is False
assert w2a_h.get("wave1_contracts_unchanged") is True

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
        # Wave 1 + Wave 2A tables still intact
        cur.execute("SELECT to_regclass('payroll_compensation_contracts') AS t")
        assert dict(cur.fetchone())["t"] is not None
        cur.execute("SELECT to_regclass('payroll_adapter_export_runs') AS t")
        assert dict(cur.fetchone())["t"] is not None
        print("wave1_wave2a_tables_ok")
    conn.commit()
print("MIGRATE_OK payroll_native_preview_wave2b_prod")
print("ACK_PRODUCTION_PAYROLL_W2BB=YES")
PY
