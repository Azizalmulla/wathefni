#!/usr/bin/env bash
# Publish Employee App canary OTA with Auth Wave 2 flags guaranteed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export EXPO_PUBLIC_LOCAL_PIN_UNLOCK="${EXPO_PUBLIC_LOCAL_PIN_UNLOCK:-1}"
export EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK="${EXPO_PUBLIC_LOCAL_BIOMETRIC_UNLOCK:-1}"
export EXPO_PUBLIC_LOCAL_AUTO_LOCK="${EXPO_PUBLIC_LOCAL_AUTO_LOCK:-1}"
export EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC="${EXPO_PUBLIC_LOCAL_AUTO_LOCK_BIOMETRIC:-1}"
export EXPO_PUBLIC_API_BASE_URL="${EXPO_PUBLIC_API_BASE_URL:-https://api.octo-hr.com}"

MSG="${1:-Employee App canary OTA}"

python3 scripts/verify-auth-wave2-flags.py --preflight

npx -y eas-cli@latest update \
  --branch canary \
  --environment production \
  --message "$MSG" \
  --non-interactive

python3 scripts/verify-auth-wave2-flags.py --dist
