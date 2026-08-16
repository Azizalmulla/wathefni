#!/usr/bin/env bash
# Roll back Employee App P1 Phase 3 (Profile projection enrichment) on production.
#
# Backend-only: /app/profile loses personal/employment structured sections and returns
# to the lean employee + onboarding payload. No schema or data change was made.
# Mobile Phase 3 is JS-only — revert via OTA, not a native rebuild.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
BACKUP="${BACKUP:-/opt/wathefni/backups/employee-app-p1-phase3-20260808T073000Z}"

ssh -o BatchMode=yes "$VPS" "set -e
  test -f '$BACKUP'/app.py
  install -m 644 '$BACKUP'/app.py /opt/wathefni/orchestrator/
  /opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app.py
  systemctl restart wathefni-orchestrator.service
  sleep 22
  systemctl is-active wathefni-orchestrator.service
  curl -sS -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health"
echo "EMPLOYEE_APP_P1_PHASE3_ROLLBACK_OK"
