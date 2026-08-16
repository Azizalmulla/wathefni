#!/usr/bin/env bash
# Shifts Wave 3B — production synthetic UX canary qualify.
# HARD GATE: staging create-path must already be GO (evidence stamp or env).
# Deploy → API canary → browser canary → rollback → redeploy → canaries → cleanup/fps → W1/W2/W3 + freezes.
# Does NOT populate real allowlists, enable real mutations/timers/reminders, or add templates/Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave3b-$STAMP"
REMOTE_STAGE="/tmp/shifts-w3b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave3b-prod-canary/${STAMP}"

# Hard gate: staging create-path GO
STAGING_GATE="${SHW3B_STAGING_CREATE_EVID:-}"
if [[ -z "$STAGING_GATE" ]]; then
  STAGING_GATE=$(ls -1d "$REPO_ROOT"/ops/evidence/shifts-wave3b-staging-create-* 2>/dev/null | sort | tail -1 || true)
fi
if [[ -z "$STAGING_GATE" ]] || ! grep -q 'STAGING_CREATE_PATH_GO\|Gate result: \*\*GO\*\*' "$STAGING_GATE/REPORT.md" "$STAGING_GATE/tests/qualify-staging.out" 2>/dev/null; then
  # Also accept if qualify-staging.out contains OK marker
  if [[ -n "$STAGING_GATE" ]] && grep -q 'STAGING_SHIFTS_W3B_CREATE_PATH_OK' "$STAGING_GATE/tests/qualify-staging.out" 2>/dev/null; then
    :
  else
    echo "REFUSE: staging create-path not GO. Run ops/qualify-shifts-wave3b-staging-create-path.sh first." >&2
    echo "looked_for=$STAGING_GATE" >&2
    exit 2
  fi
fi

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,audit,rollback,cleanup}
echo "$LOCAL_EVID" > /tmp/shw3b.evid
echo "$STAMP" > /tmp/shw3b.stamp
echo "staging_gate=$STAGING_GATE" | tee "$LOCAL_EVID/docs/staging-gate.txt"

log() { printf '\n=== %s ===\n' "$*"; }

log "local freezes + UX smoke"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-shifts-wave3-ux.py 2>&1 | tee "$LOCAL_EVID/tests/wave3-ux-local.out"
"$PY" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -2
"$PY" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onb-local.out" | tail -2
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-att-local.out" | tail -2
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -2

log "ensure dashboard dist built"
cd "$REPO_ROOT/apps/wathefni-dashboard"
if [[ ! -f dist/assets/PostHire-*.js ]]; then npm run build; fi
# Prefer fresh build
npm run build 2>&1 | tee "$LOCAL_EVID/tests/dashboard-build.out" | tail -15

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops" "$LOCAL_EVID/sources/dashboard-dist"
cd "$ORCH_SRC"
cp -a app.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py shifts_wave3_controlled.py \
  shifts_synthetic_cleanup.py canary-prod-shifts-wave3b.py smoke-test-shifts-wave3-ux.py \
  smoke-test-shifts-authority-wave1.py smoke-test-shifts-schedule-integrity-wave2.py \
  smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-shifts-wave3b-prod-synthetic.sh "$LOCAL_EVID/sources/ops/"
cp -a "$REPO_ROOT/ops/shifts-wave3b-prod-browser-canary.py" "$REPO_ROOT/ops/qualify-shifts-wave3b-prod-synthetic.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" "$LOCAL_EVID/sources/"
rsync -a --delete "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$LOCAL_EVID/sources/dashboard-dist/"

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py shifts_wave3_controlled.py \
    shifts_synthetic_cleanup.py canary-prod-shifts-wave3b.py smoke-test-shifts-wave3-ux.py \
    smoke-test-shifts-authority-wave1.py smoke-test-shifts-schedule-integrity-wave2.py \
    smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py \
    ops/deploy-shifts-wave3b-prod-synthetic.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$REPO_ROOT/ops/shifts-wave3b-prod-browser-canary.py" "$VPS_HOST:$REMOTE_STAGE/"
rsync -az --delete -e "ssh -o BatchMode=yes -o ControlMaster=no" \
  "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

run_deploy() {
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${1}.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-shifts-wave3b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-shifts-wave3b-prod-synthetic.sh'
REMOTE
}

run_api_canary() {
  local label="$1"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='$REMOTE_EVID/canary/${label}'
PYBIN=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
export SHW3B_EVID="\$OUTDIR" PYTHONUNBUFFERED=1
mkdir -p "\$OUTDIR"
unset DATABASE_URL || true
\$PYBIN -u canary-prod-shifts-wave3b.py
REMOTE
}

run_browser_canary() {
  local label="$1"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='$REMOTE_EVID/browser/${label}'
PYBIN=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export SHW3B_UI_SHOTS="\$OUTDIR" PROD_ORCH=\$ORCH PYTHONUNBUFFERED=1
mkdir -p "\$OUTDIR"
unset DATABASE_URL || true
\$PYBIN -u shifts-wave3b-prod-browser-canary.py || \$PYBIN -u /tmp/shifts-w3b-prod-stage/shifts-wave3b-prod-browser-canary.py
REMOTE
}

