#!/usr/bin/env bash
# Contained PRODUCTION-DARK deploy for Unified Candidates + Talent Pool.
# Feature flag OFF globally. No tenant enablement. Does NOT use ops/deploy.sh production.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"

APPROVED_COMMIT="40a4e2621f4818bf7c0f6ce3642032297bfbe7b2"
APPROVED_ARTIFACT="c0a1fc0d129745999228a657c7acbb602076a42db6ec883a16a4c848bf4bdf45"
QUALIFIED_STAGE="/tmp/unified-candidates-staging-20260725T142706Z"
# Modules from staging evidence matching allowlist hashes
REMOTE_MODULE_SRC="/opt/wathefni/staging/staging-evidence/unified-candidates/20260725T142706Z"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_STAGE="/tmp/unified-candidates-production-dark-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/unified-candidates-dark/$STAMP"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-unified-candidates-dark-$STAMP"
PROD_ORCH="/opt/wathefni/orchestrator"

log() { printf '\n=== %s ===\n' "$*"; }

mkdir -p "$LOCAL_STAGE"

log "verify approved commit + artifact allowlist"
COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
test "$COMMIT" = "$APPROVED_COMMIT" || {
  echo "REFUSING: HEAD=$COMMIT expected $APPROVED_COMMIT" >&2
  exit 2
}
test -f "$QUALIFIED_STAGE/artifact.sha256"
test "$(cat "$QUALIFIED_STAGE/artifact.sha256")" = "$APPROVED_ARTIFACT"
cp "$QUALIFIED_STAGE/allowlist.sha256" "$QUALIFIED_STAGE/artifact.sha256" "$QUALIFIED_STAGE/source.commit" "$LOCAL_STAGE/"
echo "commit=$COMMIT artifact=$APPROVED_ARTIFACT"

log "pull production app.py and patch surgically (production anchors)"
scp -o BatchMode=yes "$VPS_HOST:$PROD_ORCH/app.py" "$LOCAL_STAGE/app.py.pre"
python3 "$ORCH_SRC/ops/patch-production-app-unified-candidates.py" \
  "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched"
shasum -a 256 "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched" | tee "$LOCAL_STAGE/app.py.sha256"
grep -q UNIFIED_CANDIDATES_PRODUCTION_DARK_PATCH "$LOCAL_STAGE/app.py.patched"

log "fetch allowlisted module bytes from qualified staging evidence"
"${SSH[@]}" "sha256sum \
  '$REMOTE_MODULE_SRC/unified_candidates.py' \
  '$REMOTE_MODULE_SRC/unified_candidates_routes.py' \
  '$REMOTE_MODULE_SRC/test_unified_candidates.py' \
  '$REMOTE_MODULE_SRC/local-qualify-unified-candidates.py'" | tee "$LOCAL_STAGE/modules.remote.sha256"
scp -o BatchMode=yes \
  "$VPS_HOST:$REMOTE_MODULE_SRC/unified_candidates.py" \
  "$VPS_HOST:$REMOTE_MODULE_SRC/unified_candidates_routes.py" \
  "$VPS_HOST:$REMOTE_MODULE_SRC/test_unified_candidates.py" \
  "$VPS_HOST:$REMOTE_MODULE_SRC/local-qualify-unified-candidates.py" \
  "$LOCAL_STAGE/"

log "predeploy backup + evidence dirs"
"${SSH[@]}" "set -e
  mkdir -p '$REMOTE_BACKUP' '$REMOTE_EVIDENCE'
  # record pre state
  {
    echo commit_expected=$APPROVED_COMMIT
    echo artifact_expected=$APPROVED_ARTIFACT
    echo prod_app_pre=\$(sha256sum $PROD_ORCH/app.py | awk '{print \$1}')
    echo last_green=\$(cat /opt/wathefni/orchestrator/last-green.sha256 2>/dev/null || cat /opt/wathefni/staging/last-green.sha256 2>/dev/null || echo unknown)
    systemctl show wathefni-orchestrator.service -p Environment --no-pager | tr ' ' '\n' | grep UNIFIED || echo NO_UNIFIED_FLAG
  } > '$REMOTE_EVIDENCE/PREDEPLOY.txt'
  cp -a $PROD_ORCH/app.py '$REMOTE_BACKUP/app.py.pre'
  if [ -d /var/www/wathefni-dashboard ]; then cp -a /var/www/wathefni-dashboard '$REMOTE_BACKUP/dashboard-dist.pre'; fi
  # fresh production DB backup via standard tool + explicit dump
  /usr/local/bin/backup-wathefni daily
  tmpdump=\$(mktemp /tmp/wathefni-prod-XXXX.dump)
  chown postgres:postgres \"\$tmpdump\"
  sudo -u postgres pg_dump -Fc -d wathefni -f \"\$tmpdump\"
  mv \"\$tmpdump\" '$REMOTE_BACKUP/db.dump'
  chmod 640 '$REMOTE_BACKUP/db.dump'
  sha256sum '$REMOTE_BACKUP/db.dump' '$REMOTE_BACKUP/app.py.pre' > '$REMOTE_BACKUP/SHA256SUMS'
  pg_restore --list '$REMOTE_BACKUP/db.dump' >/dev/null
  echo BACKUP_OK
  cat > '$REMOTE_BACKUP/ROLLBACK.sh' <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd \"\$(dirname \"\$0\")\" && pwd)
