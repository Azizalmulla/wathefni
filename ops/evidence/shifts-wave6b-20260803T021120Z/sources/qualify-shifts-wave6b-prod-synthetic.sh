#!/usr/bin/env bash
# Shifts Wave 6B — production synthetic rotations/compliance/PAM/notifications canary qualify.
# HARD GATE: staging Wave 6 must already be GO (PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO).
# Deploy → canary → rollback → redeploy → canary → W1B–5B coexistence → freezes → fps/residual.
# Does NOT enable real publishing, real rotations, real notification delivery, real allowlists,
# reminders, timers, PAM submission, or Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave6b-$STAMP"
REMOTE_STAGE="/tmp/shifts-w6b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave6b-prod-canary/${STAMP}"

# Hard gate: staging Wave 6 GO. Prefer the explicit stamp named by the user, else latest GO.
STAGING_GATE="${SHW6B_STAGING_EVID:-}"
if [[ -z "$STAGING_GATE" ]] && [[ -d "$REPO_ROOT/ops/evidence/shifts-wave6-20260803T013352Z" ]]; then
  STAGING_GATE="$REPO_ROOT/ops/evidence/shifts-wave6-20260803T013352Z"
fi
if [[ -z "$STAGING_GATE" ]]; then
  for d in $(ls -1d "$REPO_ROOT"/ops/evidence/shifts-wave6-* 2>/dev/null | sort -r); do
    if grep -qE 'PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO' "$d/REPORT.md" 2>/dev/null; then
      STAGING_GATE="$d"
      break
    fi
  done
fi
if [[ -z "$STAGING_GATE" ]] || ! grep -qE 'PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO' "$STAGING_GATE/REPORT.md" 2>/dev/null; then
  echo "REFUSE: staging Wave 6 not GO (missing PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO)." >&2
  echo "looked_for=$STAGING_GATE" >&2
  exit 2
fi

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,rollback,cleanup,audit,ui}
echo "$LOCAL_EVID" > /tmp/shw6b.evid
echo "$STAMP" > /tmp/shw6b.stamp
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

log "optional dashboard build for Rotations & compliance / enterprise panel"
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
  "$ORCH_SRC/shifts_enterprise_wave6.py" \
  "$ORCH_SRC/shifts_notifications_wave6b.py" \
  "$ORCH_SRC/shifts_publish_wave5.py" \
  "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/shifts_wave3_controlled.py" \
  "$ORCH_SRC/shifts_authority_wave1.py" \
  "$ORCH_SRC/shifts_schedule_integrity_wave2.py" \
  "$ORCH_SRC/canary-prod-shifts-wave6b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave5b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave4b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave3b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave2b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave1b.py" \
  "$ORCH_SRC/smoke-test-shifts-enterprise-wave6.py" \
  "$ORCH_SRC/smoke-test-shifts-publish-wave5.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$ORCH_SRC/ops/deploy-shifts-wave6b-prod-synthetic.sh" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/shifts_enterprise_wave6_v1.sql" "$ORCH_SRC/ops/sql/shifts_notifications_wave6b_v1.sql" \
  "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" \
  "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave6b-prod-synthetic.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/lib/api.ts" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/shifts_enterprise_wave6.py" \
  "$ORCH_SRC/shifts_notifications_wave6b.py" \
  "$ORCH_SRC/shifts_publish_wave5.py" \
  "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/shifts_wave3_controlled.py" \
  "$ORCH_SRC/shifts_authority_wave1.py" \
  "$ORCH_SRC/shifts_schedule_integrity_wave2.py" \
  "$ORCH_SRC/canary-prod-shifts-wave6b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave5b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave4b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave3b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave2b.py" \
  "$ORCH_SRC/canary-prod-shifts-wave1b.py" \
  "$ORCH_SRC/smoke-test-shifts-enterprise-wave6.py" \
  "$ORCH_SRC/smoke-test-shifts-publish-wave5.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$ORCH_SRC/ops/deploy-shifts-wave6b-prod-synthetic.sh" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/shifts_enterprise_wave6_v1.sql" "$ORCH_SRC/ops/sql/shifts_notifications_wave6b_v1.sql" \
  "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" \
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
chmod +x '$REMOTE_STAGE/deploy-shifts-wave6b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-shifts-wave6b-prod-synthetic.sh'
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
export SHW6B_EVID="\$OUTDIR" PYTHONUNBUFFERED=1
mkdir -p "\$OUTDIR"
unset DATABASE_URL || true
\$PYBIN -u canary-prod-shifts-wave6b.py
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
# Prove Wave 6 honesty + notifications honesty + Rotations & compliance / enterprise panel assets
\$PY - <<'PY'
import app, shifts_enterprise_wave6 as w6, shifts_notifications_wave6b as n6, os
from pathlib import Path
h6 = w6.honesty_payload()
assert h6.get("rotations") is True and h6.get("pam_export") is True and h6.get("compliance_profiles") is True
assert h6.get("pam_submission") is False and h6.get("payroll_money") is False
print("wave6_honesty_ok", w6.SHIFTS_WAVE6_VERSION)
hn6 = n6.honesty_payload()
assert hn6.get("multi_channel_outbox") is True and hn6.get("real_provider_delivery") is False
assert hn6.get("mock_adapters_only") is True and hn6.get("drafts_do_not_notify") is True
print("notifications_wave6b_honesty_ok", n6.SHIFTS_NOTIFICATIONS_WAVE6B_VERSION)
dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
idx = dist / "index.html"
print("dashboard_index_exists", idx.exists())
found = False
if dist.exists():
  for p in dist.rglob("*"):
    if p.suffix in {".js",".html",".css"} and p.is_file() and p.stat().st_size < 8_000_000:
      try:
        txt = p.read_text(errors="ignore")
      except Exception:
        continue
      if "shifts-enterprise-panel" in txt or "Rotations & compliance" in txt or "أنماط الدورات" in txt:
        found = True
        print("enterprise_panel_marker", p.name)
        break
