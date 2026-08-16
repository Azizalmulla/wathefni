#!/usr/bin/env bash
set -euo pipefail

HOST="${WATHEFNI_PRODUCTION_HOST:-root@76.13.63.68}"
BACKUP="/opt/wathefni/backups/production-pre-full-interaction-audit-20260805T195406Z"
LATE_BACKUP="/opt/wathefni/backups/production-pre-interaction-audit-late-20260805T220256Z"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

# First return the late follow-up (backend authority, gateway auth, dashboard)
# to the already-qualified base audit state.
ssh "$HOST" "'$LATE_BACKUP/ROLLBACK.sh'"

ssh "$HOST" "set -e
  cd '$BACKUP'
  sha256sum -c SHA256SUMS
  install -m 0644 '$BACKUP/talent_pool_classification_routes.py' /opt/wathefni/orchestrator/talent_pool_classification_routes.py
  rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzzz-full-interaction-capacity.conf
  rm -rf '$BACKUP/dashboard-restore'
  mkdir -p '$BACKUP/dashboard-restore'
  tar -C '$BACKUP/dashboard-restore' -xzf '$BACKUP/wathefni-dashboard.tar.gz'
  rsync -a --delete '$BACKUP/dashboard-restore/wathefni-dashboard/' /var/www/wathefni-dashboard/
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator.service
  for i in \$(seq 1 30); do
    if curl -fsS http://127.0.0.1:8010/health >/dev/null; then
      systemctl is-active wathefni-orchestrator.service
      exit 0
    fi
    sleep 1
  done
  exit 1
"

# The canary branch had no prior OTA update, so this republishes the embedded
# runtime 0.1.0 bundle for both platforms.
(
  cd "$ROOT/apps/wathefni-employee-mobile"
  npx eas-cli update:rollback 34a288bc-36c6-40fb-80e3-a38fe5449320 \
    --message "Rollback interaction authority fixes 20260805T220256Z" \
    --platform all \
    --non-interactive
)
