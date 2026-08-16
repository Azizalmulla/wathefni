#!/usr/bin/env bash
# Payroll Final — production synthetic marker deploy (Waves 1–5 already frozen).
# Adds final evidence drop-in only. Does NOT start new feature waves.
# payment_processing=disabled; no remittance/filing/bank/WPS/AS'HAL/payments/AI.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-payroll-final-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-final-prod-synthetic/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/payroll-final-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzz-payroll-final-synthetic.conf
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/posthire
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} "$BACKUP"/{modules,dashboard-posthire} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
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

for f in payroll_authority_wave1.py payroll_external_adapter_wave2a.py payroll_native_preview_wave2b.py \
         payroll_payslip_wave3.py payroll_close_export_wave4.py payroll_pifss_eos_wave5.py; do
  test -f "$ORCH/$f" || { echo "REFUSE: missing $f"; exit 3; }
done

ORCH_PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
ORCH_ENV=$(tr '\0' '\n' < "/proc/$ORCH_PID/environ")
for w in WAVE1 WAVE2A WAVE2B WAVE3 WAVE4 WAVE5; do
  echo "$ORCH_ENV" | grep -q "^WATHEFNI_PAYROLL_${w}=1" || { echo "REFUSE: $w not enabled"; exit 3; }
done
for w in WAVE2A WAVE2B WAVE3 WAVE4 WAVE5; do
  echo "$ORCH_ENV" | grep -q "^WATHEFNI_PAYROLL_${w}_SYNTHETIC_ONLY=1" || { echo "REFUSE: $w SYNTHETIC_ONLY required"; exit 3; }
done

INGEST=$(echo "$ORCH_ENV" | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up modules + dropins + dashboard"
for f in app.py payroll_authority_wave1.py payroll_external_adapter_wave2a.py payroll_native_preview_wave2b.py \
         payroll_payslip_wave3.py payroll_close_export_wave4.py payroll_pifss_eos_wave5.py canary-prod-payroll-final.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
[[ -f "$DROPIN" ]] && cp -a "$DROPIN" "$BACKUP/payroll-final-synthetic.conf" || true
mkdir -p "$DASH_SRC"
for f in StatutoryWorksheetWorkspace.tsx payrollStatutoryUx.ts CloseExportWorkspace.tsx payrollCloseExportUx.ts \
         PayslipWorkspace.tsx payrollPayslipUx.ts payrollExternalUx.ts PostHire.tsx; do
  [[ -f "$DASH_SRC/$f" ]] && cp -a "$DASH_SRC/$f" "$BACKUP/dashboard-posthire/" || true
done
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzz-payroll-final-synthetic.conf
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/posthire
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  # Restore canary only; do not wipe wave modules if backup incomplete
  [[ -f "$BACKUP_DIR/modules/canary-prod-payroll-final.py" ]] && \
    cp -a "$BACKUP_DIR/modules/canary-prod-payroll-final.py" "$ORCH/" 2>/dev/null || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  for f in "$BACKUP_DIR"/systemd-dropins/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    [[ "$base" == "zzzzzzzzzzzzzzzzzzzz-payroll-final-synthetic.conf" ]] && continue
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
ENV_DUMP=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ)
for w in WAVE1 WAVE2A WAVE2B WAVE3 WAVE4 WAVE5; do
  echo "$ENV_DUMP" | grep -q "^WATHEFNI_PAYROLL_${w}=1"
done
if echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_FINAL_SYNTHETIC=1'; then
  echo "REFUSE: FINAL marker still enabled after rollback" >&2
  exit 4
fi
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying final canary + UI copies"
for f in canary-prod-payroll-final.py \
         smoke-test-payroll-pifss-eos-wave5-ux.py \
         smoke-test-payroll-close-export-wave4-ux.py \
         smoke-test-payroll-payslip-wave3-ux.py \
         smoke-test-payroll-external-ops-wave2ac-ux.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
for f in StatutoryWorksheetWorkspace.tsx payrollStatutoryUx.ts CloseExportWorkspace.tsx payrollCloseExportUx.ts \
         PayslipWorkspace.tsx payrollPayslipUx.ts payrollExternalUx.ts PostHire.tsx; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$DASH_SRC/$f"
done
test -f "$ORCH/canary-prod-payroll-final.py" || { echo "REFUSE: final canary not staged"; exit 3; }

log "writing final synthetic marker drop-in (Wave 1–5 drop-ins untouched)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_FINAL_SYNTHETIC=1
Environment=WATHEFNI_PAYROLL_FINAL_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_FINAL_SCOPE=waves_1_through_5
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/payroll-final-synthetic.conf"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator

{
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'PAYROLL|CAPTURE_INGEST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/payroll-final-flags.txt"
import os
import payroll_authority_wave1 as pyw1
import payroll_external_adapter_wave2a as w2a
import payroll_native_preview_wave2b as w2b
import payroll_payslip_wave3 as w3
import payroll_close_export_wave4 as w4
import payroll_pifss_eos_wave5 as w5
print("PAYROLL_FINAL", os.environ.get("WATHEFNI_PAYROLL_FINAL_SYNTHETIC"))
assert os.environ.get("WATHEFNI_PAYROLL_FINAL_SYNTHETIC") == "1"
assert pyw1.payroll_wave1_enabled()
assert w2a.payroll_wave2a_enabled() and w2a.payroll_wave2a_synthetic_only()
assert w2b.payroll_wave2b_enabled() and w2b.payroll_wave2b_synthetic_only()
assert w3.payroll_wave3_enabled() and w3.payroll_wave3_synthetic_only()
assert w4.payroll_wave4_enabled() and w4.payroll_wave4_synthetic_only()
assert w5.payroll_wave5_enabled() and w5.payroll_wave5_synthetic_only()
h = w5.honesty_payload()
assert h["payment_processing"] == "disabled"
assert h["remittance"] is False and h["eos_auto_payable"] is False
assert h["native_results_authoritative"] is False
assert h["external_payroll_authority"] == "external"
print("flags_ok_synthetic=true")
print("ACK_OK")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
