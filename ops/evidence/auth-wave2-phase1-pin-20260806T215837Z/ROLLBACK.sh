#!/usr/bin/env bash
# Rollback Auth Wave 2 Phase 1 PIN OTA (restores prior canary JS; Wave 1 behavior).
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
# Prior canary group before Phase 1 PIN (onboarding-completion reconcile stamp):
PRIOR_GROUP="${1:-b540423a-de1a-44c9-afa5-caa9504d2957}"
npx eas-cli update:republish --group "$PRIOR_GROUP" --branch canary --non-interactive
echo "Republished prior group $PRIOR_GROUP to canary. Force-quit/reopen app to load."
