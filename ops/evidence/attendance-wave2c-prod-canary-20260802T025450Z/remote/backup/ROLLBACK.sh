#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/attendance_authority_wave1.py" "$ORCH/attendance_authority_wave1.py"
cp -a "$BACKUP_DIR/attendance_authority_postgres.py" "$ORCH/attendance_authority_postgres.py" 2>/dev/null || true
cp -a "$BACKUP_DIR/attendance_authority_hooks.py" "$ORCH/attendance_authority_hooks.py" 2>/dev/null || true
rm -f "$ORCH"/attendance_capture_*.py "$ORCH"/canary-prod-attendance-wave2c.py "$ORCH"/attendance_capture_lab_biotime.py
rm -f "$DROPIN"
# restore prior dropins directory snapshot if present
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
  # restore 1C dropin from backup snapshot if it existed
  if [[ -f "$BACKUP_DIR/systemd-dropins/zz-attendance-wave1c-synthetic-canary.conf" ]]; then
    cp -a "$BACKUP_DIR/systemd-dropins/zz-attendance-wave1c-synthetic-canary.conf" /etc/systemd/system/wathefni-orchestrator.service.d/
  fi
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
