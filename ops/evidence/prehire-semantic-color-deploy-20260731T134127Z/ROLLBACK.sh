#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Rolled back semantic-color 20260731T134127Z"
