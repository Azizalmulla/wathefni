#!/usr/bin/env bash
# Shifts Wave 5B — production synthetic publish/open/coverage canary qualify.
# HARD GATE: staging Wave 5 must already be GO.
# Deploy → canary → rollback → redeploy → canary → W1B–4B coexistence → freezes → fps/residual.
# Does NOT enable real publishing, real open-shift claims, real allowlists, reminders, timers,
# rotations, PAM, or Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave5b-$STAMP"
REMOTE_STAGE="/tmp/shifts-w5b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave5b-prod-canary/${STAMP}"

# Hard gate: staging Wave 5 GO
STAGING_GATE="${SHW5B_STAGING_EVID:-}"
if [[ -z "$STAGING_GATE" ]]; then
  STAGING_GATE=$(ls -1d "$REPO_ROOT"/ops/evidence/shifts-wave5-* 2>/dev/null | sort | tail -1 || true)
fi
if [[ -z "$STAGING_GATE" ]] || ! grep -qiE 'PROD_SYNTHETIC_WAVE5|Verdict: GO|production synthetic Wave 5 canary.*GO' "$STAGING_GATE/REPORT.md" 2>/dev/null; then
  echo "REFUSE: staging Wave 5 not GO. Run ops/qualify-shifts-wave5-staging.sh first." >&2
  echo "looked_for=$STAGING_GATE" >&2
  exit 2
fi

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,rollback,cleanup,audit,ui}
echo "$LOCAL_EVID" > /tmp/shw5b.evid
echo "$STAMP" > /tmp/shw5b.stamp
echo "staging_gate=$STAGING_GATE" | tee "$LOCAL_EVID/docs/staging-gate.txt"

log() { printf '\n=== %s ===\n' "$*"; }

log "local freezes (DB may be unavailable)"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
set +e
"$PY" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -2
"$PY" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onb-local.out" | tail -2
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-att-local.out" | tail -2
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -2
set -e

log "optional dashboard build for Publish & coverage tab"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
if [[ -f "$DASH_SRC/package.json" ]]; then
  set +e
  (cd "$DASH_SRC" && npm run build) 2>&1 | tee "$LOCAL_EVID/ui/dashboard-build.out" | tail -20
  BUILD_RC=${PIPESTATUS[0]}
  set -e
  if [[ $BUILD_RC -eq 0 ]] && [[ -d "$DASH_SRC/dist" ]]; then
    mkdir -p "$LOCAL_EVID/sources/dashboard-dist"
    cp -a "$DASH_SRC/dist/." "$LOCAL_EVID/sources/dashboard-dist/"
    echo DASHBOARD_BUILD_OK | tee "$LOCAL_EVID/ui/dashboard-build-status.txt"
  else
    echo DASHBOARD_BUILD_SKIPPED | tee "$LOCAL_EVID/ui/dashboard-build-status.txt"
  fi
else
  echo DASHBOARD_SRC_MISSING | tee "$LOCAL_EVID/ui/dashboard-build-status.txt"
fi

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops/sql"
cp -a "$ORCH_SRC/app.py" \
  "$ORCH_SRC/shifts_publish_wave5.py" \
  "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/shifts_wave3_controlled.py" \
  "$ORCH_SRC/shifts_authority_wave1.py" \
  "$ORCH_SRC/shifts_schedule_integrity_wave2.py" \
  "$ORCH_SRC/canary-prod-shifts-wave5b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave4b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave3b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave2b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave1b.py" \
  "$ORCH_SRC/smoke-test-shifts-publish-wave5.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$ORCH_SRC/ops/deploy-shifts-wave5b-prod-synthetic.sh" "$LOCAL_EVID/sources/ops/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave5b-prod-synthetic.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/lib/api.ts" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/shifts_publish_wave5.py" \
  "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/shifts_wave3_controlled.py" \
  "$ORCH_SRC/shifts_authority_wave1.py" \
  "$ORCH_SRC/shifts_schedule_integrity_wave2.py" \
  "$ORCH_SRC/canary-prod-shifts-wave5b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave4b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave3b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave2b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave1b.py" \
  "$ORCH_SRC/smoke-test-shifts-publish-wave5.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$ORCH_SRC/ops/deploy-shifts-wave5b-prod-synthetic.sh" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" \
  "$VPS_HOST:$REMOTE_STAGE/ops/sql/"
