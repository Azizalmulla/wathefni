#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile" 2>/dev/null || cd apps/wathefni-employee-mobile
npx eas-cli@latest update:republish --group c12f398e-68a6-4c77-8781-6315d2402a92 --branch canary --non-interactive
