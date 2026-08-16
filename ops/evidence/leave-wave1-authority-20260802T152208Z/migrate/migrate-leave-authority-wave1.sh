#!/usr/bin/env bash
# Leave Wave 1 — apply authority schema pack (local/staging only).
# Does NOT enable balances_enforced / legal_reviewed.
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
import leave_authority_wave1 as leave_w1

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
print("env", os.environ.get("WATHEFNI_ENV"))
print("schema_version", leave_w1.LEAVE_AUTHORITY_SCHEMA_VERSION)
print("expected_db", expected)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"DB mismatch: connected={db} expected={expected}")
        if db == "wathefni":
            raise SystemExit("REFUSE production database")
        leave_w1.ensure_leave_authority_wave1_schema(cur)
        leave_w1.seed_company_leave_authority_settings(cur, "WATHEFNI")
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='leave_requests' AND column_name='row_version'
            """
        )
        assert cur.fetchone(), "leave_requests.row_version missing"
        cur.execute(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname='public'
              AND tablename IN ('leave_authority_settings','leave_type_catalogue')
            ORDER BY 1
            """
        )
        tables = [dict(r)["tablename"] for r in cur.fetchall()]
        print("tables", tables)
        assert tables == ["leave_authority_settings", "leave_type_catalogue"], tables
        cur.execute("SELECT leave_type, ledger_eligible FROM leave_type_catalogue ORDER BY leave_type")
        catalogue = [dict(r) for r in cur.fetchall()]
        print("catalogue", catalogue)
        assert {r["leave_type"] for r in catalogue} >= {"annual", "sick", "unpaid", "other"}
        cur.execute("SELECT balances_enforced, legal_reviewed FROM leave_authority_settings WHERE company_code='WATHEFNI'")
        settings = dict(cur.fetchone() or {})
        assert settings.get("balances_enforced") is False
        assert settings.get("legal_reviewed") is False
    conn.commit()
print("MIGRATE_OK leave_authority_wave1")
PY
