#!/usr/bin/env bash
# Migrate Leave Wave 3 schema (staging/local). Does NOT enable enforcement.
set -euo pipefail
ORCH="${ORCH:-$(cd "$(dirname "$0")/.." && pwd)}"
PY="${ORCH_PYTHON:-python3}"
cd "$ORCH"
"$PY" - <<'PY'
import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("WATHEFNI_LEAVE_WORKFLOW_WAVE3", "on")
import app
import leave_workflow_wave3 as w3
import leave_authority_wave1 as w1
import leave_policy_wave2 as w2
with app.db_connect() as conn:
    with conn.cursor() as cur:
        w1.ensure_leave_authority_wave1_schema(cur)
        w2.ensure_leave_policy_wave2_schema(cur)
        w3.ensure_leave_workflow_wave3_schema(cur)
    conn.commit()
print("LEAVE_WAVE3_SCHEMA_OK", w3.LEAVE_WORKFLOW_WAVE3_VERSION)
print("enforced=false legal_reviewed=false")
PY
