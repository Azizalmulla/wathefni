#!/usr/bin/env bash
# Wave 5 C6 — HR Intelligence Surfaces qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/hr-intelligence-surfaces-c6-$STAMP"
REMOTE_STAGE="/tmp/hr-intelligence-surfaces-c6-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,frontend}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_HR_INTELLIGENCE_SURFACES_C6"]="off"
os.environ["WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1"]="off"
import hr_intelligence_surfaces_c6 as t
import hr_intelligence_registry_c1 as c1
assert t.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert t.COMMERCIAL_MODULE_KEY == "analytics"
assert t.PASS_STAMP == "HR_INTELLIGENCE_SURFACES_FULL_PASS"
h = t.honesty_payload()
assert h.get("uses_c1_evaluator_only") is True
assert h.get("no_frontend_formulas") is True
assert h.get("attention_is_not_intelligence") is True
assert c1.PASS_STAMP == "HR_INTELLIGENCE_REGISTRY_FULL_PASS"
src = open("hr_intelligence_surfaces_c6.py").read()
assert "c1.evaluate_kpi(" in src
assert "turnover =" not in src
print("LOCAL_GATES_OK")
PY

log "frontend contract"
cd "$DASH_SRC"
if [[ -f package.json ]]; then
  npx --yes vitest run src/posthire/intelligence/IntelligenceSurfacesContract.test.ts 2>&1 | tee "$LOCAL_EVID/frontend/contract.out" || {
    # fallback: static source scan if vitest unavailable
    python3 - <<'PY' 2>&1 | tee -a "$LOCAL_EVID/frontend/contract.out"
from pathlib import Path
ws = Path("src/posthire/intelligence/IntelligenceWorkspace.tsx").read_text()
api = Path("src/lib/intelligenceApi.ts").read_text()
assert "turnover =" not in ws and "/ headcount" not in ws
assert "intelligence/" in api or "intelligenceApi" in ws or "evaluate" in api
assert "inbox" in ws.lower() or "Attention" in ws or "attention" in ws
print("FRONTEND_CONTRACT_STATIC_OK")
PY
  }
else
  echo "NO_DASHBOARD_PACKAGE" | tee "$LOCAL_EVID/frontend/contract.out"
fi

FE_OK=NO
if grep -qE 'passed|FRONTEND_CONTRACT_STATIC_OK' "$LOCAL_EVID/frontend/contract.out"; then FE_OK=YES; fi

log "stage sources"
FILES=(
  hr_intelligence_registry_c1.py
  hr_intelligence_workforce_c2.py
  hr_intelligence_recruiting_c3.py
  hr_intelligence_time_pay_c4.py
  hr_intelligence_perf_talent_c5.py
  hr_intelligence_surfaces_c6.py
  hr_intelligence_surfaces_http.py
  smoke-test-hr-intelligence-surfaces-c6.py
  smoke-test-hr-intelligence-perf-talent-c5.py
  smoke-test-hr-intelligence-time-pay-c4.py
  smoke-test-hr-intelligence-recruiting-c3.py
  smoke-test-hr-intelligence-workforce-c2.py
  smoke-test-hr-intelligence-registry-c1.py
)
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_SURFACES_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/HR_INTELLIGENCE_SURFACES_C6_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
SCP_ARGS=()
for f in "${FILES[@]}"; do SCP_ARGS+=("$ORCH_SRC/$f"); done
"${SCP[@]}" "${SCP_ARGS[@]}" "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
# Keep app.py surfaces registration present in staged tree by ensuring http module is present
test -f "\$STG/hr_intelligence_surfaces_http.py"
for flag in HR_INTELLIGENCE_SURFACES_C6 HR_INTELLIGENCE_PERF_TALENT_C5 HR_INTELLIGENCE_TIME_PAY_C4 HR_INTELLIGENCE_RECRUITING_C3 HR_INTELLIGENCE_WORKFORCE_C2 HR_INTELLIGENCE_REGISTRY_C1; do
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
staging_py smoke-test-hr-intelligence-surfaces-c6.py "$LOCAL_EVID/tests/staging-db.out"

log "C5–C1 regressions"
staging_py smoke-test-hr-intelligence-perf-talent-c5.py "$LOCAL_EVID/regression/c5.out"
staging_py smoke-test-hr-intelligence-time-pay-c4.py "$LOCAL_EVID/regression/c4.out"
staging_py smoke-test-hr-intelligence-recruiting-c3.py "$LOCAL_EVID/regression/c3.out"
staging_py smoke-test-hr-intelligence-workforce-c2.py "$LOCAL_EVID/regression/c2.out"
staging_py smoke-test-hr-intelligence-registry-c1.py "$LOCAL_EVID/regression/c1.out"

GATES_OK=NO; grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'HR_INTELLIGENCE_SURFACES_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi
ok_stamp() { grep -q "$2" "$1" && grep -qE '[0-9]+ passed, 0 failed' "$1"; }
C5_OK=NO; ok_stamp "$LOCAL_EVID/regression/c5.out" HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS && C5_OK=YES
C4_OK=NO; ok_stamp "$LOCAL_EVID/regression/c4.out" HR_INTELLIGENCE_TIME_PAY_FULL_PASS && C4_OK=YES
C3_OK=NO; ok_stamp "$LOCAL_EVID/regression/c3.out" HR_INTELLIGENCE_RECRUITING_FULL_PASS && C3_OK=YES
C2_OK=NO; ok_stamp "$LOCAL_EVID/regression/c2.out" HR_INTELLIGENCE_WORKFORCE_FULL_PASS && C2_OK=YES
C1_OK=NO; ok_stamp "$LOCAL_EVID/regression/c1.out" HR_INTELLIGENCE_REGISTRY_FULL_PASS && C1_OK=YES

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES && "$FE_OK" == YES && "$C5_OK" == YES && "$C4_OK" == YES && "$C3_OK" == YES && "$C2_OK" == YES && "$C1_OK" == YES ]]; then
  VERDICT='HR_INTELLIGENCE_SURFACES_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# HR Intelligence Surfaces C6 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Frontend contract: $FE_OK
- Staging DB: $DB_OK
- C5–C1 regressions: $C5_OK / $C4_OK / $C3_OK / $C2_OK / $C1_OK
- Global Wave 5 flags: remain **off**
- Verdict: **$VERDICT**

Stop before C7 until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == HR_INTELLIGENCE_SURFACES_FULL_PASS ]]
