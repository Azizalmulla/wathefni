#!/usr/bin/env bash
# Local / CI deploy gate. Broken R8/R7/R2 unit suites must not ship.
# Does not SSH. Does not apply schema. Historical deploy-*.sh stay unchanged;
# new deploys should invoke this script first.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
HR_SRC="$REPO_ROOT/apps/wathefni-hr-mobile"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

cd "$ORCH_SRC"
"$PY" smoke-test-r8-delivery-safety.py
"$PY" smoke-test-r7-mobile-native-safety.py
"$PY" smoke-test-r2-security.py

if [[ -x "$HR_SRC/node_modules/.bin/vitest" ]]; then
  (cd "$HR_SRC" && npx vitest run)
fi

if [[ -f "$MOBILE_SRC/scripts/composition-shapes-test.js" && -x "$MOBILE_SRC/node_modules/.bin/tsc" ]]; then
  (cd "$MOBILE_SRC" && node scripts/composition-shapes-test.js)
fi

echo "WATHEFNI_DEPLOY_GATE_OK"
