#!/usr/bin/env bash
# Deadlock Remediation Wave 1-BR — deploy-time schema apply (serialized).
# Applies core + inbound/migration schemas under advisory lock.
# Runtime API/workers must NOT set WATHEFNI_SCHEMA_APPLY.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_NAME="${WATHEFNI_ENV:?WATHEFNI_ENV required}"
if [[ "$ENV_NAME" == "staging" ]]; then
  : "${ACK_STAGING_SCHEMA_WAVE1BR:?Set ACK_STAGING_SCHEMA_WAVE1BR=YES}"
  [[ "$ACK_STAGING_SCHEMA_WAVE1BR" == "YES" ]] || { echo "REFUSE ACK"; exit 2; }
elif [[ "$ENV_NAME" == "production" ]]; then
  : "${ACK_PRODUCTION_SCHEMA_WAVE1BR:?Set ACK_PRODUCTION_SCHEMA_WAVE1BR=YES}"
  [[ "$ACK_PRODUCTION_SCHEMA_WAVE1BR" == "YES" ]] || { echo "REFUSE ACK"; exit 2; }
else
  echo "REFUSE: WATHEFNI_ENV must be staging or production"
  exit 2
fi

export WATHEFNI_SCHEMA_APPLY=1
PYBIN="${ORCH_PYTHON:-python3}"

"$PYBIN" - <<'PY'
import os
import sys

sys.path.insert(0, ".")
import app
import schema_contract as sc
import inbound_cv_intake as intake
import inbound_cv_processing as processing
import durable_email_ingress as durable
import migration_wave1_cv_foundation as mig

assert sc.schema_apply_allowed(), "WATHEFNI_SCHEMA_APPLY must be on for migrate"
print("contract", sc.SCHEMA_CONTRACT_VERSION)
print("lock_id", sc.DEPLOY_ADVISORY_LOCK_ID)

# Wave 1-BR migrator applies the deadlock-hot-path schemas under one advisory lock.
# Full app mega-DDL remains available via app.ensure_schema only when explicitly
# invoked with APPLY=1; staging/prod already have core tables provisioned.

def _bundle(cur):
    sc.ensure_ledger_table(cur)
    durable.apply_schema(cur)
    intake.apply_schema(cur)
    processing.apply_schema(cur)
    mig.apply_schema(cur)
    # Prove hr_turns + core relations exist (created by prior deploys / app schema).
    sc.require_core_runtime_schema(cur)
    sc.record_apply(cur, module="wave1br.bundle")

with app.db_connect() as conn:
    with conn.cursor() as cur:
        sc.with_deploy_advisory_lock(cur, _bundle)
    conn.commit()

# Fail closed validation with apply disabled in-process check path
os.environ.pop("WATHEFNI_SCHEMA_APPLY", None)
sc.reset_counters()
app._SCHEMA_READY = False
# Runtime path: validate only (no DDL)
app.ensure_schema(force=True)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        intake.require_schema(cur)
        processing.require_schema(cur)
        durable.require_schema(cur)
        mig.require_schema(cur)
    conn.commit()
print("post_apply_validate_ok", sc.counters())
assert sc.counters()["apply_calls"] == 0
print("MIGRATE_SCHEMA_WAVE1BR_OK")
PY
