#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl reload caddy || true
echo "Rolled back candidates-quiet 20260731T192545Z"
