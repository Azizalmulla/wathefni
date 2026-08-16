#!/usr/bin/env bash
# Controlled forward dual-write canary (WATHEFNI). ENFORCE stays OFF. No channel cutover.
set -euo pipefail

VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS")
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_SCRIPT="/tmp/unified-inbound-cv-forward-dual-write-canary.py"
EVIDENCE_ROOT="/opt/wathefni/production-evidence/unified-inbound-cv-forward-dual-write-canary"

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

log "upload canary script"
scp -o BatchMode=yes \
  "$LOCAL_ROOT/ops/unified-inbound-cv-forward-dual-write-canary.py" \
  "$VPS:$REMOTE_SCRIPT"

log "execute canary"
"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
STAMP='$STAMP'
EVIDENCE_ROOT='$EVIDENCE_ROOT'
REMOTE_SCRIPT='$REMOTE_SCRIPT'
EV="\$EVIDENCE_ROOT/\$STAMP"
mkdir -p "\$EV"
chmod 700 "\$EVIDENCE_ROOT" "\$EV"
export FWD_CANARY_EVIDENCE="\$EV"
/opt/wathefni/orchestrator/.venv/bin/python "\$REMOTE_SCRIPT" | tee "\$EV/canary.stdout.json"
python3 -c "import json; d=json.load(open('\$EV/canary.json')); assert d.get('ok') is True, d.get('assertions'); print('CANARY_OK', d.get('passed'), '/', d.get('passed')+d.get('failed'))"
curl -sf http://127.0.0.1:8010/health | tee "\$EV/final-health.txt"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
psql "\$WATHEFNI_DATABASE_URL" -c "
SELECT count(*) AS apps FROM applications WHERE company_code='WATHEFNI';
SELECT app_key, position_code, data_source_detail FROM applications
 WHERE data_source_detail LIKE '%forward_dual_write_canary%' ORDER BY app_key;
SELECT count(*) AS verified_bindings FROM application_job_bindings WHERE company_code='WATHEFNI' AND verified;
" | tee "\$EV/db-after.txt"
echo DONE "\$EV"
REMOTE

log "fetch evidence"
mkdir -p "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-forward-dual-write-canary"
scp -o BatchMode=yes -r \
  "$VPS:$EVIDENCE_ROOT/$STAMP/" \
  "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-forward-dual-write-canary/"
echo "$STAMP" > "$LOCAL_ROOT/ops/screenshots/unified-inbound-cv-forward-dual-write-canary/LATEST_STAMP.txt"
log "local evidence ops/screenshots/unified-inbound-cv-forward-dual-write-canary/$STAMP"
