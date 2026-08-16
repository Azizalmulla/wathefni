#!/usr/bin/env bash
# Leave Wave 2C — production schema migrate for policy pack (ACK required).
# Seeds kw_private_sector_v2@2.1.0. Does NOT set enforced=true or legal_reviewed=true.
set -euo pipefail

ORCH="${ORCH:-/opt/wathefni/orchestrator}"
cd "$ORCH"

: "${WATHEFNI_ENV:?}"
: "${ACK_PRODUCTION_LEAVE_W2C:?Set ACK_PRODUCTION_LEAVE_W2C=YES to migrate production}"
if [[ "$ACK_PRODUCTION_LEAVE_W2C" != "YES" ]]; then
  echo "REFUSE: ACK_PRODUCTION_LEAVE_W2C must be YES"
  exit 2
fi
if [[ "$WATHEFNI_ENV" != "production" ]]; then
  echo "REFUSE: WATHEFNI_ENV must be production for this script"
  exit 2
fi

PYBIN="${ORCH_PYTHON:-.venv/bin/python}"
"$PYBIN" - <<'PY'
import json, os, sys
sys.path.insert(0, ".")
import app
import leave_policy_wave2 as w2

assert os.environ.get("WATHEFNI_ENV") == "production"
assert (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni"
print("wave2_version", w2.LEAVE_POLICY_WAVE2_VERSION)
print("pack_version", w2.KUWAIT_PRIVATE_PACK["version"])
assert w2.LEAVE_POLICY_WAVE2_VERSION == "2.1.0"
assert w2.KUWAIT_PRIVATE_PACK["version"] == "2.1.0"
assert w2.KUWAIT_PRIVATE_PACK["enforced"] is False
assert w2.KUWAIT_PRIVATE_PACK["legal_reviewed"] is False
assert w2.KUWAIT_PRIVATE_PACK["policies"]["annual"]["eligibility_months"] == 6
assert w2.carryover_enabled(w2.KUWAIT_PRIVATE_PACK) is False

year = w2.kuwait_today_wave2().year
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        assert db == "wathefni", db
        w2.ensure_leave_policy_wave2_schema(cur)
        w2.seed_kuwait_private_policy_pack(cur)
        w2.bind_company_policy_pack(cur, "WATHEFNI", pack_version="2.1.0")
        w2.seed_fixed_kuwait_holidays(cur, "WATHEFNI", year=year)
        # Refresh company policy seeds without flipping enforced
        app.seed_leave_policy_presets()
        app.seed_company_leave_policies("WATHEFNI")
        cur.execute(
            """
            UPDATE leave_policies
            SET eligibility_months=6,
                days_per_year=30,
                weekend_days=ARRAY['fri','sat'],
                exclude_public_holidays=true,
                enforced=false,
                legal_reviewed=false,
                updated_at=now()
            WHERE company_code='WATHEFNI' AND leave_type='annual'
            """
        )
        cur.execute(
            """
            UPDATE leave_policies
            SET tiers=%s::jsonb, enforced=false, legal_reviewed=false, updated_at=now()
            WHERE company_code='WATHEFNI' AND leave_type='sick'
            """,
            (json.dumps(w2.KUWAIT_PRIVATE_PACK["policies"]["sick"]["tiers"]),),
        )
        cur.execute(
            """
            SELECT pack_code, version, legal_reviewed, enforced, carryover_enabled
            FROM leave_policy_packs
            WHERE pack_code='kw_private_sector_v2' AND version='2.1.0'
            """
        )
        pack = dict(cur.fetchone())
        assert pack["legal_reviewed"] is False and pack["enforced"] is False
        assert pack["carryover_enabled"] is False
        cur.execute(
            "SELECT pack_version FROM leave_company_policy_bindings WHERE company_code='WATHEFNI'"
        )
        bind = dict(cur.fetchone())
        assert bind["pack_version"] == "2.1.0"
        cur.execute(
            """
            SELECT status FROM leave_holiday_year_versions
            WHERE calendar_code='kw_public_v2' AND year=%s
            ORDER BY version DESC LIMIT 1
            """,
            (year,),
        )
        hv = dict(cur.fetchone())
        assert hv["status"] == "pending_review", hv
        cur.execute(
            "SELECT COUNT(*) AS n FROM public_holidays WHERE company_code='WATHEFNI' AND year=%s AND review_status='seeded_fixed'",
            (year,),
        )
        assert int(dict(cur.fetchone())["n"]) >= 3
        # Pin authority honesty if table exists
        cur.execute(
            """
            UPDATE leave_authority_settings
            SET balances_enforced=false, legal_reviewed=false, updated_at=now()
            WHERE company_code='WATHEFNI'
            """
        )
    conn.commit()
print("MIGRATE_OK leave_policy_wave2c_prod", w2.LEAVE_POLICY_WAVE2_VERSION)
PY
