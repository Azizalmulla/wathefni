#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"

echo "Publishing AUTO_LOCK=1 AUTO_LOCK_BIOMETRIC=0 (PIN-only overlay) on canary…"
EXPO_PUBLIC_LOCAL_PIN_UNLOCK=1 \
EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK=1 \
EXPO_PUBLIC_LOCAL_AUTO_LOCK=1 \
EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC=0 \
EXPO_PUBLIC_API_BASE_URL=https://api.wathefni.ai \
EXPO_PUBLIC_PUSH_REGISTRATION_ENABLED=0 \
  npx eas-cli update --branch canary \
  --message "ROLLBACK Phase 3B arm-fix: disable overlay Face ID (PIN-only)" \
  --clear-cache --non-interactive
