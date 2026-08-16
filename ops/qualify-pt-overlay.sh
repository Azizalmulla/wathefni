#!/usr/bin/env bash
# Shared PT overlay qualifier. Usage: qualify-pt-overlay.sh pt4|pt5|pt6|pt7
set -euo pipefail
SLICE="${1:?slice required}"
VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

case "$SLICE" in
  pt4)
    EVID_NAME="pt4-talent-map"; VERDICT_NAME="PT4_DYNAMIC_TALENT_MAP_FULL_PASS"
    UNIT=smoke-test-pt4-talent-map.py; DB=smoke-test-pt4-talent-map-db.py
    UNIT_MARK=PT4_DYNAMIC_TALENT_MAP_UNIT_PASS; DB_MARK=PT4_DYNAMIC_TALENT_MAP_DB_PASS
    PRED=smoke-test-pt3-role-fit.py; PRED_MARK=PT3_ROLE_FIT_READINESS_UNIT_PASS
    LIVE_PATHS=("/dashboard/posthire/talent/map" "/dashboard/posthire/talent/models")
    EXTRA=(talent_map_pt4.py)
    FULL_VITEST=1
    ;;
  pt5)
    EVID_NAME="pt5-succession-mobility"; VERDICT_NAME="PT5_SUCCESSION_MOBILITY_INTELLIGENCE_FULL_PASS"
    UNIT=smoke-test-pt5-succession-mobility.py; DB=smoke-test-pt5-succession-mobility-db.py
    UNIT_MARK=PT5_SUCCESSION_MOBILITY_INTELLIGENCE_UNIT_PASS; DB_MARK=PT5_SUCCESSION_MOBILITY_INTELLIGENCE_DB_PASS
    PRED=smoke-test-pt4-talent-map.py; PRED_MARK=PT4_DYNAMIC_TALENT_MAP_UNIT_PASS
    LIVE_PATHS=("/dashboard/posthire/talent/succession-intelligence" "/dashboard/posthire/talent/map")
    EXTRA=(talent_succession_intel_pt5.py talent_map_pt4.py)
    FULL_VITEST=1
    ;;
  pt6)
    EVID_NAME="pt6-trajectory-capability"; VERDICT_NAME="PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_FULL_PASS"
    UNIT=smoke-test-pt6-trajectory.py; DB=smoke-test-pt6-trajectory-db.py
    UNIT_MARK=PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_UNIT_PASS; DB_MARK=PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_DB_PASS
    PRED=smoke-test-pt5-succession-mobility.py; PRED_MARK=PT5_SUCCESSION_MOBILITY_INTELLIGENCE_UNIT_PASS
    LIVE_PATHS=("/dashboard/posthire/talent/capability/holder-dependency/x" "/dashboard/posthire/talent/map")
    EXTRA=(talent_trajectory_pt6.py talent_succession_intel_pt5.py talent_map_pt4.py hr_intelligence_registry_c1.py)
    FULL_VITEST=1
    ;;
  pt7)
    EVID_NAME="pt7-assistant-talent"; VERDICT_NAME="PT7_ASSISTANT_TALENT_INTELLIGENCE_FULL_PASS"
    UNIT=smoke-test-pt7-assistant.py; DB=smoke-test-pt7-assistant-db.py
    UNIT_MARK=PT7_ASSISTANT_TALENT_INTELLIGENCE_UNIT_PASS; DB_MARK=PT7_ASSISTANT_TALENT_INTELLIGENCE_DB_PASS
    PRED=smoke-test-pt6-trajectory.py; PRED_MARK=PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_UNIT_PASS
    LIVE_PATHS=("/dashboard/posthire/talent/models" "/dashboard/posthire/talent/map")
    EXTRA=(talent_assistant_pt7.py smoke-test-pt-flagship-evals-db.py)
    FULL_VITEST=1
    ;;
  *) echo "unknown slice $SLICE"; exit 1 ;;
esac

LOCAL_EVID="$REPO_ROOT/ops/evidence/${EVID_NAME}-$STAMP"
REMOTE_STAGE="/tmp/${EVID_NAME}-stage"
STG=/opt/wathefni/staging/orchestrator
mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,dashboard,mobile}
log() { printf '\n=== %s ===\n' "$*"; }

FILES=(
  talent_surfaces.py talent_http.py talent_profile_c5.py talent_succession_c6.py
  talent_evidence_index_pt1.py talent_models_pt2.py talent_role_fit_pt3.py
  talent_map_pt4.py talent_succession_intel_pt5.py talent_trajectory_pt6.py
  "$UNIT" "$DB" "$PRED" smoke-test-r5c-talent-surface.py smoke-test-wave4-product-acceptance.py
  "${EXTRA[@]}"
)

