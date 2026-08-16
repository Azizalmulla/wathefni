#!/usr/bin/env bash
set -euo pipefail
BACKUP="/opt/wathefni/backups/production-pre-waveC-entitlement-20260801T042210Z"
cp -a "$BACKUP/restore-new/orchestrator/assistant_capability_catalog.py" /opt/wathefni/orchestrator/
cp -a "$BACKUP/restore-new/orchestrator/action_registry.py" /opt/wathefni/orchestrator/
cp -a "$BACKUP/restore-new/orchestrator/workspace_capability.py" /opt/wathefni/orchestrator/
rsync -a --delete "$BACKUP/restore-new/dashboard-dist/" /var/www/wathefni-dashboard/
cp -a "$BACKUP/restore-new/dashboard-src/App.tsx" /opt/wathefni/apps/wathefni-dashboard/src/App.tsx
if [[ -f "$BACKUP/restore-new/dashboard-src/workspaceCapability.ts" ]]; then
  mkdir -p /opt/wathefni/apps/wathefni-dashboard/src/lib
  cp -a "$BACKUP/restore-new/dashboard-src/workspaceCapability.ts" /opt/wathefni/apps/wathefni-dashboard/src/lib/workspaceCapability.ts
fi
systemctl restart wathefni-orchestrator
sleep 5
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "restore_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Restored waveC-entitlement 20260801T042210Z"
