#!/usr/bin/env bash
# Guarded staging dark deploy for durable email ingress.
# inbound=off, workers stopped, no Postmark enablement, no production touch.
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
VPS="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=20 "$VPS")
LOCAL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH_SRC="$LOCAL_ROOT/wathefni-orchestrator"
PATCHED_APP="${PATCHED_APP:-/tmp/staging-app-durable-ingress.py}"
REMOTE_STAGE="/tmp/durable-ingress-dark-${STAMP}"
EVIDENCE_ROOT="/opt/wathefni/staging/staging-evidence/durable-email-ingress-dark"
BACKUP_ROOT="/opt/wathefni/backups/staging-pre-durable-ingress-${STAMP}"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

[[ -f "$PATCHED_APP" ]] || { echo "missing patched app: $PATCHED_APP" >&2; exit 1; }

SOURCE_COMMIT="$(cd "$LOCAL_ROOT" && git rev-parse HEAD)"
APP_SHA="$(sha256sum "$PATCHED_APP" | awk '{print $1}')"
MOD_SHA="$(
  cd "$ORCH_SRC" && sha256sum \
    durable_email_ingress.py \
    intake_quarantine_storage.py \
    intake_malware_scanner.py \
    durable-email-ingress-worker.py \
    smoke-test-inbound-email.py \
    | sha256sum | awk '{print $1}'
)"
ARTIFACT_SHA="$(printf '%s\n%s\n' "$APP_SHA" "$MOD_SHA" | sha256sum | awk '{print $1}')"

log "source_commit=$SOURCE_COMMIT"
log "app_sha=$APP_SHA"
log "modules_bundle_sha=$MOD_SHA"
log "artifact_sha=$ARTIFACT_SHA"

# Upload payload
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
scp -o BatchMode=yes \
  "$PATCHED_APP" \
  "$ORCH_SRC/durable_email_ingress.py" \
  "$ORCH_SRC/intake_quarantine_storage.py" \
  "$ORCH_SRC/intake_malware_scanner.py" \
  "$ORCH_SRC/durable-email-ingress-worker.py" \
  "$ORCH_SRC/smoke-test-inbound-email.py" \
  "$LOCAL_ROOT/ops/durable-email-ingress-staging-dark-qualify.py" \
  "$VPS:$REMOTE_STAGE/"

# Rename patched app on remote
"${SSH[@]}" "mv '$REMOTE_STAGE/$(basename "$PATCHED_APP")" '$REMOTE_STAGE/app.py'"

"${SSH[@]}" bash -s <<REMOTE
set -euo pipefail
STAMP='$STAMP'
SOURCE_COMMIT='$SOURCE_COMMIT'
APP_SHA='$APP_SHA'
MOD_SHA='$MOD_SHA'
ARTIFACT_SHA='$ARTIFACT_SHA'
REMOTE_STAGE='$REMOTE_STAGE'
EVIDENCE_ROOT='$EVIDENCE_ROOT'
BACKUP_ROOT='$BACKUP_ROOT'
STAGING_ORCH='$STAGING_ORCH'
EV="\$EVIDENCE_ROOT/\$STAMP"
mkdir -p "\$EV" "\$BACKUP_ROOT"
chmod 700 "\$EVIDENCE_ROOT" "\$EV" "\$BACKUP_ROOT"

log() { printf '%s %s\n' "\$(date -u +%Y-%m-%dT%H:%M:%SZ)" "\$*" | tee -a "\$EV/deploy.log"; }

