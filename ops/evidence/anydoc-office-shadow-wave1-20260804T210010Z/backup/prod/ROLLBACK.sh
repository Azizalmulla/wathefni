#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
for f in anydoc_office_shadow.py app.py requirements.txt; do
  [[ -f "$BACKUP_DIR/modules/$f" ]] && cp -a "$BACKUP_DIR/modules/$f" "$PROD/$f" || true
done
# If module did not exist pre-wave, remove it
if [[ ! -f "$BACKUP_DIR/modules/anydoc_office_shadow.py" ]]; then
  rm -f "$PROD/anydoc_office_shadow.py"
fi
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/anydoc-office-shadow.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
echo ROLLBACK_ANYDOC_OFFICE_SHADOW_OK
