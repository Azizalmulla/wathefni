#!/usr/bin/env bash
# Leave Wave 4 — production deploy: UX controlled readiness + real-decision allowlist.
# Keeps enforced=false / legal_reviewed=false. SYNTHETIC_ONLY retained for authority canaries.
# Does NOT enable Payroll money or broaden employee-app allowlist.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-leave-wave4-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/leave-wave4/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/leave-w4-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzz-leave-wave4.conf
W1B_DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-leave-authority-wave1b-synthetic.conf
W2C_DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzz-leave-policy-wave2c.conf
W3B_DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzz-leave-workflow-wave3b.conf
PYBIN="$ORCH/.venv/bin/python"
# Dual-control needs ≥2 allowlisted phones
ALLOWLIST="${LEAVE_REAL_DECISION_ALLOWLIST:-96599338566,96588009911}"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests} "$BACKUP"/modules "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/leave_authority_wave1.py" "$ORCH/leave_policy_wave2.py" \
    "$ORCH/leave_workflow_wave3.py" "$ORCH/employee_lifecycle_wave3c.py" 2>/dev/null || true
  ls -la "$ORCH/leave_wave4_controlled.py" 2>&1 || echo "leave_wave4_controlled.py ABSENT"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'LEAVE|BALANCES|ATTENDANCE_CAPTURE_INGEST|EMPLOYEE_APP' \
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
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/leave-fingerprints-before.json"
import json, app
REAL_FPS = {
  "e3217e0e-466f-4f38-aa10-dab503dcb0a4": "abf4cba7cb8702b2d7c067db795d0701",
  "51cd940f-a04b-4ad1-9a6a-43e3da59a222": "8f6d67e3cc4fbf5ee321af235ecbb20d",
}
STALE_ID = "dbf82ecf-7ac4-451b-b41c-03de943f2161"
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
        cur.execute("""
          SELECT leave_id::text, employee_key, leave_type, status, start_date::text, end_date::text,
                 md5(leave_id::text||coalesce(employee_key,'')||coalesce(leave_type,'')||coalesce(status,'')||coalesce(start_date::text,'')||coalesce(end_date::text,'')) AS fp
          FROM leave_requests WHERE company_code='WATHEFNI' ORDER BY leave_id::text
        """)
        rows=[dict(r) for r in cur.fetchall()]
        reals=[r for r in rows if r["leave_id"] in REAL_FPS or r["leave_id"]==STALE_ID]
        cur.execute("SELECT COUNT(*) AS n FROM leave_events WHERE company_code='WATHEFNI'"); ev=int(dict(cur.fetchone())["n"])
        cur.execute("SELECT COUNT(*) AS n FROM leave_ledger WHERE company_code='WATHEFNI'"); led=int(dict(cur.fetchone())["n"])
        cur.execute("SELECT COUNT(*) AS n FROM leave_balances WHERE company_code='WATHEFNI'"); bal=int(dict(cur.fetchone())["n"])
        cur.execute("SELECT leave_type, enforced, legal_reviewed FROM leave_policies WHERE company_code='WATHEFNI' ORDER BY 1")
        pols=[dict(r) for r in cur.fetchall()]
out={"db":db,"leave_requests_all":len(rows),"real_leaves":reals,"leave_events":ev,"leave_ledger":led,"leave_balances":bal,"policies":pols}
for r in reals:
    if r["leave_id"] in REAL_FPS:
        assert REAL_FPS[r["leave_id"]]==r["fp"], (r, REAL_FPS[r["leave_id"]])
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
for f in leave_authority_wave1.py employee_lifecycle_wave3c.py leave_policy_wave2.py leave_workflow_wave3.py leave_wave4_controlled.py action_registry.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
echo "leave_wave4_absent_pre=$( [[ -f $ORCH/leave_wave4_controlled.py ]] && echo no || echo yes )" | tee "$BACKUP/pre-module-state.txt"
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzz-leave-wave4.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ ! -f "$BACKUP_DIR/modules/leave_wave4_controlled.py" ]]; then
  rm -f "$ORCH/leave_wave4_controlled.py"
fi
if [[ -d "$BACKUP_DIR/modules" ]]; then
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
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying wave4 modules from stage"
for f in app.py leave_wave4_controlled.py leave_workflow_wave3.py leave_policy_wave2.py leave_authority_wave1.py \
         employee_lifecycle_wave3c.py action_registry.py canary-prod-leave-wave4.py \
         smoke-test-leave-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops"
