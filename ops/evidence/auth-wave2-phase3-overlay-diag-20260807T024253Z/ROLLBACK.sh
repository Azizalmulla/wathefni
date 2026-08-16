#!/usr/bin/env bash
# Disable auto-lock (safe) or republish prior PIN-overlay OTA.
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"

echo "Publishing AUTO_LOCK=0 disable OTA on canary…"
EXPO_PUBLIC_LOCAL_PIN_UNLOCK=1 \
EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK=1 \
EXPO_PUBLIC_LOCAL_AUTO_LOCK=0 \
EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC=0 \
EXPO_PUBLIC_API_BASE_URL=https://api.wathefni.ai \
EXPO_PUBLIC_PUSH_REGISTRATION_ENABLED=0 \
  npx eas-cli update --branch canary \
  --message "ROLLBACK Phase 3: disable auto-lock (from overlay-diag)" \
  --clear-cache --non-interactive
