#!/usr/bin/env bash
# WATHEFNI controlled-live readiness runner (owner canary only).
# Does NOT enable normal-user live tools or Ranking reader.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
PROD_ORCH="/opt/wathefni/orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/candidate-knowledge-controlled-live/$STAMP"

MODULES=(
  candidate_knowledge_tools.py
  candidate_knowledge_index_worker.py
  candidate_knowledge_store.py
  candidate_knowledge_embeddings.py
  candidate_knowledge_search.py
  candidate_knowledge_indexer.py
  candidate_knowledge_postgres_index_store.py
)

log() { printf '\n=== %s ===\n' "$*"; }

log "preflight"
"${SSH[@]}" "set -euo pipefail
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  db=\$(psql \"\$WATHEFNI_DATABASE_URL\" -Atc 'SELECT current_database()')
  test \"\$db\" = 'wathefni'
  test -f /root/.openclaw/secrets/voyage.env
  mkdir -p '$REMOTE_EVIDENCE'
  echo PREFLIGHT_OK
"

log "deploy updated modules"
(
  cd "$ORCH_SRC"
  scp -o BatchMode=yes "${MODULES[@]}" "$VPS_HOST:$PROD_ORCH/"
)
scp -o BatchMode=yes \
  "$REPO_ROOT/ops/candidate-knowledge-controlled-live-qualify.py" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"

mkdir -p "$REPO_ROOT/ops/evidence/candidate-knowledge-controlled-live"
cat > "$REPO_ROOT/ops/evidence/candidate-knowledge-controlled-live/LATEST_PATHS.txt" <<EOF
STAMP=$STAMP
REMOTE_EVIDENCE=$REMOTE_EVIDENCE
EOF

log "run controlled-live qualification"
"${SSH[@]}" "set -euo pipefail
  export PYTHONUNBUFFERED=1
  export PYTHONPATH=/opt/wathefni/orchestrator
  export CK_LIVE_EVIDENCE='$REMOTE_EVIDENCE'
  /opt/wathefni/orchestrator/.venv/bin/python3 '$REMOTE_EVIDENCE/candidate-knowledge-controlled-live-qualify.py'
"

log "fetch evidence"
mkdir -p "$REPO_ROOT/ops/evidence/candidate-knowledge-controlled-live/$STAMP"
scp -o BatchMode=yes -r "$VPS_HOST:$REMOTE_EVIDENCE/." "$REPO_ROOT/ops/evidence/candidate-knowledge-controlled-live/$STAMP/"
echo "DONE stamp=$STAMP evidence=$REPO_ROOT/ops/evidence/candidate-knowledge-controlled-live/$STAMP"
