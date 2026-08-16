#!/usr/bin/env bash
# Wave 3 C3 — Exit intent (resignation/termination/EOC) qualify — synthetic; real termination dark.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/exit-intent-c3-$STAMP"
REMOTE_STAGE="/tmp/exit-intent-c3-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_RESIGNATION_ESS_C3"]="off"
os.environ["WATHEFNI_REAL_TERMINATION_CANARY"]="off"
import exit_intent_c3 as e
assert e.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert e.honesty_payload().get("assistant_mutations") is False
assert e.honesty_payload().get("clearance_in_c3") is False
assert e.honesty_payload().get("real_termination_dark") is True
assert e.real_termination_canary_on() is False
assert e.PASS_STAMP == "RESIGNATION_TERMINATION_FULL_PASS"
print("LOCAL_GATES_OK")
PY

log "stage sources"
cp -a \
  "$ORCH_SRC/exit_intent_c3.py" \
  "$ORCH_SRC/smoke-test-exit-intent-c3.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/EXIT_INTENT_C3_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/exit_intent_c3.py" \
  "$ORCH_SRC/smoke-test-exit-intent-c3.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global resignation/exit unlock; real termination dark)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
if grep -Rls 'WATHEFNI_RESIGNATION_ESS_C3=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_RESIGNATION_ESS_C3_ON; exit 1
fi
if grep -Rls 'WATHEFNI_REAL_TERMINATION_CANARY=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_REAL_TERMINATION_CANARY_ON; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_EXIT_INTENT_OFF_REAL_TERM_DARK
REMOTE

log "staging DB prove"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-db.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
export PYTHONPATH="\$STG:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_REAL_TERMINATION_CANARY=off
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" smoke-test-exit-intent-c3.py
echo STAGING_RC=\$?
REMOTE

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'RESIGNATION_TERMINATION_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='RESIGNATION_TERMINATION_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Exit Intent C3 — Staging Prove (synthetic)

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- Global RESIGNATION_ESS_C3: remains **off**
- REAL_TERMINATION_CANARY: remains **off**
- Verdict: **$VERDICT**

Stop before C4 Offboarding + Clearance until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != RESIGNATION_TERMINATION_FULL_PASS ]]; then
  exit 1
fi
exit 0
