#!/usr/bin/env bash
# Leave Wave 1B — production WATHEFNI synthetic authority canary deploy.
# Deploys Wave 1 leave authority; enables SYNTHETIC_ONLY only.
# Keeps balances observe-only / enforced=false. No UI redesign. No real leave decisions.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-leave-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/leave-wave1b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/leave-w1b-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-leave-authority-wave1b-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests} "$BACKUP"/modules "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" || true
  ls -la "$ORCH/leave_authority_wave1.py" 2>&1 || echo "leave_authority_wave1.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'LEAVE|BALANCES|ATTENDANCE_CAPTURE_INGEST|ONBOARDING_SEED|EMPLOYEE_LIFECYCLE_V3_SYNTHETIC' \
    | sort || true
  echo "=== accrual timer ==="
  systemctl is-enabled wathefni-leave-accrual.timer || true
  systemctl show wathefni-leave-accrual.timer -p ActiveState,SubState,NextElapseUSecRealtime || true
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
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/leave-fingerprints-before.json"
import json, app
REAL_FPS = {
  "e3217e0e-466f-4f38-aa10-dab503dcb0a4": "abf4cba7cb8702b2d7c067db795d0701",
  "51cd940f-a04b-4ad1-9a6a-43e3da59a222": "8f6d67e3cc4fbf5ee321af235ecbb20d",
  "dbf82ecf-7ac4-451b-b41c-03de943f2161": "34c7cf18a4d758698bbf7cac6da70d1f",
}
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
        cur.execute("""
          SELECT leave_id::text, employee_key, leave_type, status, start_date::text, end_date::text,
                 md5(leave_id::text||coalesce(employee_key,'')||coalesce(leave_type,'')||coalesce(status,'')||coalesce(start_date::text,'')||coalesce(end_date::text,'')) AS fp
          FROM leave_requests WHERE company_code='WATHEFNI' ORDER BY leave_id::text
        """)
        rows=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) AS n FROM leave_events WHERE company_code='WATHEFNI'"); ev=int(dict(cur.fetchone())["n"])
        cur.execute("SELECT COUNT(*) AS n FROM leave_ledger WHERE company_code='WATHEFNI'"); led=int(dict(cur.fetchone())["n"])
        cur.execute("SELECT COUNT(*) AS n FROM leave_balances WHERE company_code='WATHEFNI'"); bal=int(dict(cur.fetchone())["n"])
        cur.execute("SELECT leave_type, enforced, legal_reviewed FROM leave_policies WHERE company_code='WATHEFNI' ORDER BY 1")
        pols=[dict(r) for r in cur.fetchall()]
out={"db":db,"leave_requests":rows,"leave_events":ev,"leave_ledger":led,"leave_balances":bal,"policies":pols}
assert len(rows)==3, rows
for r in rows:
    assert REAL_FPS.get(r["leave_id"])==r["fp"], (r, REAL_FPS.get(r["leave_id"]))
for p in pols:
    assert p["enforced"] is False and p["legal_reviewed"] is False
print(json.dumps(out, indent=2, default=str))
PY

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up orchestrator modules + leave fingerprints"
cp -a "$ORCH/app.py" "$BACKUP/app.py"
for f in leave_authority_wave1.py employee_lifecycle_wave3c.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
sudo -u postgres psql -d wathefni -c "COPY (
  SELECT leave_id, employee_key, leave_type, status, start_date, end_date,
         md5(leave_id::text||coalesce(employee_key,'')||coalesce(leave_type,'')||coalesce(status,'')||coalesce(start_date::text,'')||coalesce(end_date::text,'')) AS fp
  FROM leave_requests WHERE company_code='WATHEFNI' ORDER BY leave_id
) TO STDOUT WITH CSV HEADER" > "$BACKUP/leave-requests-fingerprint.csv"
sudo -u postgres psql -d wathefni -c "COPY (
  SELECT employee_key, leave_type, period_year, entitlement_days, accrued_to_date, consumed, current_balance
  FROM leave_balances WHERE company_code='WATHEFNI' ORDER BY employee_key, leave_type, period_year
) TO STDOUT WITH CSV HEADER" > "$BACKUP/leave-balances-fingerprint.csv"
sudo -u postgres psql -d wathefni -c "COPY (
  SELECT entry_id, employee_key, leave_type, entry_kind, days, leave_id
  FROM leave_ledger WHERE company_code='WATHEFNI' ORDER BY entry_id
) TO STDOUT WITH CSV HEADER" > "$BACKUP/leave-ledger-fingerprint.csv"

