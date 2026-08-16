#!/usr/bin/env bash
# Leave Wave 2 — policy/balance schema pack (local/staging only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
: "${WATHEFNI_ENV:?}"
if [[ "${WATHEFNI_ENV}" == "production" ]]; then
  echo "REFUSE: Wave 2 migrate is local/staging only"
  exit 2
fi
ACK_DB="${ACK_DB:-${WATHEFNI_EXPECTED_DATABASE_NAME:-}}"
: "${ACK_DB:?}"
if [[ "$ACK_DB" == "wathefni" ]]; then
  echo "REFUSE: production DB name"
  exit 2
fi
PYBIN="${ORCH_PYTHON:-python3}"
"$PYBIN" - <<'PY'
import os, sys
sys.path.insert(0, ".")
import app
import leave_policy_wave2 as w2
expected = os.environ.get("ACK_DB") or os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME")
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        db = dict(cur.fetchone())["db"]
        assert db == expected, (db, expected)
        assert db != "wathefni"
        w2.ensure_leave_policy_wave2_schema(cur)
        w2.seed_kuwait_private_policy_pack(cur)
        w2.bind_company_policy_pack(cur, "WATHEFNI")
        year = w2.kuwait_today_wave2().year
        w2.seed_fixed_kuwait_holidays(cur, "WATHEFNI", year=year)
        app.seed_leave_policy_presets()
        app.seed_company_leave_policies("WATHEFNI")
        # Refresh sick tiers on company policy if empty
        cur.execute(
            """
            UPDATE leave_policies SET tiers=%s::jsonb, updated_at=now()
            WHERE company_code='WATHEFNI' AND leave_type='sick'
              AND (tiers IS NULL OR tiers = '[]'::jsonb)
            """,
            (__import__("json").dumps(w2.KUWAIT_PRIVATE_PACK["policies"]["sick"]["tiers"]),),
        )
        cur.execute("SELECT balances_enforced FROM leave_authority_settings WHERE company_code='WATHEFNI'")
        # may not exist on fresh — ignore
        cur.execute("SELECT legal_reviewed, enforced, version FROM leave_policy_packs WHERE pack_code='kw_private_sector_v2' ORDER BY version DESC LIMIT 1")
        pack = dict(cur.fetchone())
        assert pack["legal_reviewed"] is False and pack["enforced"] is False
        assert pack["version"] == "2.1.0"
        cur.execute("SELECT COUNT(*) AS n FROM public_holidays WHERE company_code='WATHEFNI' AND year=%s", (year,))
        assert int(dict(cur.fetchone())["n"]) >= 3
    conn.commit()
print("MIGRATE_OK leave_policy_wave2", w2.LEAVE_POLICY_WAVE2_VERSION)
PY
