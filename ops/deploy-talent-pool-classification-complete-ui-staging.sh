#!/usr/bin/env bash
# Contained STAGING deploy for complete Talent Pool Classification UI.
# Deploys orchestrator modules + surgically patched app.py + dashboard dist.
# Does NOT touch /var/www or production orchestrator. Workers OFF.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_STAGE="/tmp/tpc-complete-ui-staging-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/staging/staging-evidence/talent-pool-classification-complete-ui/$STAMP"
REMOTE_BACKUP="/opt/wathefni/backups/staging-pre-tpc-complete-ui-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
STAGING_DASH="/opt/wathefni/staging/dashboard-dist"

log() { printf '\n=== %s ===\n' "$*"; }

mkdir -p "$LOCAL_STAGE/dashboard-dist"

log "source commit + artifact hashes"
COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
{
  ( cd "$ORCH_SRC" && shasum -a 256 \
      talent_pool_classification.py \
      talent_pool_classification_routes.py \
      talent_pool_taxonomy_v1.json \
      test_talent_pool_classification.py \
      ops/local-qualify-talent-pool-classification-complete-ui.py \
      ops/patch-staging-app-talent-pool-classification-complete-ui.py )
} | tee "$LOCAL_STAGE/allowlist.sha256"
ARTIFACT_SHA="$(shasum -a 256 "$LOCAL_STAGE/allowlist.sha256" | awk '{print $1}')"
echo "$COMMIT" > "$LOCAL_STAGE/source.commit"
echo "$ARTIFACT_SHA" > "$LOCAL_STAGE/artifact.sha256"
printf 'commit=%s\nartifact=%s\n' "$COMMIT" "$ARTIFACT_SHA"

log "local unit gates"
( cd "$ORCH_SRC" && python3 -m unittest test_talent_pool_classification.py -q )
( cd "$ORCH_SRC" && python3 ops/local-qualify-talent-pool-classification-complete-ui.py | tee "$LOCAL_STAGE/local-qualify.log" )

log "build dashboard"
( cd "$DASH_SRC" && npm test -- --run src/components/candidates/ClassificationFilters.test.tsx src/components/candidates/CandidatesTable.test.tsx )
( cd "$DASH_SRC" && npm run build )
rsync -a --delete "$DASH_SRC/dist/" "$LOCAL_STAGE/dashboard-dist/"
( cd "$LOCAL_STAGE/dashboard-dist" && find . -type f | sort | xargs shasum -a 256 ) | tee "$LOCAL_STAGE/dashboard-dist.sha256"
DASH_MANIFEST_SHA="$(shasum -a 256 "$LOCAL_STAGE/dashboard-dist.sha256" | awk '{print $1}')"
echo "$DASH_MANIFEST_SHA" > "$LOCAL_STAGE/dashboard-manifest.sha256"
# feature markers
grep -R "classification-filter-bar\|classification-compact-chip\|candidate-classification-section\|classification_skill\|Include Medium AI\|Show classification history" \
  "$LOCAL_STAGE/dashboard-dist" >/dev/null
printf 'dashboard_manifest=%s\n' "$DASH_MANIFEST_SHA"

log "patch staging app.py"
scp -o BatchMode=yes "$VPS_HOST:$STAGING_ORCH/app.py" "$LOCAL_STAGE/app.py.pre"
python3 "$ORCH_SRC/ops/patch-staging-app-talent-pool-classification-complete-ui.py" \
  "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched"
grep -q TALENT_POOL_CLASSIFICATION_COMPLETE_UI_PATCH "$LOCAL_STAGE/app.py.patched"
python3 -c "compile(open('$LOCAL_STAGE/app.py.patched').read(), 'app.py.patched', 'exec')"
shasum -a 256 "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched" | tee "$LOCAL_STAGE/app.py.sha256"

