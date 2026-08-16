#!/usr/bin/env bash
# Payroll Wave 2B-B — production WATHEFNI synthetic native-preview deploy.
# Enables WAVE2B + SYNTHETIC_ONLY. Previews non-authoritative; payment_processing=disabled.
# Does NOT alter Wave 1 / Wave 2A / Wave 2A-C freeze drop-ins on rollback of this wave.
# No payslips, bank/WPS, PIFSS, EOS, journals, payments, or AI.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-payroll-wave2bb-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave2bb-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/payroll-w2bb-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-payroll-wave2bb-synthetic.conf
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests} "$BACKUP"/modules "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/payroll_authority_wave1.py" "$ORCH/payroll_external_adapter_wave2a.py" 2>/dev/null || true
  ls -la "$ORCH/payroll_native_preview_wave2b.py" 2>&1 || echo "payroll_native_preview_wave2b.py absent"
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

test -f "$ORCH/payroll_authority_wave1.py" || { echo "REFUSE: Wave 1 module missing"; exit 3; }
test -f "$ORCH/payroll_external_adapter_wave2a.py" || { echo "REFUSE: Wave 2A module missing (freeze prerequisite)"; exit 3; }

ORCH_PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
if [[ -z "$ORCH_PID" || "$ORCH_PID" == "0" || ! -r "/proc/$ORCH_PID/environ" ]]; then
  echo "REFUSE: orchestrator PID unavailable ($ORCH_PID)"
  exit 3
fi
ORCH_ENV=$(tr '\0' '\n' < "/proc/$ORCH_PID/environ")
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE1=1' || { echo "REFUSE: Wave 1 flag not enabled"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1' || { echo "REFUSE: Wave 2A flag not enabled"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1' || { echo "REFUSE: Wave 2A SYNTHETIC_ONLY required"; exit 3; }

INGEST=$(echo "$ORCH_ENV" | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/preview-counts-before.json"
import json, app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
        out={"db": db}
        for t in (
            "payroll_preview_runs",
            "payroll_compensation_contracts",
            "payroll_adapter_export_runs",
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
HAD_W2B=0
[[ -f "$ORCH/payroll_native_preview_wave2b.py" ]] && HAD_W2B=1
echo "$HAD_W2B" > "$BACKUP/had_wave2b_module.txt"
for f in app.py payroll_authority_wave1.py payroll_external_adapter_wave2a.py payroll_native_preview_wave2b.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
[[ -f "$DROPIN" ]] && cp -a "$DROPIN" "$BACKUP/payroll-wave2bb-synthetic.conf" || true
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-payroll-wave2bb-synthetic.conf
test -d "$BACKUP_DIR"
# Restore pre-Wave-2B-B code; remove Wave 2B drop-in; keep Wave 1 + Wave 2A drop-ins
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
HAD=$(cat "$BACKUP_DIR/had_wave2b_module.txt" 2>/dev/null || echo 0)
if [[ "$HAD" != "1" ]]; then
  rm -f "$ORCH/payroll_native_preview_wave2b.py"
fi
rm -f "$DROPIN"
# Restore other drop-ins from backup (Wave 1 / Wave 2A retained)
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  # Do not wipe directory; re-copy known freeze drop-ins and ensure Wave 2B drop-in gone
  for f in "$BACKUP_DIR"/systemd-dropins/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    [[ "$base" == "zzzzzzzzzzzzzzzz-payroll-wave2bb-synthetic.conf" ]] && continue
    cp -a "$f" /etc/systemd/system/wathefni-orchestrator.service.d/"$base"
  done
fi
rm -f "$DROPIN"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1'
if tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2B=1'; then
  echo "REFUSE: WAVE2B still enabled after rollback" >&2
  exit 4
fi
echo ROLLBACK_OK
# Preview schema tables remain additive; canary cleans synthetic rows.
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying wave2b modules + app routes"
for f in app.py payroll_native_preview_wave2b.py payroll_authority_wave1.py payroll_external_adapter_wave2a.py \
         canary-prod-payroll-native-preview-wave2bb.py \
         smoke-test-payroll-native-preview-wave2b.py \
         smoke-test-payroll-external-adapter-wave2a.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql"
[[ -f "$STAGE/migrate-payroll-native-preview-wave2b-prod.sh" ]] && cp -a "$STAGE/migrate-payroll-native-preview-wave2b-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/payroll_native_preview_wave2b_v1.sql" ]] && cp -a "$STAGE/payroll_native_preview_wave2b_v1.sql" "$ORCH/ops/sql/"
[[ -f "$STAGE/payroll_authority_wave1_v1.sql" ]] && cp -a "$STAGE/payroll_authority_wave1_v1.sql" "$ORCH/ops/sql/"
[[ -f "$STAGE/payroll_external_adapter_wave2a_v1.sql" ]] && cp -a "$STAGE/payroll_external_adapter_wave2a_v1.sql" "$ORCH/ops/sql/"

test -f "$ORCH/payroll_native_preview_wave2b.py" || { echo "REFUSE: wave2b module not staged"; exit 3; }
grep -q 'payroll_native_preview_wave2b' "$ORCH/app.py" || { echo "REFUSE: app.py missing wave2b import/routes"; exit 3; }

log "writing synthetic-only Wave 2B drop-in (Wave 1/2A drop-ins untouched)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE2B=1
Environment=WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS=PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,W2BB
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES=965541,965539
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/payroll-wave2bb-synthetic.conf"

log "migrate schema (ACK)"
chmod +x "$ORCH/ops/migrate-payroll-native-preview-wave2b-prod.sh"
ACK_PRODUCTION_PAYROLL_W2BB=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-payroll-native-preview-wave2b-prod.sh" \
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
  sha256sum "$ORCH/payroll_native_preview_wave2b.py" "$ORCH/app.py" "$ORCH/payroll_authority_wave1.py" "$ORCH/payroll_external_adapter_wave2a.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'PAYROLL|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/payroll-wave2bb-flags.txt"
import os
import payroll_native_preview_wave2b as w2b
import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
print("PAYROLL_WAVE2B", os.environ.get("WATHEFNI_PAYROLL_WAVE2B"))
print("SYNTHETIC_ONLY", w2b.payroll_wave2b_synthetic_only())
print("enabled", w2b.payroll_wave2b_enabled())
print("company", w2b.payroll_wave2b_enabled_for_company("WATHEFNI"))
print("markers", w2b.synthetic_key_markers())
print("prefixes", w2b.synthetic_phone_prefixes())
h = w2b.honesty_payload()
print("honesty", {k: h[k] for k in (
  "payment_processing","authoritative","preview_only","ai_calculations",
  "external_flows_unchanged","bank_files","pifss","synthetic_only"
)})
assert w2b.payroll_wave2b_enabled()
assert w2b.payroll_wave2b_synthetic_only()
assert w2b.payroll_wave2b_enabled_for_company("WATHEFNI")
assert h["payment_processing"] == "disabled"
assert h["authoritative"] is False
assert h["preview_only"] is True
assert h["ai_calculations"] is False
assert h["external_flows_unchanged"] is True
assert pyw1.payroll_wave1_enabled()
assert w2a.payroll_wave2a_enabled() and w2a.payroll_wave2a_synthetic_only()
print("flags_ok_synthetic=true")
print("ACK_OK")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
