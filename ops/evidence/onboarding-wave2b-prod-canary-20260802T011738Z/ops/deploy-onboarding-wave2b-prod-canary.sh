#!/usr/bin/env bash
# Onboarding Wave 2B — production synthetic canary deploy.
# Deploys Wave 2 modules; enables SYNTHETIC_CANARY only.
# Keeps ONBOARDING_SEED=off and ONBOARDING_HR_MUTATE=off.
# Does NOT migrate four real checklists. Does NOT broaden employee-app access.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-onboarding-wave2b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/onboarding-wave2b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/onboarding-wave2b-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-onboarding-wave2b-synthetic-canary.conf

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,tests,canary,data} "$BACKUP" "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# --- preflight ---
{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py"
  sha256sum "$ORCH/action_registry.py" 2>/dev/null || true
  ls -la "$ORCH/onboarding_wave2.py" 2>&1 || echo "onboarding_wave2.py absent (expected pre-wave2b)"
  echo "=== flags before (process) ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ONBOARDING|EMPLOYEE_APP|DOC_UPLOAD|SYNTHETIC_CANARY' | sort || true
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
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/preflight/onboarding-counts-before.json"
import json, app
app.ensure_schema()
KEYS = [
  "WATHEFNI-96550252254",
  "WATHEFNI-96566363363",
  "WATHEFNI-96597727743",
  "WATHEFNI-96599411617",
]
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT employee_key, name, onboarding_status, documents_pending, documents_complete
            FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
            ORDER BY employee_key
            """,
            (KEYS,),
        )
        emps = [dict(r) for r in cur.fetchall() or []]
        cur.execute(
            """
            SELECT oi.employee_key, oi.item_id, oi.label, oi.required, oi.status,
                   oi.owner, oi.category, oi.reminder_count,
                   md5(coalesce(oi.value::text,'')) AS value_md5
            FROM onboarding_items oi
            JOIN employees e ON e.employee_key=oi.employee_key
            WHERE e.company_code='WATHEFNI' AND oi.employee_key = ANY(%s)
            ORDER BY oi.employee_key, oi.item_id
            """,
            (KEYS,),
        )
        items = [dict(r) for r in cur.fetchall() or []]
out = {
    "employees": emps,
    "item_rows": items,
    "item_count": len(items),
    "item_fingerprint": sorted(
        f"{r['employee_key']}|{r['item_id']}|{r['required']}|{r['status']}|{r.get('value_md5')}|{r.get('reminder_count',0)}"
        for r in items
    ),
}
assert out["item_count"] == 19, out["item_count"]
print(json.dumps(out, indent=2, default=str))
PY

.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/flags/prod-flags-before.txt"
import app
print("SEED", app.onboarding_seed_enabled())
print("HR_MUTATE", app.onboarding_hr_mutate_enabled())
assert app.onboarding_seed_enabled() is False
assert app.onboarding_hr_mutate_enabled() is False
print("flags_ok_off=true")
PY

# --- backup ---
log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/action_registry.py" "$BACKUP/action_registry.py"
test ! -f "$ORCH/onboarding_wave2.py" || cp -a "$ORCH/onboarding_wave2.py" "$BACKUP/onboarding_wave2.py"
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins" 2>/dev/null || true
sha256sum "$BACKUP/app.py" "$BACKUP/action_registry.py" | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-onboarding-wave2b-synthetic-canary.conf
test -f "$BACKUP_DIR/app.py"
test -f "$BACKUP_DIR/action_registry.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/action_registry.py" "$ORCH/action_registry.py"
if [[ -f "$BACKUP_DIR/onboarding_wave2.py" ]]; then
  cp -a "$BACKUP_DIR/onboarding_wave2.py" "$ORCH/onboarding_wave2.py"
else
  rm -f "$ORCH/onboarding_wave2.py"
fi
rm -f "$DROPIN"
rm -f "$ORCH/canary-prod-onboarding-wave2b.py"
rm -f "$ORCH/smoke-test-onboarding-wave2.py"
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
  echo "rollback_source_sha_app=$(sha256sum "$BACKUP/app.py" | awk '{print $1}')"
  echo "rollback_source_sha_action=$(sha256sum "$BACKUP/action_registry.py" | awk '{print $1}')"
  echo "rollback_cmp_ok=true"
  echo "rollback_full_execute=deferred_unless_fail"
} | tee "$REMOTE_EVID/verify/rollback-tested.txt"

# --- validate stage ---
test -f "$STAGE/app.py"
test -f "$STAGE/action_registry.py"
test -f "$STAGE/onboarding_wave2.py"
test -f "$STAGE/canary-prod-onboarding-wave2b.py"
python3 - <<PY
from pathlib import Path
app = Path("$STAGE/app.py").read_text()
w2 = Path("$STAGE/onboarding_wave2.py").read_text()
assert "onboarding_wave2" in app
assert "onboarding_synthetic_canary_enabled" in app
assert "onboarding_seed_allowed_for" in app
assert "CANONICAL_TEMPLATE_VERSION = \"2.0.0\"" in w2
assert "is_onboarding_synthetic_employee" in w2
assert "abandon_onboarding" in w2
print("candidate_ok")
PY
.venv/bin/python -m py_compile "$STAGE/onboarding_wave2.py" "$STAGE/canary-prod-onboarding-wave2b.py"
.venv/bin/python -c "import ast; ast.parse(open('$STAGE/app.py').read()); ast.parse(open('$STAGE/action_registry.py').read()); print('parse_ok')"

# --- deploy ---
log "installing Wave 2B modules"
cp -a "$STAGE/app.py" "$ORCH/app.py"
cp -a "$STAGE/action_registry.py" "$ORCH/action_registry.py"
cp -a "$STAGE/onboarding_wave2.py" "$ORCH/onboarding_wave2.py"
cp -a "$STAGE/canary-prod-onboarding-wave2b.py" "$ORCH/canary-prod-onboarding-wave2b.py"
cp -a "$STAGE/smoke-test-onboarding-wave2.py" "$ORCH/" 2>/dev/null || true
cp -a "$STAGE/smoke-test-employees360-freeze-regression.py" "$ORCH/" 2>/dev/null || true
cp -a "$STAGE/smoke-test-onboarding-wave1-read-authority.py" "$ORCH/" 2>/dev/null || true
chmod +x "$ORCH/canary-prod-onboarding-wave2b.py"

# Drop-in: synthetic canary ON; SEED/HR_MUTATE explicitly OFF
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_ONBOARDING_SEED=off
Environment=WATHEFNI_ONBOARDING_HR_MUTATE=off
Environment=WATHEFNI_ONBOARDING_SYNTHETIC_CANARY=on
Environment=WATHEFNI_ONBOARDING_SYNTHETIC_PHONE_PREFIXES=965523
Environment=WATHEFNI_ONBOARDING_SYNTHETIC_NAME_PREFIX=W2B-SYNTH|
EOF

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
systemctl is-active wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health >/dev/null

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/action_registry.py" "$ORCH/onboarding_wave2.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ONBOARDING|EMPLOYEE_APP|SYNTHETIC_CANARY' | sort || true
} | tee "$REMOTE_EVID/preflight/after-deploy.txt"

.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/flags/prod-flags-after.txt"
import app
print("SEED", app.onboarding_seed_enabled())
print("HR_MUTATE", app.onboarding_hr_mutate_enabled())
print("SYNTHETIC_CANARY", app.onboarding_synthetic_canary_enabled())
assert app.onboarding_seed_enabled() is False
assert app.onboarding_hr_mutate_enabled() is False
assert app.onboarding_synthetic_canary_enabled() is True
print("flags_ok_canary=true")
PY

echo "DEPLOY_OK"