(
  cd "$BACKUP"
  sha256sum app.py leave-requests-fingerprint.csv leave-balances-fingerprint.csv leave-ledger-fingerprint.csv 2>/dev/null || true
  find modules -type f 2>/dev/null | while read -r f; do sha256sum "$f"; done
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-leave-authority-wave1b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ -d "$BACKUP_DIR/modules" ]]; then
  # Remove wave1 module if it was absent pre-deploy
  if [[ ! -f "$BACKUP_DIR/modules/leave_authority_wave1.py" ]]; then
    rm -f "$ORCH/leave_authority_wave1.py"
  fi
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  # restore dropins snapshot without re-adding removed leave dropin
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

log "deploying leave authority modules"
for f in app.py leave_authority_wave1.py employee_lifecycle_wave3c.py \
         canary-prod-leave-authority-wave1b.py \
         smoke-test-leave-authority-wave1.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         ops/migrate-leave-authority-wave1-prod.sh \
         ops/sql/leave_authority_wave1_v1.sql; do
  if [[ -f "$STAGE/$f" ]]; then
    mkdir -p "$ORCH/$(dirname "$f")"
    cp -a "$STAGE/$f" "$ORCH/$f"
  elif [[ -f "$STAGE/$(basename "$f")" && "$(basename "$f")" == *.py ]]; then
    cp -a "$STAGE/$(basename "$f")" "$ORCH/$(basename "$f")"
  fi
done
# Flat stage copies
for f in app.py leave_authority_wave1.py employee_lifecycle_wave3c.py canary-prod-leave-authority-wave1b.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql"
[[ -f "$STAGE/migrate-leave-authority-wave1-prod.sh" ]] && cp -a "$STAGE/migrate-leave-authority-wave1-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/leave_authority_wave1_v1.sql" ]] && cp -a "$STAGE/leave_authority_wave1_v1.sql" "$ORCH/ops/sql/"

log "writing synthetic-only drop-in"
# Preserve attendance markers and append LVW1B so leave-derived attendance works for canary synthetics.
ATT_MARKERS="ATTW1C,ATTW2C,ATTW2E,ATTW2G,ATTW3,ATTW4B,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|,W2G-SYNTH|,W3-SYNTH|,LVW1B,LVW1B-SYNTH|"
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_LEAVE_AUTHORITY=on
Environment=WATHEFNI_LEAVE_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY=on
Environment=WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS=LVW1B,LVW1B-SYNTH|
Environment=WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965525
Environment=WATHEFNI_LEAVE_BALANCES=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=${ATT_MARKERS}
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524,965525
EOF

log "migrate schema 1.0.0"
chmod +x "$ORCH/ops/migrate-leave-authority-wave1-prod.sh"
ACK_PRODUCTION_LEAVE_W1B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-leave-authority-wave1-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/leave_authority_wave1.py" "$ORCH/employee_lifecycle_wave3c.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'LEAVE|BALANCES|ATTENDANCE_AUTHORITY_SYNTHETIC|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/leave-authority-flags.txt"
import os, leave_authority_wave1 as w
print("LEAVE_AUTHORITY", os.environ.get("WATHEFNI_LEAVE_AUTHORITY"))
print("SYNTHETIC_ONLY", w.leave_authority_synthetic_only())
print("enabled", w.leave_authority_enabled())
print("companies", sorted(w.leave_authority_companies()))
assert w.leave_authority_enabled()
assert w.leave_authority_synthetic_only()
assert "WATHEFNI" in w.leave_authority_companies()
print("flags_ok_synthetic=true")
PY

# Accrual timer unchanged
systemctl is-enabled wathefni-leave-accrual.timer | tee "$REMOTE_EVID/verify/accrual-timer.txt"
systemctl is-active wathefni-leave-accrual.timer | tee -a "$REMOTE_EVID/verify/accrual-timer.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
