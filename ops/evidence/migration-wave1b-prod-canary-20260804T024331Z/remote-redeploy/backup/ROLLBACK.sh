#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzz-migration-wave1b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  # Restore prior modules if present; otherwise remove Wave 1-B-only files when absent from backup.
  for f in app.py migration_wave1_cv_foundation.py smoke-test-migration-wave1.py canary-prod-migration-wave1b.py; do
    if [[ -f "$BACKUP_DIR/modules/$f" ]]; then
      cp -a "$BACKUP_DIR/modules/$f" "$ORCH/$f"
    else
      rm -f "$ORCH/$f"
    fi
  done
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
