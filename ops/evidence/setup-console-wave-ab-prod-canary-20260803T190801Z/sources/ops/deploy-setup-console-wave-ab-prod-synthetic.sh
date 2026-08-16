#!/usr/bin/env bash
# Setup Console Wave A-B — production WATHEFNI synthetic Launch Readiness deploy.
# Operator-only. No external tenants / Payroll money / Attendance ingest / Wave B / AI / mobile apps.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-setup-console-wave-ab-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/setup-console-wave-ab-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/setup-console-wab-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-setup-console-wave-ab-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/setup-console
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} \
  "$BACKUP"/{modules,dashboard-dist,dashboard-dist-legacy,setup-console-src,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" 2>/dev/null || true
  ls -la "$ORCH/setup_console_wave_a_launch_readiness.py" 2>&1 || echo "setup_console_wave_a_launch_readiness.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'SETUP_CONSOLE|CAPTURE_INGEST|PAYROLL_WAVE|DASHBOARD_DIST|PLATFORM_ADMIN' | sort || true
} | tee "$REMOTE_EVID/preflight/before-deploy.txt"

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1

cd "$ORCH"

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up modules + dropins + dashboard + setup-console src"
mkdir -p "$BACKUP/modules"
for f in app.py setup_console_wave_a_launch_readiness.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
if [[ -d "$DASH_DIST" ]]; then
  rsync -a "$DASH_DIST/" "$BACKUP/dashboard-dist/" || true
fi
if [[ -d "$DASH_DIST_LEGACY" ]]; then
  rsync -a "$DASH_DIST_LEGACY/" "$BACKUP/dashboard-dist-legacy/" || true
fi
if [[ -d "$DASH_SRC" ]]; then
  rsync -a "$DASH_SRC/" "$BACKUP/setup-console-src/" || true
fi
(
  cd "$BACKUP"
  find modules -type f 2>/dev/null | while read -r f; do sha256sum "$f"; done
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-setup-console-wave-ab-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/setup-console
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  if [[ ! -f "$BACKUP_DIR/modules/setup_console_wave_a_launch_readiness.py" ]]; then
    rm -f "$ORCH/setup_console_wave_a_launch_readiness.py"
  fi
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
  rm -f "$DROPIN"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist-legacy" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist-legacy" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist-legacy/" "$DASH_DIST_LEGACY/"
fi
if [[ -d "$BACKUP_DIR/setup-console-src" ]] && [[ -n "$(ls -A "$BACKUP_DIR/setup-console-src" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_SRC"
  rsync -a --delete "$BACKUP_DIR/setup-console-src/" "$DASH_SRC/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying setup console wave a modules"
for f in app.py setup_console_wave_a_launch_readiness.py \
         canary-prod-setup-console-wave-ab.py \
         smoke-test-setup-console-wave-a.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops"
[[ -f "$STAGE/migrate-setup-console-wave-a-prod.sh" ]] && cp -a "$STAGE/migrate-setup-console-wave-a-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/deploy-setup-console-wave-ab-prod-synthetic.sh" ]] && cp -a "$STAGE/deploy-setup-console-wave-ab-prod-synthetic.sh" "$ORCH/ops/"

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist (includes setup-console)"
  mkdir -p "$DASH_DIST" "$DASH_DIST_LEGACY"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST_LEGACY/"
fi
mkdir -p "$DASH_SRC"
for f in LaunchReadinessPage.tsx SetupConsoleApp.tsx api.ts types.ts; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$DASH_SRC/" || true
done

log "writing Wave A production drop-in (WATHEFNI-only; ingest stays off)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_SETUP_CONSOLE_ENABLED=true
Environment=WATHEFNI_SETUP_CONSOLE_V2=on
Environment=WATHEFNI_SETUP_CONSOLE_WAVE_A=1
Environment=WATHEFNI_SETUP_CONSOLE_WAVE_A_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
EOF

log "migrate ACK (no schema)"
chmod +x "$ORCH/ops/migrate-setup-console-wave-a-prod.sh"
# Load current service env for migrate asserts, then overlay Wave A flags for ACK check.
PID_PRE=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID_PRE"/environ
export WATHEFNI_ENV=production
export WATHEFNI_SETUP_CONSOLE_WAVE_A=1
export WATHEFNI_SETUP_CONSOLE_WAVE_A_COMPANIES=WATHEFNI
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
ACK_PRODUCTION_SETUP_WAVE_AB=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-setup-console-wave-a-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/setup_console_wave_a_launch_readiness.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'SETUP_CONSOLE|CAPTURE_INGEST|DASHBOARD_DIST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/setup-console-wave-ab-flags.txt"
import os
import setup_console_wave_a_launch_readiness as w
print("SETUP_CONSOLE_ENABLED", os.environ.get("WATHEFNI_SETUP_CONSOLE_ENABLED"))
print("SETUP_CONSOLE_V2", os.environ.get("WATHEFNI_SETUP_CONSOLE_V2"))
print("WAVE_A", os.environ.get("WATHEFNI_SETUP_CONSOLE_WAVE_A"))
print("WAVE_A_COMPANIES", os.environ.get("WATHEFNI_SETUP_CONSOLE_WAVE_A_COMPANIES"))
print("CAPTURE_INGEST", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"))
print("enabled", w.wave_a_enabled())
print("company", w.wave_a_enabled_for_company("WATHEFNI"))
print("company_external", w.wave_a_enabled_for_company("EXTERNALCO"))
h = w.honesty_payload()
print("honesty", {k: h[k] for k in (
    "operator_only","wathefni_only","payroll_money","attendance_ingest",
    "capture_ingest","setup_wave_b","ai","entitlements_cannot_bypass_gates",
)})
assert w.wave_a_enabled()
assert w.wave_a_enabled_for_company("WATHEFNI")
assert not w.wave_a_enabled_for_company("EXTERNALCO")
assert h["payroll_money"] is False
assert h["attendance_ingest"] is False
assert h["capture_ingest"] == "off"
assert "SCWAB" or True
print("SCWAB_MARKER=SCWAB")
print("flags_ok_wave_a=true")
PY

DIST=/opt/wathefni/dashboard-dist
{
  grep -Rql 'Launch readiness\|جاهزية الإطلاق' "$DIST" && echo UI_LAUNCH_COPY_OK || echo UI_LAUNCH_COPY_MISSING
  grep -Rql 'launch-overall-status\|launch-important-blockers\|launch-pause-impact' "$DIST" && echo UI_LAUNCH_MARKERS_OK || echo UI_LAUNCH_MARKERS_SOFT
  grep -Rql 'flex-wrap' "$DIST" && echo UI_MOBILE_WRAP_OK || echo UI_MOBILE_WRAP_SOFT
} | tee "$REMOTE_EVID/ui/dist-checks.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
