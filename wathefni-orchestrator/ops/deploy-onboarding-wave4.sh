#!/usr/bin/env bash
# Onboarding Wave 4 — production deploy: WATHEFNI-only HR_MUTATE + UX backend.
# Keeps ONBOARDING_SEED=off. Does not broaden employee-app allowlist.
# Does not change four-real checklist history (canary restores fingerprint).
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-onboarding-wave4-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/onboarding-wave4/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/onboarding-wave4-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-onboarding-wave4-hr-mutate.conf

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,tests,canary,ux} "$BACKUP"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  sha256sum "$ORCH/app.py" "$ORCH/action_registry.py" "$ORCH/onboarding_wave2.py"
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
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("""
      SELECT oi.employee_key, oi.item_id, oi.required, oi.status, oi.value, oi.reminder_count
      FROM onboarding_items oi JOIN employees e ON e.employee_key=oi.employee_key
      WHERE e.company_code='WATHEFNI' AND oi.employee_key=ANY(%s)
      ORDER BY oi.employee_key, oi.item_id
    """, (KEYS,))
    rows=[dict(r) for r in cur.fetchall()]
def fp(r):
  v=r.get("value"); vs="" if v is None else str(v)
  req="True" if r.get("required") is True else ("False" if r.get("required") is False else str(r.get("required")))
  return f"{r['employee_key']}|{r['item_id']}|{req}|{r['status']}|{hashlib.md5(vs.encode()).hexdigest()}|{int(r.get('reminder_count') or 0)}"
out={"item_count":len(rows),"fingerprint":sorted(fp(r) for r in rows),
     "seed":app.onboarding_seed_enabled(),"hr_mutate":app.onboarding_hr_mutate_enabled()}
assert out["seed"] is False
print(json.dumps(out, indent=2, default=str))
PY

log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/action_registry.py" "$BACKUP/action_registry.py"
cp -a "$ORCH/onboarding_wave2.py" "$BACKUP/onboarding_wave2.py"
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins" 2>/dev/null || true
sha256sum "$BACKUP/app.py" "$BACKUP/action_registry.py" | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-onboarding-wave4-hr-mutate.conf
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/action_registry.py" "$ORCH/action_registry.py"
cp -a "$BACKUP_DIR/onboarding_wave2.py" "$ORCH/onboarding_wave2.py" 2>/dev/null || true
rm -f "$DROPIN"
rm -f "$ORCH/canary-prod-onboarding-wave4.py"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
systemctl is-active wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo "ROLLBACK_OK"
RB
chmod +x "$BACKUP/ROLLBACK.sh"
bash -n "$BACKUP/ROLLBACK.sh"
{
  echo "rollback_syntax_ok=true"
  echo "rollback_script=$BACKUP/ROLLBACK.sh"
} | tee "$REMOTE_EVID/verify/rollback-tested.txt"

test -f "$STAGE/app.py"
test -f "$STAGE/action_registry.py"
test -f "$STAGE/canary-prod-onboarding-wave4.py"
.venv/bin/python -c "import ast; ast.parse(open('$STAGE/app.py').read()); ast.parse(open('$STAGE/action_registry.py').read()); print('parse_ok')"
.venv/bin/python -m py_compile "$STAGE/canary-prod-onboarding-wave4.py"

log "installing wave4 modules"
cp -a "$STAGE/app.py" "$ORCH/app.py"
cp -a "$STAGE/action_registry.py" "$ORCH/action_registry.py"
cp -a "$STAGE/canary-prod-onboarding-wave4.py" "$ORCH/canary-prod-onboarding-wave4.py"
cp -a "$STAGE/smoke-test-employees360-freeze-regression.py" "$ORCH/" 2>/dev/null || true
cp -a "$STAGE/smoke-test-onboarding-wave1-read-authority.py" "$ORCH/" 2>/dev/null || true
# Keep wave2 module if stage has updates
if [[ -f "$STAGE/onboarding_wave2.py" ]]; then
  cp -a "$STAGE/onboarding_wave2.py" "$ORCH/onboarding_wave2.py"
fi

# Enable WATHEFNI-only HR mutate; keep SEED off
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_ONBOARDING_SEED=off
Environment=WATHEFNI_ONBOARDING_HR_MUTATE=on
Environment=WATHEFNI_ONBOARDING_HR_MUTATE_COMPANIES=WATHEFNI
EOF

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break
  sleep 1
done
systemctl is-active wathefni-orchestrator

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
{
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ONBOARDING|EMPLOYEE_APP' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

while IFS= read -r -d '' line; do
  case "$line" in
    WATHEFNI_*=*) export "$line" ;;
  esac
done < /proc/"$PID"/environ

.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/flags/flag-assert.txt"
import app
assert app.onboarding_seed_enabled() is False
assert app.onboarding_hr_mutate_enabled() is True
assert app.onboarding_hr_mutate_companies() == {"WATHEFNI"}
assert app.onboarding_hr_mutate_enabled_for_company("WATHEFNI") is True
assert app.onboarding_hr_mutate_enabled_for_company("OTHERCO") is False
print("seed_off=true")
print("hr_mutate_wathefni_only=true")
print("sha_app", __import__("hashlib").sha256(open("/opt/wathefni/orchestrator/app.py","rb").read()).hexdigest())
PY

sha256sum "$ORCH/app.py" "$ORCH/action_registry.py" | tee "$REMOTE_EVID/verify/shas-after.txt"
echo "DEPLOY_OK"
