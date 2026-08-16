#!/usr/bin/env bash
set -euo pipefail
snap="$(cd "$(dirname "$0")" && pwd)"
echo "Restoring Interviews pre-promote snapshot: $snap"
tar -xzf "$snap/orchestrator.tgz" -C /opt/wathefni/orchestrator
rm -rf /var/www/wathefni-dashboard.rb
mkdir -p /var/www/wathefni-dashboard.rb
tar -xzf "$snap/dashboard-public.tgz" -C /var/www/wathefni-dashboard.rb
rsync -a --delete /var/www/wathefni-dashboard.rb/ /var/www/wathefni-dashboard/
rm -rf /var/www/wathefni-dashboard.rb
systemctl restart wathefni-orchestrator.service
sleep 3
systemctl reload caddy
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health
echo "DB restore ONLY if required (destructive):"
echo "  set -a; . /root/.openclaw/secrets/postgres.env; set +a"
echo "  pg_restore --clean --if-exists -d \"\$DATABASE_URL\" \"$snap/wathefni.dump\""