[[ -f "$STAGE/migrate-leave-wave4-prod.sh" ]] && cp -a "$STAGE/migrate-leave-wave4-prod.sh" "$ORCH/ops/"
mkdir -p /opt/wathefni/ops
[[ -f "$STAGE/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" ]] && \
  cp -a "$STAGE/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md" /opt/wathefni/ops/

log "writing wave4 drop-in (keeps wave1b + wave2c + wave3b)"
ATT_MARKERS="ATTW1C,ATTW2C,ATTW2E,ATTW2G,ATTW3,ATTW4B,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|,W2G-SYNTH|,W3-SYNTH|,LVW1B,LVW1B-SYNTH|,LVW2C,LVW2C-SYNTH|,LVW3B,LVW3B-SYNTH|,LVW4,LVW4-SYNTH|"
if [[ -f "$W1B_DROPIN" ]]; then
  cat > "$W1B_DROPIN" <<EOF
[Service]
Environment=WATHEFNI_LEAVE_AUTHORITY=on
Environment=WATHEFNI_LEAVE_AUTHORITY_COMPANIES=WATHEFNI
Environment=WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY=on
Environment=WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS=LVW1B,LVW1B-SYNTH|,LVW2C,LVW2C-SYNTH|,LVW3B,LVW3B-SYNTH|,LVW4,LVW4-SYNTH|
Environment=WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965525,965526,965527
Environment=WATHEFNI_LEAVE_BALANCES=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=${ATT_MARKERS}
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524,965525,965526,965527
EOF
fi
[[ -f "$W2C_DROPIN" ]] || cat > "$W2C_DROPIN" <<EOF
[Service]
Environment=WATHEFNI_LEAVE_POLICY_WAVE2=on
Environment=WATHEFNI_LEAVE_BALANCES=on
EOF
[[ -f "$W3B_DROPIN" ]] || cat > "$W3B_DROPIN" <<EOF
[Service]
Environment=WATHEFNI_LEAVE_WORKFLOW_WAVE3=on
Environment=WATHEFNI_LEAVE_POLICY_WAVE2=on
Environment=WATHEFNI_LEAVE_BALANCES=on
EOF
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_LEAVE_WAVE4=on
Environment=WATHEFNI_LEAVE_REAL_DECISION_GATE=on
Environment=WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST=${ALLOWLIST}
Environment=WATHEFNI_LEAVE_WORKFLOW_WAVE3=on
Environment=WATHEFNI_LEAVE_POLICY_WAVE2=on
Environment=WATHEFNI_LEAVE_BALANCES=on
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/zzzzzzz-leave-wave4.conf"
cp -a "$W1B_DROPIN" "$REMOTE_EVID/flags/" 2>/dev/null || true
cp -a "$W2C_DROPIN" "$REMOTE_EVID/flags/" 2>/dev/null || true
cp -a "$W3B_DROPIN" "$REMOTE_EVID/flags/" 2>/dev/null || true

log "migrate wave4 schema"
chmod +x "$ORCH/ops/migrate-leave-wave4-prod.sh"
ACK_PRODUCTION_LEAVE_W4=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-leave-wave4-prod.sh" \
  | tee "$REMOTE_EVID/schema/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/leave_wave4_controlled.py" "$ORCH/leave_workflow_wave3.py" \
    "$ORCH/leave_policy_wave2.py" "$ORCH/leave_authority_wave1.py" "$ORCH/employee_lifecycle_wave3c.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'LEAVE|BALANCES|CAPTURE_INGEST|EMPLOYEE_APP' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/wave4-live.txt"
import os, leave_wave4_controlled as w4, leave_workflow_wave3 as w3, leave_authority_wave1 as w1
assert os.environ.get("WATHEFNI_LEAVE_WAVE4","").lower() in {"on","1","true","yes"}
assert w4.leave_wave4_enabled()
assert w4.leave_real_decision_gate_enabled()
assert "96599338566" in w4.real_decision_allowlist() or len(w4.real_decision_allowlist()) >= 1
assert w3.leave_workflow_wave3_enabled()
flags=w1.honesty_balance_flags()
assert flags.get("balances_enforced") is False
assert flags.get("legal_reviewed") is False
print("wave4", w4.LEAVE_WAVE4_VERSION, "enabled", True)
print("allowlist", sorted(w4.real_decision_allowlist()))
print("honesty", flags)
print("flags_ok_wave4=true")
PY

systemctl is-enabled wathefni-leave-accrual.timer | tee "$REMOTE_EVID/verify/accrual-timer.txt"
systemctl is-active wathefni-leave-accrual.timer | tee -a "$REMOTE_EVID/verify/accrual-timer.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID allowlist=$ALLOWLIST"
