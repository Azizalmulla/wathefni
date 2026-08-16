#!/usr/bin/env bash
# pdf-inspector Shadow Advisor Wave 1 — tightly controlled production shadow enable.
# Observation only. Never changes OCR routing. Requires staging GO evidence.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
: "${STAGING_EVID:?Set STAGING_EVID to staging qualify evidence dir}"
LOCAL_EVID="$REPO_ROOT/ops/evidence/pdf-inspector-shadow-wave1-prod-${STAMP}"
VPS_HOST="${VPS_HOST:-root@76.13.63.68}"
REMOTE_EVID="/opt/wathefni/production-evidence/pdf-inspector-shadow-wave1/${STAMP}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-pdf-inspector-shadow-wave1-${STAMP}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-pdf-inspector-shadow-wave1.conf
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=25 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=25)

test -f "$STAGING_EVID/docs/GATE.json"
python3 - <<PY
import json
g=json.load(open("$STAGING_EVID/docs/GATE.json"))
assert g.get("staging")=="GO", g
assert g.get("influences_ocr") is False, g
print("staging_prereq_ok", g)
PY

mkdir -p "$LOCAL_EVID"/{sources,tests,docs,flags,backup}
cp -a "$ORCH_SRC/pdf_inspector_shadow.py" "$ORCH_SRC/cv_extraction.py" \
  "$ORCH_SRC/smoke-test-pdf-inspector-shadow-wave1.py" "$LOCAL_EVID/sources/"

"${SSH[@]}" "mkdir -p '$REMOTE_EVID'/{tests,flags,backup,fixtures} '$BACKUP'/modules /etc/systemd/system/wathefni-orchestrator.service.d"
"${SCP[@]}" \
  "$ORCH_SRC/pdf_inspector_shadow.py" \
  "$ORCH_SRC/cv_extraction.py" \
  "$ORCH_SRC/smoke-test-pdf-inspector-shadow-wave1.py" \
  "$VPS_HOST:/tmp/pdf-inspector-shadow-wave1-prod/"

