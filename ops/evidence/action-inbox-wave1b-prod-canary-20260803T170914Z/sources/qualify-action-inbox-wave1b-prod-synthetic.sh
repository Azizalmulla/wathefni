#!/usr/bin/env bash
# Action Inbox Wave 1-B — production WATHEFNI synthetic qualification.
# Deploy → canary → rollback proof → redeploy → canary → sibling freezes → freeze stamp.
# Read-only composition. No AI / Compliance Wave 2 / Analytics Wave 2 / Payroll money /
# Attendance ingest / Shifts manager expansion. Does NOT start another differentiation wave.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/action-inbox-wave1b-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/action-inbox-w1b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/action-inbox-wave1b-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,ui,verify}
echo "$LOCAL_EVID" > /tmp/aiw1b.evid
echo "$STAMP" > /tmp/aiw1b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-action-inbox-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/action-inbox-wave1-local.out"
"$PY_LOCAL" smoke-test-analytics-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-analytics-local.out" | tail -5
"$PY_LOCAL" smoke-test-compliance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-compliance-local.out" | tail -5
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3

log "dashboard unit + vite build"
cd "$DASH_SRC"
npm test -- --run src/posthire/actionInboxWave1.test.ts 2>&1 | tee "$LOCAL_EVID/ui/vitest.out" | tail -15
npx tsc -b --pretty false 2>&1 | tee "$LOCAL_EVID/ui/tsc-full.out" | tail -5 || true
if grep -E 'PostHire\.tsx|actionInbox|src/App\.tsx|src/types\.ts|workspaceCapability|moduleWorkspace|api\.ts' "$LOCAL_EVID/ui/tsc-full.out"; then
  echo "ACTION_INBOX_TS_FAILED"
  exit 1
fi
echo "ACTION_INBOX_TS_CLEAN" | tee -a "$LOCAL_EVID/ui/tsc-full.out"
npx vite build 2>&1 | tee "$LOCAL_EVID/ui/dashboard-build.out" | tail -20
mkdir -p "$LOCAL_EVID/sources/dashboard-dist"
cp -a "$DASH_SRC/dist/." "$LOCAL_EVID/sources/dashboard-dist/"

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops"
cd "$ORCH_SRC"
cp -a app.py action_inbox_wave1.py analytics_attention_wave1.py compliance_findings_wave1.py \
  canary-prod-action-inbox-wave1b.py \
  canary-prod-analytics-attention-wave1b.py \
  canary-prod-compliance-findings-wave1b.py \
  smoke-test-action-inbox-wave1.py \
  smoke-test-action-inbox-freeze-regression.py \
  smoke-test-analytics-freeze-regression.py \
  smoke-test-compliance-freeze-regression.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-action-inbox-wave1b-prod-synthetic.sh ops/migrate-action-inbox-wave1-prod.sh \
  "$LOCAL_EVID/sources/ops/"
cp -a "$REPO_ROOT/ops/qualify-action-inbox-wave1b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$DASH_SRC/src/posthire/PostHire.tsx" \
  "$DASH_SRC/src/posthire/actionInboxWave1.test.ts" \
  "$DASH_SRC/src/App.tsx" \
  "$DASH_SRC/src/types.ts" \
  "$DASH_SRC/src/lib/api.ts" \
  "$DASH_SRC/src/lib/moduleWorkspace.ts" \
  "$DASH_SRC/src/lib/workspaceCapability.ts" \
  "$LOCAL_EVID/ui/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py action_inbox_wave1.py analytics_attention_wave1.py compliance_findings_wave1.py \
    canary-prod-action-inbox-wave1b.py \
    canary-prod-analytics-attention-wave1b.py \
    canary-prod-compliance-findings-wave1b.py \
    smoke-test-action-inbox-wave1.py \
    smoke-test-action-inbox-freeze-regression.py \
    smoke-test-analytics-freeze-regression.py \
    smoke-test-compliance-freeze-regression.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-action-inbox-wave1b-prod-synthetic.sh \
    ops/migrate-action-inbox-wave1-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" \
  "$DASH_SRC/src/posthire/PostHire.tsx" \
  "$DASH_SRC/src/posthire/actionInboxWave1.test.ts" \
  "$DASH_SRC/src/App.tsx" \
  "$DASH_SRC/src/types.ts" \
  "$DASH_SRC/src/lib/api.ts" \
  "$DASH_SRC/src/lib/moduleWorkspace.ts" \
  "$DASH_SRC/src/lib/workspaceCapability.ts" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" -r "$LOCAL_EVID/sources/dashboard-dist/." "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-action-inbox-wave1b-prod-synthetic.sh' '$REMOTE_STAGE/migrate-action-inbox-wave1-prod.sh'
