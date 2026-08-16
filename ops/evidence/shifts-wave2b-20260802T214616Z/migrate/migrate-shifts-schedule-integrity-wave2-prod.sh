#!/usr/bin/env bash
# Shifts Wave 2B — production schema migrate (ACK required).
# Applies integrity schema only. Does NOT enable real-employee mutations.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_SHIFTS_W2B:?ACK_PRODUCTION_SHIFTS_W2B=YES required}"
if [[ "${ACK_PRODUCTION_SHIFTS_W2B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_SHIFTS_W2B must be YES"
  exit 2
fi

: "${WATHEFNI_ENV:?}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import shifts_schedule_integrity_wave2 as w2

assert os.environ.get("WATHEFNI_ENV") == "production"
assert os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") == "wathefni"
print("schema_version", w2.SHIFTS_WAVE2_VERSION)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni"
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
            assert dict(cur.fetchone())["t"], tbl
            print(tbl, "ok")
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
        assert set(cols) >= {"current_version_no", "schedule_reason_code", "lineage_json"}
    conn.commit()
print("SHIFTS_W2B_PROD_MIGRATE_OK")
PY
