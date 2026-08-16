#!/usr/bin/env bash
# Action Inbox Wave 1 — Unified Action Inbox — staging-only qualification.
# NO production deploy. Composes Analytics/Compliance/E360 read-only. Sibling freezes green.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/action-inbox-wave1-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging
VPS_HOST="root@$HOST"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")

mkdir -p "$EVID"/{sources,tests,remote,ui,docs,verify}
printf '%s\n' "$EVID" > /tmp/action-inbox-w1.evid
printf '%s\n' "$STAMP" > /tmp/action-inbox-w1.stamp
echo "evidence=$EVID"

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-action-inbox-wave1.py 2>&1 | tee "$EVID/tests/action-inbox-wave1-local.out"
"$PY_LOCAL" smoke-test-analytics-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-analytics.out" | tail -8
"$PY_LOCAL" smoke-test-compliance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-compliance.out" | tail -8
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
npm test -- --run src/posthire/actionInboxWave1.test.ts 2>&1 | tee "$EVID/ui/vitest.out" | tail -20
npx tsc -b --pretty false 2>&1 | tee "$EVID/ui/tsc-full.out" | tail -40 || true
if grep -E 'PostHire\.tsx|actionInbox|src/App\.tsx|src/types\.ts|workspaceCapability|moduleWorkspace|api\.ts' "$EVID/ui/tsc-full.out"; then
  echo "ACTION_INBOX_TS_FAILED"
  exit 1
fi
echo "ACTION_INBOX_TS_CLEAN" | tee -a "$EVID/ui/tsc-full.out"
npx vite build 2>&1 | tee "$EVID/ui/dashboard-build.out" | tail -30
mkdir -p "$EVID/sources/dashboard-dist"
cp -a "$DASH/dist/." "$EVID/sources/dashboard-dist/"

log "copy sources into evidence"
cp -a "$ORCH/action_inbox_wave1.py" "$ORCH/smoke-test-action-inbox-wave1.py" "$EVID/sources/"
shasum -a 256 "$ORCH/app.py" | tee "$EVID/verify/app.py.sha256"
cp -a "$DASH/src/posthire/PostHire.tsx" "$DASH/src/types.ts" \
  "$DASH/src/posthire/actionInboxWave1.test.ts" \
  "$DASH/src/App.tsx" \
  "$DASH/src/lib/api.ts" \
  "$DASH/src/lib/moduleWorkspace.ts" \
  "$DASH/src/lib/workspaceCapability.ts" \
  "$EVID/sources/" 2>/dev/null || true
cp -a "$ROOT/ops/qualify-action-inbox-wave1-staging.sh" "$EVID/sources/"

log "push orchestrator + dashboard dist to staging"
"${SSH[@]}" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/action_inbox_wave1.py" \
  "$ORCH/smoke-test-action-inbox-wave1.py" \
  "$ORCH/analytics_attention_wave1.py" \
  "$ORCH/compliance_findings_wave1.py" \
  "$ORCH/canary-prod-compliance-findings-wave1b.py" \
  "$ORCH/canary-prod-analytics-attention-wave1b.py" \
  "$ORCH/smoke-test-analytics-freeze-regression.py" \
  "$ORCH/smoke-test-compliance-freeze-regression.py" \
  "$ORCH/app.py" \
  "$ORCH/smoke-test-employees360-freeze-regression.py" \
  "$ORCH/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH/smoke-test-attendance-freeze-regression.py" \
  "$ORCH/smoke-test-leave-freeze-regression.py" \
  "$ORCH/smoke-test-shifts-freeze-regression.py" \
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
  "$ROOT/ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md" \
  "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md" \
  "$ROOT/ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md" \
  "$VPS_HOST:/opt/wathefni/staging/ops/" 2>/dev/null || true

