#!/usr/bin/env bash
# Compliance Wave 1-B — production WATHEFNI synthetic Findings Contract deploy.
# Deploys Wave 1 compliance findings code + dashboard dist.
# Enforces SYNTHETIC_ONLY. Document compliance only.
# No AI / government APIs / fines / filings / legal-compliance claims.
set -euo pipefail

STAMP="${STAMP:?}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-compliance-wave1b-${STAMP}"
REMOTE_EVID="/opt/wathefni/production-evidence/compliance-wave1b-prod-canary/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/compliance-w1b-prod-stage}"
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-compliance-wave1b-synthetic.conf
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
  sha256sum "$ORCH/app.py" 2>/dev/null || true
  ls -la "$ORCH/compliance_findings_wave1.py" 2>&1 || echo "compliance_findings_wave1.py absent"
  echo "=== flags before ==="
  tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ \
    | grep -E 'COMPLIANCE_WAVE1|ANALYTICS_WAVE1|CAPTURE_INGEST|DASHBOARD_DIST' | sort || true
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

INGEST=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep '^WATHEFNI_ATTENDANCE_CAPTURE_INGEST=' || echo "unset")
echo "$INGEST" | tee "$REMOTE_EVID/preflight/ingest-before.txt"
if echo "$INGEST" | grep -qiE '=on|=true|=1|=yes'; then
  echo "REFUSE: CAPTURE_INGEST must remain off" >&2
  exit 3
fi

log "backing up modules + dropins + dashboard"
mkdir -p "$BACKUP/modules"
for f in app.py compliance_findings_wave1.py analytics_attention_wave1.py \
         kuwait_pilot_document_journey.py kuwait_first_client_foundation.py; do
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
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-compliance-wave1b-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  if [[ ! -f "$BACKUP_DIR/modules/compliance_findings_wave1.py" ]]; then
    rm -f "$ORCH/compliance_findings_wave1.py"
  fi
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
echo ROLLBACK_OK
# Note: durable wave ACK rows are intentionally retained (audit). Canary-tagged rows are cleaned by canary.
RB
chmod +x "$BACKUP/ROLLBACK.sh"
cp -a "$BACKUP/ROLLBACK.sh" "$REMOTE_EVID/backup/ROLLBACK.sh"

log "deploying compliance wave1 modules"
for f in app.py compliance_findings_wave1.py analytics_attention_wave1.py \
         kuwait_pilot_document_journey.py kuwait_first_client_foundation.py \
         canary-prod-compliance-findings-wave1b.py \
         smoke-test-compliance-findings-wave1.py \
         smoke-test-compliance-freeze-regression.py \
         smoke-test-analytics-freeze-regression.py \
         smoke-test-employees360-freeze-regression.py \
         smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py \
         smoke-test-leave-freeze-regression.py \
         smoke-test-shifts-freeze-regression.py \
         canary-prod-analytics-attention-wave1b.py; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" "$ORCH/$f"
done
mkdir -p "$ORCH/ops"
[[ -f "$STAGE/migrate-compliance-findings-wave1-prod.sh" ]] && cp -a "$STAGE/migrate-compliance-findings-wave1-prod.sh" "$ORCH/ops/"
[[ -f "$STAGE/deploy-compliance-wave1b-prod-synthetic.sh" ]] && cp -a "$STAGE/deploy-compliance-wave1b-prod-synthetic.sh" "$ORCH/ops/"

if [[ -d "$STAGE/dashboard-dist" ]] && [[ -n "$(ls -A "$STAGE/dashboard-dist" 2>/dev/null || true)" ]]; then
  log "deploying dashboard dist"
  mkdir -p "$DASH_DIST" "$DASH_DIST_LEGACY"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST/"
  rsync -a --delete "$STAGE/dashboard-dist/" "$DASH_DIST_LEGACY/"
fi
mkdir -p /opt/wathefni/apps/wathefni-dashboard/src/posthire
for f in PostHire.tsx complianceFindingsWave1.test.ts; do
  [[ -f "$STAGE/$f" ]] && cp -a "$STAGE/$f" /opt/wathefni/apps/wathefni-dashboard/src/posthire/ || true
done
[[ -f "$STAGE/App.tsx" ]] && mkdir -p /opt/wathefni/apps/wathefni-dashboard/src && cp -a "$STAGE/App.tsx" /opt/wathefni/apps/wathefni-dashboard/src/ || true
[[ -f "$STAGE/types.ts" ]] && cp -a "$STAGE/types.ts" /opt/wathefni/apps/wathefni-dashboard/src/ || true

log "writing synthetic-only drop-in"
cat > "$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_COMPLIANCE_WAVE1=1
Environment=WATHEFNI_COMPLIANCE_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_ONLY=1
Environment=WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_KEY_MARKERS=CFW1,CFW1-SYNTH|
Environment=WATHEFNI_COMPLIANCE_WAVE1_SYNTHETIC_PHONE_PREFIXES=965541
Environment=WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
EOF

log "migrate ACK schema"
chmod +x "$ORCH/ops/migrate-compliance-findings-wave1-prod.sh"
ACK_PRODUCTION_COMPLIANCE_W1B=YES ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/migrate-compliance-findings-wave1-prod.sh" \
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
  sha256sum "$ORCH/app.py" "$ORCH/compliance_findings_wave1.py"
  echo "=== flags after ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'COMPLIANCE_WAVE1|CAPTURE_INGEST|DASHBOARD_DIST' | sort
} | tee "$REMOTE_EVID/flags/after-deploy.txt"

PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/"$PID"/environ
"$PYBIN" - <<'PY' | tee "$REMOTE_EVID/flags/compliance-wave1-flags.txt"
import os, compliance_findings_wave1 as w, analytics_attention_wave1 as a
print("COMPLIANCE_WAVE1", os.environ.get("WATHEFNI_COMPLIANCE_WAVE1"))
print("SYNTHETIC_ONLY", w.compliance_wave1_synthetic_only())
print("enabled", w.compliance_wave1_enabled())
print("company", w.compliance_wave1_enabled_for_company("WATHEFNI"))
print("markers", w.synthetic_key_markers())
print("prefixes", w.synthetic_phone_prefixes())
h = w.honesty_payload()
print("honesty", {k: h[k] for k in (
    "document_compliance_only","government_verified","legal_compliance_claims",
    "fine_calculations","ai","analytics_excludes_compliance","synthetic_only"
)})
assert w.compliance_wave1_enabled()
assert w.compliance_wave1_synthetic_only()
assert w.compliance_wave1_enabled_for_company("WATHEFNI")
assert h["government_verified"] is False
assert h["legal_compliance_claims"] is False
assert h["fine_calculations"] is False
assert a.honesty_payload()["compliance_metrics"] is False
print("flags_ok_synthetic=true")
PY

DIST=/opt/wathefni/dashboard-dist
{
  grep -Rql 'Findings by severity\|النتائج حسب الخطورة' "$DIST" && echo UI_FINDINGS_COPY_OK || echo UI_FINDINGS_COPY_MISSING
  grep -Rql 'Never government verified\|ليست تحققاً حكومياً' "$DIST" && echo UI_HONESTY_COPY_OK || echo UI_HONESTY_COPY_MISSING
  grep -Rql 'sm:grid-cols-2\|sm:grid-cols-3' "$DIST" && echo UI_RESPONSIVE_GRID_OK || echo UI_RESPONSIVE_GRID_SOFT
} | tee "$REMOTE_EVID/ui/dist-checks.txt"

echo "DEPLOY_OK stamp=$STAMP backup=$BACKUP evid=$REMOTE_EVID"