log "remote backup"
"${SSH[@]}" "set -e
  mkdir -p '$REMOTE_BACKUP' '$REMOTE_EVIDENCE'
  cp -a $STAGING_ORCH/app.py '$REMOTE_BACKUP/app.py.pre'
  cp -a $STAGING_ORCH/talent_pool_classification.py '$REMOTE_BACKUP/' 2>/dev/null || true
  cp -a $STAGING_ORCH/talent_pool_classification_routes.py '$REMOTE_BACKUP/' 2>/dev/null || true
  cp -a $STAGING_ORCH/talent_pool_taxonomy_v1.json '$REMOTE_BACKUP/' 2>/dev/null || true
  cp -a /etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf '$REMOTE_BACKUP/' 2>/dev/null || true
  cp -a /etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf '$REMOTE_BACKUP/' 2>/dev/null || true
  cp -a $STAGING_DASH '$REMOTE_BACKUP/dashboard-dist.pre'
  tmpdump=\$(mktemp /tmp/wathefni-staging-tpc-ui-XXXX.dump)
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
if [ -f \"\$ROOT/talent_pool_classification.py\" ]; then
  cp -a \"\$ROOT/talent_pool_classification.py\" /opt/wathefni/staging/orchestrator/
  cp -a \"\$ROOT/talent_pool_classification_routes.py\" /opt/wathefni/staging/orchestrator/
  cp -a \"\$ROOT/talent_pool_taxonomy_v1.json\" /opt/wathefni/staging/orchestrator/
fi
if [ -f \"\$ROOT/talent-pool-classification.conf\" ]; then
  cp -a \"\$ROOT/talent-pool-classification.conf\" /etc/systemd/system/wathefni-orchestrator-staging.service.d/
fi
rsync -a --delete \"\$ROOT/dashboard-dist.pre/\" /opt/wathefni/staging/dashboard-dist/
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
curl -sf http://127.0.0.1:8011/health
EOS
  chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'
  echo BACKUP_OK
"

log "upload artifacts"
scp -o BatchMode=yes \
  "$ORCH_SRC/talent_pool_classification.py" \
  "$ORCH_SRC/talent_pool_classification_routes.py" \
  "$ORCH_SRC/talent_pool_taxonomy_v1.json" \
  "$ORCH_SRC/test_talent_pool_classification.py" \
  "$ORCH_SRC/ops/local-qualify-talent-pool-classification-complete-ui.py" \
  "$ORCH_SRC/ops/patch-staging-app-talent-pool-classification-complete-ui.py" \
  "$LOCAL_STAGE/app.py.patched" \
  "$LOCAL_STAGE/allowlist.sha256" \
  "$LOCAL_STAGE/artifact.sha256" \
  "$LOCAL_STAGE/dashboard-dist.sha256" \
  "$LOCAL_STAGE/dashboard-manifest.sha256" \
  "$LOCAL_STAGE/source.commit" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"
rsync -az --delete -e "ssh -o BatchMode=yes" \
  "$LOCAL_STAGE/dashboard-dist/" "$VPS_HOST:$REMOTE_EVIDENCE/dashboard-dist/"

log "activate staging (classification UI ON for WATHEFNI only; workers OFF; production untouched)"
"${SSH[@]}" "set -e
  cp '$REMOTE_EVIDENCE/talent_pool_classification.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/talent_pool_classification_routes.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/talent_pool_taxonomy_v1.json' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/test_talent_pool_classification.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/local-qualify-talent-pool-classification-complete-ui.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/app.py.patched' $STAGING_ORCH/app.py
  rsync -a --delete '$REMOTE_EVIDENCE/dashboard-dist/' $STAGING_DASH/
  mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
  cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf <<'EOF'
[Service]
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION=off
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=WATHEFNI
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA=on
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL=on
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off
Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_UI=on
EOF
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator-staging.service
  for i in \$(seq 1 90); do curl -sf http://127.0.0.1:8011/health >/dev/null && break; sleep 1; done
  curl -sf http://127.0.0.1:8011/health >/dev/null
  /opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
import os, pathlib, sys
os.environ['WATHEFNI_ENV']='staging'
os.environ['WATHEFNI_POSTGRES_ENV']='/root/.openclaw/secrets/postgres.staging.env'
os.environ['WATHEFNI_WORKSPACE']='/opt/wathefni/staging/workspace'
os.environ['WATHEFNI_EXPECTED_DATABASE_HOST']='127.0.0.1'
os.environ['WATHEFNI_EXPECTED_DATABASE_PORT']='5432'
os.environ['WATHEFNI_EXPECTED_DATABASE_NAME']='wathefni_staging'
os.environ['WATHEFNI_DATABASE_ENVIRONMENT_MARKER']='wathefni-staging-hr2-isolation-v1'
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
print('SCHEMA_OK', ver, tpc.CLASSIFIER_VERSION)
PY
  # production orchestrator may already have dark classifier; must not change prod dashboard
  test -d /var/www/wathefni-dashboard
  PROD_DASH_SHA=\$(find /var/www/wathefni-dashboard -type f | sort | xargs sha256sum | sha256sum | awk '{print \$1}')
  echo PROD_DASH_SHA=\$PROD_DASH_SHA
  echo STAGING_COMPLETE_UI_DEPLOY_OK evidence=$REMOTE_EVIDENCE backup=$REMOTE_BACKUP
"

printf '%s\n' "$REMOTE_EVIDENCE" > /tmp/tpc-complete-ui-evidence.path
printf '%s\n' "$ARTIFACT_SHA" > /tmp/tpc-complete-ui-artifact.sha
printf '%s\n' "$DASH_MANIFEST_SHA" > /tmp/tpc-complete-ui-dashboard.sha
printf '%s\n' "$COMMIT" > /tmp/tpc-complete-ui-commit.sha
printf '%s\n' "$REMOTE_BACKUP" > /tmp/tpc-complete-ui-backup.path
echo "DONE stamp=$STAMP artifact=$ARTIFACT_SHA dashboard=$DASH_MANIFEST_SHA commit=$COMMIT"