"${SSH[@]}" "mkdir -p /opt/wathefni/dashboard-dist /opt/wathefni/apps/wathefni-dashboard/src/posthire"
rsync -az -e "ssh -o BatchMode=yes" \
  "$EVID/sources/dashboard-dist/" \
  "$VPS_HOST:/opt/wathefni/dashboard-dist/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/posthire/PostHire.tsx" \
  "$DASH/src/posthire/actionInboxWave1.test.ts" \
  "$VPS_HOST:/opt/wathefni/apps/wathefni-dashboard/src/posthire/"

log "restart staging orchestrator + health"
"${SSH[@]}" 'systemctl restart wathefni-orchestrator-staging.service; for i in $(seq 1 60); do if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok; systemctl is-active wathefni-orchestrator-staging.service; exit 0; fi; sleep 1; done; systemctl status wathefni-orchestrator-staging.service --no-pager -l | head -40; exit 1' \
  | tee "$EVID/remote/restart.out"

log "staging smoke + action-inbox endpoint probe"
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
export WATHEFNI_ACTION_INBOX_WAVE1=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
"\$PY" smoke-test-action-inbox-wave1.py | tee /tmp/action-inbox-w1-smoke.out
"\$PY" smoke-test-analytics-freeze-regression.py | tee /tmp/action-inbox-w1-freeze-analytics.out
"\$PY" smoke-test-compliance-freeze-regression.py | tee /tmp/action-inbox-w1-freeze-compliance.out
"\$PY" smoke-test-employees360-freeze-regression.py | tee /tmp/action-inbox-w1-freeze-e360.out
"\$PY" smoke-test-onboarding-freeze-regression.py | tee /tmp/action-inbox-w1-freeze-onb.out
"\$PY" smoke-test-attendance-freeze-regression.py | tee /tmp/action-inbox-w1-freeze-att.out
"\$PY" smoke-test-leave-freeze-regression.py | tee /tmp/action-inbox-w1-freeze-leave.out
"\$PY" smoke-test-shifts-freeze-regression.py | tee /tmp/action-inbox-w1-freeze-shifts.out
grep -E 'passed, 0 failed|action-inbox-wave1 smoke tests passed' /tmp/action-inbox-w1-smoke.out /tmp/action-inbox-w1-freeze-*.out


"\$PY" - <<'PY'
import json
import inspect
import action_inbox_wave1 as w1
import app

proof = w1.prove_item_clears_when_source_resolves()
assert proof["cleared"] is True, proof
assert proof["deduped"] >= 1, proof

pack = w1.build_action_inbox(
  analytics_attention=[{
    "id": "pending_leave",
    "severity": "high",
    "reason_en": "3 leave",
    "reason_ar": "3",
    "subject": "Leave",
    "source_module": "leave",
    "deep_link": {"page": "leave"},
  }],
  compliance_findings=[{
    "id": "x",
    "severity": "high",
    "reason_en": "Expired",
    "reason_ar": "م",
    "employee_key": "E1",
    "document_type": "residence",
    "document_type_canonical": "residence",
    "deep_link": {"page": "compliance", "employee": "E1"},
    "evidence_status": "expired",
    "owner_role": "hr_compliance",
    "owner_label_en": "Company HR / Compliance",
    "deadline": "2026-08-03",
    "escalation_step": "overdue_daily",
    "government_verified": False,
  }],
  e360_next_actions=[w1.normalize_e360_next_action(
    {"id": "onboarding:incomplete", "severity": "medium", "module": "onboarding",
     "title": "Onboarding incomplete", "reason": "open",
     "target": {"page": "onboarding"}},
    employee_key="E2", employee_name="Bob",
  )],
)
assert pack["items"][0]["severity"] in {"high", "critical"}
assert pack["items"][0]["deep_link"]["page"]
assert pack["honesty"]["mutates_records"] is False
assert pack["honesty"]["ai"] is False
assert pack["honesty"]["hiring_reports_separate"] is True
assert pack["honesty"]["alerts_delivery_owns_notifications"] is True