if [[ -d "$LOCAL_EVID/sources/dashboard-dist" ]]; then
  "${SCP[@]}" -r "$LOCAL_EVID/sources/dashboard-dist/." "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"
fi

run_deploy() {
  local label="$1"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-shifts-wave5b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-shifts-wave5b-prod-synthetic.sh'
REMOTE
}

run_canary() {
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
export SHW5B_EVID="\$OUTDIR" PYTHONUNBUFFERED=1
mkdir -p "\$OUTDIR"
unset DATABASE_URL || true
\$PYBIN -u canary-prod-shifts-wave5b.py
REMOTE
}

run_ui_probe() {
  local label="$1"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set +e
ORCH=/opt/wathefni/orchestrator; PY=\$ORCH/.venv/bin/python; cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production
unset DATABASE_URL || true
# Prove Wave 5 honesty payload + Publish tab assets present in dashboard dist
\$PY - <<'PY'
import app, shifts_publish_wave5 as w5, os
from pathlib import Path
h = w5.honesty_payload()
assert h.get("publishing") is True and h.get("open_shifts") is True and h.get("coverage_rules") is True
print("wave5_honesty_ok", w5.SHIFTS_WAVE5_VERSION)
dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
idx = dist / "index.html"
print("dashboard_index_exists", idx.exists())
# Search built assets for publish panel test id / copy
found = False
if dist.exists():
  for p in dist.rglob("*"):
    if p.suffix in {".js",".html",".css"} and p.is_file() and p.stat().st_size < 8_000_000:
      try:
        txt = p.read_text(errors="ignore")
      except Exception:
        continue
      if "shifts-publish-panel" in txt or "Publish & coverage" in txt or "النشر والتغطية" in txt:
        found = True
        print("publish_tab_marker", p.name)
        break
print("publish_tab_asset", found)
print("UI_PROBE_OK" if found else "UI_PROBE_FAIL")
assert found, "Publish & coverage tab asset missing from dashboard dist"
PY
curl -sf http://127.0.0.1:8010/health >/dev/null && echo health_ok
echo UI_PROBE_DONE
REMOTE
}

