#!/usr/bin/env bash
set -euo pipefail
# Rollback eligibility OTA to prior crash-fix tip (85f648c9…)
cd "$(dirname "$0")/../../../../apps/wathefni-employee-mobile"
npx --yes eas-cli update:rollback 388e8cf5-1d6b-4140-9c84-bfff55504928 \
  --message "Rollback Bank ESS eligibility OTA" \
  --platform all --non-interactive
# Or re-point canary tip by republishing prior group 85f648c9-73a0-4b14-9d8e-838913496a4d assets.
