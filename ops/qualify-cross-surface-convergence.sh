#!/usr/bin/env bash
# Cross-surface leave/attendance/module-disable convergence on staging DB.
set -euo pipefail
VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/e2e-cross-surface-$STAMP"
REMOTE_STAGE="/tmp/e2e-cross-surface-stage"
STG=/opt/wathefni/staging/orchestrator
mkdir -p "$LOCAL_EVID"/{tests,sources}
cp -a "$REPO_ROOT/ops/e2e/cross-surface-convergence.py" "$LOCAL_EVID/sources/"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "$REPO_ROOT/ops/e2e/cross-surface-convergence.py" "$VPS_HOST:$REMOTE_STAGE/cross-surface-convergence.py"
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/cross-surface.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
PYBIN=\$PROD/.venv/bin/python
export PYTHONPATH="\$STG:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DELIVERY_MODE=dry_run
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" '$REMOTE_STAGE/cross-surface-convergence.py'
REMOTE
echo "EVIDENCE=$LOCAL_EVID"
if grep -q "CROSS_SURFACE_PASS" "$LOCAL_EVID/tests/cross-surface.out"; then
  echo CROSS_SURFACE_GREEN
  exit 0
fi
echo CROSS_SURFACE_RED
exit 1
