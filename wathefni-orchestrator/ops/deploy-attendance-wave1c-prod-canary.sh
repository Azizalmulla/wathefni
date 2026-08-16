#!/usr/bin/env bash
# Attendance Wave 1C — production synthetic canary deploy.
# Deploys authority modules + surgically patched app.py.
# Enables AUTHORITY only for WATHEFNI + SYNTHETIC_ONLY + postgres store.
# Keeps ATTENDANCE_IMPORT off. Does not enable real clocking/QR/GPS/kiosk.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-attendance-wave1c-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-wave1c-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/attw1c-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave1c-synthetic-canary.conf

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,canary,backup,schema} "$BACKUP"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/attendance_import.py"
  ls -la "$ORCH"/attendance_authority*.py 2>&1 || true
  echo "=== flags before ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ATTENDANCE|ONBOARDING_SEED|EMPLOYEE_APP|DB_POOL' | sort || true
} | tee "$REMOTE_EVID/preflight/before-deploy.txt"

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
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
        cur.execute("SELECT current_database() AS db")
        db = cur.fetchone()["db"]
        assert db == "wathefni"
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
        n = int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'")
        demo = int(cur.fetchone()["n"])
        cur.execute("SELECT to_regclass('attendance_punches') AS r")
        punches = cur.fetchone()["r"]
print(json.dumps({"db": db, "wathefni_rows": n, "demo_seed": demo, "punches_table": punches}, indent=2))
assert n == 42 and demo == 42
PY

# --- backup ---
log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/attendance_import.py" "$BACKUP/attendance_import.py" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
# pg_dump schema-only for attendance* + data for attendance_records fingerprint
sudo -u postgres pg_dump -d wathefni --schema-only -t 'attendance_*' > "$BACKUP/attendance-schema-before.sql" || true
sudo -u postgres psql -d wathefni -c "COPY (SELECT attendance_id, employee_key, status, metadata->>'demo_seed' AS demo_seed FROM attendance_records WHERE company_code='WATHEFNI' ORDER BY attendance_id) TO STDOUT WITH CSV HEADER" > "$BACKUP/attendance-records-fingerprint.csv"
sha256sum "$BACKUP/app.py" "$BACKUP/attendance-records-fingerprint.csv" | tee "$BACKUP/SHA256SUMS"
if [[ -f "$BACKUP/attendance_import.py" ]]; then
  sha256sum "$BACKUP/attendance_import.py" | tee -a "$BACKUP/SHA256SUMS"
fi
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave1c-synthetic-canary.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/attendance_import.py" "$ORCH/attendance_import.py" 2>/dev/null || true
rm -f "$ORCH/attendance_authority_wave1.py" "$ORCH/attendance_authority_postgres.py" "$ORCH/attendance_authority_hooks.py" "$ORCH/canary-prod-attendance-wave1c.py"
rm -f "$DROPIN"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"
cp -a "$BACKUP/SHA256SUMS" "$REMOTE_EVID/backup/SHA256SUMS"

# --- deploy modules + patched app ---
log "deploying modules"
test -f "$STAGE/app.patched.py"
test -f "$STAGE/attendance_authority_wave1.py"
test -f "$STAGE/attendance_authority_postgres.py"
test -f "$STAGE/attendance_authority_hooks.py"
test -f "$STAGE/canary-prod-attendance-wave1c.py"
cp -a "$STAGE/app.patched.py" "$ORCH/app.py"
cp -a "$STAGE/attendance_authority_wave1.py" "$ORCH/"
cp -a "$STAGE/attendance_authority_postgres.py" "$ORCH/"
cp -a "$STAGE/attendance_authority_hooks.py" "$ORCH/"
cp -a "$STAGE/canary-prod-attendance-wave1c.py" "$ORCH/"

# Conservative pool + synthetic-only flags
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_AUTHORITY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,W1C-SYNTH|
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_IMPORT=off
Environment=WATHEFNI_DB_POOL_MAX=8
EOF

systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 4
curl -fsS http://127.0.0.1:8010/health | tee "$REMOTE_EVID/verify/health-after-deploy.json"
echo

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/attendance_authority_wave1.py" "$ORCH/attendance_authority_postgres.py" "$ORCH/attendance_authority_hooks.py"
  echo "=== flags after (process) ==="
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ATTENDANCE|DB_POOL|ONBOARDING_SEED|EMPLOYEE_APP_REAL' | sort
} | tee "$REMOTE_EVID/flags/prod-flags-after.txt"

# Load process env into shell for schema + canary
while IFS= read -r -d '' line; do
  case "$line" in
    WATHEFNI_*=*) export "$line" ;;
  esac
done < /proc/"$PID"/environ

cd "$ORCH"
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/schema/schema-after.txt"
import app, attendance_authority_hooks as hooks
assert app.attendance_authority_enabled() is True
assert app.attendance_authority_companies() == {"WATHEFNI"}
assert app.attendance_authority_synthetic_only() is True
assert app.attendance_authority_allowed_for("WATHEFNI", {"employee_key":"WATHEFNI-96550252254","phone":"96550252254"}) is False
assert app.attendance_authority_allowed_for("WATHEFNI", {"employee_key":"WATHEFNI-ATTW1C-TEST","phone":"965524000001"}) is True
with app.db_connect() as conn:
    with conn.cursor() as cur:
        hooks.ensure_schema(cur)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public' AND tablename LIKE 'attendance_%'
          ORDER BY 1
        """)
        print("tables", [r["tablename"] for r in cur.fetchall()])
        cur.execute("""
          SELECT tgname FROM pg_trigger
          WHERE tgname LIKE 'trg_attendance_%'
          ORDER BY 1
        """)
        print("triggers", [r["tgname"] for r in cur.fetchall()])
    conn.commit()
print("schema_ok")
PY

# Prove rollback script exists and is executable (dry listing)
test -x "$BACKUP/ROLLBACK.sh"
echo "rollback_script_ready=true" | tee "$REMOTE_EVID/backup/rollback-ready.txt"

# Run canary
export WAVE1C_CANARY_OUT="$REMOTE_EVID/canary"
.venv/bin/python canary-prod-attendance-wave1c.py 2>&1 | tee "$REMOTE_EVID/canary/out.txt"
grep -q 'fail=0' "$REMOTE_EVID/canary/out.txt"

# Freeze regressions (offline)
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$REMOTE_EVID/verify/e360-freeze.txt"
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$REMOTE_EVID/verify/onboarding-freeze.txt"
grep -E 'passed, 0 failed|SUMMARY pass=.*fail=0' "$REMOTE_EVID/verify/e360-freeze.txt" "$REMOTE_EVID/verify/onboarding-freeze.txt" || true

# Post counts
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/verify/attendance-counts-after.json"
import json, app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
        n=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'")
        demo=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_punches")
        punches=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_day_projections WHERE employee_key LIKE 'WATHEFNI-ATTW1C-%'")
        synth=int(cur.fetchone()["n"])
print(json.dumps({"wathefni_rows":n,"demo_seed":demo,"punches_total":punches,"synth_projections_left":synth}, indent=2))
assert n==42 and demo==42 and synth==0
PY

echo DEPLOY_CANARY_OK
echo REMOTE_EVID=$REMOTE_EVID
echo BACKUP=$BACKUP
