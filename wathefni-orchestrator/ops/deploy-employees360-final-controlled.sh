#!/usr/bin/env bash
# Employees 360 final controlled rollout — deploy allowlist gates (WATHEFNI only).
set -euo pipefail
STAMP="${STAMP:?}"
REMOTE_EVID="/opt/wathefni/production-evidence/employees360-final-controlled-rollout/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-employees360-final-${STAMP}"
ORCH=/opt/wathefni/orchestrator
STAGE="${STAGE_DIR:-/tmp/e360-final-stage}"

mkdir -p "$REMOTE_EVID"/{preflight,verify,keys} "$BACKUP" "$STAGE"

# --- backup ---
cp -a "$ORCH/app.py" "$BACKUP/app.py"
cp -a "$ORCH/employee_selfservice_wave5.py" "$BACKUP/employee_selfservice_wave5.py"
cp -a "$ORCH/employee_lifecycle_wave3.py" "$BACKUP/employee_lifecycle_wave3.py"
cp -a "$ORCH/employee_policy_packs_wave3h.py" "$BACKUP/employee_policy_packs_wave3h.py"
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/employee-ess-v5.conf "$BACKUP/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf "$BACKUP/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/setup-console-v2.conf "$BACKUP/" 2>/dev/null || true
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:?backup dir}"
ORCH=/opt/wathefni/orchestrator
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/employee_selfservice_wave5.py" "$ORCH/employee_selfservice_wave5.py"
cp -a "$BACKUP_DIR/employee_lifecycle_wave3.py" "$ORCH/employee_lifecycle_wave3.py"
cp -a "$BACKUP_DIR/employee_policy_packs_wave3h.py" "$ORCH/employee_policy_packs_wave3h.py"
# restore drop-ins if present
for f in employee-ess-v5.conf employee-lifecycle-v3-synthetic.conf setup-console-v2.conf; do
  if [[ -f "$BACKUP_DIR/$f" ]]; then
    cp -a "$BACKUP_DIR/$f" "/etc/systemd/system/wathefni-orchestrator.service.d/$f"
  fi
done
# remove final-rollout drop-in if we added one
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/employee-final-controlled-rollout.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
RB
chmod +x "$BACKUP/ROLLBACK.sh"
bash -n "$BACKUP/ROLLBACK.sh"
echo "rollback_syntax_ok=true" | tee "$REMOTE_EVID/verify/rollback-tested.txt"
echo "rollback_executable=true" | tee -a "$REMOTE_EVID/verify/rollback-tested.txt"

# --- install modules ---
test -f "$STAGE/app.py"
test -f "$STAGE/employee_selfservice_wave5.py"
test -f "$STAGE/employee_lifecycle_wave3.py"
test -f "$STAGE/employee_policy_packs_wave3h.py"
cp -a "$STAGE/app.py" "$ORCH/app.py"
cp -a "$STAGE/employee_selfservice_wave5.py" "$ORCH/employee_selfservice_wave5.py"
cp -a "$STAGE/employee_lifecycle_wave3.py" "$ORCH/employee_lifecycle_wave3.py"
cp -a "$STAGE/employee_policy_packs_wave3h.py" "$ORCH/employee_policy_packs_wave3h.py"

# Canary key — Talal Fadhli (consenting controlled canary; not a dashboard owner)
CANARY_KEY="WATHEFNI-96550252254"
ALL_REALS="WATHEFNI-96550252254,WATHEFNI-96566363363,WATHEFNI-96597727743,WATHEFNI-96599411617"

# Drop-in: keep synthetic-only ON; add named real allowlists; enable app for canary only
cat > /etc/systemd/system/wathefni-orchestrator.service.d/zz-employee-final-controlled-rollout.conf <<EOF
[Service]
Environment=WATHEFNI_EMPLOYEE_ESS_V5_REAL_ALLOWLIST=${CANARY_KEY}
Environment=WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST=
Environment=WATHEFNI_EMPLOYEE_LIFECYCLE_V3_REAL_ALLOWLIST=${ALL_REALS}
Environment=WATHEFNI_EMPLOYEE_APP=on
Environment=WATHEFNI_EMPLOYEE_APP_REQUIRE_ALLOWLIST=on
Environment=WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=${CANARY_KEY}
EOF
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/employee-final-controlled-rollout.conf

# Ensure company module employee_app enabled for WATHEFNI
set -a; source /root/.openclaw/secrets/postgres.env; set +a
export WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
cd "$ORCH"
.venv/bin/python - <<'PY'
import sys
sys.path.insert(0,"/opt/wathefni/orchestrator")
import app
app.ensure_schema()
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
          INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
          VALUES ('WATHEFNI','employee_app', true, 'final_controlled_rollout', '{}'::jsonb, now())
          ON CONFLICT (company_code, module_key) DO UPDATE
            SET enabled=true, source='final_controlled_rollout', updated_at=now()
        """)
    conn.commit()
print("company_module_employee_app=enabled")
PY

systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
curl -fsS http://127.0.0.1:8010/health >/dev/null

{
  echo "=== SHAs ==="
  sha256sum "$ORCH/app.py" "$ORCH/employee_selfservice_wave5.py" "$ORCH/employee_lifecycle_wave3.py" "$ORCH/employee_policy_packs_wave3h.py"
  echo "=== drop-in ==="
  cat /etc/systemd/system/wathefni-orchestrator.service.d/employee-final-controlled-rollout.conf
  echo "=== flags sample ==="
  systemctl show wathefni-orchestrator -p Environment --value | tr ' ' '\n' | grep -E 'ESS_V5_REAL|BANK_REAL|LIFECYCLE_V3_REAL|EMPLOYEE_APP' || true
} | tee "$REMOTE_EVID/preflight/after-deploy.txt"

echo "DEPLOY_OK"
