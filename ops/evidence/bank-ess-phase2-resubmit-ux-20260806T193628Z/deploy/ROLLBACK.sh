#!/usr/bin/env bash
set -euo pipefail
VPS=root@76.13.63.68
BACKUP=/opt/wathefni/backups/bank-ess-phase2-resubmit-20260806T193628Z
ssh "$VPS" "
  cp '$BACKUP/employee_bank_ess.py' '$BACKUP/employee_selfservice_wave5.py' /opt/wathefni/orchestrator/
  systemctl restart wathefni-orchestrator
  sleep 4
  curl -fsS http://127.0.0.1:8010/health
"
# OTA rollback: npx eas-cli update:republish --group f4f7a2d6-da32-45b6-a08c-4669e66701d4 --branch canary
