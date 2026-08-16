#!/usr/bin/env bash
# Attendance Wave 3 — apply exception-ops PostgreSQL schema (staging/local only).
# Does NOT enable production, real clocking, or devices.
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
import os, sys
sys.path.insert(0, ".")
import app
import attendance_ops_postgres as ops_pg

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
print("env", os.environ.get("WATHEFNI_ENV"))
print("expected_db", expected)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"DB mismatch: connected={db} expected={expected}")
        if db == "wathefni":
            raise SystemExit("REFUSE production database")
        ops_pg.ensure_attendance_ops_postgres_schema(cur)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public'
            AND tablename LIKE 'attendance_ops_%'
          ORDER BY 1
        """)
        tables = [r["tablename"] for r in cur.fetchall()]
        print("tables", tables)
        required = (
            "attendance_ops_exceptions",
            "attendance_ops_cases",
            "attendance_ops_disputes",
            "attendance_ops_comments",
            "attendance_ops_attachments",
            "attendance_ops_audit_events",
            "attendance_ops_idempotency",
        )
        for req in required:
            assert req in tables, req
        cur.execute("""
          SELECT tgname FROM pg_trigger
          WHERE tgname = 'trg_att_ops_audit_immutable'
        """)
        print("triggers", [r["tgname"] for r in cur.fetchall()])
print("OK wave3 schema")
PY
