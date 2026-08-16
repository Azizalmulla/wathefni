#!/usr/bin/env bash
# Attendance Wave 2F — rollback capture-ops tables (staging/local only).
# Refuses production DB and refuses residual non-synthetic rows unless FORCE_DROP=1
# with SYNTHETIC_PREFIX match-only cleanup first.
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
SYNTHETIC_PREFIX="${SYNTHETIC_PREFIX:-ATTW2F}"

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<PY
import os, sys
sys.path.insert(0, ".")
import app
import attendance_capture_postgres as cap

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
prefix = os.environ.get("SYNTHETIC_PREFIX", "ATTW2F")
force = os.environ.get("FORCE_DROP", "").strip().lower() in {"1", "true", "yes", "on"}

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
            cur.execute(f"SELECT to_regclass(%s) AS r", (table,))
            if not cur.fetchone()["r"]:
                return 0
            cur.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE {col} NOT LIKE %s AND {col} NOT LIKE %s",
                (prefix + "%", "ATTW2F%"),
            )
            return int(cur.fetchone()["n"])

        for table in (
            "attendance_capture_sites",
            "attendance_capture_connectors",
            "attendance_capture_remediation",
            "attendance_capture_replay_ledger",
        ):
            n = residual(table)
            print(f"residual_non_synthetic {table}={n}")
            if n > 0 and not force:
                raise SystemExit(f"REFUSE rollback: {table} has {n} non-synthetic rows (set FORCE_DROP=1 to override on staging)")

        cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
        cur.execute(cap.WAVE2F_ROLLBACK_DDL)
    conn.commit()
print("ROLLBACK_OK")
PY
