#!/usr/bin/env bash
# Leave Wave 3B — production schema migrate for workflow Wave 3 (ACK required).
# Does NOT set enforced=true or legal_reviewed=true. Does NOT mutate real balances.
set -euo pipefail

ORCH="${ORCH:-/opt/wathefni/orchestrator}"
cd "$ORCH"

: "${WATHEFNI_ENV:?}"
: "${ACK_PRODUCTION_LEAVE_W3B:?Set ACK_PRODUCTION_LEAVE_W3B=YES to migrate production}"
if [[ "$ACK_PRODUCTION_LEAVE_W3B" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_LEAVE_W3B must be YES"
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

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
assert w3.LEAVE_WORKFLOW_WAVE3_VERSION == "3.0.0"
assert "needs_info" in w1.LEAVE_PRIMARY_STATUSES
assert "withdrawn" in w1.LEAVE_PRIMARY_STATUSES

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        assert db == "wathefni", db
        w1.ensure_leave_authority_wave1_schema(cur)
        w2.ensure_leave_policy_wave2_schema(cur)
        w3.ensure_leave_workflow_wave3_schema(cur)
        # Honesty pins
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
        # Confirm wave3 columns exist
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='leave_requests'
              AND column_name IN ('duration_unit','chargeable_days','chargeable_hours','payroll_handoff')
            ORDER BY 1
            """
        )
        cols = {dict(r)["column_name"] for r in cur.fetchall()}
        assert cols >= {"duration_unit", "chargeable_days", "chargeable_hours", "payroll_handoff"}, cols
        cur.execute("SELECT to_regclass('public.leave_request_attachments') AS t")
        assert dict(cur.fetchone())["t"] == "leave_request_attachments"
        cur.execute("SELECT to_regclass('public.leave_payroll_handoff_events') AS t")
        assert dict(cur.fetchone())["t"] == "leave_payroll_handoff_events"
    conn.commit()
print("MIGRATE_OK leave_workflow_wave3b_prod", w3.LEAVE_WORKFLOW_WAVE3_VERSION)
print("enforced=false legal_reviewed=false")
PY
