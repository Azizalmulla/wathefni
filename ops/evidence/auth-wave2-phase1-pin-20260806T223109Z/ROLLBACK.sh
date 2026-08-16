#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
PRIOR_GROUP="${1:-9dc373a9-b9ce-4a7a-9877-5023454ecdc3}"
npx eas-cli update:republish --group "$PRIOR_GROUP" --branch canary --non-interactive
echo "Republished $PRIOR_GROUP to canary."
