#!/usr/bin/env bash
set -euo pipefail
cd /Users/azizalmulla/Desktop/claw/apps/wathefni-employee-mobile
npx eas-cli update:rollback 85f648c9-73a0-4b14-9d8e-838913496a4d \
  --message "Rollback Bank ESS OTA fix 20260806T172002Z" \
  --platform all --non-interactive
