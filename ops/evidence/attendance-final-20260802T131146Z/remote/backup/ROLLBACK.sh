#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
WWW=/var/www/wathefni-dashboard
DROPIN_FINAL=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-final-freeze.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ -d "$BACKUP_DIR/modules" ]]; then cp -a "$BACKUP_DIR/modules"/. "$ORCH/" || true; fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -d "$WWW" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$WWW/"
fi
rm -f "$DROPIN_FINAL"
# Restore prior dropins if snapshot present
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
