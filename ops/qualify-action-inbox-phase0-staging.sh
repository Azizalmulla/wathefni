#!/usr/bin/env bash
# Action Inbox Phase 0 — real-canary safety gates — staging only.
# Proves fail-closed viewer/subject allowlists, payroll exclude, soft-kill, WAVE1=0.
# Does NOT enable lasting Aziz/Talal real-HR canary (allowlists cleared at end).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/action-inbox-phase0-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging
VPS_HOST="root@$HOST"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
DROPIN_STAGING=/etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-action-inbox-phase0.conf

mkdir -p "$EVID"/{sources,tests,remote,ui,docs,verify}
echo "$EVID" > /tmp/action-inbox-p0.evid
echo "$STAMP" > /tmp/action-inbox-p0.stamp
echo "evidence=$EVID"

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-action-inbox-wave1.py 2>&1 | tee "$EVID/tests/action-inbox-wave1-local.out"
"$PY_LOCAL" smoke-test-action-inbox-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-action-inbox.out" | tail -8
"$PY_LOCAL" smoke-test-analytics-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-analytics.out" | tail -3
"$PY_LOCAL" smoke-test-compliance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-compliance.out" | tail -3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-e360.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -3

log "dashboard unit + build"
cd "$DASH"
npm test -- --run src/posthire/actionInboxWave1.test.ts 2>&1 | tee "$EVID/ui/vitest.out" | tail -15
npx tsc -b --pretty false 2>&1 | tee "$EVID/ui/tsc-full.out" | tail -5 || true
if grep -E 'PostHire\.tsx|actionInbox|src/App\.tsx|workspaceCapability|api\.ts|src/types\.ts' "$EVID/ui/tsc-full.out"; then
  echo "ACTION_INBOX_TS_FAILED"
  exit 1
fi
echo "ACTION_INBOX_TS_CLEAN" | tee -a "$EVID/ui/tsc-full.out"
npx vite build 2>&1 | tee "$EVID/ui/dashboard-build.out" | tail -20
mkdir -p "$EVID/sources/dashboard-dist"
cp -a "$DASH/dist/." "$EVID/sources/dashboard-dist/"

log "stage sources"
cp -a "$ORCH/action_inbox_wave1.py" "$ORCH/app.py" \
  "$ORCH/smoke-test-action-inbox-wave1.py" \
  "$ORCH/smoke-test-action-inbox-freeze-regression.py" \
  "$ORCH/canary-prod-action-inbox-wave1b.py" \
  "$EVID/sources/"
cp -a "$ROOT/ops/qualify-action-inbox-phase0-staging.sh" "$EVID/sources/" 2>/dev/null || true

log "push to staging"
"${SSH[@]}" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/action_inbox_wave1.py" \
  "$ORCH/app.py" \
  "$ORCH/smoke-test-action-inbox-wave1.py" \
  "$ORCH/smoke-test-action-inbox-freeze-regression.py" \
  "$ORCH/canary-prod-action-inbox-wave1b.py" \
  "$ORCH/smoke-test-analytics-freeze-regression.py" \
  "$ORCH/smoke-test-compliance-freeze-regression.py" \
  "$ORCH/smoke-test-employees360-freeze-regression.py" \
  "$ORCH/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH/smoke-test-attendance-freeze-regression.py" \
  "$ORCH/smoke-test-leave-freeze-regression.py" \
  "$ORCH/smoke-test-shifts-freeze-regression.py" \
  "$VPS_HOST:$REMOTE_ORCH/"
"${SSH[@]}" "mkdir -p /opt/wathefni/dashboard-dist /opt/wathefni/ops /opt/wathefni/staging/ops"
rsync -az -e "ssh -o BatchMode=yes" "$EVID/sources/dashboard-dist/" "$VPS_HOST:/opt/wathefni/dashboard-dist/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" \
  "$ROOT/ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md" \
  "$ROOT/ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md" \
  "$ROOT/ops/EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$ROOT/ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true

log "staging drop-in soft-kill (empty allowlists) + restart"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$EVID/remote/restart-softkill.out"
set -euo pipefail
mkdir -p "$(dirname '$DROPIN_STAGING')"
cat > '$DROPIN_STAGING' <<'EOF'
[Service]
Environment=WATHEFNI_ACTION_INBOX_WAVE1=1
Environment=WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY=1
Environment=WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL=1
Environment=WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=
Environment=WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in \$(seq 1 60); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok; exit 0; fi
  sleep 1
