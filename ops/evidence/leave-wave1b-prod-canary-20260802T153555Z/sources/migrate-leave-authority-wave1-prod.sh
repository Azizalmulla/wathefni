#!/usr/bin/env bash
# Leave Wave 1B — production schema migrate (ACK required).
# Applies leave_authority_wave1 schema 1.0.0 only. Does NOT enable enforced=true.
set -euo pipefail

ORCH="${ORCH:-/opt/wathefni/orchestrator}"
cd "$ORCH"

: "${WATHEFNI_ENV:?}"
: "${ACK_PRODUCTION_LEAVE_W1B:?Set ACK_PRODUCTION_LEAVE_W1B=YES to migrate production}"
if [[ "$ACK_PRODUCTION_LEAVE_W1B" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_LEAVE_W1B must be YES"
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
import leave_authority_wave1 as leave_w1

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("schema_version", leave_w1.LEAVE_AUTHORITY_SCHEMA_VERSION)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        assert db == "wathefni", db
        leave_w1.ensure_leave_authority_wave1_schema(cur)
        leave_w1.seed_company_leave_authority_settings(cur, "WATHEFNI")
        # Hard-pin observe-only
        cur.execute(
            """
            UPDATE leave_authority_settings
            SET balances_enforced=false, legal_reviewed=false, updated_at=now()
            WHERE company_code='WATHEFNI'
            """
        )
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name='leave_requests' AND column_name='row_version'
            """
        )
        assert cur.fetchone(), "row_version missing"
        cur.execute("SELECT leave_type FROM leave_type_catalogue ORDER BY 1")
        cats = [dict(r)["leave_type"] for r in cur.fetchall()]
        assert set(cats) >= {"annual", "sick", "unpaid", "other"}, cats
        cur.execute(
            "SELECT balances_enforced, legal_reviewed FROM leave_authority_settings WHERE company_code='WATHEFNI'"
        )
        s = dict(cur.fetchone())
        assert s["balances_enforced"] is False and s["legal_reviewed"] is False
    conn.commit()
print("MIGRATE_OK leave_authority_wave1_prod")
PY
