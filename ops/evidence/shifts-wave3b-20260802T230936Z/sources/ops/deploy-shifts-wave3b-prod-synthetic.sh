#!/usr/bin/env bash
# Shifts Wave 3B — production WATHEFNI synthetic UX canary deploy.
# Requires staging create-path GO. Synthetic SHW3B / 965531* only.
# Real allowlists empty. REAL_MUTATION_GATE on. REAL_REMINDERS off. Timers disabled.
# CAPTURE_INGEST stays off. No templates / Payroll money.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-shifts-wave3b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave3b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/shifts-w3b-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzz-shifts-wave3b-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,canary,tests,cleanup,rollback,screenshots,browser} \
  "$BACKUP"/{modules,dashboard-dist,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/shifts_wave3_controlled.py" 2>/dev/null || true
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
ORPHANS={"0a6e73dd-9c6d-49a0-b253-39a9922ebd70","6a84a671-eb7f-43ea-870e-af859a440467","f9ebecf3-8838-456a-8124-c34c3c7600ca"}
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
print(json.dumps({"db":db,"assignment_count":len(assigns),"assignment_fps":{a["shift_id"]:a["fp"] for a in assigns},"orphan_fps":{a["shift_id"]:a["fp"] for a in assigns if a["shift_id"] in ORPHANS}}, indent=2))
PY

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
for m in shifts_authority_wave1.py shifts_schedule_integrity_wave2.py shifts_wave3_controlled.py shifts_synthetic_cleanup.py; do
  [[ -f "$ORCH/$m" ]] && cp -a "$ORCH/$m" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
if [[ -d "$DASH_DIST" ]]; then cp -a "$DASH_DIST/." "$BACKUP/dashboard-dist/"; fi
if [[ -d "$DASH_DIST_LEGACY" ]]; then
  mkdir -p "$BACKUP/dashboard-dist-legacy"
  cp -a "$DASH_DIST_LEGACY/." "$BACKUP/dashboard-dist-legacy/"
fi
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzz-shifts-wave3b-synthetic.conf
test -d "$BACKUP_DIR"
[[ -f "$BACKUP_DIR/app.py" ]] && cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
for m in shifts_authority_wave1.py shifts_schedule_integrity_wave2.py shifts_wave3_controlled.py shifts_synthetic_cleanup.py; do
  [[ -f "$BACKUP_DIR/modules/$m" ]] && cp -a "$BACKUP_DIR/modules/$m" "$ORCH/" || true
done
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  mkdir -p /etc/systemd/system/wathefni-orchestrator.service.d
  cp -a "$BACKUP_DIR/systemd-dropins/." /etc/systemd/system/wathefni-orchestrator.service.d/ || true
  rm -f "$DROPIN"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rm -rf "$DASH_DIST"; mkdir -p "$DASH_DIST"; cp -a "$BACKUP_DIR/dashboard-dist/." "$DASH_DIST/"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist-legacy" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist-legacy" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_DIST_LEGACY"
  rsync -a --delete "$BACKUP_DIR/dashboard-dist-legacy/" "$DASH_DIST_LEGACY/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying modules + dashboard + canaries"
for f in app.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py shifts_wave3_controlled.py \
         shifts_synthetic_cleanup.py canary-prod-shifts-wave3b.py \
         smoke-test-shifts-wave3-ux.py smoke-test-shifts-authority-wave1.py \
         smoke-test-shifts-schedule-integrity-wave2.py \
         smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
if [[ -d "$STAGE/dashboard-dist" ]]; then
  mkdir -p "$DASH_DIST" "$DASH_DIST_LEGACY"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  # Production process default path when WATHEFNI_DASHBOARD_DIST unset historically
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST_LEGACY/"
fi
[[ -f "$STAGE/shifts-wave3b-prod-browser-canary.py" ]] && cp -a "$STAGE/shifts-wave3b-prod-browser-canary.py" "$ORCH/"

log "writing Wave 3B synthetic-only drop-in (extends Wave1/Wave2 markers; allowlists empty; gate on)"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
Environment=WATHEFNI_SHIFTS_WAVE3=1
Environment=WATHEFNI_SHIFTS_WAVE3_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_REAL_MUTATION_GATE=1
Environment=WATHEFNI_SHIFTS_HR_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_REAL_REMINDERS=0
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_KEY_MARKERS=SHW3B,SHW3B-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_PHONE_PREFIXES=965531
Environment=WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW1,SHW1-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965528,965530,965531
Environment=WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965530,965531
Environment=WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/shifts-wave3b-synthetic.conf"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && echo health_ok && break
  sleep 1
done
systemctl is-active wathefni-orchestrator | tee "$REMOTE_EVID/verify/service-active.txt"

{
  echo "=== flags after ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'SHIFTS_|CAPTURE_INGEST|DASHBOARD_DIST' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort || true
  sha256sum "$ORCH/app.py" "$ORCH/shifts_wave3_controlled.py" 2>/dev/null || true
  echo "=== served index scripts ==="
  curl -s http://127.0.0.1:8010/dashboard/ | grep -oE 'assets/[^"]+\.js' | head -5
} | tee "$REMOTE_EVID/verify/after-deploy.txt"

echo DEPLOY_SHIFTS_W3B_OK
