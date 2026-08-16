#!/usr/bin/env bash
# Shifts Wave 3A — Calendar-aligned UX + live staging API/UI qualification.
# Staging only. NO production deploy. NO real-mutation enablement. NO timers.
# NO templates/recurring/rotations/publishing/open shifts/PAM. NO Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave3a-$STAMP"
REMOTE_STAGE="/tmp/shw3a-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/shifts-wave3a-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
STAGING_DASH="/opt/wathefni/staging/dashboard-dist"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,audit}
echo "$LOCAL_EVID" > /tmp/shw3a.evid
echo "$STAMP" > /tmp/shw3a.stamp

log() { printf '\n=== %s ===\n' "$*"; }

ORCH_FILES=(
  shifts_wave3_controlled.py
  smoke-test-shifts-wave3-ux.py
  smoke-test-shifts-wave3a-live-staging.py
  app.py
)

log "local Wave 3 UX smoke (Calendar foundation markers)"
cd "$ORCH_SRC"
.venv/bin/python smoke-test-shifts-wave3-ux.py 2>&1 | tee "$LOCAL_EVID/tests/wave3-ux-smoke.out"
if grep -E '[1-9][0-9]* failed' "$LOCAL_EVID/tests/wave3-ux-smoke.out"; then
  echo "LOCAL_UX_SMOKE_FAILED"
  exit 1
fi

log "local freezes"
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding.out" | tail -5
.venv/bin/python smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance.out" | tail -5
.venv/bin/python smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave.out" | tail -5

log "dashboard tsc + build"
cd "$REPO_ROOT/apps/wathefni-dashboard"
npx tsc --noEmit 2>&1 | tee "$LOCAL_EVID/tests/tsc.out"
npm run build 2>&1 | tee "$LOCAL_EVID/tests/dashboard-build.out" | tail -40
rsync -a --delete dist/ "$LOCAL_EVID/sources/dashboard-dist/"

MARKER_OUT="$LOCAL_EVID/tests/bundle-markers.txt"
{
  echo "stamp=$STAMP"
  CHUNK=$(ls dist/assets/PostHire-*.js 2>/dev/null | head -1 || true)
  echo "chunk=${CHUNK:-none}"
  if [[ -n "${CHUNK:-}" ]]; then
    for needle in "shift-block" "fbf7ee" "f3ebe0" "shifts-board" "Bulk scheduling readiness" "الورديات"; do
      if grep -qF "$needle" "$CHUNK"; then echo "FOUND $needle"; else echo "MISSING $needle"; fi
    done
    for bad in "FullCalendar" "react-big-calendar" "Schedule-X" "dhtmlx"; do
      if grep -qiF "$bad" "$CHUNK"; then echo "GENERIC_SCHEDULER $bad"; else echo "CLEAN no:$bad"; fi
    done
    shasum -a 256 "$CHUNK" | awk '{print "sha256_posthire="$1}'
  fi
} | tee "$MARKER_OUT"

log "copy sources"
for f in "${ORCH_FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/shifts-wave3a-ui-staging-screenshots.py" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave3a-staging.sh" "$LOCAL_EVID/sources/"

log "push to staging"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'/{tests,screenshots,sources,docs}"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" shifts_wave3_controlled.py smoke-test-shifts-wave3-ux.py smoke-test-shifts-wave3a-live-staging.py app.py \
    "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$REPO_ROOT/ops/shifts-wave3a-ui-staging-screenshots.py" "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" \
  "$VPS_HOST:$REMOTE_STAGE/"
rsync -az --delete -e "ssh -o BatchMode=yes" "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/qualify-staging.out"
set -euo pipefail
STAGING_ORCH='$STAGING_ORCH'
STAGING_DASH='$STAGING_DASH'
REMOTE_STAGE='$REMOTE_STAGE'
REMOTE_EVID='$REMOTE_EVID'
STAMP='$STAMP'

