#!/usr/bin/env bash
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
EXPO_PUBLIC_LOCAL_PIN_UNLOCK=1 EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK=1 EXPO_PUBLIC_LOCAL_AUTO_LOCK=0 \
EXPO_PUBLIC_API_BASE_URL=https://api.wathefni.ai EXPO_PUBLIC_PUSH_REGISTRATION_ENABLED=0 \
  npx eas-cli update --branch canary --message "DISABLE Phase 3 auto-lock" --non-interactive
