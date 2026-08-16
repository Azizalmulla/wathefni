#!/usr/bin/env bash
# Production Readiness R8 — Observability / CI / migration safety qualification.
# Does not begin R9. Stop for owner review after a green freeze.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
HR_SRC="$REPO_ROOT/apps/wathefni-hr-mobile"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r8-delivery-safety-$STAMP"
REMOTE_STAGE="/tmp/r8-delivery-safety-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,hr-mobile,mobile,migrations}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  observability.py
  observability_http.py
  migration_framework.py
  security_rate_limit.py
  smoke-test-r8-delivery-safety.py
  smoke-test-r8-delivery-safety-db.py
)

log "1/8 deploy gate + R7 client suites"
bash "$SCRIPT_DIR/gate-wathefni-deploy.sh" 2>&1 | tee "$LOCAL_EVID/tests/deploy-gate.out"
cd "$HR_SRC"
npx vitest run 2>&1 | tee "$LOCAL_EVID/hr-mobile/vitest.out"
cd "$MOBILE_SRC"
node scripts/composition-shapes-test.js 2>&1 | tee "$LOCAL_EVID/mobile/composition.out"
"$PY" scripts/verify-capability-foundation.py 2>&1 | tee "$LOCAL_EVID/mobile/capability-foundation.out"
node scripts/push-follow-through-test.js 2>&1 | tee "$LOCAL_EVID/mobile/push.out"
"$PY" scripts/a11y-i18n-static-scan.py 2>&1 | tee "$LOCAL_EVID/mobile/i18n.out"

log "2/8 R8 unit + frozen unit regressions"
cd "$ORCH_SRC"
"$PY" smoke-test-r8-delivery-safety.py 2>&1 | tee "$LOCAL_EVID/tests/r8-unit.out"
"$PY" smoke-test-r7-mobile-native-safety.py 2>&1 | tee "$LOCAL_EVID/regression/r7-unit.out"
"$PY" smoke-test-r6-setup-self-service.py 2>&1 | tee "$LOCAL_EVID/regression/r6-unit.out"
"$PY" smoke-test-r2-security.py 2>&1 | tee "$LOCAL_EVID/regression/r2-unit.out"
"$PY" smoke-test-r3-data-safety.py 2>&1 | tee "$LOCAL_EVID/regression/r3-unit.out"
"$PY" smoke-test-r4-truth-in-ui.py 2>&1 | tee "$LOCAL_EVID/regression/r4-unit.out"
"$PY" smoke-test-r5a-capability-honesty.py 2>&1 | tee "$LOCAL_EVID/regression/r5a-unit.out"
"$PY" smoke-test-r5c-talent-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5c-unit.out"
"$PY" smoke-test-wave4-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave4-unit.out"

