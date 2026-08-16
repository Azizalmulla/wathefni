#!/usr/bin/env bash
# PT1 — OKR Operating Depth + Talent Evidence Index qualification.
# Does not begin PT2. Does not resume R7.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/pt1-okr-evidence-$STAMP"
REMOTE_STAGE="/tmp/pt1-okr-evidence-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,dashboard,mobile,inventories}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  module_catalog.py
  capability_readiness.py
  setup_console_wave4_policies.py
  performance_surfaces.py
  performance_http.py
  talent_surfaces.py
  talent_http.py
  performance_goals_c1.py
  performance_reviews_c2.py
  performance_feedback_c3.py
  performance_calibration_c4.py
  talent_profile_c5.py
  talent_succession_c6.py
  okr_operating_pt1.py
  talent_evidence_index_pt1.py
  smoke-test-pt1-okr-evidence.py
  smoke-test-pt1-okr-evidence-db.py
  smoke-test-r5b-performance-surface.py
  smoke-test-r5c-talent-surface.py
  smoke-test-r5a-capability-honesty.py
  smoke-test-r6-setup-self-service.py
  smoke-test-r4-truth-in-ui.py
  smoke-test-r3-data-safety.py
  smoke-test-r2-security-db.py
  smoke-test-internal-auth.py
)

log "1/8 dashboard vitest + employee composition"
cd "$DASH_SRC"
if [[ -x "$DASH_SRC/node_modules/.bin/vitest" ]]; then
  npx vitest run \
    src/lib/workspaceCapability.test.ts \
    src/lib/dashboardNavigation.test.ts \
    src/lib/moduleWorkspace.test.ts \
    src/pages/shared/dataState.test.tsx \
    2>&1 | tee "$LOCAL_EVID/dashboard/named.out"
  npx vitest run 2>&1 | tee "$LOCAL_EVID/dashboard/full.out"
else
  echo "vitest missing" | tee "$LOCAL_EVID/dashboard/named.out"
  exit 1
fi
cd "$MOBILE_SRC"
node scripts/composition-shapes-test.js 2>&1 | tee "$LOCAL_EVID/mobile/composition.out"

log "2/8 local PT1 unit contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-pt1-okr-evidence.py 2>&1 | tee "$LOCAL_EVID/tests/pt1-unit.out"

log "3/8 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/okr_operating_pt1.py'
test -f '$STG/talent_evidence_index_pt1.py'
python3 -m py_compile '$STG/okr_operating_pt1.py' '$STG/talent_evidence_index_pt1.py' '$STG/performance_http.py' '$STG/talent_http.py'
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

log "4/8 staging DB journeys A–H"
staging_py smoke-test-pt1-okr-evidence-db.py "$LOCAL_EVID/tests/staging-db.out"

log "5/8 live deployed staging service"
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

python3 - <<'PY'
import json, urllib.request, urllib.error
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

