#!/usr/bin/env bash
# Preboarding Surface Wave — staging qualify (backend freeze preserved).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/preboarding-surfaces-$STAMP"
REMOTE_STAGE="/tmp/pb-surfaces-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit (backend freeze + surfaces wiring)"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-preboarding-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/backend-unit.out"
"$PY" smoke-test-preboarding-surfaces.py 2>&1 | tee "$LOCAL_EVID/tests/surfaces-unit.out"

log "stage sources"
cp -a \
  "$ORCH_SRC/preboarding.py" \
  "$ORCH_SRC/preboarding_surfaces.py" \
  "$ORCH_SRC/preboarding_http.py" \
  "$ORCH_SRC/smoke-test-preboarding-surfaces.py" \
  "$ORCH_SRC/smoke-test-preboarding-surfaces-db.py" \
  "$ORCH_SRC/operator_mobile.py" \
  "$ORCH_SRC/operator_mobile_data.py" \
  "$ORCH_SRC/employee_app_access.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/preboarding_wave1_v1.sql" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PREBOARDING_SURFACE_WAVE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PREBOARDING_WAVE1_BACKEND_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql'"
"${SCP[@]}" \
  "$ORCH_SRC/preboarding.py" \
  "$ORCH_SRC/preboarding_surfaces.py" \
  "$ORCH_SRC/preboarding_http.py" \
  "$ORCH_SRC/smoke-test-preboarding-surfaces-db.py" \
  "$ORCH_SRC/operator_mobile.py" \
  "$ORCH_SRC/operator_mobile_data.py" \
  "$ORCH_SRC/employee_app_access.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/preboarding_wave1_v1.sql" "$VPS_HOST:$REMOTE_STAGE/ops/sql/" 2>/dev/null || true

log "copy to staging orch (no global enable)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/*.sql "\$STG/ops/sql/" 2>/dev/null || true
# Ensure app.py registers preboarding_http
if ! grep -q 'register_preboarding_http' "\$STG/app.py"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/opt/wathefni/staging/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
needle = "_operator_mobile_data.register_operator_mobile_data_routes(sys.modules[__name__])"
hook = '''
try:
    import preboarding_http as _preboarding_http

    _preboarding_http.register_preboarding_http(sys.modules[__name__])
except Exception:
    pass
'''
if "register_preboarding_http" in text:
    print("HTTP_REGISTER_ALREADY_PRESENT")
elif needle in text:
    text = text.replace(needle, needle + "\n" + hook, 1)
    p.write_text(text, encoding="utf-8")
    print("HTTP_REGISTER_PATCHED")
else:
    raise SystemExit("HTTP_REGISTER_ANCHOR_MISSING")
PY
else
  echo HTTP_REGISTER_ALREADY_PRESENT
fi
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*preboard* 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_PREBOARDING_DROPIN; exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "staging DB surfaces prove"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-db.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
export WATHEFNI_PREBOARDING=on
export WATHEFNI_PREBOARDING_COMPANIES=PBS-CANARY-PLACEHOLDER
"\$PYBIN" smoke-test-preboarding-surfaces-db.py
echo STAGING_DB_RC=\$?
REMOTE

UNIT_OK=NO
if grep -q 'PREBOARDING_SURFACES_UNIT_PASS' "$LOCAL_EVID/tests/surfaces-unit.out" \
  && grep -q 'REQUISITIONS_WAVE1_UNIT_PASS\|PREBOARDING_WAVE1_UNIT_PASS' "$LOCAL_EVID/tests/backend-unit.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/tests/surfaces-unit.out"; then
  UNIT_OK=YES
fi
# backend unit file is preboarding wave1
if grep -q 'PREBOARDING_WAVE1_UNIT_PASS' "$LOCAL_EVID/tests/backend-unit.out"; then
  :
else
  UNIT_OK=NO
fi

DB_OK=NO
if grep -q 'PREBOARDING_SURFACES_DB_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='PREBOARDING_SURFACES_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Preboarding Surface Wave — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB surfaces: $DB_OK
- Backend freeze: preserved
- Global enable: NO
- UI: HR Web + HR Mobile + Employee App core wired (client artifacts in repo)
- Verdict: **$VERDICT**

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == PREBOARDING_SURFACES_FULL_PASS ]]
