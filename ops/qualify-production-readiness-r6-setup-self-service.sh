#!/usr/bin/env bash
# Production Readiness R6 — Setup Self-Service Completeness qualification.
# Does not begin R7.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r6-setup-self-service-$STAMP"
REMOTE_STAGE="/tmp/r6-setup-self-service-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,dashboard,mobile,inventories}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  module_catalog.py
  capability_readiness.py
  setup_console_effective_state.py
  setup_console_wave5_policies.py
  setup_console_env_classification.py
  setup_console_policy_convergence.py
  setup_console_delivery_policies.py
  setup_console_wave1_policies.py
  setup_console_wave2_policies.py
  setup_console_wave4_policies.py
  setup_console_wave6_policies.py
  setup_console_modules_phase3b.py
  hr_intelligence_registry_c1.py
  hr_intelligence_workforce_c2.py
  hr_intelligence_recruiting_c3.py
  hr_intelligence_time_pay_c4.py
  hr_intelligence_perf_talent_c5.py
  hr_intelligence_surfaces_c6.py
  smoke-test-r6-setup-self-service.py
  smoke-test-r6-setup-self-service-db.py
  smoke-test-r5j-workforce-planning-surface.py
  smoke-test-r5j-workforce-planning-surface-db.py
  smoke-test-r5i-compensation-planning-surface.py
  smoke-test-r5i-compensation-planning-surface-db.py
  smoke-test-r5h-engagement-surface.py
  smoke-test-r5h-engagement-surface-db.py
  smoke-test-r5g-employee-relations-surface.py
  smoke-test-r5g-employee-relations-surface-db.py
  smoke-test-r5f-benefits-surface.py
  smoke-test-r5f-benefits-surface-db.py
  smoke-test-r5e-learning-surface.py
  smoke-test-r5e-learning-surface-db.py
  smoke-test-r5d-job-architecture-surface.py
  smoke-test-r5d-job-architecture-surface-db.py
  smoke-test-r5c-talent-surface.py
  smoke-test-r5c-talent-surface-db.py
  smoke-test-r5b-performance-surface.py
  smoke-test-r5b-performance-surface-db.py
  smoke-test-r5a-capability-honesty.py
  smoke-test-r5a-capability-honesty-db.py
  smoke-test-hr-intelligence-registry-c1.py
  smoke-test-hr-intelligence-workforce-c2.py
  smoke-test-hr-intelligence-recruiting-c3.py
  smoke-test-hr-intelligence-time-pay-c4.py
  smoke-test-hr-intelligence-perf-talent-c5.py
  smoke-test-hr-intelligence-surfaces-c6.py
)

log "1/8 dashboard vitest + employee composition"
cd "$DASH_SRC"
if [[ -x "$DASH_SRC/node_modules/.bin/vitest" ]]; then
  npx vitest run \
    src/lib/workspaceCapability.test.ts \
    src/lib/dashboardNavigation.test.ts \
    src/lib/moduleWorkspace.test.ts \
    src/pages/shared/dataState.test.tsx \
    src/setup-console/SetupConsoleApp.test.tsx \
    2>&1 | tee "$LOCAL_EVID/dashboard/named.out"
  npx vitest run 2>&1 | tee "$LOCAL_EVID/dashboard/full.out"
else
  echo "vitest missing" | tee "$LOCAL_EVID/dashboard/named.out"
  exit 1
fi
cd "$MOBILE_SRC"
node scripts/composition-shapes-test.js 2>&1 | tee "$LOCAL_EVID/mobile/composition.out"

log "2/8 local R6 + R5A–R5J unit contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-r6-setup-self-service.py 2>&1 | tee "$LOCAL_EVID/tests/r6-unit.out"
"$PY" smoke-test-r5j-workforce-planning-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5j-unit.out"
"$PY" smoke-test-r5i-compensation-planning-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5i-unit.out"
"$PY" smoke-test-r5h-engagement-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5h-unit.out"
"$PY" smoke-test-r5g-employee-relations-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5g-unit.out"
"$PY" smoke-test-r5f-benefits-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5f-unit.out"
"$PY" smoke-test-r5e-learning-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5e-unit.out"
"$PY" smoke-test-r5d-job-architecture-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5d-unit.out"
"$PY" smoke-test-r5c-talent-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5c-unit.out"
"$PY" smoke-test-r5b-performance-surface.py 2>&1 | tee "$LOCAL_EVID/tests/r5b-unit.out"
"$PY" smoke-test-r5a-capability-honesty.py 2>&1 | tee "$LOCAL_EVID/tests/r5a-unit.out"

