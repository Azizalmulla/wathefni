#!/usr/bin/env bash
# Attendance Wave 1B — safe rollback of Wave 1B additive objects.
# Refuses if non-synthetic company data exists in authority tables.
# Set ROLLBACK_DROP_BASE=1 to also drop Wave 1 base tables (still refuses residual).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${WATHEFNI_ENV:?WATHEFNI_ENV required}"
if [[ "${WATHEFNI_ENV}" == "production" ]]; then
  echo "REFUSE: will not rollback production from this script"
  exit 2
fi

ACK_DB="${ACK_DB:-${WATHEFNI_EXPECTED_DATABASE_NAME:-}}"
: "${ACK_DB:?ACK_DB required}"
SYNTHETIC_PREFIX="${SYNTHETIC_PREFIX:-ATTW1}"

python3 - <<PY
import os, sys
sys.path.insert(0, ".")
import app
import attendance_authority_postgres as pg

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
prefix = os.environ.get("SYNTHETIC_PREFIX", "ATTW1")
drop_base = os.environ.get("ROLLBACK_DROP_BASE", "").strip() in {"1", "true", "yes", "on"}

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"DB mismatch: {db} != {expected}")
        if db == "wathefni":
            raise SystemExit("REFUSE production database")

        def residual(table, col="company_code"):
            cur.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {col} NOT LIKE %s", (prefix + "%",))
            return int(cur.fetchone()["n"])

        for table in (
            "attendance_punches",
            "attendance_day_projections",
            "attendance_corrections",
            "attendance_payroll_snapshots",
            "attendance_authority_events",
            "attendance_compat_drift",
        ):
            cur.execute("SELECT to_regclass(%s) AS r", (table,))
            if not cur.fetchone()["r"]:
                print("missing", table)
                continue
            n = residual(table)
            print(f"residual_non_synthetic {table}={n}")
            if n > 0:
                raise SystemExit(f"REFUSE rollback: {table} has {n} non-synthetic rows")

        cur.execute(pg.WAVE1B_ROLLBACK_DDL)
        if drop_base:
            cur.execute("""
              DROP TABLE IF EXISTS attendance_payroll_snapshots CASCADE;
              DROP TABLE IF EXISTS attendance_corrections CASCADE;
              DROP TABLE IF EXISTS attendance_day_projections CASCADE;
              DROP TABLE IF EXISTS attendance_punches CASCADE;
            """)
            print("base_tables_dropped=true")
        else:
            print("base_tables_retained=true")
    conn.commit()
print("ROLLBACK_OK")
PY
