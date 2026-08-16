#!/usr/bin/env bash
set -euo pipefail
BACKUP="/opt/wathefni/backups/production-pre-waveC-entitlement-20260801T042210Z"
cp -a "$BACKUP/orchestrator/assistant_capability_catalog.py" /opt/wathefni/orchestrator/
cp -a "$BACKUP/orchestrator/action_registry.py" /opt/wathefni/orchestrator/
cp -a "$BACKUP/orchestrator/workspace_capability.py" /opt/wathefni/orchestrator/
rsync -a --delete "$BACKUP/dashboard-dist/" /var/www/wathefni-dashboard/
if [[ -f "$BACKUP/dashboard-src/App.tsx" ]]; then
  cp -a "$BACKUP/dashboard-src/App.tsx" /opt/wathefni/apps/wathefni-dashboard/src/App.tsx
fi
systemctl restart wathefni-orchestrator
sleep 5
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "rollback_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Rolled back waveC-entitlement 20260801T042210Z"
