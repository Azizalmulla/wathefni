#!/usr/bin/env bash
# Payroll Wave 1 — apply authority foundation schema (local/staging only).
# Does NOT enable payment_processing or money authority.
# Does NOT touch production wathefni DB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${WATHEFNI_ENV:?WATHEFNI_ENV required (staging|local|development)}"
if [[ "${WATHEFNI_ENV}" == "production" ]]; then
  echo "REFUSE: will not migrate production from this script"
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

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
print("env", os.environ.get("WATHEFNI_ENV"))
print("wave1_version", pyw1.PAYROLL_WAVE1_VERSION)
print("expected_db", expected)
honesty = pyw1.honesty_payload()
assert honesty.get("payment_processing") == "disabled"
assert honesty.get("money_authority") is False
print("honesty", {k: honesty[k] for k in ("payment_processing", "money_authority", "modes", "annual_leave_eligibility_months")})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"DB mismatch: connected={db} expected={expected}")
        if db == "wathefni":
            raise SystemExit("REFUSE production database")
        pyw1.ensure_payroll_wave1_schema(cur, force=True)
        settings = pyw1.ensure_company_settings(cur, company_code="WATHEFNI")
        assert settings.get("payment_processing") == "disabled"
        assert int(settings.get("annual_leave_eligibility_months") or 0) == 6
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public'
              AND tablename IN (
                'payroll_company_settings',
                'payroll_compensation_contracts',
                'payroll_compensation_components',
                'payroll_compensation_events',
                'payroll_periods',
                'payroll_period_events'
              )
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("tables", tables)
        assert len(tables) == 6, tables
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='payroll_timesheets'
              AND column_name IN ('quarantine_status', 'row_version')
            ORDER BY 1
            """
        )
        cols = [dict(r)["column_name"] for r in cur.fetchall()]
        print("timesheet_cols", cols)
        assert "quarantine_status" in cols and "row_version" in cols, cols
        q = pyw1.quarantine_smoke_timesheets(cur, company_code="WATHEFNI")
        print("quarantine", {"ok": q.get("ok"), "count": q.get("count"), "hard_deleted": q.get("hard_deleted")})
        assert q.get("ok") is True
        assert q.get("hard_deleted") is False
    conn.commit()
print("MIGRATE_OK payroll_authority_wave1")
PY
