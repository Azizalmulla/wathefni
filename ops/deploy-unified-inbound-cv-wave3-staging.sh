#!/usr/bin/env bash
# Contained staging deploy for Unified Inbound CV Wave 1–3 (surgical).
# Deploys modules + patches staging app.py in place. Never touches production.
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=20 "$VPS")
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$LOCAL_ROOT/wathefni-orchestrator"
REMOTE_STAGE="/tmp/unified-inbound-cv-wave3-${STAMP}"
EVIDENCE_ROOT="/opt/wathefni/staging/staging-evidence/unified-inbound-cv-wave3"
BACKUP_ROOT="/opt/wathefni/backups/staging-pre-unified-inbound-cv-${STAMP}"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
DROPIN_DIR="/etc/systemd/system/wathefni-orchestrator-staging.service.d"
DROPIN_FILE="${DROPIN_DIR}/unified-inbound-cv.conf"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "upload artifacts"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
scp -o BatchMode=yes \
  "$ORCH_SRC/inbound_cv_intake.py" \
  "$ORCH_SRC/inbound_cv_processing.py" \
  "$ORCH_SRC/inbound_cv_adapters.py" \
  "$ORCH_SRC/durable_email_ingress.py" \
  "$LOCAL_ROOT/ops/patch-staging-app-unified-inbound-cv-wave3.py" \
  "$LOCAL_ROOT/ops/unified-inbound-cv-wave3-staging-qualify.py" \
  "$VPS:$REMOTE_STAGE/"

"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
STAMP='$STAMP'
REMOTE_STAGE='$REMOTE_STAGE'
EVIDENCE_ROOT='$EVIDENCE_ROOT'
BACKUP_ROOT='$BACKUP_ROOT'
STAGING_ORCH='$STAGING_ORCH'
DROPIN_DIR='$DROPIN_DIR'
DROPIN_FILE='$DROPIN_FILE'
EV="\$EVIDENCE_ROOT/\$STAMP"
mkdir -p "\$EV" "\$BACKUP_ROOT" "\$DROPIN_DIR" "\$STAGING_ORCH/ops"
chmod 700 "\$EVIDENCE_ROOT" "\$EV" "\$BACKUP_ROOT"

