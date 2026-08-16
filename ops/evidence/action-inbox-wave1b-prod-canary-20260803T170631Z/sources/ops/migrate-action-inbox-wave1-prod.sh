#!/usr/bin/env bash
# Action Inbox Wave 1-B — production ACK + additive schema (ACK required).
# Creates action_inbox_wave_acks only. No frozen-module schema changes.
# Read-only composition. No AI / Compliance Wave 2 / Analytics Wave 2 / Payroll money.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_ACTION_INBOX_W1B:?Set ACK_PRODUCTION_ACTION_INBOX_W1B=YES to migrate production}"
if [[ "${ACK_PRODUCTION_ACTION_INBOX_W1B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_ACTION_INBOX_W1B must be YES"
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
import action_inbox_wave1 as w1
import analytics_attention_wave1 as anw1
import compliance_findings_wave1 as cfw1

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
honesty = w1.honesty_payload()
assert honesty.get("read_only") is True
assert honesty.get("composes_only") is True
assert honesty.get("mutates_records") is False
assert honesty.get("ai") is False
assert honesty.get("hiring_reports_separate") is True
assert honesty.get("alerts_delivery_owns_notifications") is True
assert honesty.get("compliance_wave2") is False
assert honesty.get("analytics_wave2") is False
assert honesty.get("payroll_money") is False
assert honesty.get("attendance_ingest") is False
assert honesty.get("shifts_manager_expansion") is False
assert anw1.honesty_payload().get("compliance_metrics") is False
assert cfw1.honesty_payload().get("legal_compliance_claims") is False
print("wave1_version", w1.ACTION_INBOX_WAVE1_VERSION)
print("contract", w1.ACTION_INBOX_WAVE1_CONTRACT)
print("honesty_ok", {k: honesty[k] for k in (
    "read_only", "mutates_records", "synthetic_only", "ai", "hiring_reports_separate"
)})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni", db
        w1.ensure_action_inbox_wave1_schema(cur, force=True)
        ack = w1.record_action_inbox_wave_ack(
            cur,
            company_code="WATHEFNI",
            environment="production",
            details={**honesty, "ack": "ACK_PRODUCTION_ACTION_INBOX_W1B=YES"},
            canary_tag=None,
        )
        conn.commit()
        cur.execute("SELECT to_regclass('public.action_inbox_wave_acks') AS reg")
        reg = dict(cur.fetchone())["reg"]
        assert reg == "action_inbox_wave_acks", reg
        print("ack_id", ack.get("ack_id"))
        print("ACK_PRODUCTION_ACTION_INBOX_W1B=YES")
print("MIGRATE_OK")
PY