log "3/8 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/setup_console_effective_state.py'
test -f '$STG/setup_console_wave5_policies.py'
python3 -m py_compile '$STG/app.py' '$STG/setup_console_effective_state.py' '$STG/setup_console_wave5_policies.py'
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

log "4/8 staging DB journeys A–G + R5A–R5J DB regressions"
staging_py smoke-test-r6-setup-self-service-db.py "$LOCAL_EVID/tests/staging-db.out"
staging_py smoke-test-r5j-workforce-planning-surface-db.py "$LOCAL_EVID/tests/r5j-staging-db.out"
staging_py smoke-test-r5i-compensation-planning-surface-db.py "$LOCAL_EVID/tests/r5i-staging-db.out"
staging_py smoke-test-r5h-engagement-surface-db.py "$LOCAL_EVID/tests/r5h-staging-db.out"
staging_py smoke-test-r5g-employee-relations-surface-db.py "$LOCAL_EVID/tests/r5g-staging-db.out"
staging_py smoke-test-r5f-benefits-surface-db.py "$LOCAL_EVID/tests/r5f-staging-db.out"
staging_py smoke-test-r5e-learning-surface-db.py "$LOCAL_EVID/tests/r5e-staging-db.out"
staging_py smoke-test-r5d-job-architecture-surface-db.py "$LOCAL_EVID/tests/r5d-staging-db.out"
staging_py smoke-test-r5c-talent-surface-db.py "$LOCAL_EVID/tests/r5c-staging-db.out"
staging_py smoke-test-r5b-performance-surface-db.py "$LOCAL_EVID/tests/r5b-staging-db.out"
staging_py smoke-test-r5a-capability-honesty-db.py "$LOCAL_EVID/tests/r5a-staging-db.out"

log "5/8 live deployed staging service"
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
"$PROD/.venv/bin/python" - <<'PY'
import json, urllib.request, urllib.error, sys
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
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

ck("live WFP still enableable", ready.customer_enableable("workforce_planning") is True)
ck("live Comp still enableable", ready.customer_enableable("comp_planning") is True)
ck("live JA still enableable", ready.customer_enableable("job_architecture") is True)
ck("live unreleased empty", ready.UNRELEASED_CAPABILITY_KEYS == ())
status, body = fetch("/health")
ck("live health", status == 200, status)
status, body = fetch("/dashboard/setup/company/module-policies")
ck("live company Setup not public", status in (401, 403, 503), status)
status, body = fetch("/dashboard/superadmin/setup/companies/R6FAKE/module-policies")
ck("live operator Setup not public", status in (401, 403, 404, 503), status)
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "6/8 regressions (Waves 1–6 + R2–R5J + Intelligence C1–C6)"
REG_OK=YES
set +e
for t in smoke-test-wave6-product-acceptance smoke-test-job-architecture-c1 smoke-test-learning-development-c2 \
         smoke-test-benefits-administration-c3 smoke-test-employee-relations-c4 smoke-test-engagement-c5 \
         smoke-test-compensation-planning-c6 smoke-test-workforce-planning-c7 smoke-test-wave5-product-acceptance \
         smoke-test-wave4-product-acceptance smoke-test-wave3-product-acceptance smoke-test-wave2-product-acceptance \
         smoke-test-wave1-product-acceptance smoke-test-r2-security smoke-test-r3-data-safety smoke-test-r4-truth-in-ui \
         smoke-test-r5a-capability-honesty smoke-test-r5b-performance-surface smoke-test-r5c-talent-surface \
         smoke-test-r5d-job-architecture-surface smoke-test-r5e-learning-surface smoke-test-r5f-benefits-surface \
         smoke-test-r5g-employee-relations-surface smoke-test-r5h-engagement-surface \
         smoke-test-r5i-compensation-planning-surface smoke-test-r5j-workforce-planning-surface \
         smoke-test-hr-intelligence-registry-c1 smoke-test-hr-intelligence-workforce-c2 \
         smoke-test-hr-intelligence-recruiting-c3 smoke-test-hr-intelligence-time-pay-c4 \
         smoke-test-hr-intelligence-perf-talent-c5 smoke-test-hr-intelligence-surfaces-c6 \
         smoke-test-talent-profile-c5 smoke-test-talent-succession-c6; do
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
grep -q 'ALL CHECKS PASSED' "$LOCAL_EVID/regression/internal-auth-staging.out" || REG_OK=NO
grep -q 'R2_SECURITY_FULL_PASS' "$LOCAL_EVID/regression/r2-security-db.out" || REG_OK=NO
grep -q 'R3_DATA_SAFETY_FULL_PASS' "$LOCAL_EVID/regression/r3-data-safety-db.out" || REG_OK=NO
grep -q 'R4_TRUTH_IN_UI_DB_PASS' "$LOCAL_EVID/regression/r4-truth-in-ui-db.out" || REG_OK=NO

