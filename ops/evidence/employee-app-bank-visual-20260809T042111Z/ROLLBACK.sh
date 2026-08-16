#!/usr/bin/env bash
set -euo pipefail
# Rollback Bank visual OTA to Documents density tip, and optionally clear fixtures.
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
npx -y eas-cli@latest update:republish --group 0561f73f-4b2b-4592-896c-874244ab2639 --branch canary --non-interactive
echo "OTA rolled back to 0561f73f-4b2b-4592-896c-874244ab2639"
if [[ "${1:-}" == "--cleanup-fixtures" ]]; then
  ssh root@76.13.63.68 'cd /opt/wathefni/orchestrator && .venv/bin/python ops-seed-bank-visual-fixture.py --cleanup'
fi
