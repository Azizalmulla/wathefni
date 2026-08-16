#!/usr/bin/env bash
# Wave 1 — Probation backend prove on staging.
# No global enable. No Probation UI.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/probation-wave1-$STAMP"
REMOTE_STAGE="/tmp/prb-wave1-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/probation-wave1/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources/ops/sql}
echo "$LOCAL_EVID" > /tmp/prb-wave1.evid

log() { printf '\n=== %s ===\n' "$*"; }

log "local unit smoke"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
set +e
"$PY" smoke-test-probation-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"
UNIT_RC=${PIPESTATUS[0]}
set -e
if [[ "$UNIT_RC" -ne 0 ]]; then
  echo "UNIT_FAILED"
  exit 1
fi

log "stage sources"
cp -a "$ORCH_SRC/probation.py" \
  "$ORCH_SRC/smoke-test-probation-wave1.py" \
  "$ORCH_SRC/smoke-test-probation-wave1-db.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/probation_wave1_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/PROBATION_WAVE1_BACKEND.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
# Also refresh hire bridge soft hook + app schema ensure if present
cp -a "$ORCH_SRC/hire_ready_bridge.py" "$LOCAL_EVID/sources/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/probation.py" \
  "$ORCH_SRC/smoke-test-probation-wave1.py" \
  "$ORCH_SRC/smoke-test-probation-wave1-db.py" \
  "$ORCH_SRC/hire_ready_bridge.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/probation_wave1_v1.sql" "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

log "copy into staging orchestrator (authority only; NO global flag)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
test -d "\$STG"
cp -a '$REMOTE_STAGE'/probation.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-probation-wave1.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-probation-wave1-db.py "\$STG/"
cp -a '$REMOTE_STAGE'/hire_ready_bridge.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/probation_wave1_v1.sql "\$STG/ops/sql/"
if ! grep -q 'ensure_probation_schema' "\$STG/app.py"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/opt/wathefni/staging/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
hook = '''
            # Wave 1 — probation schema (dark; runtime gated by flags; no UI yet).
            try:
                import probation as _probation

                _probation.ensure_probation_schema(cur)
            except Exception:
                pass
'''
if "ensure_probation_schema" in text:
    print("APP_HOOK_ALREADY_PRESENT")
else:
    marker = "ensure_preboarding_schema(cur)"
    idx = text.find(marker)
    if idx < 0:
        raise SystemExit("APP_HOOK_ANCHOR_MISSING")
    end = text.find("except Exception:", idx)
    end = text.find("pass", end)
    end = text.find("\\n", end) + 1
    text = text[:end] + hook + text[end:]
    p.write_text(text, encoding="utf-8")
    print("APP_HOOK_PATCHED")
PY
else
  echo APP_HOOK_ALREADY_PRESENT
fi
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*probation* 2>/dev/null; then
  echo 'UNEXPECTED_SYSTEMD_PROBATION_DROPIN'
  exit 1
fi
echo STAGING_COPY_OK_NO_GLOBAL_ENABLE
REMOTE

log "staging DB prove (process-scoped flags only)"
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
"\$PYBIN" smoke-test-probation-wave1-db.py
echo STAGING_DB_RC=\$?
REMOTE

DB_OK=NO
if grep -q 'PROBATION_WAVE1_DB_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

UNIT_OK=NO
if grep -q 'PROBATION_WAVE1_UNIT_FULL_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='PROBATION_WAVE1_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Probation Wave 1 Backend — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB: $DB_OK
- Global enable: NO
- UI: none (backend authority only)
- Hire→Ready bridge: FROZEN (soft optional probation hook only)
- Verdict: **$VERDICT**

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != PROBATION_WAVE1_FULL_PASS ]]; then
  exit 1
fi
