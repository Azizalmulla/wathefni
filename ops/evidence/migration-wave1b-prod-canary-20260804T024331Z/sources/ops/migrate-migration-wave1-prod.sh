#!/usr/bin/env bash
# Migration Wave 1-B — production ACK + schema ensure (WATHEFNI synthetic only).
# Does NOT enable real customer migration, millions cutover, Wave 2, money, or ingest.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_MIGRATION_WAVE1B:?Set ACK_PRODUCTION_MIGRATION_WAVE1B=YES to ACK production}"
if [[ "${ACK_PRODUCTION_MIGRATION_WAVE1B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_MIGRATION_WAVE1B must be YES"
  exit 2
fi

: "${WATHEFNI_ENV:?}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

INGEST="${WATHEFNI_ATTENDANCE_CAPTURE_INGEST:-off}"
if echo "$INGEST" | grep -qiE '^(on|true|1|yes)$'; then
  echo "REFUSE: WATHEFNI_ATTENDANCE_CAPTURE_INGEST must remain off" >&2
  exit 3
fi

export WATHEFNI_MIGRATION_WAVE1="${WATHEFNI_MIGRATION_WAVE1:-1}"
export WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY="${WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY:-1}"
export WATHEFNI_MIGRATION_WAVE1_COMPANIES="${WATHEFNI_MIGRATION_WAVE1_COMPANIES:-WATHEFNI}"
# Wave 1-BR: migrate scripts are the only allowed schema mutators.
export WATHEFNI_SCHEMA_APPLY=1

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os
import sys

sys.path.insert(0, ".")
import app
import migration_wave1_cv_foundation as mig

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
assert mig.migration_wave1_enabled()
assert mig.migration_wave1_synthetic_only()
assert os.environ.get("WATHEFNI_SCHEMA_APPLY") == "1"
allowed = mig.allowed_companies()
assert allowed is not None and "WATHEFNI" in allowed, allowed
assert os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off").lower() in {
    "off", "0", "false", "no", ""
}

honesty = mig.honesty_payload()
assert honesty["auto_admit"] is False
assert honesty["millions_claim"] is False
assert honesty["real_customer_data"] is False
assert honesty["payroll_money"] is False

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        assert db == "wathefni", db
        mig.apply_schema(cur)
        ack_id = mig.record_wave_ack(
            cur,
            wave="migration_wave1_foundation_cv_chunked",
            company_code="WATHEFNI",
            environment="production",
            detail={
                **honesty,
                "ack": "ACK_PRODUCTION_MIGRATION_WAVE1B=YES",
                "marker": "MIGW1B",
            },
        )
        conn.commit()
        print("ack_id", ack_id)
        print("ACK_PRODUCTION_MIGRATION_WAVE1B=YES")
        print("residual_policy=synthetic_batches_rolled_back_ack_retained")
print("MIGRATE_OK")
PY
