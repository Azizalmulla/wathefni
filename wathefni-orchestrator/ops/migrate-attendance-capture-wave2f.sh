#!/usr/bin/env bash
# Attendance Wave 2F — apply capture-ops PostgreSQL schema (staging/local only).
# Does NOT enable production flags, real punch ingest, or customer devices.
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
import attendance_capture_postgres as cap

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
        cap.ensure_attendance_capture_postgres_schema(cur)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public'
            AND tablename LIKE 'attendance_capture_%'
          ORDER BY 1
        """)
        tables = [r["tablename"] for r in cur.fetchall()]
        print("tables", tables)
        required = (
            "attendance_capture_sites",
            "attendance_capture_devices",
            "attendance_capture_connectors",
            "attendance_capture_credentials",
            "attendance_capture_health",
            "attendance_capture_health_events",
            "attendance_capture_checkpoints",
            "attendance_capture_mappings",
            "attendance_capture_quarantine",
            "attendance_capture_remediation",
            "attendance_capture_idempotency",
            "attendance_capture_audit_events",
            "attendance_capture_replay_ledger",
        )
        for req in required:
            assert req in tables, req
        cur.execute("""
          SELECT tgname FROM pg_trigger
          WHERE tgname IN (
            'trg_att_cap_audit_immutable',
            'trg_att_cap_replay_immutable'
          )
          ORDER BY 1
        """)
        print("triggers", [r["tgname"] for r in cur.fetchall()])
        # No plaintext secret columns
        cur.execute("""
          SELECT table_name, column_name FROM information_schema.columns
          WHERE table_name LIKE 'attendance_capture_%'
            AND column_name IN ('password','token','api_secret','secret','biotime_password')
        """)
        bad = cur.fetchall()
        assert not bad, bad
    conn.commit()
print("MIGRATE_OK")
print("authority_model=durable_postgres_capture_ops_wave2f_v1")
PY
