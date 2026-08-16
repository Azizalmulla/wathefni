#!/usr/bin/env bash
# Payroll Wave 1B — production WATHEFNI synthetic foundation deploy.
# Deploys Wave 1 payroll foundation; enables SYNTHETIC_ONLY only.
# Keeps payment_processing=disabled. No money, G2N, PIFSS, WPS, EOS, payslips, journals, XBRL.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-payroll-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave1b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/payroll-w1b-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-payroll-wave1b-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,quarantine,canary,tests} "$BACKUP"/modules "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" || true
  ls -la "$ORCH/payroll_authority_wave1.py" 2>&1 || echo "payroll_authority_wave1.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'PAYROLL|PAYMENT|ATTENDANCE_CAPTURE_INGEST|LEAVE_AUTHORITY|SHIFTS_AUTHORITY_WAVE1' \
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
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/smoke-timesheets-before.json"
import json, app
SMOKE_IDS = [
  "cc68a9fb-df72-4e13-a0db-cc13a3805380",
  "7950dafd-6cf7-44b1-9f92-26f685c34ab5",
]
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
        cur.execute("""
          SELECT column_name FROM information_schema.columns
          WHERE table_schema='public' AND table_name='payroll_timesheets'
            AND column_name IN ('quarantine_status','row_version')
        """)
        have = {dict(r)["column_name"] for r in cur.fetchall()}
        cols = "timesheet_id::text, employee_key, status, payroll_status, period_start::text, period_end::text, created_by_phone"
        if "quarantine_status" in have:
            cols += ", quarantine_status"
        cur.execute(f"""
          SELECT {cols}
          FROM payroll_timesheets
          WHERE company_code='WATHEFNI' AND timesheet_id::text = ANY(%s)
          ORDER BY timesheet_id::text
        """, (SMOKE_IDS,))
        rows=[dict(r) for r in cur.fetchall()]
out={"db":db,"smoke_timesheets":rows,"wave1_cols_present":sorted(have),"company_payment_processing":"disabled"}
assert len(rows)==2, rows
print(json.dumps(out, indent=2, default=str))
PY

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up orchestrator modules + smoke fingerprint"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
for f in payroll_authority_wave1.py tenant_control_roles.py tool_call_orchestrator.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
sudo -u postgres psql -d wathefni -c "COPY (
  SELECT timesheet_id, employee_key, status, payroll_status, period_start, period_end, created_by_phone
  FROM payroll_timesheets
  WHERE company_code='WATHEFNI'
    AND timesheet_id::text IN (
      'cc68a9fb-df72-4e13-a0db-cc13a3805380',
      '7950dafd-6cf7-44b1-9f92-26f685c34ab5'
    )
  ORDER BY timesheet_id
) TO STDOUT WITH CSV HEADER" > "$BACKUP/smoke-timesheets-before.csv"

(
  cd "$BACKUP"
  sha256sum app.py smoke-timesheets-before.csv 2>/dev/null || true
  find modules -type f 2>/dev/null | while read -r f; do sha256sum "$f"; done
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-payroll-wave1b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ -d "$BACKUP_DIR/modules" ]]; then
  if [[ ! -f "$BACKUP_DIR/modules/payroll_authority_wave1.py" ]]; then
    rm -f "$ORCH/payroll_authority_wave1.py"
  fi
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
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
# Note: smoke quarantine rows are intentionally NOT un-quarantined by rollback.
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying payroll wave1 modules"
for f in app.py payroll_authority_wave1.py tenant_control_roles.py tool_call_orchestrator.py \
         canary-prod-payroll-authority-wave1b.py \
         smoke-test-payroll-authority-wave1.py \
         smoke-test-multi-user-wave1-roles.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql"
[[ -f "$STAGE/migrate-payroll-authority-wave1-prod.sh" ]] && cp -a "$STAGE/migrate-payroll-authority-wave1-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/payroll_authority_wave1_v1.sql" ]] && cp -a "$STAGE/payroll_authority_wave1_v1.sql" "$ORCH/ops/sql/"

log "writing synthetic-only drop-in"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE1=1
Environment=WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS=PYW1,PYW1-SYNTH|
Environment=WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES=965539
EOF

log "migrate schema + quarantine smoke"
chmod +x "$ORCH/ops/migrate-payroll-authority-wave1-prod.sh"
ACK_PRODUCTION_PAYROLL_W1B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-payroll-authority-wave1-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"
cp -a "$REMOTE_EVID/schema/migrate.out" "$REMOTE_EVID/quarantine/migrate-quarantine.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/payroll_authority_wave1.py" "$ORCH/tenant_control_roles.py" "$ORCH/tool_call_orchestrator.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'PAYROLL|CAPTURE_INGEST|LEAVE_AUTHORITY=|SHIFTS_AUTHORITY_WAVE1=' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/payroll-wave1-flags.txt"
import os, payroll_authority_wave1 as w
print("PAYROLL_WAVE1", os.environ.get("WATHEFNI_PAYROLL_WAVE1"))
print("SYNTHETIC_ONLY", w.payroll_wave1_synthetic_only())
print("enabled", w.payroll_wave1_enabled())
print("company", w.payroll_wave1_enabled_for_company("WATHEFNI"))
print("markers", w.synthetic_key_markers())
print("prefixes", w.synthetic_phone_prefixes())
h = w.honesty_payload()
print("honesty", {k: h[k] for k in ("payment_processing","money_authority","synthetic_only","annual_leave_eligibility_months")})
assert w.payroll_wave1_enabled()
assert w.payroll_wave1_synthetic_only()
assert w.payroll_wave1_enabled_for_company("WATHEFNI")
assert h["payment_processing"] == "disabled"
assert h["money_authority"] is False
print("flags_ok_synthetic=true")
PY

"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/quarantine/smoke-after.json"
import json, app
SMOKE_IDS = [
  "cc68a9fb-df72-4e13-a0db-cc13a3805380",
  "7950dafd-6cf7-44b1-9f92-26f685c34ab5",
]
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
          SELECT timesheet_id::text, employee_key, status, payroll_status, quarantine_status
          FROM payroll_timesheets
          WHERE company_code='WATHEFNI' AND timesheet_id::text = ANY(%s)
          ORDER BY 1
        """, (SMOKE_IDS,))
        rows=[dict(r) for r in cur.fetchall()]
assert len(rows)==2
for r in rows:
    assert r["quarantine_status"]=="wave0_smoke_quarantined", r
    assert r["payroll_status"]=="quarantined", r
print(json.dumps({"quarantined": rows, "hard_deleted": False, "count": len(rows)}, indent=2))
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