done
exit 1
REMOTE

log "staging phase0 proofs"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$EVID/remote/staging-smoke.out"
set -euo pipefail
ORCH="$REMOTE_ORCH"
cd "\$ORCH"
set -a; source "$POSTGRES_ENV"; set +a
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV="$POSTGRES_ENV"
export ACK_DB="$ACK_DB_DEFAULT"
export WATHEFNI_EXPECTED_DATABASE_NAME="$ACK_DB_DEFAULT"
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
PY=/opt/wathefni/orchestrator/.venv/bin/python
test -x "\$PY" || PY=python3
"\$PY" smoke-test-action-inbox-wave1.py | tee /tmp/aiw1-p0-smoke.out
"\$PY" smoke-test-action-inbox-freeze-regression.py | tee /tmp/aiw1-p0-freeze.out | tail -5
"\$PY" smoke-test-analytics-freeze-regression.py | tee /tmp/aiw1-p0-an.out | tail -2
"\$PY" smoke-test-compliance-freeze-regression.py | tee /tmp/aiw1-p0-cf.out | tail -2
"\$PY" smoke-test-employees360-freeze-regression.py | tee /tmp/aiw1-p0-e360.out | tail -2
"\$PY" smoke-test-onboarding-freeze-regression.py | tee /tmp/aiw1-p0-onb.out | tail -2
"\$PY" smoke-test-attendance-freeze-regression.py | tee /tmp/aiw1-p0-att.out | tail -2
"\$PY" smoke-test-leave-freeze-regression.py | tee /tmp/aiw1-p0-leave.out | tail -2
"\$PY" smoke-test-shifts-freeze-regression.py | tee /tmp/aiw1-p0-shifts.out | tail -2

"\$PY" - <<'PY'
import json, os
import action_inbox_wave1 as w1
import app
from fastapi import HTTPException

def ctx(phone, uid, email=None):
    perms = ["analytics.read","compliance.read","employees.read","onboarding.read","leave.read","attendance.read","shifts.read","payroll.read"]
    return {
        "company_code": "WATHEFNI",
        "hr_phone": phone,
        "actor_phone": phone,
        "actor_user_id": uid,
        "actor_email": email,
        "actor_role": "owner",
        "permission_authority": "backend_current",
        "permission_subject_user_id": uid,
        "permission_subject_company": "WATHEFNI",
        "permissions": perms,
        "hr_user": {"user_id": uid, "email": email, "phone": phone},
        "access": {
            "permission_authority": "backend_current",
            "permission_subject_user_id": uid,
            "permission_subject_company": "WATHEFNI",
            "permissions": perms,
        },
    }

# Soft-kill empty allowlists: Aziz denied
try:
    app.dashboard_action_inbox_payload(ctx("96599338566", "88b17ca9-aff4-4721-a553-c1b5514ef95f", "azizalmulla16@gmail.com"))
    raise SystemExit("expected viewer denial with empty allowlist")
except HTTPException as exc:
    assert exc.detail.get("error") == "action_inbox_viewer_denied", exc.detail
print("SOFT_KILL_DENY_OK")

assert w1.nav_offerable_for_viewer(company_code="WATHEFNI", phone="96599338566") is False
print("NAV_SOFT_KILL_OK")

# Authorize temporary canary probe
os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = "96599338566"
os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = "WATHEFNI-96550252254"
assert w1.viewer_is_allowlisted(phone="96599338566") is True
assert w1.viewer_is_allowlisted(phone="66363363") is False
pack = app.dashboard_action_inbox_payload(ctx("96599338566", "88b17ca9-aff4-4721-a553-c1b5514ef95f", "azizalmulla16@gmail.com"))
assert pack.get("contract") == w1.ACTION_INBOX_WAVE1_CONTRACT
for item in pack.get("items") or []:
    assert str(item.get("employee_key") or "").upper() == "WATHEFNI-96550252254", item
    assert not w1.is_payroll_inbox_item(item), item
    assert (item.get("deep_link") or {}).get("page") != "payroll"
print("AUTHORIZED_TALAL_ONLY_OK", {"total": pack.get("summary", {}).get("total")})

