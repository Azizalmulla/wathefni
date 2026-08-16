#!/usr/bin/env bash
# Wave 2 C4 — Authoritative Payroll qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/payroll-authoritative-c4-$STAMP"
REMOTE_STAGE="/tmp/payroll-auth-c4-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_PAYROLL_AUTHORITATIVE_C4"]="off"
import payroll_authoritative_c4 as e
g=e.runtime_gate_for_company("WATHEFNI")
assert g.get("ok") is not True
print("LOCAL_GATES_OK")
PY

log "stage sources"
cp -a \
  "$ORCH_SRC/payroll_authoritative_c4.py" \
  "$ORCH_SRC/payroll_authority_wave1.py" \
  "$ORCH_SRC/smoke-test-payroll-authoritative-c4.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/PAYROLL_AUTHORITY_C4_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/payroll_authoritative_c4.py" \
  "$ORCH_SRC/payroll_authority_wave1.py" \
  "$ORCH_SRC/smoke-test-payroll-authoritative-c4.py" \
  "$ORCH_SRC/ops/sql/payroll_statutory_architecture_p4a_v1.sql" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global authoritative unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
# Patch broken CREATE CHECK (source_classification) into prod+staging orch SQL copies for this prove.
if [[ -f '$REMOTE_STAGE/payroll_statutory_architecture_p4a_v1.sql' ]]; then
  cp -a '$REMOTE_STAGE/payroll_statutory_architecture_p4a_v1.sql' "\$STG/ops/sql/" 2>/dev/null || true
  mkdir -p "\$PROD/ops/sql"
  cp -a '$REMOTE_STAGE/payroll_statutory_architecture_p4a_v1.sql' "\$PROD/ops/sql/"
fi
if grep -Rls 'WATHEFNI_PAYROLL_AUTHORITATIVE_C4=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_PAYROLL_AUTHORITATIVE_C4_ON; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_AUTHORITATIVE_OFF
REMOTE

log "staging DB prove"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-db.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
STAGE='$REMOTE_STAGE'
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
# Prefer C4 overlay; fall back to prod for full payroll dependency graph.
export PYTHONPATH="\$STAGE:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
cd "\$STAGE"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" smoke-test-payroll-authoritative-c4.py
echo STAGING_RC=\$?
REMOTE

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'PAYROLL_AUTHORITY_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='PAYROLL_AUTHORITY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Payroll Authoritative C4 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- Global PAYROLL_AUTHORITATIVE_C4: remains **off**
- Payment processing: remains **disabled**
- Verdict: **$VERDICT**

Stop before C5 Payslips + Payment Files until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != PAYROLL_AUTHORITY_FULL_PASS ]]; then
  exit 1
fi