###############################################################################
# Preflight gates
###############################################################################
log "preflight gates"
grep -E '^(WATHEFNI_INBOUND_EMAIL|WATHEFNI_SENDER_ACKNOWLEDGMENT)=' /root/.openclaw/secrets/wathefni-intake.staging.env | tee "\$EV/preflight-inbound.txt"
test "\$(grep '^WATHEFNI_INBOUND_EMAIL=' /root/.openclaw/secrets/wathefni-intake.staging.env | cut -d= -f2)" = "off"
test "\$(systemctl is-active wathefni-intake-worker-staging.service || true)" = "inactive"
test "\$(systemctl is-enabled wathefni-intake-worker-staging.service || true)" = "disabled"
findmnt -n /opt/wathefni/staging/quarantine/email-intake | tee "\$EV/preflight-mount.txt"
docker inspect -f '{{.State.Health.Status}}' wathefni-staging-clamav | tee "\$EV/preflight-clamav-health.txt"
python3 - <<'PY' | tee "\$EV/preflight-clamav-version.txt"
import socket
s=socket.create_connection(("127.0.0.1",3310),timeout=5)
s.sendall(b"zVERSION\0")
print(s.recv(256).decode().replace("\0","").strip())
s.close()
PY
test -n "\$(grep '^WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET=' /root/.openclaw/secrets/wathefni-intake.staging.env | cut -d= -f2-)"
test -n "\$(grep '^WATHEFNI_POSTMARK_INBOUND_SECRET=' /root/.openclaw/secrets/wathefni-intake.staging.env | cut -d= -f2-)"

# Redacted config
python3 - <<'PY' > "\$EV/config.redacted.env"
from pathlib import Path
secret_keys={"WATHEFNI_POSTMARK_INBOUND_SECRET","WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET"}
for line in Path("/root/.openclaw/secrets/wathefni-intake.staging.env").read_text().splitlines():
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        print(line); continue
    k,v=line.split("=",1)
    print(f"{k}=***REDACTED***" if k in secret_keys or k.endswith("_SECRET") or "TOKEN" in k else line)
PY
chmod 600 "\$EV/config.redacted.env"

###############################################################################
# Backup + quarantine backup proof
###############################################################################
log "staging database backup"
set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
pg_dump "\$WATHEFNI_DATABASE_URL" -Fc -f "\$BACKUP_ROOT/db.dump"
sha256sum "\$BACKUP_ROOT/db.dump" | tee "\$EV/db-backup.sha256"
# Code snapshot for rollback
cp -a "\$STAGING_ORCH/app.py" "\$BACKUP_ROOT/app.py.pre"
sha256sum "\$BACKUP_ROOT/app.py.pre" | tee "\$EV/app-pre.sha256"
# Snapshot any existing ingress modules if present
for f in durable_email_ingress.py intake_quarantine_storage.py intake_malware_scanner.py durable-email-ingress-worker.py smoke-test-inbound-email.py; do
  if [[ -f "\$STAGING_ORCH/\$f" ]]; then
    cp -a "\$STAGING_ORCH/\$f" "\$BACKUP_ROOT/\$f.pre"
  fi
done
# Quarantine backup
QBACKUP=\$(/usr/local/bin/backup-wathefni-staging-email-quarantine)
echo "\$QBACKUP" | tee "\$EV/quarantine-backup-run.txt"
sha256sum "\$QBACKUP/quarantine.tar.zst" | tee "\$EV/quarantine-backup.sha256"
RESTORE_TMP=\$(mktemp -d /tmp/q-restore-dark.XXXXXX)
tar --zstd -xf "\$QBACKUP/quarantine.tar.zst" -C "\$RESTORE_TMP"
python3 - <<PY | tee "\$EV/quarantine-restore-proof.json"
import hashlib, json
from pathlib import Path
live=Path("/opt/wathefni/staging/quarantine/email-intake")
rest=Path("$RESTORE_TMP")
files=list(live.rglob("*.bin"))[:5]
matched=0
for f in files:
    other=rest/f.relative_to(live)
    if other.is_file() and hashlib.sha256(f.read_bytes()).digest()==hashlib.sha256(other.read_bytes()).digest():
        matched+=1
print(json.dumps({"compared": len(files), "matched": matched, "backup": "$QBACKUP"}))
PY
rm -rf "\$RESTORE_TMP"

cat > "\$BACKUP_ROOT/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_ROOT="$(cd "$(dirname "$0")" && pwd)"
STAGING_ORCH=/opt/wathefni/staging/orchestrator
cp -a "$BACKUP_ROOT/app.py.pre" "$STAGING_ORCH/app.py"
for f in durable_email_ingress.py intake_quarantine_storage.py intake_malware_scanner.py durable-email-ingress-worker.py smoke-test-inbound-email.py; do
  if [[ -f "$BACKUP_ROOT/$f.pre" ]]; then
    cp -a "$BACKUP_ROOT/$f.pre" "$STAGING_ORCH/$f"
  else
    rm -f "$STAGING_ORCH/$f"
  fi
