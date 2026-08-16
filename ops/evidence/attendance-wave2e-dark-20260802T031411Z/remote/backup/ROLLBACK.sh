#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2e-capture-ops-dark.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
# restore prior capture modules snapshot
rm -f "$ORCH"/attendance_capture_ops.py "$ORCH"/attendance_capture_ops_http.py \
  "$ORCH"/attendance_capture_secrets.py "$ORCH"/attendance_capture_registry.py \
  "$ORCH"/attendance_capture_remediation.py "$ORCH"/attendance_capture_health.py \
  "$ORCH"/attendance_capture_compat.py
if [[ -d "$BACKUP_DIR/capture_modules" ]]; then
  cp -a "$BACKUP_DIR/capture_modules"/. "$ORCH/" || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
