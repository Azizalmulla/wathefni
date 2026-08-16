#!/usr/bin/env bash
# Platform Assistant Wave 2-B — production ACK (audit + honesty).
# Does NOT enable mutations, WhatsApp widening, CK, money, ingest, or Wave 3.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_PLATFORM_ASSISTANT_W2B:?Set ACK_PRODUCTION_PLATFORM_ASSISTANT_W2B=YES to ACK production}"
if [[ "${ACK_PRODUCTION_PLATFORM_ASSISTANT_W2B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_PLATFORM_ASSISTANT_W2B must be YES"
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
import platform_assistant_wave2_safe_ops_reads as wave2

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"

# Force wave flags for ACK asserts (drop-in applies after restart).
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", "1")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE2", "1")
os.environ.setdefault("WATHEFNI_PLATFORM_ASSISTANT_WAVE2_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_ASSISTANT_MUTATIONS", "0")
os.environ.setdefault("WATHEFNI_ASSISTANT_KILL", "0")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")

honesty = wave2.honesty_payload()
assert honesty.get("wathefni_only") is True
assert honesty.get("hr_dashboard_only") is True
assert honesty.get("mutates_records") is False or honesty.get("mutations") is False
assert honesty.get("payroll_money") is False or honesty.get("payroll") is False
assert honesty.get("attendance_ingest") is False
assert honesty.get("capture_ingest") == "off"
assert honesty.get("attendance_records_basis") == "existing_records_only"
assert honesty.get("whatsapp_widening") is False
assert honesty.get("candidate_knowledge_wired") is False
assert honesty.get("payroll") is False
assert honesty.get("shifts") is False
assert honesty.get("onboarding_assistant_surface") is False
assert spine.wave1_enabled_for_company("WATHEFNI")
assert wave2.wave2_enabled_for_company("WATHEFNI")
assert not wave2.wave2_enabled_for_company("ACME")
assert spine.assistant_mutations_allowed() is False
assert spine.assistant_kill_engaged() is False
print("wave1_version", spine.WAVE1_VERSION)
print("wave2_version", wave2.WAVE2_VERSION)
print("contract", wave2.WAVE2_CONTRACT)
print("honesty_ok", {k: honesty.get(k) for k in (
    "wathefni_only", "hr_dashboard_only", "mutations", "payroll", "shifts",
    "attendance_ingest", "capture_ingest", "attendance_records_basis",
    "whatsapp_widening", "wave2_scope",
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
            event_type="assistant.wave2b_production_ack",
            channel="web_dashboard",
            detail={**honesty, "ack": "ACK_PRODUCTION_PLATFORM_ASSISTANT_W2B=YES"},
            environment="production",
        )
        conn.commit()
        cur.execute("SELECT to_regclass('public.assistant_spine_events') AS reg")
        reg = dict(cur.fetchone())["reg"]
        assert reg == "assistant_spine_events", reg
        print("ack_event_id", ack.get("event_id"))
        print("ACK_PRODUCTION_PLATFORM_ASSISTANT_W2B=YES")
        print("residual_policy=canary_tagged_cleaned_ack_retained")
print("MIGRATE_OK")
PY
