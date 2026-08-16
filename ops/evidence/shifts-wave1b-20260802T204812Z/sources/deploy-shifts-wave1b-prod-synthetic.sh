#!/usr/bin/env bash
# Shifts Wave 1B — production WATHEFNI synthetic canary deploy.
# Enables WAVE1 + SYNTHETIC_ONLY for WATHEFNI. Keeps CAPTURE_INGEST=off.
# Does NOT enable templates/recurring/publish/open shifts/Payroll money.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-shifts-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave1b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/shifts-w1b-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-authority-wave1b-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui,orphan,cleanup,rollback} \
  "$BACKUP"/{modules,dashboard-dist,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" || true
  ls -la "$ORCH/shifts_authority_wave1.py" 2>&1 || echo "shifts_authority_wave1.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'SHIFTS_AUTHORITY|CAPTURE_INGEST|LEAVE_|ATTENDANCE_' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort || true
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
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/shift-fingerprints-before.json"
import json, hashlib, app
ORPHANS = {
  "0a6e73dd-9c6d-49a0-b253-39a9922ebd70",
  "6a84a671-eb7f-43ea-870e-af859a440467",
  "f9ebecf3-8838-456a-8124-c34c3c7600ca",
}
def fp(r):
    parts=[str(r.get(k) or "") for k in ("shift_id","employee_key","employee_phone","shift_date","start_time","end_time","status","updated_at","role","location","timezone")]
    return hashlib.md5("|".join(parts).encode()).hexdigest()
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
        cur.execute("""
          SELECT shift_id::text, employee_key, coalesce(employee_phone,'') employee_phone, shift_date::text,
                 start_time::text, end_time::text, status, updated_at::text,
                 coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone
          FROM shift_assignments WHERE company_code='WATHEFNI' ORDER BY shift_id::text
        """)
        assigns=[dict(r) for r in cur.fetchall()]
        for a in assigns: a["fp"]=fp(a)
        cur.execute("SELECT count(*) AS n FROM shift_events WHERE company_code='WATHEFNI'"); ev=int(dict(cur.fetchone())["n"])
        cur.execute("SELECT count(*) AS n FROM shift_swap_requests WHERE company_code='WATHEFNI'"); sw=int(dict(cur.fetchone())["n"])
out={"db":db,"assignment_count":len(assigns),"event_count":ev,"swap_count":sw,
     "orphans":[a for a in assigns if a["shift_id"] in ORPHANS],
     "assignment_fps":{a["shift_id"]:a["fp"] for a in assigns}}
assert len(out["orphans"])==3, out["orphans"]
print(json.dumps(out, indent=2, default=str))
PY

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up code, dashboard dist, dropins, table dumps"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
[[ -f "$ORCH/shifts_authority_wave1.py" ]] && cp -a "$ORCH/shifts_authority_wave1.py" "$BACKUP/modules/" || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
if [[ -d "$DASH_DIST" ]]; then
  cp -a "$DASH_DIST/." "$BACKUP/dashboard-dist/"
fi
sudo -u postgres psql -d wathefni -c "COPY (
  SELECT shift_id, employee_key, employee_phone, shift_date, start_time, end_time, status, updated_at, role, location, timezone
  FROM shift_assignments WHERE company_code='WATHEFNI' ORDER BY shift_id
) TO STDOUT WITH CSV HEADER" > "$BACKUP/shift-assignments.csv"
sudo -u postgres psql -d wathefni -c "COPY (
  SELECT event_id, shift_id, event_type, created_at FROM shift_events WHERE company_code='WATHEFNI' ORDER BY event_id
) TO STDOUT WITH CSV HEADER" > "$BACKUP/shift-events.csv"
sudo -u postgres psql -d wathefni -c "COPY (
  SELECT * FROM shift_swap_requests WHERE company_code='WATHEFNI' ORDER BY swap_id
) TO STDOUT WITH CSV HEADER" > "$BACKUP/shift-swap-requests.csv" || true
(
  cd "$BACKUP"
  sha256sum app.py shift-assignments.csv shift-events.csv 2>/dev/null || true
  find modules dashboard-dist -type f 2>/dev/null | head -200 | while read -r f; do sha256sum "$f"; done
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"
cp -a "$BACKUP/SHA256SUMS" "$REMOTE_EVID/backup/"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-authority-wave1b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ ! -f "$BACKUP_DIR/modules/shifts_authority_wave1.py" ]]; then
  rm -f "$ORCH/shifts_authority_wave1.py"
else
  cp -a "$BACKUP_DIR/modules/shifts_authority_wave1.py" "$ORCH/"
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rm -rf "$DASH_DIST"
  mkdir -p "$DASH_DIST"
  cp -a "$BACKUP_DIR/dashboard-dist/." "$DASH_DIST/"
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

log "deploying modules + canary + freeze scripts"
for f in app.py shifts_authority_wave1.py canary-prod-shifts-wave1b.py \
         smoke-test-shifts-authority-wave1.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql"
[[ -f "$STAGE/migrate-shifts-authority-wave1-prod.sh" ]] && cp -a "$STAGE/migrate-shifts-authority-wave1-prod.sh" "$ORCH/ops/" && chmod +x "$ORCH/ops/migrate-shifts-authority-wave1-prod.sh"
[[ -f "$STAGE/shifts_authority_wave1_v1.sql" ]] && cp -a "$STAGE/shifts_authority_wave1_v1.sql" "$ORCH/ops/sql/"

if [[ -d "$STAGE/dashboard-dist" ]]; then
  log "deploying dashboard dist"
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  grep -l expected_updated_at "$DASH_DIST"/assets/*.js 2>/dev/null | tee "$REMOTE_EVID/ui/dist-token.txt" || {
    echo "REFUSE: dashboard dist missing expected_updated_at" >&2
    exit 4
  }
fi

log "writing synthetic-only drop-in"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529
Environment=WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF

log "migrate schema 1.1.0"
ACK_PRODUCTION_SHIFTS_W1B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-shifts-authority-wave1-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/shifts_authority_wave1.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'SHIFTS_AUTHORITY|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/shifts-authority-flags.txt"
import os, shifts_authority_wave1 as s
print("WAVE1", os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_WAVE1"))
print("COMPANIES", os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_COMPANIES"))
print("SYNTHETIC_ONLY", os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY"))
print("MARKERS", os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS"))
print("PHONES", os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES"))
print("CAPTURE_INGEST", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"))
print("version", s.SHIFTS_WAVE1_VERSION)
assert s.shifts_wave1_enabled()
assert s.shifts_authority_synthetic_only()
assert "WATHEFNI" in s.shifts_authority_companies()
assert s.SHIFTS_WAVE1_VERSION == "1.1.0"
assert "SHW1B" in s.synthetic_key_markers()
assert "965529" in s.synthetic_phone_prefixes()
print("flags_ok_synthetic=true")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