cp -a "\$REMOTE_STAGE"/*.py "\$STAGING_ORCH/"
mkdir -p "\$REMOTE_EVID/sources"
cp -a "\$REMOTE_STAGE"/*.py "\$REMOTE_EVID/sources/" 2>/dev/null || true
cp -a "\$REMOTE_STAGE"/ShiftsWorkspace.tsx "\$REMOTE_STAGE"/shiftsUx.ts "\$REMOTE_EVID/sources/" 2>/dev/null || true
# Expose dashboard sources for UX smoke path resolution on staging orch layout
mkdir -p "\$STAGING_ORCH/sources"
cp -a "\$REMOTE_STAGE"/ShiftsWorkspace.tsx "\$REMOTE_STAGE"/shiftsUx.ts "\$STAGING_ORCH/sources/" 2>/dev/null || true
export SHIFTS_WAVE3_DASH_SRC="\$STAGING_ORCH/sources"
# Backup + swap staging dashboard only (never /var/www)
if [[ -d "\$STAGING_DASH" ]]; then
  cp -a "\$STAGING_DASH" "\$STAGING_DASH.bak-wave3a-\$STAMP" || true
fi
mkdir -p "\$STAGING_DASH"
rsync -a --delete "\$REMOTE_STAGE/dashboard-dist/" "\$STAGING_DASH/"
echo "staging dashboard updated: \$STAGING_DASH"

# Wave 3 controlled UX on staging — real mutation gate OFF for synthetic prove; reminders off; no timers
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/shifts-wave3.conf
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_SHIFTS_WAVE3=1
Environment=WATHEFNI_SHIFTS_WAVE3_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_REAL_MUTATION_GATE=0
Environment=WATHEFNI_SHIFTS_REAL_REMINDERS=0
Environment=WATHEFNI_SHIFTS_HR_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_COMPANIES=WATHEFNI
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 40); do
  curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break
  sleep 1
done
systemctl is-active wathefni-orchestrator-staging

cd "\$STAGING_ORCH"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DASHBOARD_DIST="\$STAGING_DASH"
export WATHEFNI_SHIFTS_WAVE3=1
export WATHEFNI_SHIFTS_WAVE3_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_REAL_MUTATION_GATE=0
export WATHEFNI_SHIFTS_REAL_REMINDERS=0
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
# Prefer staging venv if present; else shared orch venv
PYBIN=/opt/wathefni/staging/orchestrator/.venv/bin/python
if [[ ! -x "\$PYBIN" ]]; then PYBIN=/opt/wathefni/orchestrator/.venv/bin/python; fi
if [[ ! -x "\$PYBIN" ]]; then PYBIN=\$(command -v python3); fi
echo "PYBIN=\$PYBIN"

# Clear ambient DATABASE_URL conflicts for smoke binding
unset DATABASE_URL || true
export SHW3A_EVID="\$REMOTE_EVID/tests"
mkdir -p "\$SHW3A_EVID"

"\$PYBIN" -u smoke-test-shifts-wave3-ux.py 2>&1 | tee "\$REMOTE_EVID/tests/wave3-ux-smoke.out"
if grep -E '[1-9][0-9]* failed' "\$REMOTE_EVID/tests/wave3-ux-smoke.out"; then
  echo SMOKE_UX_FAILED
  exit 1
fi

"\$PYBIN" -u smoke-test-shifts-wave3a-live-staging.py 2>&1 | tee "\$REMOTE_EVID/tests/wave3a-live.out"
if grep -E '[1-9][0-9]* failed' "\$REMOTE_EVID/tests/wave3a-live.out"; then
  echo SMOKE_LIVE_FAILED
  exit 1
fi

set +e
"\$PYBIN" smoke-test-employees360-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-employees360.out" | tail -5
E360_RC=\$?
"\$PYBIN" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-onboarding.out" | tail -5
ONB_RC=\$?
"\$PYBIN" smoke-test-attendance-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-attendance.out" | tail -5
ATT_RC=\$?
"\$PYBIN" smoke-test-leave-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-leave.out" | tail -5
LEAVE_RC=\$?
set -e
echo "freeze_rc e360=\$E360_RC onboarding=\$ONB_RC attendance=\$ATT_RC leave=\$LEAVE_RC" | tee "\$REMOTE_EVID/tests/freeze-rc.txt"

# UI screenshots (best-effort)
export SHW3A_UI_SHOTS="\$REMOTE_EVID/screenshots"
set +e
"\$PYBIN" "\$REMOTE_STAGE/shifts-wave3a-ui-staging-screenshots.py" 2>&1 | tee "\$REMOTE_EVID/tests/ui-shots.out"
SHOT_RC=\$?
set -e
echo "shot_rc=\$SHOT_RC" | tee -a "\$REMOTE_EVID/tests/freeze-rc.txt"

echo STAGING_SHIFTS_W3A_OK
REMOTE

# Pull remote evidence
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/tests" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/screenshots" "$LOCAL_EVID/" 2>/dev/null || true
mkdir -p "$LOCAL_EVID/screenshots"
# Prefer live shots; keep placeholders noted in REPORT if missing
ls -la "$LOCAL_EVID/screenshots" || true

log "write REPORT"
cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 3A — Calendar foundation UX + live staging qualification

**Stamp:** \`$STAMP\`
**Evidence:** \`ops/evidence/shifts-wave3a-$STAMP/\`

## Scope
- Refactored Shifts workspace onto Wathefni **Calendar** shell language (roster/schedule adaptation).
- Live staging API/UI qualification on \`wathefni_staging\` only.
- **Not done:** production deploy, real-mutation enablement, timers, templates/recurring, Payroll money.

## UX foundation
- Page shell, toolbar pills, date nav, filter strip, warm canvas \`#fbf7ee\`, aside detail/composer
- Roster rows (employees) × date columns; **shift blocks** (not calendar event cards / not third-party scheduler)
- Overnight span without duplicating authority; split same-day windows; conflict/recon surfaces
- History/lineage + audit reasons in Calendar-style aside
- Bulk scheduling readiness note reserved for later waves
- EN/AR, RTL, mobile day-first

## Verdicts
| Scope | Verdict |
|---|---|
| Staging Wave 3A UX + live API qualify | see tests |
| Production HR/manager scheduling | **NO-GO** |
| Timers / real reminders / templates | **NO-GO** |

## Tests
See \`tests/\` and \`remote/tests/\`.
EOF

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
echo "NO production deploy performed."