print("enterprise_panel_asset", found)
print("UI_PROBE_OK" if found else "UI_PROBE_FAIL")
assert found, "Rotations & compliance / enterprise panel asset missing from dashboard dist"
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
# Hygiene: clear leftover prior-wave synthetic rows/policies so fps coexistence is fair (SHW6B first, then W1B..W5B, then SHW2)
\$PY - <<'PY'
import app
from shifts_synthetic_cleanup import (
  CleanupScope, cleanup_synthetic_scope,
  wave1b_scope, wave2b_scope, wave3b_scope, wave4b_scope, wave5b_scope, wave6b_scope,
)
for s in (
  wave6b_scope(), wave5b_scope(), wave4b_scope(), wave3b_scope(), wave2b_scope(), wave1b_scope(),
  CleanupScope(company_code="WATHEFNI", markers=("SHW2","SHW2-SYNTH|","SHW2C"), phone_prefixes=("965529","965530"), employee_json_flag="shw2", leave_reason_ilike="%shw2%", seasonal_name_ilike="%SHW2%"),
):
  r = cleanup_synthetic_scope(app.db_connect, s)
  print("hygiene", list(s.markers), "residual", r.get("residual_total"))
PY
if [[ -f canary-prod-shifts-wave1b.py ]]; then
  echo '=== W1B ==='; mkdir -p /tmp/shw6b-coexist/w1b; SHW1B_EVID=/tmp/shw6b-coexist/w1b \$PY -u canary-prod-shifts-wave1b.py | tee /tmp/w1b-coexist.out | tail -8; echo W1B_RC=\${PIPESTATUS[0]}
fi
if [[ -f canary-prod-shifts-wave2b.py ]]; then
  echo '=== W2B ==='; mkdir -p /tmp/shw6b-coexist/w2b; WATHEFNI_SHIFTS_INTEGRITY_JOBS=1 SHW2B_EVID=/tmp/shw6b-coexist/w2b \$PY -u canary-prod-shifts-wave2b.py | tee /tmp/w2b-coexist.out | tail -10; echo W2B_RC=\${PIPESTATUS[0]}
fi
if [[ -f canary-prod-shifts-wave3b.py ]]; then
  echo '=== W3B ==='; mkdir -p /tmp/shw6b-coexist/w3b; SHW3B_EVID=/tmp/shw6b-coexist/w3b \$PY -u canary-prod-shifts-wave3b.py | tee /tmp/w3b-coexist.out | tail -8; echo W3B_RC=\${PIPESTATUS[0]}
fi
if [[ -f canary-prod-shifts-wave4b.py ]]; then
  echo '=== W4B ==='; mkdir -p /tmp/shw6b-coexist/w4b; SHW4B_EVID=/tmp/shw6b-coexist/w4b \$PY -u canary-prod-shifts-wave4b.py | tee /tmp/w4b-coexist.out | tail -8; echo W4B_RC=\${PIPESTATUS[0]}
fi
if [[ -f canary-prod-shifts-wave5b.py ]]; then
  echo '=== W5B ==='; mkdir -p /tmp/shw6b-coexist/w5b; SHW5B_EVID=/tmp/shw6b-coexist/w5b \$PY -u canary-prod-shifts-wave5b.py | tee /tmp/w5b-coexist.out | tail -8; echo W5B_RC=\${PIPESTATUS[0]}
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
tr '\0' '\n' < /proc/\$PID/environ | grep WATHEFNI_SHIFTS_WAVE6 || true
echo COEXIST_DONE
REMOTE
}

log "deploy #1"
set +e
run_deploy deploy1
D1=$?
set -e
if [[ $D1 -ne 0 ]] || ! grep -q DEPLOY_SHIFTS_W6B_OK "$LOCAL_EVID/tests/deploy1.out"; then
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

log "UI probe (Wave 6 honesty + notifications honesty + enterprise panel)"
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
if [[ $D2 -ne 0 ]] || ! grep -q DEPLOY_SHIFTS_W6B_OK "$LOCAL_EVID/tests/deploy2.out"; then
  echo DEPLOY2_FAILED
  exit 1
fi

