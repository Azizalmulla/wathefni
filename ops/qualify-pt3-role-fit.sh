#!/usr/bin/env bash
# PT3 — Role Fit + Readiness Intelligence qualification.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/pt3-role-fit-$STAMP"
REMOTE_STAGE="/tmp/pt3-role-fit-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,dashboard,mobile,inventories}
log() { printf '\n=== %s ===\n' "$*"; }
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  talent_surfaces.py talent_http.py talent_profile_c5.py talent_succession_c6.py
  talent_evidence_index_pt1.py talent_models_pt2.py talent_role_fit_pt3.py
  job_architecture_c1.py
  smoke-test-pt3-role-fit.py smoke-test-pt3-role-fit-db.py
  smoke-test-pt2-talent-models.py smoke-test-r5c-talent-surface.py
  smoke-test-job-architecture-c1.py smoke-test-wave4-product-acceptance.py
)

log "1/6 dashboard + mobile"
cd "$DASH_SRC"
npx vitest run src/lib/workspaceCapability.test.ts src/lib/dashboardNavigation.test.ts src/pages/shared/dataState.test.tsx 2>&1 | tee "$LOCAL_EVID/dashboard/named.out"
npx vitest run 2>&1 | tee "$LOCAL_EVID/dashboard/full.out"
cd "$MOBILE_SRC"
node scripts/composition-shapes-test.js 2>&1 | tee "$LOCAL_EVID/mobile/composition.out"

log "2/6 local contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-pt3-role-fit.py 2>&1 | tee "$LOCAL_EVID/tests/pt3-unit.out"
"$PY" smoke-test-pt2-talent-models.py 2>&1 | tee "$LOCAL_EVID/regression/pt2-unit.out"
"$PY" smoke-test-r5c-talent-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5c.out"
"$PY" smoke-test-job-architecture-c1.py 2>&1 | tee "$LOCAL_EVID/regression/ja-c1.out"
"$PY" smoke-test-wave4-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave4.out"

log "3/6 stage"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
cp -a "$DASH_SRC/src/posthire/TalentWorkspace.tsx" "$LOCAL_EVID/dashboard/TalentWorkspace.tsx"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
python3 -m py_compile '$STG/talent_role_fit_pt3.py' '$STG/talent_http.py'
echo STAGING_COPY_OK
REMOTE

staging_py() {
  local script="$1" out="$2"
  "${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$out"
set -euo pipefail
STG=$STG; PROD=/opt/wathefni/orchestrator; PYBIN=\$PROD/.venv/bin/python
export PYTHONPATH="\$STG:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
cd "\$STG"
export WATHEFNI_ENV=staging WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DELIVERY_MODE=dry_run
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" "$script"
echo STAGING_RC=\$?
REMOTE
}

log "4/6 staging DB"
staging_py smoke-test-pt3-role-fit-db.py "$LOCAL_EVID/tests/staging-db.out"

log "5/6 live"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
systemctl restart wathefni-orchestrator-staging
S=000
for i in $(seq 1 15); do sleep 8; S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health); [ "$S" = "200" ] && break; done
echo "staging_health=$S"
[ "$S" = "200" ] || { echo "LIVE_SERVICE 0 passed, 1 failed"; exit 0; }
python3 - <<'PY'
import urllib.request, urllib.error
P=F=0
def ck(l,c,d=None):
    global P,F
    print(f"      {'PASS' if c else 'FAIL'}  {l}" + (f" :: {d}" if d is not None and not c else ""))
    P += int(bool(c)); F += int(not c)
def fetch(p):
    try:
        with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8011"+p), timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
ck("live health", fetch("/health")==200)
for p in ("/dashboard/posthire/talent/role-fit/sets","/dashboard/posthire/talent/role-fit/evaluations","/dashboard/posthire/talent/models"):
    ck(f"live {p} not public", fetch(p) in (401,403,503), fetch(p))
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "6/6 verdict"
DASH_OK=NO
grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out" && DASH_OK=YES
MOBILE_OK=NO
grep -qE 'PASS employee app composition|passed' "$LOCAL_EVID/mobile/composition.out" && MOBILE_OK=YES
UNIT_OK=NO
grep -q 'PT3_ROLE_FIT_READINESS_UNIT_PASS' "$LOCAL_EVID/tests/pt3-unit.out" && UNIT_OK=YES
PRED_OK=NO
grep -q 'PT2_TALENT_MODELS_WHY_UNIT_PASS' "$LOCAL_EVID/regression/pt2-unit.out" && grep -q 'R5C_TALENT_SURFACE_UNIT_PASS' "$LOCAL_EVID/regression/r5c.out" && PRED_OK=YES
JA_OK=YES
grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/regression/ja-c1.out" && JA_OK=NO
grep -qE '[0-9]+ passed' "$LOCAL_EVID/regression/ja-c1.out" || JA_OK=NO
WAVE_OK=NO
grep -q 'WAVE4_PRODUCT_UNIT_PASS' "$LOCAL_EVID/regression/wave4.out" && WAVE_OK=YES
DB_OK=NO
grep -q 'PT3_ROLE_FIT_READINESS_DB_PASS' "$LOCAL_EVID/tests/staging-db.out" && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES
LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES
DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES
VERDICT=FAIL
if [[ "$DASH_OK$MOBILE_OK$UNIT_OK$PRED_OK$JA_OK$WAVE_OK$DB_OK$LIVE_OK$DEPLOY_OK" == YESYESYESYESYESYESYESYESYES ]]; then
  VERDICT='PT3_ROLE_FIT_READINESS_FULL_PASS'
fi
cat > "$LOCAL_EVID/REPORT.md" <<EOF
# PT3 — Role Fit + Readiness

- Stamp: $STAMP
- Dashboard: $DASH_OK
- Mobile: $MOBILE_OK
- PT3 unit: $UNIT_OK
- PT2/R5C: $PRED_OK
- JA C1: $JA_OK
- Wave 4: $WAVE_OK
- Staging DB: $DB_OK
- Live: $LIVE_OK
- Deploy: $DEPLOY_OK
- Verdict: **$VERDICT**
EOF
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