log() { printf '%s %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\$*" | tee -a "\$EV/deploy.log"; }

rollback() {
  log "ROLLBACK from \$BACKUP_ROOT"
  systemctl stop wathefni-orchestrator-staging.service || true
  cp -a "\$BACKUP_ROOT/app.py" "\$STAGING_ORCH/app.py"
  cp -a "\$BACKUP_ROOT/durable_email_ingress.py" "\$STAGING_ORCH/durable_email_ingress.py"
  for f in inbound_cv_intake.py inbound_cv_processing.py inbound_cv_adapters.py; do
    rm -f "\$STAGING_ORCH/\$f"
    [[ -f "\$BACKUP_ROOT/\$f" ]] && cp -a "\$BACKUP_ROOT/\$f" "\$STAGING_ORCH/\$f" || true
  done
  rm -f "\$DROPIN_FILE"
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator-staging.service
  for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf http://127.0.0.1:8011/health >/dev/null; then
      log "rollback health ok"
      return 0
    fi
    sleep 1
  done
  log "rollback health FAILED"
  return 1
}

trap 'log "deploy failed"; rollback; exit 1' ERR

log "preflight"
test ! -e /etc/systemd/system/wathefni-orchestrator.service.d/unified-inbound-cv.conf
systemctl is-active wathefni-orchestrator-staging.service | tee "\$EV/preflight-active.txt"
curl -sf http://127.0.0.1:8011/health | tee "\$EV/preflight-health.txt"

log "backup"
cp -a "\$STAGING_ORCH/app.py" "\$BACKUP_ROOT/app.py"
cp -a "\$STAGING_ORCH/durable_email_ingress.py" "\$BACKUP_ROOT/durable_email_ingress.py"
sha256sum "\$BACKUP_ROOT/app.py" "\$BACKUP_ROOT/durable_email_ingress.py" | tee "\$EV/backup.sha256"

log "install modules"
cp -a "\$REMOTE_STAGE/inbound_cv_intake.py" "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE/inbound_cv_processing.py" "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE/inbound_cv_adapters.py" "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE/durable_email_ingress.py" "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE/unified-inbound-cv-wave3-staging-qualify.py" "\$STAGING_ORCH/ops/"
cp -a "\$REMOTE_STAGE/patch-staging-app-unified-inbound-cv-wave3.py" "\$STAGING_ORCH/ops/"

log "surgical patch staging app.py"
/opt/wathefni/orchestrator/.venv/bin/python "\$STAGING_ORCH/ops/patch-staging-app-unified-inbound-cv-wave3.py" "\$STAGING_ORCH/app.py" | tee "\$EV/patch-result.json"
# compile check without starting uvicorn
/opt/wathefni/orchestrator/.venv/bin/python -m py_compile "\$STAGING_ORCH/app.py" "\$STAGING_ORCH/inbound_cv_intake.py" "\$STAGING_ORCH/inbound_cv_processing.py" "\$STAGING_ORCH/inbound_cv_adapters.py" "\$STAGING_ORCH/durable_email_ingress.py"

log "enable staging-only dual-write flags"
cat > "\$DROPIN_FILE" <<'EOF'
[Service]
Environment=WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on
Environment=WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE=on
Environment=WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER=on
Environment=WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS=on
Environment=WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING=on
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service

log "wait for health"
ok=0
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then
    ok=1
    break
  fi
  sleep 1
done
test "\$ok" = "1"
curl -sf http://127.0.0.1:8011/health | tee "\$EV/post-restart-health.txt"

PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_INTAKE|UNIFIED_CV|UNIFIED_INBOUND|UNIFIED_ADAPTER' | tee "\$EV/staging-flags.txt"
grep -q 'WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on' "\$EV/staging-flags.txt"

PPID_PROD=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
if tr '\\0' '\\n' < /proc/\$PPID_PROD/environ | grep -q 'WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on'; then
  echo "production dual-write unexpectedly on" >&2
  exit 1
fi
echo "production_dual_write=off" | tee "\$EV/production-dual-write.txt"

log "run qualify"
WAVE3_EVIDENCE="\$EV" /opt/wathefni/orchestrator/.venv/bin/python \
  "\$STAGING_ORCH/ops/unified-inbound-cv-wave3-staging-qualify.py" | tee "\$EV/qualify.stdout.json"

sha256sum \
  "\$STAGING_ORCH/inbound_cv_intake.py" \
  "\$STAGING_ORCH/inbound_cv_processing.py" \
  "\$STAGING_ORCH/inbound_cv_adapters.py" \
  "\$STAGING_ORCH/durable_email_ingress.py" \
  "\$STAGING_ORCH/app.py" | tee "\$EV/deployed.sha256"

printf '%s\n' "\$STAMP" > /tmp/unified-inbound-cv-wave3.stamp
printf '%s\n' "\$EV" > /tmp/unified-inbound-cv-wave3.evidence
printf '%s\n' "\$BACKUP_ROOT" > /tmp/unified-inbound-cv-wave3.backup
log "PASS evidence=\$EV"
REMOTE

log "fetch evidence"
scp -o BatchMode=yes "$VPS:/tmp/unified-inbound-cv-wave3.evidence" /tmp/unified-inbound-cv-wave3.evidence
EV_PATH="$(cat /tmp/unified-inbound-cv-wave3.evidence)"
mkdir -p "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-wave3"
scp -o BatchMode=yes \
  "$VPS:$EV_PATH/qualification.json" \
  "$VPS:$EV_PATH/qualify.stdout.json" \
  "$VPS:$EV_PATH/staging-flags.txt" \
  "$VPS:$EV_PATH/deployed.sha256" \
  "$VPS:$EV_PATH/post-restart-health.txt" \
  "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-wave3/" || true
log "done evidence=$EV_PATH"
