#!/usr/bin/env bash
# Payroll Wave 4-B — production WATHEFNI synthetic close/export deploy.
# Enables WAVE4 + SYNTHETIC_ONLY. Journal drafts + bank-export contract validation only.
# payment_processing=disabled. Does NOT alter Wave 1/2A/2B/3 freeze drop-ins on rollback.
# No real bank format/connection, WPS/AS'HAL, PIFSS, EOS, payments, or AI.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-payroll-wave4b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave4b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/payroll-w4b-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzz-payroll-wave4b-synthetic.conf
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/posthire
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} "$BACKUP"/{modules,dashboard-posthire} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/payroll_authority_wave1.py" "$ORCH/payroll_external_adapter_wave2a.py" "$ORCH/payroll_native_preview_wave2b.py" "$ORCH/payroll_payslip_wave3.py" 2>/dev/null || true
  ls -la "$ORCH/payroll_close_export_wave4.py" 2>&1 || echo "payroll_close_export_wave4.py absent"
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
test -f "$ORCH/payroll_external_adapter_wave2a.py" || { echo "REFUSE: Wave 2A module missing"; exit 3; }
test -f "$ORCH/payroll_native_preview_wave2b.py" || { echo "REFUSE: Wave 2B module missing"; exit 3; }
test -f "$ORCH/payroll_payslip_wave3.py" || { echo "REFUSE: Wave 3 module missing (freeze prerequisite)"; exit 3; }

ORCH_PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
if [[ -z "$ORCH_PID" || "$ORCH_PID" == "0" || ! -r "/proc/$ORCH_PID/environ" ]]; then
  echo "REFUSE: orchestrator PID unavailable ($ORCH_PID)"
  exit 3
fi
ORCH_ENV=$(tr '\0' '\n' < "/proc/$ORCH_PID/environ")
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE1=1' || { echo "REFUSE: Wave 1 flag not enabled"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1' || { echo "REFUSE: Wave 2A flag not enabled"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1' || { echo "REFUSE: Wave 2A SYNTHETIC_ONLY required"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE2B=1' || { echo "REFUSE: Wave 2B flag not enabled"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1' || { echo "REFUSE: Wave 2B SYNTHETIC_ONLY required"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE3=1' || { echo "REFUSE: Wave 3 flag not enabled"; exit 3; }
echo "$ORCH_ENV" | grep -q '^WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1' || { echo "REFUSE: Wave 3 SYNTHETIC_ONLY required"; exit 3; }

INGEST=$(echo "$ORCH_ENV" | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/preflight/close-counts-before.json"
import json, app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=dict(cur.fetchone())["db"]; assert db=="wathefni"
        out={"db": db}
        for t in ("payroll_close_runs", "payroll_preview_runs", "payroll_adapter_import_runs", "payroll_payslip_documents"):
            cur.execute("SELECT to_regclass(%s) AS t", (t,))
            present = dict(cur.fetchone())["t"] is not None
            out[t] = {"present": present}
            if present:
                cur.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE company_code=%s", ("WATHEFNI",))
                out[t]["count"] = int(dict(cur.fetchone())["n"])
print(json.dumps(out, indent=2))
PY

log "backing up modules + dropins + dashboard posthire"
HAD_W4=0
[[ -f "$ORCH/payroll_close_export_wave4.py" ]] && HAD_W4=1
echo "$HAD_W4" > "$BACKUP/had_wave4_module.txt"
for f in app.py payroll_authority_wave1.py payroll_external_adapter_wave2a.py payroll_native_preview_wave2b.py payroll_payslip_wave3.py payroll_close_export_wave4.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
[[ -f "$DROPIN" ]] && cp -a "$DROPIN" "$BACKUP/payroll-wave4b-synthetic.conf" || true
mkdir -p "$DASH_SRC"
for f in CloseExportWorkspace.tsx payrollCloseExportUx.ts PayslipWorkspace.tsx payrollPayslipUx.ts payrollExternalUx.ts PostHire.tsx; do
  [[ -f "$DASH_SRC/$f" ]] && cp -a "$DASH_SRC/$f" "$BACKUP/dashboard-posthire/" || true
done
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzz-payroll-wave4b-synthetic.conf
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/posthire
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
HAD=$(cat "$BACKUP_DIR/had_wave4_module.txt" 2>/dev/null || echo 0)
if [[ "$HAD" != "1" ]]; then
  rm -f "$ORCH/payroll_close_export_wave4.py"
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  for f in "$BACKUP_DIR"/systemd-dropins/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    [[ "$base" == "zzzzzzzzzzzzzzzzzz-payroll-wave4b-synthetic.conf" ]] && continue
    cp -a "$f" /etc/systemd/system/wathefni-orchestrator.service.d/"$base"
  done
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/dashboard-posthire" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-posthire" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_SRC"
  cp -a "$BACKUP_DIR/dashboard-posthire"/. "$DASH_SRC/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
ENV_DUMP=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ)
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2B=1'
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE3=1'
if echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE4=1'; then
  echo "REFUSE: WAVE4 still enabled after rollback" >&2
  exit 4
fi
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying wave4 modules + app routes + dashboard UI"
for f in app.py payroll_close_export_wave4.py payroll_payslip_wave3.py payroll_native_preview_wave2b.py payroll_authority_wave1.py payroll_external_adapter_wave2a.py \
         canary-prod-payroll-close-export-wave4b.py \
         smoke-test-payroll-close-export-wave4.py \
         smoke-test-payroll-close-export-wave4-ux.py \
         smoke-test-payroll-payslip-wave3.py \
         smoke-test-payroll-native-preview-wave2b.py \
         smoke-test-payroll-external-adapter-wave2a.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql" "$DASH_SRC"
[[ -f "$STAGE/migrate-payroll-close-export-wave4-prod.sh" ]] && cp -a "$STAGE/migrate-payroll-close-export-wave4-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/payroll_close_export_wave4_v1.sql" ]] && cp -a "$STAGE/payroll_close_export_wave4_v1.sql" "$ORCH/ops/sql/"
for f in CloseExportWorkspace.tsx payrollCloseExportUx.ts PayslipWorkspace.tsx payrollPayslipUx.ts payrollExternalUx.ts PostHire.tsx; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$DASH_SRC/$f"
done

