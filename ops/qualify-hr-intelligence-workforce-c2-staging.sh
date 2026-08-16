#!/usr/bin/env bash
# Wave 5 C2 — Workforce Intelligence qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/hr-intelligence-workforce-c2-$STAMP"
REMOTE_STAGE="/tmp/hr-intelligence-workforce-c2-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_HR_INTELLIGENCE_WORKFORCE_C2"]="off"
os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"]="off"
import hr_intelligence_workforce_c2 as t
import hr_intelligence_registry_c1 as c1
assert t.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert t.COMMERCIAL_MODULE_KEY == "analytics"
assert t.PASS_STAMP == "HR_INTELLIGENCE_WORKFORCE_FULL_PASS"
assert t.honesty_payload().get("uses_c1_registry_evaluator") is True
assert t.honesty_payload().get("fte_remains_blocked") is True
assert t.honesty_payload().get("turnover_not_exits_over_current_hc") is True
assert c1.PASS_STAMP == "HR_INTELLIGENCE_REGISTRY_FULL_PASS"
assert callable(c1.register_formula_handler)
print("LOCAL_GATES_OK")
PY

log "stage sources"
cp -a \
  "$ORCH_SRC/hr_intelligence_registry_c1.py" \
  "$ORCH_SRC/hr_intelligence_workforce_c2.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-workforce-c2.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-registry-c1.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_WORKFORCE_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_WORKFORCE_C2_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/hr_intelligence_registry_c1.py" \
  "$ORCH_SRC/hr_intelligence_workforce_c2.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-workforce-c2.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-registry-c1.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
for flag in HR_INTELLIGENCE_WORKFORCE_C2 HR_INTELLIGENCE_REGISTRY_C1; do
  if grep -Rls "WATHEFNI_\${flag}=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
    echo "UNEXPECTED_SYSTEMD_\${flag}_ON"; exit 1
  fi
done
echo STAGING_COPY_OK_GLOBAL_HR_INTELLIGENCE_OFF
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
"\$PYBIN" smoke-test-hr-intelligence-workforce-c2.py
echo STAGING_RC=\$?
REMOTE

log "C1 regression smoke"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/regression/c1.out"
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
"\$PYBIN" smoke-test-hr-intelligence-registry-c1.py
REMOTE

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'HR_INTELLIGENCE_WORKFORCE_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi
C1_OK=NO
if grep -q 'HR_INTELLIGENCE_REGISTRY_FULL_PASS' "$LOCAL_EVID/regression/c1.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/regression/c1.out"; then
  C1_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES && "$C1_OK" == YES ]]; then
  VERDICT='HR_INTELLIGENCE_WORKFORCE_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# HR Intelligence Workforce C2 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- C1 regression: $C1_OK
- Global Wave 5 flags: remain **off**
- Verdict: **$VERDICT**

Stop before C3 until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != HR_INTELLIGENCE_WORKFORCE_FULL_PASS ]]; then
  exit 1
fi
exit 0