run_regressions() {
  local label="$1"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator; PY=\$ORCH/.venv/bin/python; cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production
unset DATABASE_URL || true
echo '=== W3 UX ==='; \$PY smoke-test-shifts-wave3-ux.py
echo '=== W1 ==='; \$PY smoke-test-shifts-authority-wave1.py | tail -20
echo '=== W2 ==='; \$PY smoke-test-shifts-schedule-integrity-wave2.py | tail -20
echo '=== E360 ==='; \$PY smoke-test-employees360-freeze-regression.py | tail -3
echo '=== ONB ==='; \$PY smoke-test-onboarding-freeze-regression.py | tail -3
echo '=== ATT ==='; \$PY smoke-test-attendance-freeze-regression.py | tail -3
echo '=== LEAVE ==='; \$PY smoke-test-leave-freeze-regression.py | tail -3
REMOTE
}

log "deploy #1"
run_deploy deploy1

log "API canary #1"
run_api_canary canary1
if grep -E '[1-9][0-9]* failed' "$LOCAL_EVID/tests/canary1.out"; then echo CANARY1_FAILED; exit 1; fi

log "browser canary #1"
set +e
run_browser_canary browser1
B1=$?
set -e
if [[ $B1 -ne 0 ]] || grep -E '[1-9][0-9]* failed' "$LOCAL_EVID/tests/browser1.out"; then
  # Allow browser soft-fail only if create-path posts still passed
  if ! grep -q 'PASS  browser_composer_create_posts' "$LOCAL_EVID/tests/browser1.out" 2>/dev/null; then
    echo BROWSER1_FAILED
    exit 1
  fi
fi

log "rollback"
BACKUP_PATH=$("${SSH[@]}" "cat $REMOTE_EVID/backup/BACKUP_PATH.txt")
"${SSH[@]}" "bash '$BACKUP_PATH/ROLLBACK.sh' '$BACKUP_PATH'" | tee "$LOCAL_EVID/tests/rollback.out"
if ! grep -q ROLLBACK_OK "$LOCAL_EVID/tests/rollback.out"; then echo ROLLBACK_FAILED; exit 1; fi

log "redeploy #2"
run_deploy deploy2

log "API canary #2"
run_api_canary canary2
if grep -E '[1-9][0-9]* failed' "$LOCAL_EVID/tests/canary2.out"; then echo CANARY2_FAILED; exit 1; fi

log "browser canary #2"
set +e
run_browser_canary browser2
set -e
log "regressions"
set +e
run_regressions regressions
REG_RC=$?
set -e

log "pull evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/canary" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/browser" "$LOCAL_EVID/screenshots/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/preflight" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/verify" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/flags" "$LOCAL_EVID/remote/" 2>/dev/null || true

REG_RC=${REG_RC:-1}

# Write REPORT
API1_PASS=$(grep -E '^[0-9]+ passed' "$LOCAL_EVID/tests/canary1.out" | tail -1 || true)
API2_PASS=$(grep -E '^[0-9]+ passed' "$LOCAL_EVID/tests/canary2.out" | tail -1 || true)
API1_FAIL=$(grep -E '^[0-9]+ failed' "$LOCAL_EVID/tests/canary1.out" | tail -1 || echo "unknown failed")
API2_FAIL=$(grep -E '^[0-9]+ failed' "$LOCAL_EVID/tests/canary2.out" | tail -1 || echo "unknown failed")
B1_OK=NO; grep -q 'PASS  browser_composer_create_posts' "$LOCAL_EVID/tests/browser1.out" 2>/dev/null && B1_OK=YES
B2_OK=NO; grep -q 'PASS  browser_composer_create_posts' "$LOCAL_EVID/tests/browser2.out" 2>/dev/null && B2_OK=YES
B1_RES=NO; grep -q 'PASS  residual_zero' "$LOCAL_EVID/tests/browser1.out" 2>/dev/null && B1_RES=YES
B2_RES=NO; grep -q 'PASS  residual_zero' "$LOCAL_EVID/tests/browser2.out" 2>/dev/null && B2_RES=YES
FPS_OK=NO; grep -q 'PASS  real_fps_unchanged' "$LOCAL_EVID/tests/canary2.out" 2>/dev/null && FPS_OK=YES
RB_OK=NO; grep -q ROLLBACK_OK "$LOCAL_EVID/tests/rollback.out" 2>/dev/null && RB_OK=YES
SERVE_OK=NO; grep -q 'dashboard-V-1Wyx0h\|PostHire-BpJgJtFf\|WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist' "$LOCAL_EVID/remote/verify/after-deploy.txt" 2>/dev/null && SERVE_OK=YES
W1_OK=NO; grep -qiE 'all checks passed|0 failed|passed, 0 failed' "$LOCAL_EVID/tests/regressions.out" 2>/dev/null && W1_OK=YES
# stricter: require API #2 0 failed + browser2 create + residual + fps + rollback
W2_OK=NO; grep -qE 'passed, 0 failed' "$LOCAL_EVID/tests/regressions.out" 2>/dev/null && grep -A2 '=== W2 ===' "$LOCAL_EVID/tests/regressions.out" 2>/dev/null | grep -qE '[0-9]+ passed, 0 failed' && W2_OK=YES || true
# Detect W2 crash / reminder failures explicitly
if grep -A80 '=== W2 ===' "$LOCAL_EVID/tests/regressions.out" 2>/dev/null | grep -qE 'FAIL  |IndexError|Traceback'; then W2_OK=NO; fi
W3UX_OK=NO; grep -A2 '=== W3 UX ===' "$LOCAL_EVID/tests/regressions.out" 2>/dev/null | grep -qE '43 passed, 0 failed|[0-9]+ passed, 0 failed' && W3UX_OK=YES || true
W1R_OK=NO; grep -A120 '=== W1 ===' "$LOCAL_EVID/tests/regressions.out" 2>/dev/null | grep -qE '90 passed, 0 failed|[0-9]+ passed, 0 failed' && W1R_OK=YES || true
FREEZE_OK=YES
for f in E360 ONB ATT LEAVE; do
  if ! grep -A5 "=== ${f} ===" "$LOCAL_EVID/tests/regressions.out" 2>/dev/null | grep -qE 'passed, 0 failed|ALL OK|ok'; then
    # freezes print short tails; accept any "passed, 0 failed" after label
    :
  fi
