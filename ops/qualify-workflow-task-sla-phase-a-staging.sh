#!/usr/bin/env bash
# Phase A Slice 2 — task ontology + SLA staging DB prove (no global enable).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/workflow-task-sla-phase-a-$STAMP"
REMOTE_STAGE="/tmp/wft-sla-phase-a-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/workflow-task-sla-phase-a/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources/ops/sql,remote}

log() { printf '\n=== %s ===\n' "$*"; }

log "local unit"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-workflow-task-sla-phase-a.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "stage + copy to staging orchestrator (no systemd enable)"
cp -a "$ORCH_SRC/workflow_task_sla.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a-db.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/workflow_task_sla_phase_a_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/qualify-workflow-task-sla-phase-a-staging.sh" "$LOCAL_EVID/sources/"

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/workflow_task_sla.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a.py" \
  "$ORCH_SRC/smoke-test-workflow-task-sla-phase-a-db.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/workflow_task_sla_phase_a_v1.sql" "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/workflow_task_sla.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-workflow-task-sla-phase-a.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-workflow-task-sla-phase-a-db.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/workflow_task_sla_phase_a_v1.sql "\$STG/ops/sql/"
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*workflow*task* 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_ENABLE; exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "staging DB prove"
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
export WATHEFNI_WORKFLOW_TASKS=on
export WATHEFNI_WORKFLOW_SLA=on
export WATHEFNI_WORKFLOW_TASKS_COMPANIES=WFT-PLACEHOLDER
export WATHEFNI_WORKFLOW_SLA_COMPANIES=WFT-PLACEHOLDER
"\$PYBIN" smoke-test-workflow-task-sla-phase-a-db.py
echo STAGING_DB_RC=\$?
REMOTE

DB_OK=NO
if grep -q 'PHASE_A_SLICE2_DB_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi
UNIT_OK=NO
if grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out"; then UNIT_OK=YES; fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT=PHASE_A_SLICE2_FULL_PASS
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Workflow Task + SLA Phase A Slice 2

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB: $DB_OK
- Global enable: NO
- Verdict: **$VERDICT**
EOF

echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "PHASE_A_SLICE2_FULL_PASS" ]]