log "3/8 stage orchestrator sources + migrations"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$ORCH_SRC/migrations/." "$LOCAL_EVID/migrations/"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE/migrations'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "$ORCH_SRC/migrations/" "$VPS_HOST:$REMOTE_STAGE/migrations/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
mkdir -p '$STG/migrations'
cp -a '$REMOTE_STAGE'/migrations/*.sql '$STG/migrations/'
test -f '$STG/observability.py'
test -f '$STG/observability_http.py'
test -f '$STG/migration_framework.py'
test -f '$STG/migrations/0001_r8_delivery_safety.sql'
python3 -m py_compile '$STG/app.py' '$STG/observability.py' '$STG/observability_http.py' '$STG/migration_framework.py' '$STG/security_rate_limit.py'
echo STAGING_COPY_OK
REMOTE

staging_env() {
  cat <<'ENV'
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
PYBIN=$PROD/.venv/bin/python
export PYTHONPATH="$STG:$PROD${PYTHONPATH:+:$PYTHONPATH}"
cd "$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DELIVERY_MODE=dry_run
set -a; source "$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
ENV
}

log "4/8 apply forward migrations (deploy-only flag)"
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-migrate.out"
$(staging_env)
export WATHEFNI_SCHEMA_APPLY=1
"\$PYBIN" - <<'PY'
import migration_framework as mf
import app
done = mf.apply_with_connection(app)
print("MIGRATIONS_APPLIED", done)
PY
unset WATHEFNI_SCHEMA_APPLY || true
echo MIGRATE_OK
REMOTE

log "5/8 staging DB contracts (runtime, no apply flag)"
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-db.out"
$(staging_env)
unset WATHEFNI_SCHEMA_APPLY || true
"\$PYBIN" smoke-test-r8-delivery-safety-db.py
echo STAGING_RC=\$?
REMOTE

log "6/8 live staging health / ready / ingest"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
S=000
for i in $(seq 1 15); do
  sleep 8
  S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health || true)
  [ "$S" = "200" ] && break
done
echo "staging_health=$S"
[ "$S" = "200" ] || { echo LIVE_HEALTH_FAIL; exit 1; }

R=000
R=$(curl -s -o /tmp/r8-ready.json -w "%{http_code}" http://127.0.0.1:8011/ready || true)
echo "staging_ready=$R"
python3 - <<'PY'
import json
body = json.load(open("/tmp/r8-ready.json"))
print("ready_status", body.get("status"))
print("ready_migrations_ok", (body.get("delivery") or {}).get("migrations", {}).get("ok"))
print("ready_has_failed_jobs", "failed_jobs" in (body.get("delivery") or {}))
if body.get("status") != "ready":
    raise SystemExit("ready_not_ready")
PY
[ "$R" = "200" ] || { echo LIVE_READY_FAIL; exit 1; }

I=$(curl -s -o /tmp/r8-ingest.json -w "%{http_code}" \
  -H 'Content-Type: application/json' \
  -d '{"surface":"hr_web","message":"r8-live-qualify password=hunter2 +96550001111 ceo@acme.test"}' \
  http://127.0.0.1:8011/dashboard/telemetry/error || true)
echo "staging_ingest=$I"
python3 - <<'PY'
import json
body = json.load(open("/tmp/r8-ingest.json"))
print("ingest_ok", body.get("ok"), "event_id", body.get("event_id"))
if not body.get("ok"):
    raise SystemExit("ingest_failed")
PY
[ "$I" = "200" ] || { echo LIVE_INGEST_FAIL; exit 1; }
echo LIVE_HEALTH_OK
REMOTE

log "7/8 copy docs"
cp -a "$ORCH_SRC/ops/RESTORE_RUNBOOK.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/.github/workflows/delivery-safety.yml" "$LOCAL_EVID/docs/"
cp -a "$SCRIPT_DIR/gate-wathefni-deploy.sh" "$LOCAL_EVID/docs/"

log "8/8 verdict"
GATE_OK=NO
grep -q 'WATHEFNI_DEPLOY_GATE_OK' "$LOCAL_EVID/tests/deploy-gate.out" && GATE_OK=YES

HR_OK=NO
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/hr-mobile/vitest.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/hr-mobile/vitest.out"; then HR_OK=YES; fi

MOBILE_OK=NO
grep -qE 'PASS employee app composition' "$LOCAL_EVID/mobile/composition.out" \
  && grep -q 'employee mobile capability foundation: GREEN' "$LOCAL_EVID/mobile/capability-foundation.out" \
  && ! grep -qE '^FAIL ' "$LOCAL_EVID/mobile/push.out" \
  && grep -q 'EN/AR key parity' "$LOCAL_EVID/mobile/i18n.out" \
  && MOBILE_OK=YES

R8_OK=NO
grep -q 'R8_DELIVERY_SAFETY_UNIT_PASS' "$LOCAL_EVID/tests/r8-unit.out" && R8_OK=YES

REG_OK=NO
grep -q 'R7_MOBILE_NATIVE_SAFETY_UNIT_PASS' "$LOCAL_EVID/regression/r7-unit.out" \
  && grep -q 'R6_SETUP_SELF_SERVICE_UNIT_PASS' "$LOCAL_EVID/regression/r6-unit.out" \
  && grep -q 'R2_SECURITY_UNIT_PASS' "$LOCAL_EVID/regression/r2-unit.out" \
  && grep -q 'R3_DATA_SAFETY_UNIT_PASS' "$LOCAL_EVID/regression/r3-unit.out" \
  && grep -q 'R4_TRUTH_IN_UI_UNIT_PASS' "$LOCAL_EVID/regression/r4-unit.out" \
  && grep -q 'R5A_CAPABILITY_HONESTY_UNIT_PASS' "$LOCAL_EVID/regression/r5a-unit.out" \
  && grep -q 'R5C_TALENT_SURFACE_UNIT_PASS' "$LOCAL_EVID/regression/r5c-unit.out" \
  && grep -q 'WAVE4_PRODUCT_UNIT_PASS' "$LOCAL_EVID/regression/wave4-unit.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/regression/"*.out \
  && REG_OK=YES

MIG_OK=NO
grep -q 'MIGRATE_OK' "$LOCAL_EVID/tests/staging-migrate.out" \
  && grep -q 'MIGRATIONS_APPLIED' "$LOCAL_EVID/tests/staging-migrate.out" \
  && MIG_OK=YES

DB_OK=NO
grep -q 'R8_DELIVERY_SAFETY_DB_PASS' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

LIVE_OK=NO
grep -q 'LIVE_HEALTH_OK' "$LOCAL_EVID/live/live-service.out" \
  && grep -q 'staging_ready=200' "$LOCAL_EVID/live/live-service.out" \
  && grep -q 'staging_ingest=200' "$LOCAL_EVID/live/live-service.out" \
  && LIVE_OK=YES

VERDICT=FAIL
if [[ "$GATE_OK" == YES && "$HR_OK" == YES && "$MOBILE_OK" == YES && "$R8_OK" == YES && "$REG_OK" == YES && "$MIG_OK" == YES && "$DB_OK" == YES && "$LIVE_OK" == YES ]]; then
  VERDICT='PRODUCTION_READINESS_R8_DELIVERY_SAFETY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Production Readiness R8 — Observability / CI / migration safety

- Stamp: $STAMP
- Deploy gate: $GATE_OK
- HR Mobile vitest: $HR_OK
- Employee composition / foundation / push / i18n: $MOBILE_OK
- R8 source contracts: $R8_OK
- Frozen unit regressions (R7 + R6 + R2–R5A/C + Wave 4): $REG_OK
- Staging forward migrations: $MIG_OK
- Staging DB contracts: $DB_OK
- Live staging health / ready / ingest: $LIVE_OK
- Verdict: **$VERDICT**

FULL_PASS is not authorisation for production rollout.
Do not begin R9 automatically.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
