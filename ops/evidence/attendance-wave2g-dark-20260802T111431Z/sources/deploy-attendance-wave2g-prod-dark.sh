#!/usr/bin/env bash
# Attendance Wave 2G — production DARK persistence deploy.
# Deploys Wave 2F durable capture-ops (Postgres) with CAPTURE_INGEST=off.
# Never connects a customer device or enables real punch channels.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-attendance-wave2g-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-wave2g-dark/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/attw2g-stage}"
DROPIN_2E=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2e-capture-ops-dark.conf
DROPIN_2G=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2g-capture-store-postgres.conf
DROPIN_2C=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
DASH_DIST=/opt/wathefni/dashboard-dist
SECRETS=/root/.openclaw/secrets/attendance-capture.env
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,canary,backup,schema,privacy,cleanup,ui,tests,rollback} "$BACKUP" "$STAGE"

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
  sha256sum "$ORCH/app.py" "$ORCH"/attendance_authority_*.py "$ORCH"/attendance_capture_*.py 2>/dev/null || true
  echo "=== flags before ==="
  load_service_env
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'ATTENDANCE|DB_POOL|IMPORT|CAPTURE' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort || true
  echo "=== capture_store before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep CAPTURE_STORE || echo "CAPTURE_STORE_unset (process-local memory expected)"
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
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=cur.fetchone()["db"]; assert db=="wathefni"
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'"); n=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'"); demo=int(cur.fetchone()["n"])
        import attendance_authority_wave1 as core
        cur.execute("SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)", (list(core.FOUR_REAL_ATTENDANCE_KEYS),))
        four=int(cur.fetchone()["n"])
print(json.dumps({"db":db,"wathefni_rows":n,"demo_seed":demo,"four_reals":four}, indent=2))
assert n==42 and demo==42 and four==4
PY

"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/capture-store-mode-before.json"
import json, os
print(json.dumps({
  "capture_store_env": os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_STORE"),
  "process_local_expected": not (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_STORE") or "").strip(),
  "note": "pre-deploy: Wave 2E process-local memory (CAPTURE_STORE unset)",
}, indent=2))
PY

log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
mkdir -p "$BACKUP/capture_modules" "$BACKUP/dashboard-dist" "$BACKUP/ops"
for f in "$ORCH"/attendance_capture_*.py "$ORCH"/attendance_authority_*.py; do
  [[ -f "$f" ]] && cp -a "$f" "$BACKUP/capture_modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins"
if [[ -d "$DASH_DIST" ]]; then
  rsync -a --delete "$DASH_DIST/" "$BACKUP/dashboard-dist/" || true
fi
sudo -u postgres psql -d wathefni -c "COPY (SELECT attendance_id, employee_key, status, metadata->>'demo_seed' AS demo_seed FROM attendance_records WHERE company_code='WATHEFNI' ORDER BY attendance_id) TO STDOUT WITH CSV HEADER" > "$BACKUP/attendance-records-fingerprint.csv"
sha256sum "$BACKUP/app.py" "$BACKUP/attendance-records-fingerprint.csv" | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

if [[ ! -f "$SECRETS" ]]; then
  echo "REFUSE: missing $SECRETS (Wave 2E should have provisioned Fernet key)" >&2
  exit 3
fi
{
  echo "secrets_path=$SECRETS"
  echo "secrets_mode=$(stat -c %a "$SECRETS")"
  echo "credential_key_absent_from_evidence=true"
} | tee "$REMOTE_EVID/privacy/secrets-provisioned.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN_2G=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2g-capture-store-postgres.conf
PYBIN="$ORCH/.venv/bin/python"
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
if [[ -d "$BACKUP_DIR/capture_modules" ]]; then
  # restore modules that existed; remove wave2g-only postgres module if rolled back to pre-2G
  cp -a "$BACKUP_DIR/capture_modules"/. "$ORCH/" || true
  if [[ ! -f "$BACKUP_DIR/capture_modules/attendance_capture_postgres.py" ]]; then
    rm -f "$ORCH/attendance_capture_postgres.py"
  fi
fi
rm -f "$DROPIN_2G"
# Drop Wave 2G tables if present (inline; works even after module restore removes postgres helper)
"$PYBIN" - <<'SQL' || true
import sys
sys.path.insert(0, "/opt/wathefni/orchestrator")
import app
DDL = """
DROP TRIGGER IF EXISTS trg_att_cap_audit_immutable ON attendance_capture_audit_events;
DROP TRIGGER IF EXISTS trg_att_cap_replay_immutable ON attendance_capture_replay_ledger;
DROP FUNCTION IF EXISTS attendance_capture_audit_forbid_mutation();
DROP FUNCTION IF EXISTS attendance_capture_replay_forbid_mutation();
DROP TABLE IF EXISTS attendance_capture_replay_ledger CASCADE;
DROP TABLE IF EXISTS attendance_capture_audit_events CASCADE;
DROP TABLE IF EXISTS attendance_capture_idempotency CASCADE;
DROP TABLE IF EXISTS attendance_capture_remediation CASCADE;
DROP TABLE IF EXISTS attendance_capture_quarantine CASCADE;
DROP TABLE IF EXISTS attendance_capture_mappings CASCADE;
DROP TABLE IF EXISTS attendance_capture_checkpoints CASCADE;
DROP TABLE IF EXISTS attendance_capture_health_events CASCADE;
DROP TABLE IF EXISTS attendance_capture_health CASCADE;
DROP TABLE IF EXISTS attendance_capture_credentials CASCADE;
DROP TABLE IF EXISTS attendance_capture_connectors CASCADE;
DROP TABLE IF EXISTS attendance_capture_devices CASCADE;
DROP TABLE IF EXISTS attendance_capture_sites CASCADE;
"""
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
        cur.execute(DDL)
    conn.commit()
print("SCHEMA_DROP_OK")
SQL
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 30); do
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
cp -a "$STAGE"/attendance_capture_postgres.py "$ORCH/"
cp -a "$STAGE"/attendance_capture_ops.py "$ORCH/"
cp -a "$STAGE"/attendance_capture_ops_http.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/attendance_capture_secrets.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/attendance_capture_registry.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/attendance_capture_remediation.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/attendance_capture_health.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/attendance_capture_pipeline.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/attendance_capture_contract.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/attendance_capture_agent.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/canary-prod-attendance-wave2g.py "$ORCH/"
cp -a "$STAGE"/smoke-test-attendance-capture-wave2f.py "$ORCH/" 2>/dev/null || true
mkdir -p "$ORCH/ops"
cp -a "$STAGE"/migrate-attendance-capture-wave2g-prod.sh "$ORCH/ops/"
cp -a "$STAGE"/rollback-attendance-capture-wave2g-prod.sh "$ORCH/ops/"
chmod +x "$ORCH/ops"/migrate-attendance-capture-wave2g-prod.sh "$ORCH/ops"/rollback-attendance-capture-wave2g-prod.sh