def fetch(path, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:8011" + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body

status, body = fetch("/health")
ck("live health", status == 200, status)
for path in (
    "/dashboard/performance/okr-cycles",
    "/dashboard/performance/workspace",
    "/app/performance/okr-cycles/current",
    "/dashboard/posthire/talent/evidence-index/x",
):
    status, body = fetch(path)
    ck(f"live {path} not public", status in (401, 403, 503), status)
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "6/8 regressions (Waves 1–6 + R2–R6 + R5 surfaces)"
REG_OK=YES
set +e
for t in smoke-test-wave6-product-acceptance smoke-test-job-architecture-c1 smoke-test-learning-development-c2 \
         smoke-test-benefits-administration-c3 smoke-test-employee-relations-c4 smoke-test-engagement-c5 \
         smoke-test-compensation-planning-c6 smoke-test-workforce-planning-c7 smoke-test-wave5-product-acceptance \
         smoke-test-wave4-product-acceptance smoke-test-wave3-product-acceptance smoke-test-wave2-product-acceptance \
         smoke-test-wave1-product-acceptance smoke-test-r2-security smoke-test-r3-data-safety smoke-test-r4-truth-in-ui \
         smoke-test-r5a-capability-honesty smoke-test-r5b-performance-surface smoke-test-r5c-talent-surface \
         smoke-test-r6-setup-self-service; do
  if [[ -f "$ORCH_SRC/$t.py" ]]; then
    "$PY" "$ORCH_SRC/$t.py" >"$LOCAL_EVID/regression/$t.out" 2>&1
    echo "$t rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
  else
    echo "$t missing" >> "$LOCAL_EVID/regression/summary.txt"
  fi
done
"$PY" -m unittest test_interaction_authority_contracts >"$LOCAL_EVID/regression/interaction-authority-contracts.out" 2>&1
echo "interaction_authority_contracts rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
set -e
staging_py smoke-test-internal-auth.py "$LOCAL_EVID/regression/internal-auth-staging.out" || true
staging_py smoke-test-r2-security-db.py "$LOCAL_EVID/regression/r2-security-db.out" || true
staging_py smoke-test-r3-data-safety-db.py "$LOCAL_EVID/regression/r3-data-safety-db.out" || true
staging_py smoke-test-r4-truth-in-ui-db.py "$LOCAL_EVID/regression/r4-truth-in-ui-db.out" || true
for f in "$LOCAL_EVID"/regression/smoke-test-*.out; do
  [[ -f "$f" ]] || continue
  grep -qE '^[[:space:]]*FAIL  |Traceback' "$f" && REG_OK=NO
  grep -qE '[0-9]+ passed' "$f" || REG_OK=NO
done
grep -q 'OK' "$LOCAL_EVID/regression/interaction-authority-contracts.out" || REG_OK=NO
grep -q 'ALL CHECKS PASSED' "$LOCAL_EVID/regression/internal-auth-staging.out" || REG_OK=NO
grep -q 'R2_SECURITY_FULL_PASS' "$LOCAL_EVID/regression/r2-security-db.out" || REG_OK=NO
grep -q 'R3_DATA_SAFETY_FULL_PASS' "$LOCAL_EVID/regression/r3-data-safety-db.out" || REG_OK=NO
grep -q 'R4_TRUTH_IN_UI_DB_PASS' "$LOCAL_EVID/regression/r4-truth-in-ui-db.out" || REG_OK=NO

log "7/8 inventories + matrices"
cd "$REPO_ROOT"
python3 - <<PY
from pathlib import Path
evid = Path("$LOCAL_EVID")
inv = evid / "inventories"
inv.mkdir(parents=True, exist_ok=True)
http = Path("wathefni-orchestrator/performance_http.py").read_text(encoding="utf-8")
th = Path("wathefni-orchestrator/talent_http.py").read_text(encoding="utf-8")
routes = [line.strip() for line in (http + "\n" + th).splitlines() if "@app.get" in line or "@app.post" in line or "_bind(" in line]
(inv / "api-inventory.md").write_text(
    "# PT1 API inventory\\n\\n" + "\\n".join(f"- {r}" for r in routes) + "\\n",
    encoding="utf-8",
)
print("INVENTORIES_OK", len(routes))
PY
cp -a "$REPO_ROOT/ops/pt1-okr-evidence-matrices.md" "$LOCAL_EVID/docs/matrices.md"
cp -a "$REPO_ROOT/ops/PT1_OKR_EVIDENCE_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/freeze-amendment.md"

log "8/8 verdict"
DASH_OK=NO
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out"; then DASH_OK=YES; fi
if grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/named.out"; then DASH_OK=NO; fi

MOBILE_OK=NO
if grep -qE 'PASS employee app composition|passed' "$LOCAL_EVID/mobile/composition.out" \
   && ! grep -qE '^FAIL  |^[[:space:]]*FAIL  ' "$LOCAL_EVID/mobile/composition.out"; then
  MOBILE_OK=YES
fi

UNIT_OK=NO
grep -q 'PT1_OKR_EVIDENCE_UNIT_PASS' "$LOCAL_EVID/tests/pt1-unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/pt1-unit.out" && UNIT_OK=YES

DB_OK=NO
grep -q 'PT1_OKR_EVIDENCE_DB_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES

DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES

VERDICT=FAIL
if [[ "$DASH_OK" == YES && "$MOBILE_OK" == YES && "$UNIT_OK" == YES && "$DB_OK" == YES && "$LIVE_OK" == YES && "$REG_OK" == YES && "$DEPLOY_OK" == YES ]]; then
  VERDICT='PT1_OKR_EVIDENCE_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# PT1 — OKR Operating Depth + Talent Evidence Index

- Stamp: $STAMP
- Dashboard vitest: $DASH_OK
- Employee composition: $MOBILE_OK
- Local unit contracts: $UNIT_OK
- Staging deploy: $DEPLOY_OK
- Staging DB journeys A–H: $DB_OK
- Live deployed staging service: $LIVE_OK
- Waves 1–6 + R2–R6 + R5 surface regressions: $REG_OK
- Verdict: **$VERDICT**

Scope: PT1 overlay only. C1 remains OKR SoT. OKR cycle ≠ review cycle.
Do not begin PT2. Do not resume R7.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
