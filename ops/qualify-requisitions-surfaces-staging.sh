#!/usr/bin/env bash
# Requisitions Surface Wave — staging qualify (backend freeze preserved).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/requisitions-surfaces-$STAMP"
REMOTE_STAGE="/tmp/req-surfaces-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit (backend freeze + surfaces wiring)"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-requisitions-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/backend-unit.out"
"$PY" smoke-test-requisitions-surfaces.py 2>&1 | tee "$LOCAL_EVID/tests/surfaces-unit.out"

log "stage sources"
cp -a \
  "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/requisitions_surfaces.py" \
  "$ORCH_SRC/requisitions_http.py" \
  "$ORCH_SRC/smoke-test-requisitions-surfaces.py" \
  "$ORCH_SRC/smoke-test-requisitions-surfaces-db.py" \
  "$ORCH_SRC/operator_mobile.py" \
  "$ORCH_SRC/operator_mobile_data.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/requisitions_wave1_v1.sql" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/REQUISITIONS_WAVE1_BACKEND_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql'"
"${SCP[@]}" \
  "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/requisitions_surfaces.py" \
  "$ORCH_SRC/requisitions_http.py" \
  "$ORCH_SRC/smoke-test-requisitions-surfaces-db.py" \
  "$ORCH_SRC/operator_mobile.py" \
  "$ORCH_SRC/operator_mobile_data.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/requisitions_wave1_v1.sql" "$VPS_HOST:$REMOTE_STAGE/ops/sql/" 2>/dev/null || true

log "copy to staging orch (no global enable)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/*.sql "\$STG/ops/sql/" 2>/dev/null || true
if ! grep -q 'register_requisitions_http' "\$STG/app.py"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/opt/wathefni/staging/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
needle = "register_probation_http(sys.modules[__name__])"
hook = '''
try:
    import requisitions_http as _requisitions_http

    _requisitions_http.register_requisitions_http(sys.modules[__name__])
except Exception:
    pass
'''
if "register_requisitions_http" in text:
    print("HTTP_REGISTER_ALREADY_PRESENT")
elif needle in text:
    idx = text.find(needle)
    end2 = text.find("except Exception:", idx)
    if end2 > 0:
        end = text.find("pass", end2)
        end = text.find("\\n", end) + 1
        text = text[:end] + hook + text[end:]
        p.write_text(text, encoding="utf-8")
        print("HTTP_REGISTER_PATCHED")
    else:
        raise SystemExit("HTTP_REGISTER_ANCHOR_INCOMPLETE")
else:
    raise SystemExit("HTTP_REGISTER_ANCHOR_MISSING")
PY
else
  echo HTTP_REGISTER_ALREADY_PRESENT
fi
if ! grep -q 'requisitions.approve' "\$STG/app.py"; then
  echo 'WARN_STAGING_APP_MISSING_REQUISITIONS_RBAC_SYNC_LOCAL_APP'
fi
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*requisition* 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_REQUISITIONS_DROPIN; exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "sync requisitions RBAC into staging app.py if needed"
"${SSH[@]}" "bash -s" <<'REMOTE' | tee "$LOCAL_EVID/tests/staging-app-sync.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator/app.py
python3 - <<'PY'
from pathlib import Path
p = Path("/opt/wathefni/staging/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
changed = False
if "requisitions.read" not in text:
    marker = "_POSTHIRE_PERMS_FULL = {"
    hook = '''_REQUISITIONS_PERMS_FULL = {
    "requisitions.read", "requisitions.manage", "requisitions.approve",
}
_REQUISITIONS_PERMS_OPERATE = {
    "requisitions.read", "requisitions.manage",
}
_REQUISITIONS_PERMS_APPROVE = {
    "requisitions.read", "requisitions.approve",
}
_REQUISITIONS_PERMS_READ = {"requisitions.read"}

'''
    if marker in text:
        text = text.replace(marker, hook + marker, 1)
        changed = True
    # best-effort inject into owner role block once
    if '*_POSTHIRE_PERMS_FULL,' in text and '*_REQUISITIONS_PERMS_FULL,' not in text:
        text = text.replace('*_POSTHIRE_PERMS_FULL,', '*_REQUISITIONS_PERMS_FULL,\n        *_POSTHIRE_PERMS_FULL,', 3)
        changed = True
if changed:
    p.write_text(text, encoding="utf-8")
    print("APP_RBAC_PATCHED")
else:
    print("APP_RBAC_OK")
PY
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
"\$PYBIN" smoke-test-requisitions-surfaces-db.py
echo STAGING_DB_RC=\$?
REMOTE

UNIT_OK=NO
if grep -q 'REQUISITIONS_SURFACES_UNIT_FULL_PASS' "$LOCAL_EVID/tests/surfaces-unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/surfaces-unit.out"; then
  UNIT_OK=YES
fi
DB_OK=NO
if grep -q 'REQUISITIONS_SURFACES_DB_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='REQUISITIONS_SURFACES_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Requisitions Surfaces — Staging Prove

- Stamp: $STAMP
- Surfaces unit: $UNIT_OK
- Staging DB: $DB_OK
- Backend freeze: preserved (no SM rewrite)
- Global enable: NO
- Verdict: **$VERDICT**

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != REQUISITIONS_SURFACES_FULL_PASS ]]; then
  exit 1
fi
