#!/usr/bin/env bash
# WATHEFNI Candidate Knowledge final controlled live release + freeze.
# External tenants OFF. Role Profiles OFF. No iOS/Android / post-hiring audit.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
PROD_ORCH="/opt/wathefni/orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-ck-final-live-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/candidate-knowledge-final-live/$STAMP"

MODULES=(
  candidate_knowledge_live_registration.py
  candidate_knowledge_tools.py
  candidate_knowledge_authority.py
  candidate_knowledge_store.py
  candidate_knowledge_embeddings.py
  candidate_knowledge_search.py
  candidate_knowledge_indexer.py
  candidate_knowledge_postgres_index_store.py
  candidate_knowledge_index_worker.py
  ranking_evidence_adapter.py
  ranking_evidence_shadow.py
  candidate_ranking.py
  action_registry.py
  tool_call_orchestrator.py
  app.py
)

log() { printf '\n=== %s ===\n' "$*"; }

log "preflight"
"${SSH[@]}" "set -euo pipefail
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  db=\$(psql \"\$WATHEFNI_DATABASE_URL\" -Atc 'SELECT current_database()')
  test \"\$db\" = 'wathefni'
  test -f /root/.openclaw/secrets/voyage.env
  mkdir -p '$REMOTE_BACKUP/modules' '$REMOTE_EVIDENCE'
  echo PREFLIGHT_OK
"

log "backup + artifact hashes"
"${SSH[@]}" "set -euo pipefail
  cp -a /opt/wathefni/var/ck-flags.production.env '$REMOTE_BACKUP/ck-flags.production.env.pre' || true
  cp -a $PROD_ORCH/candidate_knowledge*.py $PROD_ORCH/ranking_evidence*.py $PROD_ORCH/candidate_ranking.py $PROD_ORCH/action_registry.py $PROD_ORCH/tool_call_orchestrator.py $PROD_ORCH/app.py '$REMOTE_BACKUP/modules/' 2>/dev/null || true
  tmpdump=\$(mktemp /tmp/wathefni-prod-ck-final-XXXX.dump)
  chown postgres:postgres \"\$tmpdump\"
  sudo -u postgres pg_dump -Fc -d wathefni -f \"\$tmpdump\"
  mv \"\$tmpdump\" '$REMOTE_BACKUP/db.dump'
  chmod 640 '$REMOTE_BACKUP/db.dump'
  pg_restore --list '$REMOTE_BACKUP/db.dump' > '$REMOTE_BACKUP/db.restore-list'
  test -s '$REMOTE_BACKUP/db.restore-list'
  {
    echo timestamp=\$(date -u +%FT%TZ)
    echo health=\$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health)
    echo orch_path=$PROD_ORCH
    echo db=wathefni
    sha256sum $PROD_ORCH/app.py $PROD_ORCH/action_registry.py $PROD_ORCH/candidate_ranking.py $PROD_ORCH/tool_call_orchestrator.py 2>/dev/null | sed 's#$PROD_ORCH/##' || true
    sha256sum $PROD_ORCH/candidate_knowledge*.py $PROD_ORCH/ranking_evidence*.py 2>/dev/null | sed 's#$PROD_ORCH/##' || true
    echo '--- flags ---'
    cat /opt/wathefni/var/ck-flags.production.env || true
  } > '$REMOTE_EVIDENCE/PREDEPLOY.txt'
  cat > '$REMOTE_BACKUP/ROLLBACK.sh' <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd \"\$(dirname \"\$0\")\" && pwd)
systemctl stop wathefni-ck-index.service || true
systemctl disable wathefni-ck-index.service || true
if [[ -f \"\$ROOT/ck-flags.production.env.pre\" ]]; then
  cp -a \"\$ROOT/ck-flags.production.env.pre\" /opt/wathefni/var/ck-flags.production.env
fi
# Hard pin safe-off if pre flags missing
if [[ ! -f /opt/wathefni/var/ck-flags.production.env ]]; then
  cat > /opt/wathefni/var/ck-flags.production.env <<EOF
WATHEFNI_CANDIDATE_KNOWLEDGE=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI
WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA=on
WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=0
WATHEFNI_CK_RANKING_SHADOW=0
WATHEFNI_ENV=production
WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
EOF
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
echo ROLLBACK_FLAGS_APPLIED
EOS
  chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'
  echo BACKUP_OK path=$REMOTE_BACKUP
"

log "deploy modules"
(
  cd "$ORCH_SRC"
  scp -o BatchMode=yes "${MODULES[@]}" "$VPS_HOST:$PROD_ORCH/"
)
scp -o BatchMode=yes \
  "$REPO_ROOT/ops/candidate-knowledge-final-live-qualify.py" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"

mkdir -p "$REPO_ROOT/ops/evidence/candidate-knowledge-final-live"
cat > "$REPO_ROOT/ops/evidence/candidate-knowledge-final-live/LATEST_PATHS.txt" <<EOF
STAMP=$STAMP
REMOTE_BACKUP=$REMOTE_BACKUP
REMOTE_EVIDENCE=$REMOTE_EVIDENCE
EOF

log "run final live qualification"
"${SSH[@]}" "set -euo pipefail
  export PYTHONUNBUFFERED=1
  export PYTHONPATH=/opt/wathefni/orchestrator
  export CK_FINAL_EVIDENCE='$REMOTE_EVIDENCE'
  export CK_FINAL_BACKUP='$REMOTE_BACKUP'
  /opt/wathefni/orchestrator/.venv/bin/python3 '$REMOTE_EVIDENCE/candidate-knowledge-final-live-qualify.py'
"

log "fetch evidence"
mkdir -p "$REPO_ROOT/ops/evidence/candidate-knowledge-final-live/$STAMP"
scp -o BatchMode=yes -r "$VPS_HOST:$REMOTE_EVIDENCE/." "$REPO_ROOT/ops/evidence/candidate-knowledge-final-live/$STAMP/"
echo "DONE stamp=$STAMP evidence=$REPO_ROOT/ops/evidence/candidate-knowledge-final-live/$STAMP"
