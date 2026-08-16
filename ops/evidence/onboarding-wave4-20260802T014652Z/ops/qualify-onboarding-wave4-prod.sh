#!/usr/bin/env bash
# Onboarding Wave 4 — production qualification.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID="/opt/wathefni/production-evidence/onboarding-wave4/${STAMP}"
BEFORE_JSON="${REMOTE_EVID}/preflight/fingerprint-before.json"
mkdir -p "$REMOTE_EVID"/{verify,tests,canary,flags,ux}

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

echo '=== wave4 HR mutate canary ===' | tee "$REMOTE_EVID/tests/wave4-canary.txt"
export WAVE4_CANARY_OUT="$REMOTE_EVID/canary"
$PY canary-prod-onboarding-wave4.py 2>&1 | tee -a "$REMOTE_EVID/tests/wave4-canary.txt"

echo '=== fingerprint reconcile + UX payload ==='
$PY - <<PY | tee "$REMOTE_EVID/verify/prod-qualification.json"
import json, hashlib, inspect, app
from pathlib import Path
KEYS = [
  "WATHEFNI-96550252254",
  "WATHEFNI-96566363363",
  "WATHEFNI-96597727743",
  "WATHEFNI-96599411617",
]
before = json.loads(Path("$BEFORE_JSON").read_text())
before_fp = before.get("fingerprint")
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT oi.employee_key, oi.item_id, oi.required, oi.status, oi.value, oi.reminder_count
            FROM onboarding_items oi
            JOIN employees e ON e.employee_key=oi.employee_key
            WHERE e.company_code='WATHEFNI' AND oi.employee_key = ANY(%s)
            ORDER BY oi.employee_key, oi.item_id
            """,
            (KEYS,),
        )
        items = [dict(r) for r in cur.fetchall() or []]
def fp(r):
  v=r.get("value"); vs="" if v is None else str(v)
  req="True" if r.get("required") is True else ("False" if r.get("required") is False else str(r.get("required")))
  return f"{r['employee_key']}|{r['item_id']}|{req}|{r['status']}|{hashlib.md5(vs.encode()).hexdigest()}|{int(r.get('reminder_count') or 0)}"
after_fp = sorted(fp(r) for r in items)
# UX payload sample (Talal)
talal = app.find_employee_by_key(KEYS[0], company_code="WATHEFNI")
summary = app.employee_onboarding_summary(talal, company_code="WATHEFNI")
enrich = app.onboarding_queue_enrichment("WATHEFNI", KEYS)
Path("$REMOTE_EVID/ux/queue-enrichment.json").write_text(json.dumps(enrich, indent=2, default=str)+"\n")
Path("$REMOTE_EVID/ux/talal-summary.json").write_text(json.dumps({
  "planned_start_date": summary.get("planned_start_date"),
  "overdue_count": summary.get("overdue_count"),
  "next_item_label": summary.get("next_item_label"),
  "next_owner_group": summary.get("next_owner_group"),
  "pending_count": summary.get("pending_count"),
  "bank_collection": summary.get("bank_collection"),
  "owner_groups": sorted({i.get("owner_group") for i in summary.get("items") or []}),
  "hr_mutate_company": app.onboarding_hr_mutate_enabled_for_company("WATHEFNI"),
}, indent=2, default=str)+"\n")
out = {
  "seed_enabled": app.onboarding_seed_enabled(),
  "hr_mutate_enabled": app.onboarding_hr_mutate_enabled(),
  "hr_mutate_companies": sorted(app.onboarding_hr_mutate_companies()),
  "synthetic_canary": app.onboarding_synthetic_canary_enabled(),
  "item_count": len(items),
  "checklist_unchanged": before_fp == after_fp,
  "bank_forbidden": app.validate_onboarding_item_receipt("bank_details", "KW81IBAN", None) == (False, "bank_via_ess_required"),
  "detail_has_manager_gate": "context_manager_allows_employee" in inspect.getsource(app.dashboard_posthire_onboarding_detail),
  "list_uses_scope_where": "_employee_scope_where" in inspect.getsource(app.list_onboarding_page),
  "cancel_registered": "cancel_onboarding" in open("action_registry.py").read(),
  "reschedule_registered": "reschedule_onboarding" in open("action_registry.py").read(),
}
assert out["seed_enabled"] is False
assert out["hr_mutate_enabled"] is True
assert out["hr_mutate_companies"] == ["WATHEFNI"]
assert out["checklist_unchanged"] is True
assert out["bank_forbidden"] is True
print(json.dumps(out, indent=2))
PY

echo "QUALIFY_OK"
