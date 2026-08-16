#!/usr/bin/env bash
# Production Readiness R3 — Production Data Safety qualification.
#
# Proves the R1 data-safety blocker set (P0-6 plus implicit WATHEFNI fallback
# and production-capable demo/fixture paths) against isolated staging:
#
#   1. local unit contracts        — pure logic + process refusals + source scan
#   2. staging database paths      — two isolated synthetic tenants, clean bootstrap
#   3. live deployed service       — restarted staging process, company fail-closed
#   4. Waves 1–6 + R2 regressions  — frozen surfaces stay green
#
# Does not touch production customer data. Does not begin R4.
# FULL_PASS here does not authorise production rollout.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r3-data-safety-$STAMP"
REMOTE_STAGE="/tmp/r3-data-safety-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,inventory}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  production_data_safety.py
  employee_migration_connectors.py
  smoke-test-r3-data-safety.py
  smoke-test-r3-data-safety-db.py
  ops-seed-inbox-visual-fixture.py
  smoke-test-r2-security-db.py
  smoke-test-internal-auth.py
)

log "1/6 local unit contracts + inventory"
cd "$ORCH_SRC"
"$PY" smoke-test-r3-data-safety.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"
R3_INVENTORY_OUT="$LOCAL_EVID/inventory/script-inventory.json" "$PY" "$REPO_ROOT/ops/r3-data-safety-inventory.py" \
  2>&1 | tee "$LOCAL_EVID/inventory/scan.out"

log "2/6 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/apps/wathefni-employee-mobile/src/hr/features/demoProductionGuard.ts" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/apps/wathefni-employee-mobile/app.config.js" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R3_DATA_SAFETY_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/production_data_safety.py'
test -f '$STG/employee_migration_connectors.py'
python3 -m py_compile '$STG/production_data_safety.py'
echo STAGING_COPY_OK
REMOTE

staging_py() {
  local script="$1" out="$2"
  "${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$out"
set -euo pipefail
STG=$STG
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
"\$PYBIN" "$script"
echo STAGING_RC=\$?
REMOTE
}

log "3/6 staging database data-safety paths (isolated synthetic tenants)"
staging_py smoke-test-r3-data-safety-db.py "$LOCAL_EVID/tests/staging-db.out"

log "4/6 live deployed staging service"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
S=000
for i in $(seq 1 15); do
  sleep 8
  S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health)
  [ "$S" = "200" ] && break
done
echo "staging_health=$S"
[ "$S" = "200" ] || { echo "LIVE_SERVICE 0 passed, 1 failed"; exit 0; }

STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
export PYTHONPATH="$STG:$PROD"
export WATHEFNI_ENV=staging
export WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"$PROD/.venv/bin/python" - <<'PY'
import os, sys
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
import production_data_safety as pds
from fastapi import HTTPException
import app

P = F = 0
def ck(label, cond, detail=None):
    global P, F
    if cond:
        P += 1
        print(f"      PASS  {label}")
    else:
        F += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")

try:
    app.require_company_code(None)
    ck("live missing company fails closed", False)
except HTTPException as exc:
    ck("live missing company fails closed", exc.status_code == 400, exc.status_code)
    ck("live missing company does not resolve to WATHEFNI", "WATHEFNI" not in str(exc.detail))
ck("live explicit tenant still resolves", app.require_company_code("R3LIVEOK") == "R3LIVEOK")
ck("live WATHEFNI still resolves only when named", app.require_company_code("WATHEFNI") == "WATHEFNI")
ck("live synthetic connectors off by default", pds.synthetic_connectors_allowed("R3LIVEOK") is False)
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "5/6 regressions (Waves 1–6 + R2 security + internal-auth)"
REG_OK=YES
set +e
for t in smoke-test-wave6-product-acceptance smoke-test-job-architecture-c1 smoke-test-learning-development-c2 \
         smoke-test-benefits-administration-c3 smoke-test-employee-relations-c4 smoke-test-engagement-c5 \
         smoke-test-compensation-planning-c6 smoke-test-workforce-planning-c7 smoke-test-wave5-product-acceptance \
         smoke-test-wave4-product-acceptance smoke-test-wave3-product-acceptance smoke-test-wave2-product-acceptance \
         smoke-test-wave1-product-acceptance smoke-test-r2-security; do
  "$PY" "$ORCH_SRC/$t.py" >"$LOCAL_EVID/regression/$t.out" 2>&1
  echo "$t rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
done
"$PY" -m unittest test_interaction_authority_contracts >"$LOCAL_EVID/regression/interaction-authority-contracts.out" 2>&1
echo "interaction_authority_contracts rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
set -e
staging_py smoke-test-internal-auth.py "$LOCAL_EVID/regression/internal-auth-staging.out"
staging_py smoke-test-r2-security-db.py "$LOCAL_EVID/regression/r2-security-db.out"
for f in "$LOCAL_EVID"/regression/smoke-test-*.out; do
  grep -qE '^[[:space:]]*FAIL  |Traceback' "$f" && REG_OK=NO
  grep -qE '[0-9]+ passed' "$f" || REG_OK=NO
done
grep -q 'OK' "$LOCAL_EVID/regression/interaction-authority-contracts.out" || REG_OK=NO
grep -q 'ALL CHECKS PASSED' "$LOCAL_EVID/regression/internal-auth-staging.out" || REG_OK=NO
grep -q 'R2_SECURITY_FULL_PASS' "$LOCAL_EVID/regression/r2-security-db.out" || REG_OK=NO

log "6/6 verdict"
UNIT_OK=NO
grep -q 'R3_DATA_SAFETY_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" && UNIT_OK=YES

DB_OK=NO
grep -q 'R3_DATA_SAFETY_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES

DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES

INV_OK=NO
set +e
python3 - <<'PY'
import json, pathlib, sys, os
p = pathlib.Path(os.environ["LOCAL_EVID"]) / "inventory" / "script-inventory.json"
if not p.exists():
    sys.exit(1)
data = json.loads(p.read_text())
sys.exit(1 if data.get("counts_by_disposition", {}).get("unsafe_production_default") else 0)
PY
inv_rc=$?
set -e
if [[ "$inv_rc" -eq 0 ]]; then INV_OK=YES; else INV_OK=NO; fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES && "$LIVE_OK" == YES && "$REG_OK" == YES && "$DEPLOY_OK" == YES && "$INV_OK" == YES ]]; then
  VERDICT='PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Production Readiness R3 — Production Data Safety

- Stamp: $STAMP
- Local unit contracts: $UNIT_OK
- Script inventory (no live production defaults): $INV_OK
- Staging deploy: $DEPLOY_OK
- Staging DB data-safety paths (isolated synthetic tenants): $DB_OK
- Live deployed staging service: $LIVE_OK
- Waves 1–6 + R2 security + internal-auth regressions: $REG_OK
- Verdict: **$VERDICT**

Scope: R1 P0-6, implicit WATHEFNI fallback, production-capable demo/fixture paths.
Does not touch production customer data. Does not begin R4 Truth-in-UI.
FULL_PASS is not authorisation for production rollout.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS" ]]
