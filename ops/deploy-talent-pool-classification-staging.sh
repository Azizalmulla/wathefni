#!/usr/bin/env bash
# Contained STAGING deploy for Talent Pool Classification.
# Does NOT touch production. Workers OFF. External tenants OFF.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_STAGE="/tmp/talent-pool-classification-staging-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/staging/staging-evidence/talent-pool-classification/$STAMP"
REMOTE_BACKUP="/opt/wathefni/backups/staging-pre-talent-pool-classification-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"

ALLOWLIST=(
  talent_pool_classification.py
  talent_pool_classification_routes.py
  talent_pool_taxonomy_v1.json
  test_talent_pool_classification.py
  local-qualify-talent-pool-classification.py
  ops/patch-staging-app-talent-pool-classification.py
)

log() { printf '\n=== %s ===\n' "$*"; }

mkdir -p "$LOCAL_STAGE"
log "source commit + artifact SHA"
COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
{
  ( cd "$ORCH_SRC" && shasum -a 256 \
      talent_pool_classification.py \
      talent_pool_classification_routes.py \
      talent_pool_taxonomy_v1.json \
      test_talent_pool_classification.py \
      local-qualify-talent-pool-classification.py \
      ops/patch-staging-app-talent-pool-classification.py )
} | tee "$LOCAL_STAGE/allowlist.sha256"
ARTIFACT_SHA="$(shasum -a 256 "$LOCAL_STAGE/allowlist.sha256" | awk '{print $1}')"
echo "$COMMIT" > "$LOCAL_STAGE/source.commit"
echo "$ARTIFACT_SHA" > "$LOCAL_STAGE/artifact.sha256"
printf 'commit=%s\nartifact=%s\n' "$COMMIT" "$ARTIFACT_SHA"

log "local unit gate"
( cd "$ORCH_SRC" && python3 -m unittest test_talent_pool_classification.py -q )
( cd "$ORCH_SRC" && python3 local-qualify-talent-pool-classification.py | tee "$LOCAL_STAGE/local-qualify.log" | tail -5 )

log "patch staging app.py surgically"
scp -o BatchMode=yes "$VPS_HOST:$STAGING_ORCH/app.py" "$LOCAL_STAGE/app.py.pre"
python3 "$ORCH_SRC/ops/patch-staging-app-talent-pool-classification.py" \
  "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched"
grep -q TALENT_POOL_CLASSIFICATION_STAGING_PATCH "$LOCAL_STAGE/app.py.patched"
shasum -a 256 "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched" | tee "$LOCAL_STAGE/app.py.sha256"

log "remote backup"
"${SSH[@]}" "set -e
  mkdir -p '$REMOTE_BACKUP' '$REMOTE_EVIDENCE'
  cp -a $STAGING_ORCH/app.py '$REMOTE_BACKUP/app.py.pre'
  # preserve unified-candidates drop-in
  cp -a /etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf '$REMOTE_BACKUP/' 2>/dev/null || true
  tmpdump=\$(mktemp /tmp/wathefni-staging-tpc-XXXX.dump)
  chown postgres:postgres \"\$tmpdump\"
  sudo -u postgres pg_dump -Fc -d wathefni_staging -f \"\$tmpdump\"
  mv \"\$tmpdump\" '$REMOTE_BACKUP/db.dump'
  chmod 640 '$REMOTE_BACKUP/db.dump'
  sha256sum '$REMOTE_BACKUP/db.dump' '$REMOTE_BACKUP/app.py.pre' > '$REMOTE_BACKUP/SHA256SUMS'
  cat > '$REMOTE_BACKUP/ROLLBACK.sh' <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd \"\$(dirname \"\$0\")\" && pwd)
systemctl stop wathefni-orchestrator-staging.service || true
cp -a \"\$ROOT/app.py.pre\" /opt/wathefni/staging/orchestrator/app.py
rm -f /opt/wathefni/staging/orchestrator/talent_pool_classification.py \
      /opt/wathefni/staging/orchestrator/talent_pool_classification_routes.py \
      /opt/wathefni/staging/orchestrator/talent_pool_taxonomy_v1.json \
      /opt/wathefni/staging/orchestrator/test_talent_pool_classification.py \
      /opt/wathefni/staging/orchestrator/local-qualify-talent-pool-classification.py
