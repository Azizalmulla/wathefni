#!/usr/bin/env bash
# Clean canary company through Setup on isolated staging. No SQL fixtures.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/store-release-clean-canary-$STAMP"
REMOTE_STAGE="/tmp/store-release-clean-canary-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,sources}
cp -a "$REPO_ROOT/ops/e2e/clean-canary.py" "$LOCAL_EVID/sources/"

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "$REPO_ROOT/ops/e2e/clean-canary.py" "$VPS_HOST:$REMOTE_STAGE/clean-canary.py"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/clean-canary.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
PYBIN=\$PROD/.venv/bin/python
export PYTHONPATH="\$STG:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
export WATHEFNI_ENV=staging
export WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DELIVERY_MODE=dry_run
export WATHEFNI_CANARY_BASE=http://127.0.0.1:8011
export WATHEFNI_SETUP_OPERATOR_ENV=/root/.openclaw/secrets/wathefni-setup-operator.env
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" '$REMOTE_STAGE/clean-canary.py'
REMOTE

echo "EVIDENCE=$LOCAL_EVID"
if grep -q "CLEAN_CANARY_PASS" "$LOCAL_EVID/tests/clean-canary.out"; then
  echo CLEAN_CANARY_GREEN
  exit 0
fi
if grep -q "CLEAN_CANARY_BLOCKED" "$LOCAL_EVID/tests/clean-canary.out"; then
  echo CLEAN_CANARY_BLOCKED
  exit 2
fi
echo CLEAN_CANARY_RED
exit 1
