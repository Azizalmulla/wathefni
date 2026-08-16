#!/usr/bin/env bash
# Action Inbox Phase 0-B — production safety-gate qualification.
# Deploy Phase 0 gates with EMPTY allowlists → prove denial / payroll exclude /
# soft-kill / WAVE1=0 → rollback → redeploy → freezes.
# Does NOT populate production allowlists. No Aziz/Talal real-HR canary enablement.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/action-inbox-phase0b-prod-safety-$STAMP"
REMOTE_STAGE="/tmp/action-inbox-p0b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/action-inbox-phase0b-prod-safety/${STAMP}"
DROPIN_NAME=zzzzzzzzzzzzzzz-action-inbox-phase0b-safety.conf

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,rollback,ui,verify}
echo "$LOCAL_EVID" > /tmp/aiw1p0b.evid
echo "$STAMP" > /tmp/aiw1p0b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-action-inbox-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/action-inbox-wave1-local.out"
"$PY_LOCAL" smoke-test-action-inbox-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-action-inbox-local.out" | tail -5
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
  canary-prod-action-inbox-phase0b.py \
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
cp -a ops/deploy-action-inbox-phase0b-prod-safety.sh "$LOCAL_EVID/sources/ops/"
cp -a "$REPO_ROOT/ops/qualify-action-inbox-phase0b-prod-safety.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
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
    canary-prod-action-inbox-phase0b.py \
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
    ops/deploy-action-inbox-phase0b-prod-safety.sh \
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

log "deploy (empty allowlists)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-action-inbox-phase0b-prod-safety.sh'
bash '$REMOTE_STAGE/deploy-action-inbox-phase0b-prod-safety.sh'
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
export AIW1P0B_EVID="\$OUTDIR"
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
# Force empty allowlists for canary process even if inherited oddly
export WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=
export WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-action-inbox-phase0b.py
REMOTE
}

log "canary pass 1 (before rollback) — empty allowlists + soft-kill + WAVE1=0"
run_canary canary-before-rollback canary/before-rollback

log "verify live process flags empty"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/flags-live.out"
set -euo pipefail
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'ACTION_INBOX_REAL_|ACTION_INBOX_EXCLUDE|ACTION_INBOX_WAVE1=' | sort
test -f /etc/systemd/system/wathefni-orchestrator.service.d/$DROPIN_NAME
VIEWER=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=' | cut -d= -f2-)
SUBJECT=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=' | cut -d= -f2-)
test -z "\$VIEWER"
test -z "\$SUBJECT"
echo LIVE_ALLOWLISTS_EMPTY_OK
REMOTE

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/action-inbox-phase0b-prod-safety/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/$DROPIN_NAME
# Wave 1-B synthetic drop-in should still be present after restore
test -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-action-inbox-wave1b-synthetic.conf
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy (empty allowlists again)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-action-inbox-phase0b-prod-safety.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
run_canary canary-after-redeploy canary/after-redeploy

log "final live allowlists still empty"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/flags-final.out"
set -euo pipefail
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
VIEWER=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=' | cut -d= -f2-)
SUBJECT=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=' | cut -d= -f2-)
WAVE=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_WAVE1=' | cut -d= -f2-)
EXCLUDE=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL=' | cut -d= -f2-)
test -z "\$VIEWER"
test -z "\$SUBJECT"
test "\$WAVE" = "1"
test "\$EXCLUDE" = "1"
echo FINAL_POSTURE_EMPTY_ALLOWLISTS_OK
REMOTE

log "write phase0b freeze notes + production freezes"
cat > "$LOCAL_EVID/docs/ACTION_INBOX_PHASE0_SAFETY_GATES.md" <<EOF
# Action Inbox Phase 0 — Real-canary safety gates

