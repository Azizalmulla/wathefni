#!/usr/bin/env bash
# Attendance Wave 3 — apply ops Postgres schema on PRODUCTION (synthetic canary).
# Requires explicit ACKs. Does NOT enable CAPTURE_INGEST, devices, or real clocking.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${WATHEFNI_ENV:?WATHEFNI_ENV required}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: this migrate is production-only (got WATHEFNI_ENV=$WATHEFNI_ENV)"
  exit 2
fi

: "${ACK_PRODUCTION_ATTENDANCE_OPS_WAVE3:?Set ACK_PRODUCTION_ATTENDANCE_OPS_WAVE3=1 to proceed}"
if [[ "${ACK_PRODUCTION_ATTENDANCE_OPS_WAVE3}" != "1" ]]; then
  echo "REFUSE: ACK_PRODUCTION_ATTENDANCE_OPS_WAVE3 must be 1"
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
import attendance_ops_postgres as ops_pg

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
        ops_pg.ensure_attendance_ops_postgres_schema(cur)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public' AND tablename LIKE 'attendance_ops_%'
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
          SELECT tgname FROM pg_trigger WHERE tgname='trg_att_ops_audit_immutable'
        """)
        print("triggers", [r["tgname"] for r in cur.fetchall()])
print("OK wave3 prod schema")
PY