rm -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
curl -sf http://127.0.0.1:8011/health
EOS
  chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'
  echo BACKUP_OK
"

log "upload modules + dark flags (master OFF, workers OFF, tenants empty, UI OFF)"
scp -o BatchMode=yes \
  "$ORCH_SRC/talent_pool_classification.py" \
  "$ORCH_SRC/talent_pool_classification_routes.py" \
  "$ORCH_SRC/talent_pool_taxonomy_v1.json" \
  "$ORCH_SRC/test_talent_pool_classification.py" \
  "$ORCH_SRC/local-qualify-talent-pool-classification.py" \
  "$LOCAL_STAGE/app.py.patched" \
  "$LOCAL_STAGE/allowlist.sha256" \
  "$LOCAL_STAGE/artifact.sha256" \
  "$LOCAL_STAGE/source.commit" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"

"${SSH[@]}" "set -e
  cp '$REMOTE_EVIDENCE/talent_pool_classification.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/talent_pool_classification_routes.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/talent_pool_taxonomy_v1.json' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/test_talent_pool_classification.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/local-qualify-talent-pool-classification.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/app.py.patched' $STAGING_ORCH/app.py
  mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
  # Keep Unified Candidates drop-in untouched; add independent classification drop-in
  cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf <<'EOF'
[Service]
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION=off
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA=on
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL=off
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_UI=off
EOF
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator-staging.service
  for i in \$(seq 1 60); do curl -sf http://127.0.0.1:8011/health >/dev/null && break; sleep 1; done
  curl -sf http://127.0.0.1:8011/health >/dev/null
  # Apply additive schema while dark
  /opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
import os, pathlib
os.environ['WATHEFNI_ENV']='staging'
os.environ['WATHEFNI_POSTGRES_ENV']='/root/.openclaw/secrets/postgres.staging.env'
os.environ['WATHEFNI_WORKSPACE']='/opt/wathefni/staging/workspace'
os.environ['WATHEFNI_EXPECTED_DATABASE_HOST']='127.0.0.1'
os.environ['WATHEFNI_EXPECTED_DATABASE_PORT']='5432'
os.environ['WATHEFNI_EXPECTED_DATABASE_NAME']='wathefni_staging'
os.environ['WATHEFNI_DATABASE_ENVIRONMENT_MARKER']='wathefni-staging-hr2-isolation-v1'
import sys
sys.path.insert(0,'/opt/wathefni/staging/orchestrator')
import talent_pool_classification as tpc
vals={}
for line in pathlib.Path('/root/.openclaw/secrets/postgres.staging.env').read_text().splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1); vals[k.strip()]=v.strip().strip('\"')
import psycopg2
from psycopg2.extras import RealDictCursor
with psycopg2.connect(vals['WATHEFNI_DATABASE_URL'], cursor_factory=RealDictCursor) as conn:
    with conn.cursor() as cur:
        tpc.ensure_classification_schema(cur)
        ver=tpc.seed_global_taxonomy(cur)
        conn.commit()
print('SCHEMA_OK', ver)
PY
  # Confirm production untouched
  test ! -f /opt/wathefni/orchestrator/talent_pool_classification.py
  echo DARK_DEPLOY_OK evidence=$REMOTE_EVIDENCE backup=$REMOTE_BACKUP
"

printf '%s\n' "$REMOTE_EVIDENCE" > /tmp/tpc-staging-evidence.path
printf '%s\n' "$ARTIFACT_SHA" > /tmp/tpc-staging-artifact.sha
printf '%s\n' "$COMMIT" > /tmp/tpc-staging-commit.sha
echo "DONE stamp=$STAMP artifact=$ARTIFACT_SHA commit=$COMMIT"
