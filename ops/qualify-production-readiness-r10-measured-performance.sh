#!/usr/bin/env bash
# Production Readiness R10 — measured performance on isolated staging.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r10-measured-performance-$STAMP"
REMOTE_STAGE="/tmp/r10-measured-performance-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,live}
log() { printf '\n=== %s ===\n' "$*"; }
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(app.py smoke-test-r10-measured-performance.py smoke-test-r10-measured-performance-db.py production_data_safety.py)

log "1/4 local R10 contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-r10-measured-performance.py 2>&1 | tee "$LOCAL_EVID/tests/r10-unit.out"

log "2/4 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"
"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
echo STAGING_COPY_OK
REMOTE

log "3/4 measure staging directory / home / health"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/tests/staging-db.out"
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
"$PYBIN" smoke-test-r10-measured-performance-db.py
echo STAGING_RC=$?
REMOTE

log "4/4 live /health /ready timing"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/timing.out"
set -euo pipefail
python3 - <<'PY'
import time, urllib.request
for path in ("/health", "/ready"):
    url = "http://127.0.0.1:8011" + path
    start = time.perf_counter()
    with urllib.request.urlopen(url, timeout=10) as resp:
        code = resp.status
        body = resp.read(200)
    elapsed = time.perf_counter() - start
    print(f"{path} status={code} ms={elapsed*1000:.0f}")
    if code != 200:
        raise SystemExit(f"{path} not 200")
    if elapsed > 2.5:
        raise SystemExit(f"{path} over budget {elapsed:.3f}s")
print("LIVE_TIMING_OK")
PY
REMOTE

echo "EVIDENCE=$LOCAL_EVID"
if grep -q "R10_MEASURED_PERFORMANCE_UNIT_PASS" "$LOCAL_EVID/tests/r10-unit.out" \
  && grep -q "R10_MEASURED_PERFORMANCE_DB_PASS" "$LOCAL_EVID/tests/staging-db.out" \
  && grep -q "LIVE_TIMING_OK" "$LOCAL_EVID/live/timing.out"; then
  echo R10_QUALIFY_GREEN
  exit 0
fi
echo R10_QUALIFY_RED
exit 1
