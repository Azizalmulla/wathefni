#!/usr/bin/env bash
# Contained staging deploy for Unified Candidates + Talent Pool.
# Does NOT touch production. Does NOT run ops/deploy.sh production.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_STAGE="/tmp/unified-candidates-staging-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/staging/staging-evidence/unified-candidates/$STAMP"
REMOTE_BACKUP="/opt/wathefni/backups/staging-pre-unified-candidates-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
STAGING_DASH="/opt/wathefni/staging/dashboard-dist"

ALLOWLIST=(
  unified_candidates.py
  unified_candidates_routes.py
  test_unified_candidates.py
  local-qualify-unified-candidates.py
  ops/patch-staging-app-unified-candidates.py
)

log() { printf '\n=== %s ===\n' "$*"; }

mkdir -p "$LOCAL_STAGE"
log "source commit + local artifact SHA"
COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
{
  ( cd "$ORCH_SRC" && shasum -a 256 "${ALLOWLIST[@]}" )
  shasum -a 256 "$ORCH_SRC"/ops/patch-staging-app-unified-candidates.py
} | tee "$LOCAL_STAGE/allowlist.sha256"
ARTIFACT_SHA="$(shasum -a 256 "$LOCAL_STAGE/allowlist.sha256" | awk '{print $1}')"
echo "$COMMIT" > "$LOCAL_STAGE/source.commit"
echo "$ARTIFACT_SHA" > "$LOCAL_STAGE/artifact.sha256"
printf 'commit=%s\nartifact=%s\n' "$COMMIT" "$ARTIFACT_SHA"

log "build dashboard (contained)"
( cd "$DASH_SRC" && npm test -- --run && npm run build )

log "patch staging app.py surgically"
scp -o BatchMode=yes "$VPS_HOST:$STAGING_ORCH/app.py" "$LOCAL_STAGE/app.py.pre"
python3 "$ORCH_SRC/ops/patch-staging-app-unified-candidates.py" \
  "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched"
shasum -a 256 "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched" | tee "$LOCAL_STAGE/app.py.sha256"

log "remote backup + evidence dirs"
"${SSH[@]}" "mkdir -p '$REMOTE_BACKUP' '$REMOTE_EVIDENCE' && \
  cp -a '$STAGING_ORCH/app.py' '$REMOTE_BACKUP/app.py.pre' && \
  cp -a '$STAGING_DASH' '$REMOTE_BACKUP/dashboard-dist.pre' && \
  tmpdump=\$(mktemp /tmp/wathefni-staging-XXXX.dump) && \
  chown postgres:postgres \"\$tmpdump\" && \
  sudo -u postgres pg_dump -Fc -d wathefni_staging -f \"\$tmpdump\" && \
  mv \"\$tmpdump\" '$REMOTE_BACKUP/db.dump' && \
  chmod 640 '$REMOTE_BACKUP/db.dump' && \
  sha256sum '$REMOTE_BACKUP/db.dump' '$REMOTE_BACKUP/app.py.pre' > '$REMOTE_BACKUP/SHA256SUMS' && \
  cat > '$REMOTE_BACKUP/ROLLBACK.sh' <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd \"\$(dirname \"\$0\")\" && pwd)
systemctl stop wathefni-orchestrator-staging.service || true
cp -a \"\$ROOT/app.py.pre\" /opt/wathefni/staging/orchestrator/app.py
rm -f /opt/wathefni/staging/orchestrator/unified_candidates.py \
      /opt/wathefni/staging/orchestrator/unified_candidates_routes.py
rsync -a --delete \"\$ROOT/dashboard-dist.pre/\" /opt/wathefni/staging/dashboard-dist/
rm -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
curl -sf http://127.0.0.1:8011/health
EOS
chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'"

