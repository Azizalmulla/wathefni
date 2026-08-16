#!/usr/bin/env bash
# Narrow audited legacy Job-binding backfill for WATHEFNI (exact 11 apps).
# ENFORCE stays OFF. No channel cutover.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS")
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_SCRIPT="/tmp/unified-inbound-cv-legacy-binding-backfill.py"
EVIDENCE_ROOT="/opt/wathefni/production-evidence/unified-inbound-cv-legacy-binding-backfill"
BACKUP_ROOT="/opt/wathefni/backups/production-pre-legacy-binding-backfill-${STAMP}"
FLAGS_FILE="/opt/wathefni/var/unified-inbound-cv.production.env"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "preflight"
"${SSH[@]}" "set -euo pipefail
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  db=\$(psql \"\$WATHEFNI_DATABASE_URL\" -Atc 'SELECT current_database()')
  test \"\$db\" = 'wathefni'
  PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
  if tr '\\0' '\\n' < /proc/\$PID/environ | grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on'; then
    echo REFUSING_ENFORCE_ON; exit 2
  fi
  echo PREFLIGHT_OK
"

log "upload backfill script"
scp -o BatchMode=yes \
  "$LOCAL_ROOT/ops/unified-inbound-cv-legacy-binding-backfill.py" \
  "$VPS:$REMOTE_SCRIPT"

log "backup + execute on host"
"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
STAMP='$STAMP'
EVIDENCE_ROOT='$EVIDENCE_ROOT'
BACKUP_ROOT='$BACKUP_ROOT'
FLAGS_FILE='$FLAGS_FILE'
REMOTE_SCRIPT='$REMOTE_SCRIPT'
EV="\$EVIDENCE_ROOT/\$STAMP"
mkdir -p "\$EV" "\$BACKUP_ROOT"
chmod 700 "\$EVIDENCE_ROOT" "\$EV" "\$BACKUP_ROOT"

log() { printf '%s %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\$*" | tee -a "\$EV/deploy.log"; }

log "health + flags snapshot"
curl -sf http://127.0.0.1:8010/health | tee "\$EV/pre-health.txt"
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_' | sort | tee "\$EV/production-flags-pre.txt"
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/production-flags-pre.txt"
grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on' "\$EV/production-flags-pre.txt"

log "db snapshot of bindings"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
psql "\$WATHEFNI_DATABASE_URL" -c "
SELECT count(*) AS verified_bindings FROM application_job_bindings WHERE company_code='WATHEFNI' AND verified;
SELECT count(*) AS applications FROM applications WHERE company_code='WATHEFNI';
" | tee "\$EV/db-before.txt"
tmpdump=\$(mktemp /tmp/bindings-XXXXXX.dump)
chown postgres:postgres "\$tmpdump"
sudo -u postgres pg_dump -Fc -d wathefni \
  -t application_job_bindings -t application_cv_bindings -t intake_consent_events \
  -f "\$tmpdump"
mv "\$tmpdump" "\$BACKUP_ROOT/bindings.dump"
chmod 640 "\$BACKUP_ROOT/bindings.dump" || true
ls -la "\$BACKUP_ROOT/bindings.dump" | tee "\$EV/bindings-dump-ls.txt"

cat > "\$BACKUP_ROOT/ROLLBACK_BACKFILL.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
# Deletes only legacy_backfill bindings for the audited allowlist.
set -a; source /root/.openclaw/secrets/postgres.env; set +a
psql "\$WATHEFNI_DATABASE_URL" <<'SQL'
BEGIN;
DELETE FROM application_cv_bindings b
USING application_job_bindings j
WHERE b.company_code=j.company_code AND b.app_key=j.app_key
  AND j.company_code='WATHEFNI'
  AND COALESCE(j.provenance->>'legacy_backfill','')='true'
  AND j.app_key IN (
    '96597727743-WATHEFNI-FULLSTACK_DEVELOPER',
    '96599338566-WATHEFNI-FULLSTACK_DEVELOPER',
    '96597727743-WATHEFNI-MARKETING_SPECIALIST',
    '96550252254-WATHEFNI-SOCIAL_MEDIA_MANAGER',
    '96599652277-WATHEFNI-SOCIAL_MEDIA_MANAGER',
    '96597485758-WATHEFNI-HR',
    '96598900677-WATHEFNI-ACCOUNTING',
    '96598900677-WATHEFNI-FINANCE',
    '96598900677-WATHEFNI-HR',
    '96566363363-WATHEFNI-IT_MAINTENANCE',
    '96597485758-WATHEFNI-ACCOUNTING_EXCEL'
  );
DELETE FROM application_job_bindings
WHERE company_code='WATHEFNI'
  AND COALESCE(provenance->>'legacy_backfill','')='true'
  AND app_key IN (
    '96597727743-WATHEFNI-FULLSTACK_DEVELOPER',
    '96599338566-WATHEFNI-FULLSTACK_DEVELOPER',
    '96597727743-WATHEFNI-MARKETING_SPECIALIST',
    '96550252254-WATHEFNI-SOCIAL_MEDIA_MANAGER',
    '96599652277-WATHEFNI-SOCIAL_MEDIA_MANAGER',
    '96597485758-WATHEFNI-HR',
    '96598900677-WATHEFNI-ACCOUNTING',
    '96598900677-WATHEFNI-FINANCE',
    '96598900677-WATHEFNI-HR',
    '96566363363-WATHEFNI-IT_MAINTENANCE',
    '96597485758-WATHEFNI-ACCOUNTING_EXCEL'
  );
DELETE FROM intake_consent_events
WHERE company_code='WATHEFNI'
  AND consent_kind='legacy_backfill'
  AND COALESCE(evidence->>'app_key','') IN (
    '96597727743-WATHEFNI-FULLSTACK_DEVELOPER',
    '96599338566-WATHEFNI-FULLSTACK_DEVELOPER',
    '96597727743-WATHEFNI-MARKETING_SPECIALIST',
    '96550252254-WATHEFNI-SOCIAL_MEDIA_MANAGER',
    '96599652277-WATHEFNI-SOCIAL_MEDIA_MANAGER',
    '96597485758-WATHEFNI-HR',
    '96598900677-WATHEFNI-ACCOUNTING',
    '96598900677-WATHEFNI-FINANCE',
    '96598900677-WATHEFNI-HR',
    '96566363363-WATHEFNI-IT_MAINTENANCE',
    '96597485758-WATHEFNI-ACCOUNTING_EXCEL'
  );
COMMIT;
SQL
echo ROLLBACK_BACKFILL_OK
EOS
chmod +x "\$BACKUP_ROOT/ROLLBACK_BACKFILL.sh"

log "run audited backfill (includes in-process rollback proof + re-apply)"
LEGACY_BACKFILL_OUT="\$EV" \
  /opt/wathefni/orchestrator/.venv/bin/python "\$REMOTE_SCRIPT" full \
  | tee "\$EV/backfill.stdout.json"
python3 -c "import json; d=json.load(open('\$EV/backfill.json')); assert d.get('ok') is True, d; print('ASSERTIONS', d.get('assertions'))"

log "kill-switch proof (rename flags file; restore)"
mv "\$FLAGS_FILE" "\$FLAGS_FILE.killed.bak"
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health >/dev/null
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_INBOUND_CV_WAVE4|UNIFIED_VERIFIED_JOB_BINDING' | tee "\$EV/kill-switch-flags.txt" || true
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE=on' "\$EV/kill-switch-flags.txt"
mv "\$FLAGS_FILE.killed.bak" "\$FLAGS_FILE"
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health | tee "\$EV/post-kill-restore-health.txt"
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_' | sort | tee "\$EV/production-flags-restored.txt"
grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on' "\$EV/production-flags-restored.txt"
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/production-flags-restored.txt"
echo KILL_SWITCH_OK > "\$EV/kill-switch-proof.txt"

log "final health + binding counts"
curl -sf http://127.0.0.1:8010/health | tee "\$EV/final-health.txt"
psql "\$WATHEFNI_DATABASE_URL" -c "
SELECT count(*) AS verified_bindings FROM application_job_bindings WHERE company_code='WATHEFNI' AND verified;
SELECT app_key, position_code, provenance->>'legacy_backfill' AS legacy
FROM application_job_bindings WHERE company_code='WATHEFNI' AND verified ORDER BY app_key;
SELECT count(*) AS applications FROM applications WHERE company_code='WATHEFNI';
" | tee "\$EV/db-after.txt"

log "DONE backfill PASS evidence=\$EV"
REMOTE

log "fetch evidence"
mkdir -p "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-legacy-binding-backfill"
scp -o BatchMode=yes -r \
  "$VPS:$EVIDENCE_ROOT/$STAMP/" \
  "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-legacy-binding-backfill/"
echo "$STAMP" > "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-legacy-binding-backfill/LATEST_STAMP.txt"
log "local evidence ops/screenshots/unified-inbound-cv-legacy-binding-backfill/$STAMP"
