#!/usr/bin/env bash
# Payroll Wave 1 — staging qualification (local sync + staging migrate/smoke + sibling freezes).
# Does NOT deploy production. Does NOT enable payment_processing / money authority.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave1-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs"
printf '%s\n' "$EVID" > /tmp/payroll-w1.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w1.stamp
echo "evidence=$EVID"
echo "remote_orch=$REMOTE_ORCH"

cp -a "$ORCH/payroll_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-payroll-authority-wave1.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/payroll_authority_wave1_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-payroll-authority-wave1.py" "$EVID/tests/"
cp -a "$ORCH/tenant_control_roles.py" "$EVID/sources/"
cp -a "$ORCH/tool_call_orchestrator.py" "$EVID/sources/"
cp -a "$ORCH/smoke-test-multi-user-wave1-roles.py" "$EVID/tests/"

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/smoke-test-payroll-authority-wave1.py" \
  "$ORCH/tenant_control_roles.py" \
  "$ORCH/tool_call_orchestrator.py" \
  "$ORCH/smoke-test-multi-user-wave1-roles.py" \
  "$ORCH/app.py" \
  "$ORCH/shifts_notifications_wave6b.py" \
  "$ORCH/shifts_controlled_wave6c.py" \
  "$ORCH/shifts_enterprise_wave6.py" \
  "$ORCH/shifts_publish_wave5.py" \
  "$ORCH/shifts_templates_wave4.py" \
  "$ORCH/shifts_wave3_controlled.py" \
  "$ORCH/shifts_schedule_integrity_wave2.py" \
  "$ORCH/shifts_authority_wave1.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-payroll-authority-wave1.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
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
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-payroll-authority-wave1.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-payroll-authority-wave1.sh | tee /tmp/payroll-w1-migrate.out
"\$PY" smoke-test-payroll-authority-wave1.py | tee /tmp/payroll-w1-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w1-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
"\$PY" smoke-test-multi-user-wave1-roles.py | tee /tmp/payroll-w1-roles.out
echo STAGING_PAYROLL_W1_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w1-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w1-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w1-roles.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -20
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -20
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -20
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -20
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -20

# Gate summary
{
  echo "# Payroll Wave 1 staging qualify"
  echo "stamp=$STAMP"
  echo "evidence=$EVID"
  echo "payment_processing=disabled"
  echo "money_authority=false"
  echo "production_deploy=false"
} | tee "$EVID/docs/GATE.txt"

echo "QUALIFY_DONE evidence=$EVID"
