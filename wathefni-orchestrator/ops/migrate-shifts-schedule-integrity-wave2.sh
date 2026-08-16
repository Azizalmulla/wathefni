#!/usr/bin/env bash
# Shifts Wave 2 — apply schedule integrity schema (local/staging only).
# REFUSES production / ACK_DB=wathefni.
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
import shifts_schedule_integrity_wave2 as w2

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
print("env", os.environ.get("WATHEFNI_ENV"))
print("schema_version", w2.SHIFTS_WAVE2_VERSION)
print("expected_db", expected)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"REFUSE: connected to {db}, expected {expected}")
        w2.ensure_shifts_integrity_wave2_schema(cur)
        w2.seed_shift_integrity_settings(cur, "WATHEFNI")
        for tbl in (
            "shift_integrity_settings",
            "shift_assignment_versions",
            "shift_reminder_queue",
            "shift_seasonal_policies",
            "shift_reconciliation_flags",
        ):
            cur.execute("SELECT to_regclass(%s) AS t", (tbl,))
            print(tbl, dict(cur.fetchone())["t"])
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='shift_assignments'
              AND column_name IN ('current_version_no','schedule_reason_code','lineage_json')
            ORDER BY 1
            """
        )
        cols = [dict(r)["column_name"] for r in cur.fetchall()]
        print("shift_assignment_wave2_cols", cols)
    conn.commit()
print("SHIFTS_W2_MIGRATE_OK")
PY
