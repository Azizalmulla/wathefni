#!/usr/bin/env bash
set -euo pipefail
BK_DIR="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$BK_DIR/dashboard-dist/" /opt/wathefni/dashboard-dist/
if [[ -d "$BK_DIR/www" ]] && [[ -n "$(ls -A "$BK_DIR/www" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BK_DIR/www/" /var/www/wathefni-dashboard/
fi
echo ROLLBACK_OK employee-profile-360-closure
