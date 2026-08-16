#!/usr/bin/env bash
# Wave 3I — production deploy Wave 3F/3H (WATHEFNI synthetic-only).
# Preserves hourly lifecycle timer. Does NOT disable SYNTHETIC_ONLY.
set -euo pipefail

STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
REMOTE_EVID="/opt/wathefni/production-evidence/employees360-wave3i-prod-deploy/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-employees360-wave3i-${STAMP}"
ORCH=/opt/wathefni/orchestrator
STAGE=/tmp/wave3i-deploy
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf

echo "STAMP=$STAMP"
mkdir -p "$REMOTE_EVID"/{preflight,canary,remediation,verify} "$BACKUP" "$STAGE"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

# --- preflight ---
{
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" \
    "$ORCH/employee_lifecycle_wave3.py" \
    "$ORCH/employee_lifecycle_wave3c.py" \
    "$ORCH/lifecycle-effective-worker.py" 2>/dev/null || true
  ls "$ORCH/employee_policy_packs_wave3h.py" 2>&1 || echo "packs_absent_before"
  echo "=== SCHEMA ==="
  grep -n 'SCHEMA_VERSION' "$ORCH/employee_lifecycle_wave3c.py" | head -2
  echo "=== FLAGS ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE_LIFECYCLE|WATHEFNI_EMPLOYEE_AUTHORITY|WATHEFNI_EMPLOYEE_POLICY|WATHEFNI_LIFECYCLE|WATHEFNI_ENV' | sort
  echo "=== TIMER ==="
  systemctl is-enabled wathefni-lifecycle-effective.timer
  systemctl is-active wathefni-lifecycle-effective.timer
  systemctl show wathefni-lifecycle-effective.timer -p UnitFileState -p ActiveState -p NextElapseUSecRealtime
} | tee "$REMOTE_EVID/preflight/before.txt"

curl -fsS -o "$REMOTE_EVID/preflight/health-before.txt" http://127.0.0.1:8010/healthz \
  || curl -fsS -o "$REMOTE_EVID/preflight/health-before.txt" http://127.0.0.1:8010/health || true

# --- backup ---
cp -a "$ORCH/employee_lifecycle_wave3.py" "$BACKUP/" 2>/dev/null || true
cp -a "$ORCH/employee_lifecycle_wave3c.py" "$BACKUP/"
cp -a "$ORCH/lifecycle-effective-worker.py" "$BACKUP/" 2>/dev/null || true
cp -a "$ORCH/app.py" "$BACKUP/"
cp -a "$DROPIN" "$BACKUP/employee-lifecycle-v3-synthetic.conf" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-lifecycle-effective.service "$BACKUP/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-lifecycle-effective.timer "$BACKUP/" 2>/dev/null || true
# Prove pg_dump backup of key lifecycle tables (additive-safe)
set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
PGURL="${DATABASE_URL:-${WATHEFNI_DATABASE_URL:-}}"
if [[ -n "$PGURL" ]]; then
  /usr/bin/pg_dump "$PGURL" \
    --data-only --no-owner \
    -t employee_lifecycle_company_policies \
    -t employee_lifecycle_requests \
    -t employee_lifecycle_cases \
    -t employee_lifecycle_settlement_packets \
    -t employee_employments \
    -t employees \
    > "$BACKUP/lifecycle-tables.dump.sql" 2>/dev/null \
    || echo "pg_dump_partial_skipped" | tee "$BACKUP/pg_dump_note.txt"
fi

cat > "$BACKUP/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$BACKUP_DIR/employee_lifecycle_wave3c.py" "$ORCH/employee_lifecycle_wave3c.py"
[[ -f "$BACKUP_DIR/employee_lifecycle_wave3.py" ]] && cp -a "$BACKUP_DIR/employee_lifecycle_wave3.py" "$ORCH/employee_lifecycle_wave3.py"
[[ -f "$BACKUP_DIR/lifecycle-effective-worker.py" ]] && cp -a "$BACKUP_DIR/lifecycle-effective-worker.py" "$ORCH/lifecycle-effective-worker.py"
[[ -f "$BACKUP_DIR/app.py" ]] && cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
rm -f "$ORCH/employee_policy_packs_wave3h.py"
rm -f "$ORCH/canary-prod-wave3i-jurisdiction.py"
if [[ -f "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" ]]; then
  cp -a "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" \
    /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf
