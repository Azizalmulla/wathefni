#!/usr/bin/env bash
# Shifts Wave 5B — production WATHEFNI synthetic publish/open/coverage canary deploy.
# Requires staging Wave 5 GO. Synthetic SHW5B / 965535* only.
# Real allowlists empty. REAL_MUTATION_GATE on. REAL_REMINDERS off. Timers/jobs disabled.
# CAPTURE_INGEST stays off. No real publishing / real open-shift claims / rotations / PAM / Payroll money.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-shifts-wave5b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave5b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/shifts-w5b-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzz-shifts-wave5b-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,canary,tests,cleanup,rollback,ui} \
  "$BACKUP"/{modules,dashboard-dist,systemd-dropins,sql} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" \
    "$ORCH/shifts_publish_wave5.py" \
    "$ORCH/shifts_templates_wave4.py" \
    "$ORCH/shifts_synthetic_cleanup.py" \
    "$ORCH/shifts_wave3_controlled.py" \
    "$ORCH/shifts_authority_wave1.py" \
    "$ORCH/shifts_schedule_integrity_wave2.py" 2>/dev/null || true
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'SHIFTS_|CAPTURE_INGEST|DASHBOARD_DIST' \
    | sed 's/WATHEFNI_CAPTURE_CREDENTIAL_KEY=.*/WATHEFNI_CAPTURE_CREDENTIAL_KEY=[REDACTED]/' \
    | sort || true
  echo "=== schema before ==="
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
  export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
  export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
  export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
  unset DATABASE_URL || true
  cd "$ORCH"
  "$PYBIN" - <<'PY'
import app
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("SELECT current_database() AS db"); print("db", dict(cur.fetchone())["db"])
    for t in (
      "shift_schedule_periods","shift_schedule_versions","shift_schedule_draft_rows","shift_schedule_events",
      "shift_open_shifts","shift_open_shift_claims","shift_coverage_rules",
      "shift_templates","shift_recurrences",
    ):
      cur.execute("SELECT to_regclass(%s) AS r", (t,))
      print(t, dict(cur.fetchone())["r"])
    cur.execute("""
      SELECT column_name FROM information_schema.columns
      WHERE table_name='shift_assignments'
        AND column_name IN (
          'schedule_period_id','schedule_version_id','schedule_source',
          'source_kind','template_id','recurrence_id','occurrence_key','regen_detached'
        )
      ORDER BY 1
    """)
    print("provenance_cols", [r["column_name"] for r in cur.fetchall()])
PY
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
unset DATABASE_URL || true

cd "$ORCH"
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/fingerprints-before.json"
import json, hashlib, app
ORPHANS={"0a6e73dd-9c6d-49a0-b253-39a9922ebd70","6a84a671-eb7f-43ea-870e-af859a440467","f9ebecf3-8838-456a-8124-c34c3c7600ca"}
def fp(r):
  parts=[str(r.get(k) or "") for k in ("shift_id","employee_key","employee_phone","shift_date","start_time","end_time","status","updated_at","role","location","timezone","schedule_period_id","schedule_version_id","schedule_source")]
  return hashlib.md5("|".join(parts).encode()).hexdigest()
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
    cur.execute("""
      SELECT column_name FROM information_schema.columns
      WHERE table_name='shift_assignments' AND column_name='schedule_period_id'
    """)
    has_w5 = bool(cur.fetchone())
    if has_w5:
      cur.execute("""
        SELECT shift_id::text, employee_key, coalesce(employee_phone,'') employee_phone, shift_date::text,
               start_time::text, end_time::text, status, updated_at::text,
               coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone,
               coalesce(schedule_period_id::text,'') schedule_period_id,
               coalesce(schedule_version_id::text,'') schedule_version_id,
               coalesce(schedule_source,'') schedule_source
        FROM shift_assignments WHERE company_code='WATHEFNI'
          AND coalesce(employee_key,'') NOT LIKE '%%SHW5B%%'
          AND coalesce(employee_phone,'') NOT LIKE '965535%%'
        ORDER BY shift_id::text
      """)
    else:
      cur.execute("""
        SELECT shift_id::text, employee_key, coalesce(employee_phone,'') employee_phone, shift_date::text,
               start_time::text, end_time::text, status, updated_at::text,
               coalesce(role,'') role, coalesce(location,'') location, coalesce(timezone,'') timezone,
               '' schedule_period_id, '' schedule_version_id, '' schedule_source
        FROM shift_assignments WHERE company_code='WATHEFNI'
          AND coalesce(employee_key,'') NOT LIKE '%%SHW5B%%'
          AND coalesce(employee_phone,'') NOT LIKE '965535%%'
        ORDER BY shift_id::text
      """)
    assigns=[dict(r) for r in cur.fetchall()]
    for a in assigns: a["fp"]=fp(a)
    periods=[]; versions=[]; opens=[]; rules=[]
    try:
      cur.execute("SELECT to_regclass('shift_schedule_periods') AS r")
      if dict(cur.fetchone())["r"]:
        cur.execute("SELECT period_id::text, name, status, updated_at::text FROM shift_schedule_periods WHERE company_code='WATHEFNI' AND name NOT LIKE '%%SHW5B%%' ORDER BY 1")
        periods=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT version_id::text, period_id::text, state, version_no FROM shift_schedule_versions WHERE company_code='WATHEFNI' AND period_id IN (SELECT period_id FROM shift_schedule_periods WHERE company_code='WATHEFNI' AND name NOT LIKE '%%SHW5B%%') ORDER BY 1")
        versions=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT open_shift_id::text, status, shift_date::text FROM shift_open_shifts WHERE company_code='WATHEFNI' AND coalesce(notes,'') NOT LIKE '%%SHW5B%%' ORDER BY 1")
        opens=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT rule_id::text, name, enabled FROM shift_coverage_rules WHERE company_code='WATHEFNI' AND name NOT LIKE '%%SHW5B%%' ORDER BY 1")
        rules=[dict(r) for r in cur.fetchall()]
    except Exception as e:
      conn.rollback()
      print(json.dumps({"note":"wave5_tables_absent_pre_deploy","error":str(e)[:200]}), flush=True)
