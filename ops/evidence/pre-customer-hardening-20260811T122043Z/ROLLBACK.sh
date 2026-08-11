#!/usr/bin/env bash
# Pre-Customer Hardening Wave — rollback.
set -euo pipefail

VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
BACKUP="/opt/wathefni/backups/pre-customer-hardening-20260811T122043Z"

echo "== 1. Mobile OTA: republish the prior canary group"
( cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile" \
  && npx eas-cli@latest update:republish --group 75042c41-ca1b-4e10-8306-dd16c84c256c --branch canary --non-interactive )

echo "== 2. Orchestrator code"
ssh -o BatchMode=yes "$VPS_HOST" "cp $BACKUP/code/*.py /opt/wathefni/orchestrator/ && systemctl restart wathefni-orchestrator.service && sleep 8 && curl -fsS localhost:8010/health >/dev/null && echo orchestrator_restored"

echo "== 3. HR web dashboard bundle (served from /opt/wathefni/dashboard-dist per Caddyfile)"
ssh -o BatchMode=yes "$VPS_HOST" "rsync -a --delete /opt/wathefni/backups/dashboard-dist-20260811T124800Z/ /opt/wathefni/dashboard-dist/ && echo dashboard_restored"

cat <<'NOTE'
== 4. Schema (only if genuinely required)
The schema changes are additive and backward compatible; rolling back code does
not require dropping them. If they must be reverted:
  ALTER TABLE candidates ALTER COLUMN active_company_code DROP NOT NULL;
  -- onboarding_items.company_code can stay; older code ignores it.
Row-level backups (pre-change) are CSV in:
  /opt/wathefni/backups/pre-customer-hardening-20260811T122043Z/{candidates,onboarding_items}.csv
The 7 deleted unowned candidate rows are in that candidates.csv.
NOTE
