#!/usr/bin/env bash
# Wave 5C — production deploy Wave 5/5B ESS for WATHEFNI-only synthetic canary.
# Preserves Wave 3F/3H + Wave 4 + lifecycle SYNTHETIC_ONLY.
# Does NOT enable real lifecycle, EMPLOYEE_APP, Wave 6, or pre-hire/Wave D changes.
set -euo pipefail

STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
REMOTE_EVID="/opt/wathefni/production-evidence/employees360-wave5c-prod-canary/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-employees360-wave5c-${STAMP}"
ORCH=/opt/wathefni/orchestrator
STAGE=/tmp/wave5c-deploy
DROPIN_ESS=/etc/systemd/system/wathefni-orchestrator.service.d/employee-ess-v5.conf
ESS_BANK_SECRET_FILE=/root/.openclaw/secrets/wathefni-ess-bank.production.env

echo "STAMP=$STAMP"
mkdir -p "$REMOTE_EVID"/{preflight,canary,verify,schema,http,keys} "$BACKUP" "$STAGE"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

# --- preflight ---
{
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" \
    "$ORCH/employee_lifecycle_wave3c.py" \
    "$ORCH/employee_policy_packs_wave3h.py" \
    "$ORCH/employee_org_wave4.py" \
    "$ORCH/lifecycle-effective-worker.py" 2>/dev/null || true
  ls "$ORCH/employee_selfservice_wave5.py" 2>&1 || echo "ess_wave5_absent_before"
  echo "=== SCHEMA META (lifecycle/org) ==="
  grep -n 'SCHEMA_VERSION' "$ORCH/employee_lifecycle_wave3c.py" "$ORCH/employee_org_wave4.py" 2>/dev/null | head -6
  echo "=== FLAGS before ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE|WATHEFNI_LIFECYCLE|WATHEFNI_ENV|WATHEFNI_ESS' | sort
  echo "=== TIMER ==="
  systemctl is-enabled wathefni-lifecycle-effective.timer
  systemctl is-active wathefni-lifecycle-effective.timer
  echo "=== ESS TABLES before ==="
  set -a
  # shellcheck disable=SC1091
  source /root/.openclaw/secrets/postgres.env
  set +a
  psql "$WATHEFNI_DATABASE_URL" -Atc \
    "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'employee_ess_%' ORDER BY 1;" \
    || true
  echo "=== ESS ROUTES BEFORE ==="
  curl -fsS http://127.0.0.1:8010/openapi.json 2>/dev/null | python3 -c \
    "import sys,json; p=json.load(sys.stdin).get('paths',{}); print(sum(1 for k in p if 'employee-ess' in k))" \
    || echo "openapi_unavailable"
} | tee "$REMOTE_EVID/preflight/before.txt"

curl -fsS -o "$REMOTE_EVID/preflight/health-before.txt" http://127.0.0.1:8010/healthz \
  || curl -fsS -o "$REMOTE_EVID/preflight/health-before.txt" http://127.0.0.1:8010/health || true

# --- backup ---
cp -a "$ORCH/app.py" "$BACKUP/"
cp -a "$ORCH/lifecycle-effective-worker.py" "$BACKUP/" 2>/dev/null || true
cp -a "$ORCH/employee_lifecycle_wave3c.py" "$BACKUP/" 2>/dev/null || true
cp -a "$ORCH/employee_policy_packs_wave3h.py" "$BACKUP/" 2>/dev/null || true
cp -a "$ORCH/employee_org_wave4.py" "$BACKUP/" 2>/dev/null || true
[[ -f "$ORCH/employee_selfservice_wave5.py" ]] && cp -a "$ORCH/employee_selfservice_wave5.py" "$BACKUP/employee_selfservice_wave5.py.pre" || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf "$BACKUP/" 2>/dev/null || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/employee-org-v4.conf "$BACKUP/" 2>/dev/null || true
mkdir -p "$BACKUP/orchestrator.service.d"
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/orchestrator.service.d/" 2>/dev/null || true

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
/usr/bin/pg_dump "$WATHEFNI_DATABASE_URL" \
  --schema-only --no-owner \
  -t employees \
  -t employee_employments \
  -t employee_key_authority_map \
  -t employee_sessions \
  -t employee_org_assignments \
  > "$BACKUP/pre-wave5c-schema.sql" 2>/dev/null \
  || echo "schema_dump_partial" | tee "$BACKUP/pg_dump_note.txt"