print(json.dumps({
  "db":db,
  "has_wave5_provenance": has_w5,
  "assignment_count":len(assigns),
  "assignment_fps":{a["shift_id"]:a["fp"] for a in assigns},
  "orphan_fps":{a["shift_id"]:a["fp"] for a in assigns if a["shift_id"] in ORPHANS},
  "period_count":len(periods),
  "version_count":len(versions),
  "open_shift_count":len(opens),
  "coverage_rule_count":len(rules),
}, indent=2))
PY

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "SHW2 seasonal hygiene before deploy"
"$PYBIN" - <<'PY'
import app
from shifts_synthetic_cleanup import CleanupScope, cleanup_synthetic_scope, wave2b_scope
r = cleanup_synthetic_scope(app.db_connect, CleanupScope(
  company_code="WATHEFNI", markers=("SHW2","SHW2-SYNTH|","SHW2C"),
  phone_prefixes=("965529","965530"), employee_json_flag="shw2",
  leave_reason_ilike="%shw2%", seasonal_name_ilike="%SHW2%",
))
print("shw2_hygiene_residual", r.get("residual_total"), "seasonal_deleted", (r.get("deleted") or {}).get("shift_seasonal_policies"))
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("UPDATE shift_seasonal_policies SET enabled=false WHERE company_code=%s AND name ILIKE %s AND enabled", ("WATHEFNI","%SHW2%"))
    print("disabled_remaining", cur.rowcount)
  conn.commit()
PY

log "backing up code + config + table dumps"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
for m in shifts_publish_wave5.py shifts_templates_wave4.py shifts_synthetic_cleanup.py shifts_wave3_controlled.py \
         shifts_authority_wave1.py shifts_schedule_integrity_wave2.py canary-prod-shifts-wave5b.py \
         canary-prod-shifts-wave4b.py canary-prod-shifts-wave3b.py canary-prod-shifts-wave2b.py canary-prod-shifts-wave1b.py; do
  [[ -f "$ORCH/$m" ]] && cp -a "$ORCH/$m" "$BACKUP/modules/" || true
done
[[ -f "$ORCH/ops/sql/shifts_publish_wave5_v1.sql" ]] && cp -a "$ORCH/ops/sql/shifts_publish_wave5_v1.sql" "$BACKUP/sql/" || true
[[ -f "$ORCH/ops/sql/shifts_templates_wave4_v1.sql" ]] && cp -a "$ORCH/ops/sql/shifts_templates_wave4_v1.sql" "$BACKUP/sql/" || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
if [[ -d "$DASH_DIST" ]]; then cp -a "$DASH_DIST/." "$BACKUP/dashboard-dist/"; fi
if [[ -d "$DASH_DIST_LEGACY" ]]; then
  mkdir -p "$BACKUP/dashboard-dist-legacy"
  cp -a "$DASH_DIST_LEGACY/." "$BACKUP/dashboard-dist-legacy/"
fi

set -a; source /root/.openclaw/secrets/postgres.env; set +a
export PGPASSWORD="${POSTGRES_PASSWORD:-${PGPASSWORD:-}}"
PGUSER_V="${POSTGRES_USER:-postgres}"
for t in shift_schedule_periods shift_schedule_versions shift_schedule_draft_rows shift_schedule_events \
         shift_open_shifts shift_open_shift_claims shift_coverage_rules \
         shift_templates shift_recurrences shift_recurrence_exceptions shift_recurrence_events; do
  pg_dump -h 127.0.0.1 -p 5432 -U "$PGUSER_V" -d wathefni -t "$t" --data-only 2>/dev/null \
    > "$BACKUP/sql/${t}.sql" || echo "-- absent $t" > "$BACKUP/sql/${t}.sql"
