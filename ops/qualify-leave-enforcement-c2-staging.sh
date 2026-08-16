#!/usr/bin/env bash
# Wave 2 C2 — Leave Enforcement qualify (company-scoped; global enforcement off).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/leave-enforcement-c2-$STAMP"
REMOTE_STAGE="/tmp/leave-enf-c2-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit/DB prove (uses staging DB via SSH below; local gates if no DB)"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
# Gate-only quick check by importing module
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_LEAVE_ENFORCEMENT"]="off"
import leave_enforcement_c2 as e
g=e.leave_enforcement_enabled_for_company(None,"WATHEFNI")
assert g.get("ok") is not True
print("LOCAL_GATES_OK")
PY

log "freeze regression"
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-regression.out" || true

log "stage sources"
cp -a \
  "$ORCH_SRC/leave_enforcement_c2.py" \
  "$ORCH_SRC/leave_policy_wave2.py" \
  "$ORCH_SRC/smoke-test-leave-enforcement-c2.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/LEAVE_ENFORCEMENT_C2_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/leave_enforcement_c2.py" \
  "$ORCH_SRC/leave_policy_wave2.py" \
  "$ORCH_SRC/smoke-test-leave-enforcement-c2.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global enforcement enable)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
if grep -Rls 'WATHEFNI_LEAVE_ENFORCEMENT=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_LEAVE_ENFORCEMENT_ON; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_ENFORCEMENT_OFF
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
# Process-scoped flags only inside the smoke.
"\$PYBIN" smoke-test-leave-enforcement-c2.py
echo STAGING_RC=\$?
REMOTE

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'LEAVE_ENFORCEMENT_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi
FREEZE_OK=YES
if ! grep -qE 'passed, 0 failed' "$LOCAL_EVID/tests/freeze-regression.out" 2>/dev/null; then
  FREEZE_OK=NO
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES && "$FREEZE_OK" == YES ]]; then
  VERDICT='LEAVE_ENFORCEMENT_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Leave Enforcement C2 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- Freeze regression: $FREEZE_OK
- Global LEAVE_ENFORCEMENT: remains **off**
- Verdict: **$VERDICT**

Stop before C3 Shifts MSS until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != LEAVE_ENFORCEMENT_FULL_PASS ]]; then
  exit 1
fi
