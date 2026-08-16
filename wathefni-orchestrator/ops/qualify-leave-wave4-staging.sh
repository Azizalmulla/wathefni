#!/usr/bin/env bash
# Leave Wave 4 — staging qualification (sync + migrate/smoke + freezes). Not production.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/leave-wave4-staging-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID"/{sources,migrate,tests,remote,verify,docs,ui}
printf '%s\n' "$EVID" > /tmp/leave-w4.evid
printf '%s\n' "$STAMP" > /tmp/leave-w4.stamp
echo "evidence=$EVID"

cp -a "$ORCH/leave_wave4_controlled.py" "$EVID/sources/"
cp -a "$ORCH/leave_workflow_wave3.py" "$EVID/sources/"
cp -a "$ORCH/smoke-test-leave-wave4-ux.py" "$EVID/tests/"
cp -a "$ORCH/smoke-test-leave-freeze-regression.py" "$EVID/tests/"
cp -a "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" "$EVID/docs/"
cp -a "$ROOT/.cursor/rules/leave-freeze.mdc" "$EVID/docs/"

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/leave_wave4_controlled.py" \
  "$ORCH/leave_workflow_wave3.py" \
  "$ORCH/leave_policy_wave2.py" \
  "$ORCH/leave_authority_wave1.py" \
  "$ORCH/action_registry.py" \
  "$ORCH/smoke-test-leave-wave4-ux.py" \
  "$ORCH/smoke-test-leave-freeze-regression.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops /opt/wathefni/ops"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "root@$HOST:/opt/wathefni/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/.cursor/rules/leave-freeze.mdc" \
  "root@$HOST:/opt/wathefni/ops/"

# Staging flags for wave4 (drop-in under staging service if present)
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<'REMOTE_FLAGS'
set -euo pipefail
DROP=/etc/systemd/system/wathefni-orchestrator-staging.service.d
mkdir -p "$DROP"
cat > "$DROP/zzzz-leave-wave4.conf" <<EOF
[Service]
Environment=WATHEFNI_LEAVE_WAVE4=on
Environment=WATHEFNI_LEAVE_REAL_DECISION_GATE=on
Environment=WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST=96599338566,96588009911
Environment=WATHEFNI_LEAVE_WORKFLOW_WAVE3=on
Environment=WATHEFNI_LEAVE_POLICY_WAVE2=on
Environment=WATHEFNI_LEAVE_BALANCES=on
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in $(seq 1 40); do curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break; sleep 1; done
systemctl is-active wathefni-orchestrator-staging.service
REMOTE_FLAGS

ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/remote/migrate-smoke.out"
set -euo pipefail
ORCH="$REMOTE_ORCH"
cd "\$ORCH"
set -a
source "$POSTGRES_ENV"
set +a
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV="$POSTGRES_ENV"
export WATHEFNI_EXPECTED_DATABASE_NAME="$ACK_DB_DEFAULT"
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_LEAVE_BALANCES=on
export WATHEFNI_LEAVE_POLICY_WAVE2=on
export WATHEFNI_LEAVE_WORKFLOW_WAVE3=on
export WATHEFNI_LEAVE_WAVE4=on
export WATHEFNI_LEAVE_REAL_DECISION_GATE=on
export WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST=96599338566,96588009911
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
"\$PY" - <<'PY'
import app, leave_wave4_controlled as w4, leave_workflow_wave3 as w3, leave_authority_wave1 as w1, leave_policy_wave2 as w2
with app.db_connect() as conn:
    with conn.cursor() as cur:
        w1.ensure_leave_authority_wave1_schema(cur)
        w2.ensure_leave_policy_wave2_schema(cur)
        w3.ensure_leave_workflow_wave3_schema(cur)
        w4.ensure_leave_wave4_schema(cur)
        cur.execute("UPDATE leave_policies SET enforced=false, legal_reviewed=false WHERE company_code='WATHEFNI'")
    conn.commit()
print('MIGRATE_OK_STAGING_W4', w4.LEAVE_WAVE4_VERSION)
PY
"\$PY" smoke-test-leave-wave4-ux.py | tee /tmp/leave-w4-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/leave-w4-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
"\$PY" smoke-test-leave-freeze-regression.py | tee /tmp/leave-w4-freeze.out
if grep -E '[1-9][0-9]* failed' /tmp/leave-w4-freeze.out; then
  echo FREEZE_SMOKE_FAILED
  exit 1
fi
echo STAGING_LEAVE_W4_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/leave-w4-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/leave-w4-freeze.out" "$EVID/tests/" 2>/dev/null || true

# Optional dashboard dist sync for LeaveWorkspace (staging only)
if [[ -d "$ROOT/apps/wathefni-dashboard" ]]; then
  (
    cd "$ROOT/apps/wathefni-dashboard"
    if [[ -f package.json ]]; then
      npm run build 2>&1 | tee "$EVID/ui/dashboard-build.out" | tail -30
      ssh -o BatchMode=yes "root@$HOST" "mkdir -p /opt/wathefni/staging/dashboard-dist.bak-leave-w4-$STAMP && rsync -a /opt/wathefni/staging/dashboard-dist/ /opt/wathefni/staging/dashboard-dist.bak-leave-w4-$STAMP/ || true"
      rsync -az --delete -e "ssh -o BatchMode=yes" dist/ "root@$HOST:/opt/wathefni/staging/dashboard-dist/"
      ssh -o BatchMode=yes "root@$HOST" 'grep -o "LeaveWorkspace\|balancesBanner\|non-binding\|غير ملزم" /opt/wathefni/staging/dashboard-dist/assets/*.js 2>/dev/null | head -10 || true'
    fi
  ) || echo "UI_BUILD_SKIPPED"
fi

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -30
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -10
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -10
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -10

echo "QUALIFY_DONE evidence=$EVID"
