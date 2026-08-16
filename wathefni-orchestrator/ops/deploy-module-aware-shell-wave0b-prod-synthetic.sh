#!/usr/bin/env bash
# Module-Aware Shell Wave 0-B — production WATHEFNI synthetic Focused Workforce deploy.
# Dashboard + orchestrator shell honesty. Mutations off. Ingest off. No further waves.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
DASH=/var/www/wathefni-dashboard
BACKUP="/opt/wathefni/backups/production-pre-module-aware-shell-wave0b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/module-aware-shell-wave0b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/module-aware-shell-w0b-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-module-aware-shell-wave0b-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests} \
  "$BACKUP"/{modules,systemd-dropins,dashboard-dist} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/assistant_capability_catalog.py" "$ORCH/workspace_capability.py" 2>/dev/null || true
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'PLATFORM_ASSISTANT|ASSISTANT_KILL|ASSISTANT_MUTATIONS|CAPTURE_INGEST|DASHBOARD_DIST' | sort || true
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

log "backing up modules + dashboard + dropins"
mkdir -p "$BACKUP/modules" "$BACKUP/dashboard-dist"
for f in app.py assistant_capability_catalog.py workspace_capability.py \
         smoke-test-module-aware-shell-wave0.py test_workspace_composition_matrix.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
rsync -a "$DASH/" "$BACKUP/dashboard-dist/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
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
DASH=/var/www/wathefni-dashboard
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-module-aware-shell-wave0b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH/"
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
  rm -f "$DROPIN"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
systemctl reload caddy || true
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying shell wave0 modules + dashboard"
for f in app.py assistant_capability_catalog.py workspace_capability.py \
         smoke-test-module-aware-shell-wave0.py test_workspace_composition_matrix.py \
         canary-prod-module-aware-shell-wave0b.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py \
         smoke-test-platform-assistant-wave1.py \
         smoke-test-platform-assistant-wave2.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops"
[[ -f "$STAGE/migrate-module-aware-shell-wave0-prod.sh" ]] && cp -a "$STAGE/migrate-module-aware-shell-wave0-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/deploy-module-aware-shell-wave0b-prod-synthetic.sh" ]] && cp -a "$STAGE/deploy-module-aware-shell-wave0b-prod-synthetic.sh" "$ORCH/ops/"

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH/"
  echo "DASHBOARD_DIST_DEPLOYED" | tee "$REMOTE_EVID/verify/dashboard.txt"
else
  echo "REFUSE: missing dashboard-dist in stage" >&2
  exit 3
fi

log "writing Wave 0-B production drop-in (mutations off; ingest off)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_ASSISTANT_MUTATIONS=0
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_DASHBOARD_DIST=/var/www/wathefni-dashboard
Environment=WATHEFNI_MODULE_AWARE_SHELL_WAVE0=1
EOF

log "migrate ACK"
chmod +x "$ORCH/ops/migrate-module-aware-shell-wave0-prod.sh"
PID_PRE=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID_PRE"/environ
export WATHEFNI_ENV=production
export WATHEFNI_ASSISTANT_MUTATIONS=0
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
export WATHEFNI_MODULE_AWARE_SHELL_WAVE0=1
ACK_PRODUCTION_MODULE_AWARE_SHELL_W0B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-module-aware-shell-wave0-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator
systemctl reload caddy || true

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/assistant_capability_catalog.py" "$ORCH/workspace_capability.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'MODULE_AWARE_SHELL|ASSISTANT_MUTATIONS|CAPTURE_INGEST|DASHBOARD_DIST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/module-aware-shell-wave0b-flags.txt"
import os
import workspace_capability as wc
print("SHELL_WAVE0", os.environ.get("WATHEFNI_MODULE_AWARE_SHELL_WAVE0"))
print("MUTATIONS", os.environ.get("WATHEFNI_ASSISTANT_MUTATIONS"))
print("CAPTURE_INGEST", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"))
print("DASHBOARD_DIST", os.environ.get("WATHEFNI_DASHBOARD_DIST"))
assert os.environ.get("WATHEFNI_ASSISTANT_MUTATIONS", "0") in {"0", "false", "off", ""}
assert os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off").lower() in {"off", "0", "false", "no", ""}
assert wc.resolve_focused_posthire_landing(["payroll"], available_pages=["payroll", "employees"]) == "payroll"
print("MASW0B_MARKER=MASW0B")
print("flags_ok_shell_wave0b=true")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
