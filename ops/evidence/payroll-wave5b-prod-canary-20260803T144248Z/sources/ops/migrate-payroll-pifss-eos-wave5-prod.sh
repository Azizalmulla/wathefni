#!/usr/bin/env bash
# Payroll Wave 5-B — production schema migrate (ACK required).
# Applies payroll_statutory_* / payroll_pifss_* / payroll_eos_* worksheet schema only.
# Does NOT alter Wave 1/2A/2B/3/4 DDL or flows.
# payment_processing remains disabled; review worksheets only (no remittance/filing).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PAYROLL_W5B:?Set ACK_PRODUCTION_PAYROLL_W5B=YES to migrate production}"
if [[ "${ACK_PRODUCTION_PAYROLL_W5B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PAYROLL_W5B must be YES"
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
import payroll_pifss_eos_wave5 as w5

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("wave5_version", w5.PAYROLL_WAVE5_VERSION)
print("wave4_version", w4.PAYROLL_WAVE4_VERSION)
print("wave3_version", w3.PAYROLL_WAVE3_VERSION)
print("wave2b_version", w2b.PAYROLL_WAVE2B_VERSION)
print("wave2a_version", w2a.PAYROLL_WAVE2A_VERSION)
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)

h = w5.honesty_payload()
assert h.get("payment_processing") == "disabled"
assert h.get("posts_payment") is False
assert h.get("remittance") is False
assert h.get("statutory_filing") is False
assert h.get("automatic_legal_compliance_claim") is False
assert h.get("pifss_worksheets") is True and h.get("pifss_remittance") is False
assert h.get("eos_worksheets") is True and h.get("eos_auto_payable") is False
assert h.get("bank_files") is False and h.get("wps") is False and h.get("ashal") is False
assert h.get("ai_calculations") is False
assert h.get("native_results_authoritative") is False
assert h.get("external_payroll_authority") == "external"
assert h.get("wave1_flows_unchanged") is True
assert h.get("wave2a_flows_unchanged") is True
assert h.get("wave2b_flows_unchanged") is True
assert h.get("wave3_flows_unchanged") is True
assert h.get("wave4_flows_unchanged") is True
print("honesty_ok", {k: h[k] for k in (
    "payment_processing", "posts_payment", "remittance", "statutory_filing",
    "pifss_worksheets", "pifss_remittance", "eos_worksheets", "eos_auto_payable",
    "automatic_legal_compliance_claim", "native_results_authoritative",
    "external_payroll_authority", "ai_calculations", "synthetic_only",
)})

inv = w5.freeze_invariants()
assert inv.get("missing_rule_fail_closed") is True
assert inv.get("approved_history_immutable") is True
assert inv.get("no_remittance") is True and inv.get("no_auto_payable") is True
assert inv.get("category_separation") is True and inv.get("effective_dated_rules") is True

w4_h = w4.honesty_payload()
assert w4_h.get("payment_processing") == "disabled" and w4_h.get("journals") is False
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
        for t in (
            "payroll_compensation_contracts",
            "payroll_adapter_export_runs",
            "payroll_preview_runs",
            "payroll_payslip_documents",
            "payroll_close_runs",
        ):
            cur.execute("SELECT to_regclass(%s) AS t", (t,))
            assert dict(cur.fetchone())["t"] is not None, t
        print("wave1_2a_2b_3_4_tables_ok")
    conn.commit()
print("MIGRATE_OK payroll_pifss_eos_wave5_prod")
print("ACK_PRODUCTION_PAYROLL_W5B=YES")
PY