log "phase1: apply additive schema with flag OFF"
# Deploy modules + patched app, but keep flag OFF via drop-in absent / off
rsync -az \
  "$ORCH_SRC/unified_candidates.py" \
  "$ORCH_SRC/unified_candidates_routes.py" \
  "$ORCH_SRC/test_unified_candidates.py" \
  "$ORCH_SRC/local-qualify-unified-candidates.py" \
  "$LOCAL_STAGE/app.py.patched" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"
"${SSH[@]}" "cp '$REMOTE_EVIDENCE/unified_candidates.py' '$STAGING_ORCH/' && \
  cp '$REMOTE_EVIDENCE/unified_candidates_routes.py' '$STAGING_ORCH/' && \
  cp '$REMOTE_EVIDENCE/test_unified_candidates.py' '$STAGING_ORCH/' && \
  cp '$REMOTE_EVIDENCE/local-qualify-unified-candidates.py' '$STAGING_ORCH/' && \
  cp '$REMOTE_EVIDENCE/app.py.patched' '$STAGING_ORCH/app.py' && \
  mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d && \
  cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf <<'EOF'
[Service]
Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off
Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS=
EOF
  systemctl daemon-reload && systemctl restart wathefni-orchestrator-staging.service && \
  sleep 2 && curl -sf http://127.0.0.1:8011/health && \
  /opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
import os, pathlib, psycopg2
os.environ['WATHEFNI_ENV']='staging'
os.environ['WATHEFNI_POSTGRES_ENV']='/root/.openclaw/secrets/postgres.staging.env'
vals={}
for line in pathlib.Path('/root/.openclaw/secrets/postgres.staging.env').read_text().splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1); vals[k.strip()]=v.strip().strip('\"')
conn=psycopg2.connect(vals['WATHEFNI_DATABASE_URL'])
cur=conn.cursor()
import sys
sys.path.insert(0,'/opt/wathefni/staging/orchestrator')
import unified_candidates as uc
uc.ensure_unified_candidates_schema(cur)
conn.commit()
for t in ('candidate_record_governance','candidate_fact_review_events','candidate_saved_views'):
    cur.execute('SELECT to_regclass(%s)', (t,))
    print(t, cur.fetchone()[0])
conn.close()
print('schema_ok')
PY"

log "deploy dashboard dist (feature-gated UI; backend still OFF until tenant enable)"
rsync -az --delete "$DASH_SRC/dist/" "$VPS_HOST:$STAGING_DASH/"

log "record artifact on host"
"${SSH[@]}" "printf 'commit=%s\nartifact=%s\nbackup=%s\n' '$COMMIT' '$ARTIFACT_SHA' '$REMOTE_BACKUP' > '$REMOTE_EVIDENCE/ARTIFACT.txt' && \
  cp '$LOCAL_STAGE/allowlist.sha256' '$REMOTE_EVIDENCE/' 2>/dev/null || true; \
  sha256sum '$STAGING_ORCH/app.py' '$STAGING_ORCH/unified_candidates.py' '$STAGING_ORCH/unified_candidates_routes.py' > '$REMOTE_EVIDENCE/deployed.sha256'"

# copy local allowlist evidence
scp -o BatchMode=yes "$LOCAL_STAGE/allowlist.sha256" "$LOCAL_STAGE/source.commit" "$LOCAL_STAGE/artifact.sha256" "$LOCAL_STAGE/app.py.sha256" \
  "$VPS_HOST:$REMOTE_EVIDENCE/" || true

printf '%s\n' "$STAMP" > /tmp/unified-candidates-staging.stamp
printf '%s\n' "$REMOTE_EVIDENCE" > /tmp/unified-candidates-staging.evidence
printf '%s\n' "$REMOTE_BACKUP" > /tmp/unified-candidates-staging.backup
printf '%s\n' "$COMMIT" > /tmp/unified-candidates-staging.commit
printf '%s\n' "$ARTIFACT_SHA" > /tmp/unified-candidates-staging.artifact
echo "DEPLOY_PHASE1_COMPLETE stamp=$STAMP evidence=$REMOTE_EVIDENCE backup=$REMOTE_BACKUP"
