#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN_W3=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave3-ops-synthetic.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" || true
fi
rm -f "$DROPIN_W3"
# Keep ops tables (empty synthetic leftover ok); do not drop schema on rollback by default
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