/usr/bin/pg_dump "$WATHEFNI_DATABASE_URL" \
  --data-only --no-owner \
  -t employee_key_authority_map \
  -t employee_employments \
  > "$BACKUP/authority-tables.dump.sql" 2>/dev/null || true

# Snapshot four real employees (hub + employment) for untouched proof
psql "$WATHEFNI_DATABASE_URL" -c "
COPY (
  SELECT e.employee_key, e.name, e.phone, e.email, e.updated_at,
         emp.employment_id, emp.employment_status, emp.lifecycle_state, emp.policy_pack_status
  FROM employees e
  LEFT JOIN LATERAL (
    SELECT * FROM employee_employments ee
    WHERE ee.company_code=e.company_code AND ee.legacy_employee_key=e.employee_key
    ORDER BY ee.created_at DESC LIMIT 1
  ) emp ON true
  WHERE e.company_code='WATHEFNI'
    AND e.employee_key IN (
      'WATHEFNI-96550252254','WATHEFNI-96566363363','WATHEFNI-96597727743','WATHEFNI-96599411617'
    )
  ORDER BY e.employee_key
) TO STDOUT WITH CSV HEADER
" > "$BACKUP/four-reals-before.csv"

cat > "$BACKUP/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
[[ -f "$BACKUP_DIR/lifecycle-effective-worker.py" ]] && cp -a "$BACKUP_DIR/lifecycle-effective-worker.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee_lifecycle_wave3c.py" ]] && cp -a "$BACKUP_DIR/employee_lifecycle_wave3c.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee_policy_packs_wave3h.py" ]] && cp -a "$BACKUP_DIR/employee_policy_packs_wave3h.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee_org_wave4.py" ]] && cp -a "$BACKUP_DIR/employee_org_wave4.py" "$ORCH/"
rm -f "$ORCH/employee_selfservice_wave5.py"
rm -f "$ORCH/canary-prod-wave5c-ess.py"
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/employee-ess-v5.conf
# Restore prior drop-ins for lifecycle/org if present
[[ -f "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" ]] && \
  cp -a "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" \
    /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf
[[ -f "$BACKUP_DIR/employee-org-v4.conf" ]] && \
  cp -a "$BACKUP_DIR/employee-org-v4.conf" \
    /etc/systemd/system/wathefni-orchestrator.service.d/employee-org-v4.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
systemctl enable --now wathefni-lifecycle-effective.timer 2>/dev/null || true
sleep 2
curl -fsS http://127.0.0.1:8010/healthz || curl -fsS http://127.0.0.1:8010/health
echo "rolled back Wave 5C ESS modules/flags; Wave 3F/3H + Wave 4 + SYNTHETIC_ONLY retained"
echo "NOTE: additive employee_ess_* tables left in place; bank secret file NOT deleted (manual ops)."
EOS
chmod +x "$BACKUP/ROLLBACK.sh"
test -x "$BACKUP/ROLLBACK.sh"
grep -q 'employee_selfservice_wave5.py' "$BACKUP/ROLLBACK.sh"
echo "rollback_script_ok" | tee "$REMOTE_EVID/verify/rollback-proof.txt"
ls -la "$BACKUP" | tee "$REMOTE_EVID/verify/backup-listing.txt"

