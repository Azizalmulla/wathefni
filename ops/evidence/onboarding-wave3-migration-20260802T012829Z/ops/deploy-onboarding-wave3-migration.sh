#!/usr/bin/env bash
# Onboarding Wave 3 — deploy migration module + count fix; run controlled migration.
# Does NOT enable SEED/HR_MUTATE. Migration gate is process-local to the runner.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-onboarding-wave3-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/onboarding-wave3-migration/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/onboarding-wave3-stage}"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,tests,migration,backup} "$BACKUP"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  sha256sum "$ORCH/app.py" "$ORCH/onboarding_wave2.py"
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ONBOARDING|EMPLOYEE_APP' | sort
} | tee "$REMOTE_EVID/preflight/before.txt"

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
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in
    WATHEFNI_*=*) export "$line" ;;
  esac
done < /proc/"$PID"/environ

.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/preflight/fingerprint-before.json"
import json, hashlib, app
KEYS=["WATHEFNI-96550252254","WATHEFNI-96566363363","WATHEFNI-96597727743","WATHEFNI-96599411617"]
app.ensure_schema()
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("""
      SELECT oi.employee_key, oi.item_id, oi.required, oi.status, oi.value, oi.reminder_count,
             oi.label, e.name
      FROM onboarding_items oi JOIN employees e ON e.employee_key=oi.employee_key
      WHERE e.company_code='WATHEFNI' AND oi.employee_key=ANY(%s)
      ORDER BY oi.employee_key, oi.item_id
    """, (KEYS,))
    rows=[dict(r) for r in cur.fetchall()]
def fp(r):
  v=r.get("value"); vs="" if v is None else str(v)
  req="True" if r.get("required") is True else ("False" if r.get("required") is False else str(r.get("required")))
  return f"{r['employee_key']}|{r['item_id']}|{req}|{r['status']}|{hashlib.md5(vs.encode()).hexdigest()}|{int(r.get('reminder_count') or 0)}"
out={"item_count":len(rows),"fingerprint":sorted(fp(r) for r in rows),"seed":app.onboarding_seed_enabled(),"hr_mutate":app.onboarding_hr_mutate_enabled()}
assert out["item_count"]==19
assert out["seed"] is False
assert out["hr_mutate"] is False
print(json.dumps(out, indent=2, default=str))
PY

# Backup code + DB dump of onboarding rows for four reals
log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/onboarding_wave2.py" "$BACKUP/onboarding_wave2.py" 2>/dev/null || true
cp -a "$ORCH/action_registry.py" "$BACKUP/action_registry.py" 2>/dev/null || true
test ! -f "$ORCH/onboarding_wave3_migration.py" || cp -a "$ORCH/onboarding_wave3_migration.py" "$BACKUP/"
sha256sum "$BACKUP/app.py" | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

# SQL snapshot for data rollback (in addition to in-module snapshots)
.venv/bin/python - <<'PY' | tee "$BACKUP/onboarding-items-four-reals.json"
import json, app
KEYS=["WATHEFNI-96550252254","WATHEFNI-96566363363","WATHEFNI-96597727743","WATHEFNI-96599411617"]
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("SELECT * FROM onboarding_items WHERE employee_key=ANY(%s) ORDER BY employee_key, item_id", (KEYS,))
    items=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT employee_key, onboarding_status, start_date, documents_pending, documents_complete, onboarding_template_version, raw_json FROM employees WHERE employee_key=ANY(%s)", (KEYS,))
    emps=[dict(r) for r in cur.fetchall()]
print(json.dumps({"items":items,"employees":emps}, indent=2, default=str))
PY

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
# Restore Wave 3 pre-migration app.py and optionally note data rollback via migration module.
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
if [[ -f "$BACKUP_DIR/onboarding_wave2.py" ]]; then
  cp -a "$BACKUP_DIR/onboarding_wave2.py" "$ORCH/onboarding_wave2.py"
fi
if [[ -f "$BACKUP_DIR/action_registry.py" ]]; then
  cp -a "$BACKUP_DIR/action_registry.py" "$ORCH/action_registry.py"
fi
# Remove wave3 module only if it did not exist pre-migration
if [[ ! -f "$BACKUP_DIR/onboarding_wave3_migration.py" ]]; then
  rm -f "$ORCH/onboarding_wave3_migration.py" "$ORCH/migrate-prod-onboarding-wave3.py"
fi
systemctl restart wathefni-orchestrator
sleep 3
systemctl is-active wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo "CODE_ROLLBACK_OK — data rollback must use onboarding_wave3_migration.rollback_batch"
RB
chmod +x "$BACKUP/ROLLBACK.sh"
bash -n "$BACKUP/ROLLBACK.sh"
{
  echo "rollback_syntax_ok=true"
  echo "rollback_script=$BACKUP/ROLLBACK.sh"
  echo "data_rollback=module_rollback_batch"
} | tee "$REMOTE_EVID/verify/rollback-tested.txt"

# Deploy modules
test -f "$STAGE/onboarding_wave3_migration.py"
test -f "$STAGE/migrate-prod-onboarding-wave3.py"
test -f "$STAGE/app.py"
python3 - <<PY
from pathlib import Path
assert "retired_legacy" in Path("$STAGE/app.py").read_text()
assert "dual_control" in Path("$STAGE/onboarding_wave3_migration.py").read_text().lower() or "self_approval_forbidden" in Path("$STAGE/onboarding_wave3_migration.py").read_text()
print("candidate_ok")
PY
.venv/bin/python -m py_compile "$STAGE/onboarding_wave3_migration.py" "$STAGE/migrate-prod-onboarding-wave3.py"
.venv/bin/python -c "import ast; ast.parse(open('$STAGE/app.py').read()); print('app_parse_ok')"

log "installing wave3 migration modules"
cp -a "$STAGE/app.py" "$ORCH/app.py"
cp -a "$STAGE/onboarding_wave3_migration.py" "$ORCH/onboarding_wave3_migration.py"
cp -a "$STAGE/migrate-prod-onboarding-wave3.py" "$ORCH/migrate-prod-onboarding-wave3.py"
cp -a "$STAGE/smoke-test-employees360-freeze-regression.py" "$ORCH/" 2>/dev/null || true
chmod +x "$ORCH/migrate-prod-onboarding-wave3.py"

systemctl restart wathefni-orchestrator
for i in $(seq 1 15); do
  curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break
  sleep 1
done
systemctl is-active wathefni-orchestrator

# Confirm SEED/HR_MUTATE still off in process
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
{
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ONBOARDING_SEED|ONBOARDING_HR_MUTATE|WAVE3_MIGRATION|EMPLOYEE_APP' | sort || true
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

while IFS= read -r -d '' line; do
  case "$line" in
    WATHEFNI_*=*) export "$line" ;;
  esac
done < /proc/"$PID"/environ
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/flags/flag-assert.txt"
import app
assert app.onboarding_seed_enabled() is False
assert app.onboarding_hr_mutate_enabled() is False
print("seed_off_hr_mutate_off=true")
PY

echo "DEPLOY_OK"
