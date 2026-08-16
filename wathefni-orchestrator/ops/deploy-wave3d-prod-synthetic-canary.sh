#!/usr/bin/env bash
# Wave 3D controlled production deploy — WATHEFNI synthetic canary only.
set -euo pipefail

STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
REMOTE_EVID="/opt/wathefni/production-evidence/employees360-wave3d-synthetic-canary/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-employees360-wave3d-${STAMP}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf

echo "STAMP=$STAMP"
mkdir -p "$REMOTE_EVID" "$BACKUP"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

# --- preflight SHAs ---
{
  sha256sum "$ORCH/app.py"
  sha256sum "$ORCH/employee_authority_wave2.py" 2>/dev/null || true
  ls "$ORCH"/employee_lifecycle_wave3*.py 2>/dev/null || echo "no wave3 modules yet"
} | tee "$REMOTE_EVID/sha-before.txt"

curl -fsS -o "$REMOTE_EVID/health-before.txt" -w "\n" http://127.0.0.1:8010/healthz || curl -fsS -o "$REMOTE_EVID/health-before.txt" http://127.0.0.1:8010/health || true

# --- backup ---
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/employee_authority_wave2.py" "$BACKUP/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "$BACKUP/systemd-dropins" 2>/dev/null || true
cat > "$BACKUP/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf
rm -f "$ORCH/employee_lifecycle_wave3.py" "$ORCH/employee_lifecycle_wave3c.py" "$ORCH/lifecycle-effective-worker.py"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 2
curl -fsS http://127.0.0.1:8010/healthz || curl -fsS http://127.0.0.1:8010/health
echo "rolled back wave3d modules + drop-in"
EOS
chmod +x "$BACKUP/ROLLBACK.sh"

# --- install modules (from /tmp/wave3d-deploy staged by scp) ---
STAGE=/tmp/wave3d-deploy
test -f "$STAGE/employee_lifecycle_wave3.py"
test -f "$STAGE/employee_lifecycle_wave3c.py"
test -f "$STAGE/lifecycle-effective-worker.py"
test -f "$STAGE/canary-prod-wave3d-synthetic.py"
test -f "$STAGE/app-fragment-employee-lifecycle-wave3d.py.txt"

cp -a "$STAGE/employee_lifecycle_wave3.py" "$ORCH/"
cp -a "$STAGE/employee_lifecycle_wave3c.py" "$ORCH/"
cp -a "$STAGE/lifecycle-effective-worker.py" "$ORCH/"
cp -a "$STAGE/canary-prod-wave3d-synthetic.py" "$ORCH/"
chmod +x "$ORCH/lifecycle-effective-worker.py" "$ORCH/canary-prod-wave3d-synthetic.py"

# --- inject app.py routes if missing ---
if grep -q "dashboard_employee_lifecycle_policy_get" "$ORCH/app.py"; then
  echo "lifecycle routes already present"
else
  python3 <<'PY'
from pathlib import Path
app_path = Path("/opt/wathefni/orchestrator/app.py")
frag = Path("/tmp/wave3d-deploy/app-fragment-employee-lifecycle-wave3d.py.txt").read_text()
src = app_path.read_text()
if "dashboard_employee_lifecycle_policy_get" in src:
    print("already injected")
else:
    # Insert before _parse_employee_import_file if present, else after status decide
    needle = "def _parse_employee_import_file"
    if needle in src:
        pos = src.index(needle)
        # back up to include preceding blank lines
        while pos > 0 and src[pos-1] == "\n":
            pos -= 1
        # keep one blank line before fragment
        src = src[:pos] + "\n\n" + frag + src[pos:]
    else:
        marker = "def dashboard_employee_status_decide_request"
        if marker not in src:
            raise SystemExit("cannot find insertion point in app.py")
        # find end of that function roughly: next \n\ndef at column 0
        i = src.index(marker)
        import re
        m = re.search(r"\n\ndef ", src[i+10:])
        if not m:
            raise SystemExit("cannot find end of status decide")
        pos = i + 10 + m.start()
        src = src[:pos] + "\n\n" + frag + src[pos:]
    app_path.write_text(src)
    print("injected lifecycle routes")
PY
fi

# --- compile check ---
/opt/wathefni/orchestrator/.venv/bin/python -m py_compile \
  "$ORCH/employee_lifecycle_wave3.py" \
  "$ORCH/employee_lifecycle_wave3c.py" \
  "$ORCH/lifecycle-effective-worker.py" \
  "$ORCH/canary-prod-wave3d-synthetic.py"
