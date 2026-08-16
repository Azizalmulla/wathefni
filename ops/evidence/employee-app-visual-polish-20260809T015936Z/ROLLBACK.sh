#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile" 2>/dev/null || cd apps/wathefni-employee-mobile
npx eas-cli@latest update:republish --group c4249469-8c13-4d47-a053-ded2149dc3f3 --branch canary --non-interactive
