#!/usr/bin/env bash
# Production Readiness R7 — Mobile keyboard and native safety qualification.
# Physical-device matrix (PH-5…PH-11) remains RP. This script proves source
# contracts + frozen unit regressions. Does not begin R8.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
HR_SRC="$REPO_ROOT/apps/wathefni-hr-mobile"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r7-mobile-native-safety-$STAMP"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,hr-mobile,mobile}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

log "1/6 HR Mobile vitest + i18n"
cd "$HR_SRC"
if [[ -x "$HR_SRC/node_modules/.bin/vitest" ]]; then
  npx vitest run 2>&1 | tee "$LOCAL_EVID/hr-mobile/vitest.out"
else
  echo "vitest missing" | tee "$LOCAL_EVID/hr-mobile/vitest.out"
  exit 1
fi

log "2/6 employee composition, keyboard foundation, push, i18n"
cd "$MOBILE_SRC"
node scripts/composition-shapes-test.js 2>&1 | tee "$LOCAL_EVID/mobile/composition.out"
"$PY" scripts/verify-capability-foundation.py 2>&1 | tee "$LOCAL_EVID/mobile/capability-foundation.out"
node scripts/push-follow-through-test.js 2>&1 | tee "$LOCAL_EVID/mobile/push.out"
"$PY" scripts/a11y-i18n-static-scan.py 2>&1 | tee "$LOCAL_EVID/mobile/i18n.out"

log "3/6 R7 source contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-r7-mobile-native-safety.py 2>&1 | tee "$LOCAL_EVID/tests/r7-unit.out"
cp -a smoke-test-r7-mobile-native-safety.py "$LOCAL_EVID/sources/"

log "4/6 frozen unit regressions (R6 + R2–R5A + Wave 4)"
cd "$ORCH_SRC"
"$PY" smoke-test-r6-setup-self-service.py 2>&1 | tee "$LOCAL_EVID/regression/r6-unit.out"
"$PY" smoke-test-r2-security.py 2>&1 | tee "$LOCAL_EVID/regression/r2-unit.out"
"$PY" smoke-test-r3-data-safety.py 2>&1 | tee "$LOCAL_EVID/regression/r3-unit.out"
"$PY" smoke-test-r4-truth-in-ui.py 2>&1 | tee "$LOCAL_EVID/regression/r4-unit.out"
"$PY" smoke-test-r5a-capability-honesty.py 2>&1 | tee "$LOCAL_EVID/regression/r5a-unit.out"
"$PY" smoke-test-r5c-talent-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5c-unit.out"
"$PY" smoke-test-wave4-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave4-unit.out"

log "5/6 live staging health (no orchestrator overlay — R7 is client-side)"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health || true)
echo "staging_health=$S"
[ "$S" = "200" ] || exit 1
echo LIVE_HEALTH_OK
REMOTE

log "6/6 verdict"
HR_OK=NO
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/hr-mobile/vitest.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/hr-mobile/vitest.out"; then HR_OK=YES; fi

MOBILE_OK=NO
grep -qE 'PASS employee app composition' "$LOCAL_EVID/mobile/composition.out" \
  && grep -q 'employee mobile capability foundation: GREEN' "$LOCAL_EVID/mobile/capability-foundation.out" \
  && ! grep -qE '^FAIL ' "$LOCAL_EVID/mobile/push.out" \
  && grep -q 'EN/AR key parity' "$LOCAL_EVID/mobile/i18n.out" \
  && MOBILE_OK=YES

R7_OK=NO
grep -q 'R7_MOBILE_NATIVE_SAFETY_UNIT_PASS' "$LOCAL_EVID/tests/r7-unit.out" && R7_OK=YES

REG_OK=NO
grep -q 'R6_SETUP_SELF_SERVICE_UNIT_PASS' "$LOCAL_EVID/regression/r6-unit.out" \
  && grep -q 'R2_SECURITY_UNIT_PASS' "$LOCAL_EVID/regression/r2-unit.out" \
  && grep -q 'R3_DATA_SAFETY_UNIT_PASS' "$LOCAL_EVID/regression/r3-unit.out" \
  && grep -q 'R4_TRUTH_IN_UI_UNIT_PASS' "$LOCAL_EVID/regression/r4-unit.out" \
  && grep -q 'R5A_CAPABILITY_HONESTY_UNIT_PASS' "$LOCAL_EVID/regression/r5a-unit.out" \
  && grep -q 'R5C_TALENT_SURFACE_UNIT_PASS' "$LOCAL_EVID/regression/r5c-unit.out" \
  && grep -q 'WAVE4_PRODUCT_UNIT_PASS' "$LOCAL_EVID/regression/wave4-unit.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/regression/"*.out \
  && REG_OK=YES

LIVE_OK=NO
grep -q 'LIVE_HEALTH_OK' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES

VERDICT=FAIL
if [[ "$HR_OK" == YES && "$MOBILE_OK" == YES && "$R7_OK" == YES && "$REG_OK" == YES && "$LIVE_OK" == YES ]]; then
  VERDICT='PRODUCTION_READINESS_R7_MOBILE_NATIVE_SAFETY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Production Readiness R7 — Mobile keyboard and native safety

- Stamp: $STAMP
- HR Mobile vitest: $HR_OK
- Employee composition / foundation / push / i18n: $MOBILE_OK
- R7 source contracts: $R7_OK
- Frozen unit regressions: $REG_OK
- Live staging health: $LIVE_OK
- Verdict: **$VERDICT**

Physical-device matrix (Face ID, push delivery, native RTL paint) remains RP.
FULL_PASS is not authorisation for production rollout.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
