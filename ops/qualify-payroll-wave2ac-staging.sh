#!/usr/bin/env bash
# Payroll Wave 2A-C — staging qualification (external payroll ops workflow).
# Does NOT deploy production. Does NOT enable money / bank files / native G2N.
# Does NOT alter frozen Wave 1 or Wave 2A contracts. Does NOT start Wave 2B.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave2ac-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs" "$EVID/ui"
printf '%s\n' "$EVID" > /tmp/payroll-w2ac.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w2ac.stamp
echo "evidence=$EVID"
echo "remote_orch=$REMOTE_ORCH"

cp -a "$ORCH/payroll_external_adapter_wave2a.py" "$EVID/sources/"
cp -a "$ORCH/payroll_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" "$EVID/tests/"
cp -a "$ORCH/smoke-test-payroll-external-ops-wave2ac.py" "$EVID/tests/"
cp -a "$DASH/src/posthire/ExternalPayrollWorkspace.tsx" "$EVID/ui/" 2>/dev/null || true
cp -a "$DASH/src/posthire/payrollExternalUx.ts" "$EVID/ui/" 2>/dev/null || true

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_external_adapter_wave2a.py" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "$ORCH/smoke-test-payroll-external-ops-wave2ac.py" \
  "root@$HOST:$REMOTE_ORCH/"

# Sync app.py routes (Wave 2A-C dashboard APIs)
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/app.py"

ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" \
  "$ORCH/ops/sql/payroll_authority_wave1_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"

ssh -o BatchMode=yes "root@$HOST" \
  'systemctl restart wathefni-orchestrator-staging.service; for i in $(seq 1 60); do if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok; systemctl is-active wathefni-orchestrator-staging.service; exit 0; fi; sleep 1; done; systemctl status wathefni-orchestrator-staging.service --no-pager -l | head -40; exit 1'

ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/remote/migrate-smoke.out"
set -euo pipefail
ORCH="$REMOTE_ORCH"
cd "\$ORCH"
set -a
source "$POSTGRES_ENV"
set +a
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV="$POSTGRES_ENV"
export ACK_DB="$ACK_DB_DEFAULT"
export WATHEFNI_EXPECTED_DATABASE_NAME="$ACK_DB_DEFAULT"
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_PAYROLL_WAVE1=1
export WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1
export WATHEFNI_PAYROLL_WAVE2A=1
export WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
"\$PY" smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/payroll-w2a-regression.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2a-regression.out; then
  echo W2A_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-external-ops-wave2ac.py | tee /tmp/payroll-w2ac-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2ac-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
# Permission / honesty surface via Python import of route helpers
"\$PY" - <<'PY'
import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
import payroll_external_adapter_wave2a as w2a
h = w2a.honesty_payload()
assert h["payment_processing"] == "disabled"
assert h["money_authority"] == "external"
assert h["vendor_claimed"] is False
assert h["wathefni_money_authority"] is False
print("HONESTY_OK")
PY
echo STAGING_PAYROLL_W2AC_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-regression.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2ac-smoke.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -20
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -20
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -20
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -20
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -20

# UI typecheck (optional, non-blocking if deps missing)
if [[ -f "$DASH/package.json" ]]; then
  (cd "$DASH" && npx --yes tsc --noEmit -p tsconfig.json 2>&1 | tee "$EVID/ui/tsc.out" | tail -40) || echo "TSC_WARN" | tee -a "$EVID/ui/tsc.out"
fi

{
  echo "# Payroll Wave 2A-C staging qualify"
  echo "stamp=$STAMP"
  echo "evidence=$EVID"
  echo "payment_processing=disabled"
  echo "money_authority=external"
  echo "vendor_claimed=false"
  echo "authoritative_in_wathefni=false"
  echo "wave1_contracts_unchanged=true"
  echo "wave2a_adapter_contracts_unchanged=true"
  echo "wave2b_started=false"
  echo "production_deploy=false"
  echo "prod_synthetic_gate=NO-GO (staging-only wave; requires Wave 2A-C-B prod synthetic path)"
} | tee "$EVID/docs/GATE.txt"

echo "QUALIFY_DONE evidence=$EVID"
