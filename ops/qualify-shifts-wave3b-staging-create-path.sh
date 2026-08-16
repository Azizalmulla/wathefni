#!/usr/bin/env bash
# Shifts Wave 3B — mandatory staging create-path / browser composer closure.
# Must GO before any production synthetic deploy.
# NO production deploy. NO real allowlists. NO timers. NO templates/Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave3b-staging-create-$STAMP"
REMOTE_STAGE="/tmp/shw3b-stg-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/shifts-wave3b-create-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
STAGING_DASH="/opt/wathefni/staging/dashboard-dist"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,audit}
echo "$LOCAL_EVID" > /tmp/shw3b-stg.evid
echo "$STAMP" > /tmp/shw3b-stg.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local UX smoke + freezes"
cd "$ORCH_SRC"
.venv/bin/python smoke-test-shifts-wave3-ux.py 2>&1 | tee "$LOCAL_EVID/tests/wave3-ux-smoke.out"
if grep -E '[1-9][0-9]* failed' "$LOCAL_EVID/tests/wave3-ux-smoke.out"; then
  echo LOCAL_UX_FAILED
  exit 1
fi
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360.out" | tail -2
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onb.out" | tail -2
.venv/bin/python smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-att.out" | tail -2
.venv/bin/python smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave.out" | tail -2

log "dashboard build"
cd "$REPO_ROOT/apps/wathefni-dashboard"
npx tsc --noEmit 2>&1 | tee "$LOCAL_EVID/tests/tsc.out"
npm run build 2>&1 | tee "$LOCAL_EVID/tests/dashboard-build.out" | tail -25
# Bundle must call canonical create endpoint, not plural /actions
API_CHUNK=$(ls dist/assets/api-*.js | head -1)
POST_CHUNK=$(ls dist/assets/PostHire-*.js | head -1)
{
  echo "api_chunk=$API_CHUNK"
  echo "post_chunk=$POST_CHUNK"
  if grep -qF '/dashboard/posthire/shifts' "$API_CHUNK" && grep -qF 'method:`POST`' "$API_CHUNK"; then echo FOUND canonical_shifts_create_post; else echo MISSING canonical_shifts_create_post; fi
  if grep -qF '/dashboard/posthire/actions' "$API_CHUNK" "$POST_CHUNK"; then echo BAD plural_actions_path; else echo CLEAN no_plural_actions; fi
  if grep -qF 'shifts-create-submit' "$POST_CHUNK"; then echo FOUND create_submit_testid; else echo MISSING create_submit_testid; fi
  shasum -a 256 "$API_CHUNK" "$POST_CHUNK"
} | tee "$LOCAL_EVID/tests/bundle-markers.txt"
if grep -qE 'BAD plural_actions_path|MISSING canonical_shifts_create_post|MISSING create_submit_testid' "$LOCAL_EVID/tests/bundle-markers.txt"; then
  echo BUNDLE_MARKER_FAILED
  exit 1
fi

log "copy sources"
cp -a "$ORCH_SRC"/{app.py,shifts_wave3_controlled.py,shifts_schedule_integrity_wave2.py,shifts_authority_wave1.py,smoke-test-shifts-wave3-ux.py} "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/shifts-wave3b-staging-create-path-browser.py" "$REPO_ROOT/ops/qualify-shifts-wave3b-staging-create-path.sh" "$LOCAL_EVID/sources/"
rsync -a --delete "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$LOCAL_EVID/sources/dashboard-dist/"

log "push staging"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'/{tests,screenshots,sources}"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py shifts_wave3_controlled.py shifts_schedule_integrity_wave2.py shifts_authority_wave1.py \
    smoke-test-shifts-wave3-ux.py "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$REPO_ROOT/ops/shifts-wave3b-staging-create-path-browser.py" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
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
mkdir -p "\$STAGING_ORCH/sources" "\$REMOTE_EVID/sources"
cp -a "\$REMOTE_STAGE"/ShiftsWorkspace.tsx "\$REMOTE_STAGE"/shiftsUx.ts "\$STAGING_ORCH/sources/" "\$REMOTE_EVID/sources/"
cp -a "\$REMOTE_STAGE"/*.py "\$REMOTE_EVID/sources/"
export SHIFTS_WAVE3_DASH_SRC="\$STAGING_ORCH/sources"

if [[ -d "\$STAGING_DASH" ]]; then cp -a "\$STAGING_DASH" "\$STAGING_DASH.bak-w3b-\$STAMP" || true; fi
rsync -a --delete "\$REMOTE_STAGE/dashboard-dist/" "\$STAGING_DASH/"

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
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_KEY_MARKERS=SHW3B,SHW3B-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_PHONE_PREFIXES=965531
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965530,965531
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965530,965531
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break; sleep 1; done

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
export WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
export WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python

"\$PYBIN" -u smoke-test-shifts-wave3-ux.py 2>&1 | tee "\$REMOTE_EVID/tests/wave3-ux-smoke.out"
if grep -E '[1-9][0-9]* failed' "\$REMOTE_EVID/tests/wave3-ux-smoke.out"; then echo UX_FAILED; exit 1; fi

export SHW3B_UI_SHOTS="\$REMOTE_EVID/screenshots"
export STAGING_ORCH="\$STAGING_ORCH"
"\$PYBIN" -u "\$REMOTE_STAGE/shifts-wave3b-staging-create-path-browser.py" 2>&1 | tee "\$REMOTE_EVID/tests/create-path-browser.out"
if grep -E '[1-9][0-9]* failed' "\$REMOTE_EVID/tests/create-path-browser.out"; then
  echo CREATE_PATH_FAILED
  exit 1
fi
echo STAGING_SHIFTS_W3B_CREATE_PATH_OK
REMOTE

"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/tests" "$LOCAL_EVID/remote/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/screenshots" "$LOCAL_EVID/" 2>/dev/null || true

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 3B — staging create-path closure

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/shifts-wave3b-staging-create-$STAMP/\`

## Gate
Mandatory before production synthetic Wave 3B deploy.

## Fixes
- Canonical \`POST /dashboard/posthire/shifts\` create endpoint
- Workspace composer uses \`createShift\` (not plural \`/dashboard/posthire/actions\`)
- Browser UI proves same-day, split, overnight via composer
- UI ↔ API ↔ DB reconcile + residual zero (SHW3B staging markers)

## Verdict
See \`tests/create-path-browser.out\` / \`remote/tests/\`.
Production deploy must not proceed unless create-path is **GO**.
EOF

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
if grep -q 'STAGING_SHIFTS_W3B_CREATE_PATH_OK' "$LOCAL_EVID/tests/qualify-staging.out"; then
  echo "STAGING_CREATE_PATH_GO"
else
  echo "STAGING_CREATE_PATH_NO_GO"
  exit 1
fi
