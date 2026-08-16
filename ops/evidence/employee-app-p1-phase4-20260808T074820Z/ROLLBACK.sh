#!/usr/bin/env bash
# Roll back Employee App P1 Phase 4 on production.
#
# Backend: restore app.py + outbound_delivery.py from the Phase 4 backup
# (removes push data path enrichment; push still delivers, tap falls back to Inbox
# on older clients).
# Mobile: republish prior canary OTA group (Payslips P0.1).
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
BACKUP="${BACKUP:-/opt/wathefni/backups/employee-app-p1-phase4-20260808T074820Z}"
PRIOR_OTA_GROUP="${PRIOR_OTA_GROUP:-905477b6-1db1-4b6b-b0c8-bcc72bb32c3a}"

ssh -o BatchMode=yes "$VPS" "set -e
  test -f '$BACKUP'/app.py
  install -m 644 '$BACKUP'/app.py /opt/wathefni/orchestrator/
  if [ -f '$BACKUP'/outbound_delivery.py ]; then
    install -m 644 '$BACKUP'/outbound_delivery.py /opt/wathefni/orchestrator/
  fi
  /opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app.py /opt/wathefni/orchestrator/outbound_delivery.py
  systemctl restart wathefni-orchestrator.service
  sleep 22
  systemctl is-active wathefni-orchestrator.service
  curl -sS -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health"

echo "Backend restored from $BACKUP"
echo "To roll mobile JS back to prior canary group $PRIOR_OTA_GROUP:"
echo "  cd apps/wathefni-employee-mobile && npx eas-cli update:rollback --branch canary --group-id $PRIOR_OTA_GROUP --non-interactive"
echo "  (or republish that group's message via eas update from the prior tag)"
echo "EMPLOYEE_APP_P1_PHASE4_ROLLBACK_BACKEND_OK"
