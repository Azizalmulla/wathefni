#!/usr/bin/env bash
# Shifts Wave 2 — staging qualification (schedule integrity).
# Local/staging only. Does NOT deploy production. Does NOT enable real-employee mutations.
# Does NOT build templates/recurring/rotations/publishing/open shifts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/shifts-wave2-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
REMOTE_DASH="${REMOTE_DASH:-/opt/wathefni/staging/dashboard-dist}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs"
printf '%s\n' "$EVID" > /tmp/shifts-w2.evid
printf '%s\n' "$STAMP" > /tmp/shifts-w2.stamp
echo "evidence=$EVID"
echo "remote_orch=$REMOTE_ORCH"

cp -a "$ORCH/shifts_schedule_integrity_wave2.py" "$EVID/sources/"
cp -a "$ORCH/shifts_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-shifts-schedule-integrity-wave2.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/shifts_schedule_integrity_wave2_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-shifts-schedule-integrity-wave2.py" "$EVID/tests/"
cp -a "$ORCH/smoke-test-shifts-authority-wave1.py" "$EVID/tests/"

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/shifts_schedule_integrity_wave2.py" \
  "$ORCH/shifts_authority_wave1.py" \
  "$ORCH/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH/smoke-test-shifts-authority-wave1.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-shifts-schedule-integrity-wave2.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/shifts_schedule_integrity_wave2_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"

ssh -o BatchMode=yes "root@$HOST" \
  'systemctl restart wathefni-orchestrator-staging.service; for i in $(seq 1 40); do curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break; sleep 1; done; systemctl is-active wathefni-orchestrator-staging.service'

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
export WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
export WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=0
export WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
export WATHEFNI_SHIFTS_LEAVE_CONFLICT_MODE=require_ack
export WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
export WATHEFNI_DASHBOARD_DIST="$REMOTE_DASH"
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-shifts-schedule-integrity-wave2.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-shifts-schedule-integrity-wave2.sh | tee /tmp/shifts-w2-migrate.out
export PYTHONUNBUFFERED=1
"\$PY" -u smoke-test-shifts-schedule-integrity-wave2.py | tee /tmp/shifts-w2-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/shifts-w2-smoke.out; then
  echo SMOKE_W2_FAILED
  exit 1
fi
"\$PY" -u smoke-test-shifts-authority-wave1.py | tee /tmp/shifts-w1-regress.out
if grep -E '[1-9][0-9]* failed' /tmp/shifts-w1-regress.out; then
  echo SMOKE_W1_REGRESS_FAILED
  exit 1
fi
echo STAGING_SHIFTS_W2_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/shifts-w2-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/shifts-w2-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/shifts-w1-regress.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -30
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -30
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -30
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -30

echo "QUALIFY_DONE evidence=$EVID"
