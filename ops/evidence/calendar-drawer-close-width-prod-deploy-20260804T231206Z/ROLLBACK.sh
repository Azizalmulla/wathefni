#!/usr/bin/env bash
set -euo pipefail
BK_DIR="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$BK_DIR/dashboard-dist/" /opt/wathefni/dashboard-dist/
if [[ -d "$BK_DIR/www" ]] && [[ -n "$(ls -A "$BK_DIR/www" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BK_DIR/www/" /var/www/wathefni-dashboard/
fi
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done
echo ROLLBACK_OK calendar-drawer-close-width