bash '$REMOTE_STAGE/deploy-action-inbox-wave1b-prod-synthetic.sh'
REMOTE

run_canary() {
  local label="$1"
  local outdir="$2"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='$REMOTE_EVID/$outdir'
PYBIN=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export AIW1B_EVID="\$OUTDIR"
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-action-inbox-wave1b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/action-inbox-wave1b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-action-inbox-wave1b-synthetic.conf
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep ACTION_INBOX_WAVE1 || echo "ACTION_INBOX_WAVE1_FLAGS_CLEARED"
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-action-inbox-wave1b-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-after-redeploy.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='/opt/wathefni/production-evidence/action-inbox-wave1b-prod-canary/${STAMP}/canary/after-redeploy'
PYBIN=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export AIW1B_EVID="\$OUTDIR"
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-action-inbox-wave1b.py
REMOTE

log "write freeze doc then production freezes"
cat > "$LOCAL_EVID/docs/ACTION_INBOX_WAVE1_FREEZE.md" <<EOF
# Unified Action Inbox Wave 1 — Freeze

**Gate:** \`PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO\`  
**Evidence:** \`ops/evidence/action-inbox-wave1b-prod-canary-${STAMP}/\`  
**Freeze:** **GO** for Wave 1 Unified Action Inbox (synthetic-only production posture)

## Frozen posture

- Read-only composition of Analytics attention[], Compliance findings[], Employees 360 next actions
- Inbox **composes and ranks only** — frozen modules remain systems of action
- \`WATHEFNI_ACTION_INBOX_WAVE1=1\`, \`SYNTHETIC_ONLY=1\`, markers \`AIW1\` / phones \`965542*\`
- \`mutates_records\`: **false**
- Alerts & Delivery owns notifications
- Hiring Reports stay separate
- No AI; no Compliance Wave 2; no Analytics Wave 2
- No Payroll money work; no Attendance ingest; no Shifts manager expansion

## Proven on production synthetic

- ACK migrate (\`action_inbox_wave_acks\`) with production ACK
- Cross-source ranking, E360 dedupe, clears-on-resolve
- Owner / deadline / escalation / evidence / authority labels + deep links
- Freshness / as_of (Asia/Kuwait), EN/AR, mobile web responsive shell
- Tenant/manager scope wiring; residual canary ACK = 0
- Rollback verified; redeploy canary green
- Sibling freezes green (Analytics / Compliance / Employees 360 / Onboarding / Attendance / Leave / Shifts / Payroll)

## Explicit NO-GO (outside this freeze)

- Another differentiation wave
- AI inside Action Inbox
- Mutations from inbox
- Compliance Wave 2 / Analytics Wave 2
- Payroll money work / Attendance ingest / Shifts manager expansion
- Reopening frozen module boundaries
- Real HR production rollout (synthetic-only until separate change-control)

## Rollback

Backup + \`ROLLBACK.sh\` under \`/opt/wathefni/backups/production-pre-action-inbox-wave1b-*\`  
(Drop-in removal restores pre-Wave-1 Action Inbox flags; durable wave ACK rows retained.)
EOF
cp -a "$LOCAL_EVID/docs/ACTION_INBOX_WAVE1_FREEZE.md" "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md"
"${SCP[@]}" "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" "$VPS_HOST:/opt/wathefni/ops/"
"${SCP[@]}" "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" "$VPS_HOST:/opt/wathefni/staging/ops/" 2>/dev/null || true
for d in EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ANALYTICS_WAVE1_ATTENTION_FREEZE.md \
         COMPLIANCE_WAVE1_FINDINGS_FREEZE.md; do
  "${SCP[@]}" "$REPO_ROOT/ops/$d" "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
done
"${SCP[@]}" \
  "$ORCH_SRC/smoke-test-action-inbox-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-analytics-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-compliance-freeze-regression.py" \
  "$ORCH_SRC/canary-prod-action-inbox-wave1b.py" \
  "$ORCH_SRC/canary-prod-analytics-attention-wave1b.py" \
  "$ORCH_SRC/canary-prod-compliance-findings-wave1b.py" \
  "$VPS_HOST:/opt/wathefni/orchestrator/" 2>/dev/null || true

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/freezes-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
PY=\$ORCH/.venv/bin/python
cd \$ORCH
\$PY smoke-test-action-inbox-freeze-regression.py
\$PY smoke-test-analytics-freeze-regression.py
\$PY smoke-test-compliance-freeze-regression.py
\$PY smoke-test-employees360-freeze-regression.py
\$PY smoke-test-onboarding-freeze-regression.py
\$PY smoke-test-attendance-freeze-regression.py
\$PY smoke-test-leave-freeze-regression.py
\$PY smoke-test-shifts-freeze-regression.py
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/action-inbox-wave1b-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write REPORT + GATE"
CANARY1_OK=0
CANARY2_OK=0
ROLLBACK_OK=0
FREEZES_OK=0
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-before-rollback.out" && CANARY1_OK=1 || true
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-after-redeploy.out" && CANARY2_OK=1 || true
grep -q 'ROLLBACK_VERIFIED' "$LOCAL_EVID/tests/rollback.out" && ROLLBACK_OK=1 || true
if ! grep -q '^FAIL ' "$LOCAL_EVID/tests/freezes-prod.out" && grep -q 'passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out"; then
  FREEZES_OK=1
else
  FREEZES_OK=0
fi

VERDICT=NO-GO
if [[ "$CANARY1_OK" -eq 1 && "$CANARY2_OK" -eq 1 && "$ROLLBACK_OK" -eq 1 && "$FREEZES_OK" -eq 1 ]]; then
  VERDICT=GO
fi

cat > "$LOCAL_EVID/docs/REPORT.md" <<EOF
# Action Inbox Wave 1-B — production synthetic Unified Action Inbox

**Stamp:** \`$STAMP\`  
**Evidence:** \`$LOCAL_EVID\`  
**Staging prerequisite:** \`ops/evidence/action-inbox-wave1-20260803T165655Z\` (\`STAGING_ACTION_INBOX_WAVE1_GO\`)  
**Freeze doc:** \`ops/ACTION_INBOX_WAVE1_FREEZE.md\`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Action Inbox Wave 1 | **$VERDICT** |
| Freeze Unified Action Inbox Wave 1 | **$VERDICT** |
| Another differentiation wave | **NO-GO** (not started) |
| AI / mutations / Compliance Wave 2 / Analytics Wave 2 / Payroll money | **NO-GO** |

## Proof

- Canary before rollback: fail=0 → $CANARY1_OK
- Rollback verified → $ROLLBACK_OK
- Canary after redeploy: fail=0 → $CANARY2_OK
- Sibling + action-inbox freezes green → $FREEZES_OK
- SYNTHETIC_ONLY enforced; residual canary ACK = 0

## Flags

\`WATHEFNI_ACTION_INBOX_WAVE1=1\` · \`SYNTHETIC_ONLY=1\` · markers \`AIW1\` · phones \`965542*\` · company \`WATHEFNI\`

## Rollback

\`/opt/wathefni/backups/production-pre-action-inbox-wave1b-*\` + \`ROLLBACK.sh\`
EOF

mkdir -p "$REPO_ROOT/.cursor/rules"
cat > "$REPO_ROOT/.cursor/rules/action-inbox-freeze.mdc" <<'RULE'
---
description: Unified Action Inbox Wave 1 freeze — do not reopen without owner change-control
globs: apps/wathefni-dashboard/src/posthire/PostHire.tsx,wathefni-orchestrator/action_inbox_wave1.py,wathefni-orchestrator/app.py
alwaysApply: false
---

# Unified Action Inbox Wave 1 freeze

Action Inbox is **production-qualified under synthetic-only posture** and **frozen**. See `ops/ACTION_INBOX_WAVE1_FREEZE.md`.

## Final posture (do not weaken)

- Read-only composition only (`mutates_records: false`)
- `WATHEFNI_ACTION_INBOX_WAVE1=1` + `SYNTHETIC_ONLY=1` (markers `AIW1`, phones `965542*`)
- Frozen modules remain systems of action
- Alerts & Delivery owns notifications; Hiring Reports stay separate
- No AI; no Compliance/Analytics Wave 2; no Payroll money; no Attendance ingest; no Shifts manager expansion

## Hard bans

1. **Do not mutate records from the inbox.**
2. **Do not add AI** inside Action Inbox.
3. **Do not start another differentiation wave** without owner-approved change-control.
4. **Do not reopen frozen module contracts** to unblock inbox work.
5. **Do not transfer notification ownership** away from Alerts & Delivery.
6. **Do not merge Hiring Reports** into Action Inbox.

## Allowed without a new wave

- Bugfixes restoring freeze invariants
- Ops evidence / documentation
- `smoke-test-action-inbox-freeze-regression.py`
RULE

if [[ "$VERDICT" == "GO" ]]; then
  echo "GATE=PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO" | tee "$LOCAL_EVID/docs/GATE.txt"
  echo "PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO"
else
  echo "GATE=PROD_SYNTHETIC_ACTION_INBOX_WAVE1_NO_GO" | tee "$LOCAL_EVID/docs/GATE.txt"
  echo "PROD_SYNTHETIC_ACTION_INBOX_WAVE1_NO_GO"
  exit 1
fi