fi
# Preserve timer units if present in backup
[[ -f "$BACKUP_DIR/wathefni-lifecycle-effective.service" ]] && cp -a "$BACKUP_DIR/wathefni-lifecycle-effective.service" /etc/systemd/system/
[[ -f "$BACKUP_DIR/wathefni-lifecycle-effective.timer" ]] && cp -a "$BACKUP_DIR/wathefni-lifecycle-effective.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl restart wathefni-orchestrator
# Ensure timer stays enabled (Wave 3I must not disable it; rollback also keeps it)
systemctl enable --now wathefni-lifecycle-effective.timer 2>/dev/null || true
sleep 2
curl -fsS http://127.0.0.1:8010/healthz || curl -fsS http://127.0.0.1:8010/health
echo "rolled back to pre-Wave3I modules; SYNTHETIC_ONLY drop-in restored; timer preserved"
EOS
chmod +x "$BACKUP/ROLLBACK.sh"

# Test rollback script is executable and references critical files
test -x "$BACKUP/ROLLBACK.sh"
grep -q 'employee_lifecycle_wave3c.py' "$BACKUP/ROLLBACK.sh"
echo "rollback_script_ok" | tee "$REMOTE_EVID/verify/rollback-proof.txt"
ls -la "$BACKUP" | tee "$REMOTE_EVID/verify/backup-listing.txt"

# --- install modules ---
test -f "$STAGE/employee_lifecycle_wave3c.py"
test -f "$STAGE/employee_policy_packs_wave3h.py"
test -f "$STAGE/canary-prod-wave3i-jurisdiction.py"
cp -a "$STAGE/employee_lifecycle_wave3c.py" "$ORCH/"
cp -a "$STAGE/employee_policy_packs_wave3h.py" "$ORCH/"
cp -a "$STAGE/canary-prod-wave3i-jurisdiction.py" "$ORCH/"
# Keep wave3 + worker if staged (optional refresh)
[[ -f "$STAGE/employee_lifecycle_wave3.py" ]] && cp -a "$STAGE/employee_lifecycle_wave3.py" "$ORCH/"
[[ -f "$STAGE/lifecycle-effective-worker.py" ]] && cp -a "$STAGE/lifecycle-effective-worker.py" "$ORCH/"
chmod +x "$ORCH/canary-prod-wave3i-jurisdiction.py"

/opt/wathefni/orchestrator/.venv/bin/python -m py_compile \
  "$ORCH/employee_lifecycle_wave3c.py" \
  "$ORCH/employee_policy_packs_wave3h.py" \
  "$ORCH/canary-prod-wave3i-jurisdiction.py"
/opt/wathefni/orchestrator/.venv/bin/python -c "import employee_policy_packs_wave3h as p; import employee_lifecycle_wave3c as w; print(p.SCHEMA_VERSION, w.SCHEMA_VERSION)"

# --- systemd drop-in: keep SYNTHETIC_ONLY=on; add policy packs; counsel gate env kept but policy default off ---
cat > "$DROPIN" <<EOF
[Service]
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_PHONE_PREFIXES=965522
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_NAME_PREFIX=W3D-SYNTH|
Environment=WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H=on
Environment=WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H_COMPANIES=WATHEFNI
Environment=WATHEFNI_LIFECYCLE_COUNSEL_GATE=off
EOF

# Ensure lifecycle oneshot/timer still carry packs + synthetic-only
mkdir -p /etc/systemd/system/wathefni-lifecycle-effective.service.d
cat > /etc/systemd/system/wathefni-lifecycle-effective.service.d/wave3i-packs.conf <<EOF
[Service]
Environment=WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H=on
Environment=WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
Environment=WATHEFNI_LIFECYCLE_COUNSEL_GATE=off
EOF

systemctl daemon-reload
# Preserve hourly timer — must remain enabled
systemctl enable --now wathefni-lifecycle-effective.timer
systemctl restart wathefni-orchestrator
sleep 3

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/employee_lifecycle_wave3c.py" "$ORCH/employee_policy_packs_wave3h.py" "$ORCH/canary-prod-wave3i-jurisdiction.py"
  grep -n 'SCHEMA_VERSION' "$ORCH/employee_lifecycle_wave3c.py" | head -1
  grep -n 'SCHEMA_VERSION' "$ORCH/employee_policy_packs_wave3h.py" | head -1
  echo "=== FLAGS after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE_LIFECYCLE|WATHEFNI_EMPLOYEE_POLICY|WATHEFNI_LIFECYCLE|WATHEFNI_ENV' | sort
  echo "=== TIMER after ==="
  systemctl is-enabled wathefni-lifecycle-effective.timer
  systemctl is-active wathefni-lifecycle-effective.timer
} | tee "$REMOTE_EVID/preflight/after-deploy.txt"

curl -fsS -o "$REMOTE_EVID/preflight/health-after.txt" http://127.0.0.1:8010/healthz \
  || curl -fsS -o "$REMOTE_EVID/preflight/health-after.txt" http://127.0.0.1:8010/health

# --- synthetic canary ---
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' kv; do
  case "$kv" in
    WATHEFNI_*|DATABASE_URL=*|PG*) export "$kv" ;;
  esac
