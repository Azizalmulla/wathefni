#!/usr/bin/env bash
# Cross-surface canonical-truth convergence across the store-release domains.
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
cp -a "$REPO_ROOT/ops/e2e/cross-surface-domain-matrix.py" "$LOCAL_EVID/sources/"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "$REPO_ROOT/ops/e2e/cross-surface-convergence.py" \
  "$REPO_ROOT/ops/e2e/cross-surface-domain-matrix.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-prehire-registry-parity.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-interview-workflow-live.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-onboarding-dashboard.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-attendance-truth-c1.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-shift-management.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-payroll-payslip-wave3.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-document-hub.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5b-performance-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5c-talent-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5e-learning-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5f-benefits-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5g-employee-relations-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5h-engagement-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5i-compensation-planning-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r5j-workforce-planning-surface-db.py" \
  "$REPO_ROOT/wathefni-orchestrator/smoke-test-r6-setup-self-service-db.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
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
WATHEFNI_ORCHESTRATOR_ROOT="\$STG" WATHEFNI_MATRIX_TEST_ROOT="$REMOTE_STAGE" \
  "\$PYBIN" '$REMOTE_STAGE/cross-surface-domain-matrix.py'
REMOTE
echo "EVIDENCE=$LOCAL_EVID"
if grep -q "CROSS_SURFACE_PASS" "$LOCAL_EVID/tests/cross-surface.out" && \
   grep -q "CROSS_SURFACE_DOMAIN_MATRIX_PASS" "$LOCAL_EVID/tests/cross-surface.out"; then
  echo CROSS_SURFACE_GREEN
  exit 0
fi
echo CROSS_SURFACE_RED
exit 1
