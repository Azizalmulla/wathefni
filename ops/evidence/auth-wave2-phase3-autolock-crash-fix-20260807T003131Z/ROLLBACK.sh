#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
npx eas-cli update:republish --group 83fe64f6-a46f-4cfb-b6ed-6e7229a6c27a --non-interactive -m "ROLLBACK Phase 3 crash-fix"