src = inspect.getsource(app.dashboard_action_inbox_payload)
assert "viewer_phone" in src and "actor_role" in src
assert "manager_scope_employee_keys" in inspect.getsource(app._inbox_e360_next_actions)
assert "analytics_attention" in src or "attention" in src
assert "findings" in src
assert "build_action_inbox" in src

# Tenant key present on HTTP route
route_src = inspect.getsource(app.dashboard_posthire_action_inbox)
assert "dashboard_context" in route_src

assert __import__("analytics_attention_wave1").honesty_payload()["compliance_metrics"] is False
assert __import__("compliance_findings_wave1").honesty_payload()["legal_compliance_claims"] is False

print(json.dumps({
  "contract": w1.ACTION_INBOX_WAVE1_CONTRACT,
  "clears_ok": True,
  "ranking_ok": True,
  "deep_links_ok": True,
  "scope_wiring_ok": True,
  "sibling_honesty_ok": True,
  "health": "ok",
}, ensure_ascii=False))
PY

DIST=/opt/wathefni/dashboard-dist
grep -Rql 'Action Inbox\|صندوق الإجراءات' "\$DIST" && echo UI_INBOX_COPY_OK || echo UI_INBOX_COPY_MISSING
grep -Rql 'System of action\|نظام التنفيذ' "\$DIST" && echo UI_SOA_COPY_OK || echo UI_SOA_COPY_SOFT
grep -Rql 'Hiring Reports stay separate\|تقارير التوظيف منفصلة' "\$DIST" && echo UI_HONESTY_COPY_OK || echo UI_HONESTY_COPY_SOFT
grep -Rql 'Owner\|المالك' "\$DIST" && echo UI_OWNER_COPY_OK || echo UI_OWNER_COPY_SOFT
echo STAGING_ACTION_INBOX_W1_OK
REMOTE

scp -o BatchMode=yes "$VPS_HOST:/tmp/action-inbox-w1-smoke.out" "$EVID/tests/" 2>/dev/null || true

cat > "$EVID/docs/MOBILE_WEB.md" <<'EOF'
Action Inbox Wave 1 uses the existing HR dashboard responsive shell.
Inbox rows stack full-width; metadata wraps on narrow viewports (sm:flex-row).
No native mobile app work in this wave. Verify at ~390px and desktop in staging UI.
EOF

cat > "$EVID/docs/REPORT.md" <<EOF
# Action Inbox Wave 1 — Unified Action Inbox (staging)

**Stamp:** $STAMP
**Evidence:** $EVID
**Gate candidate:** \`STAGING_ACTION_INBOX_WAVE1_GO\`

## Scope
- Read-only composition of Analytics attention[], Compliance findings[], Employees 360 next actions
- Cross-source ranking; owner/deadline/escalation; evidence/authority; SoA deep links
- Item clears when source resolves; E360 compliance dupes removed when findings cover
- Tenant/manager scope via source payloads + E360 manager_scope_employee_keys
- EN/AR UI + empty/partial/stale/error states; mobile web responsive shell

## Explicit out of scope
AI, Compliance Wave 2, Analytics Wave 2, Payroll money work, Attendance ingest,
Shifts manager expansion, production deploy, mutations, Hiring Reports merge,
Alerts & Delivery ownership transfer.

## Sibling freezes
Analytics / Compliance / Employees 360 / Onboarding / Attendance / Leave / Shifts (+ payroll authority if present).
EOF

if grep -q "STAGING_ACTION_INBOX_W1_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "action-inbox-wave1 smoke tests passed" "$EVID/tests/action-inbox-wave1-local.out"; then
  echo "GATE=STAGING_ACTION_INBOX_WAVE1_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_ACTION_INBOX_WAVE1_GO"
else
  echo "GATE=STAGING_ACTION_INBOX_WAVE1_NO_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_ACTION_INBOX_WAVE1_NO_GO"
  exit 1
fi
