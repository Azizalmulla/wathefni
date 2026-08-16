#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave1c-synthetic-canary.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/attendance_import.py" "$ORCH/attendance_import.py" 2>/dev/null || true
rm -f "$ORCH/attendance_authority_wave1.py" "$ORCH/attendance_authority_postgres.py" "$ORCH/attendance_authority_hooks.py" "$ORCH/canary-prod-attendance-wave1c.py"
rm -f "$DROPIN"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
