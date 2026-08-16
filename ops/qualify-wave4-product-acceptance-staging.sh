#!/usr/bin/env bash
# Wave 4 — Product Acceptance / modularity matrix (company-scoped canary).
# Process-scoped flags inside DB smoke. No systemd-global enable.
# Does NOT unlock Wave 5 analytics or reopen C1–C6 domain authority.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/wave4-product-acceptance-$STAMP"
REMOTE_STAGE="/tmp/w4p-product-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-wave4-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "stage sources"
cp -a \
  "$ORCH_SRC/setup_console_wave4_policies.py" \
  "$ORCH_SRC/smoke-test-wave4-product-acceptance.py" \
  "$ORCH_SRC/smoke-test-wave4-product-acceptance-db.py" \
  "$ORCH_SRC/performance_goals_c1.py" \
  "$ORCH_SRC/performance_reviews_c2.py" \
  "$ORCH_SRC/performance_feedback_c3.py" \
  "$ORCH_SRC/performance_calibration_c4.py" \
  "$ORCH_SRC/talent_profile_c5.py" \
  "$ORCH_SRC/talent_succession_c6.py" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/setup-console/Wave4PerformanceTalentPoliciesCard.tsx" "$LOCAL_EVID/sources/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/setup_console_wave4_policies.py" \
  "$ORCH_SRC/smoke-test-wave4-product-acceptance-db.py" \
  "$ORCH_SRC/performance_goals_c1.py" \
  "$ORCH_SRC/performance_reviews_c2.py" \
  "$ORCH_SRC/performance_feedback_c3.py" \
  "$ORCH_SRC/performance_calibration_c4.py" \
  "$ORCH_SRC/talent_profile_c5.py" \
  "$ORCH_SRC/talent_succession_c6.py" \
  "$ORCH_SRC/app.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "copy to staging orch (no global Wave4 enable)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
for flag in PERFORMANCE_GOALS_C1 PERFORMANCE_REVIEWS_C2 PERFORMANCE_FEEDBACK_C3 PERFORMANCE_CALIBRATION_C4 TALENT_PROFILE_C5 TALENT_SUCCESSION_C6 PERFORMANCE_TALENT_PRODUCT_C7 PERFORMANCE_KILL TALENT_KILL; do
  if grep -Rls "WATHEFNI_\${flag}=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
    echo "UNEXPECTED_SYSTEMD_WAVE4_ON \$flag"; exit 1
  fi
done
echo STAGING_COPY_OK_NO_GLOBAL_WAVE4_ENABLE
REMOTE

log "staging DB product acceptance prove"
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
"\$PYBIN" smoke-test-wave4-product-acceptance-db.py
echo STAGING_DB_RC=\$?
REMOTE

log "C1–C6 staging regression smokes"
REG_OK=YES
: > "$LOCAL_EVID/regression/summary.txt"
"${SCP[@]}" \
  "$ORCH_SRC/smoke-test-performance-goals-c1.py" \
  "$ORCH_SRC/smoke-test-performance-reviews-c2.py" \
  "$ORCH_SRC/smoke-test-performance-feedback-c3.py" \
  "$ORCH_SRC/smoke-test-performance-calibration-c4.py" \
  "$ORCH_SRC/smoke-test-talent-profile-c5.py" \
  "$ORCH_SRC/smoke-test-talent-succession-c6.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/regression/staging-c1-c6.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
cp -a '$REMOTE_STAGE'/*.py "\$STG/" 2>/dev/null || true
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
FAILS=0
for db in \
  smoke-test-performance-goals-c1.py \
  smoke-test-performance-reviews-c2.py \
  smoke-test-performance-feedback-c3.py \
  smoke-test-performance-calibration-c4.py \
  smoke-test-talent-profile-c5.py \
  smoke-test-talent-succession-c6.py
do
  echo "=== REG C \$db ==="
  if ! "\$PYBIN" "\$db"; then
    echo "REG_C_FAIL \$db"
    FAILS=\$((FAILS+1))
  fi
done
echo REG_C_FAILS=\$FAILS
test "\$FAILS" -eq 0
REMOTE
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
  REG_OK=NO
fi

log "Wave 1–3 freeze regression (unit)"
set +e
"$PY" "$ORCH_SRC/smoke-test-wave1-product-acceptance.py" >"$LOCAL_EVID/regression/wave1-unit.out" 2>&1
W1_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave2-product-acceptance.py" >"$LOCAL_EVID/regression/wave2-unit.out" 2>&1
W2_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave3-product-acceptance.py" >"$LOCAL_EVID/regression/wave3-unit.out" 2>&1
W3_RC=$?
set -e
echo "WAVE1_UNIT rc=$W1_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
echo "WAVE2_UNIT rc=$W2_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
echo "WAVE3_UNIT rc=$W3_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
if [[ $W1_RC -ne 0 || $W2_RC -ne 0 || $W3_RC -ne 0 ]]; then REG_OK=NO; fi
echo "REG_OK=$REG_OK" | tee -a "$LOCAL_EVID/regression/summary.txt"

UNIT_OK=NO
if grep -q 'WAVE4_PRODUCT_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi
DB_OK=NO
if grep -q 'WAVE4_PRODUCT_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES && "$REG_OK" == YES ]]; then
  VERDICT='WAVE4_PRODUCT_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Wave 4 Product Acceptance — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB / product gate: $DB_OK
- C1–C6 regression + Wave1/Wave2/Wave3 unit: $REG_OK
- Global Wave 4 runtime flags: remain **off**
- No new C1–C6 domain authority in C7
- Verdict: **$VERDICT**

Stop for owner sign-off before Wave 5.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != WAVE4_PRODUCT_FULL_PASS ]]; then
  exit 1
fi
exit 0
