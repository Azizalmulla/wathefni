#!/usr/bin/env bash
# Platform Assistant Wave 1-B — production ACK (audit schema + honesty).
# Does NOT enable mutations, WhatsApp widening, CK, money, or ingest.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PLATFORM_ASSISTANT_W1B:?Set ACK_PRODUCTION_PLATFORM_ASSISTANT_W1B=YES to ACK production}"
if [[ "${ACK_PRODUCTION_PLATFORM_ASSISTANT_W1B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PLATFORM_ASSISTANT_W1B must be YES"
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

PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os
import sys

sys.path.insert(0, ".")
import app
import platform_assistant_spine_wave1 as spine

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"

# Force wave1 flags for ACK asserts (drop-in applies after restart).
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
os.environ.setdefault("WATHEFNI_ASSISTANT_KILL", "0")

honesty = spine.honesty_payload()
assert honesty.get("wathefni_only") is True
assert honesty.get("hr_dashboard_only") is True
assert honesty.get("mutates_records") is False
assert honesty.get("payroll_money") is False
assert honesty.get("attendance_ingest") is False
assert honesty.get("whatsapp_widening") is False
assert honesty.get("candidate_knowledge_wired") is False
assert honesty.get("default_posthire_entry") == "action_inbox"
assert spine.wave1_enabled_for_company("WATHEFNI")
assert not spine.wave1_enabled_for_company("ACME")
assert spine.assistant_mutations_allowed() is False
assert spine.assistant_kill_engaged() is False
print("wave1_version", spine.WAVE1_VERSION)
print("contract", spine.WAVE1_CONTRACT)
print("honesty_ok", {k: honesty[k] for k in (
    "wathefni_only", "hr_dashboard_only", "mutates_records", "payroll_money",
    "attendance_ingest", "whatsapp_widening", "default_posthire_entry",
)})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni", db
        spine.ensure_assistant_spine_audit_schema(cur, force=True)
        ack = spine.record_assistant_event(
            cur,
            company_code="WATHEFNI",
            event_type="assistant.wave1b_production_ack",
            channel="web_dashboard",
            detail={**honesty, "ack": "ACK_PRODUCTION_PLATFORM_ASSISTANT_W1B=YES"},
            environment="production",
        )
        conn.commit()
        cur.execute("SELECT to_regclass('public.assistant_spine_events') AS reg")
        reg = dict(cur.fetchone())["reg"]
        assert reg == "assistant_spine_events", reg
        print("ack_event_id", ack.get("event_id"))
        print("ACK_PRODUCTION_PLATFORM_ASSISTANT_W1B=YES")
        # Residual: only durable ACK retained; canary tags cleaned separately.
        print("residual_policy=canary_tagged_cleaned_ack_retained")
print("MIGRATE_OK")
PY
