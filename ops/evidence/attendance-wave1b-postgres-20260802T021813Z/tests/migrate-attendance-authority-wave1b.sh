#!/usr/bin/env bash
# Attendance Wave 1B — apply authority Postgres schema (staging/local only).
# Does NOT enable production flags or real clocking.
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

python3 - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import attendance_authority_wave1 as core
import attendance_authority_postgres as pg

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
# Soft check via app env marker when available
print("env", os.environ.get("WATHEFNI_ENV"))
print("expected_db", expected)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database()")
        db = cur.fetchone()["current_database"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"DB mismatch: connected={db} expected={expected}")
        if db == "wathefni":
            raise SystemExit("REFUSE production database")
        pg.ensure_attendance_authority_postgres_schema(cur)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public'
            AND tablename LIKE 'attendance_%'
          ORDER BY 1
        """)
        tables = [r["tablename"] for r in cur.fetchall()]
        print("tables", tables)
        for req in (
            "attendance_punches",
            "attendance_day_projections",
            "attendance_corrections",
            "attendance_payroll_snapshots",
            "attendance_authority_events",
            "attendance_compat_drift",
        ):
            assert req in tables, req
        cur.execute("""
          SELECT tgname FROM pg_trigger
          WHERE tgname IN (
            'trg_attendance_punches_immutable',
            'trg_attendance_payroll_snapshots_immutable'
          )
          ORDER BY 1
        """)
        print("triggers", [r["tgname"] for r in cur.fetchall()])
    conn.commit()
print("MIGRATE_OK")
PY
