#!/usr/bin/env bash
# Attendance final — production WATHEFNI synthetic UX promote + freeze deploy.
# Promotes Wave 4B dashboard UX. Keeps CAPTURE_INGEST=off, synthetic-only authority/ops.
# No devices, QR, GPS, kiosk, real clocking, or real payroll money impact.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
WWW=/var/www/wathefni-dashboard
BACKUP="/opt/wathefni/backups/production-pre-attendance-final-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-final/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/attw-final-stage}"
# zzz- so this wins over zz-attendance-wave* drop-ins that also set SYNTHETIC_KEY_MARKERS
DROPIN_FINAL=/etc/systemd/system/wathefni-orchestrator.service.d/zzz-attendance-final-freeze.conf
DROPIN_FINAL_LEGACY=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-final-freeze.conf
DROPIN_W3=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave3-ops-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,dashboard,privacy} "$BACKUP"/{modules,dashboard-dist,systemd-dropins}

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

load_service_env() {
  local PID
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  while IFS= read -r -d '' line; do
    case "$line" in WATHEFNI_*=*) export "$line" ;; esac
  done < /proc/"$PID"/environ
}

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH"/attendance_ops_*.py "$ORCH"/attendance_authority_*.py "$ORCH"/attendance_capture_ops*.py 2>/dev/null || true
  ls "$WWW/assets"/PostHire-*.js 2>/dev/null | while read -r f; do sha256sum "$f"; done
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ATTENDANCE|CAPTURE|IMPORT|OPS' \
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
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/attendance-counts-before.json"
import json, app
import attendance_authority_wave1 as core
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=cur.fetchone()["db"]; assert db=="wathefni"
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'"); n=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'"); demo=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)", (list(core.FOUR_REAL_ATTENDANCE_KEYS),))
        four=int(cur.fetchone()["n"])
print(json.dumps({"db":db,"wathefni_rows":n,"demo_seed":demo,"four_reals":four}, indent=2))
assert n==42 and demo==42 and four==4
PY

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must be off" >&2
  exit 3
fi

log "backing up orchestrator + dashboard + dropins"
cp -a "$ORCH/app.py" "$BACKUP/app.py" 2>/dev/null || true
for f in "$ORCH"/attendance_ops_*.py "$ORCH"/attendance_authority_*.py "$ORCH"/attendance_capture_ops*.py; do
  [[ -f "$f" ]] && cp -a "$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" || true
if [[ -d "$WWW" ]]; then
  rsync -a "$WWW/" "$BACKUP/dashboard-dist/"
fi
sudo -u postgres psql -d wathefni -c "COPY (SELECT attendance_id, employee_key, status, metadata->>'demo_seed' AS demo_seed FROM attendance_records WHERE company_code='WATHEFNI' ORDER BY attendance_id) TO STDOUT WITH CSV HEADER" > "$BACKUP/attendance-records-fingerprint.csv"
(
  cd "$BACKUP"
  find modules dashboard-dist -type f 2>/dev/null | head -5 >/dev/null || true
  sha256sum app.py attendance-records-fingerprint.csv 2>/dev/null || true
  ls dashboard-dist/assets/PostHire-*.js 2>/dev/null | while read -r f; do sha256sum "$f"; done
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
WWW=/var/www/wathefni-dashboard
DROPIN_FINAL=/etc/systemd/system/wathefni-orchestrator.service.d/zzz-attendance-final-freeze.conf
DROPIN_FINAL_LEGACY=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-final-freeze.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ -d "$BACKUP_DIR/modules" ]]; then cp -a "$BACKUP_DIR/modules"/. "$ORCH/" || true; fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -d "$WWW" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$WWW/"
fi
rm -f "$DROPIN_FINAL" "$DROPIN_FINAL_LEGACY"
# Restore prior dropins if snapshot present
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying orchestrator modules"
for f in attendance_ops_wave3.py attendance_ops_postgres.py attendance_ops_http.py \
         attendance_authority_wave1.py attendance_authority_postgres.py \
         seed-and-prove-attendance-wave4b.py canary-prod-attendance-final.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py; do
  if [[ -f "$STAGE/$f" ]]; then cp -a "$STAGE/$f" "$ORCH/"; fi