log "1 dashboard/mobile ($SLICE)"
cd "$DASH_SRC"
npx vitest run src/lib/workspaceCapability.test.ts src/pages/shared/dataState.test.tsx 2>&1 | tee "$LOCAL_EVID/dashboard/named.out"
if [[ "$FULL_VITEST" == 1 ]]; then
  npx vitest run 2>&1 | tee "$LOCAL_EVID/dashboard/full.out"
else
  cp "$LOCAL_EVID/dashboard/named.out" "$LOCAL_EVID/dashboard/full.out"
fi
cd "$MOBILE_SRC"
node scripts/composition-shapes-test.js 2>&1 | tee "$LOCAL_EVID/mobile/composition.out"

log "2 local contracts"
cd "$ORCH_SRC"
"$PY" "$UNIT" 2>&1 | tee "$LOCAL_EVID/tests/unit.out"
"$PY" "$PRED" 2>&1 | tee "$LOCAL_EVID/regression/pred.out"
"$PY" smoke-test-r5c-talent-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5c.out"
"$PY" smoke-test-wave4-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave4.out"
if [[ "$SLICE" == pt6 || "$SLICE" == pt7 ]]; then
  "$PY" smoke-test-wave5-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave5.out"
fi
if [[ "$SLICE" == pt7 ]]; then
  "$PY" smoke-test-pt1-okr-evidence.py 2>&1 | tee "$LOCAL_EVID/regression/pt1.out"
  "$PY" smoke-test-pt2-talent-models.py 2>&1 | tee "$LOCAL_EVID/regression/pt2.out"
  "$PY" smoke-test-pt3-role-fit.py 2>&1 | tee "$LOCAL_EVID/regression/pt3.out"
  "$PY" smoke-test-pt4-talent-map.py 2>&1 | tee "$LOCAL_EVID/regression/pt4.out"
  "$PY" smoke-test-pt5-succession-mobility.py 2>&1 | tee "$LOCAL_EVID/regression/pt5.out"
  "$PY" smoke-test-job-architecture-c1.py 2>&1 | tee "$LOCAL_EVID/regression/ja.out"
  "$PY" smoke-test-wave1-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave1.out"
  "$PY" smoke-test-wave2-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave2.out"
  "$PY" smoke-test-wave3-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave3.out"
  "$PY" smoke-test-wave6-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave6.out"
  "$PY" smoke-test-r2-security.py 2>&1 | tee "$LOCAL_EVID/regression/r2.out"
  "$PY" smoke-test-r3-data-safety.py 2>&1 | tee "$LOCAL_EVID/regression/r3.out"
  "$PY" smoke-test-r4-truth-in-ui.py 2>&1 | tee "$LOCAL_EVID/regression/r4.out"
  "$PY" smoke-test-r5a-capability-honesty.py 2>&1 | tee "$LOCAL_EVID/regression/r5a.out"
  "$PY" smoke-test-r5b-performance-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5b.out"
  "$PY" smoke-test-r5d-job-architecture-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5d.out"
  "$PY" smoke-test-r5e-learning-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5e.out"
  "$PY" smoke-test-r6-setup-self-service.py 2>&1 | tee "$LOCAL_EVID/regression/r6.out"
  "$PY" smoke-test-requisitions-wave1.py 2>&1 | tee "$LOCAL_EVID/regression/recruiting.out"
  cp -a "$ORCH_SRC/action_registry.py" "$ORCH_SRC/tool_call_orchestrator.py" "$ORCH_SRC/assistant_capability_catalog.py" "$LOCAL_EVID/sources/" 2>/dev/null || true
fi

log "3 stage"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
cp -a "$DASH_SRC/src/posthire/TalentWorkspace.tsx" "$LOCAL_EVID/dashboard/TalentWorkspace.tsx"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
python3 -m py_compile '$STG/${EXTRA[0]}' '$STG/talent_http.py'
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

log "4 staging DB"
staging_py "$DB" "$LOCAL_EVID/tests/staging-db.out"
if [[ "$SLICE" == pt7 ]]; then
  staging_py smoke-test-pt-flagship-evals-db.py "$LOCAL_EVID/tests/flagship-evals.out"
fi