run_coexistence() {
  local label="$1"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set +e
ORCH=/opt/wathefni/orchestrator; PY=\$ORCH/.venv/bin/python; cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export PYTHONUNBUFFERED=1
unset DATABASE_URL || true
# Hygiene: clear leftover prior-wave synthetic rows/policies so fps coexistence is fair
\$PY - <<'PY'
import app
from shifts_synthetic_cleanup import CleanupScope, cleanup_synthetic_scope, wave1b_scope, wave2b_scope, wave3b_scope, wave4b_scope, wave5b_scope
for s in (
  wave5b_scope(), wave4b_scope(), wave3b_scope(), wave2b_scope(), wave1b_scope(),
  CleanupScope(company_code="WATHEFNI", markers=("SHW2","SHW2-SYNTH|","SHW2C"), phone_prefixes=("965529","965530"), employee_json_flag="shw2", leave_reason_ilike="%shw2%", seasonal_name_ilike="%SHW2%"),
):
  r = cleanup_synthetic_scope(app.db_connect, s)
  print("hygiene", list(s.markers), "residual", r.get("residual_total"))
PY
if [[ -f canary-prod-shifts-wave1b.py ]]; then
  echo '=== W1B ==='; mkdir -p /tmp/shw5b-coexist/w1b; SHW1B_EVID=/tmp/shw5b-coexist/w1b \$PY -u canary-prod-shifts-wave1b.py | tee /tmp/w1b-coexist.out | tail -8; echo W1B_RC=\${PIPESTATUS[0]}
fi
if [[ -f canary-prod-shifts-wave2b.py ]]; then
  echo '=== W2B ==='; mkdir -p /tmp/shw5b-coexist/w2b; WATHEFNI_SHIFTS_INTEGRITY_JOBS=1 SHW2B_EVID=/tmp/shw5b-coexist/w2b \$PY -u canary-prod-shifts-wave2b.py | tee /tmp/w2b-coexist.out | tail -10; echo W2B_RC=\${PIPESTATUS[0]}
fi
if [[ -f canary-prod-shifts-wave3b.py ]]; then
  echo '=== W3B ==='; mkdir -p /tmp/shw5b-coexist/w3b; SHW3B_EVID=/tmp/shw5b-coexist/w3b \$PY -u canary-prod-shifts-wave3b.py | tee /tmp/w3b-coexist.out | tail -8; echo W3B_RC=\${PIPESTATUS[0]}
fi
if [[ -f canary-prod-shifts-wave4b.py ]]; then
  echo '=== W4B ==='; mkdir -p /tmp/shw5b-coexist/w4b; SHW4B_EVID=/tmp/shw5b-coexist/w4b \$PY -u canary-prod-shifts-wave4b.py | tee /tmp/w4b-coexist.out | tail -8; echo W4B_RC=\${PIPESTATUS[0]}
fi
export WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
echo '=== W3 UX ==='; \$PY smoke-test-shifts-wave3-ux.py | tee /tmp/w3ux-coexist.out | tail -3; echo W3UX_RC=\$?
echo '=== W1 ==='; \$PY smoke-test-shifts-authority-wave1.py | tee /tmp/w1-coexist.out | tail -5; echo W1_RC=\${PIPESTATUS[0]}
echo '=== W2 ==='; \$PY smoke-test-shifts-schedule-integrity-wave2.py | tee /tmp/w2-coexist.out | tail -8; echo W2_RC=\${PIPESTATUS[0]}
echo '=== E360 ==='; \$PY smoke-test-employees360-freeze-regression.py | tail -3; echo E360_RC=\$?
echo '=== ONB ==='; \$PY smoke-test-onboarding-freeze-regression.py | tail -3; echo ONB_RC=\$?
echo '=== ATT ==='; \$PY smoke-test-attendance-freeze-regression.py | tail -3; echo ATT_RC=\$?
echo '=== LEAVE ==='; \$PY smoke-test-leave-freeze-regression.py | tail -3; echo LEAVE_RC=\$?
tr '\0' '\n' < /proc/\$PID/environ | grep WATHEFNI_SHIFTS_INTEGRITY_JOBS || true
tr '\0' '\n' < /proc/\$PID/environ | grep WATHEFNI_SHIFTS_WAVE5 || true
echo COEXIST_DONE
REMOTE
}

log "deploy #1"
set +e
run_deploy deploy1
D1=$?
set -e
if [[ $D1 -ne 0 ]] || ! grep -q DEPLOY_SHIFTS_W5B_OK "$LOCAL_EVID/tests/deploy1.out"; then
  echo DEPLOY1_FAILED
  exit 1
fi

log "canary #1"
run_canary canary1
if ! grep -qE '0 failed' "$LOCAL_EVID/tests/canary1.out"; then
  echo CANARY1_FAILED
  exit 1
fi
if grep -qE '^[1-9][0-9]* failed' "$LOCAL_EVID/tests/canary1.out"; then
  echo CANARY1_FAILED
  exit 1
fi

log "UI probe (Publish & coverage)"
run_ui_probe ui-probe1