done
# Freeze authority docs for regression gates on the VPS
mkdir -p /opt/wathefni/ops
if [[ -f "$STAGE/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" ]]; then
  cp -a "$STAGE/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" /opt/wathefni/ops/
fi
# Keep Wave 3 dropin; add final freeze dropin (ingest off, synthetic-only reinforced)
rm -f "$DROPIN_FINAL_LEGACY"
cat > "$DROPIN_FINAL" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_OPS=on
Environment=WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_OPS_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY=on
Environment=WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ATTENDANCE_IMPORT=off
Environment=WATHEFNI_ATTENDANCE_AUTHORITY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,ATTW2E,ATTW2G,ATTW3,ATTW4B,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|,W2G-SYNTH|,W3-SYNTH|
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
EOF
cp -a "$DROPIN_FINAL" "$REMOTE_EVID/flags/"
# Ensure wave3 dropin still has ingest off
if [[ -f "$DROPIN_W3" ]] && ! grep -q 'CAPTURE_INGEST=off' "$DROPIN_W3"; then
  echo 'Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off' >> "$DROPIN_W3"
fi

log "promoting dashboard dist"
test -d "$STAGE/dashboard-dist"
test -f "$STAGE/dashboard-dist/index.html"
rsync -a --delete "$STAGE/dashboard-dist/" "$WWW/"
ls "$WWW/assets"/PostHire-*.js | while read -r f; do sha256sum "$f"; done | tee "$REMOTE_EVID/dashboard/posthire-sha.txt"
# Bundle markers
CHUNK=$(ls "$WWW/assets"/PostHire-*.js | head -1)
{
  echo "chunk=$CHUNK"
  for needle in "Attendance operations" "عمليات الحضور" "Connector health" "Day detail" "Approved — ready to apply"; do
    if grep -qF "$needle" "$CHUNK"; then echo "FOUND $needle"; else echo "MISSING $needle"; fi
  done
} | tee "$REMOTE_EVID/dashboard/bundle-markers.txt"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 90); do
  if curl -sf http://127.0.0.1:8010/health >/dev/null; then break; fi
  sleep 1
done
curl -sf http://127.0.0.1:8010/health | tee "$REMOTE_EVID/verify/health-after-restart.json"

{
  echo "=== flags after ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ATTENDANCE|CAPTURE|IMPORT|OPS' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

if tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -qiE '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=(on|true|1|yes)$'; then
  echo "REFUSE: ingest enabled after deploy" >&2
  exit 4
fi
if ! tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -qiE '^WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY=(on|true|1|yes)$'; then
  echo "REFUSE: OPS_SYNTHETIC_ONLY must be on" >&2
  exit 5
fi
if ! tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -qiE '^WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=(on|true|1|yes)$'; then
  echo "REFUSE: AUTHORITY_SYNTHETIC_ONLY must be on" >&2
  exit 6
fi

"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/attendance-counts-after-deploy.json"
import json, app
import attendance_authority_wave1 as core
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'"); n=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'"); demo=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)", (list(core.FOUR_REAL_ATTENDANCE_KEYS),))
        four=int(cur.fetchone()["n"])
print(json.dumps({"wathefni_rows":n,"demo_seed":demo,"four_reals":four}, indent=2))
assert n==42 and demo==42 and four==4
PY

sudo -u postgres psql -d wathefni -c "\dt attendance*" > "$REMOTE_EVID/schema/attendance-tables.txt" || true
sha256sum "$ORCH"/attendance_ops_wave3.py "$ORCH"/attendance_authority_wave1.py \
  "$WWW"/assets/PostHire-*.js 2>/dev/null | tee "$REMOTE_EVID/verify/shas-after.txt"

echo "DEPLOY_OK stamp=$STAMP"
