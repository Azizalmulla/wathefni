#!/usr/bin/env bash
# Wave 7 — production qualification: Wave 6 UI + thin read APIs for Workforce hub.
# Preserves ESS/lifecycle SYNTHETIC_ONLY. Does NOT enable real lifecycle/ESS/app.
set -euo pipefail

STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
REMOTE_EVID="/opt/wathefni/production-evidence/employees360-wave7-prod-qual/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-employees360-wave7-${STAMP}"
ORCH=/opt/wathefni/orchestrator
DASH=/var/www/wathefni-dashboard
STAGE=/tmp/wave7-deploy
APPS_SRC=/opt/wathefni/apps/wathefni-dashboard

echo "STAMP=$STAMP"
mkdir -p "$REMOTE_EVID"/{preflight,verify,schema,http,canary,keys} "$BACKUP/dashboard-dist" "$BACKUP/restore-new-dist" "$STAGE"

{
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/employee_org_wave4.py" "$ORCH/employee_selfservice_wave5.py" \
    "$ORCH/employee_lifecycle_wave3c.py" "$ORCH/employee_policy_packs_wave3h.py" 2>/dev/null || true
  sha256sum "$DASH/index.html" 2>/dev/null || true
  echo "=== FLAGS before ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE_(ESS|ORG|LIFECYCLE|POLICY|AUTHORITY|APP)' | sort
  echo "=== ROUTES before ==="
  curl -fsS http://127.0.0.1:8010/openapi.json | python3 -c "
import sys,json
p=json.load(sys.stdin).get('paths',{})
print('remediation', 'PRESENT' if '/dashboard/posthire/employee-lifecycle/remediation' in p else 'ABSENT')
m=p.get('/dashboard/posthire/employee-org/migration-batches') or {}
print('migration_batches_methods', sorted(m.keys()))
"
} | tee "$REMOTE_EVID/preflight/before.txt"

curl -fsS -o "$REMOTE_EVID/preflight/health-before.txt" http://127.0.0.1:8010/health

# --- backup ---
cp -a "$ORCH/app.py" "$BACKUP/"
cp -a "$ORCH/employee_org_wave4.py" "$BACKUP/"
rsync -a --delete "$DASH/" "$BACKUP/dashboard-dist/"
tar -C /var/www -czf "$BACKUP/dashboard-public.tgz" wathefni-dashboard
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
DASH=/var/www/wathefni-dashboard
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/employee_org_wave4.py" "$ORCH/employee_org_wave4.py"
rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH/"
systemctl restart wathefni-orchestrator
systemctl reload caddy || true
sleep 2
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo "rolled back Wave 7 UI + thin routes; Wave 3/4/5 flags unchanged"
EOS
chmod +x "$BACKUP/ROLLBACK.sh"
bash -n "$BACKUP/ROLLBACK.sh"
test -x "$BACKUP/ROLLBACK.sh"
echo "rollback_script_ok" | tee "$REMOTE_EVID/verify/rollback-proof.txt"
ls -la "$BACKUP" | tee "$REMOTE_EVID/verify/backup-listing.txt"

# --- install orchestrator thin APIs ---
test -f "$STAGE/app.py"
test -f "$STAGE/employee_org_wave4.py"
cp -a "$STAGE/app.py" "$ORCH/app.py"
cp -a "$STAGE/employee_org_wave4.py" "$ORCH/employee_org_wave4.py"
"$ORCH/.venv/bin/python" -m py_compile "$ORCH/app.py" "$ORCH/employee_org_wave4.py"
( cd "$ORCH" && "$ORCH/.venv/bin/python" -c "import employee_org_wave4 as w; print('list_migration_batches', hasattr(w,'list_migration_batches'))" )

systemctl restart wathefni-orchestrator
sleep 3
curl -fsS -o "$REMOTE_EVID/preflight/health-after-api.txt" http://127.0.0.1:8010/health

# --- install dashboard dist ---
test -d "$STAGE/dashboard-dist"
test -f "$STAGE/dashboard-dist/index.html"
rsync -a --delete "$STAGE/dashboard-dist/" "$REMOTE_EVID/dashboard-dist-new/" 2>/dev/null || mkdir -p "$REMOTE_EVID/dashboard-dist-meta"
rsync -a --delete "$STAGE/dashboard-dist/" "$DASH/"
rsync -a --delete "$DASH/" "$BACKUP/restore-new-dist/"
# keep apps source PostHire/employees360 in sync for ops
if [[ -d "$STAGE/dashboard-src-posthire" ]]; then
  mkdir -p "$APPS_SRC/src/posthire"
  rsync -a "$STAGE/dashboard-src-posthire/" "$APPS_SRC/src/posthire/"
fi
systemctl reload caddy || true
sleep 1
curl -fsS -o "$REMOTE_EVID/preflight/health-after.txt" http://127.0.0.1:8010/health
curl -fsS -o /dev/null -w "dashboard_http=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 | tee "$REMOTE_EVID/preflight/dashboard-http.txt"

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/employee_org_wave4.py"
  sha256sum "$DASH/index.html"
  ls "$DASH/assets"/PostHire-*.js "$DASH/assets"/dashboard-*.js 2>/dev/null | xargs sha256sum
  echo "=== FLAGS after (must preserve synthetic) ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE_(ESS|ORG|LIFECYCLE|POLICY|AUTHORITY|APP)' | sort | \
    sed -E 's/(WATHEFNI_ESS_BANK_SECRET_KEY(_PREVIOUS)?)=.*/\1=<redacted>/'
  echo "=== ROUTES after ==="
  curl -fsS http://127.0.0.1:8010/openapi.json | python3 -c "
import sys,json
p=json.load(sys.stdin).get('paths',{})
print('remediation', 'PRESENT' if '/dashboard/posthire/employee-lifecycle/remediation' in p else 'ABSENT')
m=p.get('/dashboard/posthire/employee-org/migration-batches') or {}
print('migration_batches_methods', sorted(m.keys()))
"
  echo "=== UI markers ==="
  python3 - <<'PY'
from pathlib import Path
dash=Path("/var/www/wathefni-dashboard")
html=(dash/"index.html").read_text()
post=next(dash.glob("assets/PostHire-*.js"))
text=post.read_text(errors="ignore")
print("posthire_chunk", post.name)
print("has_workforce", "workforce" in text)
print("has_employees360", "employees360" in text or "WorkforcePage" in text or "workforce-hub" in text)
print("html_refs_dashboard", "dashboard-" in html)
PY
} | tee "$REMOTE_EVID/preflight/after-deploy.txt"

# flag invariants
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
ENVF=$(tr '\0' '\n' < /proc/$PID/environ)
echo "$ENVF" | grep -q 'WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY=on'
echo "$ENVF" | grep -q 'WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on'
echo "$ENVF" | grep -q 'WATHEFNI_EMPLOYEE_APP=off'
echo "safety_flags_preserved=true" | tee "$REMOTE_EVID/verify/safety-flags.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
