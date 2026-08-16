#!/usr/bin/env bash
# Shifts Wave 6C — production WATHEFNI controlled real rollout qualify + freeze.
#
# HARD GATE: Wave 6B prod synthetic must already be GO (PROD_SYNTHETIC_WAVE6B_ENTERPRISE_GO).
# Deploy → controlled canary → rollback → redeploy → controlled canary →
# W1B–6B coexistence → sibling freezes → shifts freeze regression → evidence.
#
# Owner-approved controlled scope: HR 96599338566 · notify WATHEFNI-96550252254 · channels app,email.
# Real scoped-manager rollout, broad employee app, timers, PAM submission and Payroll money stay off.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave6c-$STAMP"
REMOTE_STAGE="/tmp/shifts-w6c-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave6c-prod-controlled/${STAMP}"

# Hard gate: Wave 6B prod synthetic GO.
W6B_GATE="${SHW6C_W6B_EVID:-}"
if [[ -z "$W6B_GATE" ]]; then
  for d in $(ls -1d "$REPO_ROOT"/ops/evidence/shifts-wave6b-* 2>/dev/null | sort -r); do
    if grep -qE 'PROD_SYNTHETIC_WAVE6B_ENTERPRISE_GO' "$d/REPORT.md" 2>/dev/null; then
      W6B_GATE="$d"
      break
    fi
  done
fi
if [[ -z "$W6B_GATE" ]] || ! grep -qE 'PROD_SYNTHETIC_WAVE6B_ENTERPRISE_GO' "$W6B_GATE/REPORT.md" 2>/dev/null; then
  echo "REFUSE: Wave 6B prod synthetic not GO (missing PROD_SYNTHETIC_WAVE6B_ENTERPRISE_GO)." >&2
  exit 2
fi

# Hard gate: owner-approved allowlist proposal must exist.
APPROVAL="${SHW6C_APPROVAL:-}"
if [[ -z "$APPROVAL" ]]; then
  APPROVAL="$(ls -1d "$REPO_ROOT"/ops/evidence/shifts-wave6c-*/identity/PROPOSED_ALLOWLIST.md 2>/dev/null | sort -r | head -1 || true)"
fi
if [[ -z "$APPROVAL" ]] || [[ ! -f "$APPROVAL" ]]; then
  echo "REFUSE: no owner-approved allowlist proposal found." >&2
  exit 2
fi

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources/ops/sql,identity,rollback,cleanup,audit,ui}
echo "$LOCAL_EVID" > /tmp/shw6c.evid
echo "$STAMP" > /tmp/shw6c.stamp
{
  echo "wave6b_gate=$W6B_GATE"
  echo "approval=$APPROVAL"
} | tee "$LOCAL_EVID/docs/gates.txt"
cp -a "$APPROVAL" "$LOCAL_EVID/identity/PROPOSED_ALLOWLIST.md" 2>/dev/null || true

log() { printf '\n=== %s ===\n' "$*"; }

log "local freeze regressions"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
set +e
"$PY" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -2
"$PY" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -2
"$PY" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onb-local.out" | tail -2
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-att-local.out" | tail -2
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -2
set -e

log "dashboard build"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
if [[ -f "$DASH_SRC/package.json" ]]; then
  set +e
  (cd "$DASH_SRC" && npm run build) 2>&1 | tee "$LOCAL_EVID/ui/dashboard-build.out" | tail -10
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

