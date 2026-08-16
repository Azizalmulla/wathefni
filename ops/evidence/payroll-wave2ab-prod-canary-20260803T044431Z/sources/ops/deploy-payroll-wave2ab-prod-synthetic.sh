#!/usr/bin/env bash
# Payroll Wave 2A-B — production WATHEFNI synthetic external-adapter deploy.
# Enables WAVE2A + SYNTHETIC_ONLY only. Keeps money_authority=external.
# vendor_claimed=false. No bank files, native G2N, real vendor, or Wave 2B.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-payroll-wave2ab-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave2ab-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/payroll-w2ab-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-payroll-wave2ab-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests} "$BACKUP"/modules "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/payroll_authority_wave1.py" 2>/dev/null || echo "payroll_authority_wave1.py missing"
  ls -la "$ORCH/payroll_external_adapter_wave2a.py" 2>&1 || echo "payroll_external_adapter_wave2a.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'PAYROLL|ATTENDANCE_CAPTURE_INGEST' | sort || true
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

# Require Wave 1 already present (frozen foundation)
test -f "$ORCH/payroll_authority_wave1.py" || { echo "REFUSE: Wave 1 module missing"; exit 3; }
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
  | grep -q '^WATHEFNI_PAYROLL_WAVE1=1' || { echo "REFUSE: Wave 1 flag not enabled"; exit 3; }

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/adapter-counts-before.json"
import json, app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
        out={"db": db}
        for t in (
            "payroll_adapter_export_runs",
            "payroll_adapter_import_runs",
            "payroll_adapter_quarantine",
            "payroll_compensation_contracts",
        ):
            cur.execute("SELECT to_regclass(%s) AS t", (t,))
            present = dict(cur.fetchone())["t"] is not None
            out[t] = {"present": present}
            if present:
                cur.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE company_code=%s", ("WATHEFNI",))
                out[t]["count"] = int(dict(cur.fetchone())["n"])
print(json.dumps(out, indent=2))
PY

log "backing up modules + dropins"
for f in payroll_external_adapter_wave2a.py payroll_authority_wave1.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-payroll-wave2ab-synthetic.conf
test -d "$BACKUP_DIR"
# Remove Wave 2A-B module if it was absent pre-deploy
if [[ ! -f "$BACKUP_DIR/modules/payroll_external_adapter_wave2a.py" ]]; then
  rm -f "$ORCH/payroll_external_adapter_wave2a.py"
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
# Note: adapter run rows are soft-status data; canary cleans synthetics. Schema tables remain additive.
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying wave2a modules"
for f in payroll_external_adapter_wave2a.py payroll_authority_wave1.py \
         canary-prod-payroll-external-adapter-wave2ab.py \
         smoke-test-payroll-external-adapter-wave2a.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql"
[[ -f "$STAGE/migrate-payroll-external-adapter-wave2a-prod.sh" ]] && cp -a "$STAGE/migrate-payroll-external-adapter-wave2a-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/payroll_external_adapter_wave2a_v1.sql" ]] && cp -a "$STAGE/payroll_external_adapter_wave2a_v1.sql" "$ORCH/ops/sql/"
# Wave 1 SQL dependency (unchanged)
[[ -f "$STAGE/payroll_authority_wave1_v1.sql" ]] && cp -a "$STAGE/payroll_authority_wave1_v1.sql" "$ORCH/ops/sql/"

log "writing synthetic-only Wave 2A drop-in"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE2A=1
Environment=WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS=PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES=965540,965539
EOF

log "migrate schema (ACK)"
chmod +x "$ORCH/ops/migrate-payroll-external-adapter-wave2a-prod.sh"
ACK_PRODUCTION_PAYROLL_W2AB=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-payroll-external-adapter-wave2a-prod.sh" \
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
  sha256sum "$ORCH/payroll_external_adapter_wave2a.py" "$ORCH/payroll_authority_wave1.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'PAYROLL|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/payroll-wave2a-flags.txt"
import os, payroll_external_adapter_wave2a as w, payroll_authority_wave1 as pyw1
print("PAYROLL_WAVE2A", os.environ.get("WATHEFNI_PAYROLL_WAVE2A"))
print("SYNTHETIC_ONLY", w.payroll_wave2a_synthetic_only())
print("enabled", w.payroll_wave2a_enabled())
print("company", w.payroll_wave2a_enabled_for_company("WATHEFNI"))
print("markers", w.synthetic_key_markers())
print("prefixes", w.synthetic_phone_prefixes())
h = w.honesty_payload()
print("honesty", {k: h[k] for k in (
  "payment_processing","money_authority","wathefni_money_authority","posts_payment",
  "vendor_claimed","bank_files","native_gross_to_net","wave1_contracts_unchanged","synthetic_only"
)})
assert w.payroll_wave2a_enabled()
assert w.payroll_wave2a_synthetic_only()
assert w.payroll_wave2a_enabled_for_company("WATHEFNI")
assert h["payment_processing"] == "disabled"
assert h["money_authority"] == "external"
assert h["wathefni_money_authority"] is False
assert h["vendor_claimed"] is False
assert h["posts_payment"] is False
assert pyw1.payroll_wave1_enabled()  # Wave 1 freeze posture remains
print("flags_ok_synthetic=true")
print("ACK_OK")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
