#!/usr/bin/env bash
# Wave 1 — Hire→Ready bridge prove on staging.
# No systemd-global enable. Truth-sync writers only process-scoped company canary inside DB smoke.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/hire-ready-bridge-$STAMP"
REMOTE_STAGE="/tmp/hrb-wave1-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/hire-ready-bridge/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
echo "$LOCAL_EVID" > /tmp/hrb-wave1.evid
echo "$STAMP" > /tmp/hrb-wave1.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local unit smoke"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
set +e
"$PY" smoke-test-hire-ready-bridge.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"
UNIT_RC=${PIPESTATUS[0]}
set -e
if [[ "$UNIT_RC" -ne 0 ]]; then
  echo "UNIT_FAILED"
  exit 1
fi

log "stage sources (no systemd env enable)"
cp -a "$ORCH_SRC/hire_ready_bridge.py" \
  "$ORCH_SRC/hire_operations.py" \
  "$ORCH_SRC/offer_service.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$ORCH_SRC/preboarding_http.py" \
  "$ORCH_SRC/smoke-test-hire-ready-bridge.py" \
  "$ORCH_SRC/smoke-test-hire-ready-bridge-db.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-hire-ready-bridge-staging.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/HIRE_READY_BRIDGE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PREBOARDING_SURFACE_WAVE_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/hire_ready_bridge.py" \
  "$ORCH_SRC/hire_operations.py" \
  "$ORCH_SRC/offer_service.py" \
  "$ORCH_SRC/employment_truth_sync.py" \
  "$ORCH_SRC/preboarding_http.py" \
  "$ORCH_SRC/smoke-test-hire-ready-bridge.py" \
  "$ORCH_SRC/smoke-test-hire-ready-bridge-db.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "copy into staging orchestrator tree (NO global flag)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
test -d "\$STG"
cp -a '$REMOTE_STAGE'/hire_ready_bridge.py "\$STG/"
cp -a '$REMOTE_STAGE'/hire_operations.py "\$STG/"
cp -a '$REMOTE_STAGE'/offer_service.py "\$STG/"
cp -a '$REMOTE_STAGE'/employment_truth_sync.py "\$STG/"
cp -a '$REMOTE_STAGE'/preboarding_http.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-hire-ready-bridge.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-hire-ready-bridge-db.py "\$STG/"
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*hire*ready* 2>/dev/null; then
  echo 'UNEXPECTED_SYSTEMD_HIRE_READY_DROPIN'
  exit 1
fi
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*truth*sync* 2>/dev/null; then
  echo 'UNEXPECTED_SYSTEMD_TRUTH_SYNC_DROPIN'
  exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "staging DB prove (process-scoped flags only; writers company canary inside smoke)"
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
# Deliberately leave systemd-global writers OFF; DB smoke sets process-scoped canary.
"\$PYBIN" smoke-test-hire-ready-bridge-db.py
echo STAGING_DB_RC=\$?
REMOTE

DB_OK=NO
if grep -q 'HIRE_READY_BRIDGE_DB_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

UNIT_OK=NO
if grep -q 'HIRE_READY_BRIDGE_UNIT_FULL_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='HIRE_READY_BRIDGE_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Hire → Ready Bridge — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB: $DB_OK
- Global enable: NO (process-scoped flags only)
- Truth-sync writers: company canary inside DB smoke only; systemd remains OFF
- Preboarding surfaces: FROZEN (contract preserved)
- Verdict: **$VERDICT**

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != HIRE_READY_BRIDGE_FULL_PASS ]]; then
  exit 1
fi
