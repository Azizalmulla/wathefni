#!/usr/bin/env bash
# WATHEFNI Unified Inbound CV Wave 1–4 production-dark migration.
# Shadow gate only. No ENFORCE. No channel cutover. No external tenants.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS")
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$LOCAL_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_STAGE="/tmp/unified-inbound-cv-prod-dark-${STAMP}"
BACKUP_ROOT="/opt/wathefni/backups/production-pre-unified-inbound-cv-dark-${STAMP}"
EVIDENCE_ROOT="/opt/wathefni/production-evidence/unified-inbound-cv-dark"
PROD_ORCH="/opt/wathefni/orchestrator"
DROPIN_DIR="/etc/systemd/system/wathefni-orchestrator.service.d"
DROPIN_FILE="${DROPIN_DIR}/unified-inbound-cv.conf"
FLAGS_FILE="/opt/wathefni/var/unified-inbound-cv.production.env"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "preflight production isolation"
"${SSH[@]}" "set -euo pipefail
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  db=\$(psql \"\$WATHEFNI_DATABASE_URL\" -Atc 'SELECT current_database()')
  test \"\$db\" = 'wathefni'
  test \"\$db\" != 'wathefni_staging'
  PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
  if tr '\\0' '\\n' < /proc/\$PID/environ | grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on'; then
    echo REFUSING_ENFORCE_ALREADY_ON; exit 2
  fi
  echo PREFLIGHT_OK db=\$db
"

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
  "$ORCH_SRC/durable_email_ingress.py" \
  "$LOCAL_ROOT/ops/patch-staging-app-unified-inbound-cv-wave3.py" \
  "$LOCAL_ROOT/ops/patch-production-app-unified-inbound-cv-dark.py" \
  "$LOCAL_ROOT/ops/unified-inbound-cv-production-dark-observe.py" \
  "$VPS:$REMOTE_STAGE/"

log "backup + deploy + observe on host"
"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
STAMP='$STAMP'
REMOTE_STAGE='$REMOTE_STAGE'
BACKUP_ROOT='$BACKUP_ROOT'
EVIDENCE_ROOT='$EVIDENCE_ROOT'
PROD_ORCH='$PROD_ORCH'
DROPIN_DIR='$DROPIN_DIR'
DROPIN_FILE='$DROPIN_FILE'
FLAGS_FILE='$FLAGS_FILE'
EV="\$EVIDENCE_ROOT/\$STAMP"
mkdir -p "\$EV" "\$BACKUP_ROOT/modules" "\$DROPIN_DIR" /opt/wathefni/var "\$PROD_ORCH/ops"
chmod 700 "\$EVIDENCE_ROOT" "\$EV" "\$BACKUP_ROOT"

log() { printf '%s %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\$*" | tee -a "\$EV/deploy.log"; }

rollback() {
  log "ROLLBACK from \$BACKUP_ROOT"
  systemctl stop wathefni-orchestrator.service || true
  cp -a "\$BACKUP_ROOT/app.py" "\$PROD_ORCH/app.py"
  cp -a "\$BACKUP_ROOT/durable_email_ingress.py" "\$PROD_ORCH/durable_email_ingress.py"
  for f in inbound_cv_intake.py inbound_cv_processing.py inbound_cv_adapters.py \
           inbound_cv_person_registry.py inbound_cv_wave4.py talent_pool_authority.py \
           job_binding_authority.py verified_job_binding_gate.py candidate_knowledge_wave4.py \
           candidate_knowledge_types.py candidate_knowledge_authority.py; do
    rm -f "\$PROD_ORCH/\$f"
    [[ -f "\$BACKUP_ROOT/modules/\$f" ]] && cp -a "\$BACKUP_ROOT/modules/\$f" "\$PROD_ORCH/\$f" || true
  done
  if [[ -f "\$BACKUP_ROOT/unified-inbound-cv.conf" ]]; then
    cp -a "\$BACKUP_ROOT/unified-inbound-cv.conf" "\$DROPIN_FILE"
  else
    rm -f "\$DROPIN_FILE"
  fi
  if [[ -f "\$BACKUP_ROOT/unified-inbound-cv.production.env" ]]; then
    cp -a "\$BACKUP_ROOT/unified-inbound-cv.production.env" "\$FLAGS_FILE"
  else
    rm -f "\$FLAGS_FILE"
  fi
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator.service
  for i in \$(seq 1 60); do
    if curl -sf http://127.0.0.1:8010/health >/dev/null; then
      log "rollback health ok"
      echo ROLLBACK_OK > "\$EV/rollback-proof.txt"
      return 0
    fi
    sleep 1
  done
  log "rollback health FAILED"
  return 1
}

trap 'log "deploy failed"; rollback; exit 1' ERR

log "predeploy evidence"
{
  echo timestamp=\$(date -u +%FT%TZ)
  echo health=\$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health)
  echo orch=\$PROD_ORCH
  echo db=wathefni
  sha256sum "\$PROD_ORCH/app.py" "\$PROD_ORCH/durable_email_ingress.py" "\$PROD_ORCH/action_registry.py" 2>/dev/null || true
} | tee "\$EV/PREDEPLOY.txt"

log "backup artifacts + db"
cp -a "\$PROD_ORCH/app.py" "\$BACKUP_ROOT/app.py"
cp -a "\$PROD_ORCH/durable_email_ingress.py" "\$BACKUP_ROOT/durable_email_ingress.py"
cp -a /etc/systemd/system/wathefni-orchestrator.service "\$BACKUP_ROOT/" || true
cp -a /etc/systemd/system/wathefni-orchestrator.service.d "\$BACKUP_ROOT/service.d.pre" || true
[[ -f "\$DROPIN_FILE" ]] && cp -a "\$DROPIN_FILE" "\$BACKUP_ROOT/unified-inbound-cv.conf" || true
[[ -f "\$FLAGS_FILE" ]] && cp -a "\$FLAGS_FILE" "\$BACKUP_ROOT/unified-inbound-cv.production.env" || true
for f in inbound_cv_intake.py inbound_cv_processing.py inbound_cv_adapters.py \
         inbound_cv_person_registry.py inbound_cv_wave4.py talent_pool_authority.py \
         job_binding_authority.py verified_job_binding_gate.py candidate_knowledge_wave4.py \
         candidate_knowledge_types.py candidate_knowledge_authority.py; do
  [[ -f "\$PROD_ORCH/\$f" ]] && cp -a "\$PROD_ORCH/\$f" "\$BACKUP_ROOT/modules/\$f" || true
done
sha256sum "\$BACKUP_ROOT/app.py" "\$BACKUP_ROOT/durable_email_ingress.py" | tee "\$EV/backup.sha256"

tmpdump=\$(mktemp /tmp/wathefni-prod-uicv-XXXX.dump)
chown postgres:postgres "\$tmpdump"
sudo -u postgres pg_dump -Fc -d wathefni -f "\$tmpdump"
mv "\$tmpdump" "\$BACKUP_ROOT/db.dump"
chmod 640 "\$BACKUP_ROOT/db.dump"
pg_restore --list "\$BACKUP_ROOT/db.dump" > "\$BACKUP_ROOT/db.restore-list"
test -s "\$BACKUP_ROOT/db.restore-list"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
psql "\$WATHEFNI_DATABASE_URL" -Atc "
SELECT 'tables=' || coalesce(string_agg(tablename, ',' ORDER BY tablename), '')
FROM pg_tables
WHERE schemaname='public'
  AND tablename = ANY(ARRAY[
    'intake_source_events','intake_subjects','intake_items','cv_versions',
    'talent_pool_entries','application_job_bindings','application_cv_bindings',
    'intake_consent_events','cv_processing_stage_runs'
  ]);
" | tee "\$EV/schema-pre.txt"

cat > "\$BACKUP_ROOT/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd "\$(dirname "\$0")" && pwd)
systemctl stop wathefni-orchestrator.service || true
cp -a "\$ROOT/app.py" /opt/wathefni/orchestrator/app.py
cp -a "\$ROOT/durable_email_ingress.py" /opt/wathefni/orchestrator/durable_email_ingress.py
for f in inbound_cv_intake.py inbound_cv_processing.py inbound_cv_adapters.py \
         inbound_cv_person_registry.py inbound_cv_wave4.py talent_pool_authority.py \
         job_binding_authority.py verified_job_binding_gate.py candidate_knowledge_wave4.py \
         candidate_knowledge_types.py candidate_knowledge_authority.py; do
  rm -f "/opt/wathefni/orchestrator/\$f"
  [[ -f "\$ROOT/modules/\$f" ]] && cp -a "\$ROOT/modules/\$f" "/opt/wathefni/orchestrator/\$f" || true
done
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/unified-inbound-cv.conf
rm -f /opt/wathefni/var/unified-inbound-cv.production.env
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 60); do
  curl -sf http://127.0.0.1:8010/health >/dev/null && break
  sleep 1
