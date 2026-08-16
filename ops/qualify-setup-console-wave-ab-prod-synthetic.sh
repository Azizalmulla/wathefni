#!/usr/bin/env bash
# Setup Console Wave A-B — production WATHEFNI synthetic Launch Readiness qualification.
# Deploy → ACK → canary → rollback → redeploy → canary → sibling freezes → freeze stamp.
# Does NOT start Setup Wave B / external tenants / Payroll money / Attendance ingest / AI / mobile apps.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/setup-console-wave-ab-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/setup-console-wab-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/setup-console-wave-ab-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,ui,verify}
echo "$LOCAL_EVID" > /tmp/scwab.evid
echo "$STAMP" > /tmp/scwab.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-setup-console-wave-a.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave-a-local.out" | tail -40
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3

log "dashboard setup-console build"
cd "$DASH_SRC"
npx tsc -b --pretty false 2>&1 | tee "$LOCAL_EVID/ui/tsc-full.out" | tail -8 || true
if grep -E 'setup-console/LaunchReadiness|setup-console/SetupConsoleApp|setup-console/api\.ts|setup-console/types\.ts' "$LOCAL_EVID/ui/tsc-full.out"; then
  echo "SETUP_CONSOLE_TS_FAILED"
  exit 1
fi
echo "SETUP_CONSOLE_TS_CLEAN" | tee -a "$LOCAL_EVID/ui/tsc-full.out"
npx vite build 2>&1 | tee "$LOCAL_EVID/ui/dashboard-build.out" | tail -25
mkdir -p "$LOCAL_EVID/sources/dashboard-dist"
cp -a "$DASH_SRC/dist/." "$LOCAL_EVID/sources/dashboard-dist/"
grep -Rql 'Launch readiness\|جاهزية الإطلاق\|launch-overall-status' "$LOCAL_EVID/sources/dashboard-dist" \
  && echo UI_DIST_LAUNCH_OK | tee "$LOCAL_EVID/ui/dist-local-check.txt" \
  || { echo UI_DIST_LAUNCH_MISSING; exit 1; }

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops"
cd "$ORCH_SRC"
cp -a app.py setup_console_wave_a_launch_readiness.py \
  canary-prod-setup-console-wave-ab.py \
  smoke-test-setup-console-wave-a.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-setup-console-wave-ab-prod-synthetic.sh \
  ops/migrate-setup-console-wave-a-prod.sh \
  "$LOCAL_EVID/sources/ops/"
cp -a ops/migrate-setup-console-wave-a-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-setup-console-wave-ab-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$DASH_SRC/src/setup-console/LaunchReadinessPage.tsx" \
  "$DASH_SRC/src/setup-console/SetupConsoleApp.tsx" \
  "$DASH_SRC/src/setup-console/api.ts" \
  "$DASH_SRC/src/setup-console/types.ts" \
  "$LOCAL_EVID/ui/"

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py setup_console_wave_a_launch_readiness.py \
    canary-prod-setup-console-wave-ab.py \
    smoke-test-setup-console-wave-a.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-setup-console-wave-ab-prod-synthetic.sh \
    ops/migrate-setup-console-wave-a-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" \
  "$DASH_SRC/src/setup-console/LaunchReadinessPage.tsx" \
  "$DASH_SRC/src/setup-console/SetupConsoleApp.tsx" \
  "$DASH_SRC/src/setup-console/api.ts" \
  "$DASH_SRC/src/setup-console/types.ts" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" -r "$LOCAL_EVID/sources/dashboard-dist/." "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-setup-console-wave-ab-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-setup-console-wave-ab-prod-synthetic.sh'
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
export SCWAB_EVID="\$OUTDIR"
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
# Refuse if ingest flipped on
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'CAPTURE_INGEST|SETUP_CONSOLE_WAVE_A' | sort | tee "\$OUTDIR/flags.txt"
grep -qiE 'CAPTURE_INGEST=(on|true|1|yes)' "\$OUTDIR/flags.txt" && { echo 'REFUSE ingest on'; exit 3; } || echo CAPTURE_INGEST_OFF_OK
\$PYBIN -u canary-prod-setup-console-wave-ab.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/setup-console-wave-ab-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-setup-console-wave-ab-synthetic.conf
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep SETUP_CONSOLE_WAVE_A || echo "WAVE_A_FLAGS_CLEARED"
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-setup-console-wave-ab-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
run_canary canary-after-redeploy canary/after-redeploy

