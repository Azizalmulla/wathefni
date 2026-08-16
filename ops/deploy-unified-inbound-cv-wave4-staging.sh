#!/usr/bin/env bash
# Contained staging deploy for Unified Inbound CV Wave 4 (surgical).
# Never touches production systemd units or production dual-write flags.
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=20 "$VPS")
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$LOCAL_ROOT/wathefni-orchestrator"
REMOTE_STAGE="/tmp/unified-inbound-cv-wave4-${STAMP}"
EVIDENCE_ROOT="/opt/wathefni/staging/staging-evidence/unified-inbound-cv-wave4"
BACKUP_ROOT="/opt/wathefni/backups/staging-pre-unified-inbound-cv-wave4-${STAMP}"
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
  "$ORCH_SRC/inbound_cv_person_registry.py" \
  "$ORCH_SRC/inbound_cv_wave4.py" \
  "$ORCH_SRC/talent_pool_authority.py" \
  "$ORCH_SRC/job_binding_authority.py" \
  "$ORCH_SRC/verified_job_binding_gate.py" \
  "$ORCH_SRC/candidate_knowledge_wave4.py" \
  "$ORCH_SRC/candidate_knowledge_types.py" \
  "$ORCH_SRC/candidate_knowledge_authority.py" \
  "$LOCAL_ROOT/ops/patch-staging-app-unified-inbound-cv-wave4.py" \
  "$LOCAL_ROOT/ops/unified-inbound-cv-wave4-staging-qualify.py" \
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
  for f in inbound_cv_person_registry.py inbound_cv_wave4.py talent_pool_authority.py \
           job_binding_authority.py verified_job_binding_gate.py candidate_knowledge_wave4.py \
           inbound_cv_processing.py inbound_cv_adapters.py candidate_knowledge_authority.py \
           candidate_knowledge_types.py; do
    rm -f "\$STAGING_ORCH/\$f"
    [[ -f "\$BACKUP_ROOT/\$f" ]] && cp -a "\$BACKUP_ROOT/\$f" "\$STAGING_ORCH/\$f" || true
  done
  # Restore prior drop-in from backup if present; else keep Wave 3 baseline flags.
  if [[ -f "\$BACKUP_ROOT/unified-inbound-cv.conf" ]]; then
    cp -a "\$BACKUP_ROOT/unified-inbound-cv.conf" "\$DROPIN_FILE"
  fi
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
[[ -f "\$DROPIN_FILE" ]] && cp -a "\$DROPIN_FILE" "\$BACKUP_ROOT/unified-inbound-cv.conf" || true
for f in inbound_cv_person_registry.py inbound_cv_wave4.py talent_pool_authority.py \
         job_binding_authority.py verified_job_binding_gate.py candidate_knowledge_wave4.py \
         inbound_cv_processing.py inbound_cv_adapters.py candidate_knowledge_authority.py \
         candidate_knowledge_types.py; do
  [[ -f "\$STAGING_ORCH/\$f" ]] && cp -a "\$STAGING_ORCH/\$f" "\$BACKUP_ROOT/\$f" || true
done
sha256sum "\$BACKUP_ROOT/app.py" | tee "\$EV/backup.sha256"

log "install modules"
for f in inbound_cv_intake.py inbound_cv_processing.py inbound_cv_adapters.py \
         inbound_cv_person_registry.py inbound_cv_wave4.py talent_pool_authority.py \
         job_binding_authority.py verified_job_binding_gate.py candidate_knowledge_wave4.py \
         candidate_knowledge_types.py candidate_knowledge_authority.py; do
  cp -a "\$REMOTE_STAGE/\$f" "\$STAGING_ORCH/\$f"
done
cp -a "\$REMOTE_STAGE/unified-inbound-cv-wave4-staging-qualify.py" "\$STAGING_ORCH/ops/"
cp -a "\$REMOTE_STAGE/patch-staging-app-unified-inbound-cv-wave4.py" "\$STAGING_ORCH/ops/"

log "surgical patch staging app.py"
/opt/wathefni/orchestrator/.venv/bin/python "\$STAGING_ORCH/ops/patch-staging-app-unified-inbound-cv-wave4.py" "\$STAGING_ORCH/app.py" | tee "\$EV/patch-result.json"
/opt/wathefni/orchestrator/.venv/bin/python -m py_compile \
  "\$STAGING_ORCH/app.py" \
  "\$STAGING_ORCH/inbound_cv_wave4.py" \
  "\$STAGING_ORCH/inbound_cv_person_registry.py" \
  "\$STAGING_ORCH/talent_pool_authority.py" \
  "\$STAGING_ORCH/job_binding_authority.py" \
  "\$STAGING_ORCH/verified_job_binding_gate.py" \
  "\$STAGING_ORCH/candidate_knowledge_wave4.py"

log "enable staging-only Wave 4 flags (shadow gate; no enforce)"
cat > "\$DROPIN_FILE" <<'EOF'
[Service]
Environment=WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on
Environment=WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE=on
Environment=WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER=on
Environment=WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS=on
Environment=WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING=on
Environment=WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on
Environment=WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE=on
Environment=WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES=on
Environment=WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS=on
Environment=WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY=on
Environment=WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE=on
Environment=WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on
EOF
# Explicitly do NOT set WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE
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
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_' | tee "\$EV/staging-flags.txt"
grep -q 'WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on' "\$EV/staging-flags.txt"
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/staging-flags.txt"

# Production unit must not have wave4 drop-in
if [[ -e /etc/systemd/system/wathefni-orchestrator.service.d/unified-inbound-cv.conf ]]; then
  echo "production drop-in present" > /tmp/wave4-prod-flags-check.txt
  exit 1
fi
PROD_PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service || echo 0)
if [[ "\$PROD_PID" != "0" && -r /proc/\$PROD_PID/environ ]]; then
  if tr '\\0' '\\n' < /proc/\$PROD_PID/environ | grep -q 'WATHEFNI_UNIFIED_INBOUND_CV_WAVE4='; then
    echo "production has wave4 flag" > /tmp/wave4-prod-flags-check.txt
    exit 1
  fi
fi
echo "not_present" > /tmp/wave4-prod-flags-check.txt
cp -a /tmp/wave4-prod-flags-check.txt "\$EV/production-flags.txt"

log "qualify"
WAVE4_EVIDENCE="\$EV" /opt/wathefni/orchestrator/.venv/bin/python \
  "\$STAGING_ORCH/ops/unified-inbound-cv-wave4-staging-qualify.py" | tee "\$EV/qualify.stdout.json"
test "\$(python3 -c "import json;print(json.load(open('\$EV/qualification.json'))['failed'])")" = "0"

log "DONE Wave 4 staging qualify PASS evidence=\$EV"
trap - ERR
REMOTE

log "fetch evidence"
mkdir -p "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-wave4"
scp -o BatchMode=yes -r \
  "$VPS:$EVIDENCE_ROOT/$STAMP/" \
  "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-wave4/" || true
log "local evidence copy: ops/screenshots/unified-inbound-cv-wave4/$STAMP"
