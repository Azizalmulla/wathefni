#!/usr/bin/env bash
# Wave 6 C2 — Learning & Development qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/learning-development-c2-$STAMP"
REMOTE_STAGE="/tmp/learning-development-c2-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,frontend}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_LEARNING_C2"]="off"
os.environ["WATHEFNI_LEARNING_COMPANIES"]=""
import learning_development_c2 as ld
import setup_console_wave6_policies as w6
import job_architecture_c1 as ja
assert ld.PASS_STAMP == "LEARNING_DEVELOPMENT_FULL_PASS"
assert ja.PASS_STAMP == "JOB_ARCHITECTURE_FULL_PASS"
assert ld.COMMERCIAL_MODULE_KEY == "learning"
assert ld.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert w6.honesty_payload().get("setup_owns_wave6_policies") is True
assert "learning" in w6.WAVE6_MODULE_KEYS
assert "job_architecture" in w6.WAVE6_MODULE_KEYS
h = ld.honesty_payload()
assert h["does_not_duplicate_c3_development"] is True
assert h["completion_does_not_silently_close_development_action"] is True
assert h["ja_optional"] is True
assert h["assistant_mutations"] is False
src = open("learning_development_c2.py").read()
assert "ld_learning_items" in src and "ld_assignments" in src
assert "silently_closed_c3 = false" in src
assert "CREATE TABLE IF NOT EXISTS employees" not in src
print("LOCAL_GATES_OK")
PY

log "frontend setup card present"
python3 - <<'PY' 2>&1 | tee "$LOCAL_EVID/frontend/contract.out"
from pathlib import Path
root = Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/setup-console")
card = (root / "Wave6LearningPoliciesCard.tsx").read_text()
app = (root / "SetupConsoleApp.tsx").read_text()
ja = (root / "Wave6JobArchitecturePoliciesCard.tsx").read_text()
assert "Wave6LearningPoliciesCard" in app
assert "Wave6JobArchitecturePoliciesCard" in app
assert "wave6_learning" in card
assert "C3" in card or "development" in card.lower()
assert "wave6_job_architecture" in ja
print("FRONTEND_SETUP_CARD_OK")
PY

log "stage sources"
FILES=(
  learning_development_c2.py
  setup_console_wave6_policies.py
  smoke-test-learning-development-c2.py
  job_architecture_c1.py
)
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/LEARNING_DEVELOPMENT_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/LEARNING_DEVELOPMENT_C2_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/learning_development_c2.py" \
  "$ORCH_SRC/setup_console_wave6_policies.py" \
  "$ORCH_SRC/smoke-test-learning-development-c2.py" \
  "$ORCH_SRC/job_architecture_c1.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
test -f "\$STG/learning_development_c2.py"
test -f "\$STG/setup_console_wave6_policies.py"
if grep -Rls "WATHEFNI_LEARNING_C2=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo "UNEXPECTED_SYSTEMD_LEARNING_ON"; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_LEARNING_OFF
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
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" smoke-test-learning-development-c2.py
echo STAGING_RC=\$?
REMOTE

log "C1 JA + Waves 1–5 freeze unit regressions"
REG_OK=YES
set +e
"$PY" "$ORCH_SRC/smoke-test-job-architecture-c1.py" >"$LOCAL_EVID/regression/ja-c1-unit.out" 2>&1
JA_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave5-product-acceptance.py" >"$LOCAL_EVID/regression/wave5-unit.out" 2>&1
W5_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave4-product-acceptance.py" >"$LOCAL_EVID/regression/wave4-unit.out" 2>&1
W4_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave1-product-acceptance.py" >"$LOCAL_EVID/regression/wave1-unit.out" 2>&1
W1_RC=$?
set -e
{
  echo "JA_C1_UNIT rc=$JA_RC"
  echo "WAVE5_UNIT rc=$W5_RC"
  echo "WAVE4_UNIT rc=$W4_RC"
  echo "WAVE1_UNIT rc=$W1_RC"
} | tee "$LOCAL_EVID/regression/summary.txt"
# JA unit may SKIP DB locally — accept unit-only pass if no FAIL
if [[ $JA_RC -ne 0 ]]; then
  if grep -qE 'FAIL  |Traceback' "$LOCAL_EVID/regression/ja-c1-unit.out"; then REG_OK=NO; fi
  if ! grep -qE '[0-9]+ passed' "$LOCAL_EVID/regression/ja-c1-unit.out"; then REG_OK=NO; fi
fi
if [[ $W5_RC -ne 0 || $W4_RC -ne 0 || $W1_RC -ne 0 ]]; then REG_OK=NO; fi

GATES_OK=NO; grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
FE_OK=NO; grep -q 'FRONTEND_SETUP_CARD_OK' "$LOCAL_EVID/frontend/contract.out" && FE_OK=YES
DB_OK=NO
if grep -q 'LEARNING_DEVELOPMENT_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$FE_OK" == YES && "$DB_OK" == YES && "$REG_OK" == YES ]]; then
  VERDICT='LEARNING_DEVELOPMENT_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Learning & Development C2 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Frontend Setup card: $FE_OK
- Staging DB: $DB_OK
- C1 JA + Wave5/Wave4/Wave1 unit freezes: $REG_OK
- Global Learning flag: remains **off**
- Verdict: **$VERDICT**

Stop before C3 Benefits until owner accepts.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "LEARNING_DEVELOPMENT_FULL_PASS" ]]
