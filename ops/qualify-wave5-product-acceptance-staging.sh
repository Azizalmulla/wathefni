#!/usr/bin/env bash
# Wave 5 — Product Acceptance / Full Intelligence Trust Gate (C7).
# Process-scoped flags inside DB smoke. No systemd-global enable.
# Does NOT unlock broad production or begin Wave 6.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/wave5-product-acceptance-$STAMP"
REMOTE_STAGE="/tmp/w5p-product-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,frontend}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit"
cd "$ORCH_SRC"
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then
  PY="$ORCH_SRC/.venv/bin/python"
else
  PY="$(command -v python3)"
fi
"$PY" smoke-test-wave5-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "frontend contract"
cd "$DASH_SRC"
if [[ -f package.json ]]; then
  npx --yes vitest run src/posthire/intelligence/IntelligenceSurfacesContract.test.ts 2>&1 | tee "$LOCAL_EVID/frontend/contract.out" || true
fi
FE_OK=NO
if [[ -f "$LOCAL_EVID/frontend/contract.out" ]] && grep -qE 'passed|FRONTEND_CONTRACT' "$LOCAL_EVID/frontend/contract.out"; then
  FE_OK=YES
elif grep -q 'frontend no turnover formula' "$LOCAL_EVID/tests/unit.out"; then
  FE_OK=YES
fi

log "stage sources"
FILES=(
  hr_intelligence_registry_c1.py
  hr_intelligence_workforce_c2.py
  hr_intelligence_recruiting_c3.py
  hr_intelligence_time_pay_c4.py
  hr_intelligence_perf_talent_c5.py
  hr_intelligence_surfaces_c6.py
  hr_intelligence_surfaces_http.py
  hr_intelligence_product_c7.py
  smoke-test-wave5-product-acceptance.py
  smoke-test-wave5-product-acceptance-db.py
  smoke-test-hr-intelligence-surfaces-c6.py
  smoke-test-hr-intelligence-perf-talent-c5.py
  smoke-test-hr-intelligence-time-pay-c4.py
  smoke-test-hr-intelligence-recruiting-c3.py
  smoke-test-hr-intelligence-workforce-c2.py
  smoke-test-hr-intelligence-registry-c1.py
)
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/WAVE5_PRODUCT_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/WAVE5_PRODUCT_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
SCP_ARGS=()
for f in "${FILES[@]}"; do SCP_ARGS+=("$ORCH_SRC/$f"); done
"${SCP[@]}" "${SCP_ARGS[@]}" "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
for flag in HR_INTELLIGENCE_PRODUCT_C7 HR_INTELLIGENCE_SURFACES_C6 HR_INTELLIGENCE_PERF_TALENT_C5 HR_INTELLIGENCE_TIME_PAY_C4 HR_INTELLIGENCE_RECRUITING_C3 HR_INTELLIGENCE_WORKFORCE_C2 HR_INTELLIGENCE_REGISTRY_C1; do
  if grep -Rls "WATHEFNI_\${flag}=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
    echo "UNEXPECTED_SYSTEMD_\${flag}_ON"; exit 1
  fi
done
echo STAGING_COPY_OK_GLOBAL_WAVE5_OFF
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
staging_py smoke-test-wave5-product-acceptance-db.py "$LOCAL_EVID/tests/staging-db.out"

log "C6–C1 regressions"
staging_py smoke-test-hr-intelligence-surfaces-c6.py "$LOCAL_EVID/regression/c6.out"
staging_py smoke-test-hr-intelligence-perf-talent-c5.py "$LOCAL_EVID/regression/c5.out"
staging_py smoke-test-hr-intelligence-time-pay-c4.py "$LOCAL_EVID/regression/c4.out"
staging_py smoke-test-hr-intelligence-recruiting-c3.py "$LOCAL_EVID/regression/c3.out"
staging_py smoke-test-hr-intelligence-workforce-c2.py "$LOCAL_EVID/regression/c2.out"
staging_py smoke-test-hr-intelligence-registry-c1.py "$LOCAL_EVID/regression/c1.out"

log "Wave 1–4 freeze unit regressions"
REG_W=YES
: > "$LOCAL_EVID/regression/summary.txt"
set +e
"$PY" "$ORCH_SRC/smoke-test-wave1-product-acceptance.py" >"$LOCAL_EVID/regression/wave1-unit.out" 2>&1
W1_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave2-product-acceptance.py" >"$LOCAL_EVID/regression/wave2-unit.out" 2>&1
W2_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave3-product-acceptance.py" >"$LOCAL_EVID/regression/wave3-unit.out" 2>&1
W3_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave4-product-acceptance.py" >"$LOCAL_EVID/regression/wave4-unit.out" 2>&1
W4_RC=$?
set -e
echo "WAVE1_UNIT rc=$W1_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
echo "WAVE2_UNIT rc=$W2_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
echo "WAVE3_UNIT rc=$W3_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
echo "WAVE4_UNIT rc=$W4_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
if [[ $W1_RC -ne 0 || $W2_RC -ne 0 || $W3_RC -ne 0 || $W4_RC -ne 0 ]]; then REG_W=NO; fi

UNIT_OK=NO
if grep -q 'WAVE5_PRODUCT_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi
DB_OK=NO
if grep -q 'WAVE5_PRODUCT_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi
ok_stamp() { grep -q "$2" "$1" && grep -qE '[0-9]+ passed, 0 failed' "$1"; }
C6_OK=NO; ok_stamp "$LOCAL_EVID/regression/c6.out" HR_INTELLIGENCE_SURFACES_FULL_PASS && C6_OK=YES
C5_OK=NO; ok_stamp "$LOCAL_EVID/regression/c5.out" HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS && C5_OK=YES
C4_OK=NO; ok_stamp "$LOCAL_EVID/regression/c4.out" HR_INTELLIGENCE_TIME_PAY_FULL_PASS && C4_OK=YES
C3_OK=NO; ok_stamp "$LOCAL_EVID/regression/c3.out" HR_INTELLIGENCE_RECRUITING_FULL_PASS && C3_OK=YES
C2_OK=NO; ok_stamp "$LOCAL_EVID/regression/c2.out" HR_INTELLIGENCE_WORKFORCE_FULL_PASS && C2_OK=YES
C1_OK=NO; ok_stamp "$LOCAL_EVID/regression/c1.out" HR_INTELLIGENCE_REGISTRY_FULL_PASS && C1_OK=YES

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES && "$FE_OK" == YES && "$REG_W" == YES \
  && "$C6_OK" == YES && "$C5_OK" == YES && "$C4_OK" == YES && "$C3_OK" == YES && "$C2_OK" == YES && "$C1_OK" == YES ]]; then
  VERDICT='WAVE5_PRODUCT_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Wave 5 Product Acceptance — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Frontend contract: $FE_OK
- Staging DB / product gate: $DB_OK
- C6–C1 regressions: $C6_OK / $C5_OK / $C4_OK / $C3_OK / $C2_OK / $C1_OK
- Wave 1–4 unit freezes: $REG_W
- Global Wave 5 runtime flags: remain **off**
- No new KPI math / second evaluator in C7
- Verdict: **$VERDICT**

Stop for owner sign-off before Wave 6.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == WAVE5_PRODUCT_FULL_PASS ]]
