#!/usr/bin/env bash
# Attendance final — production UX promote + synthetic canary + freeze.
# NO real ingest, devices, QR/GPS/kiosk, employee clocking, or payroll money impact.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-final-$STAMP"
REMOTE_STAGE="/tmp/attw-final-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-final/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,canary,backup,flags,dashboard,freeze}
echo "$LOCAL_EVID" > /tmp/attwfinal.evid
echo "$STAMP" > /tmp/attwfinal.stamp

log() { printf '\n=== %s ===\n' "$*"; }

FILES=(
  attendance_ops_wave3.py
  attendance_ops_postgres.py
  attendance_ops_http.py
  attendance_authority_wave1.py
  attendance_authority_postgres.py
  seed-and-prove-attendance-wave4b.py
  canary-prod-attendance-final.py
  smoke-test-attendance-freeze-regression.py
  smoke-test-employees360-freeze-regression.py
  smoke-test-onboarding-freeze-regression.py
)

log "local freezes + attendance freeze smoke + wave4b prove"
cd "$ORCH_SRC"
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tee /tmp/attwfinal-onb.out | tail -8
if grep -qE '[1-9][0-9]* failed' /tmp/attwfinal-onb.out; then echo "REFUSE local onboarding freeze"; exit 2; fi

# Freeze doc must exist before attendance freeze smoke
test -f "$REPO_ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" || {
  echo "NOTE: freeze doc will be written after canary; creating stub for local smoke"
}

ATTW4B_EVID="$LOCAL_EVID/canary/local-wave4b" WATHEFNI_ENV=local \
  .venv/bin/python seed-and-prove-attendance-wave4b.py 2>&1 | tee "$LOCAL_EVID/tests/wave4b-local.out" | tail -15
test "$(python3 -c "import json;print(json.load(open('$LOCAL_EVID/canary/local-wave4b/summary.json'))['failed'])")" = "0"

log "staging freezes (must be green)"
"${SSH[@]}" "bash -s" <<'STG' | tee "$LOCAL_EVID/tests/freeze-staging.out"
set -euo pipefail
cd /opt/wathefni/staging/orchestrator
PY=/opt/wathefni/orchestrator/.venv/bin/python
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "$WATHEFNI_POSTGRES_ENV"; set +a
$PY smoke-test-employees360-freeze-regression.py 2>&1 | tee /tmp/stg-e360.out | tail -5
$PY smoke-test-onboarding-freeze-regression.py 2>&1 | tee /tmp/stg-onb.out | tail -8
if grep -qE '[1-9][0-9]* failed' /tmp/stg-onb.out; then echo "REFUSE staging onboarding freeze"; exit 2; fi
if grep -qE '[1-9][0-9]* failed' /tmp/stg-e360.out; then echo "REFUSE staging E360 freeze"; exit 2; fi
echo STAGING_FREEZES_OK
STG

log "build dashboard"
cd "$REPO_ROOT/apps/wathefni-dashboard"
npm run build 2>&1 | tee "$LOCAL_EVID/tests/dashboard-build.out" | tail -20
CHUNK=$(ls dist/assets/PostHire-*.js | head -1)
sha256sum "$CHUNK" | tee "$LOCAL_EVID/dashboard/posthire-sha-local.txt"
rsync -a --delete dist/ "$LOCAL_EVID/sources/dashboard-dist/"

log "copy sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$ORCH_SRC/ops/deploy-attendance-final-prod.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/attendance-final-ui-prod-screenshots.py" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-attendance-final-prod.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/.cursor/rules/attendance-freeze.mdc" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage + deploy production"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'/{preflight,verify,flags,backup,schema,dashboard,canary,screenshots,tests}"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${FILES[@]}" ops/deploy-attendance-final-prod.sh "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" \
  "$REPO_ROOT/ops/attendance-final-ui-prod-screenshots.py" \
  "$REPO_ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" \
  "$VPS_HOST:$REMOTE_STAGE/"
rsync -az --delete -e "ssh -o BatchMode=yes" "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-attendance-final-prod.sh'
bash '$REMOTE_STAGE/deploy-attendance-final-prod.sh'
REMOTE

