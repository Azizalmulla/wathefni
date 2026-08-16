#!/usr/bin/env bash
set -euo pipefail

VPS=root@76.13.63.68
STAMP=20260806T191329Z
BACKUP="/opt/wathefni/backups/bank-ess-phase2-approval-validation-$STAMP"
DASH_BACKUP="/opt/wathefni/dashboard-dist-bak/bank-ess-phase2-approval-validation-$STAMP"

ssh "$VPS" "
  cp '$BACKUP/employee_bank_ess.py' '$BACKUP/employee_selfservice_wave5.py' /opt/wathefni/orchestrator/
  rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzzzzzz-bank-ess-validation-enforced.conf
  rsync -a --delete '$DASH_BACKUP/' /var/www/wathefni-dashboard/
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator
  sleep 4
  curl -fsS http://127.0.0.1:8010/health
"

# OTA rollback (run from the employee-mobile release tree with EAS access):
# npx eas-cli update:republish --group 59ec9dc5-2ffb-4018-b64c-788f3bb94b31 --branch canary --non-interactive
#
# The audited validation_return event is production history and must not be
# deleted by a code rollback.
