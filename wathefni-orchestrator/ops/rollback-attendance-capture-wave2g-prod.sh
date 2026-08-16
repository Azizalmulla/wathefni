#!/usr/bin/env bash
# Attendance Wave 2G — drop capture-ops durable tables on PRODUCTION after synthetic cleanup.
# Requires ACKs. Refuses if residual non-synthetic connector/site rows remain (unless FORCE_DROP=1).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${WATHEFNI_ENV:?WATHEFNI_ENV required}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: production rollback script only"
  exit 2
fi
: "${ACK_PRODUCTION_CAPTURE_ROLLBACK:?Set ACK_PRODUCTION_CAPTURE_ROLLBACK=1}"
if [[ "${ACK_PRODUCTION_CAPTURE_ROLLBACK}" != "1" ]]; then
  echo "REFUSE: ACK_PRODUCTION_CAPTURE_ROLLBACK must be 1"
  exit 2
fi
ACK_DB="${ACK_DB:-wathefni}"
SYNTHETIC_PREFIX="${SYNTHETIC_PREFIX:-ATTW2G}"
FORCE="${FORCE_DROP:-0}"

PYBIN="${ORCH_PYTHON:-/opt/wathefni/orchestrator/.venv/bin/python}"
"$PYBIN" - <<PY
import os, sys
sys.path.insert(0, ".")
import app
import attendance_capture_postgres as cap

expected = os.environ.get("ACK_DB") or "wathefni"
prefix = os.environ.get("SYNTHETIC_PREFIX", "ATTW2G")
force = os.environ.get("FORCE_DROP", "0").strip() in {"1", "true", "yes", "on"}

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
        print("connected_db", db)
        if db != expected or db != "wathefni":
            raise SystemExit(f"REFUSE db={db}")

        def count(table):
            cur.execute("SELECT to_regclass(%s) AS r", (table,))
            if not cur.fetchone()["r"]:
                return 0
            cur.execute(f"SELECT COUNT(*) AS n FROM {table}")
            return int(cur.fetchone()["n"])

        totals = {t: count(t) for t in (
            "attendance_capture_sites",
            "attendance_capture_connectors",
            "attendance_capture_remediation",
            "attendance_capture_replay_ledger",
            "attendance_capture_credentials",
        )}
        print("row_counts_before_drop", totals)
        residual = sum(totals.values())
        if residual > 0 and not force:
            # Allow drop only when caller already cleaned synthetics to zero, or FORCE_DROP.
            raise SystemExit(f"REFUSE rollback: capture tables still have {residual} rows (cleanup first or FORCE_DROP=1)")

        cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
        cur.execute(cap.WAVE2F_ROLLBACK_DDL)
    conn.commit()
print("ROLLBACK_SCHEMA_OK")
PY
