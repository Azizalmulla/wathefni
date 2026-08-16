#!/usr/bin/env bash
# Attendance Wave 3 — production WATHEFNI-only synthetic ops canary deploy.
# Enables OPS with synthetic-only; keeps CAPTURE_INGEST=off.
# No devices, no real clocking, no UI redesign, no external tenants.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-attendance-wave3-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-wave3-synthetic/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/attw3-stage}"
DROPIN_W3=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave3-ops-synthetic.conf
DROPIN_2C=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2c-synthetic-canary.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,canary,backup,schema,privacy,cleanup,tests} "$BACKUP" "$STAGE"

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
  sha256sum "$ORCH/app.py" "$ORCH"/attendance_authority_*.py "$ORCH"/attendance_ops_*.py 2>/dev/null || true
  echo "=== flags before ==="
  load_service_env
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

# Ingest must already be off
INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must be off before Wave 3 deploy" >&2
  exit 3
fi

log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
mkdir -p "$BACKUP/modules" "$BACKUP/ops"
for f in "$ORCH"/attendance_authority_*.py "$ORCH"/attendance_ops_*.py; do
  [[ -f "$f" ]] && cp -a "$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins"
sudo -u postgres psql -d wathefni -c "COPY (SELECT attendance_id, employee_key, status, metadata->>'demo_seed' AS demo_seed FROM attendance_records WHERE company_code='WATHEFNI' ORDER BY attendance_id) TO STDOUT WITH CSV HEADER" > "$BACKUP/attendance-records-fingerprint.csv"
sha256sum "$BACKUP/app.py" "$BACKUP/attendance-records-fingerprint.csv" | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN_W3=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave3-ops-synthetic.conf
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" || true
fi
rm -f "$DROPIN_W3"
# Keep ops tables (empty synthetic leftover ok); do not drop schema on rollback by default
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying modules"
cp -a "$STAGE"/attendance_ops_wave3.py "$ORCH/"
cp -a "$STAGE"/attendance_ops_postgres.py "$ORCH/"
cp -a "$STAGE"/attendance_ops_http.py "$ORCH/"
cp -a "$STAGE"/attendance_authority_wave1.py "$ORCH/"
cp -a "$STAGE"/attendance_authority_postgres.py "$ORCH/" 2>/dev/null || true
cp -a "$STAGE"/canary-prod-attendance-wave3.py "$ORCH/"
mkdir -p "$ORCH/ops"
cp -a "$STAGE"/migrate-attendance-ops-wave3-prod.sh "$ORCH/ops/"
chmod +x "$ORCH/ops"/migrate-attendance-ops-wave3-prod.sh

# Surgical app.py patches
"$PYBIN" - <<'PATCH' | tee "$REMOTE_EVID/schema/app-patch.txt"
from pathlib import Path
p = Path("/opt/wathefni/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
changed = False
if "ensure_attendance_ops_postgres_schema" not in text:
    old = """            try:
                import attendance_capture_postgres as _attendance_capture_pg

                _attendance_capture_pg.ensure_attendance_capture_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
    new = """            try:
                import attendance_capture_postgres as _attendance_capture_pg

                _attendance_capture_pg.ensure_attendance_capture_postgres_schema(cur)
            except Exception:
                pass
            try:
                import attendance_ops_postgres as _attendance_ops_pg

                _attendance_ops_pg.ensure_attendance_ops_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
    if old not in text:
        old2 = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
        conn.commit()"""
        new2 = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
            try:
                import attendance_ops_postgres as _attendance_ops_pg

                _attendance_ops_pg.ensure_attendance_ops_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
        if old2 not in text:
            raise SystemExit("app.py schema hook site not found")
        text = text.replace(old2, new2, 1)
    else:
        text = text.replace(old, new, 1)
    changed = True
    print("APP_PATCHED_WAVE3_SCHEMA")
else:
    print("APP_ALREADY_HAS_WAVE3_SCHEMA")

if "register_attendance_ops_routes" not in text:
    end = text.find("\n\n\nLEAVE_HISTORY_STATUSES")
    if end < 0:
        end = text.find("\nLEAVE_HISTORY_STATUSES")
    if end < 0:
        raise SystemExit("LEAVE_HISTORY_STATUSES anchor not found")
    if "register_attendance_capture_ops_routes" not in text[:end]:
        # insert after capture block if present elsewhere, else before LEAVE_HISTORY
        pass
    insert = '''

# --- Attendance Wave 3: HR/manager exception + correction ops (synthetic canary; no real clocking) ---
from attendance_ops_http import register_attendance_ops_routes


def _ops_payroll_date_locked(company: str, employee_key: str, work_date):
    with db_connect() as conn:
        with conn.cursor() as cur:
            return _ai_date_locked(cur, company, employee_key, work_date)


def _ops_manager_is_configured(company: str, actor_phone: str) -> bool:
    scope = manager_scope_context(actor_phone, company)
    if not scope.get("restricted"):
        return True
    return not bool(scope.get("configuration_error"))


register_attendance_ops_routes(
    app,
    Depends=Depends,
    dashboard_context=dashboard_context,
    require_entitlement=require_entitlement,
    manager_scope_allows_employee=manager_scope_allows_employee,
    context_manager_allows_employee=context_manager_allows_employee,
    record_admin_audit=record_admin_audit,
    digits=digits,
    json_safe=json_safe,
    get_employee=_capture_ops_get_employee,
    payroll_date_locked=_ops_payroll_date_locked,
    manager_is_configured=_ops_manager_is_configured,
    manager_scope_employee_keys=manager_scope_employee_keys,
)


'''
    text = text[:end] + insert + text[end:]
    changed = True
    print("APP_PATCHED_WAVE3_ROUTES")
else:
    print("APP_ALREADY_HAS_WAVE3_ROUTES")

if changed:
    p.write_text(text, encoding="utf-8")
print("app.py wave3 hooks ok")
PATCH

# Extend synthetic markers
if [[ -f "$DROPIN_2C" ]]; then
  if ! grep -q 'ATTW3' "$DROPIN_2C"; then
    sed -i 's/W2G-SYNTH|/W2G-SYNTH|,ATTW3,W3-SYNTH|/' "$DROPIN_2C" || true
  fi
fi

cat > "$DROPIN_W3" <<EOF
[Service]
Environment=WATHEFNI_ATTENDANCE_OPS=on
Environment=WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_OPS_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY=on
Environment=WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ATTENDANCE_IMPORT=off
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,ATTW2E,ATTW2G,ATTW3,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|,W2G-SYNTH|,W3-SYNTH|
EOF
echo "wrote $DROPIN_W3" | tee "$REMOTE_EVID/flags/dropin.txt"
cp -a "$DROPIN_W3" "$REMOTE_EVID/flags/"

export ACK_PRODUCTION_ATTENDANCE_OPS_WAVE3=1
export ACK_DB=wathefni
ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-attendance-ops-wave3-prod.sh" 2>&1 | tee "$REMOTE_EVID/schema/migrate.out"

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

# Hard assert ingest still off
if tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -qiE '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=(on|true|1|yes)$'; then
  echo "REFUSE: ingest enabled after deploy" >&2
  exit 4
fi
echo "DEPLOY_OK stamp=$STAMP"
