#!/usr/bin/env bash
# Shifts Wave 2B — production WATHEFNI synthetic schedule-integrity canary deploy.
# Keeps CAPTURE_INGEST=off. Does NOT enable real-employee mutations, templates, or Payroll money.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-shifts-wave2b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave2b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/shifts-w2b-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-integrity-wave2b-synthetic.conf
# Keep Wave 1B drop-in; Wave 2B adds a layered drop-in (later lexical order wins for duplicates).
DASH_DIST=/opt/wathefni/dashboard-dist
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,jobs,cleanup,rollback} \
  "$BACKUP"/{modules,dashboard-dist,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/shifts_authority_wave1.py" 2>/dev/null || true
  ls -la "$ORCH/shifts_schedule_integrity_wave2.py" 2>&1 || echo "shifts_schedule_integrity_wave2.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'SHIFTS_|CAPTURE_INGEST' \
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
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/fingerprints-before.json"
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
        def count(sql):
            cur.execute(sql); return int(dict(cur.fetchone())["n"])
        out={
          "db":db,
          "assignment_count":len(assigns),
          "assignment_fps":{a["shift_id"]:a["fp"] for a in assigns},
          "orphan_fps":{a["shift_id"]:a["fp"] for a in assigns if a["shift_id"] in ORPHANS},
          "event_count": count("SELECT count(*) AS n FROM shift_events WHERE company_code='WATHEFNI'"),
          "swap_count": count("SELECT count(*) AS n FROM shift_swap_requests WHERE company_code='WATHEFNI'"),
          "availability_count": count("SELECT count(*) AS n FROM employee_availability_requests WHERE company_code='WATHEFNI'"),
        }
        for tbl,key in (
          ("shift_assignment_versions","version_count"),
          ("shift_reminder_queue","reminder_count"),
          ("shift_seasonal_policies","seasonal_count"),
          ("shift_reconciliation_flags","recon_count"),
        ):
            try:
                out[key]=count(f"SELECT count(*) AS n FROM {tbl} WHERE company_code='WATHEFNI'")
            except Exception:
                out[key]=None
                conn.rollback()
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
for m in shifts_authority_wave1.py shifts_schedule_integrity_wave2.py; do
  [[ -f "$ORCH/$m" ]] && cp -a "$ORCH/$m" "$BACKUP/modules/" || true
done
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
for tbl in shift_swap_requests employee_availability_requests; do
  sudo -u postgres psql -d wathefni -c "COPY (SELECT * FROM $tbl WHERE company_code='WATHEFNI') TO STDOUT WITH CSV HEADER" \
    > "$BACKUP/${tbl}.csv" || true
done
for tbl in shift_assignment_versions shift_reminder_queue shift_seasonal_policies shift_reconciliation_flags; do
  sudo -u postgres psql -d wathefni -c "COPY (SELECT * FROM $tbl WHERE company_code='WATHEFNI') TO STDOUT WITH CSV HEADER" \
    > "$BACKUP/${tbl}.csv" 2>/dev/null || echo "(table absent)" > "$BACKUP/${tbl}.csv"
done
(
  cd "$BACKUP"
  sha256sum app.py shift-assignments.csv shift-events.csv 2>/dev/null || true
  find modules dashboard-dist systemd-dropins -type f 2>/dev/null | head -300 | while read -r f; do sha256sum "$f"; done
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"
cp -a "$BACKUP/SHA256SUMS" "$REMOTE_EVID/backup/"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-integrity-wave2b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ -f "$BACKUP_DIR/modules/shifts_authority_wave1.py" ]]; then
  cp -a "$BACKUP_DIR/modules/shifts_authority_wave1.py" "$ORCH/"
fi
if [[ -f "$BACKUP_DIR/modules/shifts_schedule_integrity_wave2.py" ]]; then
  cp -a "$BACKUP_DIR/modules/shifts_schedule_integrity_wave2.py" "$ORCH/"
else
  rm -f "$ORCH/shifts_schedule_integrity_wave2.py"
fi
rm -f "$DROPIN"
# Restore other drop-ins from backup if present
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  mkdir -p /etc/systemd/system/wathefni-orchestrator.service.d
  # Do not wipe Wave 1B drop-in if it existed in backup
  cp -a "$BACKUP_DIR/systemd-dropins/." /etc/systemd/system/wathefni-orchestrator.service.d/ || true
  rm -f "$DROPIN"
fi
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
for f in app.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py \
         canary-prod-shifts-wave2b.py \
         smoke-test-shifts-authority-wave1.py \
         smoke-test-shifts-schedule-integrity-wave2.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql" "$ORCH/ops/runbooks"
[[ -f "$STAGE/migrate-shifts-schedule-integrity-wave2-prod.sh" ]] && cp -a "$STAGE/migrate-shifts-schedule-integrity-wave2-prod.sh" "$ORCH/ops/" && chmod +x "$ORCH/ops/migrate-shifts-schedule-integrity-wave2-prod.sh"
[[ -f "$STAGE/shifts_schedule_integrity_wave2_v1.sql" ]] && cp -a "$STAGE/shifts_schedule_integrity_wave2_v1.sql" "$ORCH/ops/sql/"
[[ -f "$STAGE/shifts-wave2b-operator-jobs.md" ]] && cp -a "$STAGE/shifts-wave2b-operator-jobs.md" "$ORCH/ops/runbooks/"
[[ -f "$STAGE/run-shifts-wave2b-jobs.sh" ]] && cp -a "$STAGE/run-shifts-wave2b-jobs.sh" "$ORCH/ops/" && chmod +x "$ORCH/ops/run-shifts-wave2b-jobs.sh"

log "writing Wave 2B synthetic-only drop-in (keeps Wave 1B + extends markers)"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW2B,SHW2B-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965530
Environment=WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2B,SHW2B-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965530
Environment=WATHEFNI_SHIFTS_INTEGRITY_JOBS=1
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF

log "migrate Wave 2 schema"
ACK_PRODUCTION_SHIFTS_W2B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-shifts-schedule-integrity-wave2-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/shifts_authority_wave1.py" "$ORCH/shifts_schedule_integrity_wave2.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'SHIFTS_|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/shifts-integrity-flags.txt"
import os, shifts_schedule_integrity_wave2 as w2, shifts_authority_wave1 as s
print("WAVE2", os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_WAVE2"))
print("W2_COMPANIES", os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_COMPANIES"))
print("W2_SYNTHETIC_ONLY", os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY"))
print("W2_MARKERS", os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS"))
print("W2_PHONES", os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES"))
print("W2_JOBS", os.environ.get("WATHEFNI_SHIFTS_INTEGRITY_JOBS"))
print("WAVE1", os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_WAVE1"))
print("W1_SYNTHETIC_ONLY", os.environ.get("WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY"))
print("CAPTURE_INGEST", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"))
print("w2_version", w2.SHIFTS_WAVE2_VERSION)
assert w2.shifts_wave2_enabled()
assert w2.shifts_wave2_synthetic_only()
assert "WATHEFNI" in w2.shifts_wave2_companies()
assert "SHW2B" in w2.wave2_synthetic_key_markers()
assert "965530" in w2.wave2_synthetic_phone_prefixes()
assert s.shifts_wave1_enabled() and s.shifts_authority_synthetic_only()
assert "SHW2B" in s.synthetic_key_markers()
assert "965530" in s.synthetic_phone_prefixes()
print("flags_ok_synthetic=true")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
