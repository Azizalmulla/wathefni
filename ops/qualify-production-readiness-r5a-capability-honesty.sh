#!/usr/bin/env bash
# Production Readiness R5A — Capability Honesty qualification.
#
# Proves the R1 P0-1 honesty gate against local contracts and isolated staging:
#
#   1. dashboard vitest (Waves 1–3 / Wave 5 surfaces unchanged)
#   2. local R5A unit contracts
#   3. staging deploy of orchestrator sources
#   4. staging DB: preserve enabled rows, refuse customer enable
#   5. live deployed staging: reserved namespaces fail closed
#   6. Waves 1–6 authority + R2–R4 regressions
#
# Does not touch production customer data. Does not begin R5B surface delivery.
# FULL_PASS here does not authorise production rollout.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r5a-capability-honesty-$STAMP"
REMOTE_STAGE="/tmp/r5a-capability-honesty-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,dashboard}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  module_catalog.py
  capability_readiness.py
  unreleased_capability_http.py
  setup_console_wave4_policies.py
  setup_console_wave6_policies.py
  wave6_hcm_expansion_product_c8.py
  smoke-test-r5a-capability-honesty.py
  smoke-test-r5a-capability-honesty-db.py
  smoke-test-r4-truth-in-ui.py
  smoke-test-r4-truth-in-ui-db.py
  smoke-test-r3-data-safety.py
  smoke-test-r3-data-safety-db.py
  smoke-test-r2-security-db.py
  smoke-test-internal-auth.py
)

log "1/7 dashboard vitest (existing surfaces)"
cd "$DASH_SRC"
if [[ -x "$DASH_SRC/node_modules/.bin/vitest" ]]; then
  npx vitest run \
    src/lib/workspaceCapability.test.ts \
    src/lib/dashboardNavigation.test.ts \
    src/lib/moduleWorkspace.test.ts \
    src/pages/shared/dataState.test.tsx \
    2>&1 | tee "$LOCAL_EVID/dashboard/named.out"
  npx vitest run 2>&1 | tee "$LOCAL_EVID/dashboard/full.out"
else
  echo "vitest missing" | tee "$LOCAL_EVID/dashboard/named.out"
  exit 1
fi

log "2/7 local R5A unit contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-r5a-capability-honesty.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "3/7 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/capability_readiness.py'
test -f '$STG/unreleased_capability_http.py'
test -f '$STG/smoke-test-r5a-capability-honesty-db.py'
python3 -m py_compile '$STG/app.py' '$STG/capability_readiness.py' '$STG/unreleased_capability_http.py'
echo STAGING_COPY_OK
REMOTE

staging_py() {
  local script="$1" out="$2"
  "${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$out"
set -euo pipefail
STG=$STG
PROD=/opt/wathefni/orchestrator
PYBIN=\$PROD/.venv/bin/python
export PYTHONPATH="\$STG:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DELIVERY_MODE=dry_run
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" "$script"
echo STAGING_RC=\$?
REMOTE
}

log "4/7 staging database preserve + refuse enable"
staging_py smoke-test-r5a-capability-honesty-db.py "$LOCAL_EVID/tests/staging-db.out"

log "5/7 live deployed staging service"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
S=000
for i in $(seq 1 15); do
  sleep 8
  S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health)
  [ "$S" = "200" ] && break
done
echo "staging_health=$S"
[ "$S" = "200" ] || { echo "LIVE_SERVICE 0 passed, 1 failed"; exit 0; }

STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
export PYTHONPATH="$STG:$PROD"
export WATHEFNI_ENV=staging
export WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"$PROD/.venv/bin/python" - <<'PY'
import json, urllib.request, urllib.error, sys
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
import app
import capability_readiness as ready

P = F = 0
def ck(label, cond, detail=None):
    global P, F
    if cond:
        P += 1
        print(f"      PASS  {label}")
    else:
        F += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")

