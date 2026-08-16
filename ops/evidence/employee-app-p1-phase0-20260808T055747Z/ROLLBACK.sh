#!/usr/bin/env bash
# Roll back Employee App P1 Phase 0 backend files on the production orchestrator.
#
# The access-flag reconcile is intentionally NOT rolled back: it only enabled employees
# who already held a live session, and the pre-repair code does not read the flag at all.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
BACKUP="${BACKUP:-/opt/wathefni/backups/employee-app-p0-20260808T055747Z}"

ssh -o BatchMode=yes "$VPS" "set -e
  test -d '$BACKUP'
  install -m 644 '$BACKUP'/app.py '$BACKUP'/employee_app_access.py '$BACKUP'/payroll_payslip_wave3.py /opt/wathefni/orchestrator/
  /opt/wathefni/orchestrator/.venv/bin/python -m py_compile /opt/wathefni/orchestrator/app.py
  systemctl restart wathefni-orchestrator.service
  sleep 5
  systemctl is-active wathefni-orchestrator.service
  curl -sS -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health"
echo "EMPLOYEE_APP_P1_PHASE0_ROLLBACK_OK"
