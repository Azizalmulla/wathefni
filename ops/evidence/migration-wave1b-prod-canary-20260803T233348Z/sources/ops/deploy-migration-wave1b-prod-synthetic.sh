#!/usr/bin/env bash
# Migration Wave 1-B — production WATHEFNI synthetic deploy.
# Foundation module + schema ACK + env wiring. No UI. Ingest off. No Wave 2.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-migration-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/migration-wave1b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/migration-w1b-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzz-migration-wave1b-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests} \
  "$BACKUP"/{modules,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/migration_wave1_cv_foundation.py" "$ORCH/smoke-test-migration-wave1.py" 2>/dev/null || true
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'MIGRATION_WAVE1|CAPTURE_INGEST|ASSISTANT_MUTATIONS|DASHBOARD_DIST' | sort || true
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

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up modules + dropins"
mkdir -p "$BACKUP/modules"
for f in app.py migration_wave1_cv_foundation.py smoke-test-migration-wave1.py canary-prod-migration-wave1b.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
(
  cd "$BACKUP"
  find modules -type f 2>/dev/null | while read -r f; do sha256sum "$f"; done
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzz-migration-wave1b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  # Restore prior modules if present; otherwise remove Wave 1-B-only files when absent from backup.
  for f in app.py migration_wave1_cv_foundation.py smoke-test-migration-wave1.py canary-prod-migration-wave1b.py; do
    if [[ -f "$BACKUP_DIR/modules/$f" ]]; then
      cp -a "$BACKUP_DIR/modules/$f" "$ORCH/$f"
    else
      rm -f "$ORCH/$f"
    fi
  done
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
  rm -f "$DROPIN"
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

log "deploying migration wave1 modules"
mkdir -p "$ORCH/ops"
for f in app.py migration_wave1_cv_foundation.py smoke-test-migration-wave1.py canary-prod-migration-wave1b.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py \
         smoke-test-compliance-freeze-regression.py \
         smoke-test-action-inbox-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
[[ -f "$STAGE/migrate-migration-wave1-prod.sh" ]] && cp -a "$STAGE/migrate-migration-wave1-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/deploy-migration-wave1b-prod-synthetic.sh" ]] && cp -a "$STAGE/deploy-migration-wave1b-prod-synthetic.sh" "$ORCH/ops/"

log "preflight orphan / queue residual"
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/migration-queue-residual.txt"
import app
active = ("pending", "running", "retrying", "waiting_quota", "waiting_budget")
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)::int AS c
            FROM intake_processing_jobs
            WHERE company_code='WATHEFNI'
              AND job_type='cv_extraction'
              AND coalesce(payload->>'source_channel','')='other_ats_export'
              AND status=ANY(%s)
            """,
            (list(active),),
        )
        residual = int(cur.fetchone()["c"])
print("active_other_ats_export_jobs", residual)
assert residual == 0, f"REFUSE active_other_ats_export_jobs={residual}"
print("MIGRATION_QUEUE_PREFLIGHT_OK")
PY

log "writing Wave 1-B production drop-in (synthetic-only; WATHEFNI; ingest off)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_MIGRATION_WAVE1=1
Environment=WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY=1
Environment=WATHEFNI_MIGRATION_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ASSISTANT_MUTATIONS=0
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/migration-wave1b-synthetic.conf"

log "migrate ACK"
chmod +x "$ORCH/ops/migrate-migration-wave1-prod.sh"
PID_PRE=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID_PRE"/environ
export WATHEFNI_ENV=production
export WATHEFNI_MIGRATION_WAVE1=1
export WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY=1
export WATHEFNI_MIGRATION_WAVE1_COMPANIES=WATHEFNI
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
export WATHEFNI_ASSISTANT_MUTATIONS=0
ACK_PRODUCTION_MIGRATION_WAVE1B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-migration-wave1-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/migration_wave1_cv_foundation.py" "$ORCH/canary-prod-migration-wave1b.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'MIGRATION_WAVE1|CAPTURE_INGEST|ASSISTANT_MUTATIONS' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/migration-wave1b-flags.txt"
import os
import migration_wave1_cv_foundation as mig
print("MIGRATION_WAVE1", os.environ.get("WATHEFNI_MIGRATION_WAVE1"))
print("SYNTHETIC_ONLY", os.environ.get("WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY"))
print("COMPANIES", os.environ.get("WATHEFNI_MIGRATION_WAVE1_COMPANIES"))
print("CAPTURE_INGEST", os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"))
assert mig.migration_wave1_enabled()
assert mig.migration_wave1_synthetic_only()
assert mig.company_allowed("WATHEFNI")
assert not mig.company_allowed("NOTALLOWED")
assert os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off").lower() in {"off", "0", "false", "no", ""}
print("MIGW1B_MARKER=MIGW1B")
print("flags_ok_migration_wave1b=true")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
