#!/usr/bin/env bash
# Wave 4C — production deploy Wave 4B org authority (WATHEFNI synthetic qualification).
# Shares wathefni-lifecycle-effective.timer for activate_due (kill switch supported).
# Preserves Wave 3F/3H + SYNTHETIC_ONLY. Does NOT enable real lifecycle.
set -euo pipefail

STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
REMOTE_EVID="/opt/wathefni/production-evidence/employees360-wave4c-prod-deploy/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-employees360-wave4c-${STAMP}"
ORCH=/opt/wathefni/orchestrator
STAGE=/tmp/wave4c-deploy
DROPIN_ORG=/etc/systemd/system/wathefni-orchestrator.service.d/employee-org-v4.conf
DROPIN_WORKER=/etc/systemd/system/wathefni-lifecycle-effective.service.d/wave4c-org.conf

echo "STAMP=$STAMP"
mkdir -p "$REMOTE_EVID"/{preflight,canary,remediation,verify,schema,http} "$BACKUP" "$STAGE"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

# --- preflight ---
{
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" \
    "$ORCH/employee_lifecycle_wave3c.py" \
    "$ORCH/employee_policy_packs_wave3h.py" \
    "$ORCH/lifecycle-effective-worker.py" 2>/dev/null || true
  ls "$ORCH/employee_org_wave4.py" 2>&1 || echo "org_wave4_absent_before"
  echo "=== SCHEMA META ==="
  grep -n 'SCHEMA_VERSION' "$ORCH/employee_lifecycle_wave3c.py" | head -2
  echo "=== FLAGS ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE|WATHEFNI_LIFECYCLE|WATHEFNI_ENV' | sort
  echo "=== TIMER ==="
  systemctl is-enabled wathefni-lifecycle-effective.timer
  systemctl is-active wathefni-lifecycle-effective.timer
  echo "=== CONFLICTING ORG TABLES ==="
  set -a
  # shellcheck disable=SC1091
  source /root/.openclaw/secrets/postgres.env
  set +a
  psql "$WATHEFNI_DATABASE_URL" -Atc \
    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND (tablename LIKE 'employee_org_%' OR tablename LIKE 'employee_migration_%' OR tablename LIKE 'employee_bulk_%') ORDER BY 1;" \
    || true
  echo "=== ORG ROUTES BEFORE ==="
  curl -fsS http://127.0.0.1:8010/openapi.json 2>/dev/null | python3 -c \
    "import sys,json; p=json.load(sys.stdin).get('paths',{}); print(sum(1 for k in p if 'employee-org' in k or 'org-as-of' in k or 'org-history' in k))" \
    || echo "openapi_unavailable"
} | tee "$REMOTE_EVID/preflight/before.txt"

curl -fsS -o "$REMOTE_EVID/preflight/health-before.txt" http://127.0.0.1:8010/healthz \
  || curl -fsS -o "$REMOTE_EVID/preflight/health-before.txt" http://127.0.0.1:8010/health || true

# --- backup ---
cp -a "$ORCH/app.py" "$BACKUP/"
cp -a "$ORCH/lifecycle-effective-worker.py" "$BACKUP/"
cp -a "$ORCH/employee_lifecycle_wave3c.py" "$BACKUP/" 2>/dev/null || true
cp -a "$ORCH/employee_policy_packs_wave3h.py" "$BACKUP/" 2>/dev/null || true
[[ -f "$ORCH/employee_org_wave4.py" ]] && cp -a "$ORCH/employee_org_wave4.py" "$BACKUP/employee_org_wave4.py.pre" || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf "$BACKUP/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-lifecycle-effective.service "$BACKUP/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-lifecycle-effective.timer "$BACKUP/" 2>/dev/null || true
mkdir -p "$BACKUP/lifecycle-effective.service.d"
cp -a /etc/systemd/system/wathefni-lifecycle-effective.service.d/. "$BACKUP/lifecycle-effective.service.d/" 2>/dev/null || true

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
/usr/bin/pg_dump "$WATHEFNI_DATABASE_URL" \
  --schema-only --no-owner \
  -t employee_org_assignments \
  -t employee_employments \
  -t employees \
  -t employee_key_authority_map \
  -t employee_assignments \
  > "$BACKUP/pre-wave4c-schema.sql" 2>/dev/null \
  || echo "schema_dump_partial" | tee "$BACKUP/pg_dump_note.txt"

# data snapshot for authority tables (additive safety)
/usr/bin/pg_dump "$WATHEFNI_DATABASE_URL" \
  --data-only --no-owner \
  -t employee_key_authority_map \
  -t employee_assignments \
  -t employee_employments \
  > "$BACKUP/authority-tables.dump.sql" 2>/dev/null || true

cat > "$BACKUP/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/lifecycle-effective-worker.py" "$ORCH/lifecycle-effective-worker.py"
rm -f "$ORCH/employee_org_wave4.py"
rm -f "$ORCH/canary-prod-wave4c-org.py"
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/employee-org-v4.conf
rm -f /etc/systemd/system/wathefni-lifecycle-effective.service.d/wave4c-org.conf
# Restore lifecycle packs modules if present in backup
[[ -f "$BACKUP_DIR/employee_lifecycle_wave3c.py" ]] && cp -a "$BACKUP_DIR/employee_lifecycle_wave3c.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee_policy_packs_wave3h.py" ]] && cp -a "$BACKUP_DIR/employee_policy_packs_wave3h.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" ]] && \
  cp -a "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" \
    /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