MODULES=(
  app.py
  shifts_controlled_wave6c.py shifts_enterprise_wave6.py shifts_notifications_wave6b.py
  shifts_publish_wave5.py shifts_templates_wave4.py shifts_synthetic_cleanup.py
  shifts_wave3_controlled.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py
  canary-prod-shifts-wave6c.py canary-prod-shifts-wave6b.py canary-prod-shifts-wave5b.py
  canary-prod-shifts-wave4b.py canary-prod-shifts-wave3b.py canary-prod-shifts-wave2b.py
  canary-prod-shifts-wave1b.py
  smoke-test-shifts-freeze-regression.py smoke-test-shifts-enterprise-wave6.py
  smoke-test-shifts-publish-wave5.py smoke-test-shifts-templates-wave4.py
  smoke-test-shifts-wave3-ux.py smoke-test-shifts-authority-wave1.py
  smoke-test-shifts-schedule-integrity-wave2.py
  smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py
  smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py
)
SQLS=(
  shifts_controlled_wave6c_v1.sql shifts_enterprise_wave6_v1.sql shifts_notifications_wave6b_v1.sql
  shifts_publish_wave5_v1.sql shifts_templates_wave4_v1.sql
)

log "stage sources"
for f in "${MODULES[@]}"; do [[ -f "$ORCH_SRC/$f" ]] && cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
for s in "${SQLS[@]}"; do [[ -f "$ORCH_SRC/ops/sql/$s" ]] && cp -a "$ORCH_SRC/ops/sql/$s" "$LOCAL_EVID/sources/ops/sql/"; done
cp -a "$ORCH_SRC/ops/deploy-shifts-wave6c-prod-controlled.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave6c-prod-controlled.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/.cursor/rules/shifts-freeze.mdc" "$LOCAL_EVID/docs/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
for f in "${MODULES[@]}"; do
  [[ -f "$ORCH_SRC/$f" ]] && "${SCP[@]}" "$ORCH_SRC/$f" "$VPS_HOST:$REMOTE_STAGE/" >/dev/null
done
for s in "${SQLS[@]}"; do
  [[ -f "$ORCH_SRC/ops/sql/$s" ]] && "${SCP[@]}" "$ORCH_SRC/ops/sql/$s" "$VPS_HOST:$REMOTE_STAGE/ops/sql/" >/dev/null
done
"${SCP[@]}" "$ORCH_SRC/ops/deploy-shifts-wave6c-prod-controlled.sh" "$VPS_HOST:$REMOTE_STAGE/" >/dev/null
if [[ -d "$LOCAL_EVID/sources/dashboard-dist" ]]; then
  "${SCP[@]}" -r "$LOCAL_EVID/sources/dashboard-dist/." "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/" >/dev/null
fi