test -f "$ORCH/payroll_close_export_wave4.py" || { echo "REFUSE: wave4 module not staged"; exit 3; }
grep -q 'payroll_close_export_wave4' "$ORCH/app.py" || { echo "REFUSE: app.py missing wave4 import/routes"; exit 3; }

log "writing synthetic-only Wave 4 drop-in (Wave 1/2A/2B/3 drop-ins untouched)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE4=1
Environment=WATHEFNI_PAYROLL_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS=PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4B,W4
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/payroll-wave4b-synthetic.conf"

log "migrate schema (ACK)"
chmod +x "$ORCH/ops/migrate-payroll-close-export-wave4-prod.sh"
ACK_PRODUCTION_PAYROLL_W4B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-payroll-close-export-wave4-prod.sh" \
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
  sha256sum "$ORCH/payroll_close_export_wave4.py" "$ORCH/app.py" "$ORCH/payroll_payslip_wave3.py" "$ORCH/payroll_native_preview_wave2b.py" "$ORCH/payroll_authority_wave1.py" "$ORCH/payroll_external_adapter_wave2a.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'PAYROLL|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/payroll-wave4b-flags.txt"
import os
import payroll_close_export_wave4 as w4
import payroll_payslip_wave3 as w3
import payroll_native_preview_wave2b as w2b
import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
print("PAYROLL_WAVE4", os.environ.get("WATHEFNI_PAYROLL_WAVE4"))
print("SYNTHETIC_ONLY", w4.payroll_wave4_synthetic_only())
print("enabled", w4.payroll_wave4_enabled())
print("company", w4.payroll_wave4_enabled_for_company("WATHEFNI"))
print("markers", w4.synthetic_key_markers())
print("prefixes", w4.synthetic_phone_prefixes())
h = w4.honesty_payload()
print("honesty", {k: h[k] for k in (
  "payment_processing","posts_payment","journal_drafts","journals",
  "bank_export_contract","bank_files","bank_connection","wps","ashal",
  "native_results_authoritative","external_payroll_authority",
  "ai_calculations","pifss","eos","synthetic_only"
)})
assert w4.payroll_wave4_enabled() and w4.payroll_wave4_synthetic_only()
assert w4.payroll_wave4_enabled_for_company("WATHEFNI")
assert h["payment_processing"] == "disabled"
assert h["posts_payment"] is False
assert h["bank_files"] is False and h["bank_connection"] is False
assert h["wps"] is False and h["ashal"] is False
assert h["journals"] is False and h["journal_drafts"] is True
assert h["bank_export_contract"] is True
assert h["native_results_authoritative"] is False
assert h["external_payroll_authority"] == "external"
assert pyw1.payroll_wave1_enabled()
assert w2a.payroll_wave2a_enabled() and w2a.payroll_wave2a_synthetic_only()
assert w2b.payroll_wave2b_enabled() and w2b.payroll_wave2b_synthetic_only()
assert w3.payroll_wave3_enabled() and w3.payroll_wave3_synthetic_only()
print("flags_ok_synthetic=true")
print("ACK_OK")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
