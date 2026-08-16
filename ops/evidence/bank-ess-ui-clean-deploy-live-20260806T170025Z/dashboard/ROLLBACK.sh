#!/usr/bin/env bash
set -euo pipefail
# Restore pre-Bank-ESS-UI dashboard (PostHire-6LCFY5pA)
rsync -a --delete /opt/wathefni/dashboard-dist-bak/bank-ess-ui-20260806T170025Z/ /var/www/wathefni-dashboard/
curl -sS -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8010/health
sha256sum /var/www/wathefni-dashboard/assets/PostHire-*.js
