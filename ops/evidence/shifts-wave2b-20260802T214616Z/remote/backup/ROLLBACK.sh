#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-integrity-wave2b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ -f "$BACKUP_DIR/modules/shifts_authority_wave1.py" ]]; then
  cp -a "$BACKUP_DIR/modules/shifts_authority_wave1.py" "$ORCH/"
fi
if [[ -f "$BACKUP_DIR/modules/shifts_schedule_integrity_wave2.py" ]]; then
  cp -a "$BACKUP_DIR/modules/shifts_schedule_integrity_wave2.py" "$ORCH/"
else
  rm -f "$ORCH/shifts_schedule_integrity_wave2.py"
fi
rm -f "$DROPIN"
# Restore other drop-ins from backup if present
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  mkdir -p /etc/systemd/system/wathefni-orchestrator.service.d
  # Do not wipe Wave 1B drop-in if it existed in backup
  cp -a "$BACKUP_DIR/systemd-dropins/." /etc/systemd/system/wathefni-orchestrator.service.d/ || true
  rm -f "$DROPIN"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rm -rf "$DASH_DIST"
  mkdir -p "$DASH_DIST"
  cp -a "$BACKUP_DIR/dashboard-dist/." "$DASH_DIST/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
