#!/usr/bin/env bash
# Setup Console Wave A-B — production ACK (no schema mutation).
# Asserts Launch Readiness honesty + WATHEFNI-only evaluate.
# Does NOT enable external tenants, Payroll money, Attendance ingest, Wave B, AI, or mobile apps.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_SETUP_WAVE_AB:?Set ACK_PRODUCTION_SETUP_WAVE_AB=YES to ACK production}"
if [[ "${ACK_PRODUCTION_SETUP_WAVE_AB}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_SETUP_WAVE_AB must be YES"
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
import setup_console_wave_a_launch_readiness as wave_a

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"

honesty = wave_a.honesty_payload()
assert honesty.get("operator_only") is True
assert honesty.get("wathefni_only") is True
assert honesty.get("external_tenants") is False
assert honesty.get("payroll_money") is False
assert honesty.get("attendance_ingest") is False
assert honesty.get("capture_ingest") == "off"
assert honesty.get("entitlements_cannot_bypass_gates") is True
assert honesty.get("ai") is False
assert honesty.get("setup_wave_b") is False
assert honesty.get("read_only_evaluate") is True
assert honesty.get("frozen_module_contracts_unchanged") is True
print("wave_a_version", wave_a.WAVE_A_VERSION)
print("contract", wave_a.WAVE_A_CONTRACT)
print("honesty_ok", {k: honesty[k] for k in (
    "operator_only", "wathefni_only", "payroll_money", "attendance_ingest",
    "capture_ingest", "setup_wave_b", "ai",
)})

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni", db
        ok = wave_a.evaluate_launch_readiness(cur, company_code="WATHEFNI")
        bad = wave_a.evaluate_launch_readiness(cur, company_code="EXTERNALCO")
        assert ok.get("ok") is True, ok
        assert bad.get("ok") is False and bad.get("error") == "wave_a_wathefni_only", bad
        assert ok.get("entitlements_cannot_bypass_gates") is True
        assert ok.get("payroll_money") is False
        assert ok.get("attendance_ingest") is False
        assert ok.get("external_tenants") is False
        assert len(ok.get("stages") or []) == 6
        print("overall_state", ok.get("overall_state"))
        print("blockers", len(ok.get("important_blockers") or []))
        # No durable rows written — residual always 0 for this ACK.
        print("ACK_PRODUCTION_SETUP_WAVE_AB=YES")
        print("residual_rows=0")
print("MIGRATE_OK")
PY
