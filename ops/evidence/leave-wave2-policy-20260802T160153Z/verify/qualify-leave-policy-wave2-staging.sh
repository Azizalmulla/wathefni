#!/usr/bin/env bash
# Leave Wave 2 — staging qualification (local sync + staging migrate/smoke + freeze regressions).
# Does NOT deploy production. Does NOT set enforced=true. Does NOT mutate prod balances.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/leave-wave2-policy-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs"
printf '%s\n' "$EVID" > /tmp/leave-w2.evid
printf '%s\n' "$STAMP" > /tmp/leave-w2.stamp
echo "evidence=$EVID"
echo "remote_orch=$REMOTE_ORCH"

cp -a "$ORCH/leave_policy_wave2.py" "$EVID/sources/"
cp -a "$ORCH/leave_authority_wave1.py" "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/employee_lifecycle_wave3c.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-leave-policy-wave2.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/leave_policy_wave2_v2.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-leave-policy-wave2.py" "$EVID/tests/"
cp -a "$ORCH/ops/qualify-leave-policy-wave2-staging.sh" "$EVID/verify/" 2>/dev/null || true

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/leave_policy_wave2.py" \
  "$ORCH/leave_authority_wave1.py" \
  "$ORCH/smoke-test-leave-policy-wave2.py" \
  "$ORCH/employee_lifecycle_wave3c.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-leave-policy-wave2.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/leave_policy_wave2_v2.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"

ssh -o BatchMode=yes "root@$HOST" \
  'systemctl restart wathefni-orchestrator-staging.service; for i in $(seq 1 30); do curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break; sleep 1; done; systemctl is-active wathefni-orchestrator-staging.service'

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
export WATHEFNI_LEAVE_BALANCES=on
export WATHEFNI_LEAVE_POLICY_WAVE2=on
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-leave-policy-wave2.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-leave-policy-wave2.sh | tee /tmp/leave-w2-migrate.out
"\$PY" smoke-test-leave-policy-wave2.py | tee /tmp/leave-w2-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/leave-w2-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
echo STAGING_LEAVE_W2_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/leave-w2-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/leave-w2-smoke.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -20
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -20
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -20

echo "QUALIFY_DONE evidence=$EVID"