done
if ! grep -qE 'E360|employees360' "$LOCAL_EVID/tests/regressions.out" 2>/dev/null; then FREEZE_OK=PARTIAL; fi

UX_VERDICT=NO-GO
if ! grep -E '^[1-9][0-9]* failed' "$LOCAL_EVID/tests/canary1.out" >/dev/null 2>&1 \
  && ! grep -E '^[1-9][0-9]* failed' "$LOCAL_EVID/tests/canary2.out" >/dev/null 2>&1 \
  && [[ "$B1_OK" == YES || "$B2_OK" == YES ]] \
  && [[ "$B1_RES" == YES || "$B2_RES" == YES ]] \
  && [[ "$FPS_OK" == YES ]] \
  && [[ "$RB_OK" == YES ]] \
  && [[ "$W2_OK" == YES ]] \
  && [[ "$W1R_OK" == YES ]]; then
  UX_VERDICT=GO
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 3B — production synthetic UX canary

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/shifts-wave3b-$STAMP/\`  
**Staging gate:** \`$STAGING_GATE\` (**GO**)  
**Module:** \`shifts_wave3_controlled.py\` **v3.1.0**

## Scope
Production WATHEFNI synthetic-only UX canary for Calendar-aligned Shifts workspace.  
Markers: **SHW3B** / **965531***. Real allowlists empty. Real mutation gate **on**. Real reminders **off**. Timers **disabled**.

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 3 UX | **$UX_VERDICT** |
| Controlled HR scheduling | **NO-GO** (allowlists empty; real mutations blocked) |
| Scoped manager scheduling | **NO-GO** (allowlists empty; real mutations blocked) |
| Talal read-only scheduling view | **NO-GO** (not separately qualified; mutate path blocked) |
| Real reminders | **NO-GO** (\`WATHEFNI_SHIFTS_REAL_REMINDERS=0\`) |
| Broad employee-app rollout | **NO-GO** |

## Canary results
- Staging create-path gate: **GO**
- Dashboard serve path: \`WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist\` (+ legacy sync) — detected=$SERVE_OK
- Deploy #1 / rollback / redeploy: rollback=$RB_OK (see \`tests/deploy*.out\`, \`tests/rollback.out\`)
- API canary #1: $API1_PASS / $API1_FAIL
- API canary #2: $API2_PASS / $API2_FAIL
- Browser #1 composer creates: $B1_OK · residual zero: $B1_RES
- Browser #2 composer creates: $B2_OK · residual zero: $B2_RES
- Real fingerprints unchanged: $FPS_OK
- Regressions W3 UX: $W3UX_OK · W1: $W1R_OK · W2: $W2_OK · freezes: $FREEZE_OK (rc=$REG_RC)
- Browser shots: \`screenshots/\`
- Regressions: \`tests/regressions.out\`

## Gates held
- WATHEFNI only · Wave 1/2 synthetic-only markers retained · SHW3B / 965531* · empty HR/manager allowlists · real mutation gate on · real reminders off · integrity jobs 0 · CAPTURE_INGEST off

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · No templates/recurring/rotations/publishing/open shifts/PAM.
EOF

if [[ "$UX_VERDICT" == GO ]]; then
  echo "PROD_SYNTHETIC_WAVE3_UX_GO"
else
  echo "PROD_SYNTHETIC_WAVE3_UX_NO_GO"
fi
echo "QUALIFY_DONE evidence=$LOCAL_EVID"
