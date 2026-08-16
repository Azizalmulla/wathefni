#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-platform-assistant-wave2b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  if [[ ! -f "$BACKUP_DIR/modules/platform_assistant_wave2_safe_ops_reads.py" ]]; then
    rm -f "$ORCH/platform_assistant_wave2_safe_ops_reads.py"
  fi
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  # Restore pre-wave2 drop-ins (Wave 1 retained; Wave 2 drop-in removed above).
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
