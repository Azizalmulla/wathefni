#!/usr/bin/env bash
# Wave 2 C5 — Payslips + Payment Files qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/payroll-payslip-payment-c5-$STAMP"
REMOTE_STAGE="/tmp/payroll-payslip-c5-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_PAYROLL_PAYMENT_C5"]="off"
import payroll_payslip_payment_c5 as e
g=e.runtime_gate_for_company("WATHEFNI")
assert g.get("ok") is not True
assert e.honesty_payload().get("acknowledged_is_not_paid") is True
assert e.honesty_payload().get("transfers_funds") is False
print("LOCAL_GATES_OK")
PY

log "stage sources"
cp -a \
  "$ORCH_SRC/payroll_payslip_payment_c5.py" \
  "$ORCH_SRC/payroll_authoritative_c4.py" \
  "$ORCH_SRC/smoke-test-payroll-payslip-payment-c5.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/PAYSLIP_PAYMENT_C5_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/payroll_payslip_payment_c5.py" \
  "$ORCH_SRC/payroll_authoritative_c4.py" \
  "$ORCH_SRC/smoke-test-payroll-payslip-payment-c5.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global payment unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
if grep -Rls 'WATHEFNI_PAYROLL_PAYMENT_C5=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_PAYROLL_PAYMENT_C5_ON; exit 1
fi
if grep -Rls 'WATHEFNI_PAYROLL_PAYMENT_KILL=off' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null \
  && grep -Rls 'WATHEFNI_PAYROLL_PAYMENT_C5=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_PAYMENT_UNLOCK; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_PAYMENT_C5_OFF
REMOTE

log "staging DB prove"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-db.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
STAGE='$REMOTE_STAGE'
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
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
"\$PYBIN" smoke-test-payroll-payslip-payment-c5.py
echo STAGING_RC=\$?
REMOTE

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'PAYSLIP_PAYMENT_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='PAYSLIP_PAYMENT_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Payslip + Payment Files C5 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- Global PAYROLL_PAYMENT_C5: remains **off**
- Wave1 payment_processing column: remains **disabled**
- Acknowledged ≠ paid
- Verdict: **$VERDICT**

Stop before C6 Final Settlement + OT until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != PAYSLIP_PAYMENT_FULL_PASS ]]; then
  exit 1
fi
exit 0
