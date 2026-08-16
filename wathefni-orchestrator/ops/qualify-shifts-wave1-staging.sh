#!/usr/bin/env bash
# Shifts Wave 1A — staging qualification closure (lifecycle + dashboard dist + freezes).
# Does NOT deploy production. Does NOT build templates/recurring/publish.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/shifts-wave1a-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
REMOTE_DASH="${REMOTE_DASH:-/opt/wathefni/staging/dashboard-dist}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs" "$EVID/ui"
printf '%s\n' "$EVID" > /tmp/shifts-w1a.evid
printf '%s\n' "$STAMP" > /tmp/shifts-w1a.stamp
echo "evidence=$EVID"
echo "remote_orch=$REMOTE_ORCH"

cp -a "$ORCH/shifts_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-shifts-authority-wave1.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/shifts_authority_wave1_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-shifts-authority-wave1.py" "$EVID/tests/"

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/shifts_authority_wave1.py" \
  "$ORCH/smoke-test-shifts-authority-wave1.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-shifts-authority-wave1.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/shifts_authority_wave1_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"

# Rebuild + qualify dashboard distribution (staging only)
if [[ -d "$ROOT/apps/wathefni-dashboard" ]]; then
  mkdir -p "$EVID/sources/dashboard"
  cp -a "$ROOT/apps/wathefni-dashboard/src/lib/api.ts" "$EVID/sources/dashboard/" 2>/dev/null || true
  cp -a "$ROOT/apps/wathefni-dashboard/src/types.ts" "$EVID/sources/dashboard/" 2>/dev/null || true
  cp -a "$ROOT/apps/wathefni-dashboard/src/posthire/PostHire.tsx" "$EVID/sources/dashboard/" 2>/dev/null || true
  (
    cd "$ROOT/apps/wathefni-dashboard"
    npm run build 2>&1 | tee "$EVID/ui/dashboard-build.out"
    test -d dist
    # Prove concurrency token is in the built client
    if grep -R -l "expected_updated_at" dist/assets --include='*.js' >/dev/null 2>&1; then
      echo "DASHBOARD_DIST_HAS_expected_updated_at=yes" | tee "$EVID/ui/concurrency-token.txt"
      grep -R -l "expected_updated_at" dist/assets --include='*.js' | head -5 | tee -a "$EVID/ui/concurrency-token.txt"
    else
      echo "DASHBOARD_DIST_HAS_expected_updated_at=no" | tee "$EVID/ui/concurrency-token.txt"
      exit 1
    fi
    ssh -o BatchMode=yes "root@$HOST" "mkdir -p ${REMOTE_DASH}.bak-shifts-w1a-$STAMP && rsync -a $REMOTE_DASH/ ${REMOTE_DASH}.bak-shifts-w1a-$STAMP/ || true"
    rsync -az --delete -e "ssh -o BatchMode=yes" dist/ "root@$HOST:$REMOTE_DASH/"
    ssh -o BatchMode=yes "root@$HOST" "grep -R -l expected_updated_at $REMOTE_DASH/assets --include='*.js' | head -3" | tee "$EVID/ui/remote-dist-token.out"
  )
fi

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
export WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
export WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=0
export WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
export WATHEFNI_SHIFTS_LEAVE_CONFLICT_MODE=require_ack
export WATHEFNI_DASHBOARD_DIST="$REMOTE_DASH"
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-shifts-authority-wave1.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-shifts-authority-wave1.sh | tee /tmp/shifts-w1a-migrate.out
export PYTHONUNBUFFERED=1
"\$PY" -u smoke-test-shifts-authority-wave1.py | tee /tmp/shifts-w1a-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/shifts-w1a-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
echo STAGING_SHIFTS_W1A_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/shifts-w1a-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/shifts-w1a-smoke.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -30
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -30
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -30
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -30

echo "QUALIFY_DONE evidence=$EVID"
