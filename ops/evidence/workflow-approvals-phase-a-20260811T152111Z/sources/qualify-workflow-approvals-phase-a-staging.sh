#!/usr/bin/env bash
# Phase A Slice 1 — workflow_approvals DB prove on staging (no global enable, no production).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/workflow-approvals-phase-a-$STAMP"
REMOTE_STAGE="/tmp/wfa-phase-a-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/workflow-approvals-phase-a/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources/ops/sql,remote}
echo "$LOCAL_EVID" > /tmp/wfa-phase-a.evid
echo "$STAMP" > /tmp/wfa-phase-a.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local unit smoke"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
set +e
"$PY" smoke-test-workflow-approvals-phase-a.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"
UNIT_RC=${PIPESTATUS[0]}
set -e
if [[ "$UNIT_RC" -ne 0 ]]; then
  echo "UNIT_FAILED"
  exit 1
fi

log "stage sources (no systemd env enable)"
cp -a "$ORCH_SRC/workflow_approvals.py" \
  "$ORCH_SRC/smoke-test-workflow-approvals-phase-a.py" \
  "$ORCH_SRC/smoke-test-workflow-approvals-phase-a-db.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/workflow_approvals_phase_a_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/qualify-workflow-approvals-phase-a-staging.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/WORKFLOW_APPROVALS_PHASE_A_SLICE1.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/workflow_approvals.py" \
  "$ORCH_SRC/smoke-test-workflow-approvals-phase-a.py" \
  "$ORCH_SRC/smoke-test-workflow-approvals-phase-a-db.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/workflow_approvals_phase_a_v1.sql" "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

log "copy into staging orchestrator tree (schema pack + authority only; NO global flag)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
test -d "\$STG"
cp -a '$REMOTE_STAGE'/workflow_approvals.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-workflow-approvals-phase-a.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-workflow-approvals-phase-a-db.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/workflow_approvals_phase_a_v1.sql "\$STG/ops/sql/"
# Explicitly ensure we did NOT write a systemd drop-in enabling the feature.
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*workflow* 2>/dev/null; then
  echo 'UNEXPECTED_SYSTEMD_WORKFLOW_DROPIN'
  exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "staging DB prove (process-scoped flags only)"
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
# Process-only canary flags — not systemd.
export WATHEFNI_WORKFLOW_APPROVALS=on
# Company allowlist is overridden inside the smoke to a synthetic WFA* tenant.
export WATHEFNI_WORKFLOW_APPROVALS_COMPANIES=WFA-CANARY-PLACEHOLDER
"\$PYBIN" smoke-test-workflow-approvals-phase-a-db.py
echo STAGING_DB_RC=\$?
REMOTE

DB_OK=NO
if grep -q 'PHASE_A_SLICE1_DB_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

UNIT_OK=NO
if grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='PHASE_A_SLICE1_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Workflow Approvals Phase A Slice 1 — Staging DB Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB: $DB_OK
- Global enable: NO (process-scoped flags only)
- Verdict: **$VERDICT**

Evidence: \`$LOCAL_EVID\`
EOF

"${SSH[@]}" "mkdir -p '$REMOTE_EVID' && cat > '$REMOTE_EVID/REPORT.md'" < "$LOCAL_EVID/REPORT.md" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" 2>/dev/null || true

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "PHASE_A_SLICE1_FULL_PASS" ]]