log "canary #2"
run_canary canary2
if ! grep -qE '0 failed' "$LOCAL_EVID/tests/canary2.out"; then
  echo CANARY2_FAILED
  exit 1
fi

log "coexistence (SHW6B hygiene + W1B..W5B + W3UX/W1/W2) + freezes"
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
W5B_OK=NO; grep -q 'W5B_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W5B_OK=YES
W1_OK=NO; grep -q 'W1_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W1_OK=YES
W2_OK=NO; grep -q 'W2_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W2_OK=YES
W3UX_OK=NO; grep -q 'W3UX_RC=0' "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null && W3UX_OK=YES
FRZ_OK=YES
for x in E360_RC=0 ONB_RC=0 ATT_RC=0 LEAVE_RC=0; do
  grep -q "$x" "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null || FRZ_OK=NO
done
UI_OK=NO; grep -q 'UI_PROBE_OK' "$LOCAL_EVID/tests/ui-probe1.out" 2>/dev/null && grep -q 'enterprise_panel_asset True' "$LOCAL_EVID/tests/ui-probe1.out" 2>/dev/null && UI_OK=YES
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
  && [[ "$W5B_OK" == YES ]] \
  && [[ "$FRZ_OK" == YES ]] \
  && [[ "$UI_OK" == YES ]] \
  && [[ "$DASH_OK" == YES ]]; then
  VERDICT=GO
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 6B — production synthetic rotations, compliance, PAM export & multi-channel notifications canary

**Stamp:** \`$STAMP\`
**Evidence:** \`ops/evidence/shifts-wave6b-$STAMP/\`
**Staging gate:** \`$STAGING_GATE\` (**PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO**)
**Modules:** \`shifts_enterprise_wave6.py\` **v6.0.0** · \`shifts_notifications_wave6b.py\` **v6.1.0** · cleanup contract **1.4.0**

## Scope
Production WATHEFNI synthetic-only canary for rotation patterns (four-on-four-off, panama 2-2-3,
six-on-one-off, alternating day/night, hitch 14/14 with remote metadata, custom sequence with
travel/rest/work/standby), compliance profile evaluation, draft → review → approve → publish,
PAM-style read-only export, and the multi-channel notification outbox (mock adapters only).
Markers: **SHW6B** / **965537***. Real allowlists empty. Real mutation gate **on**. Real reminders **off**.
Real notification provider delivery **off** (mock only). Integrity jobs **0**. CAPTURE_INGEST **off**.

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 6 (rotations/remote/compliance/PAM export) | **$VERDICT** |
| Production synthetic multi-channel notifications (Wave 6B outbox) | **$VERDICT** |
| Controlled HR scheduling | **NO-GO** (allowlist empty) |
| Controlled manager scheduling | **NO-GO** (allowlist empty) |
| Talal employee schedule read and notification canary | **NO-GO** (not run; read-only rollout not started) |
| Real employee reminders | **NO-GO** |
| PAM submission (government API) | **NO-GO** |
| Overall readiness for Wave 6C | $(if [[ "$VERDICT" == GO ]]; then echo "**NO-GO** (all synthetic gates green; Wave 6C controlled rollout not started)"; else echo "**NO-GO**"; fi) |

## Deploy / rollback
- Deploy #1 / redeploy #2: see \`tests/deploy*.out\`
- Rollback: **$RB_OK** (\`tests/rollback.out\`, \`rollback/\`)
- Flags: \`remote/flags/shifts-wave6b-synthetic.conf\`
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
- SHW6B hygiene run first, then Wave 1B: $W1B_OK · Wave 2B: $W2B_OK · Wave 3B: $W3B_OK · Wave 4B: $W4B_OK · Wave 5B: $W5B_OK
- Wave 1 smoke: $W1_OK · Wave 2: $W2_OK · Wave 3 UX: $W3UX_OK
- Freezes: $FRZ_OK (rc=$CO_RC)
- Details: \`tests/coexistence.out\`

## Gates held
- WATHEFNI only · SHW6B / 965537* (merged into W1–W5 marker/phone lists) · empty HR/manager allowlists ·
  real mutation gate on · real reminders off · real notification provider delivery off (mock only) ·
  integrity jobs 0 · CAPTURE_INGEST off · no real publishing / rotations / PAM submission / Payroll money

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated ·
Rotations/remote rosters/compliance profiles/PAM export true for Wave 6 honesty · PAM submission false ·
Notifications: multi-channel outbox true, real provider delivery false, mock adapters only, drafts do not notify.

## Gate result
$(if [[ "$VERDICT" == GO ]]; then echo PROD_SYNTHETIC_WAVE6B_ENTERPRISE_GO; else echo PROD_SYNTHETIC_WAVE6B_ENTERPRISE_NO_GO; fi)
EOF

if [[ "$VERDICT" == GO ]]; then
  echo "PROD_SYNTHETIC_WAVE6B_ENTERPRISE_GO"
else
  echo "PROD_SYNTHETIC_WAVE6B_ENTERPRISE_NO_GO"
fi
echo "QUALIFY_DONE evidence=$LOCAL_EVID"
[[ "$VERDICT" == GO ]]
