#!/usr/bin/env bash
# Leave Wave 4 — orchestrate stage → deploy → canary → rollback/redeploy → freezes.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
HOST="${PROD_HOST:-${STAGING_HOST:-76.13.63.68}}"
EVID="$ROOT/ops/evidence/leave-wave4-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/leave-wave4/${STAMP}"
STAGE=/tmp/leave-w4-stage
BACKUP="/opt/wathefni/backups/production-pre-leave-wave4-${STAMP}"

mkdir -p "$EVID"/{local,deploy,canary,verify,tests,docs,backup,sources,flags} "$STAGE"
printf '%s\n' "$EVID" > /tmp/leave-w4-prod.evid
printf '%s\n' "$STAMP" > /tmp/leave-w4-prod.stamp
echo "evidence=$EVID stamp=$STAMP"

cp -a "$ORCH/app.py" \
  "$ORCH/leave_wave4_controlled.py" \
  "$ORCH/leave_workflow_wave3.py" \
  "$ORCH/leave_policy_wave2.py" \
  "$ORCH/leave_authority_wave1.py" \
  "$ORCH/employee_lifecycle_wave3c.py" \
  "$ORCH/action_registry.py" \
  "$ORCH/canary-prod-leave-wave4.py" \
  "$ORCH/smoke-test-leave-freeze-regression.py" \
  "$ORCH/ops/deploy-leave-wave4-prod.sh" \
  "$ORCH/ops/migrate-leave-wave4-prod.sh" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/.cursor/rules/leave-freeze.mdc" \
  "$STAGE/"
cp -a "$STAGE/." "$EVID/sources/"
sha256sum "$STAGE"/* | tee "$EVID/local/stage-shas.txt"

scp -o BatchMode=yes -r "$STAGE" "root@$HOST:/tmp/leave-w4-stage"
scp -o BatchMode=yes "$ORCH/ops/deploy-leave-wave4-prod.sh" "root@$HOST:/tmp/deploy-leave-wave4-prod.sh"

ssh -o BatchMode=yes "root@$HOST" \
  "chmod +x /tmp/deploy-leave-wave4-prod.sh; STAMP=$STAMP STAGE_DIR=/tmp/leave-w4-stage LEAVE_REAL_DECISION_ALLOWLIST=96599338566,96588009911 bash /tmp/deploy-leave-wave4-prod.sh" \
  | tee "$EVID/deploy/deploy.log"
grep -q DEPLOY_OK "$EVID/deploy/deploy.log"

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
export LVW4_EVID=$REMOTE_EVID/canary-run
mkdir -p "\$LVW4_EVID"
.venv/bin/python canary-prod-leave-wave4.py | tee $REMOTE_EVID/canary/canary-run.out
test "\$(python3 -c "import json;print(json.load(open('\$LVW4_EVID/summary.json'))['fail'])")" = "0"
echo CANARY_OK
REMOTE

ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/verify/rollback-redeploy.out"
set -euo pipefail
BACKUP=$BACKUP
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID=$REMOTE_EVID
STAGE=/tmp/leave-w4-stage
STAMP=$STAMP
test -x "\$BACKUP/ROLLBACK.sh"
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP" | tee \$REMOTE_EVID/verify/rollback-execute.txt
curl -fsS http://127.0.0.1:8010/health >/dev/null
chmod +x /tmp/deploy-leave-wave4-prod.sh
STAMP=${STAMP}-redeploy STAGE_DIR=\$STAGE LEAVE_REAL_DECISION_ALLOWLIST=96599338566,96588009911 bash /tmp/deploy-leave-wave4-prod.sh | tee \$REMOTE_EVID/verify/redeploy.out
cd "\$ORCH"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export LVW4_EVID=\$REMOTE_EVID/canary-post-redeploy
mkdir -p "\$LVW4_EVID"
# Stale leave already resolved on first canary — canary treats expired_stale as pass
.venv/bin/python canary-prod-leave-wave4.py | tee \$REMOTE_EVID/canary/canary-post-redeploy.out
test "\$(python3 -c "import json;print(json.load(open('\$LVW4_EVID/summary.json'))['fail'])")" = "0"
systemctl is-enabled wathefni-leave-accrual.timer
systemctl is-active wathefni-leave-accrual.timer
echo ROLLBACK_REDEPLOY_OK
REMOTE

mkdir -p "$EVID/remote"
scp -o BatchMode=yes -r "root@$HOST:$REMOTE_EVID/." "$EVID/remote/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/ROLLBACK.sh" "$EVID/backup/" || true
scp -o BatchMode=yes "root@$HOST:$BACKUP/SHA256SUMS" "$EVID/backup/" || true

cd "$ORCH"
.venv/bin/python smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -20
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
.venv/bin/python smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5

echo "WAVE4_PIPELINE_OK evidence=$EVID"