# Surgical app.py schema ensure (do not replace entire app.py)
"$PYBIN" - <<'PATCH' | tee "$REMOTE_EVID/schema/app-patch.txt"
from pathlib import Path
p = Path("/opt/wathefni/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
if "attendance_capture_postgres" in text:
    print("APP_ALREADY_HAS_WAVE2F_SCHEMA")
else:
    old = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
        conn.commit()"""
    new = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
            # Wave 2G additive capture-ops tables (dark; CAPTURE_STORE=postgres).
            try:
                import attendance_capture_postgres as _attendance_capture_pg

                _attendance_capture_pg.ensure_attendance_capture_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
    if old not in text:
        raise SystemExit("app.py schema hook site not found")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("APP_PATCHED_WAVE2G_SCHEMA")
PATCH

# Dashboard dist (prebuilt Capture Ops UI) — production
if [[ -d "$STAGE/dashboard-dist" ]]; then
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
fi

# Keep 2E capture-ops dark flags; add 2G durable store
if [[ ! -f "$DROPIN_2E" ]]; then
  cat > "$DROPIN_2E" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_CAPTURE_OPS=on
Environment=WATHEFNI_ATTENDANCE_CAPTURE_OPS_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ATTENDANCE_IMPORT=off
EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env
EOF
fi

cat > "$DROPIN_2G" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env
EOF

# Extend synthetic markers for Wave 2G
if [[ -f "$DROPIN_2C" ]]; then
  if ! grep -q 'ATTW2G' "$DROPIN_2C"; then
    sed -i 's/ATTW2E,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|/ATTW2E,ATTW2G,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|,W2G-SYNTH|/' "$DROPIN_2C" || true
  fi
  if ! grep -q 'W2G-SYNTH' "$DROPIN_2C"; then
    sed -i 's/W2E-SYNTH|/W2E-SYNTH|,W2G-SYNTH|/' "$DROPIN_2C" || true
  fi
fi

log "migrate schema"
export ACK_PRODUCTION_CAPTURE_PERSISTENCE=1
export ACK_DB=wathefni
ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-attendance-capture-wave2g-prod.sh" 2>&1 | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 40); do
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

sha256sum "$ORCH/app.py" "$ORCH"/attendance_capture_*.py "$ORCH"/canary-prod-attendance-wave2g.py | tee "$REMOTE_EVID/verify/post-deploy-shas.txt"
if [[ -f "$DASH_DIST/index.html" ]]; then
  sha256sum "$DASH_DIST/index.html" | tee -a "$REMOTE_EVID/verify/post-deploy-shas.txt"
fi

cd "$ORCH"
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/verify/post-deploy-gates.txt"
import app, attendance_capture_ops as ops
ops.reset_capture_ops_for_tests()
assert app.attendance_authority_enabled() is True
assert app.attendance_authority_synthetic_only() is True
assert app.attendance_import_enabled() is False
assert app.attendance_capture_ops_enabled() is True
assert app.attendance_capture_ops_enabled_for_company("WATHEFNI") is True
assert app.attendance_capture_ingest_enabled() is False
assert ops.capture_store_mode() == "postgres"
print("gates_ok store=postgres ingest=off")
PY

echo DEPLOY_OK REMOTE_EVID=$REMOTE_EVID BACKUP=$BACKUP