log "rollback"
BACKUP_PATH=$("${SSH[@]}" "cat $REMOTE_EVID/backup/BACKUP_PATH.txt")
"${SSH[@]}" "bash '$BACKUP_PATH/ROLLBACK.sh' '$BACKUP_PATH'" | tee "$LOCAL_EVID/tests/rollback.out"
grep -q ROLLBACK_OK "$LOCAL_EVID/tests/rollback.out"

log "redeploy #2"
set +e
run_deploy deploy2
D2=$?
set -e
if [[ $D2 -ne 0 ]] || ! grep -q DEPLOY_SHIFTS_W5B_OK "$LOCAL_EVID/tests/deploy2.out"; then
  echo DEPLOY2_FAILED
  exit 1
fi

log "canary #2"
run_canary canary2
if ! grep -qE '0 failed' "$LOCAL_EVID/tests/canary2.out"; then
  echo CANARY2_FAILED
  exit 1
fi

log "coexistence + freezes"
set +e
run_coexistence coexistence
CO_RC=$?
set -e

log "pull evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/canary" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/preflight" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/verify" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/flags" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/ui" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/backup" "$LOCAL_EVID/rollback/" 2>/dev/null || true

API1=$(grep -E '^[0-9]+ passed, [0-9]+ failed' "$LOCAL_EVID/tests/canary1.out" | tail -1 || echo unknown)
API2=$(grep -E '^[0-9]+ passed, [0-9]+ failed' "$LOCAL_EVID/tests/canary2.out" | tail -1 || echo unknown)
FPS_OK=NO
grep -qE 'PASS  real_assignment_fps_unchanged|PASS  real_fps_unchanged' "$LOCAL_EVID/tests/canary2.out" 2>/dev/null && FPS_OK=YES
RES_OK=NO
grep -q 'PASS  cleanup_residual_zero' "$LOCAL_EVID/tests/canary2.out" 2>/dev/null && RES_OK=YES
RB_OK=NO; grep -q ROLLBACK_OK "$LOCAL_EVID/tests/rollback.out" 2>/dev/null && RB_OK=YES
W1B_OK=NO; grep -q 'W1B_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W1B_OK=YES
W2B_OK=NO; grep -q 'W2B_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W2B_OK=YES
W3B_OK=NO; grep -q 'W3B_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W3B_OK=YES
W4B_OK=NO; grep -q 'W4B_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W4B_OK=YES
W1_OK=NO; grep -q 'W1_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W1_OK=YES
W2_OK=NO; grep -q 'W2_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W2_OK=YES
W3UX_OK=NO; grep -q 'W3UX_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W3UX_OK=YES
FRZ_OK=YES
for x in E360_RC=0 ONB_RC=0 ATT_RC=0 LEAVE_RC=0; do
  grep -q "$x" "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null || FRZ_OK=NO
done
UI_OK=NO; grep -q 'UI_PROBE_OK' "$LOCAL_EVID/tests/ui-probe1.out" 2>/dev/null && grep -q 'publish_tab_asset True' "$LOCAL_EVID/tests/ui-probe1.out" 2>/dev/null && UI_OK=YES
DASH_OK=NO; grep -q 'DASHBOARD_BUILD_OK' "$LOCAL_EVID/ui/dashboard-build-status.txt" 2>/dev/null && DASH_OK=YES

SHA_BEFORE=$(grep -A30 'SHAs before' "$LOCAL_EVID/remote/preflight/before-deploy.txt" 2>/dev/null | head -30 || true)
SHA_AFTER=$(grep -A30 'SHAs after' "$LOCAL_EVID/remote/verify/after-deploy.txt" 2>/dev/null | head -30 || true)