done
curl -sf http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
EOS
chmod +x "\$BACKUP_ROOT/ROLLBACK.sh"

log "install modules"
for f in inbound_cv_intake.py inbound_cv_processing.py inbound_cv_adapters.py \
         inbound_cv_person_registry.py inbound_cv_wave4.py talent_pool_authority.py \
         job_binding_authority.py verified_job_binding_gate.py candidate_knowledge_wave4.py \
         candidate_knowledge_types.py candidate_knowledge_authority.py durable_email_ingress.py; do
  cp -a "\$REMOTE_STAGE/\$f" "\$PROD_ORCH/\$f"
done
cp -a "\$REMOTE_STAGE/patch-staging-app-unified-inbound-cv-wave3.py" "\$PROD_ORCH/ops/"
cp -a "\$REMOTE_STAGE/patch-production-app-unified-inbound-cv-dark.py" "\$PROD_ORCH/ops/"
cp -a "\$REMOTE_STAGE/unified-inbound-cv-production-dark-observe.py" "\$PROD_ORCH/ops/"

log "surgical patch production app.py"
/opt/wathefni/orchestrator/.venv/bin/python "\$PROD_ORCH/ops/patch-production-app-unified-inbound-cv-dark.py" "\$PROD_ORCH/app.py" | tee "\$EV/patch-result.json"
/opt/wathefni/orchestrator/.venv/bin/python -m py_compile \
  "\$PROD_ORCH/app.py" \
  "\$PROD_ORCH/durable_email_ingress.py" \
  "\$PROD_ORCH/inbound_cv_intake.py" \
  "\$PROD_ORCH/inbound_cv_processing.py" \
  "\$PROD_ORCH/inbound_cv_adapters.py" \
  "\$PROD_ORCH/inbound_cv_wave4.py" \
  "\$PROD_ORCH/inbound_cv_person_registry.py" \
  "\$PROD_ORCH/talent_pool_authority.py" \
  "\$PROD_ORCH/job_binding_authority.py" \
  "\$PROD_ORCH/verified_job_binding_gate.py" \
  "\$PROD_ORCH/candidate_knowledge_wave4.py"

