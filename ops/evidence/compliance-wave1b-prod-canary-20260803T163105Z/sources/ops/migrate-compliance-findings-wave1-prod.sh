#!/usr/bin/env bash
# Compliance Wave 1-B — production ACK + additive schema (ACK required).
# Creates compliance_wave_acks only. No frozen-module schema changes.
# Document compliance only. No AI / government APIs / fines / legal claims.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${ACK_PRODUCTION_COMPLIANCE_W1B:?Set ACK_PRODUCTION_COMPLIANCE_W1B=YES to migrate production}"
if [[ "${ACK_PRODUCTION_COMPLIANCE_W1B}" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_COMPLIANCE_W1B must be YES"
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
import compliance_findings_wave1 as cfw1

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
honesty = cfw1.honesty_payload()
assert honesty.get("document_compliance_only") is True
assert honesty.get("government_verified") is False
assert honesty.get("government_apis") is False
assert honesty.get("filing") is False
assert honesty.get("fine_calculations") is False
assert honesty.get("legal_compliance_claims") is False
assert honesty.get("ai") is False
assert honesty.get("analytics_excludes_compliance") is True
assert honesty.get("alerts_delivery_owns_reminders") is True
print("wave1_version", cfw1.COMPLIANCE_WAVE1_VERSION)
print("contract", cfw1.COMPLIANCE_WAVE1_CONTRACT)
print("honesty_ok", {k: honesty[k] for k in (
    "document_compliance_only", "government_verified", "synthetic_only", "ai", "legal_compliance_claims"
)})

# Analytics freeze must still exclude Compliance metrics
import analytics_attention_wave1 as anw1
assert anw1.honesty_payload().get("compliance_metrics") is False

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        print("connected_db", db)
        assert db == "wathefni", db
        cfw1.ensure_compliance_wave1_schema(cur, force=True)
        ack = cfw1.record_compliance_wave_ack(
            cur,
            company_code="WATHEFNI",
            environment="production",
            details={**honesty, "ack": "ACK_PRODUCTION_COMPLIANCE_W1B=YES"},
            canary_tag=None,
        )
        conn.commit()
        cur.execute("SELECT to_regclass('public.compliance_wave_acks') AS reg")
        reg = dict(cur.fetchone())["reg"]
        assert reg == "compliance_wave_acks", reg
        print("ack_id", ack.get("ack_id"))
        print("ACK_PRODUCTION_COMPLIANCE_W1B=YES")
print("MIGRATE_OK")
PY
