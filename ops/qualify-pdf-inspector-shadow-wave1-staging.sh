#!/usr/bin/env bash
# pdf-inspector Shadow Advisor Wave 1 — staging qualify (observation only).
# Does not change OCR routing. Does not touch production modules. No Migration Wave 1-B.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
LOCAL_EVID="$REPO_ROOT/ops/evidence/pdf-inspector-shadow-wave1-${STAMP}"
VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
REMOTE_EVID="/opt/wathefni/staging-evidence/pdf-inspector-shadow-wave1/${STAMP}"
STG=/opt/wathefni/staging/orchestrator
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=25 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=25)

mkdir -p "$LOCAL_EVID"/{sources,tests,docs,flags}
log() { printf '\n=== %s ===\n' "$*"; }

log "stage sources"
cp -a "$ORCH_SRC/pdf_inspector_shadow.py" \
  "$ORCH_SRC/cv_extraction.py" \
  "$ORCH_SRC/smoke-test-pdf-inspector-shadow-wave1.py" \
  "$ORCH_SRC/requirements.txt" \
  "$LOCAL_EVID/sources/"

log "push staging-only modules + fixtures"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID'/{tests,flags,fixtures,backup} '$STG' /etc/systemd/system/wathefni-orchestrator-staging.service.d"
"${SCP[@]}" \
  "$ORCH_SRC/pdf_inspector_shadow.py" \
  "$ORCH_SRC/cv_extraction.py" \
  "$ORCH_SRC/smoke-test-pdf-inspector-shadow-wave1.py" \
  "$ORCH_SRC/requirements.txt" \
  "$VPS_HOST:$STG/"

WAVE0_FIX="$REPO_ROOT/ops/evidence/pdf-inspector-deep-eval-wave0-20260804/fixtures"
if [[ -d "$WAVE0_FIX" ]]; then
  "${SCP[@]}" "$WAVE0_FIX"/*.pdf "$VPS_HOST:$REMOTE_EVID/fixtures/"
fi

log "staging qualify"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-qualify.out"
set -euo pipefail
STG='$STG'
PROD_VENV=/opt/wathefni/orchestrator/.venv
PY=\$PROD_VENV/bin/python
EVID='$REMOTE_EVID'
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-pdf-inspector-shadow-wave1.conf

# Backup staging modules only
mkdir -p "\$EVID/backup"
for f in cv_extraction.py pdf_inspector_shadow.py smoke-test-pdf-inspector-shadow-wave1.py; do
  [[ -f \$STG/\$f ]] && cp -a \$STG/\$f \$EVID/backup/ || true
done

# Shared venv dependency (staging ExecStart uses this venv)
\$PY -m pip install -q 'pdf-inspector==0.2.6'
\$PY - <<'PY'
from importlib.metadata import version
import pdf_inspector
print('pdf_inspector', version('pdf-inspector'))
print('module', pdf_inspector.__file__)
PY

cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PDF_INSPECTOR_SHADOW=1
Environment=WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS=500
EOF
cp -a "\$DROPIN" "\$EVID/flags/"
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator-staging
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'PDF_INSPECTOR_SHADOW|CAPTURE_INGEST|MISTRAL_OCR' | sort | tee "\$EVID/flags/staging-environ.txt"
grep -q 'WATHEFNI_PDF_INSPECTOR_SHADOW=1' "\$EVID/flags/staging-environ.txt"

set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_CV_MISTRAL_OCR=0
export WATHEFNI_PDF_INSPECTOR_SHADOW=1
export WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS=500
export PDF_INSPECTOR_SHADOW_EVID=\$EVID/tests
export PDF_INSPECTOR_WAVE0_FIXTURES=\$EVID/fixtures
cd \$STG
\$PY -u smoke-test-pdf-inspector-shadow-wave1.py | tee \$EVID/tests/smoke.out
grep -q PDF_INSPECTOR_SHADOW_WAVE1_SMOKE_PASS \$EVID/tests/smoke.out

# Prove production modules were not overwritten by this wave
if [[ -f /opt/wathefni/orchestrator/pdf_inspector_shadow.py ]]; then
  echo 'REFUSE: production unexpectedly has pdf_inspector_shadow.py from staging wave' >&2
  exit 3
fi
echo STAGING_SHADOW_QUALIFY_OK
REMOTE

grep -q STAGING_SHADOW_QUALIFY_OK "$LOCAL_EVID/tests/staging-qualify.out"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/tests" "$LOCAL_EVID/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/flags" "$LOCAL_EVID/" 2>/dev/null || true

python3 - <<PY
import json
from pathlib import Path
evid = Path("$LOCAL_EVID")
smoke = None
for p in sorted((evid / "tests").rglob("smoke-result.json")):
    smoke = json.loads(p.read_text())
assert smoke and smoke.get("ok"), smoke
assert smoke.get("p95_shadow_wall_ms", 999) <= 150, smoke
assert smoke.get("behavioral_invariance") is True
gate = {
    "wave": "pdf_inspector_shadow_advisor_wave1",
    "staging": "GO",
    "production_shadow_observation": "PENDING_ENABLE",
    "influences_ocr": False,
    "p95_shadow_wall_ms": smoke.get("p95_shadow_wall_ms"),
    "rollback": "Remove staging drop-in zzzz-pdf-inspector-shadow-wave1.conf and unset WATHEFNI_PDF_INSPECTOR_SHADOW",
}
(evid / "docs").mkdir(parents=True, exist_ok=True)
(evid / "docs" / "GATE.json").write_text(json.dumps(gate, indent=2))
print(json.dumps(gate, indent=2))
print("LOCAL_EVID=$LOCAL_EVID")
PY

echo "STAGING_GO evid=$LOCAL_EVID"
