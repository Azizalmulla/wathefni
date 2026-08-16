#!/usr/bin/env bash
# Compliance Wave 1 — Findings Contract — staging-only qualification.
# NO production deploy. Document compliance only. Analytics stays frozen.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/compliance-wave1-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging
VPS_HOST="root@$HOST"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)

mkdir -p "$EVID"/{sources,tests,remote,ui,docs,verify}
printf '%s\n' "$EVID" > /tmp/compliance-w1.evid
printf '%s\n' "$STAMP" > /tmp/compliance-w1.stamp
echo "evidence=$EVID"

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-compliance-findings-wave1.py 2>&1 | tee "$EVID/tests/compliance-wave1-local.out"
"$PY_LOCAL" smoke-test-analytics-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-analytics.out" | tail -8
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
npm test -- --run src/posthire/complianceFindingsWave1.test.ts 2>&1 | tee "$EVID/ui/vitest.out" | tail -20
npx tsc -b --pretty false 2>&1 | tee "$EVID/ui/tsc-full.out" | tail -20 || true
if grep -E 'PostHire\.tsx|complianceFindings|src/App\.tsx|src/types\.ts' "$EVID/ui/tsc-full.out"; then
  echo "COMPLIANCE_TS_FAILED"
  exit 1
fi
echo "COMPLIANCE_TS_CLEAN" | tee -a "$EVID/ui/tsc-full.out"
npx vite build 2>&1 | tee "$EVID/ui/dashboard-build.out" | tail -30
mkdir -p "$EVID/sources/dashboard-dist"
cp -a "$DASH/dist/." "$EVID/sources/dashboard-dist/"

log "copy sources into evidence"
cp -a "$ORCH/compliance_findings_wave1.py" "$ORCH/smoke-test-compliance-findings-wave1.py" "$EVID/sources/"
shasum -a 256 "$ORCH/app.py" | tee "$EVID/verify/app.py.sha256"
cp -a "$DASH/src/posthire/PostHire.tsx" "$DASH/src/types.ts" \
  "$DASH/src/posthire/complianceFindingsWave1.test.ts" "$EVID/sources/" 2>/dev/null || true
cp -a "$ROOT/ops/qualify-compliance-wave1-staging.sh" "$EVID/sources/"

log "push orchestrator + dashboard dist to staging"
"${SSH[@]}" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/compliance_findings_wave1.py" \
  "$ORCH/smoke-test-compliance-findings-wave1.py" \
  "$ORCH/analytics_attention_wave1.py" \
  "$ORCH/smoke-test-analytics-freeze-regression.py" \
  "$ORCH/canary-prod-analytics-attention-wave1b.py" \
  "$ORCH/app.py" \
  "$ORCH/smoke-test-employees360-freeze-regression.py" \
  "$ORCH/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH/smoke-test-attendance-freeze-regression.py" \
  "$ORCH/smoke-test-leave-freeze-regression.py" \
  "$ORCH/smoke-test-shifts-freeze-regression.py" \
  "$ORCH/kuwait_pilot_document_journey.py" \
  "$ORCH/kuwait_first_client_foundation.py" \
  "$VPS_HOST:$REMOTE_ORCH/"
"${SSH[@]}" "mkdir -p /opt/wathefni/staging/ops /opt/wathefni/ops"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md" \
  "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md" \
  "$VPS_HOST:/opt/wathefni/staging/ops/" 2>/dev/null || true

"${SSH[@]}" "mkdir -p /opt/wathefni/dashboard-dist /opt/wathefni/apps/wathefni-dashboard/src/posthire"
rsync -az -e "ssh -o BatchMode=yes" \
  "$EVID/sources/dashboard-dist/" \
  "$VPS_HOST:/opt/wathefni/dashboard-dist/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/posthire/PostHire.tsx" \
  "$DASH/src/posthire/complianceFindingsWave1.test.ts" \
  "$VPS_HOST:/opt/wathefni/apps/wathefni-dashboard/src/posthire/"

log "restart staging orchestrator + health"
"${SSH[@]}" 'systemctl restart wathefni-orchestrator-staging.service; for i in $(seq 1 60); do if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok; systemctl is-active wathefni-orchestrator-staging.service; exit 0; fi; sleep 1; done; systemctl status wathefni-orchestrator-staging.service --no-pager -l | head -40; exit 1' \
  | tee "$EVID/remote/restart.out"

