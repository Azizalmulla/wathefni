#!/usr/bin/env bash
# Wave 1 — Requisitions backend + job publish gate prove on staging.
# No global enable. No Requisitions/Preboarding UI. Truth-sync writers untouched.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/requisitions-wave1-$STAMP"
REMOTE_STAGE="/tmp/req-wave1-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/requisitions-wave1/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources/ops/sql,remote}
echo "$LOCAL_EVID" > /tmp/req-wave1.evid
echo "$STAMP" > /tmp/req-wave1.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local unit smoke"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
set +e
"$PY" smoke-test-requisitions-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"
UNIT_RC=${PIPESTATUS[0]}
set -e
if [[ "$UNIT_RC" -ne 0 ]]; then
  echo "UNIT_FAILED"
  exit 1
fi

log "stage sources (no systemd env enable)"
cp -a "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/prehire_jobs.py" \
  "$ORCH_SRC/smoke-test-requisitions-wave1.py" \
  "$ORCH_SRC/smoke-test-requisitions-wave1-db.py" \
  "$LOCAL_EVID/sources/"
# app.py is large — capture only the ensure hook snippet for evidence
python3 - <<PY > "$LOCAL_EVID/sources/app_ensure_requisitions_snippet.py"
from pathlib import Path
p = Path("$ORCH_SRC/app.py")
text = p.read_text(encoding="utf-8")
needle = "ensure_requisitions_schema"
idx = text.find(needle)
print(text[max(0, idx - 200): idx + 200] if idx >= 0 else "MISSING")
PY
cp -a "$ORCH_SRC/ops/sql/requisitions_wave1_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/qualify-requisitions-wave1-staging.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/REQUISITIONS_WAVE1_BACKEND.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/requisitions.py" \
  "$ORCH_SRC/prehire_jobs.py" \
  "$ORCH_SRC/smoke-test-requisitions-wave1.py" \
  "$ORCH_SRC/smoke-test-requisitions-wave1-db.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/requisitions_wave1_v1.sql" "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

log "copy into staging orchestrator tree (authority + gate hook; NO global flag)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
test -d "\$STG"
cp -a '$REMOTE_STAGE'/requisitions.py "\$STG/"
cp -a '$REMOTE_STAGE'/prehire_jobs.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-requisitions-wave1.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-requisitions-wave1-db.py "\$STG/"
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/requisitions_wave1_v1.sql "\$STG/ops/sql/"
# Ensure app.py on staging has ensure hook (patch if missing — additive only).
# Staging trees may lag local Phase A hooks; anchor on end of _ensure_schema_impl.
if ! grep -q 'ensure_requisitions_schema' "\$STG/app.py"; then
  python3 - <<'PY'
from pathlib import Path
p = Path("/opt/wathefni/staging/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
hook = '''
            # Wave 1 — requisitions schema (dark; runtime gated by flags).
            try:
                import requisitions as _requisitions

                _requisitions.ensure_requisitions_schema(cur)
            except Exception:
                pass
'''
if "ensure_requisitions_schema" in text:
    print("APP_HOOK_ALREADY_PRESENT")
else:
    # Prefer insert after attendance_ops ensure (last known Phase A-era block on staging),
    # else before the final conn.commit() of _ensure_schema_impl.
    anchors = [
        "_attendance_ops_pg.ensure_attendance_ops_postgres_schema(cur)",
        "ensure_attendance_ops_postgres_schema(cur)",
    ]
    inserted = False
    for marker in anchors:
        idx = text.find(marker)
        if idx < 0:
            continue
        # end of surrounding try/except pass
        end = text.find("except Exception:", idx)
        if end < 0:
            end = text.find("\n", idx) + 1
        else:
            end = text.find("pass", end)
            end = text.find("\n", end) + 1
        text = text[:end] + hook + text[end:]
        inserted = True
        break
    if not inserted:
        impl = text.find("def _ensure_schema_impl")
        if impl < 0:
            raise SystemExit("APP_HOOK_IMPL_MISSING")
        # last conn.commit() before next top-level def after impl
        next_def = text.find("\ndef ", impl + 1)
        chunk = text[impl:next_def if next_def > 0 else None]
        rel = chunk.rfind("conn.commit()")
        if rel < 0:
            raise SystemExit("APP_HOOK_COMMIT_MISSING")
        abs_i = impl + rel
        text = text[:abs_i] + hook + "\n        " + text[abs_i:]
    p.write_text(text, encoding="utf-8")
    print("APP_HOOK_PATCHED")
PY
else
  echo APP_HOOK_ALREADY_PRESENT
fi
if ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/*requisition* 2>/dev/null; then
  echo 'UNEXPECTED_SYSTEMD_REQUISITION_DROPIN'
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
# Process-only canary flags — not systemd.
export WATHEFNI_REQUISITIONS=on
export WATHEFNI_REQUISITIONS_COMPANIES=REQ-CANARY-PLACEHOLDER
"\$PYBIN" smoke-test-requisitions-wave1-db.py
echo STAGING_DB_RC=\$?
REMOTE

DB_OK=NO
if grep -q 'REQUISITIONS_WAVE1_DB_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

UNIT_OK=NO
if grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='REQUISITIONS_WAVE1_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Requisitions Wave 1 — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging DB: $DB_OK
- Global enable: NO (process-scoped flags only)
- UI: none (backend + gate only)
- Truth-sync writers: untouched / remain OFF
- Verdict: **$VERDICT**

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != REQUISITIONS_WAVE1_FULL_PASS ]]; then
  exit 1
fi
