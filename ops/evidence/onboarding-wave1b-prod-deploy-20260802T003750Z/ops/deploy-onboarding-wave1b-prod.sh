#!/usr/bin/env bash
# Onboarding Wave 1B — production deploy of Wave 1 read-path repair.
# Does NOT enable SEED/HR_MUTATE, does NOT backfill checklists, does NOT broaden app.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-onboarding-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/onboarding-wave1b-prod-deploy/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/onboarding-wave1b-stage}"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,data} "$BACKUP" "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# --- preflight: flags, SHAs, corrupted loader, counts ---
{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "=== unit active ==="
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py"
  echo "=== onboarding flags (systemd) ==="
  systemctl show wathefni-orchestrator -p Environment --value | tr ' ' '\n' | grep -E 'ONBOARDING|EMPLOYEE_APP' || true
  echo "=== onboarding flags (process) ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ONBOARDING_SEED|ONBOARDING_HR_MUTATE|EMPLOYEE_APP' || true
  echo "=== loader corruption before ==="
  python3 - <<'PY'
from pathlib import Path
src=Path("/opt/wathefni/orchestrator/app.py").read_text()
s=src.find("def employee_onboarding_items"); e=src.find("\ndef ", s+1)
chunk=src[s:e]
print("candidates_read_in_loader", "candidates.read" in chunk)
print("has_load_onboarding_items", "def load_onboarding_items" in src)
assert "candidates.read" in chunk, "expected corrupted loader before deploy"
assert "def load_onboarding_items" not in src, "unexpected Wave1 helper already on prod"
print("corruption_confirmed=true")
PY
} | tee "$REMOTE_EVID/preflight/before-deploy.txt"

# Live DB counts for four reals (read-only)
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
out = {"employees": [], "item_rows": []}
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT employee_key, name, company_code, onboarding_status,
                   documents_pending, documents_complete
            FROM employees
            WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)
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
        cur.execute(
            """
            SELECT count(*) AS employees,
                   count(*) FILTER (WHERE onboarding_status='in_progress') AS in_progress
            FROM employees WHERE company_code='WATHEFNI'
            """
        )
        company = dict(cur.fetchone() or {})
        cur.execute(
            """
            SELECT count(*) AS item_rows,
                   count(*) FILTER (WHERE lower(status)='pending') AS pending,
                   count(*) FILTER (WHERE lower(status)='received') AS received
            FROM onboarding_items oi
            JOIN employees e ON e.employee_key=oi.employee_key
            WHERE e.company_code='WATHEFNI'
            """
        )
        item_stats = dict(cur.fetchone() or {})
out = {
    "company": company,
    "item_stats": item_stats,
    "employees": emps,
    "item_rows": items,
    "item_fingerprint": sorted(
        f"{r['employee_key']}|{r['item_id']}|{r['required']}|{r['status']}|{r.get('value_md5')}"
        for r in items
    ),
}
print(json.dumps(out, indent=2, default=str))
PY

# Confirm SEED/HR_MUTATE off in process
.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/flags/prod-flags-before.txt"
import os, app
# Prefer process (already loaded). Force explicit check of helpers.
print("SEED", app.onboarding_seed_enabled())
print("HR_MUTATE", app.onboarding_hr_mutate_enabled())
assert app.onboarding_seed_enabled() is False
assert app.onboarding_hr_mutate_enabled() is False
print("flags_ok_off=true")
PY

# --- backup ---
log "backing up app.py"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
sha256sum "$BACKUP/app.py" | tee "$BACKUP/app.py.sha256"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
# Rollback Onboarding Wave 1B app.py only. Does not touch SEED/HR_MUTATE drop-ins.
set -euo pipefail
BACKUP_DIR="${1:?backup dir}"
ORCH=/opt/wathefni/orchestrator
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
systemctl restart wathefni-orchestrator
sleep 2
systemctl is-active wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo "ROLLBACK_OK"
RB
chmod +x "$BACKUP/ROLLBACK.sh"
bash -n "$BACKUP/ROLLBACK.sh"
# Tested rollback proof: dry-run copy to temp + syntax + checksum match
mkdir -p /tmp/w1b-rollback-test
cp -a "$BACKUP/app.py" /tmp/w1b-rollback-test/app.py
cmp -s "$BACKUP/app.py" /tmp/w1b-rollback-test/app.py
{
  echo "rollback_syntax_ok=true"
  echo "rollback_script=$BACKUP/ROLLBACK.sh"
  echo "rollback_source_sha=$(sha256sum "$BACKUP/app.py" | awk '{print $1}')"
  echo "rollback_cmp_ok=true"
  echo "rollback_full_execute=deferred_post_go_not_run"
} | tee "$REMOTE_EVID/verify/rollback-tested.txt"

# --- deploy ---
test -f "$STAGE/app.py"
STAGE_SHA=$(sha256sum "$STAGE/app.py" | awk '{print $1}')
# refuse to deploy if candidate still corrupted
python3 - <<PY
from pathlib import Path
src=Path("$STAGE/app.py").read_text()
s=src.find("def employee_onboarding_items"); e=src.find("\\ndef ", s+1)
chunk=src[s:e]
assert "candidates.read" not in chunk
assert "def load_onboarding_items" in src
assert "def onboarding_plaintext_bank_forbidden" in src
print("candidate_ok")
PY

log "installing app.py"
cp -a "$STAGE/app.py" "$ORCH/app.py"
# optional smoke helpers (non-runtime)
mkdir -p "$ORCH/ops"
cp -a "$STAGE/smoke-test-onboarding-wave1-read-authority.py" "$ORCH/" 2>/dev/null || true
cp -a "$STAGE/smoke-test-employees360-freeze-regression.py" "$ORCH/" 2>/dev/null || true
cp -a "$STAGE/ops/onboarding-wave1-legacy-migration-assessment.py" "$ORCH/ops/" 2>/dev/null || true

systemctl restart wathefni-orchestrator
sleep 3
systemctl is-active wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health >/dev/null

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py"
  echo "expected_stage_sha=$STAGE_SHA"
  echo "=== loader after ==="
  python3 - <<'PY'
from pathlib import Path
src=Path("/opt/wathefni/orchestrator/app.py").read_text()
s=src.find("def employee_onboarding_items"); e=src.find("\ndef ", s+1)
chunk=src[s:e]
print("candidates_read_in_loader", "candidates.read" in chunk)
print("has_load_onboarding_items", "def load_onboarding_items" in src)
assert "candidates.read" not in chunk
assert "def load_onboarding_items" in src
print("loader_repaired=true")
PY
  echo "=== flags after (must remain off) ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'ONBOARDING_SEED|ONBOARDING_HR_MUTATE' || echo 'HR_MUTATE_UNSET'
} | tee "$REMOTE_EVID/preflight/after-deploy.txt"

echo "DEPLOY_OK"
