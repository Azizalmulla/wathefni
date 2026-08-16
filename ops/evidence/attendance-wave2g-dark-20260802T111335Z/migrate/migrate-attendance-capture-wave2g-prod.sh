#!/usr/bin/env bash
# Attendance Wave 2G — apply capture-ops Postgres schema on PRODUCTION.
# Requires explicit ACKs. Does NOT enable CAPTURE_INGEST or customer devices.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${WATHEFNI_ENV:?WATHEFNI_ENV required}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: this migrate is production-only (got WATHEFNI_ENV=$WATHEFNI_ENV)"
  exit 2
fi

: "${ACK_PRODUCTION_CAPTURE_PERSISTENCE:?Set ACK_PRODUCTION_CAPTURE_PERSISTENCE=1 to proceed}"
if [[ "${ACK_PRODUCTION_CAPTURE_PERSISTENCE}" != "1" ]]; then
  echo "REFUSE: ACK_PRODUCTION_CAPTURE_PERSISTENCE must be 1"
  exit 2
fi

ACK_DB="${ACK_DB:-${WATHEFNI_EXPECTED_DATABASE_NAME:-}}"
: "${ACK_DB:?ACK_DB required}"
if [[ "$ACK_DB" != "wathefni" ]]; then
  echo "REFUSE: ACK_DB must be wathefni for production migrate (got $ACK_DB)"
  exit 2
fi

PYBIN="${ORCH_PYTHON:-/opt/wathefni/orchestrator/.venv/bin/python}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import attendance_capture_postgres as cap

expected = os.environ.get("ACK_DB") or "wathefni"
print("env", os.environ.get("WATHEFNI_ENV"))
print("expected_db", expected)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
        print("connected_db", db)
        if db != expected:
            raise SystemExit(f"DB mismatch: connected={db} expected={expected}")
        if db != "wathefni":
            raise SystemExit("REFUSE: not production database")
        cap.ensure_attendance_capture_postgres_schema(cur)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public' AND tablename LIKE 'attendance_capture_%'
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
          WHERE tgname IN ('trg_att_cap_audit_immutable','trg_att_cap_replay_immutable')
          ORDER BY 1
        """)
        print("triggers", [r["tgname"] for r in cur.fetchall()])
        cur.execute("""
          SELECT table_name, column_name FROM information_schema.columns
          WHERE table_name LIKE 'attendance_capture_%'
            AND column_name IN ('password','token','api_secret','secret','biotime_password')
        """)
        bad = cur.fetchall()
        assert not bad, bad
    conn.commit()
print("MIGRATE_OK")
print("authority_model=durable_postgres_capture_ops_wave2g_v1")
PY
