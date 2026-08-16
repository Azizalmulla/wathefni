#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile" 2>/dev/null || cd apps/wathefni-employee-mobile
npx eas-cli@latest update:republish --group dd05381d-b2a0-4d59-b0f9-117e71b4b0f7 --branch canary --non-interactive