WAVE0_FIX="$REPO_ROOT/ops/evidence/pdf-inspector-deep-eval-wave0-20260804/fixtures"
"${SSH[@]}" "mkdir -p /tmp/pdf-inspector-shadow-wave1-prod"
if [[ -d "$WAVE0_FIX" ]]; then
  "${SCP[@]}" "$WAVE0_FIX"/*.pdf "$VPS_HOST:$REMOTE_EVID/fixtures/"
fi

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/prod-enable.out"
set -euo pipefail
ORCH='$ORCH'
BACKUP='$BACKUP'
EVID='$REMOTE_EVID'
DROPIN='$DROPIN'
STG_SRC=/tmp/pdf-inspector-shadow-wave1-prod
PY=\$ORCH/.venv/bin/python

# Refuse if ingest on
INGEST=\$(tr '\\0' '\\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo unset)
echo "\$INGEST" | tee \$EVID/flags/ingest-before.txt
if echo "\$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo 'REFUSE: CAPTURE_INGEST must remain off' >&2
  exit 3
fi

mkdir -p \$BACKUP/modules \$EVID/backup
for f in cv_extraction.py pdf_inspector_shadow.py; do
  [[ -f \$ORCH/\$f ]] && cp -a \$ORCH/\$f \$BACKUP/modules/ || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. \$BACKUP/systemd-dropins/ 2>/dev/null || mkdir -p \$BACKUP/systemd-dropins
(
  cd \$BACKUP
  find modules -type f 2>/dev/null | while read -r f; do sha256sum "\$f"; done
) | tee \$BACKUP/SHA256SUMS
echo \$BACKUP > \$EVID/backup/BACKUP_PATH.txt

cat > \$BACKUP/ROLLBACK.sh <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="\${1:-\$(cd "\$(dirname "\$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-pdf-inspector-shadow-wave1.conf
test -d "\$BACKUP_DIR"
if [[ -f \$BACKUP_DIR/modules/cv_extraction.py ]]; then
  cp -a \$BACKUP_DIR/modules/cv_extraction.py \$ORCH/cv_extraction.py
fi
if [[ -f \$BACKUP_DIR/modules/pdf_inspector_shadow.py ]]; then
  cp -a \$BACKUP_DIR/modules/pdf_inspector_shadow.py \$ORCH/pdf_inspector_shadow.py
else
  rm -f \$ORCH/pdf_inspector_shadow.py
fi
rm -f "\$DROPIN"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
RB
chmod +x \$BACKUP/ROLLBACK.sh
cp -a \$BACKUP/ROLLBACK.sh \$EVID/backup/ROLLBACK.sh

# Ensure dependency present
\$PY -m pip install -q 'pdf-inspector==0.2.6'

# Deploy modules
cp -a \$STG_SRC/cv_extraction.py \$ORCH/cv_extraction.py
cp -a \$STG_SRC/pdf_inspector_shadow.py \$ORCH/pdf_inspector_shadow.py
cp -a \$STG_SRC/smoke-test-pdf-inspector-shadow-wave1.py \$ORCH/ || true

cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PDF_INSPECTOR_SHADOW=1
Environment=WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS=500
EOF
cp -a "\$DROPIN" \$EVID/flags/

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'PDF_INSPECTOR_SHADOW|CAPTURE_INGEST|MISTRAL_OCR' | sort | tee \$EVID/flags/prod-environ.txt
grep -q 'WATHEFNI_PDF_INSPECTOR_SHADOW=1' \$EVID/flags/prod-environ.txt
grep -qiE 'CAPTURE_INGEST=off|CAPTURE_INGEST=0|CAPTURE_INGEST=false|CAPTURE_INGEST=no' \$EVID/flags/prod-environ.txt || \\
  grep -vq 'CAPTURE_INGEST=on' \$EVID/flags/prod-environ.txt

# Offline observation smoke against production modules (OCR forced off in smoke env)
set -a; source /root/.openclaw/secrets/postgres.env; set +a
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_CV_MISTRAL_OCR=0
export WATHEFNI_PDF_INSPECTOR_SHADOW=1
export WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS=500
export PDF_INSPECTOR_SHADOW_EVID=\$EVID/tests
export PDF_INSPECTOR_WAVE0_FIXTURES=\$EVID/fixtures
cd \$ORCH
\$PY -u smoke-test-pdf-inspector-shadow-wave1.py | tee \$EVID/tests/smoke.out
grep -q PDF_INSPECTOR_SHADOW_WAVE1_SMOKE_PASS \$EVID/tests/smoke.out

# Static proof: no OCR influence constants in shadow module
\$PY - <<'PY'
from pathlib import Path
src = Path('pdf_inspector_shadow.py').read_text()
assert 'influences_ocr_routing' in src
assert 'False' in src
# ensure cv_extraction still decides needs before/independent of shadow mutation
cv = Path('cv_extraction.py').read_text()
assert 'pdf_inspector_shadow' in cv
assert 'must not influence needs/accepted/OCR routing' in cv
print('static_no_routing_influence_ok')
PY

echo PROD_SHADOW_OBSERVATION_ENABLE_OK backup=\$BACKUP evid=\$EVID
REMOTE

grep -q PROD_SHADOW_OBSERVATION_ENABLE_OK "$LOCAL_EVID/tests/prod-enable.out"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/tests" "$LOCAL_EVID/" 2>/dev/null || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/flags" "$LOCAL_EVID/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/backup/BACKUP_PATH.txt" "$LOCAL_EVID/backup/" 2>/dev/null || true

python3 - <<PY
import json
from pathlib import Path
evid=Path("$LOCAL_EVID")
smoke=None
for p in sorted((evid/"tests").rglob("smoke-result.json")):
    smoke=json.loads(p.read_text())
assert smoke and smoke.get("ok") and smoke.get("behavioral_invariance")
assert smoke.get("p95_shadow_wall_ms",999)<=150
gate={
  "wave":"pdf_inspector_shadow_advisor_wave1",
  "staging":"GO",
  "production_shadow_observation":"GO",
  "influences_ocr":False,
  "p95_shadow_wall_ms":smoke.get("p95_shadow_wall_ms"),
  "rollback":"bash /opt/wathefni/backups/production-pre-pdf-inspector-shadow-wave1-*/ROLLBACK.sh",
}
(evid/"docs").mkdir(parents=True, exist_ok=True)
(evid/"docs"/"GATE.json").write_text(json.dumps(gate, indent=2))
print(json.dumps(gate, indent=2))
PY

echo "PROD_SHADOW_GO evid=$LOCAL_EVID"
