#!/usr/bin/env bash
# Wave 5 C4 — Time / Leave / Payroll Intelligence qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/hr-intelligence-time-pay-c4-$STAMP"
REMOTE_STAGE="/tmp/hr-intelligence-time-pay-c4-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4"]="off"
os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"]="off"
import hr_intelligence_time_pay_c4 as t
import hr_intelligence_registry_c1 as c1
assert t.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert t.COMMERCIAL_MODULE_KEY == "analytics"
assert t.PASS_STAMP == "HR_INTELLIGENCE_TIME_PAY_FULL_PASS"
assert t.honesty_payload().get("uses_c1_registry_evaluator") is True
assert t.honesty_payload().get("sealed_payroll_required") is True
assert t.honesty_payload().get("approved_leave_is_not_absenteeism") is True
assert t.honesty_payload().get("fx_conversion") is False
assert len(t.ALL_SEMANTIC_KEYS) == 18
assert c1.PASS_STAMP == "HR_INTELLIGENCE_REGISTRY_FULL_PASS"
print("LOCAL_GATES_OK")
PY

log "stage sources"
cp -a \
  "$ORCH_SRC/hr_intelligence_registry_c1.py" \
  "$ORCH_SRC/hr_intelligence_workforce_c2.py" \
  "$ORCH_SRC/hr_intelligence_recruiting_c3.py" \
  "$ORCH_SRC/hr_intelligence_time_pay_c4.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-time-pay-c4.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-recruiting-c3.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-workforce-c2.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-registry-c1.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_TIME_PAY_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_TIME_PAY_C4_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/hr_intelligence_registry_c1.py" \
  "$ORCH_SRC/hr_intelligence_workforce_c2.py" \
  "$ORCH_SRC/hr_intelligence_recruiting_c3.py" \
  "$ORCH_SRC/hr_intelligence_time_pay_c4.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-time-pay-c4.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-recruiting-c3.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-workforce-c2.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-registry-c1.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
for flag in HR_INTELLIGENCE_TIME_PAY_C4 HR_INTELLIGENCE_RECRUITING_C3 HR_INTELLIGENCE_WORKFORCE_C2 HR_INTELLIGENCE_REGISTRY_C1; do
  if grep -Rls "WATHEFNI_\${flag}=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
    echo "UNEXPECTED_SYSTEMD_\${flag}_ON"; exit 1
  fi
done
echo STAGING_COPY_OK_GLOBAL_HR_INTELLIGENCE_OFF
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

log "staging DB prove"
staging_py smoke-test-hr-intelligence-time-pay-c4.py "$LOCAL_EVID/tests/staging-db.out"

log "C3 regression smoke"
staging_py smoke-test-hr-intelligence-recruiting-c3.py "$LOCAL_EVID/regression/c3.out"

log "C2 regression smoke"
staging_py smoke-test-hr-intelligence-workforce-c2.py "$LOCAL_EVID/regression/c2.out"

log "C1 regression smoke"
staging_py smoke-test-hr-intelligence-registry-c1.py "$LOCAL_EVID/regression/c1.out"

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'HR_INTELLIGENCE_TIME_PAY_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi
C3_OK=NO
if grep -q 'HR_INTELLIGENCE_RECRUITING_FULL_PASS' "$LOCAL_EVID/regression/c3.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/regression/c3.out"; then
  C3_OK=YES
fi
C2_OK=NO
if grep -q 'HR_INTELLIGENCE_WORKFORCE_FULL_PASS' "$LOCAL_EVID/regression/c2.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/regression/c2.out"; then
  C2_OK=YES
fi
C1_OK=NO
if grep -q 'HR_INTELLIGENCE_REGISTRY_FULL_PASS' "$LOCAL_EVID/regression/c1.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/regression/c1.out"; then
  C1_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES && "$C3_OK" == YES && "$C2_OK" == YES && "$C1_OK" == YES ]]; then
  VERDICT='HR_INTELLIGENCE_TIME_PAY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# HR Intelligence Time/Pay C4 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- C3 regression: $C3_OK
- C2 regression: $C2_OK
- C1 regression: $C1_OK
- Global Wave 5 flags: remain **off**
- Verdict: **$VERDICT**

Stop before C5 until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != HR_INTELLIGENCE_TIME_PAY_FULL_PASS ]]; then
  exit 1
fi
exit 0
