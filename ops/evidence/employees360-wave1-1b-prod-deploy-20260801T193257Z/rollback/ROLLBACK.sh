#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/orchestrator/app.py.pre" "$PROD/app.py"
cp -a "$ROOT/orchestrator/hire_operations.py.pre" "$PROD/hire_operations.py"
cp -a "$ROOT/orchestrator/module_catalog.py.pre" "$PROD/module_catalog.py"
rm -f "$PROD/employee_status_approval.py"
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl daemon-reload
systemctl start wathefni-orchestrator.service
systemctl reload caddy || true
sleep 2
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health || true
echo "Rolled back employees360-wave1-1b 20260801T193257Z"
