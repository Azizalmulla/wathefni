#!/usr/bin/env bash
# Production Readiness R4 — Truth-in-UI qualification.
#
# Proves the R1 truth-in-UI blocker set (P0-7, P1-10..14, P1-16, P1-17) against
# local dashboard contracts and isolated staging:
#
#   1. dashboard vitest (named surfaces + shared data-state)
#   2. local orchestrator unit contracts + source scan
#   3. staging database notification suppression
#   4. live deployed staging service (module map present)
#   5. Waves 1–6 + R2 + R3 regressions
#
# Does not touch production customer data. Does not begin R5.
# FULL_PASS here does not authorise production rollout.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r4-truth-ui-$STAMP"
REMOTE_STAGE="/tmp/r4-truth-ui-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,scan,dashboard}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  setup_console_admin_phase4.py
  smoke-test-r4-truth-in-ui.py
  smoke-test-r4-truth-in-ui-db.py
  smoke-test-r3-data-safety.py
  smoke-test-r3-data-safety-db.py
  smoke-test-r2-security-db.py
  smoke-test-internal-auth.py
  smoke-test-outbound-shift.py
  smoke-test-reminder-frequency.py
)

log "1/7 dashboard vitest (named truth-in-UI surfaces)"
cd "$DASH_SRC"
if [[ -x "$DASH_SRC/node_modules/.bin/vitest" ]]; then
  npx vitest run \
    src/pages/shared/dataState.test.tsx \
    src/lib/alertsDeliveryAccess.test.ts \
    src/pages/InterviewsPage.test.tsx \
    src/pages/OverviewWave2Contract.test.tsx \
    src/lib/workspaceCapability.test.ts \
    src/lib/dashboardNavigation.test.ts \
    src/posthire/AlertsDeliveryWave1Contract.test.ts \
    src/components/candidates/CandidatesTable.test.tsx \
    src/lib/moduleWorkspace.test.ts \
    2>&1 | tee "$LOCAL_EVID/dashboard/named.out"
  npx vitest run 2>&1 | tee "$LOCAL_EVID/dashboard/full.out"
else
  echo "vitest missing" | tee "$LOCAL_EVID/dashboard/named.out"
  exit 1
fi

log "2/7 local unit contracts + classified scan"
cd "$ORCH_SRC"
"$PY" smoke-test-r4-truth-in-ui.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"
"$PY" "$REPO_ROOT/ops/r4-truth-in-ui-scan.py" --out "$LOCAL_EVID/scan/truth-state-scan.json" \
  2>&1 | tee "$LOCAL_EVID/scan/scan.out"

log "3/7 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R4_TRUTH_IN_UI_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/smoke-test-r4-truth-in-ui.py'
python3 -m py_compile '$STG/app.py'
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

log "4/7 staging database notification suppression"
staging_py smoke-test-r4-truth-in-ui-db.py "$LOCAL_EVID/tests/staging-db.out"

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
import sys
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
import app

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

ck("live leave_decision maps to leave", app.source_module_for_notification_flow("leave_decision") == "leave")
ck("live shift maps to shifts", app.source_module_for_notification_flow("shift") == "shifts")
ck("live app_activation maps to employee_app", app.source_module_for_notification_flow("app_activation") == "employee_app")
ck("live unmapped flow is allowed (None)", app.source_module_for_notification_flow("not_a_real_flow") is None)
ck("live helper is on deliver path", hasattr(app, "notification_source_module_enabled"))
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "6/7 regressions (Waves 1–6 + R2 + R3 + internal-auth)"
REG_OK=YES
set +e
for t in smoke-test-wave6-product-acceptance smoke-test-job-architecture-c1 smoke-test-learning-development-c2 \
         smoke-test-benefits-administration-c3 smoke-test-employee-relations-c4 smoke-test-engagement-c5 \
         smoke-test-compensation-planning-c6 smoke-test-workforce-planning-c7 smoke-test-wave5-product-acceptance \
         smoke-test-wave4-product-acceptance smoke-test-wave3-product-acceptance smoke-test-wave2-product-acceptance \
         smoke-test-wave1-product-acceptance smoke-test-r2-security smoke-test-r3-data-safety; do
  "$PY" "$ORCH_SRC/$t.py" >"$LOCAL_EVID/regression/$t.out" 2>&1
  echo "$t rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
done
"$PY" -m unittest test_interaction_authority_contracts >"$LOCAL_EVID/regression/interaction-authority-contracts.out" 2>&1
echo "interaction_authority_contracts rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
set -e
staging_py smoke-test-internal-auth.py "$LOCAL_EVID/regression/internal-auth-staging.out"
staging_py smoke-test-r2-security-db.py "$LOCAL_EVID/regression/r2-security-db.out"
staging_py smoke-test-r3-data-safety-db.py "$LOCAL_EVID/regression/r3-data-safety-db.out"
for f in "$LOCAL_EVID"/regression/smoke-test-*.out; do
  grep -qE '^[[:space:]]*FAIL  |Traceback' "$f" && REG_OK=NO
  grep -qE '[0-9]+ passed' "$f" || REG_OK=NO
done
grep -q 'OK' "$LOCAL_EVID/regression/interaction-authority-contracts.out" || REG_OK=NO
grep -q 'ALL CHECKS PASSED' "$LOCAL_EVID/regression/internal-auth-staging.out" || REG_OK=NO
grep -q 'R2_SECURITY_FULL_PASS' "$LOCAL_EVID/regression/r2-security-db.out" || REG_OK=NO
grep -q 'R3_DATA_SAFETY_FULL_PASS' "$LOCAL_EVID/regression/r3-data-safety-db.out" || REG_OK=NO

log "7/7 verdict"
DASH_OK=NO
grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" \
  && ! grep -qE 'FAIL|failed' "$LOCAL_EVID/dashboard/named.out" && DASH_OK=YES
# vitest prints "failed" in 0 failed — require 0 failed
if grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out"; then DASH_OK=NO; fi
if grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/named.out"; then DASH_OK=NO; fi
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out"; then DASH_OK=YES; fi

UNIT_OK=NO
grep -q 'R4_TRUTH_IN_UI_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" && UNIT_OK=YES

DB_OK=NO
grep -q 'R4_TRUTH_IN_UI_DB_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES

DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES

VERDICT=FAIL
if [[ "$DASH_OK" == YES && "$UNIT_OK" == YES && "$DB_OK" == YES && "$LIVE_OK" == YES && "$REG_OK" == YES && "$DEPLOY_OK" == YES ]]; then
  VERDICT='PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Production Readiness R4 — Truth-in-UI

- Stamp: $STAMP
- Dashboard vitest: $DASH_OK
- Local unit contracts: $UNIT_OK
- Staging deploy: $DEPLOY_OK
- Staging DB notification suppression: $DB_OK
- Live deployed staging service: $LIVE_OK
- Waves 1–6 + R2 + R3 regressions: $REG_OK
- Verdict: **$VERDICT**

Scope: R1 P0-7, P1-10, P1-11, P1-12, P1-13, P1-14, P1-16, P1-17.
Does not touch production customer data. Does not begin R5 Wave 4/6 Surface Programme.
FULL_PASS is not authorisation for production rollout.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
