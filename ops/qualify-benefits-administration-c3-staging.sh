#!/usr/bin/env bash
# Wave 6 C3 — Benefits Administration qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/benefits-administration-c3-$STAMP"
REMOTE_STAGE="/tmp/benefits-administration-c3-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,frontend}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_BENEFITS_C3"]="off"
os.environ["WATHEFNI_BENEFITS_COMPANIES"]=""
import benefits_administration_c3 as bn
import setup_console_wave6_policies as w6
import learning_development_c2 as ld
import job_architecture_c1 as ja
assert bn.PASS_STAMP == "BENEFITS_FULL_PASS"
assert ld.PASS_STAMP == "LEARNING_DEVELOPMENT_FULL_PASS"
assert ja.PASS_STAMP == "JOB_ARCHITECTURE_FULL_PASS"
assert bn.COMMERCIAL_MODULE_KEY == "benefits"
assert bn.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert "benefits" in w6.WAVE6_MODULE_KEYS
assert w6.honesty_payload().get("benefits_claims_out") is True
h = bn.honesty_payload()
assert h["claims_adjudication_out"] is True
assert h["works_payroll_off"] is True
assert h["contribution_not_payroll_deduction"] is True
assert h["assistant_mutations"] is False
src = open("benefits_administration_c3.py").read()
assert "bn_plans" in src and "bn_coverage_periods" in src
assert "CREATE TABLE IF NOT EXISTS bn_claim" not in src
assert "finalized_payroll_rewritten = false" in src
print("LOCAL_GATES_OK")
PY

log "frontend setup card present"
python3 - <<'PY' 2>&1 | tee "$LOCAL_EVID/frontend/contract.out"
from pathlib import Path
root = Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/setup-console")
card = (root / "Wave6BenefitsPoliciesCard.tsx").read_text()
app = (root / "SetupConsoleApp.tsx").read_text()
assert "Wave6BenefitsPoliciesCard" in app
assert "Wave6LearningPoliciesCard" in app
assert "Wave6JobArchitecturePoliciesCard" in app
assert "wave6_benefits" in card
assert "claims" in card.lower() or "مطالبات" in card
print("FRONTEND_SETUP_CARD_OK")
PY

log "stage sources"
FILES=(
  benefits_administration_c3.py
  setup_console_wave6_policies.py
  smoke-test-benefits-administration-c3.py
  learning_development_c2.py
  job_architecture_c1.py
)
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/BENEFITS_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/BENEFITS_C3_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/benefits_administration_c3.py" \
  "$ORCH_SRC/setup_console_wave6_policies.py" \
  "$ORCH_SRC/smoke-test-benefits-administration-c3.py" \
  "$ORCH_SRC/learning_development_c2.py" \
  "$ORCH_SRC/job_architecture_c1.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
test -f "\$STG/benefits_administration_c3.py"
test -f "\$STG/setup_console_wave6_policies.py"
if grep -Rls "WATHEFNI_BENEFITS_C3=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo "UNEXPECTED_SYSTEMD_BENEFITS_ON"; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_BENEFITS_OFF
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
"\$PYBIN" smoke-test-benefits-administration-c3.py
echo STAGING_RC=\$?
REMOTE

log "C1+C2 Wave6 + Waves 1–5 freeze unit regressions"
REG_OK=YES
set +e
"$PY" "$ORCH_SRC/smoke-test-job-architecture-c1.py" >"$LOCAL_EVID/regression/ja-c1-unit.out" 2>&1
JA_RC=$?
"$PY" "$ORCH_SRC/smoke-test-learning-development-c2.py" >"$LOCAL_EVID/regression/ld-c2-unit.out" 2>&1
LD_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave5-product-acceptance.py" >"$LOCAL_EVID/regression/wave5-unit.out" 2>&1
W5_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave4-product-acceptance.py" >"$LOCAL_EVID/regression/wave4-unit.out" 2>&1
W4_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave1-product-acceptance.py" >"$LOCAL_EVID/regression/wave1-unit.out" 2>&1
W1_RC=$?
set -e
{
  echo "JA_C1_UNIT rc=$JA_RC"
  echo "LD_C2_UNIT rc=$LD_RC"
  echo "WAVE5_UNIT rc=$W5_RC"
  echo "WAVE4_UNIT rc=$W4_RC"
  echo "WAVE1_UNIT rc=$W1_RC"
} | tee "$LOCAL_EVID/regression/summary.txt"
for f in ja-c1-unit.out ld-c2-unit.out; do
  if grep -qE 'FAIL  |Traceback' "$LOCAL_EVID/regression/$f"; then REG_OK=NO; fi
  if ! grep -qE '[0-9]+ passed' "$LOCAL_EVID/regression/$f"; then REG_OK=NO; fi
done
if [[ $W5_RC -ne 0 || $W4_RC -ne 0 || $W1_RC -ne 0 ]]; then REG_OK=NO; fi

GATES_OK=NO; grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
FE_OK=NO; grep -q 'FRONTEND_SETUP_CARD_OK' "$LOCAL_EVID/frontend/contract.out" && FE_OK=YES
DB_OK=NO
if grep -q 'BENEFITS_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$FE_OK" == YES && "$DB_OK" == YES && "$REG_OK" == YES ]]; then
  VERDICT='BENEFITS_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Benefits Administration C3 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Frontend Setup card: $FE_OK
- Staging DB: $DB_OK
- C1+C2 Wave6 + Wave5/Wave4/Wave1 unit freezes: $REG_OK
- Global Benefits flag: remains **off**
- Verdict: **$VERDICT**

Stop before C4 Employee Relations until owner accepts.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "BENEFITS_FULL_PASS" ]]