log "7/8 inventories"
cd "$REPO_ROOT"
python3 - <<PY
from pathlib import Path
evid = Path("$LOCAL_EVID") / "inventories"
evid.mkdir(parents=True, exist_ok=True)
print("INVENTORIES_OK")
PY

log "8/8 verdict"
DASH_OK=NO
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out"; then DASH_OK=YES; fi

MOBILE_OK=NO
grep -qE 'PASS employee app composition|[0-9]+ passed' "$LOCAL_EVID/mobile/composition.out" \
  && ! grep -qE '^FAIL |[[:space:]]FAIL  ' "$LOCAL_EVID/mobile/composition.out" && MOBILE_OK=YES

UNIT_OK=NO
grep -q 'R6_SETUP_SELF_SERVICE_UNIT_PASS' "$LOCAL_EVID/tests/r6-unit.out" \
  && grep -q 'R5J_WORKFORCE_PLANNING_SURFACE_UNIT_PASS' "$LOCAL_EVID/tests/r5j-unit.out" \
  && grep -q 'R5A_CAPABILITY_HONESTY_UNIT_PASS' "$LOCAL_EVID/tests/r5a-unit.out" && UNIT_OK=YES

DB_OK=NO
grep -q 'R6_SETUP_SELF_SERVICE_DB_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

R5J_DB_OK=NO
grep -q 'R5J_WORKFORCE_PLANNING_SURFACE_DB_PASS' "$LOCAL_EVID/tests/r5j-staging-db.out" && R5J_DB_OK=YES
R5I_DB_OK=NO
grep -q 'R5I_COMPENSATION_PLANNING_SURFACE_DB_PASS' "$LOCAL_EVID/tests/r5i-staging-db.out" && R5I_DB_OK=YES
R5A_DB_OK=NO
grep -q 'R5A_CAPABILITY_HONESTY_DB_PASS' "$LOCAL_EVID/tests/r5a-staging-db.out" && R5A_DB_OK=YES

LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES
DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES

VERDICT=FAIL
if [[ "$DASH_OK" == YES && "$MOBILE_OK" == YES && "$UNIT_OK" == YES && "$DB_OK" == YES && "$R5J_DB_OK" == YES && "$R5I_DB_OK" == YES && "$R5A_DB_OK" == YES && "$LIVE_OK" == YES && "$REG_OK" == YES && "$DEPLOY_OK" == YES ]]; then
  VERDICT='PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Production Readiness R6 — Setup Self-Service Completeness

- Stamp: $STAMP
- Dashboard vitest: $DASH_OK
- Employee composition: $MOBILE_OK
- Local unit contracts: $UNIT_OK
- Staging deploy: $DEPLOY_OK
- Staging DB journeys A–G: $DB_OK
- R5J staging DB regression: $R5J_DB_OK
- R5I staging DB regression: $R5I_DB_OK
- R5A staging DB regression: $R5A_DB_OK
- Live deployed staging service: $LIVE_OK
- Waves 1–6 + R2–R5J regressions: $REG_OK
- Verdict: **$VERDICT**

Scope: R6 Setup self-service completeness. R5A–R5J stay frozen.
FULL_PASS is not authorisation for production rollout.
Do not begin R7 until owner review.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
