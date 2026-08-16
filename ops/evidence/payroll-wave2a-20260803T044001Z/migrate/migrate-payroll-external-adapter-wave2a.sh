#!/usr/bin/env bash
# Payroll Wave 2A — apply external adapter schema (local/staging only).
# Does NOT alter Wave 1 contract DDL. Does NOT enable money / bank files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${WATHEFNI_ENV:?WATHEFNI_ENV required (staging|local|development)}"
if [[ "${WATHEFNI_ENV}" == "production" ]]; then
  echo "REFUSE: will not migrate production from this staging script"
  exit 2
fi

ACK_DB="${ACK_DB:-${WATHEFNI_EXPECTED_DATABASE_NAME:-}}"
: "${ACK_DB:?ACK_DB or WATHEFNI_EXPECTED_DATABASE_NAME required}"
if [[ "$ACK_DB" == "wathefni" ]]; then
  echo "REFUSE: ACK_DB=wathefni looks like production"
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

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
print("env", os.environ.get("WATHEFNI_ENV"))
print("wave2a_version", w2a.PAYROLL_WAVE2A_VERSION)
print("expected_db", expected)
honesty = w2a.honesty_payload()
assert honesty.get("payment_processing") == "disabled"
assert honesty.get("money_authority") == "external"
assert honesty.get("wathefni_money_authority") is False
assert honesty.get("posts_payment") is False
assert honesty.get("vendor_claimed") is False
assert honesty.get("wave1_contracts_unchanged") is True
print("honesty", {k: honesty[k] for k in ("payment_processing", "money_authority", "adapter_kind", "vendor_claimed")})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"DB mismatch: connected={db} expected={expected}")
        if db == "wathefni":
            raise SystemExit("REFUSE production database")
        # Ensure Wave 1 present (dependency) without changing its contracts
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        w2a.ensure_payroll_wave2a_schema(cur, force=True)
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public'
              AND tablename LIKE 'payroll_adapter_%'
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("adapter_tables", tables)
        assert "payroll_adapter_export_runs" in tables
        assert "payroll_adapter_import_runs" in tables
        assert "payroll_adapter_quarantine" in tables
        assert "payroll_adapter_reconciliations" in tables
        # Prove Wave 1 contract table still intact
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='payroll_compensation_contracts'
              AND column_name='row_version'
            """
        )
        assert cur.fetchone(), "wave1 contract row_version missing — unexpected"
    conn.commit()
print("MIGRATE_OK payroll_external_adapter_wave2a")
PY
