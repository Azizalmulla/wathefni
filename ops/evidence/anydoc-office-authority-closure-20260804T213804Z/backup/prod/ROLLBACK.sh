#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
for f in anydoc_office_authority.py anydoc_office_shadow.py app.py requirements.txt; do
  [[ -f "$BACKUP_DIR/modules/$f" ]] && cp -a "$BACKUP_DIR/modules/$f" "$PROD/$f" || true
done
[[ ! -f "$BACKUP_DIR/modules/anydoc_office_authority.py" ]] && rm -f "$PROD/anydoc_office_authority.py" || true
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zzz-anydoc-office-authority.conf
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/anydoc-office-authority.conf
# Restore prior shadow observation drop-in if backed up
if [[ -f "$BACKUP_DIR/systemd/wathefni-orchestrator.service.d/anydoc-office-shadow.conf" ]]; then
  cp -a "$BACKUP_DIR/systemd/wathefni-orchestrator.service.d/anydoc-office-shadow.conf"     /etc/systemd/system/wathefni-orchestrator.service.d/anydoc-office-shadow.conf
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
echo ROLLBACK_ANYDOC_OFFICE_AUTHORITY_OK
