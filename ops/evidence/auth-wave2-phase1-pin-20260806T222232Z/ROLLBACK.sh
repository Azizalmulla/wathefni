#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
PRIOR_GROUP="${1:-173506a4-e2ea-4a66-9d1e-d5b2860c426c}"
npx eas-cli update:republish --group "$PRIOR_GROUP" --branch canary --non-interactive
echo "Republished $PRIOR_GROUP to canary."
