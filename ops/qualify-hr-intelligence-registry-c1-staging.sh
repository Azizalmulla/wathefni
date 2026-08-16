#!/usr/bin/env bash
# Wave 5 C1 — KPI Registry + Intelligence spine qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/hr-intelligence-registry-c1-$STAMP"
REMOTE_STAGE="/tmp/hr-intelligence-registry-c1-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"]="off"
import hr_intelligence_registry_c1 as t
assert t.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert t.COMMERCIAL_MODULE_KEY == "analytics"
assert t.INTERNAL_NAMESPACE == "hr_intelligence"
assert t.PASS_STAMP == "HR_INTELLIGENCE_REGISTRY_FULL_PASS"
assert t.honesty_payload().get("registry_is_authority") is True
assert t.honesty_payload().get("no_duplicate_commercial_module") is True
assert t.honesty_payload().get("assistant_mutations") is False
assert t.honesty_payload().get("min_cohort_n_default") == 5
assert t.honesty_payload().get("min_cohort_n_upward_only") is True
assert t.honesty_payload().get("fte_blocked_until_authoritative_inputs") is True
assert t.honesty_payload().get("pending_start_excluded_from_headcount") is True
assert t.HEADCOUNT_POLICY["contingent_mixed_into_employee_headcount"] is False
assert t.HEADCOUNT_POLICY["fte_publishable"] is False
print("LOCAL_GATES_OK")
PY

log "stage sources"
cp -a \
  "$ORCH_SRC/hr_intelligence_registry_c1.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-registry-c1.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_REGISTRY_C1_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_REGISTRY_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/hr_intelligence_registry_c1.py" \
  "$ORCH_SRC/smoke-test-hr-intelligence-registry-c1.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global intelligence unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
if grep -Rls 'WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_HR_INTELLIGENCE_REGISTRY_C1_ON; exit 1
fi
if grep -Rls 'WATHEFNI_ANALYTICS_KILL=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_ANALYTICS_KILL_ON; exit 1
fi
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
"\$PYBIN" smoke-test-hr-intelligence-registry-c1.py
echo STAGING_RC=\$?
REMOTE

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'HR_INTELLIGENCE_REGISTRY_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='HR_INTELLIGENCE_REGISTRY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# HR Intelligence Registry C1 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- Global HR_INTELLIGENCE_REGISTRY_C1: remains **off**
- Verdict: **$VERDICT**

Stop before C2 until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != HR_INTELLIGENCE_REGISTRY_FULL_PASS ]]; then
  exit 1
fi
exit 0