def fetch(path, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:8011" + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body

ck("live health imported", hasattr(app, "app"))
ck("live fail-closed registrar present", "register_unreleased_capability_failclosed" in open("/opt/wathefni/staging/orchestrator/app.py", encoding="utf-8", errors="ignore").read())
ck("live performance not customer enableable", ready.customer_enableable("performance") is False)
ck("live talent not customer enableable", ready.customer_enableable("talent") is False)
ck("live analytics still catalog enableable", ready.catalog_module_customer_enableable("analytics") is True)

for path, cap in (
    ("/dashboard/performance", "performance"),
    ("/dashboard/posthire/talent", "talent"),
    ("/dashboard/job-architecture", "job_architecture"),
    ("/dashboard/learning", "learning"),
    ("/dashboard/benefits", "benefits"),
    ("/dashboard/employee-relations", "employee_relations"),
    ("/dashboard/engagement", "engagement"),
    ("/dashboard/compensation-planning", "comp_planning"),
    ("/dashboard/workforce-planning", "workforce_planning"),
    ("/app/performance", "performance"),
):
    status, body = fetch(path)
    try:
        payload = json.loads(body)
    except Exception:
        payload = {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    ck(f"live {path} 404", status == 404, status)
    ck(
        f"live {path} not released",
        isinstance(detail, dict) and detail.get("error") == "capability_not_released" and detail.get("capability_key") == cap,
        detail,
    )

status, body = fetch("/dashboard/posthire/intelligence/bootstrap")
try:
    payload = json.loads(body)
except Exception:
    payload = {}
detail = payload.get("detail") if isinstance(payload, dict) else None
stolen = isinstance(detail, dict) and detail.get("error") == "capability_not_released"
ck("live Intelligence namespace not stolen", stolen is False, {"status": status, "detail": detail})
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "6/7 regressions (Waves 1–6 + R2 + R3 + R4 + internal-auth)"
REG_OK=YES
set +e
for t in smoke-test-wave6-product-acceptance smoke-test-job-architecture-c1 smoke-test-learning-development-c2 \
         smoke-test-benefits-administration-c3 smoke-test-employee-relations-c4 smoke-test-engagement-c5 \
         smoke-test-compensation-planning-c6 smoke-test-workforce-planning-c7 smoke-test-wave5-product-acceptance \
         smoke-test-wave4-product-acceptance smoke-test-wave3-product-acceptance smoke-test-wave2-product-acceptance \
         smoke-test-wave1-product-acceptance smoke-test-r2-security smoke-test-r3-data-safety smoke-test-r4-truth-in-ui \
         smoke-test-r5a-capability-honesty; do
  "$PY" "$ORCH_SRC/$t.py" >"$LOCAL_EVID/regression/$t.out" 2>&1
  echo "$t rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
done
"$PY" -m unittest test_interaction_authority_contracts >"$LOCAL_EVID/regression/interaction-authority-contracts.out" 2>&1
echo "interaction_authority_contracts rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
set -e
staging_py smoke-test-internal-auth.py "$LOCAL_EVID/regression/internal-auth-staging.out"
staging_py smoke-test-r2-security-db.py "$LOCAL_EVID/regression/r2-security-db.out"
staging_py smoke-test-r3-data-safety-db.py "$LOCAL_EVID/regression/r3-data-safety-db.out"
staging_py smoke-test-r4-truth-in-ui-db.py "$LOCAL_EVID/regression/r4-truth-in-ui-db.out"
for f in "$LOCAL_EVID"/regression/smoke-test-*.out; do
  grep -qE '^[[:space:]]*FAIL  |Traceback' "$f" && REG_OK=NO
  grep -qE '[0-9]+ passed' "$f" || REG_OK=NO
done
grep -q 'OK' "$LOCAL_EVID/regression/interaction-authority-contracts.out" || REG_OK=NO
grep -q 'ALL CHECKS PASSED' "$LOCAL_EVID/regression/internal-auth-staging.out" || REG_OK=NO
grep -q 'R2_SECURITY_FULL_PASS' "$LOCAL_EVID/regression/r2-security-db.out" || REG_OK=NO
grep -q 'R3_DATA_SAFETY_FULL_PASS' "$LOCAL_EVID/regression/r3-data-safety-db.out" || REG_OK=NO
grep -q 'R4_TRUTH_IN_UI_DB_PASS' "$LOCAL_EVID/regression/r4-truth-in-ui-db.out" || REG_OK=NO

log "7/7 verdict"
DASH_OK=NO
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out"; then DASH_OK=YES; fi
if grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/named.out"; then DASH_OK=NO; fi

UNIT_OK=NO
grep -q 'R5A_CAPABILITY_HONESTY_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" && UNIT_OK=YES

DB_OK=NO
grep -q 'R5A_CAPABILITY_HONESTY_DB_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES

DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES

VERDICT=FAIL
if [[ "$DASH_OK" == YES && "$UNIT_OK" == YES && "$DB_OK" == YES && "$LIVE_OK" == YES && "$REG_OK" == YES && "$DEPLOY_OK" == YES ]]; then
  VERDICT='PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Production Readiness R5A — Capability Honesty

- Stamp: $STAMP
- Dashboard vitest: $DASH_OK
- Local unit contracts: $UNIT_OK
- Staging deploy: $DEPLOY_OK
- Staging DB preserve + refuse enable: $DB_OK
- Live deployed staging service: $LIVE_OK
- Waves 1–6 + R2 + R3 + R4 regressions: $REG_OK
- Verdict: **$VERDICT**

Scope: R1 P0-1 Wave 4/6 capability honesty gate.
Does not touch production customer data. Does not begin R5B surface delivery.
FULL_PASS is not authorisation for production rollout.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
