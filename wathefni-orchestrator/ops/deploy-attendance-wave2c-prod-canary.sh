#!/usr/bin/env bash
# Attendance Wave 2C — production synthetic BioTime connector canary deploy.
# Deploys capture stack + updated authority sources allowlist.
# Lab BioTime fixture only. Keeps IMPORT off. No real devices / clocking / QR/GPS/kiosk.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-attendance-wave2c-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-wave2c-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/attw2c-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
# Keep 1C dropin removed when 2C dropin supersedes both flag sets
DROPIN_1C=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave1c-synthetic-canary.conf

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,canary,backup,schema,privacy,cleanup,reconcile} "$BACKUP" "$STAGE"

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

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH"/attendance_authority_*.py 2>/dev/null || true
  ls -la "$ORCH"/attendance_capture_*.py 2>&1 || true
  echo "=== flags before ==="
  load_service_env
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -E 'ATTENDANCE|DB_POOL|IMPORT|CAPTURE' | sort || true
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
        cur.execute("SELECT to_regclass('attendance_punches') AS r"); punches=cur.fetchone()["r"]
print(json.dumps({"db":db,"wathefni_rows":n,"demo_seed":demo,"punches_table":punches}, indent=2))
assert n==42 and demo==42
PY

log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/attendance_authority_wave1.py" "$BACKUP/attendance_authority_wave1.py"
cp -a "$ORCH/attendance_authority_postgres.py" "$BACKUP/attendance_authority_postgres.py" 2>/dev/null || true
cp -a "$ORCH/attendance_authority_hooks.py" "$BACKUP/attendance_authority_hooks.py" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins"
sudo -u postgres psql -d wathefni -c "COPY (SELECT attendance_id, employee_key, status, metadata->>'demo_seed' AS demo_seed FROM attendance_records WHERE company_code='WATHEFNI' ORDER BY attendance_id) TO STDOUT WITH CSV HEADER" > "$BACKUP/attendance-records-fingerprint.csv"
sha256sum "$BACKUP/app.py" "$BACKUP/attendance_authority_wave1.py" "$BACKUP/attendance-records-fingerprint.csv" | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

# Credential key (never copied into evidence plaintext beyond path note)
SECRETS=/root/.openclaw/secrets/attendance-capture.env
if [[ ! -f "$SECRETS" ]]; then
  KEY=$(.venv/bin/python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)
  umask 077
  cat > "$SECRETS" <<EOF
WATHEFNI_CAPTURE_CREDENTIAL_KEY=${KEY}
EOF
  chmod 600 "$SECRETS"
fi
echo "secrets_path=$SECRETS" > "$REMOTE_EVID/privacy/secrets-provisioned.txt"
echo "secrets_mode=$(stat -c %a "$SECRETS")" >> "$REMOTE_EVID/privacy/secrets-provisioned.txt"
# Prove key not in evidence dir
if grep -R "WATHEFNI_CAPTURE_CREDENTIAL_KEY=.\+" "$REMOTE_EVID" 2>/dev/null; then
  echo "REFUSE: credential key leaked into evidence" >&2
  exit 3
fi
echo "credential_key_absent_from_evidence=true" >> "$REMOTE_EVID/privacy/secrets-provisioned.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/attendance_authority_wave1.py" "$ORCH/attendance_authority_wave1.py"
cp -a "$BACKUP_DIR/attendance_authority_postgres.py" "$ORCH/attendance_authority_postgres.py" 2>/dev/null || true
cp -a "$BACKUP_DIR/attendance_authority_hooks.py" "$ORCH/attendance_authority_hooks.py" 2>/dev/null || true
rm -f "$ORCH"/attendance_capture_*.py "$ORCH"/canary-prod-attendance-wave2c.py "$ORCH"/attendance_capture_lab_biotime.py
rm -f "$DROPIN"
# restore prior dropins directory snapshot if present
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  rm -f /etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
  # restore 1C dropin from backup snapshot if it existed
  if [[ -f "$BACKUP_DIR/systemd-dropins/zz-attendance-wave1c-synthetic-canary.conf" ]]; then
    cp -a "$BACKUP_DIR/systemd-dropins/zz-attendance-wave1c-synthetic-canary.conf" /etc/systemd/system/wathefni-orchestrator.service.d/
  fi
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
cp -a "$STAGE"/attendance_authority_wave1.py "$ORCH/"
cp -a "$STAGE"/attendance_capture_*.py "$ORCH/"
cp -a "$STAGE"/canary-prod-attendance-wave2c.py "$ORCH/"
# ensure biotime sources present
grep -q '"biotime"' "$ORCH/attendance_authority_wave1.py"
grep -q 'ATTW2C' "$ORCH/attendance_authority_wave1.py"

# Supersede 1C dropin with 2C (includes 1C flags + markers)
rm -f "$DROPIN_1C"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_AUTHORITY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,W1C-SYNTH|,W2C-SYNTH|
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_IMPORT=off
Environment=WATHEFNI_DB_POOL_MAX=8
EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env
EOF

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8010/health | tee "$REMOTE_EVID/verify/health-after-deploy.json"; echo

load_service_env
{
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ATTENDANCE|DB_POOL|CAPTURE' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort
} | tee "$REMOTE_EVID/flags/prod-flags-after.txt"
sha256sum "$ORCH/app.py" "$ORCH/attendance_authority_wave1.py" "$ORCH"/attendance_capture_*.py | tee "$REMOTE_EVID/verify/post-deploy-shas.txt"

cd "$ORCH"
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/verify/post-deploy-gates.txt"
import app, attendance_authority_wave1 as core
assert app.attendance_authority_enabled() is True
assert app.attendance_authority_synthetic_only() is True
assert app.attendance_import_enabled() is False
assert core.attendance_authority_allowed_for("WATHEFNI", {"employee_key":"WATHEFNI-96550252254","phone":"96550252254"}) is False
assert core.attendance_authority_allowed_for("WATHEFNI", {"employee_key":"WATHEFNI-ATTW2C-deadbeef","phone":"965524deadbe"}) is True
assert "biotime" in core.PUNCH_SOURCES
print("gates_ok")
PY

echo DEPLOY_OK REMOTE_EVID=$REMOTE_EVID BACKUP=$BACKUP
