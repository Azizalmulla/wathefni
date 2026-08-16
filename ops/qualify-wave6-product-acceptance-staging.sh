#!/usr/bin/env bash
# Wave 6 — Product Acceptance / Full HCM Expansion Gate (C8).
# Process-scoped flags inside DB smoke. No systemd-global enable.
# Does NOT unlock broad production or begin additional HCM domains.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/wave6-product-acceptance-$STAMP"
REMOTE_STAGE="/tmp/w6p-product-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,frontend}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit"
cd "$ORCH_SRC"
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi
"$PY" smoke-test-wave6-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "frontend setup cards"
python3 - <<'PY' 2>&1 | tee "$LOCAL_EVID/frontend/contract.out"
from pathlib import Path
import sys
sys.path.insert(0, "/Users/azizalmulla/Desktop/claw/wathefni-orchestrator")
import wave6_hcm_expansion_product_c8 as c8
fe = c8.frontend_setup_cards_scan()
assert fe["ok"] is True, fe
print("FRONTEND_SETUP_CARDS_OK")
PY

log "stage sources"
FILES=(
  wave6_hcm_expansion_product_c8.py
  setup_console_wave6_policies.py
  smoke-test-wave6-product-acceptance.py
  smoke-test-wave6-product-acceptance-db.py
  workforce_planning_c7.py
  compensation_planning_c6.py
  engagement_c5.py
  employee_relations_c4.py
  benefits_administration_c3.py
  learning_development_c2.py
  job_architecture_c1.py
)
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/WAVE6_PRODUCT_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/WAVE6_PRODUCT_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
SCP_ARGS=()
for f in "${FILES[@]}"; do SCP_ARGS+=("$ORCH_SRC/$f"); done
"${SCP[@]}" "${SCP_ARGS[@]}" "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
test -f "\$STG/wave6_hcm_expansion_product_c8.py"
for flag in HCM_EXPANSION_PRODUCT_C8 WORKFORCE_PLANNING_C7 COMP_PLANNING_C6 ENGAGEMENT_C5 EMPLOYEE_RELATIONS_C4 BENEFITS_C3 LEARNING_C2 JOB_ARCHITECTURE_C1; do
  if grep -Rls "WATHEFNI_\${flag}=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
    echo "UNEXPECTED_SYSTEMD_\${flag}_ON"; exit 1
  fi
done
echo STAGING_COPY_OK_GLOBAL_WAVE6_OFF
REMOTE

staging_py() {
  local script="$1"
  local out="$2"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$out"
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
"\$PYBIN" "$script"
echo STAGING_RC=\$?
REMOTE
}

log "staging DB product acceptance prove"
staging_py smoke-test-wave6-product-acceptance-db.py "$LOCAL_EVID/tests/staging-db.out"

log "C1–C7 Wave6 unit regressions + Waves 1–5 freeze"
REG_OK=YES
set +e
"$PY" "$ORCH_SRC/smoke-test-job-architecture-c1.py" >"$LOCAL_EVID/regression/ja-c1-unit.out" 2>&1
JA_RC=$?
"$PY" "$ORCH_SRC/smoke-test-learning-development-c2.py" >"$LOCAL_EVID/regression/ld-c2-unit.out" 2>&1
LD_RC=$?
"$PY" "$ORCH_SRC/smoke-test-benefits-administration-c3.py" >"$LOCAL_EVID/regression/bn-c3-unit.out" 2>&1
BN_RC=$?
"$PY" "$ORCH_SRC/smoke-test-employee-relations-c4.py" >"$LOCAL_EVID/regression/er-c4-unit.out" 2>&1
ER_RC=$?
"$PY" "$ORCH_SRC/smoke-test-engagement-c5.py" >"$LOCAL_EVID/regression/eg-c5-unit.out" 2>&1
EG_RC=$?
"$PY" "$ORCH_SRC/smoke-test-compensation-planning-c6.py" >"$LOCAL_EVID/regression/cp-c6-unit.out" 2>&1
CP_RC=$?
"$PY" "$ORCH_SRC/smoke-test-workforce-planning-c7.py" >"$LOCAL_EVID/regression/wfp-c7-unit.out" 2>&1
WFP_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave5-product-acceptance.py" >"$LOCAL_EVID/regression/wave5-unit.out" 2>&1
W5_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave4-product-acceptance.py" >"$LOCAL_EVID/regression/wave4-unit.out" 2>&1
W4_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave3-product-acceptance.py" >"$LOCAL_EVID/regression/wave3-unit.out" 2>&1
W3_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave2-product-acceptance.py" >"$LOCAL_EVID/regression/wave2-unit.out" 2>&1
W2_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave1-product-acceptance.py" >"$LOCAL_EVID/regression/wave1-unit.out" 2>&1
W1_RC=$?
set -e
{
  echo "JA_C1_UNIT rc=$JA_RC"
  echo "LD_C2_UNIT rc=$LD_RC"
  echo "BN_C3_UNIT rc=$BN_RC"
  echo "ER_C4_UNIT rc=$ER_RC"
  echo "EG_C5_UNIT rc=$EG_RC"
  echo "CP_C6_UNIT rc=$CP_RC"
  echo "WFP_C7_UNIT rc=$WFP_RC"
  echo "WAVE5_UNIT rc=$W5_RC"
  echo "WAVE4_UNIT rc=$W4_RC"
  echo "WAVE3_UNIT rc=$W3_RC"
  echo "WAVE2_UNIT rc=$W2_RC"
  echo "WAVE1_UNIT rc=$W1_RC"
} | tee "$LOCAL_EVID/regression/summary.txt"
for f in ja-c1-unit.out ld-c2-unit.out bn-c3-unit.out er-c4-unit.out eg-c5-unit.out cp-c6-unit.out wfp-c7-unit.out; do
  if grep -qE 'FAIL  |Traceback' "$LOCAL_EVID/regression/$f"; then REG_OK=NO; fi
  if ! grep -qE '[0-9]+ passed' "$LOCAL_EVID/regression/$f"; then REG_OK=NO; fi
done
if [[ $W5_RC -ne 0 || $W4_RC -ne 0 || $W3_RC -ne 0 || $W2_RC -ne 0 || $W1_RC -ne 0 ]]; then REG_OK=NO; fi

UNIT_OK=NO
if grep -q 'WAVE6_PRODUCT_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi
FE_OK=NO; grep -q 'FRONTEND_SETUP_CARDS_OK' "$LOCAL_EVID/frontend/contract.out" && FE_OK=YES
DB_OK=NO
if grep -q 'WAVE6_PRODUCT_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$FE_OK" == YES && "$DB_OK" == YES && "$REG_OK" == YES ]]; then
  VERDICT='WAVE6_PRODUCT_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Wave 6 Product Acceptance — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Frontend Setup cards: $FE_OK
- Staging DB: $DB_OK
- C1–C7 Wave6 + Waves 1–5 unit freezes: $REG_OK
- Global Wave 6 flags: remain **off**
- Verdict: **$VERDICT**

Freeze Wave 6 and STOP for owner sign-off. Do not begin additional HCM domains automatically.
FULL_PASS ≠ broad production rollout.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "WAVE6_PRODUCT_FULL_PASS" ]]
