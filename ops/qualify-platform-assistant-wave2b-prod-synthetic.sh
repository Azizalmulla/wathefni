#!/usr/bin/env bash
# Platform Assistant Wave 2-B — production WATHEFNI synthetic Safe Ops Queue Reads qualification.
# Deploy → ACK → canary → rollback → redeploy → canary → sibling freezes → freeze stamp.
# Does NOT start Wave 3 / Payroll / Shifts / Onboarding / WhatsApp / money / ingest / mutations.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/platform-assistant-wave2b-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/platform-assistant-w2b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/platform-assistant-wave2b-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,verify}
echo "$LOCAL_EVID" > /tmp/paw2b.evid
echo "$STAMP" > /tmp/paw2b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
export WATHEFNI_PLATFORM_ASSISTANT_WAVE1=1
export WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES=WATHEFNI
export WATHEFNI_PLATFORM_ASSISTANT_WAVE2=1
export WATHEFNI_PLATFORM_ASSISTANT_WAVE2_COMPANIES=WATHEFNI
export WATHEFNI_ASSISTANT_MUTATIONS=0
export WATHEFNI_ASSISTANT_KILL=0
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
"$PY_LOCAL" smoke-test-platform-assistant-wave2.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave2-local.out" | tail -40
"$PY_LOCAL" smoke-test-platform-assistant-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave1-local.out" | tail -15
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops"
cd "$ORCH_SRC"
cp -a app.py action_registry.py assistant_capability_catalog.py tool_call_orchestrator.py \
  platform_assistant_spine_wave1.py platform_assistant_wave2_safe_ops_reads.py \
  setup_console_wave_a_launch_readiness.py \
  canary-prod-platform-assistant-wave2b.py \
  smoke-test-platform-assistant-wave2.py \
  smoke-test-platform-assistant-wave1.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-platform-assistant-wave2b-prod-synthetic.sh \
  ops/migrate-platform-assistant-wave2-prod.sh \
  "$LOCAL_EVID/sources/ops/"
cp -a ops/migrate-platform-assistant-wave2-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-platform-assistant-wave2b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py action_registry.py assistant_capability_catalog.py tool_call_orchestrator.py \
    platform_assistant_spine_wave1.py platform_assistant_wave2_safe_ops_reads.py \
    setup_console_wave_a_launch_readiness.py \
    canary-prod-platform-assistant-wave2b.py \
    smoke-test-platform-assistant-wave2.py \
    smoke-test-platform-assistant-wave1.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-platform-assistant-wave2b-prod-synthetic.sh \
    ops/migrate-platform-assistant-wave2-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-platform-assistant-wave2b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-platform-assistant-wave2b-prod-synthetic.sh'
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
export PAW2B_EVID="\$OUTDIR"
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'PLATFORM_ASSISTANT|ASSISTANT_KILL|ASSISTANT_MUTATIONS|CAPTURE_INGEST' | sort | tee "\$OUTDIR/flags.txt"
grep -qiE 'CAPTURE_INGEST=(on|true|1|yes)' "\$OUTDIR/flags.txt" && { echo 'REFUSE ingest on'; exit 3; } || echo CAPTURE_INGEST_OFF_OK
grep -q 'ASSISTANT_MUTATIONS=0' "\$OUTDIR/flags.txt" && echo MUTATIONS_OFF_OK || { echo MUTATIONS_NOT_OFF; exit 3; }
grep -q 'PLATFORM_ASSISTANT_WAVE1=1' "\$OUTDIR/flags.txt" && echo WAVE1_ON_OK || { echo WAVE1_NOT_ON; exit 3; }
grep -q 'PLATFORM_ASSISTANT_WAVE2=1' "\$OUTDIR/flags.txt" && echo WAVE2_ON_OK || { echo WAVE2_NOT_ON; exit 3; }
\$PYBIN -u canary-prod-platform-assistant-wave2b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/platform-assistant-wave2b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-platform-assistant-wave2b-synthetic.conf
# Wave 2 flags cleared; Wave 1 should remain from restored drop-ins
ENVS=\$(tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ)
echo "\$ENVS" | grep PLATFORM_ASSISTANT_WAVE2 || echo "WAVE2_FLAGS_CLEARED"
echo "\$ENVS" | grep PLATFORM_ASSISTANT_WAVE1=1 && echo WAVE1_RETAINED || echo WAVE1_MISSING_AFTER_ROLLBACK
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-platform-assistant-wave2b-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
run_canary canary-after-redeploy canary/after-redeploy

log "write freeze doc + sibling freezes"
cat > "$LOCAL_EVID/docs/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md" <<EOF
# Platform Assistant Wave 2 — Safe Ops Queue Reads Freeze