done
rm -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/durable-email-ingress.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
sleep 2
curl -fsS -o /dev/null -w "health:%{http_code}\n" http://127.0.0.1:8011/health
echo "ROLLBACK complete. Additive intake_* tables are preserved."
EOS
chmod 755 "\$BACKUP_ROOT/ROLLBACK.sh"

printf '%s\n' "\$SOURCE_COMMIT" "\$APP_SHA" "\$MOD_SHA" "\$ARTIFACT_SHA" > "\$EV/source-artifact.txt"
{
  echo "source_commit=\$SOURCE_COMMIT"
  echo "app_sha=\$APP_SHA"
  echo "modules_bundle_sha=\$MOD_SHA"
  echo "artifact_sha=\$ARTIFACT_SHA"
  echo "backup_root=\$BACKUP_ROOT"
} | tee "\$EV/artifact-manifest.txt"

###############################################################################
# Additive schema while old code still running
###############################################################################
log "copy modules for pre-schema"
cp -a "\$REMOTE_STAGE/durable_email_ingress.py" "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE/intake_quarantine_storage.py" "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE/intake_malware_scanner.py" "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE/durable-email-ingress-worker.py" "\$STAGING_ORCH/"
# Do NOT install app.py yet
set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
set -a; source /root/.openclaw/secrets/wathefni-intake.staging.env; set +a
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY' | tee "\$EV/migration-pre-schema.json"
import json, os, psycopg2
from psycopg2.extras import RealDictCursor
import durable_email_ingress as dei
url=os.environ["WATHEFNI_DATABASE_URL"]
with psycopg2.connect(url, cursor_factory=RealDictCursor) as conn:
    with conn.cursor() as cur:
        dei.ensure_schema(cur)
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("""
          SELECT table_name FROM information_schema.tables
          WHERE table_schema='public' AND table_name LIKE 'intake_%'
          ORDER BY 1
        """)
        tables=[r["table_name"] for r in cur.fetchall()]
print(json.dumps({"ok": True, "tables": tables, "old_code_still_running": True}))
PY
curl -fsS -o /dev/null -w "health_after_pre_schema:%{http_code}\n" http://127.0.0.1:8011/health | tee -a "\$EV/deploy.log"
# Prove no intake work created by migration alone
set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
psql "\$WATHEFNI_DATABASE_URL" -At <<'SQL' | tee "\$EV/post-migration-counts.txt"
SELECT 'intake_submissions='||count(*) FROM intake_submissions;
SELECT 'intake_documents='||count(*) FROM intake_documents;
SELECT 'intake_processing_jobs='||count(*) FROM intake_processing_jobs;
SELECT 'inbound_with_submission='||count(*) FROM inbound_messages WHERE submission_id IS NOT NULL;
SQL

###############################################################################
# Deploy app + smoke update + EnvironmentFile drop-in (inbound off)
###############################################################################
log "deploy patched app.py"
cp -a "\$REMOTE_STAGE/app.py" "\$STAGING_ORCH/app.py"
cp -a "\$REMOTE_STAGE/smoke-test-inbound-email.py" "\$STAGING_ORCH/smoke-test-inbound-email.py"
cp -a "\$REMOTE_STAGE/durable-email-ingress-staging-dark-qualify.py" "\$STAGING_ORCH/ops/" 2>/dev/null || mkdir -p "\$STAGING_ORCH/ops" && cp -a "\$REMOTE_STAGE/durable-email-ingress-staging-dark-qualify.py" "\$STAGING_ORCH/ops/"
sha256sum "\$STAGING_ORCH/app.py" "\$STAGING_ORCH/durable_email_ingress.py" "\$STAGING_ORCH/intake_quarantine_storage.py" "\$STAGING_ORCH/intake_malware_scanner.py" "\$STAGING_ORCH/durable-email-ingress-worker.py" | tee "\$EV/deployed-files.sha256"

mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/durable-email-ingress.conf <<'EOF'
[Service]
# Durable email ingress staging config. INBOUND MUST remain off.
EnvironmentFile=-/root/.openclaw/secrets/wathefni-intake.staging.env
EOF
systemctl daemon-reload
# Ensure workers stay stopped
systemctl disable --now wathefni-intake-worker-staging.service >/dev/null 2>&1 || true
systemctl stop wathefni-intake-worker-staging.service >/dev/null 2>&1 || true
systemctl restart wathefni-orchestrator-staging.service
sleep 3
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=\$(curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/health || echo 000)
  [[ "\$code" == "200" ]] && break
  sleep 2
done
echo "health=\$code" | tee "\$EV/post-deploy-health.txt"
[[ "\$code" == "200" ]]

# Confirm env loaded and inbound off via readiness (needs internal token)
TOK=\$(grep '^WATHEFNI_INTERNAL_TOKEN=' /root/.openclaw/secrets/postgres.staging.env | head -1 | cut -d= -f2-)
curl -fsS -H "Authorization: Bearer \$TOK" \
  "http://127.0.0.1:8011/orchestrator/debug/intake-readiness?run_safe_scans=true" \
  | tee "\$EV/intake-readiness.json"
python3 - <<'PY'
import json
from pathlib import Path
p=Path("$EV/intake-readiness.json")
# path expansion happens in shell - use env
PY
python3 -c "
import json
from pathlib import Path
d=json.loads(Path('\$EV/intake-readiness.json').read_text())
assert d.get('inbound_enabled') is False, d
assert d.get('storage',{}).get('writable') or d.get('storage',{}).get('fsync_ok'), d
assert d.get('scanner',{}).get('ok') is True, d
assert d.get('safe_scans',{}).get('clean_ok') is True, d
assert d.get('safe_scans',{}).get('eicar_detected') is True, d
assert d.get('signing_secret_configured') is True, d
print('readiness_assertions_ok')
" | tee -a "\$EV/deploy.log"

# Webhook disabled proof (no Postmark call): unauthorized/disabled paths
# Without secret match -> 401; with secret but inbound off -> 503
SECRET=\$(grep '^WATHEFNI_POSTMARK_INBOUND_SECRET=' /root/.openclaw/secrets/wathefni-intake.staging.env | cut -d= -f2-)
c1=\$(curl -s -o /tmp/inbound_body1.json -w '%{http_code}' -X POST http://127.0.0.1:8011/webhook/postmark/inbound -H 'Content-Type: application/json' -d '{}')
c2=\$(curl -s -o /tmp/inbound_body2.json -w '%{http_code}' -X POST "http://127.0.0.1:8011/webhook/postmark/inbound?token=\$SECRET" -H 'Content-Type: application/json' -d '{}')
{
  echo "no_auth=\$c1 body=\$(cat /tmp/inbound_body1.json)"
  echo "auth_inbound_off=\$c2 body=\$(cat /tmp/inbound_body2.json)"
} | tee "\$EV/webhook-disabled-proof.txt"
[[ "\$c1" == "401" || "\$c1" == "503" ]]
[[ "\$c2" == "503" ]]

echo "worker=\$(systemctl is-active wathefni-intake-worker-staging.service || true)" | tee "\$EV/worker-gate.txt"
echo "worker_enabled=\$(systemctl is-enabled wathefni-intake-worker-staging.service || true)" | tee -a "\$EV/worker-gate.txt"

###############################################################################
# Dark qualify (synthetic queue + adapters)
###############################################################################
log "dark qualify"
set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
set -a; source /root/.openclaw/secrets/wathefni-intake.staging.env; set +a
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_ENV=staging
cd "\$STAGING_ORCH"
/opt/wathefni/orchestrator/.venv/bin/python ops/durable-email-ingress-staging-dark-qualify.py | tee "\$EV/dark-qualify.json"
python3 -c "
import json,sys
from pathlib import Path
# file may be pretty json with trailing logs — find last JSON object start
text=Path('\$EV/dark-qualify.json').read_text()
# script prints only JSON
d=json.loads(text)
assert d['failed']==0, d
print('dark_qualify_ok', d['passed'])
"

ln -sfn "\$EV" "\$EVIDENCE_ROOT/latest"
echo "\$ARTIFACT_SHA" > /opt/wathefni/staging/durable-email-ingress-dark-artifact.sha256
log "DEPLOY_PHASE_COMPLETE evidence=\$EV"
REMOTE