try:
    app.dashboard_action_inbox_payload(ctx("66363363", "fouad-denied", "f.burhama@disruptv.tech"))
    raise SystemExit("fouad should be denied")
except HTTPException as exc:
    assert exc.detail.get("error") == "action_inbox_viewer_denied", exc.detail
print("UNAUTHORIZED_VIEWER_DENY_OK")

# Clear allowlists → soft kill again
os.environ["WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST"] = ""
os.environ["WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST"] = ""
try:
    app.dashboard_action_inbox_payload(ctx("96599338566", "88b17ca9-aff4-4721-a553-c1b5514ef95f"))
    raise SystemExit("expected soft-kill after clear")
except HTTPException as exc:
    assert exc.detail.get("error") == "action_inbox_viewer_denied", exc.detail
print("CLEAR_ALLOWLIST_SOFT_KILL_OK")

# Feature flag kill
os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = "0"
try:
    app.dashboard_action_inbox_payload(ctx("96599338566", "88b17ca9-aff4-4721-a553-c1b5514ef95f"))
    raise SystemExit("expected wave disabled")
except HTTPException as exc:
    assert exc.detail.get("error") == "action_inbox_disabled", exc.detail
print("WAVE1_KILL_SWITCH_OK")
os.environ["WATHEFNI_ACTION_INBOX_WAVE1"] = "1"

print(json.dumps({"phase0": "ok", "real_canary_enabled": False}, ensure_ascii=False))
PY

DIST=/opt/wathefni/dashboard-dist
grep -Rql 'Action Inbox\|صندوق الإجراءات' "\$DIST" && echo UI_INBOX_COPY_OK || echo UI_INBOX_COPY_MISSING
echo STAGING_ACTION_INBOX_PHASE0_OK
REMOTE

log "restore staging drop-in empty allowlists (canary not enabled)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$EVID/remote/restore-softkill.out"
set -euo pipefail
cat > '$DROPIN_STAGING' <<'EOF'
[Service]
Environment=WATHEFNI_ACTION_INBOX_WAVE1=1
Environment=WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY=1
Environment=WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL=1
Environment=WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=
Environment=WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in \$(seq 1 60); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok_restored; exit 0; fi
  sleep 1
done
exit 1
REMOTE

scp -o BatchMode=yes "$VPS_HOST:/tmp/aiw1-p0-smoke.out" "$EVID/tests/" 2>/dev/null || true

cat > "$EVID/docs/REPORT.md" <<EOF
# Action Inbox Phase 0 — real-canary safety gates (staging)

**Stamp:** $STAMP  
**Evidence:** $EVID  
**Gate candidate:** \`STAGING_ACTION_INBOX_PHASE0_GO\`

## Proven
- Fail-closed viewer allowlist (API denial + nav offerable false)
- Fail-closed subject allowlist (Talal-only when set; empty soft-kill)
- Payroll/timesheet SoA rows never appear
- Clearing allowlists removes visibility immediately
- \`ACTION_INBOX_WAVE1=0\` disables inbox
- Sibling freezes green
- Ending posture: allowlists **empty** (real canary **not** enabled)

## Explicit non-goals
No lasting Aziz/Talal canary enablement, no AI, no differentiation wave, no frozen-module changes.
EOF

if grep -q "STAGING_ACTION_INBOX_PHASE0_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "SOFT_KILL_DENY_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "AUTHORIZED_TALAL_ONLY_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "UNAUTHORIZED_VIEWER_DENY_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "CLEAR_ALLOWLIST_SOFT_KILL_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "WAVE1_KILL_SWITCH_OK" "$EVID/remote/staging-smoke.out" \
  && grep -q "action-inbox-wave1 smoke tests passed" "$EVID/tests/action-inbox-wave1-local.out"; then
  echo "GATE=STAGING_ACTION_INBOX_PHASE0_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_ACTION_INBOX_PHASE0_GO"
  echo "CONDITIONAL_GO_FOR_SEPARATE_AZIZ_TALAL_CANARY=YES (allowlists still empty — not enabled)"
else
  echo "GATE=STAGING_ACTION_INBOX_PHASE0_NO_GO" | tee "$EVID/docs/GATE.txt"
  echo "STAGING_ACTION_INBOX_PHASE0_NO_GO"
  exit 1
fi
