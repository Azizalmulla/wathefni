#!/usr/bin/env bash
# Rollback for bank-ess-onboarding-broad-rollout-20260806T205803Z
# Restores pre-broad Bank ESS / app allowlists. Does NOT touch Auth Wave 2,
# Settings/setup WIP, or the pending_payroll→hr ownership behavior.
set -euo pipefail
STAMP=20260806T205803Z
VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
BK="/opt/wathefni/backups/bank-ess-broad-rollout-${STAMP}"

ssh -o BatchMode=yes "$VPS" bash -s <<EOF
set -euo pipefail
BK="$BK"
# 1. Remove broad-rollout drop-in
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzzzzz-bank-ess-broad-rollout.conf
# 2. Restore temporary Aziz canary drop-in if backed up (pre-broad state)
if [[ -f "\$BK/zzzzzzzzzzzzzzzzzzzzzzzz-bank-ess-aziz-temp-phase2-canary.conf" ]]; then
  cp "\$BK/zzzzzzzzzzzzzzzzzzzzzzzz-bank-ess-aziz-temp-phase2-canary.conf" \
     /etc/systemd/system/wathefni-orchestrator.service.d/
  echo "restored Aziz temp canary drop-in"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in \$(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done
curl -fsS http://127.0.0.1:8010/health >/dev/null && echo API_OK
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'BANK_ESS_V1_EMPLOYEE|ESS_V5_BANK_REAL|EMPLOYEE_APP_REAL' | sort
EOF

echo "ROLLBACK_OK bank-ess-onboarding-broad-rollout-$STAMP"
echo "Note: OTA/dashboard rollback remains the canary stamp ROLLBACK.sh if client code must revert."