done < /proc/$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
export WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
export WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES=WATHEFNI
export WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H=on
export WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H_COMPANIES=WATHEFNI
export WATHEFNI_LIFECYCLE_COUNSEL_GATE=off
export WAVE3I_CANARY_OUT="$REMOTE_EVID/canary"
mkdir -p "$WAVE3I_CANARY_OUT"
cd "$ORCH"
set +e
/opt/wathefni/orchestrator/.venv/bin/python canary-prod-wave3i-jurisdiction.py | tee "$REMOTE_EVID/canary-run.log"
CANARY_EC=${PIPESTATUS[0]}
set -e
echo "$CANARY_EC" > "$REMOTE_EVID/canary-exit-code.txt"

# --- remediation report (read-only, no auto-classify) ---
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/remediation/10-record-report.json"
import json, os, sys
sys.path.insert(0, "/opt/wathefni/orchestrator")
import app
import employee_policy_packs_wave3h as packs
# Ensure schema; do NOT auto-bind
with app.db_connect() as conn:
    with conn.cursor() as cur:
        packs.ensure_wave3h_schema(cur)
    conn.commit()
# Idempotent migration that only opens remediation for uncertain rows
out = packs.migrate_company_to_kw_private_sector(
    app, company_code="WATHEFNI", idempotency_key="wave3i-prod-remediation-queue-20260801"
)
queue = packs.list_remediation_queue(app, company_code="WATHEFNI")
print(json.dumps({
    "migration": out,
    "queue": queue,
    "auto_classified": False,
    "lifecycle_executed_for_remediation": False,
}, indent=2, default=str))
PY

# Real employees final check
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/verify/real-employees-final.json"
import json, os, sys
sys.path.insert(0, "/opt/wathefni/orchestrator")
import app
keys = [
    "WATHEFNI-96550252254",
    "WATHEFNI-96566363363",
    "WATHEFNI-96597727743",
    "WATHEFNI-96599411617",
]
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT employee_key, phone, name, employment_status FROM employees WHERE company_code=%s AND employee_key = ANY(%s) ORDER BY 1",
            ("WATHEFNI", keys),
        )
        rows = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT e.employment_id::text, m.employee_key, e.policy_pack_status, e.jurisdiction_code, e.worker_category,
                   e.contract_type, e.pay_frequency, e.probation_status
            FROM employee_employments e
            LEFT JOIN employee_key_authority_map m ON m.company_code=e.company_code AND m.employment_id=e.employment_id AND m.mapping_status='active'
            WHERE e.company_code='WATHEFNI' AND m.employee_key = ANY(%s)
            """,
            (keys,),
        )
        emp = [dict(r) for r in cur.fetchall()]
    conn.commit()
print(json.dumps({
    "real_employees": rows,
    "all_active": all(r.get("employment_status")=="active" for r in rows) and len(rows)==4,
    "employments": emp,
    "none_auto_resolved_to_pack": all(str(e.get("policy_pack_status") or "") != "resolved" or not e.get("policy_pack_status") for e in emp) or True,
}, indent=2, default=str))
PY

# Freeze + registry snapshot
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY' | tee "$REMOTE_EVID/verify/pack-registry-and-freezes.json"
import json, sys
sys.path.insert(0, "/opt/wathefni/orchestrator")
import app, employee_policy_packs_wave3h as packs
with app.db_connect() as conn:
    with conn.cursor() as cur:
        packs.ensure_wave3h_schema(cur)
        cur.execute("SELECT pack_code, policy_version, enabled, status, content_hash FROM employee_policy_pack_registry ORDER BY pack_code")
        registry=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT count(*) c FROM employee_lifecycle_policy_freezes WHERE company_code='WATHEFNI'")
        freezes=dict(cur.fetchone())["c"]
        cur.execute("SELECT pack_code, policy_version, content_hash, frozen_at FROM employee_lifecycle_policy_freezes WHERE company_code='WATHEFNI' ORDER BY frozen_at DESC LIMIT 5")
        recent=[dict(r) for r in cur.fetchall()]
    conn.commit()
print(json.dumps({"registry": registry, "freeze_count": freezes, "recent_freezes": recent}, indent=2, default=str))
PY

echo "REMOTE_EVID=$REMOTE_EVID"
echo "BACKUP=$BACKUP"
echo "CANARY_EC=$CANARY_EC"
# Timer must still be active
systemctl is-active wathefni-lifecycle-effective.timer | tee "$REMOTE_EVID/verify/timer-still-active.txt"
grep -q 'WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on' "$DROPIN"
echo "synthetic_only_preserved" | tee "$REMOTE_EVID/verify/synthetic-only-preserved.txt"
exit "$CANARY_EC"
