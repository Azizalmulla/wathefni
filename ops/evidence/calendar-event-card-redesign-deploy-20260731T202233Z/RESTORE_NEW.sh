#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$ROOT/restore-new-dist/" /var/www/wathefni-dashboard/
systemctl reload caddy || true
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "restore_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Restored calendar-event-card-redesign 20260731T202233Z"