systemctl stop wathefni-orchestrator.service || true
cp -a \"\$ROOT/app.py.pre\" /opt/wathefni/orchestrator/app.py
rm -f /opt/wathefni/orchestrator/unified_candidates.py \
      /opt/wathefni/orchestrator/unified_candidates_routes.py \
      /opt/wathefni/orchestrator/test_unified_candidates.py \
      /opt/wathefni/orchestrator/local-qualify-unified-candidates.py
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
curl -sf http://127.0.0.1:8010/health
EOS
  chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'
  printf '%s\n' '$REMOTE_BACKUP' > /opt/wathefni/backups/.last-predeploy-unified-candidates-dark
"

log "upload artifact + deploy with flag OFF"
scp -o BatchMode=yes \
  "$LOCAL_STAGE/unified_candidates.py" \
  "$LOCAL_STAGE/unified_candidates_routes.py" \
  "$LOCAL_STAGE/test_unified_candidates.py" \
  "$LOCAL_STAGE/local-qualify-unified-candidates.py" \
  "$LOCAL_STAGE/app.py.patched" \
  "$LOCAL_STAGE/allowlist.sha256" \
  "$LOCAL_STAGE/artifact.sha256" \
  "$LOCAL_STAGE/source.commit" \
  "$LOCAL_STAGE/app.py.sha256" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"

"${SSH[@]}" "set -e
  # preserve staging untouched — only write production paths
  cp '$REMOTE_EVIDENCE/unified_candidates.py' $PROD_ORCH/
  cp '$REMOTE_EVIDENCE/unified_candidates_routes.py' $PROD_ORCH/
  cp '$REMOTE_EVIDENCE/test_unified_candidates.py' $PROD_ORCH/
  cp '$REMOTE_EVIDENCE/local-qualify-unified-candidates.py' $PROD_ORCH/
  cp '$REMOTE_EVIDENCE/app.py.patched' $PROD_ORCH/app.py
  mkdir -p /etc/systemd/system/wathefni-orchestrator.service.d
  cat > /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf <<'EOF'
[Service]
Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off
Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS=
EOF
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator.service
  for i in \$(seq 1 60); do curl -sf http://127.0.0.1:8010/health >/dev/null && break; sleep 1; done
  curl -sf http://127.0.0.1:8010/health
  echo
  # additive schema with flag OFF
  cd $PROD_ORCH
  export WATHEFNI_ENV=production
  export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
  export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
  export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
  export WATHEFNI_EXPECTED_DATABASE_PORT=5432
  export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
  export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
  /opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
import os, pathlib, psycopg2, sys
sys.path.insert(0, '/opt/wathefni/orchestrator')
vals={}
for line in pathlib.Path('/root/.openclaw/secrets/postgres.env').read_text().splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1); vals[k.strip()]=v.strip().strip('\"')
conn=psycopg2.connect(vals['WATHEFNI_DATABASE_URL'])
cur=conn.cursor()
import unified_candidates as uc
uc.ensure_unified_candidates_schema(cur)
conn.commit()
for t in ('candidate_record_governance','candidate_fact_review_events','candidate_saved_views'):
    cur.execute('SELECT to_regclass(%s)', (t,))
    print(t, cur.fetchone()[0])
    cur.execute(f'SELECT count(*) FROM {t}')
    print(t+'_count', cur.fetchone()[0])
conn.close()
print('schema_ok')
PY
  sha256sum $PROD_ORCH/app.py $PROD_ORCH/unified_candidates.py $PROD_ORCH/unified_candidates_routes.py > '$REMOTE_EVIDENCE/deployed.sha256'
  printf 'commit=%s\nartifact=%s\nbackup=%s\nflag=off\ntenants=\n' '$APPROVED_COMMIT' '$APPROVED_ARTIFACT' '$REMOTE_BACKUP' > '$REMOTE_EVIDENCE/ARTIFACT.txt'
  # confirm staging unchanged
  test -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf
  grep -q 'TENANTS=WATHEFNI' /etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf
  echo STAGING_FLAG_UNCHANGED
"

printf '%s\n' "$STAMP" > /tmp/unified-candidates-prod-dark.stamp
printf '%s\n' "$REMOTE_EVIDENCE" > /tmp/unified-candidates-prod-dark.evidence
printf '%s\n' "$REMOTE_BACKUP" > /tmp/unified-candidates-prod-dark.backup
echo "PRODUCTION_DARK_DEPLOY_COMPLETE stamp=$STAMP evidence=$REMOTE_EVIDENCE backup=$REMOTE_BACKUP"
