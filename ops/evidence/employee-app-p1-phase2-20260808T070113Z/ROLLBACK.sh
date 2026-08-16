#!/usr/bin/env bash
# Roll back Employee App P1 Phase 2 (read-only Schedule projection) on production.
#
# Backend-only: /app/workday disappears and the Shifts / Attendance read endpoints keep
# the contracts they already had. No schema or data change was made, so there is nothing
# to unwind. The mobile side of this phase is JS-only, so reverting the client is an OTA
# revert rather than a native rebuild.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
BACKUP="${BACKUP:-/opt/wathefni/backups/employee-app-p1-workday-20260808T070000Z}"

ssh -o BatchMode=yes "$VPS" "set -e
  test -f '$BACKUP'/app.py
  install -m 644 '$BACKUP'/app.py /opt/wathefni/orchestrator/
  /opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app.py
  systemctl restart wathefni-orchestrator.service
  sleep 22
  systemctl is-active wathefni-orchestrator.service
  curl -sS -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health"
echo "EMPLOYEE_APP_P1_PHASE2_ROLLBACK_OK"
