#!/usr/bin/env bash
# Roll back Employee App P1 Phase 1 (Home projection) on the production orchestrator.
#
# Backend-only: /app/home disappears and the module read endpoints keep the contracts
# they already had, so an un-rolled-back client falls back to reading them directly.
# No schema or data change was made by this phase, so there is nothing to unwind.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
BACKUP="${BACKUP:-/opt/wathefni/backups/employee-app-p1-home-20260808T062710Z}"

ssh -o BatchMode=yes "$VPS" "set -e
  test -f '$BACKUP'/app.py
  install -m 644 '$BACKUP'/app.py /opt/wathefni/orchestrator/
  /opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app.py
  systemctl restart wathefni-orchestrator.service
  sleep 10
  systemctl is-active wathefni-orchestrator.service
  curl -sS -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health"
echo "EMPLOYEE_APP_P1_PHASE1_ROLLBACK_OK"
