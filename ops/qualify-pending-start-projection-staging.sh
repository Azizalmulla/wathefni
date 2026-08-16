#!/usr/bin/env bash
# Prove pending_start hub projection fix + Slice3 dry-run P1–P9 on staging WATHEFNI.
# Truth-sync writers remain OFF. No global enable.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/pending-start-projection-$STAMP"
REMOTE_STAGE="/tmp/pending-start-proj-stage"

mkdir -p "$LOCAL_EVID"/{tests,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local units"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-employee-wave3-lifecycle-unit.py 2>&1 | tee "$LOCAL_EVID/tests/lifecycle-unit.out"
"$PY" smoke-test-employment-truth-sync-phase-a.py 2>&1 | tee "$LOCAL_EVID/tests/truth-sync-unit.out"

log "stage sources"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/employee_lifecycle_wave3.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$ORCH_SRC/employee_app_access.py" \
  "$ORCH_SRC/leave_authority_wave1.py" \
  "$ORCH_SRC/shifts_authority_wave1.py" \
  "$ORCH_SRC/smoke-test-employee-wave3-lifecycle-unit.py" \
  "$ORCH_SRC/smoke-test-employment-truth-sync-phase-a.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

# Also need app.py for directory stats if we want full prove — truth-sync doesn't need it.
# Copy critical modules into staging orch.
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/employee_lifecycle_wave3.py "\$STG/"
cp -a '$REMOTE_STAGE'/employment_truth_sync.py "\$STG/"
cp -a '$REMOTE_STAGE'/employee_app_access.py "\$STG/"
cp -a '$REMOTE_STAGE'/leave_authority_wave1.py "\$STG/"
cp -a '$REMOTE_STAGE'/shifts_authority_wave1.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-employee-wave3-lifecycle-unit.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-employment-truth-sync-phase-a.py "\$STG/"
echo STAGING_COPY_OK
REMOTE

# Patch app.py directory/messaging helpers on staging via scp of local app.py is huge —
# instead run a focused projection prove that imports lifecycle + truth-sync only.
log "staging prove"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-prove.out"
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
echo '=== LIFECYCLE_UNIT ==='
"\$PYBIN" smoke-test-employee-wave3-lifecycle-unit.py
echo '=== TRUTH_SYNC_DB ==='
"\$PYBIN" smoke-test-employment-truth-sync-phase-a.py
echo STAGING_PENDING_START_PROVE_DONE
REMOTE

PASS_OK=NO
if grep -q 'PHASE_A_SLICE3_PENDING_START_INVARIANTS_PASS' "$LOCAL_EVID/tests/staging-prove.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-prove.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-prove.out"; then
  PASS_OK=YES
fi

VERDICT=FAIL
if [[ "$PASS_OK" == YES ]]; then
  VERDICT=PHASE_A_SLICE3_FULL_PASS
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# pending_start projection fix + Slice 3 re-prove

- Stamp: $STAMP
- Staging prove: $PASS_OK
- Truth-sync writers: OFF
- Verdict: **$VERDICT**
EOF

echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "PHASE_A_SLICE3_FULL_PASS" ]]
