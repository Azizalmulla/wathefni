#!/usr/bin/env bash
# Attendance Wave 2E — production DARK deploy: capture-ops foundation + dashboard UI.
# Keeps real device ingest OFF, IMPORT off, SYNTHETIC_ONLY on, QR/GPS/kiosk off.
# Secrets only via EnvironmentFile. Leak scan gates evidence.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-attendance-wave2e-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-wave2e-dark/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/attw2e-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2e-capture-ops-dark.conf
DROPIN_2C=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
DASH_DIST=/opt/wathefni/dashboard-dist
SECRETS=/root/.openclaw/secrets/attendance-capture.env

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,canary,backup,schema,privacy,cleanup,ui,tests} "$BACKUP" "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

load_service_env() {
  local PID
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  while IFS= read -r -d '' line; do
    case "$line" in
      WATHEFNI_*=*) export "$line" ;;
    esac
  done < /proc/"$PID"/environ
}

redact_tee() {
  # shellcheck disable=SC2001
  sed -E \
    -e 's/(WATHEFNI_CAPTURE_CREDENTIAL_KEY|BIOTIME_PASSWORD|BIOTIME_TOKEN|CONNECTOR_PASSWORD|CONNECTOR_TOKEN)=[^[:space:]]+/\1=[REDACTED]/g' \
    -e 's/("password"|"token"|"api_secret"|"secret")[[:space:]]*:[[:space:]]*"[^"]*"/\1:"[REDACTED]"/g'
}

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH"/attendance_authority_*.py "$ORCH"/attendance_capture_*.py 2>/dev/null || true
  echo "=== flags before ==="
  load_service_env
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ATTENDANCE|DB_POOL|IMPORT|CAPTURE' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort || true
} | tee "$REMOTE_EVID/preflight/before-deploy.txt"

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
load_service_env
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1

cd "$ORCH"
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/preflight/attendance-counts-before.json"
import json, app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=cur.fetchone()["db"]; assert db=="wathefni"
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'"); n=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'"); demo=int(cur.fetchone()["n"])
print(json.dumps({"db":db,"wathefni_rows":n,"demo_seed":demo}, indent=2))
assert n==42 and demo==42
PY

log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/attendance_authority_wave1.py" "$BACKUP/attendance_authority_wave1.py" 2>/dev/null || true
mkdir -p "$BACKUP/capture_modules" "$BACKUP/dashboard-dist"
for f in "$ORCH"/attendance_capture_*.py; do
  [[ -f "$f" ]] && cp -a "$f" "$BACKUP/capture_modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins"
if [[ -d "$DASH_DIST" ]]; then
  rsync -a --delete "$DASH_DIST/" "$BACKUP/dashboard-dist/" || cp -a "$DASH_DIST" "$BACKUP/dashboard-dist-copy"
fi
sudo -u postgres psql -d wathefni -c "COPY (SELECT attendance_id, employee_key, status, metadata->>'demo_seed' AS demo_seed FROM attendance_records WHERE company_code='WATHEFNI' ORDER BY attendance_id) TO STDOUT WITH CSV HEADER" > "$BACKUP/attendance-records-fingerprint.csv"
sha256sum "$BACKUP/app.py" "$BACKUP/attendance-records-fingerprint.csv" | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

# Secrets via EnvironmentFile only — never echo values
if [[ ! -f "$SECRETS" ]]; then
  KEY=$(cd "$ORCH" && .venv/bin/python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)
  umask 077
  printf 'WATHEFNI_CAPTURE_CREDENTIAL_KEY=%s\n' "$KEY" > "$SECRETS"
  chmod 600 "$SECRETS"
fi
{
  echo "secrets_path=$SECRETS"
  echo "secrets_mode=$(stat -c %a "$SECRETS")"
  echo "credential_key_absent_from_evidence=true"
} | tee "$REMOTE_EVID/privacy/secrets-provisioned.txt"
if grep -R "WATHEFNI_CAPTURE_CREDENTIAL_KEY=[^\\[]" "$REMOTE_EVID" 2>/dev/null; then
  echo "REFUSE: credential key leaked into evidence" >&2
  exit 3
fi

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2e-capture-ops-dark.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
# restore prior capture modules snapshot
rm -f "$ORCH"/attendance_capture_ops.py "$ORCH"/attendance_capture_ops_http.py \
  "$ORCH"/attendance_capture_secrets.py "$ORCH"/attendance_capture_registry.py \
  "$ORCH"/attendance_capture_remediation.py "$ORCH"/attendance_capture_health.py \
  "$ORCH"/attendance_capture_compat.py
if [[ -d "$BACKUP_DIR/capture_modules" ]]; then
  cp -a "$BACKUP_DIR/capture_modules"/. "$ORCH/" || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"
echo rollback_ready=true | tee "$REMOTE_EVID/backup/rollback-ready.txt"

log "deploying modules"
cp -a "$STAGE"/app.py "$ORCH/app.py"
cp -a "$STAGE"/attendance_capture_*.py "$ORCH/"
cp -a "$STAGE"/attendance_authority_wave1.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/canary-prod-attendance-wave2e.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/smoke-test-attendance-capture-wave2d.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/ATTENDANCE_*.md /opt/wathefni/ops/ 2>/dev/null || true

# Dashboard dist (prebuilt)
if [[ -d "$STAGE/dashboard-dist" ]]; then
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
fi

# Keep 2C synthetic authority flags; add capture-ops dark flags (ingest off)
# Prefer leaving 2C dropin in place and add 2E dropin for capture ops only
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_CAPTURE_OPS=on
Environment=WATHEFNI_ATTENDANCE_CAPTURE_OPS_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ATTENDANCE_IMPORT=off
EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env
EOF

# Ensure 2C synthetic dropin still present; recreate if missing
if [[ ! -f "$DROPIN_2C" ]]; then
  cat > "$DROPIN_2C" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_AUTHORITY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,ATTW2E,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_IMPORT=off
Environment=WATHEFNI_DB_POOL_MAX=8
EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env
EOF
else
  # Extend markers with ATTW2E / W2E-SYNTH| if not present
  if ! grep -q 'ATTW2E' "$DROPIN_2C"; then
    sed -i 's/ATTW2C,W1C-SYNTH|,W2C-SYNTH|/ATTW2C,ATTW2E,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|/' "$DROPIN_2C" || true
  fi
fi

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8010/health | tee "$REMOTE_EVID/verify/health-after-deploy.json"; echo

load_service_env
{
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ATTENDANCE|DB_POOL|CAPTURE|IMPORT' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort
} | tee "$REMOTE_EVID/flags/prod-flags-after.txt"

sha256sum "$ORCH/app.py" "$ORCH"/attendance_capture_*.py | tee "$REMOTE_EVID/verify/post-deploy-shas.txt"
if [[ -f "$DASH_DIST/index.html" ]]; then
  sha256sum "$DASH_DIST/index.html" | tee -a "$REMOTE_EVID/verify/post-deploy-shas.txt"
fi

cd "$ORCH"
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/verify/post-deploy-gates.txt"
import app
assert app.attendance_authority_enabled() is True
assert app.attendance_authority_synthetic_only() is True
assert app.attendance_import_enabled() is False
assert app.attendance_capture_ops_enabled() is True
assert app.attendance_capture_ops_enabled_for_company("WATHEFNI") is True
assert app.attendance_capture_ingest_enabled() is False
print("gates_ok")
PY

echo DEPLOY_OK REMOTE_EVID=$REMOTE_EVID BACKUP=$BACKUP
