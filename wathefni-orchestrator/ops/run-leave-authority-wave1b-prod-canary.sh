#!/usr/bin/env bash
# Local driver: stage → deploy Leave Wave 1B prod synthetic canary → prove → rollback/redeploy → freezes → REPORT.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
HOST="${STAGING_HOST:-76.13.63.68}"
EVID="$ROOT/ops/evidence/leave-wave1b-prod-canary-${STAMP}"
STAGE=/tmp/leave-w1b-stage
REMOTE_EVID="/opt/wathefni/production-evidence/leave-wave1b-prod-canary/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-leave-wave1b-${STAMP}"

mkdir -p "$EVID"/{preflight,deploy,canary,verify,backup,flags,tests,docs,sources} "$STAGE"
echo "$EVID" > /tmp/leave-w1b.evid
echo "$STAMP" > /tmp/leave-w1b.stamp
echo "evidence=$EVID stamp=$STAMP"

# Stage artifacts
cp -a "$ORCH/app.py" "$ORCH/leave_authority_wave1.py" "$ORCH/employee_lifecycle_wave3c.py" \
  "$ORCH/canary-prod-leave-authority-wave1b.py" \
  "$ORCH/smoke-test-leave-authority-wave1.py" \
  "$ORCH/smoke-test-employees360-freeze-regression.py" \
  "$ORCH/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH/smoke-test-attendance-freeze-regression.py" \
  "$STAGE/"
cp -a "$ORCH/ops/deploy-leave-authority-wave1b-prod.sh" "$ORCH/ops/migrate-leave-authority-wave1-prod.sh" "$STAGE/"
cp -a "$ORCH/ops/sql/leave_authority_wave1_v1.sql" "$STAGE/"
cp -a "$STAGE/." "$EVID/sources/" 2>/dev/null || true

rsync -az -e "ssh -o BatchMode=yes" "$STAGE/" "root@$HOST:$STAGE/"
scp -o BatchMode=yes "$ORCH/ops/deploy-leave-authority-wave1b-prod.sh" "root@$HOST:/tmp/deploy-leave-authority-wave1b-prod.sh"

# Deploy
ssh -o BatchMode=yes "root@$HOST" \
  "chmod +x /tmp/deploy-leave-authority-wave1b-prod.sh; STAMP=$STAMP STAGE_DIR=$STAGE bash /tmp/deploy-leave-authority-wave1b-prod.sh" \
  | tee "$EVID/deploy/deploy.out"

# Canary
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/canary/canary.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
cd "\$ORCH"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export LVW1B_EVID=$REMOTE_EVID/canary-run
mkdir -p "\$LVW1B_EVID"
.venv/bin/python canary-prod-leave-authority-wave1b.py | tee $REMOTE_EVID/canary/canary-run.out
grep -E '"fail": 0' $REMOTE_EVID/canary/canary-run.out || { echo CANARY_FAILED; exit 1; }
echo CANARY_OK
REMOTE

# Rollback proof then redeploy
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/verify/rollback-redeploy.out"
set -euo pipefail
BACKUP=$BACKUP
ORCH=/opt/wathefni/orchestrator
test -x "\$BACKUP/ROLLBACK.sh"
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
# After rollback, leave_authority module may be gone — confirm health
curl -fsS http://127.0.0.1:8010/health >/dev/null
# Confirm drop-in removed
if [[ -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzz-leave-authority-wave1b-synthetic.conf ]]; then
  echo 'WARN dropin still present after rollback'
fi
# Redeploy
STAMP=$STAMP STAGE_DIR=$STAGE bash /tmp/deploy-leave-authority-wave1b-prod.sh
# Re-run canary (new tag)
cd "\$ORCH"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export LVW1B_EVID=$REMOTE_EVID/canary-post-redeploy
mkdir -p "\$LVW1B_EVID"
.venv/bin/python canary-prod-leave-authority-wave1b.py | tee $REMOTE_EVID/canary/canary-post-redeploy.out
grep -E '"fail": 0' $REMOTE_EVID/canary/canary-post-redeploy.out
echo ROLLBACK_REDEPLOY_OK
REMOTE

# Pull remote evidence
mkdir -p "$EVID/remote"
scp -o BatchMode=yes -r "root@$HOST:$REMOTE_EVID/." "$EVID/remote/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/ROLLBACK.sh" "$EVID/backup/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/SHA256SUMS" "$EVID/backup/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/leave-requests-fingerprint.csv" "$EVID/backup/" || true

# Local freezes
cd "$ORCH"
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
.venv/bin/python smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5

echo "DRIVER_DONE evidence=$EVID"
