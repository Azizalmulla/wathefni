#!/usr/bin/env bash
# Payroll Wave 2A-D-B — production WATHEFNI synthetic External Run Operability deploy.
# Deploys operability UI/APIs on frozen Wave 2A adapter.
# Keeps WAVE2A + SYNTHETIC_ONLY. money_authority=external. vendor_claimed=false.
# No bank/WPS/PIFSS/EOS/payments/AI. No attendance/leave/shifts package expansion.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-payroll-wave2adb-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave2adb-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/payroll-w2adb-stage}"
# Sorts after final payroll drop-in so PYW2ADB markers win for Wave 2A synthetic keys.
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzz-payroll-wave2adb-operability.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} \
  "$BACKUP"/{modules,dashboard-dist,dashboard-dist-legacy,systemd-dropins} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/payroll_external_adapter_wave2a.py" 2>/dev/null || true
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'PAYROLL|ATTENDANCE_CAPTURE_INGEST|DASHBOARD_DIST' | sort || true
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
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
  | grep -q '^WATHEFNI_PAYROLL_WAVE1=1' || { echo "REFUSE: Wave 1 flag not enabled"; exit 3; }
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
  | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1' || { echo "REFUSE: Wave 2A flag not enabled"; exit 3; }

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up modules + dropins + dashboard"
mkdir -p "$BACKUP/modules"
for f in app.py payroll_external_adapter_wave2a.py payroll_authority_wave1.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || true
if [[ -d "$DASH_DIST" ]]; then
  rsync -a "$DASH_DIST/" "$BACKUP/dashboard-dist/" || true
fi
if [[ -d "$DASH_DIST_LEGACY" ]]; then
  rsync -a "$DASH_DIST_LEGACY/" "$BACKUP/dashboard-dist-legacy/" || true
fi
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzz-payroll-wave2adb-operability.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
  rm -f "$DROPIN"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist-legacy" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist-legacy" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist-legacy/" "$DASH_DIST_LEGACY/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1'
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying wave2adb modules"
for f in app.py payroll_external_adapter_wave2a.py payroll_authority_wave1.py \
         canary-prod-payroll-external-ops-wave2adb.py \
         canary-prod-payroll-external-ops-wave2acb.py \
         smoke-test-payroll-external-ops-wave2ad.py \
         smoke-test-payroll-external-ops-wave2ad-ux.py \
         smoke-test-payroll-external-ops-wave2ac.py \
         smoke-test-payroll-external-ops-wave2ac-ux.py \
         smoke-test-payroll-external-adapter-wave2a.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops/sql"
[[ -f "$STAGE/migrate-payroll-external-ops-wave2ad-prod.sh" ]] && cp -a "$STAGE/migrate-payroll-external-ops-wave2ad-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/deploy-payroll-wave2adb-prod-synthetic.sh" ]] && cp -a "$STAGE/deploy-payroll-wave2adb-prod-synthetic.sh" "$ORCH/ops/"
[[ -f "$STAGE/payroll_external_adapter_wave2a_v1.sql" ]] && cp -a "$STAGE/payroll_external_adapter_wave2a_v1.sql" "$ORCH/ops/sql/"
[[ -f "$STAGE/payroll_authority_wave1_v1.sql" ]] && cp -a "$STAGE/payroll_authority_wave1_v1.sql" "$ORCH/ops/sql/"

mkdir -p /opt/wathefni/apps/wathefni-dashboard/src/posthire /opt/wathefni/apps/wathefni-dashboard/src/lib
for f in ExternalPayrollWorkspace.tsx payrollExternalUx.ts PayslipWorkspace.tsx CloseExportWorkspace.tsx PostHire.tsx; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" /opt/wathefni/apps/wathefni-dashboard/src/posthire/ || true
done
[[ -f "$STAGE/api.ts" ]] && cp -a "$STAGE/api.ts" /opt/wathefni/apps/wathefni-dashboard/src/lib/ || true
[[ -f "$STAGE/types.ts" ]] && cp -a "$STAGE/types.ts" /opt/wathefni/apps/wathefni-dashboard/src/ || true

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist"
  mkdir -p "$DASH_DIST" "$DASH_DIST_LEGACY"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST_LEGACY/"
  echo DASHBOARD_DIST_DEPLOYED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
else
  echo DASHBOARD_DIST_UNCHANGED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
fi

log "writing Wave 2A-D-B synthetic-only operability drop-in"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
Environment=WATHEFNI_PAYROLL_WAVE2A=1
Environment=WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS=PYW2ADB,PYW2ADB-SYNTH|,PYW2ACB,PYW2ACB-SYNTH|,PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES=965540,965539
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/payroll-wave2adb-operability.conf"

log "migrate/ACK operability"
chmod +x "$ORCH/ops/migrate-payroll-external-ops-wave2ad-prod.sh"
ACK_PRODUCTION_PAYROLL_W2ADB=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-payroll-external-ops-wave2ad-prod.sh" \
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
  sha256sum "$ORCH/app.py" "$ORCH/payroll_external_adapter_wave2a.py" "$ORCH/payroll_authority_wave1.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'PAYROLL|CAPTURE_INGEST|DASHBOARD_DIST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/payroll-wave2adb-flags.txt"
import os, payroll_external_adapter_wave2a as w, payroll_authority_wave1 as pyw1
print("PAYROLL_WAVE2A", os.environ.get("WATHEFNI_PAYROLL_WAVE2A"))
print("SYNTHETIC_ONLY", w.payroll_wave2a_synthetic_only())
print("markers", w.synthetic_key_markers())
h = w.honesty_payload()
print("honesty", {k: h.get(k) for k in (
  "payment_processing","money_authority","wathefni_money_authority","posts_payment",
  "vendor_claimed","bank_files","ai","wave1_contracts_unchanged","wave2a_adapter_contracts_unchanged",
  "payroll_wave2ad_operability_version"
)})
pkg = h.get("package_contents") or {}
print("package_attendance_leave_shifts", pkg.get("attendance_leave_shifts_packaged"))
assert w.payroll_wave2a_enabled() and w.payroll_wave2a_synthetic_only()
assert w.payroll_wave2a_enabled_for_company("WATHEFNI")
assert any("PYW2ADB" in m for m in w.synthetic_key_markers())
assert h["payment_processing"] == "disabled"
assert h["money_authority"] == "external"
assert h["vendor_claimed"] is False
assert h.get("ai") is False
assert pkg.get("attendance_leave_shifts_packaged") is False
assert pyw1.payroll_wave1_enabled()
assert callable(w.acknowledge_quarantine)
print("flags_ok_synthetic=true")
print("ACK_OK")
PY

DIST=/opt/wathefni/dashboard-dist
{
  if grep -Rql 'External payroll run\|تشغيل الرواتب الخارجية\|Who pays' "$DIST" 2>/dev/null; then
    echo UI_OPERABILITY_COPY_OK
  else
    echo UI_OPERABILITY_COPY_CHECK
  fi
} | tee "$REMOTE_EVID/ui/dist-checks.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