**Gate:** \`PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO\`  
**Evidence:** \`ops/evidence/platform-assistant-wave2b-prod-canary-${STAMP}/\`  
**Staging prerequisite:** \`ops/evidence/platform-assistant-wave2-staging-20260803T200430Z/\` (\`STAGING_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO\`)  
**Freeze:** **GO** for Wave 2 Safe Ops Queue Reads (production synthetic WATHEFNI posture)

## Frozen posture

- Grounded read-only Leave request queue + Attendance exception queue
- \`WATHEFNI_PLATFORM_ASSISTANT_WAVE2=1\`, companies \`WATHEFNI\` (requires Wave 1)
- HR dashboard-only · mutations off · master kill retained
- Attendance labeled ingest-off / existing-record based
- Leave and Attendance remain systems of action (prepare deep links only)
- Citations · freshness · authority · grouping · EN/AR · audit events
- No Payroll · Shifts · Onboarding · WhatsApp · manager/employee/mobile assistants
- No money · Attendance ingest · mutations · frozen-module contract changes

## Proven on production synthetic

- Deploy + migrate/ACK (\`assistant.wave2b_production_ack\`); canary residual **0**; durable ACK retained
- Leave queue + Attendance exceptions summarize (citations, freshness, authority, groups, deep links)
- Tenant / permission / manager-scope isolation; WhatsApp tools hidden; mutations hidden
- Master kill + mutation kill; rollback verified; redeploy canary green
- Sibling freezes green (Employees 360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Assistant Wave 3
- Payroll / Shifts / Onboarding assistant surfaces
- WhatsApp widening / manager or employee assistants / mobile
- Payroll money · Attendance ingest · frozen-module contract changes

## Rollback

Backup + \`ROLLBACK.sh\` under \`/opt/wathefni/backups/production-pre-platform-assistant-wave2b-*\`
EOF
cp -a "$LOCAL_EVID/docs/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md" \
  "$REPO_ROOT/ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md"
"${SCP[@]}" "$REPO_ROOT/ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md" "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
"${SCP[@]}" "$REPO_ROOT/ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md" "$VPS_HOST:/opt/wathefni/staging/ops/" 2>/dev/null || true
for d in EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         PLATFORM_ASSISTANT_WAVE1_SPINE_FREEZE.md; do
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
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/platform-assistant-wave2b-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

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
FREEZE_ZERO_COUNT=$(grep -cE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out" || true)
[[ "$FREEZE_ZERO_COUNT" -ge 5 ]] || FREEZES_OK=0

VERDICT=NO-GO
if [[ "$CANARY1_OK" -eq 1 && "$CANARY2_OK" -eq 1 && "$ROLLBACK_OK" -eq 1 && "$FREEZES_OK" -eq 1 && "$DEPLOY_OK" -eq 1 ]]; then
  VERDICT=GO
fi

if [[ "$VERDICT" != "GO" ]]; then
  sed -i.bak 's/\*\*Freeze:\*\* \*\*GO\*\*/**Freeze:** **NO-GO**/' \
    "$REPO_ROOT/ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md" 2>/dev/null || true
  sed -i.bak 's/PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO/PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_NO_GO/' \
    "$REPO_ROOT/ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md" 2>/dev/null || true
fi

cat > "$LOCAL_EVID/docs/REPORT.md" <<EOF
# Platform Assistant Wave 2-B — production synthetic Safe Ops Queue Reads

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/platform-assistant-wave2b-prod-canary-$STAMP/\`  
**Staging prerequisite:** \`ops/evidence/platform-assistant-wave2-staging-20260803T200430Z/\`  
**Freeze doc:** \`ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md\`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Platform Assistant Wave 2 | **$VERDICT** |
| Freeze Assistant Wave 2 Safe Ops Reads | **$VERDICT** |
| Assistant Wave 3 | **NO-GO** (not started) |
| Payroll / Shifts / Onboarding / WhatsApp / money / ingest / mutations | **NO-GO** |

## Proof matrix

| Check | Result |
|---|---|
| Deploy + ACK | $DEPLOY_OK |
| Canary before rollback (fail=0) | $CANARY1_OK |
| Rollback verified | $ROLLBACK_OK |
| Canary after redeploy (fail=0) | $CANARY2_OK |
| Sibling freezes (5× 0 failed) | $FREEZES_OK |

## Flags

\`WATHEFNI_PLATFORM_ASSISTANT_WAVE2=1\` · companies \`WATHEFNI\` · Wave 1 on · \`ASSISTANT_MUTATIONS=0\` · \`CAPTURE_INGEST=off\` · marker \`PAW2B\`

## Residual

Canary-tagged \`assistant.wave2b_canary*\` events cleaned to **0**; durable production ACK retained.
EOF
cp -a "$LOCAL_EVID/docs/REPORT.md" "$LOCAL_EVID/REPORT.md"

GATE="PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO"
if [[ "$VERDICT" != "GO" ]]; then
  GATE="PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_NO_GO"
fi
cat > "$LOCAL_EVID/docs/GATE.txt" <<EOF
stamp=$STAMP
evidence=$LOCAL_EVID
company=WATHEFNI
channel=hr_dashboard
mutations=off
whatsapp_widening=false
wave3_started=false
payroll_money=false
attendance_ingest=false
capture_ingest=off
candidate_knowledge=false
residual=0
GATE=$GATE
PROD_SYNTHETIC_WAVE2=$VERDICT
ASSISTANT_WAVE3=NO-GO
EOF

echo "QUALIFY_DONE evidence=$LOCAL_EVID verdict=$VERDICT gate=$GATE"
[[ "$VERDICT" == "GO" ]]
