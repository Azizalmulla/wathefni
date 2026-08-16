#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/restore-new-orchestrator/app.py" "$PROD/app.py"
cp -a "$ROOT/restore-new-orchestrator/hire_operations.py" "$PROD/hire_operations.py"
cp -a "$ROOT/restore-new-orchestrator/module_catalog.py" "$PROD/module_catalog.py"
cp -a "$ROOT/restore-new-orchestrator/employee_status_approval.py" "$PROD/employee_status_approval.py"
rsync -a --delete "$ROOT/restore-new-dist/" /var/www/wathefni-dashboard/
systemctl daemon-reload
systemctl start wathefni-orchestrator.service
systemctl reload caddy || true
sleep 2
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
echo "Restored employees360-wave1-1b 20260801T193257Z"
