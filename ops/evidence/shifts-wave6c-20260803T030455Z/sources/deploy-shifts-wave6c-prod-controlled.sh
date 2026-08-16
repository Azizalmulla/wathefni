#!/usr/bin/env bash
# Shifts Wave 6C — production WATHEFNI controlled real rollout deploy.
#
# Owner-approved scope (2026-08-03):
#   HR allowlist      96599338566 (Aziz Almulla) — the ONLY actor that may mutate real shifts
#   Manager allowlist EMPTY — real scoped-manager rollout is NO-GO (no manager identity exists)
#   Real notify       WATHEFNI-96550252254 (Talal Fadhli) only, channels app + email
#   Excluded subjects WATHEFNI-ORPHAN-* and *-REALBLOCK-* (residue, never mutated or notified)
#
# WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY moves 1 -> 0 so Wave 1 authority can evaluate real
# employees. Safety comes from the actor allowlist + real mutation gate, not from that flag.
#
# Keeps off: broad employee app, real reminders, operator timers, integrity jobs,
# PAM submission, Payroll money, Attendance capture ingest.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-shifts-wave6c-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave6c-prod-controlled/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/shifts-w6c-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzz-shifts-wave6c-controlled.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
PYBIN="$ORCH/.venv/bin/python"

HR_ALLOWLIST="${W6C_HR_ALLOWLIST:-96599338566}"
NOTIFY_ALLOWLIST="${W6C_NOTIFY_ALLOWLIST:-WATHEFNI-96550252254}"
NOTIFY_CHANNELS="${W6C_NOTIFY_CHANNELS:-app,email}"
EXCLUDED="${W6C_EXCLUDED_SUBJECTS:-WATHEFNI-ORPHAN-,-REALBLOCK-}"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,canary,tests,cleanup,rollback,ui} \
  "$BACKUP"/{modules,dashboard-dist,systemd-dropins,sql} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

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
unset DATABASE_URL || true

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "hr_allowlist=$HR_ALLOWLIST"
  echo "notify_allowlist=$NOTIFY_ALLOWLIST"
  echo "notify_channels=$NOTIFY_CHANNELS"
  echo "excluded_subjects=$EXCLUDED"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" \
    "$ORCH/shifts_enterprise_wave6.py" \
    "$ORCH/shifts_notifications_wave6b.py" \
    "$ORCH/shifts_synthetic_cleanup.py" \
    "$ORCH/shifts_wave3_controlled.py" 2>/dev/null || true
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'SHIFTS_|CAPTURE_INGEST|EMPLOYEE_APP|DELIVERY_MODE|OUTBOUND' \
    | sort || true
} | tee "$REMOTE_EVID/preflight/before-deploy.txt"

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "fingerprint real (non-SHW6C) schedule lineage before deploy"
cd "$ORCH"
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/fingerprints-before.json"
import json, hashlib, app
def fp(rows):
  return hashlib.md5(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
    cur.execute("""
      SELECT shift_id::text, employee_key, shift_date::text, start_time::text, end_time::text,
             status, updated_at::text
      FROM shift_assignments WHERE company_code='WATHEFNI'
        AND coalesce(employee_key,'') NOT LIKE '%%SHW6C%%'
      ORDER BY shift_id::text
    """)
    assigns=[dict(r) for r in cur.fetchall()]
    cur.execute("""
      SELECT employee_key, coalesce(name,'') name, coalesce(phone,'') phone,
             coalesce(email,'') email, coalesce(employment_status,'') employment_status
      FROM employees WHERE company_code='WATHEFNI' ORDER BY employee_key
    """)
    emps=[dict(r) for r in cur.fetchall()]
    cur.execute("SELECT count(*) AS c FROM shift_orphan_quarantine WHERE company_code='WATHEFNI'")
    orphans=dict(cur.fetchone())["c"]
print(json.dumps({
  "db": db,
  "assignment_count": len(assigns),
  "assignment_fp": fp(assigns),
  "employee_count": len(emps),
  "employee_fp": fp(emps),
  "orphan_quarantine": orphans,
}, indent=2))
PY

log "backing up code + config + table dumps"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
for m in shifts_controlled_wave6c.py shifts_enterprise_wave6.py shifts_notifications_wave6b.py \
         shifts_publish_wave5.py shifts_templates_wave4.py shifts_synthetic_cleanup.py \
         shifts_wave3_controlled.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py \
         canary-prod-shifts-wave6c.py canary-prod-shifts-wave6b.py canary-prod-shifts-wave5b.py \
         canary-prod-shifts-wave4b.py canary-prod-shifts-wave3b.py canary-prod-shifts-wave2b.py \
         canary-prod-shifts-wave1b.py; do
  [[ -f "$ORCH/$m" ]] && cp -a "$ORCH/$m" "$BACKUP/modules/" || true
done
for s in shifts_controlled_wave6c_v1.sql shifts_enterprise_wave6_v1.sql shifts_notifications_wave6b_v1.sql \
         shifts_publish_wave5_v1.sql shifts_templates_wave4_v1.sql; do
  [[ -f "$ORCH/ops/sql/$s" ]] && cp -a "$ORCH/ops/sql/$s" "$BACKUP/sql/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
if [[ -d "$DASH_DIST" ]]; then cp -a "$DASH_DIST/." "$BACKUP/dashboard-dist/"; fi
if [[ -d "$DASH_DIST_LEGACY" ]]; then
  mkdir -p "$BACKUP/dashboard-dist-legacy"
  cp -a "$DASH_DIST_LEGACY/." "$BACKUP/dashboard-dist-legacy/"
fi

export PGPASSWORD="${POSTGRES_PASSWORD:-${PGPASSWORD:-}}"
PGUSER_V="${POSTGRES_USER:-postgres}"
for t in shift_assignments shift_assignment_versions shift_notification_events \
         shift_notification_deliveries shift_notification_acks shift_channel_preferences \
         shift_notification_consent shift_controlled_exclusions shift_controlled_job_runs \
         employee_messages; do
  pg_dump -h 127.0.0.1 -p 5432 -U "$PGUSER_V" -d wathefni -t "$t" --data-only 2>/dev/null \
    > "$BACKUP/sql/${t}.sql" || echo "-- absent $t" > "$BACKUP/sql/${t}.sql"
done

echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzz-shifts-wave6c-controlled.conf
test -d "$BACKUP_DIR"
[[ -f "$BACKUP_DIR/app.py" ]] && cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
for m in shifts_controlled_wave6c.py shifts_enterprise_wave6.py shifts_notifications_wave6b.py \
         shifts_publish_wave5.py shifts_templates_wave4.py shifts_synthetic_cleanup.py \
         shifts_wave3_controlled.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py \
         canary-prod-shifts-wave6c.py; do
  [[ -f "$BACKUP_DIR/modules/$m" ]] && cp -a "$BACKUP_DIR/modules/$m" "$ORCH/" || true
done
# Removing the drop-in restores the Wave 6B synthetic-only posture: empty allowlists,
# real delivery off, authority synthetic-only back on.
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

log "deploying modules + canary + sql pack"
mkdir -p "$ORCH/ops/sql"
for f in app.py shifts_controlled_wave6c.py shifts_enterprise_wave6.py shifts_notifications_wave6b.py \
         shifts_publish_wave5.py shifts_templates_wave4.py shifts_synthetic_cleanup.py \
         shifts_wave3_controlled.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py \
         canary-prod-shifts-wave6c.py canary-prod-shifts-wave6b.py canary-prod-shifts-wave5b.py \
         canary-prod-shifts-wave4b.py canary-prod-shifts-wave3b.py canary-prod-shifts-wave2b.py \
         canary-prod-shifts-wave1b.py \
         smoke-test-shifts-freeze-regression.py smoke-test-shifts-enterprise-wave6.py \
         smoke-test-shifts-publish-wave5.py smoke-test-shifts-templates-wave4.py \
         smoke-test-shifts-wave3-ux.py smoke-test-shifts-authority-wave1.py \
         smoke-test-shifts-schedule-integrity-wave2.py \
         smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
for s in shifts_controlled_wave6c_v1.sql shifts_enterprise_wave6_v1.sql shifts_notifications_wave6b_v1.sql \
         shifts_publish_wave5_v1.sql shifts_templates_wave4_v1.sql; do
  [[ -f "$STAGE/ops/sql/$s" ]] && cp -a "$STAGE/ops/sql/$s" "$ORCH/ops/sql/"
done

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist"
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  echo DASHBOARD_DIST_DEPLOYED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
else
  echo DASHBOARD_DIST_UNCHANGED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
fi

log "ensure Wave 6C controlled schema (additive)"
cd "$ORCH"
"$PYBIN" - <<'PY'
import app, shifts_notifications_wave6b as n6, shifts_controlled_wave6c as w6c
with app.db_connect() as conn:
  with conn.cursor() as cur:
    n6.ensure_shifts_notifications_wave6b_schema(cur)
    w6c.ensure_shifts_wave6c_schema(cur)
  conn.commit()
print("SCHEMA_ENSURE_OK")
PY

log "recording controlled subject exclusions"
"$PYBIN" - <<'PY'
import app
rows = [
  ("WATHEFNI-ORPHAN-", "Wave 1 orphan-quarantine residue: looks real to the gate, is not a person"),
  ("-REALBLOCK-", "Deliberate real-denial probe employee; never a rollout subject"),
]
with app.db_connect() as conn:
  with conn.cursor() as cur:
    for pattern, reason in rows:
      cur.execute(
        """
        INSERT INTO shift_controlled_exclusions (company_code, subject_pattern, reason)
        VALUES ('WATHEFNI', %s, %s)
        ON CONFLICT (company_code, subject_pattern) DO UPDATE SET reason=EXCLUDED.reason
        """,
        (pattern, reason),
      )
  conn.commit()
print("EXCLUSIONS_RECORDED")
PY

log "writing Wave 6C controlled drop-in (named HR allowlist; one notify recipient; timers off)"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_SHIFTS_WAVE6C=1
Environment=WATHEFNI_SHIFTS_WAVE6C_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE6C_SYNTHETIC_KEY_MARKERS=SHW6C,SHW6C-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE6C_SYNTHETIC_PHONE_PREFIXES=965538
Environment=WATHEFNI_SHIFTS_HR_ALLOWLIST=${HR_ALLOWLIST}
Environment=WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_REAL_MUTATION_GATE=1
Environment=WATHEFNI_SHIFTS_NOTIFY_REAL_DELIVERY=1
Environment=WATHEFNI_SHIFTS_NOTIFY_REAL_ALLOWLIST=${NOTIFY_ALLOWLIST}
Environment=WATHEFNI_SHIFTS_NOTIFY_REAL_CHANNELS=${NOTIFY_CHANNELS}
Environment=WATHEFNI_SHIFTS_NOTIFY_KILL=0
Environment=WATHEFNI_SHIFTS_EXCLUDED_SUBJECTS=${EXCLUDED}
Environment=WATHEFNI_SHIFTS_CONTROLLED_JOBS=1
Environment=WATHEFNI_SHIFTS_OPERATOR_TIMERS=0
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=0
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW1,SHW1-SYNTH|,SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|,SHW6B,SHW6B-SYNTH|,SHW6C,SHW6C-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965528,965530,965531,965533,965535,965537,965538
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_KEY_MARKERS=SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|,SHW6B,SHW6B-SYNTH|,SHW6C,SHW6C-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_PHONE_PREFIXES=965531,965533,965535,965537,965538
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS=SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|,SHW6B,SHW6B-SYNTH|,SHW6C,SHW6C-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES=965533,965535,965537,965538
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS=SHW5B,SHW5B-SYNTH|,SHW6B,SHW6B-SYNTH|,SHW6C,SHW6C-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES=965535,965537,965538
Environment=WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS=SHW6B,SHW6B-SYNTH|,SHW6C,SHW6C-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES=965537,965538
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW2C,SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|,SHW6B,SHW6B-SYNTH|,SHW6C,SHW6C-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965529,965530,965531,965533,965535,965537,965538
Environment=WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
Environment=WATHEFNI_SHIFTS_REAL_REMINDERS=0
Environment=WATHEFNI_SHIFTS_NOTIFICATIONS_REAL_DELIVERY=0
Environment=WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254
Environment=WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST=on
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/shifts-wave6c-controlled.conf"
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
    | grep -E 'SHIFTS_|CAPTURE_INGEST|EMPLOYEE_APP|DELIVERY_MODE|OUTBOUND' \
    | sort || true
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/shifts_controlled_wave6c.py" "$ORCH/shifts_notifications_wave6b.py" \
    "$ORCH/shifts_enterprise_wave6.py" "$ORCH/shifts_synthetic_cleanup.py" 2>/dev/null || true
  echo "=== schema after ==="
  cd "$ORCH"
  unset DATABASE_URL || true
  "$PYBIN" - <<'PY'
import app
with app.db_connect() as conn:
  with conn.cursor() as cur:
    for t in ("shift_notification_consent","shift_controlled_exclusions","shift_controlled_job_runs"):
      cur.execute("SELECT to_regclass(%s) AS r", (t,))
      print(t, dict(cur.fetchone())["r"])
    cur.execute("""
      SELECT column_name FROM information_schema.columns
      WHERE table_name='shift_notification_deliveries'
        AND column_name IN ('real_sent','recipient_ref','provider_receipt')
      ORDER BY 1
    """)
    print("delivery_provenance_cols", [r["column_name"] for r in cur.fetchall()])
    cur.execute("SELECT subject_pattern FROM shift_controlled_exclusions WHERE company_code='WATHEFNI' ORDER BY 1")
    print("exclusions", [r["subject_pattern"] for r in cur.fetchall()])
PY
} | tee "$REMOTE_EVID/verify/after-deploy.txt"

echo DEPLOY_SHIFTS_W6C_OK
