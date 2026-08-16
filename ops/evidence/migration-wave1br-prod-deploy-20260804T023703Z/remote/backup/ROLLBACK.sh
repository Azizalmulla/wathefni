#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
test -d "$BACKUP_DIR/modules"
for f in app.py inbound_cv_intake.py inbound_cv_processing.py inbound_cv_adapters.py durable_email_ingress.py migration_wave1_cv_foundation.py schema_contract.py; do
  if [[ -f "$BACKUP_DIR/modules/$f" ]]; then
    cp -a "$BACKUP_DIR/modules/$f" "$ORCH/$f"
  else
    rm -f "$ORCH/$f"
  fi
done
# Ensure SCHEMA_APPLY not left enabled
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzz-schema-wave1br-apply.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
