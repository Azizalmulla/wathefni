#!/usr/bin/env bash
# Payroll Wave 2A-C-B — production WATHEFNI synthetic external-ops deploy.
# Deploys ops workflow (adapter helpers + app routes + dashboard UI).
# Keeps WAVE2A + SYNTHETIC_ONLY. money_authority=external. vendor_claimed=false.
# Does NOT remove Wave 2A freeze posture on rollback of this wave's code.
# No bank files, native G2N, real vendor, or Wave 2B.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-payroll-wave2acb-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave2acb-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/payroll-w2acb-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-payroll-wave2ab-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
PYBIN="$ORCH/.venv/bin/python"

mkdir -p "$REMOTE_EVID"/{preflight,verify,flags,backup,schema,canary,tests,ui} "$BACKUP"/{modules,dashboard-dist,dashboard-dist-legacy} "$STAGE"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  sha256sum "$ORCH/app.py" "$ORCH/payroll_authority_wave1.py" 2>/dev/null || true
  ls -la "$ORCH/payroll_external_adapter_wave2a.py" 2>&1 || echo "payroll_external_adapter_wave2a.py absent"
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
test -f "$ORCH/payroll_external_adapter_wave2a.py" || { echo "REFUSE: Wave 2A module missing (freeze prerequisite)"; exit 3; }
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

log "backing up modules + dropin + dashboard"
for f in app.py payroll_external_adapter_wave2a.py payroll_authority_wave1.py; do
  [[ -f "$ORCH/$f" ]] && cp -a "$ORCH/$f" "$BACKUP/modules/" || true
done
[[ -f "$DROPIN" ]] && cp -a "$DROPIN" "$BACKUP/payroll-wave2ab-synthetic.conf" || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d/. "$BACKUP/systemd-dropins/" 2>/dev/null || mkdir -p "$BACKUP/systemd-dropins"
if [[ -d "$DASH_DIST" ]]; then
  rsync -a "$DASH_DIST/" "$BACKUP/dashboard-dist/" || true
fi
if [[ -d "$DASH_DIST_LEGACY" ]]; then
  rsync -a "$DASH_DIST_LEGACY/" "$BACKUP/dashboard-dist-legacy/" || true
fi
(
  cd "$BACKUP"
  find modules -type f 2>/dev/null | while read -r f; do sha256sum "$f"; done
  [[ -f payroll-wave2ab-synthetic.conf ]] && sha256sum payroll-wave2ab-synthetic.conf
) | tee "$BACKUP/SHA256SUMS"
echo "$BACKUP" > "$REMOTE_EVID/backup/BACKUP_PATH.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'RB'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-payroll-wave2ab-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
test -d "$BACKUP_DIR"
# Restore Wave 2A-C-B code; keep Wave 2A freeze drop-in from backup (still WAVE2A=1)
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
if [[ -f "$BACKUP_DIR/payroll-wave2ab-synthetic.conf" ]]; then
  cp -a "$BACKUP_DIR/payroll-wave2ab-synthetic.conf" "$DROPIN"
elif [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist-legacy" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist-legacy" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_DIST_LEGACY"
  rsync -a --delete "$BACKUP_DIR/dashboard-dist-legacy/" "$DASH_DIST_LEGACY/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
# Wave 1 + Wave 2A must remain after 2A-C-B rollback
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
echo ROLLBACK_OK
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying wave2acb modules"
for f in app.py payroll_external_adapter_wave2a.py payroll_authority_wave1.py \
         canary-prod-payroll-external-ops-wave2acb.py \
         canary-prod-payroll-external-adapter-wave2ab.py \
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
[[ -f "$STAGE/migrate-payroll-external-ops-wave2ac-prod.sh" ]] && cp -a "$STAGE/migrate-payroll-external-ops-wave2ac-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/migrate-payroll-external-adapter-wave2a-prod.sh" ]] && cp -a "$STAGE/migrate-payroll-external-adapter-wave2a-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/payroll_external_adapter_wave2a_v1.sql" ]] && cp -a "$STAGE/payroll_external_adapter_wave2a_v1.sql" "$ORCH/ops/sql/"
[[ -f "$STAGE/payroll_authority_wave1_v1.sql" ]] && cp -a "$STAGE/payroll_authority_wave1_v1.sql" "$ORCH/ops/sql/"

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist (external payroll ops workspace)"
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  mkdir -p "$DASH_DIST_LEGACY"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST_LEGACY/"
  echo DASHBOARD_DIST_DEPLOYED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
else
  echo DASHBOARD_DIST_UNCHANGED | tee "$REMOTE_EVID/ui/dashboard-deploy.txt"
fi

log "writing synthetic-only Wave 2A drop-in (markers include PYW2ACB; Wave 1 retained elsewhere)"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
Environment=WATHEFNI_PAYROLL_WAVE2A=1
Environment=WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_KEY_MARKERS=PYW2ACB,PYW2ACB-SYNTH|,PYW2AB,PYW2AB-SYNTH|,PYW2A,PYW2A-SYNTH|,PYW1,PYW1-SYNTH|
Environment=WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_PHONE_PREFIXES=965540,965539
EOF
cp -a "$DROPIN" "$REMOTE_EVID/flags/payroll-wave2acb-synthetic.conf"

log "migrate/ACK ops workflow"
chmod +x "$ORCH/ops/migrate-payroll-external-ops-wave2ac-prod.sh"
ACK_PRODUCTION_PAYROLL_W2ACB=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-payroll-external-ops-wave2ac-prod.sh" \
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
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/payroll-wave2acb-flags.txt"
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
assert "PYW2ACB" in w.synthetic_key_markers() or any("PYW2ACB" in m for m in w.synthetic_key_markers())
assert h["payment_processing"] == "disabled"
assert h["money_authority"] == "external"
assert h["wathefni_money_authority"] is False
assert h["vendor_claimed"] is False
assert h["posts_payment"] is False
assert pyw1.payroll_wave1_enabled()
assert callable(w.workspace_bootstrap)
assert callable(w.replace_import_results)
print("flags_ok_synthetic=true")
print("ACK_OK")
PY

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
