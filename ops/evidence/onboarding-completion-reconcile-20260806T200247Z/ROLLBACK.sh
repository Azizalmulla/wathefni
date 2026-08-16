#!/usr/bin/env bash
# Rollback for 20260806T200247Z — onboarding canonical state + next action.
# Order matters: OTA first (fastest to reach devices), then dashboard, then API.
set -euo pipefail
STAMP=20260806T200247Z
VPS=root@76.13.63.68

# 1. Mobile OTA: republish the previous canary group (Bank ESS resubmit UX).
#    Run from the mobile OTA lane, not the dirty main tree.
#    cd /tmp/wf-bank-ess-ota-p2-20260806T184542Z
#    npx eas-cli update:republish --group e3d3ffae-14a8-42f9-bc87-301763b0b0cd --branch canary

# 2. Dashboard bundle (onboarding drawer / queue UX).
ssh -o BatchMode=yes "$VPS" "rsync -a --delete /opt/wathefni/backups/dashboard-onboarding-ux-$STAMP/ /var/www/wathefni-dashboard/"

# 3. Orchestrator: next-item selection + reopened ownership.
ssh -o BatchMode=yes "$VPS" "cd /opt/wathefni/orchestrator \
  && cp /opt/wathefni/backups/onboarding-next-item-$STAMP/app.py app.py \
  && cp /opt/wathefni/backups/onboarding-next-item-$STAMP/onboarding_completion_contract.py onboarding_completion_contract.py \
  && systemctl restart wathefni-orchestrator \
  && for i in \$(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done \
  && curl -fsS http://127.0.0.1:8010/health >/dev/null && echo API_OK"

echo "ROLLBACK_OK onboarding-completion-reconcile-$STAMP (step 1 OTA is manual — see comment)"