log "artifact hashes post-install"
{
  sha256sum \
    "\$PROD_ORCH/app.py" \
    "\$PROD_ORCH/durable_email_ingress.py" \
    "\$PROD_ORCH/inbound_cv_intake.py" \
    "\$PROD_ORCH/inbound_cv_processing.py" \
    "\$PROD_ORCH/inbound_cv_adapters.py" \
    "\$PROD_ORCH/inbound_cv_person_registry.py" \
    "\$PROD_ORCH/inbound_cv_wave4.py" \
    "\$PROD_ORCH/talent_pool_authority.py" \
    "\$PROD_ORCH/job_binding_authority.py" \
    "\$PROD_ORCH/verified_job_binding_gate.py" \
    "\$PROD_ORCH/candidate_knowledge_wave4.py" \
    "\$PROD_ORCH/candidate_knowledge_types.py" \
    "\$PROD_ORCH/candidate_knowledge_authority.py"
} | tee "\$EV/artifact.sha256"

log "enable production-dark flags (SHADOW only; ENFORCE unset)"
cat > "\$FLAGS_FILE" <<'EOF'
# Unified Inbound CV — WATHEFNI production-dark (shadow only)
WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on
WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE=on
WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER=on
WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS=on
WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING=on
WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on
WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE=on
WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES=on
WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS=on
WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on
# Explicitly NOT set:
# WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE
EOF
cat > "\$DROPIN_FILE" <<EOF
[Service]
EnvironmentFile=-\$FLAGS_FILE
EOF
! grep -q 'VERIFIED_JOB_BINDING_ENFORCE=on' "\$FLAGS_FILE"
cp -a "\$FLAGS_FILE" "\$EV/flags.production.env"
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service

