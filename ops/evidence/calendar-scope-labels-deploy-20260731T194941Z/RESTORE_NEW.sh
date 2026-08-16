#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$ROOT/restore-new-dist/" /var/www/wathefni-dashboard/
cp -a /opt/wathefni/production-evidence/calendar-scope-labels/20260731T194941Z/calendar_projections.py /opt/wathefni/orchestrator/calendar_projections.py
systemctl restart wathefni-orchestrator
sleep 3
systemctl reload caddy || true
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "restore_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Restored calendar-scope-labels 20260731T194941Z"