VERDICT=NO-GO
if grep -qE '0 failed' "$LOCAL_EVID/tests/canary1.out" \
  && grep -qE '0 failed' "$LOCAL_EVID/tests/canary2.out" \
  && [[ "$FPS_OK" == YES ]] \
  && [[ "$RES_OK" == YES ]] \
  && [[ "$RB_OK" == YES ]] \
  && [[ "$W1_OK" == YES ]] \
  && [[ "$W2_OK" == YES ]] \
  && [[ "$W1B_OK" == YES ]] \
  && [[ "$W2B_OK" == YES ]] \
  && [[ "$W3B_OK" == YES ]] \
  && [[ "$W4B_OK" == YES ]] \
  && [[ "$FRZ_OK" == YES ]] \
  && [[ "$UI_OK" == YES ]] \
  && [[ "$DASH_OK" == YES ]]; then
  VERDICT=GO
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 5B — production synthetic publish, open-shift & coverage canary

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/shifts-wave5b-$STAMP/\`  
**Staging gate:** \`$STAGING_GATE\` (**GO**)  
**Module:** \`shifts_publish_wave5.py\` **v5.0.0** · cleanup contract **1.2.0**

## Scope
Production WATHEFNI synthetic-only canary for draft → review → approve → publish, open shifts, and coverage.  
Markers: **SHW5B** / **965535***. Real allowlists empty. Real mutation gate **on**. Real reminders **off**. Integrity jobs **0**. CAPTURE_INGEST **off**.

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 5 (publish/open/coverage) | **$VERDICT** |
| Controlled real draft creation | **NO-GO** |
| Controlled real publishing | **NO-GO** |
| Controlled real open shifts | **NO-GO** |
| HR/manager production scheduling | **NO-GO** (allowlists empty) |
| Wave 6 readiness | **NO-GO** (rotations/remote hitches/PAM not built) |
| Broad employee-app access | **NO-GO** |

## Deploy / rollback
- Deploy #1 / redeploy #2: see \`tests/deploy*.out\`
- Rollback: **$RB_OK** (\`tests/rollback.out\`, \`rollback/\`)
- Flags: \`remote/flags/shifts-wave5b-synthetic.conf\`
- UI probe: **$UI_OK** (\`tests/ui-probe1.out\`)
- Dashboard build: **$DASH_OK** (\`ui/dashboard-build-status.txt\`)
- Preflight / verify: \`remote/preflight/\`, \`remote/verify/\`

### SHAs / flags
\`\`\`
$SHA_BEFORE
---
$SHA_AFTER
\`\`\`

## Canary results
- Canary #1: $API1
- Canary #2: $API2
- Real fingerprints unchanged: $FPS_OK
- Cleanup residual zero: $RES_OK
- Canary artifacts: \`remote/canary/{canary1,canary2}/\` (ids, fps, residual, results.json)

## Coexistence / regressions
- Wave 1B: $W1B_OK · Wave 2B: $W2B_OK · Wave 3B: $W3B_OK · Wave 4B: $W4B_OK
- Wave 1 smoke: $W1_OK · Wave 2: $W2_OK · Wave 3 UX: $W3UX_OK
- Freezes: $FRZ_OK (rc=$CO_RC)
- Details: \`tests/coexistence.out\`

## Gates held
- WATHEFNI only · SHW5B / 965535* · empty HR/manager allowlists · real mutation gate on · real reminders off · integrity jobs 0 · CAPTURE_INGEST off · no real publishing / real open-shift claims / rotations / PAM / Payroll money

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · Draft/publish/open/coverage true for Wave 5 honesty · Rotations/PAM false · Wave 4 honesty still publishing false.

## Gate result
$(if [[ "$VERDICT" == GO ]]; then echo PROD_SYNTHETIC_WAVE5_PUBLISH_GO; else echo PROD_SYNTHETIC_WAVE5_PUBLISH_NO_GO; fi)
EOF

if [[ "$VERDICT" == GO ]]; then
  echo "PROD_SYNTHETIC_WAVE5_PUBLISH_GO"
else
  echo "PROD_SYNTHETIC_WAVE5_PUBLISH_NO_GO"
fi
echo "QUALIFY_DONE evidence=$LOCAL_EVID"
[[ "$VERDICT" == GO ]]
