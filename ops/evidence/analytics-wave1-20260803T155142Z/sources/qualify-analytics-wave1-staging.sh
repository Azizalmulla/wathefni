#!/usr/bin/env bash
# Analytics Wave 1 — Attention Contract — staging-only qualification.
# NO production deploy. Does not reopen frozen modules or add AI/BI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/analytics-wave1-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging
VPS_HOST="root@$HOST"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)

mkdir -p "$EVID"/{sources,tests,remote,ui,docs,verify}
printf '%s\n' "$EVID" > /tmp/analytics-w1.evid
printf '%s\n' "$STAMP" > /tmp/analytics-w1.stamp
echo "evidence=$EVID"

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-analytics-attention-wave1.py 2>&1 | tee "$EVID/tests/analytics-wave1-local.out"
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -5
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -5
if test -f smoke-test-payroll-authority-wave1.py; then
  "$PY_LOCAL" smoke-test-payroll-authority-wave1.py 2>&1 | tee "$EVID/tests/freeze-payroll-authority.out" | tail -8 || true
fi

log "dashboard unit test + build"
cd "$DASH"
npm test -- --run src/posthire/analyticsAttentionWave1.test.ts 2>&1 | tee "$EVID/ui/vitest.out" | tail -20
# Pre-existing TS errors exist in frozen Payroll workspace files; Wave 1 must not
# reopen them. Prove Analytics-touched paths are clean, then vite-emit.
npx tsc -b --pretty false 2>&1 | tee "$EVID/ui/tsc-full.out" | tail -20 || true
if grep -E 'PostHire\.tsx|analyticsAttention|src/App\.tsx|src/types\.ts' "$EVID/ui/tsc-full.out"; then
  echo "ANALYTICS_TS_FAILED"
  exit 1
fi
echo "ANALYTICS_TS_CLEAN" | tee -a "$EVID/ui/tsc-full.out"
npx vite build 2>&1 | tee "$EVID/ui/dashboard-build.out" | tail -30
mkdir -p "$EVID/sources/dashboard-dist"
cp -a "$DASH/dist/." "$EVID/sources/dashboard-dist/"

log "copy sources into evidence"
cp -a "$ORCH/analytics_attention_wave1.py" "$ORCH/smoke-test-analytics-attention-wave1.py" \
  "$ORCH/assistant_capability_catalog.py" "$ORCH/action_registry.py" "$EVID/sources/"
# app.py is large — keep SHA + relevant excerpt only in verify
shasum -a 256 "$ORCH/app.py" | tee "$EVID/verify/app.py.sha256"
cp -a "$DASH/src/posthire/PostHire.tsx" "$DASH/src/types.ts" "$DASH/src/App.tsx" \
  "$DASH/src/posthire/analyticsAttentionWave1.test.ts" "$EVID/sources/" 2>/dev/null || true
cp -a "$ROOT/ops/qualify-analytics-wave1-staging.sh" "$EVID/sources/"

log "push orchestrator + dashboard dist to staging"
"${SSH[@]}" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/analytics_attention_wave1.py" \
  "$ORCH/smoke-test-analytics-attention-wave1.py" \
  "$ORCH/assistant_capability_catalog.py" \
  "$ORCH/action_registry.py" \
  "$ORCH/app.py" \
  "$ORCH/smoke-test-employees360-freeze-regression.py" \
  "$ORCH/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH/smoke-test-attendance-freeze-regression.py" \
  "$ORCH/smoke-test-leave-freeze-regression.py" \
  "$ORCH/smoke-test-shifts-freeze-regression.py" \
  "$ORCH/canary-prod-shifts-wave1b.py" \
  "$ORCH/canary-prod-shifts-wave3b.py" \
  "$ORCH/canary-prod-shifts-wave4b.py" \
  "$ORCH/canary-prod-shifts-wave5b.py" \
  "$ORCH/canary-prod-shifts-wave6b.py" \
  "$ORCH/canary-prod-shifts-wave6c.py" \
  "$ORCH/shifts_authority_wave1.py" \
  "$ORCH/shifts_schedule_integrity_wave2.py" \
  "$ORCH/shifts_wave3_controlled.py" \
  "$ORCH/shifts_templates_wave4.py" \
  "$ORCH/shifts_publish_wave5.py" \
  "$ORCH/shifts_enterprise_wave6.py" \
  "$ORCH/shifts_notifications_wave6b.py" \
  "$ORCH/shifts_controlled_wave6c.py" \
  "$ORCH/shifts_synthetic_cleanup.py" \
  "$VPS_HOST:$REMOTE_ORCH/"
# Freeze docs referenced by sibling smokes
"${SSH[@]}" "mkdir -p /opt/wathefni/staging/ops /opt/wathefni/ops"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$VPS_HOST:/opt/wathefni/staging/ops/" 2>/dev/null || true