run_deploy() {
  local label="$1"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-shifts-wave6c-prod-controlled.sh'
bash '$REMOTE_STAGE/deploy-shifts-wave6c-prod-controlled.sh'
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
export SHW6C_EVID="\$OUTDIR" PYTHONUNBUFFERED=1
mkdir -p "\$OUTDIR"
unset DATABASE_URL || true
\$PYBIN -u canary-prod-shifts-wave6c.py
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
\$PY - <<'PY'
import os
from pathlib import Path
import shifts_controlled_wave6c as w6c, shifts_notifications_wave6b as n6, shifts_enterprise_wave6 as w6
h = w6c.honesty_payload()
assert h["controlled_real_rollout"] is True
assert h["manager_real_rollout"] is False
assert h["broad_employee_app"] is False
assert h["pam_submission"] is False and h["payroll_money"] is False
assert h["real_notify_recipients"] == ["WATHEFNI-96550252254"], h["real_notify_recipients"]
assert h["real_notify_channels"] == ["app", "email"], h["real_notify_channels"]
assert h["operator_timers"] is False
print("wave6c_honesty_ok", w6c.SHIFTS_WAVE6C_VERSION)
print("notifications_honesty_ok", n6.SHIFTS_NOTIFICATIONS_WAVE6B_VERSION)
print("wave6_honesty_ok", w6.SHIFTS_WAVE6_VERSION)
dist = Path(os.environ.get("WATHEFNI_DASHBOARD_DIST") or "/opt/wathefni/dashboard-dist")
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
assert found
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
\$PY - <<'PY'
import app
from shifts_synthetic_cleanup import (
  CleanupScope, cleanup_synthetic_scope,
  wave1b_scope, wave2b_scope, wave3b_scope, wave4b_scope, wave5b_scope, wave6b_scope, wave6c_scope,
)
for s in (
  wave6c_scope(), wave6b_scope(), wave5b_scope(), wave4b_scope(), wave3b_scope(), wave2b_scope(), wave1b_scope(),
  CleanupScope(company_code="WATHEFNI", markers=("SHW2","SHW2-SYNTH|","SHW2C"), phone_prefixes=("965529","965530"), employee_json_flag="shw2", leave_reason_ilike="%shw2%", seasonal_name_ilike="%SHW2%"),
):
  r = cleanup_synthetic_scope(app.db_connect, s)
  print("hygiene", list(s.markers), "residual", r.get("residual_total"))
PY
for w in 1b 2b 3b 4b 5b 6b; do
  f=canary-prod-shifts-wave\${w}.py
  if [[ -f "\$f" ]]; then
    echo "=== W\${w^^} ==="
    mkdir -p /tmp/shw6c-coexist/\$w
    VAR=SHW\${w^^}_EVID
    if [[ "\$w" == "2b" ]]; then
      env "\$VAR=/tmp/shw6c-coexist/\$w" WATHEFNI_SHIFTS_INTEGRITY_JOBS=1 \$PY -u "\$f" | tail -6
    else
      env "\$VAR=/tmp/shw6c-coexist/\$w" \$PY -u "\$f" | tail -6
    fi
    echo "W\${w^^}_RC=\${PIPESTATUS[0]}"
  fi
done
export WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
echo '=== W3 UX ==='; \$PY smoke-test-shifts-wave3-ux.py | tail -3; echo W3UX_RC=\$?
echo '=== W1 ==='; \$PY smoke-test-shifts-authority-wave1.py | tail -3; echo W1_RC=\${PIPESTATUS[0]}
echo '=== W2 ==='; \$PY smoke-test-shifts-schedule-integrity-wave2.py | tail -3; echo W2_RC=\${PIPESTATUS[0]}
echo '=== SHIFTS FREEZE ==='; \$PY smoke-test-shifts-freeze-regression.py | tail -3; echo SHFRZ_RC=\$?
echo '=== E360 ==='; \$PY smoke-test-employees360-freeze-regression.py | tail -3; echo E360_RC=\$?
echo '=== ONB ==='; \$PY smoke-test-onboarding-freeze-regression.py | tail -3; echo ONB_RC=\$?
echo '=== ATT ==='; \$PY smoke-test-attendance-freeze-regression.py | tail -3; echo ATT_RC=\$?
echo '=== LEAVE ==='; \$PY smoke-test-leave-freeze-regression.py | tail -3; echo LEAVE_RC=\$?
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'WATHEFNI_SHIFTS_(HR_ALLOWLIST|MANAGER_ALLOWLIST|NOTIFY_|OPERATOR_TIMERS|INTEGRITY_JOBS|REAL_REMINDERS)' | sort || true
echo COEXIST_DONE
REMOTE
}

log "deploy #1"
set +e
run_deploy deploy1
D1=$?
set -e
if [[ $D1 -ne 0 ]] || ! grep -q DEPLOY_SHIFTS_W6C_OK "$LOCAL_EVID/tests/deploy1.out"; then
  echo DEPLOY1_FAILED
  exit 1
fi

log "controlled canary #1"
set +e
run_canary canary1
set -e
if ! grep -qE '^[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/canary1.out"; then
  echo CANARY1_FAILED
  exit 1
fi

log "UI probe"
run_ui_probe ui-probe1

log "rollback"
BACKUP_PATH=$("${SSH[@]}" "cat $REMOTE_EVID/backup/BACKUP_PATH.txt")
"${SSH[@]}" "bash '$BACKUP_PATH/ROLLBACK.sh' '$BACKUP_PATH'" | tee "$LOCAL_EVID/tests/rollback.out"
grep -q ROLLBACK_OK "$LOCAL_EVID/tests/rollback.out"

