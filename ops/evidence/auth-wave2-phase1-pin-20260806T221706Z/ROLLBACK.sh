#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
PRIOR_GROUP="${1:-b41cdbcf-9338-4073-a0be-af8ea9773c71}"
npx eas-cli update:republish --group "$PRIOR_GROUP" --branch canary --non-interactive
echo "Republished $PRIOR_GROUP to canary."