done
pg_dump -h 127.0.0.1 -p 5432 -U "$PGUSER_V" -d wathefni -t shift_assignments --data-only \
  > "$BACKUP/sql/shift_assignments.sql" 2>/dev/null || true

echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzz-shifts-wave5b-synthetic.conf
test -d "$BACKUP_DIR"
[[ -f "$BACKUP_DIR/app.py" ]] && cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
for m in shifts_publish_wave5.py shifts_templates_wave4.py shifts_synthetic_cleanup.py shifts_wave3_controlled.py \
         shifts_authority_wave1.py shifts_schedule_integrity_wave2.py canary-prod-shifts-wave5b.py; do
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

log "deploying modules + canary + sql pack"
mkdir -p "$ORCH/ops/sql"
for f in app.py shifts_publish_wave5.py shifts_templates_wave4.py shifts_synthetic_cleanup.py shifts_wave3_controlled.py \
         shifts_authority_wave1.py shifts_schedule_integrity_wave2.py \
         canary-prod-shifts-wave5b.py canary-prod-shifts-wave4b.py canary-prod-shifts-wave3b.py \
         canary-prod-shifts-wave2b.py canary-prod-shifts-wave1b.py \
         smoke-test-shifts-publish-wave5.py smoke-test-shifts-templates-wave4.py smoke-test-shifts-wave3-ux.py \
         smoke-test-shifts-authority-wave1.py smoke-test-shifts-schedule-integrity-wave2.py \
         smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
[[ -f "$STAGE/ops/sql/shifts_publish_wave5_v1.sql" ]] && cp -a "$STAGE/ops/sql/shifts_publish_wave5_v1.sql" "$ORCH/ops/sql/"
[[ -f "$STAGE/ops/sql/shifts_templates_wave4_v1.sql" ]] && cp -a "$STAGE/ops/sql/shifts_templates_wave4_v1.sql" "$ORCH/ops/sql/"
[[ -f "$STAGE/shifts_publish_wave5_v1.sql" ]] && cp -a "$STAGE/shifts_publish_wave5_v1.sql" "$ORCH/ops/sql/"

# Optional dashboard dist from stage
if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist (Publish & coverage tab)"
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  echo DASHBOARD_DIST_DEPLOYED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
else
  echo DASHBOARD_DIST_UNCHANGED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
fi

log "ensure Wave 4 + Wave 5 schema on production (additive)"
"$PYBIN" - <<'PY'
import app, shifts_templates_wave4 as w4, shifts_publish_wave5 as w5
with app.db_connect() as conn:
  with conn.cursor() as cur:
    w4.ensure_shifts_templates_wave4_schema(cur)
    w5.ensure_shifts_publish_wave5_schema(cur)
  conn.commit()
print("SCHEMA_ENSURE_OK")
PY

log "writing Wave 5B synthetic-only drop-in (W1–4 retained; allowlists empty; jobs/reminders off)"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
Environment=WATHEFNI_SHIFTS_WAVE5=1
Environment=WATHEFNI_SHIFTS_WAVE5_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS=SHW5B,SHW5B-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES=965535
Environment=WATHEFNI_SHIFTS_WAVE4=1
Environment=WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS=SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES=965533,965535
Environment=WATHEFNI_SHIFTS_WAVE4_DEFAULT_HORIZON_DAYS=90
Environment=WATHEFNI_SHIFTS_WAVE3=1
Environment=WATHEFNI_SHIFTS_WAVE3_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_REAL_MUTATION_GATE=1
Environment=WATHEFNI_SHIFTS_HR_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_REAL_REMINDERS=0
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_KEY_MARKERS=SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_PHONE_PREFIXES=965531,965533,965535
Environment=WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW1,SHW1-SYNTH|,SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965528,965530,965531,965533,965535
Environment=WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW2C,SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|,SHW5B,SHW5B-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965529,965530,965531,965533,965535
Environment=WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/shifts-wave5b-synthetic.conf"
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
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/shifts_publish_wave5.py" "$ORCH/shifts_templates_wave4.py" "$ORCH/shifts_synthetic_cleanup.py" 2>/dev/null || true
  echo "=== schema after ==="
  cd "$ORCH"
  unset DATABASE_URL || true
  "$PYBIN" - <<'PY'
import app
with app.db_connect() as conn:
  with conn.cursor() as cur:
    for t in (
      "shift_schedule_periods","shift_schedule_versions","shift_schedule_draft_rows",
      "shift_open_shifts","shift_open_shift_claims","shift_coverage_rules",
    ):
      cur.execute("SELECT to_regclass(%s) AS r", (t,))
      print(t, dict(cur.fetchone())["r"])
    cur.execute("""
      SELECT column_name FROM information_schema.columns
      WHERE table_name='shift_assignments'
        AND column_name IN ('schedule_period_id','schedule_version_id','schedule_source')
      ORDER BY 1
    """)
    print("w5_l0_cols", [r["column_name"] for r in cur.fetchall()])
PY
} | tee "$REMOTE_EVID/verify/after-deploy.txt"

echo DEPLOY_SHIFTS_W5B_OK
