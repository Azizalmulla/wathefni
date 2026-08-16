#!/usr/bin/env bash
# Remove temporary Aziz Bank ESS canary allowlist after Phase 2.
# Restores synthetic-only Bank ESS + prior ESS real allowlist (Talal only).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
DROPIN="zzzzzzzzzzzzzzzzzzzzzzzz-bank-ess-aziz-temp-phase2-canary.conf"
REMOTE="/etc/systemd/system/wathefni-orchestrator.service.d/${DROPIN}"

ssh -o BatchMode=yes "$VPS_HOST" bash -s <<EOF
set -euo pipefail
if [[ -f "$REMOTE" ]]; then
  mkdir -p /opt/wathefni/backups/bank-ess-aziz-temp-cleanup
  cp "$REMOTE" "/opt/wathefni/backups/bank-ess-aziz-temp-cleanup/${DROPIN}.\$(date -u +%Y%m%dT%H%M%SZ)"
  rm -f "$REMOTE"
  echo "removed $REMOTE"
else
  echo "drop-in already absent: $REMOTE"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8010/health
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST|WATHEFNI_EMPLOYEE_ESS_V5_REAL_ALLOWLIST|WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST' | sort
EOF

echo "Cleanup complete. Re-prove Aziz should be bank_ess_not_allowlisted on /app/me + no open_bank."