systemctl enable --now wathefni-lifecycle-effective.timer 2>/dev/null || true
sleep 2
curl -fsS http://127.0.0.1:8010/healthz || curl -fsS http://127.0.0.1:8010/health
echo "rolled back Wave 4C modules/flags; Wave 3F/3H + SYNTHETIC_ONLY retained; timer preserved"
echo "NOTE: additive Wave 4 tables (if created) are left in place empty; migration-owned rows should already be rolled back by canary/API."
EOS
chmod +x "$BACKUP/ROLLBACK.sh"
test -x "$BACKUP/ROLLBACK.sh"
grep -q 'employee_org_wave4.py' "$BACKUP/ROLLBACK.sh"
echo "rollback_script_ok" | tee "$REMOTE_EVID/verify/rollback-proof.txt"
ls -la "$BACKUP" | tee "$REMOTE_EVID/verify/backup-listing.txt"

# --- install modules ---
test -f "$STAGE/employee_org_wave4.py"
test -f "$STAGE/app.py"
test -f "$STAGE/lifecycle-effective-worker.py"
test -f "$STAGE/canary-prod-wave4c-org.py"
cp -a "$STAGE/employee_org_wave4.py" "$ORCH/"
cp -a "$STAGE/app.py" "$ORCH/"
cp -a "$STAGE/lifecycle-effective-worker.py" "$ORCH/"
cp -a "$STAGE/canary-prod-wave4c-org.py" "$ORCH/"
chmod +x "$ORCH/canary-prod-wave4c-org.py" "$ORCH/lifecycle-effective-worker.py"

/opt/wathefni/orchestrator/.venv/bin/python -m py_compile \
  "$ORCH/employee_org_wave4.py" \
  "$ORCH/lifecycle-effective-worker.py" \
  "$ORCH/canary-prod-wave4c-org.py"
( cd "$ORCH" && /opt/wathefni/orchestrator/.venv/bin/python -c \
  "import employee_org_wave4 as w; print(w.SCHEMA_VERSION)" )

# --- systemd flags ---
cat > "$DROPIN_ORG" <<EOF
[Service]
Environment=WATHEFNI_EMPLOYEE_ORG_V4=on
Environment=WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE=on
Environment=WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_LOOKBACK_DAYS=7
EOF

cat > "$DROPIN_WORKER" <<EOF
[Service]
Environment=WATHEFNI_EMPLOYEE_ORG_V4=on
Environment=WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE=on
Environment=WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_LOOKBACK_DAYS=7
EOF

systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
curl -fsS -o "$REMOTE_EVID/preflight/health-after.txt" http://127.0.0.1:8010/healthz \
  || curl -fsS -o "$REMOTE_EVID/preflight/health-after.txt" http://127.0.0.1:8010/health

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/employee_org_wave4.py" "$ORCH/lifecycle-effective-worker.py" "$ORCH/canary-prod-wave4c-org.py"
  echo "=== FLAGS after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE_ORG|WATHEFNI_EMPLOYEE_LIFECYCLE|WATHEFNI_EMPLOYEE_POLICY|WATHEFNI_EMPLOYEE_AUTHORITY' | sort
  echo "=== TIMER still ==="
  systemctl is-enabled wathefni-lifecycle-effective.timer
  systemctl is-active wathefni-lifecycle-effective.timer
  echo "=== ORG ROUTES AFTER ==="
  curl -fsS http://127.0.0.1:8010/openapi.json | python3 -c \
    "import sys,json; p=json.load(sys.stdin).get('paths',{}); ks=sorted(k for k in p if 'employee-org' in k or 'org-as-of' in k or 'org-history' in k); print(len(ks)); print('\\n'.join(ks))"
} | tee "$REMOTE_EVID/preflight/after-deploy.txt"

# Ensure schema created (additive)
( cd "$ORCH" && WATHEFNI_EMPLOYEE_ORG_V4=on WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES=WATHEFNI \
  /opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
import app, employee_org_wave4 as w4
with app.db_connect() as conn:
    with conn.cursor() as cur:
        w4.ensure_org_wave4_schema(cur)
        cur.execute("SELECT value FROM employee_org_schema_meta WHERE key='schema_version'")
        row = cur.fetchone()
        print("schema_version", dict(row)["value"] if row else None)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public'
            AND (tablename LIKE 'employee_org_%' OR tablename LIKE 'employee_migration_%' OR tablename LIKE 'employee_bulk_%')
          ORDER BY 1
        """)
        for r in cur.fetchall():
            print(dict(r)["tablename"])
    conn.commit()
PY
) | tee "$REMOTE_EVID/schema/wave4-tables.txt"

# Prove shared timer runs activate-due path (oneshot)
systemctl start wathefni-lifecycle-effective.service
sleep 2
journalctl -u wathefni-lifecycle-effective.service -n 40 --no-pager | tee "$REMOTE_EVID/verify/scheduler-oneshot.log"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
