#!/usr/bin/env bash
# Payroll Wave 4-B — production schema migrate (ACK required).
# Applies payroll_close_* / journal / bank-export / finance-export schema only.
# Does NOT alter Wave 1/2A/2B/3 DDL or flows.
# payment_processing remains disabled; journal drafts + bank-export contract validation only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PAYROLL_W4B:?Set ACK_PRODUCTION_PAYROLL_W4B=YES to migrate production}"
if [[ "${ACK_PRODUCTION_PAYROLL_W4B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PAYROLL_W4B must be YES"
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
import payroll_close_export_wave4 as w4

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("wave4_version", w4.PAYROLL_WAVE4_VERSION)
print("wave3_version", w3.PAYROLL_WAVE3_VERSION)
print("wave2b_version", w2b.PAYROLL_WAVE2B_VERSION)
print("wave2a_version", w2a.PAYROLL_WAVE2A_VERSION)
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)

h = w4.honesty_payload()
assert h.get("payment_processing") == "disabled"
assert h.get("posts_payment") is False
assert h.get("bank_files") is False
assert h.get("bank_connection") is False
assert h.get("wps") is False
assert h.get("ashal") is False
assert h.get("journals") is False
assert h.get("journal_drafts") is True
assert h.get("bank_export_contract") is True
assert h.get("pifss") is False
assert h.get("eos") is False
assert h.get("ai_calculations") is False
assert h.get("native_results_authoritative") is False
assert h.get("external_payroll_authority") == "external"
assert h.get("wave1_contracts_unchanged") is True
assert h.get("wave2a_flows_unchanged") is True
assert h.get("wave2b_flows_unchanged") is True
assert h.get("wave3_flows_unchanged") is True
print("honesty_ok", {k: h[k] for k in (
    "payment_processing", "posts_payment", "journal_drafts", "journals",
    "bank_export_contract", "bank_files", "native_results_authoritative",
    "external_payroll_authority", "ai_calculations", "synthetic_only",
)})

w3_h = w3.honesty_payload()
assert w3_h.get("payment_processing") == "disabled" and w3_h.get("payslips_as_money") is False
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
        w4.ensure_payroll_wave4_schema(cur, force=True)
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public' AND (
              tablename LIKE 'payroll_close_%'
              OR tablename LIKE 'payroll_account_%'
              OR tablename LIKE 'payroll_journal_%'
              OR tablename LIKE 'payroll_bank_export_%'
              OR tablename = 'payroll_finance_exports'
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
        for t in (
            "payroll_compensation_contracts",
            "payroll_adapter_export_runs",
            "payroll_preview_runs",
            "payroll_payslip_documents",
        ):
            cur.execute("SELECT to_regclass(%s) AS t", (t,))
            assert dict(cur.fetchone())["t"] is not None, t
        print("wave1_2a_2b_3_tables_ok")
    conn.commit()
print("MIGRATE_OK payroll_close_export_wave4_prod")
print("ACK_PRODUCTION_PAYROLL_W4B=YES")
PY
