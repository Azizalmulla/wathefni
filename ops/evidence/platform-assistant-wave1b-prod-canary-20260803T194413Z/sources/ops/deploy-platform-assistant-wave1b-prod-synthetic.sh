#!/usr/bin/env bash
# Platform Assistant Wave 1-B — production WATHEFNI synthetic Spine Contract deploy.
# HR dashboard-only. Mutations off. No WhatsApp widening / CK / money / ingest / Wave 2.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-platform-assistant-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/platform-assistant-wave1b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/platform-assistant-w1b-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-platform-assistant-wave1b-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} \
  "$BACKUP"/{modules,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/action_registry.py" "$ORCH/tool_call_orchestrator.py" 2>/dev/null || true
  ls -la "$ORCH/platform_assistant_spine_wave1.py" 2>&1 || echo "platform_assistant_spine_wave1.py absent"
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

log "backing up modules + dropins"
mkdir -p "$BACKUP/modules"
for f in app.py action_registry.py assistant_capability_catalog.py tool_call_orchestrator.py \
         platform_assistant_spine_wave1.py setup_console_wave_a_launch_readiness.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-platform-assistant-wave1b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  if [[ ! -f "$BACKUP_DIR/modules/platform_assistant_spine_wave1.py" ]]; then
    rm -f "$ORCH/platform_assistant_spine_wave1.py"
  fi
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
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
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying platform assistant wave1 modules"
for f in app.py action_registry.py assistant_capability_catalog.py tool_call_orchestrator.py \
         platform_assistant_spine_wave1.py setup_console_wave_a_launch_readiness.py \
         canary-prod-platform-assistant-wave1b.py \
         smoke-test-platform-assistant-wave1.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops"
[[ -f "$STAGE/migrate-platform-assistant-wave1-prod.sh" ]] && cp -a "$STAGE/migrate-platform-assistant-wave1-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/deploy-platform-assistant-wave1b-prod-synthetic.sh" ]] && cp -a "$STAGE/deploy-platform-assistant-wave1b-prod-synthetic.sh" "$ORCH/ops/"

log "writing Wave 1-B production drop-in (mutations off; ingest off; WATHEFNI only)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE1=1
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_ASSISTANT_KILL=0
Environment=WATHEFNI_ASSISTANT_MUTATIONS=0
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
EOF

log "migrate ACK"
chmod +x "$ORCH/ops/migrate-platform-assistant-wave1-prod.sh"
PID_PRE=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID_PRE"/environ
export WATHEFNI_ENV=production
export WATHEFNI_PLATFORM_ASSISTANT_WAVE1=1
export WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES=WATHEFNI
export WATHEFNI_ASSISTANT_MUTATIONS=0
export WATHEFNI_ASSISTANT_KILL=0
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
ACK_PRODUCTION_PLATFORM_ASSISTANT_W1B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-platform-assistant-wave1-prod.sh" \
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
  sha256sum "$ORCH/app.py" "$ORCH/action_registry.py" "$ORCH/tool_call_orchestrator.py" "$ORCH/platform_assistant_spine_wave1.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'PLATFORM_ASSISTANT|ASSISTANT_KILL|ASSISTANT_MUTATIONS|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/platform-assistant-wave1b-flags.txt"
import os
import platform_assistant_spine_wave1 as w
print("WAVE1", os.environ.get("WATHEFNI_PLATFORM_ASSISTANT_WAVE1"))
print("COMPANIES", os.environ.get("WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES"))
print("KILL", os.environ.get("WATHEFNI_ASSISTANT_KILL"))
print("MUTATIONS", os.environ.get("WATHEFNI_ASSISTANT_MUTATIONS"))
print("CAPTURE_INGEST", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"))
print("enabled", w.platform_assistant_wave1_enabled())
print("company", w.wave1_enabled_for_company("WATHEFNI"))
print("company_external", w.wave1_enabled_for_company("EXTERNALCO"))
print("mutations_allowed", w.assistant_mutations_allowed())
print("kill_engaged", w.assistant_kill_engaged())
h = w.honesty_payload()
print("honesty", {k: h[k] for k in (
    "wathefni_only","hr_dashboard_only","mutates_records","payroll_money",
    "attendance_ingest","whatsapp_widening","default_posthire_entry",
)})
assert w.platform_assistant_wave1_enabled()
assert w.wave1_enabled_for_company("WATHEFNI")
assert not w.wave1_enabled_for_company("EXTERNALCO")
assert w.assistant_mutations_allowed() is False
assert w.assistant_kill_engaged() is False
assert h["payroll_money"] is False
assert h["attendance_ingest"] is False
print("PAW1B_MARKER=PAW1B")
print("flags_ok_wave1b=true")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
