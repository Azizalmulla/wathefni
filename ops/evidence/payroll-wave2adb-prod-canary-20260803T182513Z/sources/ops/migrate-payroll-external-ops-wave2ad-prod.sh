#!/usr/bin/env bash
# Payroll Wave 2A-D-B — production ACK for External Run Operability.
# Ensures additive quarantine ack columns + operability helpers.
# Does NOT enable money / vendor / bank / package expansion / AI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PAYROLL_W2ADB:?Set ACK_PRODUCTION_PAYROLL_W2ADB=YES to migrate/ACK production}"
if [[ "${ACK_PRODUCTION_PAYROLL_W2ADB}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PAYROLL_W2ADB must be YES"
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
print("wave2ad_operability", w2a.PAYROLL_WAVE2AD_OPERABILITY_VERSION)
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)

for name in (
    "workspace_bootstrap",
    "period_readiness",
    "package_contents_payload",
    "acknowledge_quarantine",
    "list_quarantine",
    "rollback_export_run",
    "replace_import_results",
):
    assert callable(getattr(w2a, name, None)), name
print("operability_helpers_ok")

honesty = w2a.honesty_payload()
assert honesty.get("payment_processing") == "disabled"
assert honesty.get("money_authority") == "external"
assert honesty.get("wathefni_money_authority") is False
assert honesty.get("posts_payment") is False
assert honesty.get("vendor_claimed") is False
assert honesty.get("bank_files") is False
assert honesty.get("ai") is False
assert honesty.get("wave1_contracts_unchanged") is True
assert honesty.get("wave2a_adapter_contracts_unchanged") is True
pkg = honesty.get("package_contents") or {}
assert pkg.get("attendance_leave_shifts_packaged") is False
assert "approved_compensation_components" in (pkg.get("included") or [])
print("honesty_ok")

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
        # Additive ack columns present
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='payroll_adapter_quarantine'
              AND column_name IN ('acknowledged_at','acknowledged_by_phone','acknowledgement_reason')
            ORDER BY 1
            """
        )
        cols = {dict(r)["column_name"] for r in cur.fetchall()}
        assert cols == {
            "acknowledgement_reason",
            "acknowledged_at",
            "acknowledged_by_phone",
        }, sorted(cols)
        print("quarantine_ack_columns_ok", sorted(cols))
        boot = w2a.workspace_bootstrap(cur, company_code="WATHEFNI")
        assert isinstance(boot.get("setup"), dict)
        assert isinstance(boot.get("package_contents"), dict)
        print("bootstrap_setup_ok")
    conn.commit()

print("MIGRATE_OK")
print("ACK_PRODUCTION_PAYROLL_W2ADB=YES")
PY
