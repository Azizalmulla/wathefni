#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
rsync -a --delete "$ROOT/restore-new-dist/" /var/www/wathefni-dashboard/
systemctl reload caddy 2>/dev/null || caddy reload 2>/dev/null || systemctl reload nginx 2>/dev/null || true
echo RESTORE_NEW_OK
