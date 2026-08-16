#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "rollback_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Rolled back assessment-configuration-ops 20260731T193752Z"