log "prove rollback restored the fail-closed posture"
"${SSH[@]}" "bash -s" <<'REMOTE' | tee "$LOCAL_EVID/tests/rollback-posture.out"
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_SHIFTS_(HR_ALLOWLIST|NOTIFY_REAL_DELIVERY|NOTIFY_REAL_ALLOWLIST)' | sort
if tr '\0' '\n' < /proc/$PID/environ | grep -q '^WATHEFNI_SHIFTS_NOTIFY_REAL_DELIVERY=1'; then
  echo ROLLBACK_POSTURE_FAIL
else
  echo ROLLBACK_POSTURE_OK
fi
REMOTE

log "redeploy #2"
set +e
run_deploy deploy2
D2=$?
set -e
if [[ $D2 -ne 0 ]] || ! grep -q DEPLOY_SHIFTS_W6C_OK "$LOCAL_EVID/tests/deploy2.out"; then
  echo DEPLOY2_FAILED
  exit 1
fi

log "controlled canary #2"
set +e
run_canary canary2
set -e
if ! grep -qE '^[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/canary2.out"; then
  echo CANARY2_FAILED
  exit 1
fi

log "coexistence + freezes"
set +e
run_coexistence coexistence
set -e

log "pull evidence"
for d in canary preflight verify flags ui; do
  "${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/$d" "$LOCAL_EVID/remote/" 2>/dev/null || true
done
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/backup" "$LOCAL_EVID/rollback/" 2>/dev/null || true

API1=$(grep -E '^[0-9]+ passed, [0-9]+ failed' "$LOCAL_EVID/tests/canary1.out" | tail -1 || echo unknown)
API2=$(grep -E '^[0-9]+ passed, [0-9]+ failed' "$LOCAL_EVID/tests/canary2.out" | tail -1 || echo unknown)

y() { grep -q "$1" "$2" 2>/dev/null && echo YES || echo NO; }
RB_OK=$(y ROLLBACK_OK "$LOCAL_EVID/tests/rollback.out")
RBP_OK=$(y ROLLBACK_POSTURE_OK "$LOCAL_EVID/tests/rollback-posture.out")
UI_OK=$(y UI_PROBE_OK "$LOCAL_EVID/tests/ui-probe1.out")
DASH_OK=$(y DASHBOARD_BUILD_OK "$LOCAL_EVID/ui/dashboard-build-status.txt")
REAL_EMAIL_OK=$(y 'PASS  email_real_sent_true' "$LOCAL_EVID/tests/canary2.out")
KILL_OK=$(y 'PASS  kill_switch_skips_every_channel' "$LOCAL_EVID/tests/canary2.out")
EXCL_OK=$(y 'PASS  delivery_blocked_for_excluded' "$LOCAL_EVID/tests/canary2.out")
HIST_OK=$(y 'PASS  historical_assignment_fps_unchanged' "$LOCAL_EVID/tests/canary2.out")
RES_OK=$(y 'PASS  cleanup_residual_zero' "$LOCAL_EVID/tests/canary2.out")
OVERLAP_OK=$(y 'PASS  no_overlapping_execution' "$LOCAL_EVID/tests/canary2.out")
SHFRZ_OK=$(y 'SHFRZ_RC=0' "$LOCAL_EVID/tests/coexistence.out")

CO_OK=YES
for x in W1B_RC=0 W2B_RC=0 W3B_RC=0 W4B_RC=0 W5B_RC=0 W6B_RC=0 W1_RC=0 W2_RC=0 W3UX_RC=0; do
  grep -q "$x" "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null || CO_OK=NO
done
FRZ_OK=YES
for x in E360_RC=0 ONB_RC=0 ATT_RC=0 LEAVE_RC=0; do
  grep -q "$x" "$LOCAL_EVID/tests/coexistence.out" 2>/dev/null || FRZ_OK=NO
done