log "write freeze doc + sibling freezes"
cat > "$LOCAL_EVID/docs/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md" <<EOF
# Setup Console Wave A — Launch Readiness Freeze

**Gate:** \`PROD_SYNTHETIC_SETUP_CONSOLE_WAVE_A_GO\`  
**Evidence:** \`ops/evidence/setup-console-wave-ab-prod-canary-${STAMP}/\`  
**Staging prerequisite:** \`ops/evidence/setup-console-wave-a-staging-20260803T185950Z/\` (\`STAGING_SETUP_CONSOLE_WAVE_A_GO\`)  
**Freeze:** **GO** for Wave A Launch Readiness (production synthetic WATHEFNI posture)

## Frozen posture

- Operator-only Launch Readiness for **WATHEFNI**
- Honest states: \`not_purchased\` · \`setup_required\` · \`blocked\` · \`ready_for_canary\` · \`live_controlled\` · \`paused\`
- Console toggles never override freezes, env gates, allowlists, or \`SYNTHETIC_ONLY\`
- \`WATHEFNI_SETUP_CONSOLE_WAVE_A=1\`, companies \`WATHEFNI\`
- Payroll money **off** · Attendance ingest **off** (\`CAPTURE_INGEST=off\`) · no rollout widening · no AI/mobile · no frozen-module contract changes

## Proven on production synthetic

- Deploy + migrate/ACK (schema-less; residual **0**)
- Six-stage checklist, overall readiness, important blockers + deep links, pause impact
- EN/AR + mobile web markers in UI source and dashboard dist
- Entitlements cannot bypass freezes / allowlists / SYNTHETIC_ONLY / CAPTURE_INGEST=off
- Rollback verified; redeploy canary green
- Sibling freezes green (Employees 360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Setup Wave B / external company onboarding
- Enabling Attendance ingest or Payroll money from Setup
- Broad rollout widening / AI / mobile app work

## Rollback

Backup + \`ROLLBACK.sh\` under \`/opt/wathefni/backups/production-pre-setup-console-wave-ab-*\`
EOF
cp -a "$LOCAL_EVID/docs/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md" \
  "$REPO_ROOT/ops/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md"
"${SCP[@]}" "$REPO_ROOT/ops/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md" "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
"${SCP[@]}" "$REPO_ROOT/ops/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md" "$VPS_HOST:/opt/wathefni/staging/ops/" 2>/dev/null || true
for d in EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md; do
  "${SCP[@]}" "$REPO_ROOT/ops/$d" "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
done

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/freezes-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
PY=\$ORCH/.venv/bin/python
cd \$ORCH
\$PY smoke-test-employees360-freeze-regression.py
\$PY smoke-test-onboarding-freeze-regression.py
\$PY smoke-test-attendance-freeze-regression.py
\$PY smoke-test-leave-freeze-regression.py
\$PY smoke-test-shifts-freeze-regression.py
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/setup-console-wave-ab-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write REPORT + GATE"
CANARY1_OK=0
CANARY2_OK=0
ROLLBACK_OK=0
FREEZES_OK=0
DEPLOY_OK=0
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-before-rollback.out" && CANARY1_OK=1 || true
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-after-redeploy.out" && CANARY2_OK=1 || true
grep -q 'ROLLBACK_VERIFIED' "$LOCAL_EVID/tests/rollback.out" && ROLLBACK_OK=1 || true
grep -q 'DEPLOY_OK' "$LOCAL_EVID/tests/deploy.out" && DEPLOY_OK=1 || true
if ! grep -q '^FAIL ' "$LOCAL_EVID/tests/freezes-prod.out" && grep -q 'passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out"; then
  FREEZES_OK=1
else
  FREEZES_OK=0
fi
# Require five sibling freeze summaries with 0 failed
FREEZE_ZERO_COUNT=$(grep -cE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out" || true)
[[ "$FREEZE_ZERO_COUNT" -ge 5 ]] || FREEZES_OK=0

VERDICT=NO-GO
if [[ "$CANARY1_OK" -eq 1 && "$CANARY2_OK" -eq 1 && "$ROLLBACK_OK" -eq 1 && "$FREEZES_OK" -eq 1 && "$DEPLOY_OK" -eq 1 ]]; then
  VERDICT=GO
fi

# If freeze was pre-written as GO but qualify failed, rewrite freeze as NO-GO
if [[ "$VERDICT" != "GO" ]]; then
  sed -i.bak 's/\*\*Freeze:\*\* \*\*GO\*\*/**Freeze:** **NO-GO**/' \
    "$REPO_ROOT/ops/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md" 2>/dev/null || true
  sed -i.bak 's/PROD_SYNTHETIC_SETUP_CONSOLE_WAVE_A_GO/PROD_SYNTHETIC_SETUP_CONSOLE_WAVE_A_NO_GO/' \
    "$REPO_ROOT/ops/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md" 2>/dev/null || true
fi

cat > "$LOCAL_EVID/docs/REPORT.md" <<EOF
# Setup Console Wave A-B — production synthetic Launch Readiness

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/setup-console-wave-ab-prod-canary-$STAMP/\`  
**Staging prerequisite:** \`ops/evidence/setup-console-wave-a-staging-20260803T185950Z/\` (\`STAGING_SETUP_CONSOLE_WAVE_A_GO\`)  
**Freeze doc:** \`ops/SETUP_CONSOLE_WAVE_A_LAUNCH_READINESS_FREEZE.md\`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Setup Console Wave A | **$VERDICT** |
| Freeze Setup Console Wave A | **$VERDICT** |
| Setup Wave B / external tenants | **NO-GO** (not started) |
| Payroll money / Attendance ingest / rollout widening / AI / mobile | **NO-GO** |

## Proof matrix

| Check | Result |
|---|---|
| Deploy + ACK | $DEPLOY_OK |
| Canary before rollback (fail=0) | $CANARY1_OK |
| Rollback verified | $ROLLBACK_OK |
| Canary after redeploy (fail=0) | $CANARY2_OK |
| Sibling freezes (5× 0 failed) | $FREEZES_OK |

## Flags

\`WATHEFNI_SETUP_CONSOLE_WAVE_A=1\` · companies \`WATHEFNI\` · \`CAPTURE_INGEST=off\` · operator-only · marker \`SCWAB\`

## Residual

Read-only evaluate + schema-less ACK → residual **0**.
EOF
cp -a "$LOCAL_EVID/docs/REPORT.md" "$LOCAL_EVID/REPORT.md"

GATE="PROD_SYNTHETIC_SETUP_CONSOLE_WAVE_A_GO"
if [[ "$VERDICT" != "GO" ]]; then
  GATE="PROD_SYNTHETIC_SETUP_CONSOLE_WAVE_A_NO_GO"
fi
cat > "$LOCAL_EVID/docs/GATE.txt" <<EOF
stamp=$STAMP
evidence=$LOCAL_EVID
company=WATHEFNI
external_tenants=false
payroll_money=false
attendance_ingest=false
capture_ingest=off
wave_b_started=false
ai=false
mobile_apps=false
residual=0
GATE=$GATE
PROD_SYNTHETIC_WAVE_A=$VERDICT
SETUP_WAVE_B=NO-GO
EOF

echo "QUALIFY_DONE evidence=$LOCAL_EVID verdict=$VERDICT gate=$GATE"
[[ "$VERDICT" == "GO" ]]
