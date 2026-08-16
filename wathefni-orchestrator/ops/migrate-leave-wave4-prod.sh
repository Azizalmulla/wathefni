#!/usr/bin/env bash
# Leave Wave 4 — production schema migrate (ACK required).
# Dual-control table + honesty pins. Does NOT set enforced=true.
set -euo pipefail

ORCH="${ORCH:-/opt/wathefni/orchestrator}"
cd "$ORCH"

: "${WATHEFNI_ENV:?}"
: "${ACK_PRODUCTION_LEAVE_W4:?Set ACK_PRODUCTION_LEAVE_W4=YES to migrate production}"
if [[ "$ACK_PRODUCTION_LEAVE_W4" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_LEAVE_W4 must be YES"
  exit 2
fi
if [[ "$WATHEFNI_ENV" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

PYBIN="${ORCH_PYTHON:-.venv/bin/python}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import leave_authority_wave1 as w1
import leave_policy_wave2 as w2
import leave_workflow_wave3 as w3
import leave_wave4_controlled as w4

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
assert w4.LEAVE_WAVE4_VERSION == "4.0.0"

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        assert db == "wathefni", db
        w1.ensure_leave_authority_wave1_schema(cur)
        w2.ensure_leave_policy_wave2_schema(cur)
        w3.ensure_leave_workflow_wave3_schema(cur)
        w4.ensure_leave_wave4_schema(cur)
        cur.execute(
            """
            UPDATE leave_authority_settings
            SET balances_enforced=false, legal_reviewed=false, updated_at=now()
            WHERE company_code='WATHEFNI'
            """
        )
        cur.execute(
            """
            UPDATE leave_policies
            SET enforced=false, legal_reviewed=false, updated_at=now()
            WHERE company_code='WATHEFNI'
            """
        )
        cur.execute("SELECT to_regclass('public.leave_dual_control_actions') AS t")
        assert dict(cur.fetchone())["t"] == "leave_dual_control_actions"
    conn.commit()
print("MIGRATE_OK leave_wave4_prod", w4.LEAVE_WAVE4_VERSION)
print("enforced=false legal_reviewed=false")
PY
