#!/usr/bin/env bash
# Action Inbox — controlled real-HR canary deploy (WATHEFNI / Aziz / Talal).
# Populates Phase 0 allowlists ONLY with approved Aziz viewer + Talal subject.
# Keeps EXCLUDE_PAYROLL=1. Read-only. No AI / Wave 2 / money / ingest / shifts expand.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-action-inbox-real-hr-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/action-inbox-real-hr-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/action-inbox-rhc-prod-stage}"
# Sorts after phase0b safety drop-in so populated allowlists win.
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-action-inbox-real-hr-canary.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
PYBIN="$ORCH/.venv/bin/python"

VIEWER_ALLOW=96599338566
SUBJECT_ALLOW=WATHEFNI-96550252254

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} \
  "$BACKUP"/{modules,dashboard-dist,dashboard-dist-legacy,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/action_inbox_wave1.py" 2>/dev/null || true
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ACTION_INBOX|CAPTURE_INGEST|DASHBOARD_DIST' | sort || true
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-action-inbox-real-hr-canary.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
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
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying canary modules (if staged)"
for f in app.py action_inbox_wave1.py analytics_attention_wave1.py compliance_findings_wave1.py \
         canary-prod-action-inbox-real-hr.py \
         canary-prod-action-inbox-phase0b.py \
         canary-prod-action-inbox-wave1b.py \
         smoke-test-action-inbox-wave1.py \
         smoke-test-action-inbox-freeze-regression.py \
         smoke-test-analytics-freeze-regression.py \
         smoke-test-compliance-freeze-regression.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops"
[[ -f "$STAGE/deploy-action-inbox-real-hr-canary.sh" ]] && cp -a "$STAGE/deploy-action-inbox-real-hr-canary.sh" "$ORCH/ops/"

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist"
  mkdir -p "$DASH_DIST" "$DASH_DIST_LEGACY"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST_LEGACY/"
fi

log "writing real-HR canary drop-in (Aziz viewer + Talal subject ONLY)"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_ACTION_INBOX_WAVE1=1
Environment=WATHEFNI_ACTION_INBOX_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_ACTION_INBOX_WAVE1_SYNTHETIC_ONLY=1
Environment=WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL=1
Environment=WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=${VIEWER_ALLOW}
Environment=WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=${SUBJECT_ALLOW}
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
EOF

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
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ACTION_INBOX|CAPTURE_INGEST|DASHBOARD_DIST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<PY | tee "$REMOTE_EVID/flags/real-hr-flags.txt"
import os, action_inbox_wave1 as w
print("WAVE1", os.environ.get("WATHEFNI_ACTION_INBOX_WAVE1"))
print("VIEWER_RAW", repr(os.environ.get("WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST")))
print("SUBJECT_RAW", repr(os.environ.get("WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST")))
print("EXCLUDE_PAYROLL", w.exclude_payroll_stream())
print("viewer_allowlist", sorted(w.real_viewer_allowlist()))
print("subject_allowlist", sorted(w.real_subject_allowlist()))
print("real_canary_enabled", w.honesty_payload().get("real_canary_enabled"))
print("within_boundary", w.allowlists_within_approved_boundary())
assert w.action_inbox_wave1_enabled()
assert w.exclude_payroll_stream() is True
assert w.viewer_is_allowlisted(phone="96599338566")
assert not w.viewer_is_allowlisted(phone="66363363")
assert w.real_subject_allowlist() == {"WATHEFNI-96550252254"}
assert w.allowlists_within_approved_boundary() is True
assert w.honesty_payload().get("real_canary_enabled") is True
print("flags_ok_aziz_talal_canary=true")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID viewer=$VIEWER_ALLOW subject=$SUBJECT_ALLOW"
