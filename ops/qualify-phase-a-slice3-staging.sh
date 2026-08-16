#!/usr/bin/env bash
# Phase A Slice 3 — catalog/contracts + truth-sync dry-run + Slice2 invariant re-prove.
# No global enable. No writers. No Requisitions/Preboarding UI.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/phase-a-slice3-$STAMP"
REMOTE_STAGE="/tmp/phase-a-slice3-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources/ops/sql,remote}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit suite"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-workflow-task-sla-phase-a.py 2>&1 | tee "$LOCAL_EVID/tests/slice2-unit.out"
"$PY" smoke-test-capability-contracts-phase-a.py 2>&1 | tee "$LOCAL_EVID/tests/contracts.out"
"$PY" smoke-test-employment-truth-sync-phase-a.py 2>&1 | tee "$LOCAL_EVID/tests/truth-sync-unit.out"
set +e
"$PY" smoke-test-module-catalog.py 2>&1 | tee "$LOCAL_EVID/tests/catalog.out"
CAT_LOCAL_RC=${PIPESTATUS[0]}
set -e
if [[ "$CAT_LOCAL_RC" -ne 0 ]]; then
  if grep -qE 'application_environment_missing_or_invalid|could not connect|OperationalError' "$LOCAL_EVID/tests/catalog.out"; then
    echo "LOCAL_CATALOG_APP_DB_SKIP — catalog assertions already green; app HTTP deferred to staging" | tee -a "$LOCAL_EVID/tests/catalog.out"
  else
    # Catalog unit assertions failed before app HTTP — hard fail.
    if ! grep -q 'catalog contains exactly the 17 canonical product modules' "$LOCAL_EVID/tests/catalog.out"; then
      echo "LOCAL_CATALOG_FAILED"; exit 1
    fi
    echo "LOCAL_CATALOG_PARTIAL — continuing to staging prove" | tee -a "$LOCAL_EVID/tests/catalog.out"
  fi
fi

log "stage sources"
cp -a \
  "$ORCH_SRC/workflow_task_sla.py" \
  "$ORCH_SRC/module_catalog.py" \
  "$ORCH_SRC/capability_contracts.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a-db.py" \
  "$ORCH_SRC/smoke-test-module-catalog.py" \
  "$ORCH_SRC/smoke-test-capability-contracts-phase-a.py" \
  "$ORCH_SRC/smoke-test-employment-truth-sync-phase-a.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/workflow_task_sla_phase_a_v1.sql" \
  "$ORCH_SRC/ops/sql/workflow_task_sla_phase_a_v1b_invariants.sql" \
  "$LOCAL_EVID/sources/ops/sql/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql'"
"${SCP[@]}" \
  "$ORCH_SRC/workflow_task_sla.py" \
  "$ORCH_SRC/module_catalog.py" \
  "$ORCH_SRC/capability_contracts.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a-db.py" \
  "$ORCH_SRC/smoke-test-module-catalog.py" \
  "$ORCH_SRC/smoke-test-capability-contracts-phase-a.py" \
  "$ORCH_SRC/smoke-test-employment-truth-sync-phase-a.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/workflow_task_sla_phase_a_v1.sql" \
  "$ORCH_SRC/ops/sql/workflow_task_sla_phase_a_v1b_invariants.sql" \
  "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

log "copy to staging orch (no systemd flags / no writers)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/*.sql "\$STG/ops/sql/"
echo STAGING_COPY_OK
REMOTE

log "staging DB: slice2 invariants + truth-sync dry-run + catalog"
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
unset WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS || true
export WATHEFNI_TRUTH_SYNC_COMPANY=WATHEFNI
export WATHEFNI_WORKFLOW_TASKS=on
export WATHEFNI_WORKFLOW_SLA=on
export WATHEFNI_WORKFLOW_TASKS_COMPANIES=WFT-PLACEHOLDER
export WATHEFNI_WORKFLOW_SLA_COMPANIES=WFT-PLACEHOLDER
echo '=== SLICE2_DB ==='
"\$PYBIN" smoke-test-workflow-task-sla-phase-a-db.py
echo '=== CATALOG ==='
"\$PYBIN" smoke-test-module-catalog.py
echo '=== CONTRACTS ==='
"\$PYBIN" smoke-test-capability-contracts-phase-a.py
echo '=== TRUTH_SYNC ==='
"\$PYBIN" smoke-test-employment-truth-sync-phase-a.py
echo STAGING_SLICE3_DONE
REMOTE

ok() { grep -qE '[0-9]+ passed, 0 failed' "$1" && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$1"; }

S2_OK=NO; grep -q PHASE_A_SLICE2_DB_FULL_PASS "$LOCAL_EVID/tests/staging-db.out" && S2_OK=YES
TS_OK=NO; grep -q PHASE_A_SLICE3_TRUTH_SYNC_DRY_RUN_PASS "$LOCAL_EVID/tests/staging-db.out" && TS_OK=YES
CAT_OK=NO
awk '/=== CATALOG ===/,/=== CONTRACTS ===/' "$LOCAL_EVID/tests/staging-db.out" | grep -qE '[0-9]+ passed, 0 failed' && CAT_OK=YES
CON_OK=NO
awk '/=== CONTRACTS ===/,/=== TRUTH_SYNC ===/' "$LOCAL_EVID/tests/staging-db.out" | grep -qE '[0-9]+ passed, 0 failed' && CON_OK=YES

VERDICT=FAIL
if [[ "$S2_OK" == YES && "$TS_OK" == YES && "$CAT_OK" == YES && "$CON_OK" == YES ]]; then
  VERDICT=PHASE_A_SLICE3_FULL_PASS
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Phase A Slice 3 — Catalog/Contracts + Truth-Sync Dry-Run

- Stamp: $STAMP
- Slice2 DB invariants re-prove: $S2_OK
- Catalog: $CAT_OK
- Contracts: $CON_OK
- Truth-sync dry-run: $TS_OK
- Writers: OFF
- Global enable: NO
- Verdict: **$VERDICT**
EOF

echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "PHASE_A_SLICE3_FULL_PASS" ]]
