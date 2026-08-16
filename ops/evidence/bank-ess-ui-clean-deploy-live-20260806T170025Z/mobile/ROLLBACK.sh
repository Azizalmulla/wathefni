#!/usr/bin/env bash
set -euo pipefail
cd /Users/azizalmulla/Desktop/claw/apps/wathefni-employee-mobile
npx eas-cli update:rollback 326e2040-6603-4c34-a6db-1022ff8095a6 \
  --message "Rollback Bank ESS UI OTA 20260806T170025Z" \
  --platform all --non-interactive
