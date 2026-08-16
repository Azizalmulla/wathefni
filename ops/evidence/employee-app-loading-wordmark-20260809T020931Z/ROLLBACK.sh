#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile" 2>/dev/null || cd apps/wathefni-employee-mobile
npx eas-cli@latest update:republish --group e0dc5e93-7165-4e6d-a195-033c15dddc11 --branch canary --non-interactive
