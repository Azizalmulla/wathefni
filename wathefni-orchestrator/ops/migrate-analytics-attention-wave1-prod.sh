#!/usr/bin/env bash
# Analytics Wave 1-B — production ACK + additive schema (ACK required).
# Creates analytics_wave_acks only. No frozen-module schema changes.
# Does NOT enable AI, Compliance metrics, or payroll money analytics.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_ANALYTICS_W1B:?Set ACK_PRODUCTION_ANALYTICS_W1B=YES to migrate production}"
if [[ "${ACK_PRODUCTION_ANALYTICS_W1B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_ANALYTICS_W1B must be YES"
  exit 2
fi

: "${WATHEFNI_ENV:?}"
if [[ "${WATHEFNI_ENV}" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os
import sys

sys.path.insert(0, ".")
import app
import analytics_attention_wave1 as anw1

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
honesty = anw1.honesty_payload()
assert honesty.get("read_only") is True
assert honesty.get("money_authority") is False
assert honesty.get("ai") is False
assert honesty.get("compliance_metrics") is False
assert honesty.get("payroll_cost_analytics") is False
assert honesty.get("hiring_reports_separate") is True
print("wave1_version", anw1.ANALYTICS_WAVE1_VERSION)
print("contract", anw1.ANALYTICS_WAVE1_CONTRACT)
print("honesty_ok", {k: honesty[k] for k in ("read_only", "money_authority", "synthetic_only", "ai")})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni", db
        anw1.ensure_analytics_wave1_schema(cur, force=True)
        ack = anw1.record_analytics_wave_ack(
            cur,
            company_code="WATHEFNI",
            environment="production",
            details={**honesty, "ack": "ACK_PRODUCTION_ANALYTICS_W1B=YES"},
            canary_tag=None,
        )
        conn.commit()
        cur.execute("SELECT to_regclass('public.analytics_wave_acks') AS reg")
        reg = dict(cur.fetchone())["reg"]
        assert reg == "analytics_wave_acks", reg
        print("ack_id", ack.get("ack_id"))
        print("ACK_PRODUCTION_ANALYTICS_W1B=YES")
print("MIGRATE_OK")
PY
