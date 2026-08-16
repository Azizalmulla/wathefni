#!/usr/bin/env bash
# Shifts Wave 1B — production schema migrate (ACK required).
# Does NOT enable flags. Does NOT touch real assignment rows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_SHIFTS_W1B:?ACK_PRODUCTION_SHIFTS_W1B=YES required}"
if [[ "${ACK_PRODUCTION_SHIFTS_W1B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_SHIFTS_W1B must be YES"
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
import shifts_authority_wave1 as sw1

assert os.environ.get("WATHEFNI_ENV") == "production"
assert os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") == "wathefni"
print("schema_version", sw1.SHIFTS_WAVE1_VERSION)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni"
        sw1.ensure_shifts_authority_wave1_schema(cur)
        sw1.seed_shift_authority_settings(cur, "WATHEFNI")
        cur.execute(
            """
            UPDATE shift_authority_settings
            SET synthetic_only=true,
                block_notice_period=false,
                garden_leave_during_notice=false,
                beyond_end_mode='require_ack',
                allow_overnight=true,
                updated_at=now()
            WHERE company_code='WATHEFNI'
            """
        )
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
        assert set(cols) >= {"ends_next_day", "break_minutes", "site_key", "idempotency_key", "row_version"}
        cur.execute("SELECT to_regclass('shift_orphan_quarantine') AS t")
        assert dict(cur.fetchone())["t"]
        cur.execute("SELECT to_regclass('shift_lifecycle_flags') AS t")
        assert dict(cur.fetchone())["t"]
        cur.execute("SELECT synthetic_only, block_notice_period FROM shift_authority_settings WHERE company_code='WATHEFNI'")
        s = dict(cur.fetchone())
        print("settings", s)
        assert s["synthetic_only"] is True
        assert s["block_notice_period"] is False
    conn.commit()
print("SHIFTS_W1B_PROD_MIGRATE_OK")
PY