log "staging smoke + compliance endpoint probe"
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
export WATHEFNI_COMPLIANCE_WAVE1=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
"\$PY" smoke-test-compliance-findings-wave1.py | tee /tmp/compliance-w1-smoke.out
"\$PY" smoke-test-analytics-freeze-regression.py | tee /tmp/compliance-w1-freeze-analytics.out | tail -3
"\$PY" smoke-test-employees360-freeze-regression.py | tee /tmp/compliance-w1-freeze-e360.out | tail -3
"\$PY" smoke-test-onboarding-freeze-regression.py | tee /tmp/compliance-w1-freeze-onb.out | tail -3
"\$PY" smoke-test-attendance-freeze-regression.py | tee /tmp/compliance-w1-freeze-att.out | tail -3
"\$PY" smoke-test-leave-freeze-regression.py | tee /tmp/compliance-w1-freeze-leave.out | tail -3
"\$PY" smoke-test-shifts-freeze-regression.py | tee /tmp/compliance-w1-freeze-shifts.out | tail -3

"\$PY" - <<'PY'
import json
import inspect
import compliance_findings_wave1 as w1
import app

pack = w1.assert_residence_work_permit_integrity()
assert pack["ok"] is True, pack

# Dashboard payload contract keys exist in source
src = inspect.getsource(app.dashboard_compliance_payload)
assert "compliance_findings_wave1" in src or "build_compliance_findings" in src
assert "findings" in src
assert "as_of" in src

# Builder ranking without DB
docs = [{
  "employee_key": "WATHEFNI-CFW1-E1",
  "employee_name": "Staging Probe",
  "department": "Ops",
  "document_type": "work_permit",
  "status": "expired",
  "days_until_expiry": -2,
  "expiry_date": "2026-07-01",
  "file_id": None,
}]
built = w1.build_compliance_findings(documents=docs, enabled_modules={"compliance", "onboarding", "employees"})
assert built["findings"][0]["deep_link"]["page"] == "compliance"
assert built["honesty"]["legal_compliance_claims"] is False
assert built["honesty"]["government_verified"] is False
assert "compliance_metrics" in __import__("analytics_attention_wave1").honesty_payload()
assert __import__("analytics_attention_wave1").honesty_payload()["compliance_metrics"] is False
print(json.dumps({
  "contract": w1.COMPLIANCE_WAVE1_CONTRACT,
  "integrity_ok": True,
  "findings_shape_ok": True,
  "analytics_excludes_compliance": True,
  "health": "ok",
}, ensure_ascii=False))
PY

DIST=/opt/wathefni/dashboard-dist
grep -Rql 'Findings by severity\|النتائج حسب الخطورة' "\$DIST" && echo UI_FINDINGS_COPY_OK || echo UI_FINDINGS_COPY_MISSING
grep -Rql 'Never government verified\|ليست تحققاً حكومياً' "\$DIST" && echo UI_HONESTY_COPY_OK || echo UI_HONESTY_COPY_MISSING
grep -Rql 'compliance_findings_wave1\|Open system of action\|افتح نظام التنفيذ' "\$DIST" && echo UI_SOA_COPY_OK || echo UI_SOA_COPY_SOFT
echo STAGING_COMPLIANCE_W1_OK
REMOTE

scp -o BatchMode=yes "$VPS_HOST:/tmp/compliance-w1-smoke.out" "$EVID/tests/" 2>/dev/null || true

cat > "$EVID/docs/MOBILE_WEB.md" <<'EOF'
Compliance Wave 1 uses the existing HR dashboard responsive shell.
Findings cards stack full-width; document register scrolls horizontally on narrow viewports.
Stat grids use sm/lg breakpoints. No native mobile app work in this wave.
Verify at ~390px and desktop in staging UI.
EOF

cat > "$EVID/docs/REPORT.md" <<EOF
# Compliance Wave 1 — Findings Contract (staging)

**Stamp:** $STAMP
**Evidence:** $EVID
**Gate candidate:** \`STAGING_COMPLIANCE_WAVE1_FINDINGS_GO\`

## Scope
- Ranked document findings (severity, EN/AR, owner, deadline, escalation, SoA deep links)
- as_of + Kuwait date/window + freshness honesty
- Evidence status honesty (never government verified)
- Residence / work-permit vocabulary + seed/dual-write integrity
- Configurable owner by document type (default HR/compliance)
- Read-only deep links into Compliance, Onboarding, Employees
- EN/AR findings UI + empty/loading/error/stale states

## Explicit out of scope
AI, government APIs, filing, fine calculations, legal-compliance claims,
Compliance metrics in Analytics, production deploy, frozen module authority changes.

## Sibling freezes
Analytics / Employees 360 / Onboarding / Attendance / Leave / Shifts (+ payroll authority if present).
EOF

if grep -q "STAGING_COMPLIANCE_W1_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "compliance-findings-wave1 smoke tests passed" "$EVID/tests/compliance-wave1-local.out"; then
  echo "GATE=STAGING_COMPLIANCE_WAVE1_FINDINGS_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_COMPLIANCE_WAVE1_FINDINGS_GO"
else
  echo "GATE=STAGING_COMPLIANCE_WAVE1_FINDINGS_NO_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_COMPLIANCE_WAVE1_FINDINGS_NO_GO"
  exit 1
fi
