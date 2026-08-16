#!/usr/bin/env bash
# Shifts Wave 1 — apply authority schema pack (local/staging only).
# Does NOT deploy production. Does NOT enable templates/recurring/publish.
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
import shifts_authority_wave1 as sw1

expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
print("env", os.environ.get("WATHEFNI_ENV"))
print("schema_version", sw1.SHIFTS_WAVE1_VERSION)
print("expected_db", expected)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        if expected and db != expected:
            raise SystemExit(f"REFUSE: connected to {db}, expected {expected}")
        sw1.ensure_shifts_authority_wave1_schema(cur)
        sw1.seed_shift_authority_settings(cur, "WATHEFNI")
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='shift_assignments'
              AND column_name IN ('ends_next_day','break_minutes','site_key','idempotency_key','row_version')
            ORDER BY 1
            """
        )
        cols = [dict(r)["column_name"] for r in cur.fetchall()]
        print("shift_assignment_wave1_cols", cols)
        cur.execute("SELECT to_regclass('shift_orphan_quarantine') AS t")
        print("orphan_table", dict(cur.fetchone())["t"])
    conn.commit()
print("SHIFTS_W1_MIGRATE_OK")
PY
