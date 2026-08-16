#!/usr/bin/env bash
# Wave 1 — Product Acceptance / Production Canary gate (WATHEFNI company-scoped only).
# Process-scoped flags inside DB smoke. No systemd-global enable. No Wave 2.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/wave1-product-acceptance-$STAMP"
REMOTE_STAGE="/tmp/w1p-product-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-wave1-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "stage sources"
cp -a \
  "$ORCH_SRC/setup_console_wave1_policies.py" \
  "$ORCH_SRC/wave1_task_sync.py" \
  "$ORCH_SRC/ops-seed-wave1-visual-canary.py" \
  "$ORCH_SRC/smoke-test-wave1-product-acceptance.py" \
  "$ORCH_SRC/smoke-test-wave1-product-acceptance-db.py" \
  "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/requisitions_http.py" \
  "$ORCH_SRC/preboarding.py" \
  "$ORCH_SRC/preboarding_http.py" \
  "$ORCH_SRC/probation.py" \
  "$ORCH_SRC/probation_http.py" \
  "$ORCH_SRC/hire_ready_bridge.py" \
  "$ORCH_SRC/app.py" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/setup-console/Wave1HireReadyPoliciesCard.tsx" "$LOCAL_EVID/sources/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/setup_console_wave1_policies.py" \
  "$ORCH_SRC/wave1_task_sync.py" \
  "$ORCH_SRC/ops-seed-wave1-visual-canary.py" \
  "$ORCH_SRC/smoke-test-wave1-product-acceptance-db.py" \
  "$ORCH_SRC/requisitions_http.py" \
  "$ORCH_SRC/preboarding_http.py" \
  "$ORCH_SRC/probation_http.py" \
  "$ORCH_SRC/app.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "copy to staging orch (no global enable)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*requisition* 2>/dev/null \
  || ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*probation* 2>/dev/null \
  || ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*preboard* 2>/dev/null \
  || ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*truth*sync* 2>/dev/null \
  || ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*hire*ready* 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_DROPIN; exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "staging DB product acceptance prove (+ visual canary seed)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-db.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" smoke-test-wave1-product-acceptance-db.py
echo STAGING_DB_RC=\$?
REMOTE

log "local regression units"
REG_OK=YES
: > "$LOCAL_EVID/regression/summary.txt"
for unit in \
  smoke-test-wave1-lifecycle-full.py \
  smoke-test-requisitions-wave1.py \
  smoke-test-requisitions-surfaces.py \
  smoke-test-preboarding-wave1.py \
  smoke-test-preboarding-surfaces.py \
  smoke-test-hire-ready-bridge.py \
  smoke-test-probation-wave1.py \
  smoke-test-probation-surfaces.py \
  smoke-test-workflow-approvals-phase-a.py \
  smoke-test-workflow-task-sla-phase-a.py \
  smoke-test-capability-contracts-phase-a.py \
  smoke-test-employment-truth-sync-phase-a.py
do
  if [[ -f "$ORCH_SRC/$unit" ]]; then
    set +e
    "$PY" "$ORCH_SRC/$unit" >"$LOCAL_EVID/regression/unit-$unit.out" 2>&1
    rc=$?
    set -e
    echo "UNIT $unit rc=$rc" | tee -a "$LOCAL_EVID/regression/summary.txt"
    if [[ $rc -ne 0 ]]; then REG_OK=NO; fi
  else
    echo "SKIP $unit" | tee -a "$LOCAL_EVID/regression/summary.txt"
  fi
done

log "staging regression DB pack (Wave 1 + Phase A)"
"${SCP[@]}" \
  "$ORCH_SRC/smoke-test-wave1-lifecycle-full-db.py" \
  "$ORCH_SRC/smoke-test-requisitions-wave1-db.py" \
  "$ORCH_SRC/smoke-test-requisitions-surfaces-db.py" \
  "$ORCH_SRC/smoke-test-preboarding-wave1-db.py" \
  "$ORCH_SRC/smoke-test-preboarding-surfaces-db.py" \
  "$ORCH_SRC/smoke-test-hire-ready-bridge-db.py" \
  "$ORCH_SRC/smoke-test-probation-wave1-db.py" \
  "$ORCH_SRC/smoke-test-probation-surfaces-db.py" \
  "$ORCH_SRC/smoke-test-workflow-approvals-phase-a-db.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a-db.py" \
  "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/preboarding.py" \
  "$ORCH_SRC/probation.py" \
  "$ORCH_SRC/hire_ready_bridge.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$VPS_HOST:$REMOTE_STAGE/" 2>/dev/null || true

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/regression/staging-db-pack.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
cp -a '$REMOTE_STAGE'/*.py "\$STG/" 2>/dev/null || true
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
FAILS=0
for db in \
  smoke-test-wave1-lifecycle-full-db.py \
  smoke-test-requisitions-wave1-db.py \
  smoke-test-requisitions-surfaces-db.py \
  smoke-test-preboarding-wave1-db.py \
  smoke-test-preboarding-surfaces-db.py \
  smoke-test-hire-ready-bridge-db.py \
  smoke-test-probation-wave1-db.py \
  smoke-test-probation-surfaces-db.py \
  smoke-test-workflow-approvals-phase-a-db.py \
  smoke-test-workflow-task-sla-phase-a-db.py
do
  echo "=== REG DB \$db ==="
  if ! "\$PYBIN" "\$db"; then
    echo "REG_DB_FAIL \$db"
    FAILS=\$((FAILS+1))
  fi
done
echo REG_DB_FAILS=\$FAILS
test "\$FAILS" -eq 0
REMOTE
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
  REG_OK=NO
fi
echo "REG_OK=$REG_OK" | tee -a "$LOCAL_EVID/regression/summary.txt"

UNIT_OK=NO
if grep -q 'WAVE1_PRODUCT_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi
DB_OK=NO
if grep -q 'WAVE1_PRODUCT_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES && "$REG_OK" == YES ]]; then
  VERDICT='WAVE1_PRODUCT_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Wave 1 Product Acceptance — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB / product gate: $DB_OK
- Regression pack: $REG_OK
- Canary company: WATHEFNI (company-scoped only; no global enable)
- Visual seed: Removable via \`ops-seed-wave1-visual-canary.py --cleanup\`
- Verdict: **$VERDICT**

## Covered
1. Product surfaces (Req / Preboard / Hire / Onboarding / Probation) + Setup Wave 1 policies
2. Modularity matrix (6 tenant configs)
3. Setup Console ownership for Wave 1 Hire→Ready policies
4. Canonical hr_tasks sync for Wave 1 events
5. Visual canary seed for owner review
6. Regression: lifecycle, requisitions, preboarding, hire-ready, probation, Phase A

## Safe debt (non-blocking)
- Requisition N-step approval binding → Wave 1 SoD single-step; platform N-step exists unbound
- Live WhatsApp/channel reminder fan-out → Phase A audit_only + canonical hr_tasks
- Broad production rollout beyond WATHEFNI canary → owner sign-off gate

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != WAVE1_PRODUCT_FULL_PASS ]]; then
  exit 1
fi