log "5 live"
LIVE_JOIN=$(printf '%s\n' "${LIVE_PATHS[@]}")
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
systemctl restart wathefni-orchestrator-staging
S=000
for i in \$(seq 1 12); do sleep 6; S=\$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health); [ "\$S" = "200" ] && break; done
echo "staging_health=\$S"
[ "\$S" = "200" ] || { echo "LIVE_SERVICE 0 passed, 1 failed"; exit 0; }
python3 - <<'PY'
import urllib.request, urllib.error
P=F=0
paths = """$LIVE_JOIN""".strip().splitlines()
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
for p in paths:
    ck(f"live {p} not public", fetch(p) in (401,403,405,503), fetch(p))
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "6 verdict"
DASH_OK=NO
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed|[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out"; then DASH_OK=YES; fi
MOBILE_OK=NO
grep -qE 'PASS employee app composition|passed' "$LOCAL_EVID/mobile/composition.out" && MOBILE_OK=YES
UNIT_OK=NO
grep -q "$UNIT_MARK" "$LOCAL_EVID/tests/unit.out" && UNIT_OK=YES
PRED_OK=NO
grep -q "$PRED_MARK" "$LOCAL_EVID/regression/pred.out" && PRED_OK=YES
WAVE_OK=NO
if grep -q 'R5C_TALENT_SURFACE_UNIT_PASS' "$LOCAL_EVID/regression/r5c.out" \
  && grep -q 'WAVE4_PRODUCT_UNIT_PASS' "$LOCAL_EVID/regression/wave4.out"; then
  WAVE_OK=YES
fi
if [[ "$SLICE" == pt6 || "$SLICE" == pt7 ]]; then
  grep -q 'WAVE5_PRODUCT_UNIT_PASS' "$LOCAL_EVID/regression/wave5.out" || WAVE_OK=NO
fi
DB_OK=NO
if ! grep -q 'SKIP DB' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -q "$DB_MARK" "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi
LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES
DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES
COMP_OK=YES
FLAGSHIP_OK=YES
if [[ "$SLICE" == pt7 ]]; then
  for m in PT1_OKR_EVIDENCE_UNIT_PASS PT2_TALENT_MODELS_WHY_UNIT_PASS PT3_ROLE_FIT_READINESS_UNIT_PASS PT4_DYNAMIC_TALENT_MAP_UNIT_PASS PT5_SUCCESSION_MOBILITY_INTELLIGENCE_UNIT_PASS WAVE1_PRODUCT_UNIT_PASS WAVE2_PRODUCT_UNIT_PASS WAVE3_PRODUCT_UNIT_PASS WAVE6_PRODUCT_UNIT_PASS R2_SECURITY_UNIT_PASS R3_DATA_SAFETY_UNIT_PASS R4_TRUTH_IN_UI_UNIT_PASS R5A_CAPABILITY_HONESTY_UNIT_PASS R5B_PERFORMANCE_SURFACE_UNIT_PASS R5D_JOB_ARCHITECTURE_SURFACE_UNIT_PASS R5E_LEARNING_SURFACE_UNIT_PASS R6_SETUP_SELF_SERVICE_UNIT_PASS REQUISITIONS_WAVE1_UNIT_PASS; do
    grep -q "$m" "$LOCAL_EVID"/regression/*.out || COMP_OK=NO
  done
  grep -qE '[0-9]+ passed' "$LOCAL_EVID/regression/ja.out" || COMP_OK=NO
  grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/regression/ja.out" && COMP_OK=NO
  FLAGSHIP_OK=NO
  if [[ -f "$LOCAL_EVID/tests/flagship-evals.out" ]] \
    && ! grep -q 'SKIP DB' "$LOCAL_EVID/tests/flagship-evals.out" \
    && grep -q 'PT_FLAGSHIP_EVALS_DB_PASS' "$LOCAL_EVID/tests/flagship-evals.out" \
    && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/flagship-evals.out" \
    && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/flagship-evals.out"; then
    FLAGSHIP_OK=YES
  fi
fi
VERDICT=FAIL
if [[ "$DASH_OK$MOBILE_OK$UNIT_OK$PRED_OK$WAVE_OK$DB_OK$LIVE_OK$DEPLOY_OK$COMP_OK$FLAGSHIP_OK" == YESYESYESYESYESYESYESYESYESYES ]]; then
  VERDICT="$VERDICT_NAME"
fi
cat > "$LOCAL_EVID/REPORT.md" <<EOF
# $SLICE qualification
- Stamp: $STAMP
- Dashboard: $DASH_OK
- Mobile: $MOBILE_OK
- Unit: $UNIT_OK
- Predecessor: $PRED_OK
- Wave contracts: $WAVE_OK
- Staging DB: $DB_OK
- Live: $LIVE_OK
- Deploy: $DEPLOY_OK
- Comprehensive predecessors: $COMP_OK
- Flagship evals 1-9: $FLAGSHIP_OK
- Verdict: **$VERDICT**
EOF
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
