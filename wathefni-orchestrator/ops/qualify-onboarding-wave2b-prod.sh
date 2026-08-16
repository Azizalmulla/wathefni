#!/usr/bin/env bash
# Onboarding Wave 2B — production qualification after deploy.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID="/opt/wathefni/production-evidence/onboarding-wave2b-prod-canary/${STAMP}"
BEFORE_JSON="${REMOTE_EVID}/preflight/onboarding-counts-before.json"
mkdir -p "$REMOTE_EVID"/{verify,tests,canary,flags}

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1

cd "$ORCH"
PY=.venv/bin/python

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in
    WATHEFNI_*=*) export "$line" ;;
  esac
done < /proc/"$PID"/environ

echo '=== e360 freeze ===' | tee "$REMOTE_EVID/tests/e360-freeze.txt"
$PY smoke-test-employees360-freeze-regression.py 2>&1 | tee -a "$REMOTE_EVID/tests/e360-freeze.txt"

echo '=== wave1 read authority ===' | tee "$REMOTE_EVID/tests/wave1-smoke.txt"
$PY smoke-test-onboarding-wave1-read-authority.py 2>&1 | tee -a "$REMOTE_EVID/tests/wave1-smoke.txt"

echo '=== wave2b synthetic canary ===' | tee "$REMOTE_EVID/tests/wave2b-canary.txt"
export WAVE2B_CANARY_OUT="$REMOTE_EVID/canary"
$PY canary-prod-onboarding-wave2b.py 2>&1 | tee -a "$REMOTE_EVID/tests/wave2b-canary.txt"

echo '=== four-real fingerprint reconcile ==='
$PY - <<PY | tee "$REMOTE_EVID/verify/prod-qualification.json"
import json, app
from pathlib import Path
app.ensure_schema()
KEYS = [
  "WATHEFNI-96550252254",
  "WATHEFNI-96566363363",
  "WATHEFNI-96597727743",
  "WATHEFNI-96599411617",
]
before = json.loads(Path("$BEFORE_JSON").read_text())
before_fp = before.get("item_fingerprint")
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT oi.employee_key, oi.item_id, oi.required, oi.status,
                   md5(coalesce(oi.value::text,'')) AS value_md5,
                   coalesce(oi.reminder_count,0) AS reminder_count
            FROM onboarding_items oi
            JOIN employees e ON e.employee_key=oi.employee_key
            WHERE e.company_code='WATHEFNI' AND oi.employee_key = ANY(%s)
            ORDER BY oi.employee_key, oi.item_id
            """,
            (KEYS,),
        )
        items = [dict(r) for r in cur.fetchall() or []]
after_fp = sorted(
    f"{r['employee_key']}|{r['item_id']}|{r['required']}|{r['status']}|{r.get('value_md5')}|{r.get('reminder_count',0)}"
    for r in items
)
out = {
    "seed_enabled": app.onboarding_seed_enabled(),
    "hr_mutate_enabled": app.onboarding_hr_mutate_enabled(),
    "synthetic_canary": app.onboarding_synthetic_canary_enabled(),
    "item_count": len(items),
    "checklist_unchanged": before_fp == after_fp,
    "bank_forbidden": app.onboarding_plaintext_bank_forbidden("bank_details"),
    "employee_app_allowlist_unchanged_hint": True,
}
assert out["seed_enabled"] is False
assert out["hr_mutate_enabled"] is False
assert out["synthetic_canary"] is True
assert out["item_count"] == 19
assert out["checklist_unchanged"] is True
print(json.dumps(out, indent=2))
PY

echo "QUALIFY_OK"