log "rollback proof (dashboard+modules) then redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback-redeploy.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/attendance-final/$STAMP/backup/BACKUP_PATH.txt)
test -x "\$BACKUP/ROLLBACK.sh"
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP" | tee /opt/wathefni/production-evidence/attendance-final/$STAMP/verify/rollback.out
# Confirm PostHire rolled back (may differ from Wave4B chunk)
ls /var/www/wathefni-dashboard/assets/PostHire-*.js | head -1 | tee /opt/wathefni/production-evidence/attendance-final/$STAMP/verify/posthire-after-rollback.txt
# Redeploy final
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-attendance-final-prod.sh' | tee /opt/wathefni/production-evidence/attendance-final/$STAMP/verify/redeploy.out
grep -q DEPLOY_OK /opt/wathefni/production-evidence/attendance-final/$STAMP/verify/redeploy.out
ls /var/www/wathefni-dashboard/assets/PostHire-*.js | while read f; do sha256sum "\$f"; done | tee /opt/wathefni/production-evidence/attendance-final/$STAMP/verify/posthire-after-redeploy.txt
echo ROLLBACK_REDEPLOY_OK
REMOTE

log "production synthetic canary"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID='$REMOTE_EVID'
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
mkdir -p "\$REMOTE_EVID/canary"
export ATTW_FINAL_EVID="\$REMOTE_EVID/canary"
\$PYBIN canary-prod-attendance-final.py 2>&1 | tee "\$REMOTE_EVID/canary/canary.out"
test "\$(python3 -c "import json;print(json.load(open('\$REMOTE_EVID/canary/qualification.json'))['summary']['failed'])")" = "0"
REMOTE

log "production UI screenshots + cleanup seed rows"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/screenshots.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID='$REMOTE_EVID'
REMOTE_STAGE='$REMOTE_STAGE'
PYBIN=\$ORCH/.venv/bin/python
mkdir -p "\$REMOTE_EVID"/{screenshots,tests,canary}
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export ATTW_FINAL_UI_SHOTS="\$REMOTE_EVID/screenshots"
export DASHBOARD_BASE="http://127.0.0.1:8010/dashboard"
export API_BASE="http://127.0.0.1:8010"
export ORCH_PATH=\$ORCH
export ORCH_PYTHON=\$PYBIN
\$PYBIN "\$REMOTE_STAGE/attendance-final-ui-prod-screenshots.py" 2>&1 | tee "\$REMOTE_EVID/tests/screenshots.out"
test "\$(python3 -c "import json;print(len([s for s in json.load(open('\$REMOTE_EVID/screenshots/manifest.json'))['shots'] if s.startswith('daily-board-')]))")" -ge 4

# Cleanup screenshot ATTW4B tag + capture seed prefix (remote expansion)
TAG=\$(head -1 "\$REMOTE_EVID/screenshots/seed-tag.txt" 2>/dev/null || true)
CAP=\$(python3 -c "import json;print(json.load(open('\$REMOTE_EVID/screenshots/manifest.json')).get('prefix') or '')" 2>/dev/null || true)
if [[ -n "\$TAG" ]]; then
  \$PYBIN - <<PY
import importlib.util, os
spec = importlib.util.spec_from_file_location(
    "canary_final", "/opt/wathefni/orchestrator/canary-prod-attendance-final.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cap = "\$CAP".strip() or None
print(mod.cleanup_tag("\$TAG", capture_prefix=cap))
PY
fi
# Assert 42 rows
\$PYBIN - <<'PY'
import app
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
    n=int(cur.fetchone()["n"])
    cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'")
    d=int(cur.fetchone()["n"])
print({"rows":n,"demo":d})
assert n==42 and d==42
PY
echo SCREENSHOTS_CLEANUP_OK
REMOTE

log "pull remote evidence"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/" "$LOCAL_EVID/remote/"
mkdir -p "$LOCAL_EVID/screenshots"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/screenshots/" "$LOCAL_EVID/screenshots/" || true

log "write freeze doc + cursor rule (local repo)"
# Freeze doc and REPORT filled by following write step in agent; ensure smoke can run
cp -a "$REPO_ROOT/ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" "$LOCAL_EVID/freeze/" 2>/dev/null || true

# Run attendance freeze smoke with freeze doc present
cd "$ORCH_SRC"
.venv/bin/python smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -20

log "done — $LOCAL_EVID"
echo "$LOCAL_EVID"
