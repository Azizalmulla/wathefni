#!/usr/bin/env bash
# Payroll Wave 3-B — production schema migrate (ACK required).
# Applies payroll_payslip_* schema only. Does NOT alter Wave 1/2A/2B DDL or flows.
# payment_processing remains disabled; payslips are documents only (not money).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PAYROLL_W3B:?Set ACK_PRODUCTION_PAYROLL_W3B=YES to migrate production}"
if [[ "${ACK_PRODUCTION_PAYROLL_W3B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PAYROLL_W3B must be YES"
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
import payroll_payslip_wave3 as w3

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("wave3_version", w3.PAYROLL_WAVE3_VERSION)
print("wave2b_version", w2b.PAYROLL_WAVE2B_VERSION)
print("wave2a_version", w2a.PAYROLL_WAVE2A_VERSION)
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)

h = w3.honesty_payload()
assert h.get("payment_processing") == "disabled"
assert h.get("payslips_as_money") is False
assert h.get("native_payslips_authoritative") is False
assert h.get("external_payslips_authority") == "external"
assert h.get("ai_calculations") is False
assert h.get("bank_files") is False
assert h.get("wave1_contracts_unchanged") is True
assert h.get("wave2a_flows_unchanged") is True
assert h.get("wave2b_flows_unchanged") is True
print("honesty_ok", {k: h[k] for k in (
    "payment_processing", "payslips_as_money", "native_payslips_authoritative",
    "external_payslips_authority", "ai_calculations", "synthetic_only",
)})

w2a_h = w2a.honesty_payload()
assert w2a_h.get("money_authority") == "external" and w2a_h.get("vendor_claimed") is False
w2b_h = w2b.honesty_payload()
assert w2b_h.get("authoritative") is False and w2b_h.get("payment_processing") == "disabled"

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
        for t in ("payroll_compensation_contracts", "payroll_adapter_export_runs", "payroll_preview_runs"):
            cur.execute("SELECT to_regclass(%s) AS t", (t,))
            assert dict(cur.fetchone())["t"] is not None, t
        print("wave1_2a_2b_tables_ok")
    conn.commit()
print("MIGRATE_OK payroll_payslip_wave3_prod")
print("ACK_PRODUCTION_PAYROLL_W3B=YES")
PY
