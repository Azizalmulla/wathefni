#!/usr/bin/env bash
# Leave Wave 3B — orchestrate stage → deploy → canary → rollback/redeploy → freezes (local driver).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
HOST="${PROD_HOST:-${STAGING_HOST:-76.13.63.68}}"
EVID="$ROOT/ops/evidence/leave-wave3b-prod-canary-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/leave-wave3b-prod-canary/${STAMP}"
STAGE=/tmp/leave-w3b-stage
BACKUP="/opt/wathefni/backups/production-pre-leave-wave3b-${STAMP}"

mkdir -p "$EVID"/{local,deploy,canary,verify,tests,docs,backup,sources,flags} "$STAGE"
printf '%s\n' "$EVID" > /tmp/leave-w3b.evid
printf '%s\n' "$STAMP" > /tmp/leave-w3b.stamp
echo "evidence=$EVID stamp=$STAMP"

# Stage files
cp -a "$ORCH/app.py" \
  "$ORCH/leave_workflow_wave3.py" \
  "$ORCH/leave_policy_wave2.py" \
  "$ORCH/leave_authority_wave1.py" \
  "$ORCH/employee_lifecycle_wave3c.py" \
  "$ORCH/canary-prod-leave-workflow-wave3b.py" \
  "$ORCH/ops/deploy-leave-workflow-wave3b-prod.sh" \
  "$ORCH/ops/migrate-leave-workflow-wave3b-prod.sh" \
  "$STAGE/"
cp -a "$STAGE/." "$EVID/sources/"
sha256sum "$STAGE"/* | tee "$EVID/local/stage-shas.txt"

# Upload stage + deploy script
scp -o BatchMode=yes -r "$STAGE" "root@$HOST:/tmp/leave-w3b-stage"
scp -o BatchMode=yes "$ORCH/ops/deploy-leave-workflow-wave3b-prod.sh" "root@$HOST:/tmp/deploy-leave-workflow-wave3b-prod.sh"

# Deploy
ssh -o BatchMode=yes "root@$HOST" \
  "chmod +x /tmp/deploy-leave-workflow-wave3b-prod.sh; STAMP=$STAMP STAGE_DIR=/tmp/leave-w3b-stage bash /tmp/deploy-leave-workflow-wave3b-prod.sh" \
  | tee "$EVID/deploy/deploy.log"
grep -q DEPLOY_OK "$EVID/deploy/deploy.log"

# Initial canary
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/canary/canary-run.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
cd "\$ORCH"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export LVW3B_EVID=$REMOTE_EVID/canary-run
mkdir -p "\$LVW3B_EVID"
.venv/bin/python canary-prod-leave-workflow-wave3b.py | tee $REMOTE_EVID/canary/canary-run.out
test "\$(python3 -c "import json;print(json.load(open('\$LVW3B_EVID/summary.json'))['fail'])")" = "0"
echo CANARY_OK
REMOTE

# Rollback + redeploy + canary
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/verify/rollback-redeploy.out"
set -euo pipefail
BACKUP=$BACKUP
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID=$REMOTE_EVID
STAGE=/tmp/leave-w3b-stage
STAMP=$STAMP
test -x "\$BACKUP/ROLLBACK.sh"
sha256sum \$ORCH/app.py \$ORCH/leave_workflow_wave3.py 2>/dev/null | tee \$REMOTE_EVID/verify/sha-before-rollback.txt || true
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP" | tee \$REMOTE_EVID/verify/rollback-execute.txt
curl -fsS http://127.0.0.1:8010/health >/dev/null
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
echo '=== flags after rollback ===' | tee \$REMOTE_EVID/verify/flags-after-rollback.txt
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'LEAVE_WORKFLOW_WAVE3|LEAVE_POLICY_WAVE2|LEAVE_AUTHORITY' | sort | tee -a \$REMOTE_EVID/verify/flags-after-rollback.txt || true
ls \$ORCH/leave_workflow_wave3.py 2>&1 | tee -a \$REMOTE_EVID/verify/flags-after-rollback.txt || true
# Redeploy
chmod +x /tmp/deploy-leave-workflow-wave3b-prod.sh
STAMP=${STAMP}-redeploy STAGE_DIR=\$STAGE bash /tmp/deploy-leave-workflow-wave3b-prod.sh | tee \$REMOTE_EVID/verify/redeploy.out
# Point drop-ins already set; run canary again
cd "\$ORCH"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export LVW3B_EVID=\$REMOTE_EVID/canary-post-redeploy
mkdir -p "\$LVW3B_EVID"
.venv/bin/python canary-prod-leave-workflow-wave3b.py | tee \$REMOTE_EVID/canary/canary-post-redeploy.out
test "\$(python3 -c "import json;print(json.load(open('\$LVW3B_EVID/summary.json'))['fail'])")" = "0"
systemctl is-enabled wathefni-leave-accrual.timer
systemctl is-active wathefni-leave-accrual.timer
echo ROLLBACK_REDEPLOY_OK
REMOTE

# Pull evidence
mkdir -p "$EVID/remote"
scp -o BatchMode=yes -r "root@$HOST:$REMOTE_EVID/." "$EVID/remote/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/ROLLBACK.sh" "$EVID/backup/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/SHA256SUMS" "$EVID/backup/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/leave-requests-fingerprint.csv" "$EVID/backup/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/leave-balances-fingerprint.csv" "$EVID/backup/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/leave-ledger-fingerprint.csv" "$EVID/backup/" || true

# Local freezes
cd "$ORCH"
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
.venv/bin/python smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5

echo "WAVE3B_PIPELINE_OK evidence=$EVID"
