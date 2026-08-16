#!/usr/bin/env bash
# Roll back Phase 4 Forgot PIN OTA by republishing prior nav-preserve canary tip
# (re-checkout prior JS is operator-driven). Safer immediate path: republish
# AUTO_LOCK build without Phase 4 from git if needed — here we document prior group.
set -euo pipefail
echo "Prior canary group (nav preserve, no Forgot PIN UI): 9a9a11be-dc9a-4e01-a1ec-f6f98bc5e2de"
echo "To roll forward-disable Phase 4, republish that tree from evidence auth-wave2-phase3b-nav-preserve-20260807T035603Z/docs"
echo "Or: eas update:rollback if available for group af0c0998-d41b-4f68-a2a2-3fabc06537c0"
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
echo "Manual: checkout prior commit/tree and eas update --branch canary"
