#!/usr/bin/env bash
# Wave 6 C1 — Job Architecture qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/job-architecture-c1-$STAMP"
REMOTE_STAGE="/tmp/job-architecture-c1-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,frontend}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"]="off"
os.environ["WATHEFNI_JOB_ARCHITECTURE_COMPANIES"]=""
import job_architecture_c1 as ja
import setup_console_wave6_policies as w6
assert ja.PASS_STAMP == "JOB_ARCHITECTURE_FULL_PASS"
assert ja.COMMERCIAL_SKU is False
assert ja.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert w6.honesty_payload().get("setup_owns_wave6_policies") is True
assert "job_architecture" in w6.WAVE6_MODULE_KEYS
h = ja.honesty_payload()
assert h["salary_bands_out_of_c1"] is True
assert h["no_fuzzy_ai_migration"] is True
assert h["career_edges_are_not_eligibility"] is True
src = open("job_architecture_c1.py").read().lower()
assert "create table" in src and "ja_grade" in src
assert "create table if not exists ja_salary" not in src
assert "create table if not exists salary_band" not in src
assert "salary_bands_out_of_c1" in src
print("LOCAL_GATES_OK")
PY

log "frontend setup card present"
python3 - <<'PY' 2>&1 | tee "$LOCAL_EVID/frontend/contract.out"
from pathlib import Path
root = Path("/Users/azizalmulla/Desktop/claw/apps/wathefni-dashboard/src/setup-console")
card = (root / "Wave6JobArchitecturePoliciesCard.tsx").read_text()
app = (root / "SetupConsoleApp.tsx").read_text()
assert "Wave6JobArchitecturePoliciesCard" in app
assert "wave6_job_architecture" in card
assert "salary" in card.lower() or "bands" in card.lower()
print("FRONTEND_SETUP_CARD_OK")
PY

log "stage sources"
FILES=(
  job_architecture_c1.py
  setup_console_wave6_policies.py
  smoke-test-job-architecture-c1.py
)
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/JOB_ARCHITECTURE_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/JOB_ARCHITECTURE_C1_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/job_architecture_c1.py" \
  "$ORCH_SRC/setup_console_wave6_policies.py" \
  "$ORCH_SRC/smoke-test-job-architecture-c1.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
# Setup wiring lives in app.py locally; DB smoke imports modules directly.
# Do not require a full app.py scp for C1 prove.
test -f "\$STG/job_architecture_c1.py"
test -f "\$STG/setup_console_wave6_policies.py"
if grep -Rls "WATHEFNI_JOB_ARCHITECTURE_C1=on" /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo "UNEXPECTED_SYSTEMD_JOB_ARCHITECTURE_ON"; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_JA_OFF
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
"\$PYBIN" smoke-test-job-architecture-c1.py
echo STAGING_RC=\$?
REMOTE

log "Wave 5 / Wave 4 freeze unit regressions"
REG_OK=YES
set +e
"$PY" "$ORCH_SRC/smoke-test-wave5-product-acceptance.py" >"$LOCAL_EVID/regression/wave5-unit.out" 2>&1
W5_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave4-product-acceptance.py" >"$LOCAL_EVID/regression/wave4-unit.out" 2>&1
W4_RC=$?
"$PY" "$ORCH_SRC/smoke-test-wave1-product-acceptance.py" >"$LOCAL_EVID/regression/wave1-unit.out" 2>&1
W1_RC=$?
set -e
echo "WAVE5_UNIT rc=$W5_RC" | tee "$LOCAL_EVID/regression/summary.txt"
echo "WAVE4_UNIT rc=$W4_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
echo "WAVE1_UNIT rc=$W1_RC" | tee -a "$LOCAL_EVID/regression/summary.txt"
if [[ $W5_RC -ne 0 || $W4_RC -ne 0 || $W1_RC -ne 0 ]]; then REG_OK=NO; fi

GATES_OK=NO; grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
FE_OK=NO; grep -q 'FRONTEND_SETUP_CARD_OK' "$LOCAL_EVID/frontend/contract.out" && FE_OK=YES
DB_OK=NO
if grep -q 'JOB_ARCHITECTURE_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$FE_OK" == YES && "$DB_OK" == YES && "$REG_OK" == YES ]]; then
  VERDICT='JOB_ARCHITECTURE_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Job Architecture C1 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Frontend Setup card: $FE_OK
- Staging DB: $DB_OK
- Wave5/Wave4/Wave1 unit freezes: $REG_OK
- Global Job Architecture flag: remains **off**
- Verdict: **$VERDICT**

Stop before C2 Learning & Development until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == JOB_ARCHITECTURE_FULL_PASS ]]