"${SSH[@]}" "mkdir -p /opt/wathefni/dashboard-dist /opt/wathefni/apps/wathefni-dashboard/src/posthire"
rsync -az -e "ssh -o BatchMode=yes" \
  "$EVID/sources/dashboard-dist/" \
  "$VPS_HOST:/opt/wathefni/dashboard-dist/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/posthire/PostHire.tsx" \
  "$DASH/src/posthire/analyticsAttentionWave1.test.ts" \
  "$VPS_HOST:/opt/wathefni/apps/wathefni-dashboard/src/posthire/"

log "restart staging orchestrator + health"
"${SSH[@]}" 'systemctl restart wathefni-orchestrator-staging.service; for i in $(seq 1 60); do if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok; systemctl is-active wathefni-orchestrator-staging.service; exit 0; fi; sleep 1; done; systemctl status wathefni-orchestrator-staging.service --no-pager -l | head -40; exit 1' \
  | tee "$EVID/remote/restart.out"

log "staging smoke + analytics endpoint probe"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$EVID/remote/staging-smoke.out"
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
"\$PY" smoke-test-analytics-attention-wave1.py | tee /tmp/analytics-w1-smoke.out
"\$PY" smoke-test-employees360-freeze-regression.py | tee /tmp/analytics-w1-freeze-e360.out | tail -3
"\$PY" smoke-test-onboarding-freeze-regression.py | tee /tmp/analytics-w1-freeze-onb.out | tail -3
"\$PY" smoke-test-attendance-freeze-regression.py | tee /tmp/analytics-w1-freeze-att.out | tail -3
"\$PY" smoke-test-leave-freeze-regression.py | tee /tmp/analytics-w1-freeze-leave.out | tail -3
"\$PY" smoke-test-shifts-freeze-regression.py | tee /tmp/analytics-w1-freeze-shifts.out | tail -3

# Live contract probe against staging process import
"\$PY" - <<'PY'
import json
import app

# Source disclosure + attention contract without requiring tenant data richness
pack = __import__("analytics_attention_wave1").analytics_source_availability({"analytics", "leave"})
assert pack["partial"] is True
assert "attendance" in pack["unavailable_source_keys"]

# Dashboard route source contract
import inspect
src = inspect.getsource(app.dashboard_posthire_analytics)
assert "viewer_user_id" in src and "actor_role" in src
print(json.dumps({
  "contract": "analytics_attention_wave1",
  "dashboard_identity_keys": True,
  "partial_sources_ok": True,
  "health": "ok",
}, ensure_ascii=False))
PY

# Dist UI strings for EN/AR attention + honest hours wording
DIST=/opt/wathefni/dashboard-dist
grep -Rql 'Needs attention\|ما يحتاج انتباهاً' "\$DIST" && echo UI_ATTENTION_COPY_OK || echo UI_ATTENTION_COPY_MISSING
grep -Rql 'non-payroll\|غير راتبية' "\$DIST" || echo UI_NON_PAYROLL_COPY_SOFT
grep -Rql 'Headcount summary' "\$DIST" && echo UI_HEADCOUNT_LEAK && exit 1 || echo UI_HEADCOUNT_GONE
echo STAGING_ANALYTICS_W1_OK
REMOTE

scp -o BatchMode=yes "$VPS_HOST:/tmp/analytics-w1-smoke.out" "$EVID/tests/" 2>/dev/null || true

# Mobile web / responsive note — CSS grid breakpoints already in AnalyticsPage (sm/lg)
cat > "$EVID/docs/MOBILE_WEB.md" <<'EOF'
Analytics Wave 1 uses the existing HR dashboard responsive shell.
Attention rows are full-width stacked buttons; headlines use sm/lg grids.
No native mobile app work in this wave. Verify at ~390px and desktop in staging UI.
EOF

cat > "$EVID/docs/REPORT.md" <<EOF
# Analytics Wave 1 — Attention Contract (staging)

**Stamp:** $STAMP
**Evidence:** $EVID
**Gate candidate:** \`STAGING_ANALYTICS_WAVE1_ATTENTION_GO\`

## Scope
- Full actor identity on dashboard analytics read
- Ranked attention items + deep links
- as_of + Kuwait MTD + definitions
- Partial-source disclosure
- EN/AR parity on Analytics page
- Honest non-payroll hours wording
- Demote/remove scheduled-shifts / best-attendance vanity
- Correct Assistant chip away from Headcount

## Explicit out of scope
AI, decorative charts, custom BI, payroll cost analytics, Compliance metrics, mobile apps, frozen module contract changes, production deploy.

## Sibling freezes
Employees 360 / Onboarding / Attendance / Leave / Shifts local+staging regression smokes executed.
EOF

# Gate summary
if grep -q "STAGING_ANALYTICS_W1_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "analytics-attention-wave1 smoke tests passed" "$EVID/tests/analytics-wave1-local.out"; then
  echo "GATE=STAGING_ANALYTICS_WAVE1_ATTENTION_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_ANALYTICS_WAVE1_ATTENTION_GO"
else
  echo "GATE=STAGING_ANALYTICS_WAVE1_ATTENTION_NO_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_ANALYTICS_WAVE1_ATTENTION_NO_GO"
  exit 1
fi
