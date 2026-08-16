#!/usr/bin/env bash
# Wave 1 — Full lifecycle staging qualify (Req→…→Probation).
# Process-scoped flags only inside DB smoke. No systemd-global enable.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/wave1-lifecycle-full-$STAMP"
REMOTE_STAGE="/tmp/w1l-lifecycle-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-wave1-lifecycle-full.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "stage sources"
cp -a \
  "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/preboarding.py" \
  "$ORCH_SRC/hire_ready_bridge.py" \
  "$ORCH_SRC/probation.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$ORCH_SRC/smoke-test-wave1-lifecycle-full.py" \
  "$ORCH_SRC/smoke-test-wave1-lifecycle-full-db.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/"*.sql "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/REQUISITIONS_SURFACE_WAVE_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PROBATION_SURFACE_WAVE_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/HIRE_READY_BRIDGE_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql'"
"${SCP[@]}" \
  "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/preboarding.py" \
  "$ORCH_SRC/hire_ready_bridge.py" \
  "$ORCH_SRC/probation.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$ORCH_SRC/smoke-test-wave1-lifecycle-full-db.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" \
  "$ORCH_SRC/ops/sql/requisitions_wave1_v1.sql" \
  "$ORCH_SRC/ops/sql/preboarding_wave1_v1.sql" \
  "$ORCH_SRC/ops/sql/probation_wave1_v1.sql" \
  "$VPS_HOST:$REMOTE_STAGE/ops/sql/" 2>/dev/null || true

log "copy to staging orch (no global enable)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/*.sql "\$STG/ops/sql/" 2>/dev/null || true
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*requisition* 2>/dev/null \
  || ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*probation* 2>/dev/null \
  || ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*truth*sync* 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_DROPIN; exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "staging DB lifecycle prove"
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
"\$PYBIN" smoke-test-wave1-lifecycle-full-db.py
echo STAGING_DB_RC=\$?
REMOTE

UNIT_OK=NO
if grep -q 'WAVE1_LIFECYCLE_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi
DB_OK=NO
if grep -q 'WAVE1_LIFECYCLE_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='WAVE1_LIFECYCLE_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Wave 1 Full Lifecycle — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB: $DB_OK
- Chain: Requisition → approval → Job gate → Candidate → Offer accept → pending_start → Preboarding → Hire → Onboarding → 30/60/90 → Probation confirm
- Modularity: without Offers / without Onboarding / without Requisitions
- Global enable: NO
- Verdict: **$VERDICT**

Evidence: \`$LOCAL_EVID\`

Note: Wave 1 product completion still requires owner review gates beyond this backend lifecycle prove.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != WAVE1_LIFECYCLE_FULL_PASS ]]; then
  exit 1
fi
