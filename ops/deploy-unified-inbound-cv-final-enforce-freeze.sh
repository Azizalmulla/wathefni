#!/usr/bin/env bash
# Final unified-intake freeze + WATHEFNI verified-binding ENFORCE canary.
# External tenants / Role Profiles stay OFF. No post-hiring / mobile work.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS")
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$LOCAL_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_STAGE="/tmp/unified-inbound-cv-final-enforce-freeze-${STAMP}"
BACKUP_ROOT="/opt/wathefni/backups/production-pre-final-enforce-freeze-${STAMP}"
EVIDENCE_ROOT="/opt/wathefni/production-evidence/unified-inbound-cv-final-enforce-freeze"
PROD_ORCH="/opt/wathefni/orchestrator"
FLAGS_FILE="/opt/wathefni/var/unified-inbound-cv.production.env"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "preflight"
"${SSH[@]}" "set -euo pipefail
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  db=\$(psql \"\$WATHEFNI_DATABASE_URL\" -Atc 'SELECT current_database()')
  test \"\$db\" = 'wathefni'
  echo PREFLIGHT_OK
"

log "upload artifacts"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
scp -o BatchMode=yes \
  "$ORCH_SRC/verified_job_binding_gate.py" \
  "$ORCH_SRC/jobs_phase2_stage_b.py" \
  "$LOCAL_ROOT/ops/patch-production-app-unified-inbound-cv-enforce-freeze.py" \
  "$LOCAL_ROOT/ops/unified-inbound-cv-final-enforce-freeze-canary.py" \
  "$VPS:$REMOTE_STAGE/"

log "backup + install + enable ENFORCE(WATHEFNI) + canary + kill/rollback/restore"
"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
STAMP='$STAMP'
REMOTE_STAGE='$REMOTE_STAGE'
BACKUP_ROOT='$BACKUP_ROOT'
EVIDENCE_ROOT='$EVIDENCE_ROOT'
PROD_ORCH='$PROD_ORCH'
FLAGS_FILE='$FLAGS_FILE'
EV="\$EVIDENCE_ROOT/\$STAMP"
mkdir -p "\$EV" "\$BACKUP_ROOT"
chmod 700 "\$EVIDENCE_ROOT" "\$EV" "\$BACKUP_ROOT"

log() { printf '%s %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\$*" | tee -a "\$EV/deploy.log"; }

log "backup"
cp -a "\$PROD_ORCH/app.py" "\$BACKUP_ROOT/app.py"
cp -a "\$PROD_ORCH/verified_job_binding_gate.py" "\$BACKUP_ROOT/verified_job_binding_gate.py"
cp -a "\$PROD_ORCH/jobs_phase2_stage_b.py" "\$BACKUP_ROOT/jobs_phase2_stage_b.py"
cp -a "\$FLAGS_FILE" "\$BACKUP_ROOT/unified-inbound-cv.production.env"
sha256sum "\$BACKUP_ROOT/app.py" "\$BACKUP_ROOT/verified_job_binding_gate.py" "\$BACKUP_ROOT/jobs_phase2_stage_b.py" | tee "\$EV/backup.sha256"

cat > "\$BACKUP_ROOT/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd "\$(dirname "\$0")" && pwd)
systemctl stop wathefni-orchestrator.service || true
cp -a "\$ROOT/app.py" /opt/wathefni/orchestrator/app.py
cp -a "\$ROOT/verified_job_binding_gate.py" /opt/wathefni/orchestrator/verified_job_binding_gate.py
cp -a "\$ROOT/jobs_phase2_stage_b.py" /opt/wathefni/orchestrator/jobs_phase2_stage_b.py
cp -a "\$ROOT/unified-inbound-cv.production.env" /opt/wathefni/var/unified-inbound-cv.production.env
systemctl daemon-reload
systemctl start wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
EOS
chmod +x "\$BACKUP_ROOT/ROLLBACK.sh"

log "install modules + ranking cursor patch"
cp -a "\$REMOTE_STAGE/verified_job_binding_gate.py" "\$PROD_ORCH/verified_job_binding_gate.py"
cp -a "\$REMOTE_STAGE/jobs_phase2_stage_b.py" "\$PROD_ORCH/jobs_phase2_stage_b.py"
/opt/wathefni/orchestrator/.venv/bin/python "\$REMOTE_STAGE/patch-production-app-unified-inbound-cv-enforce-freeze.py" "\$PROD_ORCH/app.py" | tee "\$EV/patch.json"
python3 -c "import json; d=json.load(open('\$EV/patch.json')); assert d.get('ok') is True, d"

log "freeze posture + enable ENFORCE for WATHEFNI only"
cat > "\$FLAGS_FILE" <<'EOF'
# Unified Inbound CV — FINAL FREEZE (WATHEFNI)
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
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on
WATHEFNI_UNIFIED_INTAKE_DURABLE_ROOT=/opt/wathefni/var/intake-durable
EOF

systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health | tee "\$EV/post-restart-health.txt"
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_|INTAKE_AUTHORITY|ENFORCE' | sort | tee "\$EV/production-flags-live.txt"
grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/production-flags-live.txt"
grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS=WATHEFNI' "\$EV/production-flags-live.txt"
grep -q 'WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on' "\$EV/production-flags-live.txt"

log "run final canary"
export CUTOVER_EVIDENCE="\$EV"
/opt/wathefni/orchestrator/.venv/bin/python "\$REMOTE_STAGE/unified-inbound-cv-final-enforce-freeze-canary.py" | tee "\$EV/canary.stdout.json"
python3 -c "import json; d=json.load(open('\$EV/canary.json')); assert d.get('ok') is True, d.get('assertions'); print('CANARY_OK', d['passed'])"

log "kill-switch proof (rename flags)"
mv "\$FLAGS_FILE" "\$FLAGS_FILE.killed.bak"
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'ENFORCE|INTAKE_AUTHORITY_EMAIL' | tee "\$EV/kill-switch-flags.txt" || true
! grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/kill-switch-flags.txt"
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY' | tee "\$EV/kill-switch-skip.json"
import json, sys
sys.path.insert(0, "/opt/wathefni/orchestrator")
import verified_job_binding_gate as g
assert not g.enforce_flag_on()
assert not g.enforce_enabled(company_code="WATHEFNI")
print(json.dumps({"ok": True, "enforce": False}))
PY
mv "\$FLAGS_FILE.killed.bak" "\$FLAGS_FILE"
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health | tee "\$EV/post-kill-restore-health.txt"
echo KILL_SWITCH_OK > "\$EV/kill-switch-proof.txt"

log "rollback proof then re-apply FINAL freeze posture (ENFORCE stays ON for WATHEFNI)"
bash "\$BACKUP_ROOT/ROLLBACK.sh" | tee "\$EV/rollback-run.txt"
curl -sf http://127.0.0.1:8010/health >/dev/null
cp -a "\$REMOTE_STAGE/verified_job_binding_gate.py" "\$PROD_ORCH/verified_job_binding_gate.py"
cp -a "\$REMOTE_STAGE/jobs_phase2_stage_b.py" "\$PROD_ORCH/jobs_phase2_stage_b.py"
cp -a "\$BACKUP_ROOT/app.py" "\$PROD_ORCH/app.py"
/opt/wathefni/orchestrator/.venv/bin/python "\$REMOTE_STAGE/patch-production-app-unified-inbound-cv-enforce-freeze.py" "\$PROD_ORCH/app.py" | tee "\$EV/patch-reapply.json"
cat > "\$FLAGS_FILE" <<'EOF'
# Unified Inbound CV — FINAL FREEZE (WATHEFNI)
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
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on
WATHEFNI_UNIFIED_INTAKE_DURABLE_ROOT=/opt/wathefni/var/intake-durable
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
curl -sf http://127.0.0.1:8010/health | tee "\$EV/final-health.txt"
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator.service)
tr '\\0' '\\n' < /proc/\$PID/environ | grep -E 'UNIFIED_|INTAKE_AUTHORITY|ENFORCE' | sort | tee "\$EV/final-flags-live.txt"
grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on' "\$EV/final-flags-live.txt"
grep -q 'WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS=WATHEFNI' "\$EV/final-flags-live.txt"
echo ROLLBACK_PROOF_AND_FINAL_FREEZE_OK > "\$EV/rollback-proof.txt"
echo FINAL_FREEZE_ENFORCE_WATHEFNI_ON > "\$EV/freeze-posture.txt"
log "DONE evidence=\$EV backup=\$BACKUP_ROOT"
REMOTE

log "fetch evidence"
mkdir -p "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-final-enforce-freeze"
scp -o BatchMode=yes -r \
  "$VPS:$EVIDENCE_ROOT/$STAMP/" \
  "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-final-enforce-freeze/"
echo "$STAMP" > "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-final-enforce-freeze/LATEST_STAMP.txt"
log "local evidence ops/screenshots/unified-inbound-cv-final-enforce-freeze/$STAMP"
