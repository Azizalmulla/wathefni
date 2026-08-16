#!/usr/bin/env bash
# Payroll Wave 2A — staging qualification (external adapter foundation).
# Does NOT deploy production. Does NOT enable money / bank files / native G2N.
# Does NOT alter frozen Wave 1 contracts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave2a-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs"
printf '%s\n' "$EVID" > /tmp/payroll-w2a.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w2a.stamp
echo "evidence=$EVID"
echo "remote_orch=$REMOTE_ORCH"

cp -a "$ORCH/payroll_external_adapter_wave2a.py" "$EVID/sources/"
cp -a "$ORCH/payroll_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-payroll-external-adapter-wave2a.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" "$EVID/tests/"

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_external_adapter_wave2a.py" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-payroll-external-adapter-wave2a.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"
# Ensure Wave 1 SQL still present (dependency; unchanged)
rsync -az -e "ssh -o BatchMode=yes" \
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
chmod +x ops/migrate-payroll-external-adapter-wave2a.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-payroll-external-adapter-wave2a.sh | tee /tmp/payroll-w2a-migrate.out
"\$PY" smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/payroll-w2a-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2a-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
echo STAGING_PAYROLL_W2A_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-smoke.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -20
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -20
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -20
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -20
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -20

{
  echo "# Payroll Wave 2A staging qualify"
  echo "stamp=$STAMP"
  echo "evidence=$EVID"
  echo "payment_processing=disabled"
  echo "money_authority=external"
  echo "vendor_claimed=false"
  echo "wave1_contracts_unchanged=true"
  echo "production_deploy=false"
} | tee "$EVID/docs/GATE.txt"

echo "QUALIFY_DONE evidence=$EVID"