/opt/wathefni/orchestrator/.venv/bin/python -c "import ast; ast.parse(open('$ORCH/app.py').read()); print('app.py parse ok')"

# --- systemd drop-in (synthetic only) ---
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_PHONE_PREFIXES=965522
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_NAME_PREFIX=W3D-SYNTH|
Environment=WATHEFNI_LIFECYCLE_COUNSEL_GATE=on
EOF

# oneshot prod scheduler unit (manual / canary); timer NOT enabled by default
cat > /etc/systemd/system/wathefni-lifecycle-effective.service <<EOF
[Unit]
Description=Wathefni Employees 360 Wave 3D lifecycle effective scheduler (production synthetic-only)
After=network-online.target postgresql.service wathefni-orchestrator.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/wathefni/orchestrator
Environment=WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
Environment=WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
Environment=WATHEFNI_ENV=production
Environment=WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
Environment=WATHEFNI_EXPECTED_DATABASE_PORT=5432
Environment=WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
Environment=WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
Environment=HOME=/root
Environment=WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
Environment=WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_PHONE_PREFIXES=965522
Environment=WATHEFNI_LIFECYCLE_COUNSEL_GATE=on
ExecStart=/opt/wathefni/orchestrator/.venv/bin/python lifecycle-effective-worker.py
Nice=10
EOF

systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
curl -fsS -o "$REMOTE_EVID/health-after-deploy.txt" http://127.0.0.1:8010/healthz || curl -fsS -o "$REMOTE_EVID/health-after-deploy.txt" http://127.0.0.1:8010/health

{
  sha256sum "$ORCH/app.py"
  sha256sum "$ORCH/employee_lifecycle_wave3.py"
  sha256sum "$ORCH/employee_lifecycle_wave3c.py"
  sha256sum "$ORCH/lifecycle-effective-worker.py"
  sha256sum "$ORCH/canary-prod-wave3d-synthetic.py"
} | tee "$REMOTE_EVID/sha-after-deploy.txt"

# freeze flags snapshot
tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator)/environ \
  | grep -E 'WATHEFNI_EMPLOYEE_LIFECYCLE|WATHEFNI_EMPLOYEE_AUTHORITY|WATHEFNI_ENV|WATHEFNI_INBOUND' \
  | sort | tee "$REMOTE_EVID/freeze-flags.txt"

# --- run synthetic canary ---
set -a
source /root/.openclaw/secrets/postgres.env
set +a
export WATHEFNI_ENV=production
export WAVE3D_CANARY_OUT="$REMOTE_EVID/canary"
mkdir -p "$WAVE3D_CANARY_OUT"
cd "$ORCH"
# Load same env as service for DB
while IFS= read -r -d '' kv; do
  case "$kv" in
    WATHEFNI_*|DATABASE_URL=*|PG*) export "$kv" ;;
  esac
done < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator)/environ
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
export WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
export WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES=WATHEFNI
export WATHEFNI_LIFECYCLE_COUNSEL_GATE=on
export WATHEFNI_ENV=production

/opt/wathefni/orchestrator/.venv/bin/python canary-prod-wave3d-synthetic.py | tee "$REMOTE_EVID/canary-run.log"
CANARY_EC=${PIPESTATUS[0]}
echo "$CANARY_EC" > "$REMOTE_EVID/canary-exit-code.txt"

# Prove real employees untouched again
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/real-employees-final.json"
import json, os, psycopg2
url = os.environ.get("DATABASE_URL") or os.environ.get("WATHEFNI_DATABASE_URL")
conn = psycopg2.connect(url)
cur = conn.cursor()
keys = [
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
]
cur.execute(
    "SELECT employee_key, phone, name, employment_status FROM employees WHERE company_code=%s AND employee_key = ANY(%s) ORDER BY 1",
    ("WATHEFNI", keys),
)
rows = [{"employee_key": r[0], "phone": r[1], "name": r[2], "employment_status": r[3]} for r in cur.fetchall()]
print(json.dumps({"real_employees": rows, "all_active": all(r["employment_status"]=="active" for r in rows)}, indent=2))
conn.close()
PY

echo "REMOTE_EVID=$REMOTE_EVID"
echo "BACKUP=$BACKUP"
echo "CANARY_EC=$CANARY_EC"
exit "$CANARY_EC"