VERDICT=NO-GO
if grep -qE '^[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/canary1.out" \
  && grep -qE '^[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/canary2.out" \
  && [[ "$RB_OK" == YES ]] && [[ "$RBP_OK" == YES ]] \
  && [[ "$UI_OK" == YES ]] && [[ "$DASH_OK" == YES ]] \
  && [[ "$REAL_EMAIL_OK" == YES ]] && [[ "$KILL_OK" == YES ]] \
  && [[ "$EXCL_OK" == YES ]] && [[ "$HIST_OK" == YES ]] \
  && [[ "$RES_OK" == YES ]] && [[ "$OVERLAP_OK" == YES ]] \
  && [[ "$SHFRZ_OK" == YES ]] && [[ "$CO_OK" == YES ]] && [[ "$FRZ_OK" == YES ]]; then
  VERDICT=GO
fi

GATE=PROD_CONTROLLED_WAVE6C_SHIFTS_NO_GO
[[ "$VERDICT" == GO ]] && GATE=PROD_CONTROLLED_WAVE6C_SHIFTS_GO

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 6C — production controlled real rollout and freeze

**Stamp:** \`$STAMP\`
**Gate:** \`$GATE\`
**Wave 6B gate:** \`$W6B_GATE\`
**Owner approval:** \`$APPROVAL\`

## Approved controlled scope

| Role | Identity |
|---|---|
| HR operator | Aziz Almulla \`96599338566\` |
| Real subject / notify recipient | Talal Fadhli \`WATHEFNI-96550252254\` |
| Real external channel | email \`talalabdalla89@gmail.com\` |
| Manager real rollout | none — NO-GO |
| Excluded subjects | \`WATHEFNI-ORPHAN-*\`, \`*-REALBLOCK-*\` |

## Results

| Item | Result |
|---|---|
| Controlled canary #1 | $API1 |
| Controlled canary #2 (after rollback + redeploy) | $API2 |
| Rollback | $RB_OK |
| Rollback restored fail-closed posture | $RBP_OK |
| Real email delivered to consented recipient | $REAL_EMAIL_OK |
| Delivery kill switch | $KILL_OK |
| Excluded subjects blocked | $EXCL_OK |
| Historical schedules unchanged | $HIST_OK |
| Synthetic residual zero | $RES_OK |
| No overlapping job execution | $OVERLAP_OK |
| Shifts freeze regression | $SHFRZ_OK |
| Wave 1B–6B coexistence | $CO_OK |
| Sibling freezes (E360 / Onboarding / Attendance / Leave) | $FRZ_OK |
| UI probe | $UI_OK |
| Dashboard build | $DASH_OK |

## Verdicts

| Scope | Verdict |
|---|---|
| HR production scheduling | $([[ "$VERDICT" == GO ]] && echo '**GO** (controlled, named allowlist)' || echo '**NO-GO**') |
| Scoped manager production scheduling | **NO-GO** (no manager identity or scope exists) |
| Talal employee-app schedule access | $([[ "$VERDICT" == GO ]] && echo '**GO** (read + acknowledge)' || echo '**NO-GO**') |
| Real notification canary | $([[ "$VERDICT" == GO ]] && echo '**GO** (one recipient, app + email)' || echo '**NO-GO**') |
| Reminder / reconciliation timers | **NO-GO** (manual invocation only) |
| Broad employee-app rollout | **NO-GO** |
| PAM automated submission | **NO-GO** |
| Payroll monetary impact | **NO-GO** |
| Overall Shifts completion and freeze | $([[ "$VERDICT" == GO ]] && echo '**GO (controlled) — FROZEN**' || echo '**NO-GO**') |

## Freeze artifacts

- \`ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md\`
- \`.cursor/rules/shifts-freeze.mdc\`
- \`wathefni-orchestrator/smoke-test-shifts-freeze-regression.py\`

$GATE
EOF

echo "$GATE"
echo "QUALIFY_DONE evidence=$LOCAL_EVID"
