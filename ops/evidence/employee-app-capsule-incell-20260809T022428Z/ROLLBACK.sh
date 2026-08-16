#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile" 2>/dev/null || cd apps/wathefni-employee-mobile
npx eas-cli@latest update:republish --group dff580af-bca4-44dd-94b8-97c5282b9968 --branch canary --non-interactive
