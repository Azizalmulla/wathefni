#!/usr/bin/env bash
# Action Inbox Wave 1-B — production WATHEFNI synthetic Unified Action Inbox deploy.
# Deploys Wave 1 action-inbox code + dashboard dist.
# Enforces SYNTHETIC_ONLY. Read-only composition only.
# No AI / Compliance Wave 2 / Analytics Wave 2 / Payroll money / Attendance ingest / Shifts manager expand.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-action-inbox-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/action-inbox-wave1b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/action-inbox-w1b-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-action-inbox-wave1b-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} \
  "$BACKUP"/{modules,dashboard-dist,dashboard-dist-legacy,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" 2>/dev/null || true
  ls -la "$ORCH/action_inbox_wave1.py" 2>&1 || echo "action_inbox_wave1.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ACTION_INBOX_WAVE1|COMPLIANCE_WAVE1|ANALYTICS_WAVE1|CAPTURE_INGEST|DASHBOARD_DIST' | sort || true
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

log "backing up modules + dropins + dashboard"
mkdir -p "$BACKUP/modules"
for f in app.py action_inbox_wave1.py analytics_attention_wave1.py compliance_findings_wave1.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
if [[ -d "$DASH_DIST" ]]; then
  rsync -a "$DASH_DIST/" "$BACKUP/dashboard-dist/" || true
fi
if [[ -d "$DASH_DIST_LEGACY" ]]; then
  rsync -a "$DASH_DIST_LEGACY/" "$BACKUP/dashboard-dist-legacy/" || true
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-action-inbox-wave1b-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  if [[ ! -f "$BACKUP_DIR/modules/action_inbox_wave1.py" ]]; then
    rm -f "$ORCH/action_inbox_wave1.py"
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
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
# Note: durable wave ACK rows are intentionally retained (audit). Canary-tagged rows are cleaned by canary.
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying action-inbox wave1 modules"
for f in app.py action_inbox_wave1.py analytics_attention_wave1.py compliance_findings_wave1.py \
         canary-prod-action-inbox-wave1b.py \
         smoke-test-action-inbox-wave1.py \
         smoke-test-action-inbox-freeze-regression.py \
         smoke-test-analytics-freeze-regression.py \
         smoke-test-compliance-freeze-regression.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py \
         canary-prod-analytics-attention-wave1b.py \
         canary-prod-compliance-findings-wave1b.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops"
[[ -f "$STAGE/migrate-action-inbox-wave1-prod.sh" ]] && cp -a "$STAGE/migrate-action-inbox-wave1-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/deploy-action-inbox-wave1b-prod-synthetic.sh" ]] && cp -a "$STAGE/deploy-action-inbox-wave1b-prod-synthetic.sh" "$ORCH/ops/"

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist"
  mkdir -p "$DASH_DIST" "$DASH_DIST_LEGACY"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST_LEGACY/"
fi
mkdir -p /opt/wathefni/apps/wathefni-dashboard/src/posthire
for f in PostHire.tsx actionInboxWave1.test.ts; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" /opt/wathefni/apps/wathefni-dashboard/src/posthire/ || true
done
[[ -f "$STAGE/App.tsx" ]] && mkdir -p /opt/wathefni/apps/wathefni-dashboard/src && cp -a "$STAGE/App.tsx" /opt/wathefni/apps/wathefni-dashboard/src/ || true
[[ -f "$STAGE/types.ts" ]] && cp -a "$STAGE/types.ts" /opt/wathefni/apps/wathefni-dashboard/src/ || true
for f in api.ts moduleWorkspace.ts workspaceCapability.ts; do
  [[ -f "$STAGE/$f" ]] && mkdir -p /opt/wathefni/apps/wathefni-dashboard/src/lib && cp -a "$STAGE/$f" /opt/wathefni/apps/wathefni-dashboard/src/lib/ || true
done

log "writing synthetic-only drop-in"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_ACTION_INBOX_WAVE1=1
Environment=WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY=1
Environment=WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_KEY_MARKERS=AIW1,AIW1-SYNTH|
Environment=WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_PHONE_PREFIXES=965542
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
EOF

log "migrate ACK schema"
chmod +x "$ORCH/ops/migrate-action-inbox-wave1-prod.sh"
ACK_PRODUCTION_ACTION_INBOX_W1B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-action-inbox-wave1-prod.sh" \
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
  sha256sum "$ORCH/app.py" "$ORCH/action_inbox_wave1.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ACTION_INBOX_WAVE1|CAPTURE_INGEST|DASHBOARD_DIST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/action-inbox-wave1-flags.txt"
import os, action_inbox_wave1 as w, analytics_attention_wave1 as a, compliance_findings_wave1 as c
print("ACTION_INBOX_WAVE1", os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1"))
print("SYNTHETIC_ONLY", w.action_inbox_wave1_synthetic_only())
print("enabled", w.action_inbox_wave1_enabled())
print("company", w.action_inbox_wave1_enabled_for_company("WATHEFNI"))
print("markers", w.synthetic_key_markers())
print("prefixes", w.synthetic_phone_prefixes())
h = w.honesty_payload()
print("honesty", {k: h[k] for k in (
    "read_only","mutates_records","ai","hiring_reports_separate",
    "alerts_delivery_owns_notifications","compliance_wave2","analytics_wave2",
    "payroll_money","attendance_ingest","shifts_manager_expansion","synthetic_only"
)})
assert w.action_inbox_wave1_enabled()
assert w.action_inbox_wave1_synthetic_only()
assert w.action_inbox_wave1_enabled_for_company("WATHEFNI")
assert h["mutates_records"] is False
assert h["ai"] is False
assert h["compliance_wave2"] is False
assert h["analytics_wave2"] is False
assert a.honesty_payload()["compliance_metrics"] is False
assert c.honesty_payload()["legal_compliance_claims"] is False
print("flags_ok_synthetic=true")
PY

DIST=/opt/wathefni/dashboard-dist
{
  grep -Rql 'Action Inbox\|صندوق الإجراءات' "$DIST" && echo UI_INBOX_COPY_OK || echo UI_INBOX_COPY_MISSING
  grep -Rql 'System of action\|نظام التنفيذ' "$DIST" && echo UI_SOA_COPY_OK || echo UI_SOA_COPY_SOFT
  grep -Rql 'Hiring Reports stay separate\|تقارير التوظيف منفصلة' "$DIST" && echo UI_HONESTY_COPY_OK || echo UI_HONESTY_COPY_SOFT
  grep -Rql 'sm:flex-row\|sm:grid-cols' "$DIST" && echo UI_RESPONSIVE_OK || echo UI_RESPONSIVE_SOFT
} | tee "$REMOTE_EVID/ui/dist-checks.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