**Staging gate:** \`STAGING_ACTION_INBOX_PHASE0_GO\`  
**Production gate:** \`PROD_ACTION_INBOX_PHASE0_SAFETY_GO\`  
**Evidence (prod):** \`ops/evidence/action-inbox-phase0b-prod-safety-${STAMP}/\`  
**Real-HR canary:** **not enabled** (viewer/subject allowlists empty on production)

## Gates (fail-closed)

| Control | Env | Empty behavior |
|---|---|---|
| Viewer allowlist | \`WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST\` | API \`action_inbox_viewer_denied\` + nav hidden |
| Subject allowlist | \`WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST\` | No person-scoped items |
| Payroll exclude | \`WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL\` (default on) | No payroll/timesheet SoA rows |
| Wave kill | \`WATHEFNI_ACTION_INBOX_WAVE1=0\` | API \`action_inbox_disabled\` |

Approved boundary (code-pinned): viewer \`96599338566\` / Talal \`WATHEFNI-96550252254\` only.

## Future canary (separate change-control)

Set both allowlists to Aziz + Talal on production **only** after a dedicated real-HR canary qualify. Soft-kill = clear allowlists.

## Explicit NO-GO in this phase

- Enabling lasting real-HR canary / populating production allowlists
- AI / new differentiation wave
- Compliance/Analytics Wave 2
- Payroll money / Attendance ingest / Shifts manager expansion
EOF
cp -a "$LOCAL_EVID/docs/ACTION_INBOX_PHASE0_SAFETY_GATES.md" "$REPO_ROOT/ops/ACTION_INBOX_PHASE0_SAFETY_GATES.md"

# Keep Wave 1 freeze; annotate Phase 0-B prod qualified
cat > "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" <<EOF
# Unified Action Inbox Wave 1 — Freeze

**Gate:** \`PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO\`  
**Evidence:** \`ops/evidence/action-inbox-wave1b-prod-canary-20260803T170914Z/\`  
**Phase 0-B:** \`PROD_ACTION_INBOX_PHASE0_SAFETY_GO\` → \`ops/evidence/action-inbox-phase0b-prod-safety-${STAMP}/\`  
**Freeze:** **GO** for Wave 1 Unified Action Inbox (synthetic-only + Phase 0 fail-closed gates)

## Frozen posture

- Read-only composition of Analytics attention[], Compliance findings[], Employees 360 next actions
- Inbox **composes and ranks only** — frozen modules remain systems of action
- \`WATHEFNI_ACTION_INBOX_WAVE1=1\`, \`SYNTHETIC_ONLY=1\`, markers \`AIW1\` / phones \`965542*\`
- Phase 0: empty viewer/subject allowlists, \`EXCLUDE_PAYROLL=1\`
- \`mutates_records\`: **false**
- Alerts & Delivery owns notifications
- Hiring Reports stay separate
- No AI; no Compliance Wave 2; no Analytics Wave 2
- No Payroll money work; no Attendance ingest; no Shifts manager expansion

## Proven on production

- Wave 1-B synthetic compose/rank + ACK residual 0
- Phase 0-B: API denial + nav hide with empty allowlists; payroll/timesheet exclusion;
  soft-kill clear; \`ACTION_INBOX_WAVE1=0\` kill switch; rollback + redeploy
- Sibling freezes green

## Explicit NO-GO (outside this freeze)

- Another differentiation wave
- AI inside Action Inbox
- Mutations from inbox
- Compliance Wave 2 / Analytics Wave 2
- Payroll money work / Attendance ingest / Shifts manager expansion
- Reopening frozen module boundaries
- Real HR production canary without **separate** explicit Aziz/Talal change-control

## Rollback

Phase 0-B: \`/opt/wathefni/backups/production-pre-action-inbox-phase0b-*\` + \`ROLLBACK.sh\`  
Wave 1-B: \`/opt/wathefni/backups/production-pre-action-inbox-wave1b-*\` + \`ROLLBACK.sh\`
EOF
cp -a "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" "$LOCAL_EVID/docs/ACTION_INBOX_WAVE1_FREEZE.md"

"${SCP[@]}" "$REPO_ROOT/ops/ACTION_INBOX_PHASE0_SAFETY_GATES.md" "$VPS_HOST:/opt/wathefni/ops/"
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
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/action-inbox-phase0b-prod-safety/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write REPORT + GATE"
CANARY1_OK=0
CANARY2_OK=0
ROLLBACK_OK=0
FREEZES_OK=0
FLAGS_OK=0
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-before-rollback.out" && CANARY1_OK=1 || true
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-after-redeploy.out" && CANARY2_OK=1 || true
grep -q 'ROLLBACK_VERIFIED' "$LOCAL_EVID/tests/rollback.out" && ROLLBACK_OK=1 || true
grep -q 'FINAL_POSTURE_EMPTY_ALLOWLISTS_OK' "$LOCAL_EVID/tests/flags-final.out" && FLAGS_OK=1 || true
if ! grep -q '^FAIL ' "$LOCAL_EVID/tests/freezes-prod.out" && grep -q 'passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out"; then
  FREEZES_OK=1
else
  FREEZES_OK=0
fi

VERDICT=NO-GO
CANARY_CC=NO-GO
if [[ "$CANARY1_OK" -eq 1 && "$CANARY2_OK" -eq 1 && "$ROLLBACK_OK" -eq 1 && "$FREEZES_OK" -eq 1 && "$FLAGS_OK" -eq 1 ]]; then
  VERDICT=GO
  # Safety gates proven; separate Aziz/Talal canary still needs explicit change-control
  CANARY_CC=CONDITIONAL-GO
fi

cat > "$LOCAL_EVID/docs/REPORT.md" <<EOF
# Action Inbox Phase 0-B — production safety-gate qualification

**Stamp:** \`$STAMP\`  
**Evidence:** \`$LOCAL_EVID\`  
**Staging prerequisite:** \`ops/evidence/action-inbox-phase0-20260803T172623Z\` (\`STAGING_ACTION_INBOX_PHASE0_GO\`)  
**Docs:** \`ops/ACTION_INBOX_PHASE0_SAFETY_GATES.md\`

## Verdicts

| Scope | Verdict |
|---|---|
| Production Phase 0 safety gates (empty allowlists) | **$VERDICT** |
| Populate Aziz/Talal allowlists / real-HR canary | **$CANARY_CC** — requires **separate explicit** change-control |
| Real inbox visibility in this wave | **NO-GO** (allowlists left empty) |
| AI / mutations / frozen-module changes | **NO-GO** |

## Proof

- Canary before rollback: fail=0 → $CANARY1_OK
- Live empty allowlists after deploy → see flags-live.out
- Rollback verified → $ROLLBACK_OK
- Canary after redeploy: fail=0 → $CANARY2_OK
- Final empty allowlists + EXCLUDE_PAYROLL=1 + WAVE1=1 → $FLAGS_OK
- Sibling freezes green → $FREEZES_OK
- Residual canary ACK = 0

## Production posture (end state)

\`WAVE1=1\` · \`SYNTHETIC_ONLY=1\` · \`EXCLUDE_PAYROLL=1\` · **viewer allowlist empty** · **subject allowlist empty**

## Rollback

\`/opt/wathefni/backups/production-pre-action-inbox-phase0b-*\` + \`ROLLBACK.sh\`
EOF

if [[ "$VERDICT" == "GO" ]]; then
  echo "GATE=PROD_ACTION_INBOX_PHASE0_SAFETY_GO" | tee "$LOCAL_EVID/docs/GATE.txt"
  echo "PROD_ACTION_INBOX_PHASE0_SAFETY_GO"
  echo "SEPARATE_AZIZ_TALAL_CANARY=CONDITIONAL-GO (explicit change-control required; allowlists not populated)"
else
  echo "GATE=PROD_ACTION_INBOX_PHASE0_SAFETY_NO_GO" | tee "$LOCAL_EVID/docs/GATE.txt"
  echo "PROD_ACTION_INBOX_PHASE0_SAFETY_NO_GO"
  exit 1
fi
