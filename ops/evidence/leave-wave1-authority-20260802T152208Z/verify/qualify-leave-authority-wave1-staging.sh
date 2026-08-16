#!/usr/bin/env bash
# Leave Wave 1 — staging qualification (local sync + staging migrate/smoke + freeze regressions).
# Does NOT deploy production. Does NOT set enforced=true.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/leave-wave1-authority-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs"
printf '%s\n' "$EVID" > /tmp/leave-w1.evid
printf '%s\n' "$STAMP" > /tmp/leave-w1.stamp
echo "evidence=$EVID"
echo "remote_orch=$REMOTE_ORCH"

cp -a "$ORCH/leave_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-leave-authority-wave1.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/leave_authority_wave1_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-leave-authority-wave1.py" "$EVID/tests/"
cp -a "$ORCH/employee_lifecycle_wave3c.py" "$EVID/sources/"

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/leave_authority_wave1.py" \
  "$ORCH/smoke-test-leave-authority-wave1.py" \
  "$ORCH/employee_lifecycle_wave3c.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-leave-authority-wave1.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/leave_authority_wave1_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"

ssh -o BatchMode=yes "root@$HOST" \
  'systemctl restart wathefni-orchestrator-staging.service; sleep 3; systemctl is-active wathefni-orchestrator-staging.service; curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok'

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
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-leave-authority-wave1.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-leave-authority-wave1.sh | tee /tmp/leave-w1-migrate.out
"\$PY" smoke-test-leave-authority-wave1.py | tee /tmp/leave-w1-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/leave-w1-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
echo STAGING_LEAVE_W1_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/leave-w1-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/leave-w1-smoke.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -20
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -20
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -20

echo "QUALIFY_DONE evidence=$EVID"
