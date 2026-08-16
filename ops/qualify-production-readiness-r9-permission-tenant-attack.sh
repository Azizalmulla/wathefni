#!/usr/bin/env bash
# Production Readiness R9 — live permission + tenant-isolation attack.
# Continues into the store-release program after a green freeze.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r9-permission-tenant-attack-$STAMP"
REMOTE_STAGE="/tmp/r9-permission-tenant-attack-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  smoke-test-r9-permission-tenant-attack.py
  smoke-test-r9-permission-tenant-attack-db.py
  production_data_safety.py
  setup_console_operator_auth.py
)

log "1/6 local R9 unit contracts + frozen security unit"
cd "$ORCH_SRC"
"$PY" smoke-test-r9-permission-tenant-attack.py 2>&1 | tee "$LOCAL_EVID/tests/r9-unit.out"
"$PY" smoke-test-r2-security.py 2>&1 | tee "$LOCAL_EVID/regression/r2-unit.out"

log "2/6 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/smoke-test-r9-permission-tenant-attack-db.py'
python3 -m py_compile '$STG/app.py' '$STG/smoke-test-r9-permission-tenant-attack.py' '$STG/smoke-test-r9-permission-tenant-attack-db.py'
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

log "3/6 staging live session attack (two tenants, representative roles)"
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-db.out"
$(staging_env)
"\$PYBIN" smoke-test-r9-permission-tenant-attack-db.py
echo STAGING_RC=\$?
REMOTE

log "4/6 restart staging so P1-19 predicates are in the running process"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/restart.out"
set -euo pipefail
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
S=000
for i in $(seq 1 15); do
  sleep 6
  S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health || true)
  [ "$S" = "200" ] && break
done
echo "staging_health=$S"
[ "$S" = "200" ] || { echo LIVE_HEALTH_FAIL; exit 1; }
R=$(curl -s -o /tmp/r9-ready.json -w "%{http_code}" http://127.0.0.1:8011/ready || true)
echo "staging_ready=$R"
[ "$R" = "200" ] || { echo LIVE_READY_FAIL; exit 1; }
python3 - <<'PY'
import json
body = json.load(open("/tmp/r9-ready.json"))
print("ready_status", body.get("status"))
if body.get("status") != "ready":
    raise SystemExit("ready_not_ready")
PY
echo LIVE_OK
REMOTE

log "5/6 live unauthenticated probes"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/unauth.out"
set -euo pipefail
fail=0
probe() {
  local path="$1"
  local code body
  code=$(curl -s -o /tmp/r9-unauth.body -w "%{http_code}" "http://127.0.0.1:8011$path" || true)
  body=$(python3 -c 'import pathlib; print(pathlib.Path("/tmp/r9-unauth.body").read_text(errors="replace")[:240])' 2>/dev/null || true)
  echo "$path -> $code"
  case "$code" in
    401|403|404) ;;
    503)
      # Employee app globally off is fail-closed, not a public leak.
      if echo "$body" | grep -Eq 'employee_app_disabled|employee_app_temporarily_unavailable|not available'; then
        echo "fail_closed $path 503"
      else
        echo "UNEXPECTED_OPEN $path $code $body"
        fail=1
      fi
      ;;
    *) echo "UNEXPECTED_OPEN $path $code $body"; fail=1 ;;
  esac
}
probe /dashboard/posthire/employees
probe /dashboard/posthire/leave
probe /dashboard/posthire/payroll
probe /dashboard/performance/workspace
probe /dashboard/talent/workspace
probe /dashboard/employee-relations/workspace
probe /dashboard/setup/company/module-policies
probe /app/me
probe /app/leave
if [[ "$fail" != "0" ]]; then echo LIVE_UNAUTH_FAIL; exit 1; fi
echo LIVE_UNAUTH_OK
REMOTE

log "6/6 collect stamp files"
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R9_PERMISSION_TENANT_ATTACK_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R9_PERMISSION_TENANT_ATTACK_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
echo "EVIDENCE=$LOCAL_EVID"

if grep -q "R9_PERMISSION_TENANT_ATTACK_UNIT_PASS" "$LOCAL_EVID/tests/r9-unit.out" \
  && grep -q "R9_PERMISSION_TENANT_ATTACK_DB_PASS" "$LOCAL_EVID/tests/staging-db.out" \
  && grep -q "LIVE_OK" "$LOCAL_EVID/live/restart.out" \
  && grep -q "LIVE_UNAUTH_OK" "$LOCAL_EVID/live/unauth.out"; then
  echo R9_QUALIFY_GREEN
  exit 0
fi
echo R9_QUALIFY_RED
exit 1