# --- provision ESS bank key (never log plaintext) ---
if [[ ! -f "$ESS_BANK_SECRET_FILE" ]]; then
  umask 077
  PRIMARY=$("$ORCH/.venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
  PREVIOUS=$("$ORCH/.venv/bin/python" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
  cat > "$ESS_BANK_SECRET_FILE" <<EOF
# Production ESS bank encryption keys — Wave 5C
# Do not commit. Do not copy into evidence.
WATHEFNI_ESS_BANK_SECRET_KEY=${PRIMARY}
WATHEFNI_ESS_BANK_SECRET_KEY_PREVIOUS=${PREVIOUS}
EOF
  chmod 600 "$ESS_BANK_SECRET_FILE"
  chown root:root "$ESS_BANK_SECRET_FILE"
  unset PRIMARY PREVIOUS
  echo "ess_bank_key_provisioned_new" > "$REMOTE_EVID/keys/provision-status.txt"
else
  echo "ess_bank_key_already_present" > "$REMOTE_EVID/keys/provision-status.txt"
fi
chmod 600 "$ESS_BANK_SECRET_FILE"
# Proof without revealing secret material
{
  echo "path=$ESS_BANK_SECRET_FILE"
  echo "mode=$(stat -c '%a' "$ESS_BANK_SECRET_FILE")"
  echo "owner=$(stat -c '%U:%G' "$ESS_BANK_SECRET_FILE")"
  "$ORCH/.venv/bin/python" - <<'PY'
from pathlib import Path
import hashlib, os
p = Path("/root/.openclaw/secrets/wathefni-ess-bank.production.env")
text = p.read_text()
assert "WATHEFNI_ESS_BANK_SECRET_KEY=" in text
# never print values
keys = {}
for line in text.splitlines():
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    keys[k] = {
        "present": bool(v.strip()),
        "length": len(v.strip()),
        "sha256_8": hashlib.sha256(v.strip().encode()).hexdigest()[:8],
    }
print("key_names=", sorted(keys))
for k, meta in sorted(keys.items()):
    print(f"{k}: present={meta['present']} length={meta['length']} fingerprint8={meta['sha256_8']}")
# Ensure evidence dir has no secret values
assert all(meta["length"] >= 32 for meta in keys.values())
print("key_material_not_echoed=true")
PY
} | tee "$REMOTE_EVID/keys/provision-proof.txt"

# --- install modules ---
test -f "$STAGE/employee_selfservice_wave5.py"
test -f "$STAGE/app.py"
test -f "$STAGE/canary-prod-wave5c-ess.py"
cp -a "$STAGE/employee_selfservice_wave5.py" "$ORCH/"
cp -a "$STAGE/app.py" "$ORCH/"
cp -a "$STAGE/canary-prod-wave5c-ess.py" "$ORCH/"
chmod +x "$ORCH/canary-prod-wave5c-ess.py"

"$ORCH/.venv/bin/python" -m py_compile \
  "$ORCH/employee_selfservice_wave5.py" \
  "$ORCH/canary-prod-wave5c-ess.py"
( cd "$ORCH" && "$ORCH/.venv/bin/python" -c \
  "import employee_selfservice_wave5 as w; print(w.SCHEMA_VERSION)" )

# --- systemd flags (WATHEFNI only, synthetic only; EMPLOYEE_APP stays off) ---
cat > "$DROPIN_ESS" <<EOF
[Service]
EnvironmentFile=-${ESS_BANK_SECRET_FILE}
Environment=WATHEFNI_EMPLOYEE_ESS_V5=on
Environment=WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES=WATHEFNI
Environment=WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY=on
Environment=WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_PHONE_PREFIXES=965549
Environment=WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_NAME_PREFIX=W5C-SYNTH|
EOF

# Ensure drop-in itself has no secret values
grep -q 'EnvironmentFile=-/root/.openclaw/secrets/wathefni-ess-bank.production.env' "$DROPIN_ESS"
! grep -q 'WATHEFNI_ESS_BANK_SECRET_KEY=' "$DROPIN_ESS"
cp -a "$DROPIN_ESS" "$REMOTE_EVID/verify/employee-ess-v5.conf"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 4
curl -fsS -o "$REMOTE_EVID/preflight/health-after.txt" http://127.0.0.1:8010/healthz \
  || curl -fsS -o "$REMOTE_EVID/preflight/health-after.txt" http://127.0.0.1:8010/health

{
  echo "=== SHAs after ==="
  sha256sum "$ORCH/app.py" "$ORCH/employee_selfservice_wave5.py" "$ORCH/canary-prod-wave5c-ess.py" \
    "$ORCH/employee_org_wave4.py" "$ORCH/employee_lifecycle_wave3c.py" "$ORCH/employee_policy_packs_wave3h.py"
  echo "=== FLAGS after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/$PID/environ | grep -E 'WATHEFNI_EMPLOYEE_(ESS|ORG|LIFECYCLE|POLICY|AUTHORITY|APP)|WATHEFNI_ESS_BANK' | sort | \
    sed -E 's/(WATHEFNI_ESS_BANK_SECRET_KEY(_PREVIOUS)?)=.*/\1=<redacted>/'
  echo "=== TIMER still ==="
  systemctl is-enabled wathefni-lifecycle-effective.timer
  systemctl is-active wathefni-lifecycle-effective.timer
  echo "=== ESS ROUTES AFTER ==="
  curl -fsS http://127.0.0.1:8010/openapi.json | python3 -c \
    "import sys,json; p=json.load(sys.stdin).get('paths',{}); ks=sorted(k for k in p if 'employee-ess' in k); print(len(ks)); print('\\n'.join(ks))"
  echo "=== BANK KEY IN PROC (presence only) ==="
  tr '\0' '\n' < /proc/$PID/environ | grep -c '^WATHEFNI_ESS_BANK_SECRET_KEY=' || true
  tr '\0' '\n' < /proc/$PID/environ | grep -c '^WATHEFNI_ESS_BANK_SECRET_KEY_PREVIOUS=' || true
} | tee "$REMOTE_EVID/preflight/after-deploy.txt"

# Ensure schema + prove bank encryption available without dumping key
(
  set -a
  # shellcheck disable=SC1091
  source /root/.openclaw/secrets/postgres.env
  # shellcheck disable=SC1091
  source "$ESS_BANK_SECRET_FILE"
  set +a
  export WATHEFNI_EMPLOYEE_ESS_V5=on
  export WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES=WATHEFNI
  export WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY=on
  export WATHEFNI_ENV=production
  cd "$ORCH"
  "$ORCH/.venv/bin/python" - <<'PY'
import app, employee_selfservice_wave5 as w5, os, hashlib
with app.db_connect() as conn:
    with conn.cursor() as cur:
        w5.ensure_ess_wave5_schema(cur)
        cur.execute("ALTER TABLE employee_sessions ADD COLUMN IF NOT EXISTS ess_session_epoch bigint")
        cur.execute("SELECT schema_version FROM employee_ess_schema_meta WHERE schema_name='employees360_wave5'")
        row = cur.fetchone()
        print("schema_version", dict(row).get("schema_version") if row else None)
        cur.execute("""
          SELECT tablename FROM pg_tables
          WHERE schemaname='public' AND tablename LIKE 'employee_ess_%'
          ORDER BY 1
        """)
        for r in cur.fetchall():
            print(dict(r)["tablename"])
    conn.commit()
print("bank_encryption_available", w5.bank_encryption_available())
k = os.environ.get("WATHEFNI_ESS_BANK_SECRET_KEY", "")
print("bank_key_fingerprint8", hashlib.sha256(k.encode()).hexdigest()[:8] if k else "missing")
print("bank_key_length", len(k))
import urllib.request
health = urllib.request.urlopen("http://127.0.0.1:8010/healthz").read().decode()
assert "WATHEFNI_ESS_BANK" not in health and "Fernet" not in health
print("health_has_no_bank_key", True)
PY
) | tee "$REMOTE_EVID/schema/wave5-tables.txt"

# Prove DROPIN + secret file never land in evidence as plaintext values
if grep -RInE 'WATHEFNI_ESS_BANK_SECRET_KEY=[A-Za-z0-9_\-]{20,}' "$REMOTE_EVID" --include='*.txt' --include='*.conf' --include='*.md' --include='*.json' 2>/dev/null; then
  echo "FATAL: bank secret leaked into evidence" >&2
  exit 1
fi
echo "evidence_has_no_bank_secret_values=true" | tee -a "$REMOTE_EVID/keys/provision-proof.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