log "wait for health"
ok=0
for i in \$(seq 1 60); do
  if curl -sf http://127.0.0.1:8010/health >/dev/null; then
    ok=1
    break
  fi
  sleep 1
done
test "\$ok" = "1"
curl -sf http://127.0.0.1:8010/health | tee "\$EV/post-restart-health.txt"

PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_' | sort | tee "\$EV/production-flags.txt"
cp -a "\$EV/production-flags.txt" /tmp/unified-inbound-cv-prod-dark-flags.txt
grep -q 'WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on' "\$EV/production-flags.txt"
grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on' "\$EV/production-flags.txt"
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/production-flags.txt"

psql "\$WATHEFNI_DATABASE_URL" -Atc "
SELECT 'tables=' || coalesce(string_agg(tablename, ',' ORDER BY tablename), '')
FROM pg_tables
WHERE schemaname='public'
  AND tablename = ANY(ARRAY[
    'intake_source_events','intake_subjects','intake_items','cv_versions',
    'talent_pool_entries','application_job_bindings','application_cv_bindings',
    'intake_consent_events','cv_processing_stage_runs'
  ]);
" | tee "\$EV/schema-post.txt"

log "kill-switch proof (temporary unset via override, then restore)"
# EnvironmentFile overrides Environment= in systemd, so rename the flags file briefly.
mv "\$FLAGS_FILE" "\$FLAGS_FILE.killed.bak"
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health >/dev/null
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'UNIFIED_INBOUND_CV_WAVE4|UNIFIED_VERIFIED_JOB_BINDING_GATE|UNIFIED_PERSON_REGISTRY|UNIFIED_TALENT_POOL_ENTRIES' | tee "\$EV/kill-switch-flags.txt" || true
# With flags file removed, Wave 4 keys must be absent (fail-closed / off).
! grep -q 'WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on' "\$EV/kill-switch-flags.txt"
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE=on' "\$EV/kill-switch-flags.txt"
mv "\$FLAGS_FILE.killed.bak" "\$FLAGS_FILE"
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health | tee "\$EV/post-kill-restore-health.txt"
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'UNIFIED_' | sort | tee "\$EV/production-flags-restored.txt"
cp -a "\$EV/production-flags-restored.txt" /tmp/unified-inbound-cv-prod-dark-flags.txt
grep -q 'WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on' "\$EV/production-flags-restored.txt"
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/production-flags-restored.txt"
echo KILL_SWITCH_OK > "\$EV/kill-switch-proof.txt"

log "bounded observation"
WAVE_PD_EVIDENCE="\$EV" WATHEFNI_ENV=production \
  /opt/wathefni/orchestrator/.venv/bin/python \
  "\$PROD_ORCH/ops/unified-inbound-cv-production-dark-observe.py" | tee "\$EV/observe.stdout.json"
test "\$(python3 -c "import json;print(json.load(open('\$EV/observation.json'))['failed'])")" = "0"

log "final health + enforce absent"
curl -sf http://127.0.0.1:8010/health | tee "\$EV/final-health.txt"
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/production-flags-restored.txt"
curl -sf http://127.0.0.1:8011/health >/dev/null || true

log "DONE production-dark PASS evidence=\$EV backup=\$BACKUP_ROOT"
trap - ERR
REMOTE

log "fetch evidence"
mkdir -p "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-production-dark"
scp -o BatchMode=yes -r \
  "$VPS:$EVIDENCE_ROOT/$STAMP/" \
  "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-production-dark/" || true
log "local evidence: ops/screenshots/unified-inbound-cv-production-dark/$STAMP"
echo "$STAMP" > "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-production-dark/LATEST_STAMP.txt"
