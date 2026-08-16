#!/usr/bin/env bash
# WATHEFNI-only Candidate Knowledge production-dark execution.
# Live tools OFF. Live Ranking reader OFF. External tenants OFF.
# Does not modify action_registry tool registration.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
PROD_ORCH="/opt/wathefni/orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-ck-dark-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/candidate-knowledge-dark/$STAMP"

MODULES=(
  candidate_knowledge_authority.py
  candidate_knowledge_store.py
  candidate_knowledge_readers.py
  candidate_knowledge_phase3_readers.py
  candidate_knowledge_errors.py
  candidate_knowledge_types.py
  candidate_record_state_policy.py
  candidate_knowledge_chunker.py
  candidate_knowledge_embeddings.py
  candidate_knowledge_index_schema.py
  candidate_knowledge_index_store.py
  candidate_knowledge_postgres_index_store.py
  candidate_knowledge_indexer.py
  candidate_knowledge_search.py
  candidate_knowledge_tools.py
  candidate_knowledge_index_worker.py
  ranking_evidence_adapter.py
  ranking_evidence_shadow.py
)

log() { printf '\n=== %s ===\n' "$*"; }
refuse() { echo "REFUSING: $*" >&2; exit 2; }

log "preflight production health + isolation"
"${SSH[@]}" "set -euo pipefail
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  set -a; source /root/.openclaw/secrets/postgres.env; set +a
  db=\$(psql \"\$WATHEFNI_DATABASE_URL\" -Atc 'SELECT current_database()')
  test \"\$db\" = 'wathefni'
  # refuse if accidentally pointing at staging
  test \"\$db\" != 'wathefni_staging'
  echo PREFLIGHT_OK db=\$db
"

log "backup + rollback point"
"${SSH[@]}" "set -euo pipefail
  mkdir -p '$REMOTE_BACKUP/modules' '$REMOTE_EVIDENCE'
  cp -a /etc/systemd/system/wathefni-orchestrator.service '$REMOTE_BACKUP/' || true
  cp -a /etc/systemd/system/wathefni-orchestrator.service.d '$REMOTE_BACKUP/service.d.pre' || true
  # snapshot any existing ck modules (expect none)
  cp -a $PROD_ORCH/candidate_knowledge*.py $PROD_ORCH/ranking_evidence*.py $PROD_ORCH/candidate_record_state_policy.py '$REMOTE_BACKUP/modules/' 2>/dev/null || true
  tmpdump=\$(mktemp /tmp/wathefni-prod-ck-XXXX.dump)
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
    sha256sum $PROD_ORCH/app.py $PROD_ORCH/action_registry.py | sed 's#$PROD_ORCH/##'
  } > '$REMOTE_EVIDENCE/PREDEPLOY.txt'
  cat > '$REMOTE_BACKUP/ROLLBACK.sh' <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd \"\$(dirname \"\$0\")\" && pwd)
systemctl stop wathefni-ck-index.service || true
systemctl disable wathefni-ck-index.service || true
rm -f /etc/systemd/system/wathefni-ck-index.service
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/candidate-knowledge.conf
rm -f /opt/wathefni/var/ck-flags.production.env
# Remove CK modules deployed by dark run (additive projection only).
rm -f /opt/wathefni/orchestrator/candidate_knowledge_*.py
rm -f /opt/wathefni/orchestrator/ranking_evidence_*.py
rm -f /opt/wathefni/orchestrator/candidate_record_state_policy.py
# Restore any pre-existing module copies if present.
if ls \"\$ROOT/modules\"/* >/dev/null 2>&1; then cp -a \"\$ROOT/modules\"/. /opt/wathefni/orchestrator/; fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 60); do
  curl -sf http://127.0.0.1:8010/health >/dev/null && break
  sleep 1
done
curl -sf http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
# Note: additive CK tables are retained (search projection). Drop only with explicit owner order:
# DROP TABLE IF EXISTS candidate_knowledge_chunks, candidate_knowledge_index_jobs, candidate_knowledge_access_events;
EOS
  chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'
  echo BACKUP_OK $REMOTE_BACKUP
"

log "deploy CK modules (additive; no action_registry registration)"
(
  cd "$ORCH_SRC"
  scp -o BatchMode=yes "${MODULES[@]}" "$VPS_HOST:$PROD_ORCH/"
)
scp -o BatchMode=yes \
  "$REPO_ROOT/ops/candidate-knowledge-production-dark-qualify.py" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"

log "install flags + worker unit (tools/ranking OFF)"
"${SSH[@]}" "set -euo pipefail
  mkdir -p /opt/wathefni/var /etc/systemd/system/wathefni-orchestrator.service.d
  cat > /opt/wathefni/var/ck-flags.production.env <<'EOF'
WATHEFNI_CANDIDATE_KNOWLEDGE=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI
WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA=on
WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=0
WATHEFNI_CK_RANKING_SHADOW=0
WATHEFNI_CK_EMBEDDINGS_ENABLED=1
WATHEFNI_CK_VOYAGE_ENABLED=0
WATHEFNI_CK_SEMANTIC_SEARCH=0
CK_WORKER_CONCURRENCY=1
WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
WATHEFNI_ALLOW_NON_STAGING_DB=1
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
WATHEFNI_ENV=production
EOF
  cat > /etc/systemd/system/wathefni-orchestrator.service.d/candidate-knowledge.conf <<'EOF'
[Service]
EnvironmentFile=-/opt/wathefni/var/ck-flags.production.env
EOF
  cat > /etc/systemd/system/wathefni-ck-index.service <<'EOF'
[Unit]
Description=Wathefni Candidate Knowledge Index Worker (PRODUCTION-DARK)
After=network.target postgresql.service wathefni-orchestrator.service

[Service]
Type=simple
WorkingDirectory=/opt/wathefni/orchestrator
Environment=WATHEFNI_ENV=production
Environment=WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
Environment=WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
Environment=PYTHONPATH=/opt/wathefni/orchestrator
EnvironmentFile=-/root/.openclaw/secrets/postgres.env
EnvironmentFile=-/root/.openclaw/secrets/voyage.env
EnvironmentFile=-/opt/wathefni/var/ck-flags.production.env
ExecStart=/opt/wathefni/orchestrator/.venv/bin/python3 /opt/wathefni/orchestrator/candidate_knowledge_index_worker.py
Restart=on-failure
RestartSec=5
Nice=10

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  # Apply additive schema while workers off
  PYTHONPATH=/opt/wathefni/orchestrator /opt/wathefni/orchestrator/.venv/bin/python3 - <<'PY'
from pathlib import Path
import os, psycopg2
from psycopg2.extras import RealDictCursor
from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore
vals={}
for p in ('/root/.openclaw/secrets/postgres.env','/opt/wathefni/var/ck-flags.production.env'):
  for line in Path(p).read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    k,v=line.split('=',1); vals[k.strip()]=v.strip().strip('\"').strip(\"'\")
os.environ.update(vals)
url=vals['WATHEFNI_DATABASE_URL']
class Ctx:
  def __enter__(self):
    self.conn=psycopg2.connect(url, cursor_factory=RealDictCursor); self.conn.autocommit=True; self.cur=self.conn.cursor(); return self.cur
  def __exit__(self,*a):
    self.cur.close(); self.conn.close()
store=PostgresCandidateKnowledgeIndexStore(connect=Ctx)
store.ensure_schema(); store.ensure_schema()
with Ctx() as cur:
  cur.execute('SELECT current_database() AS db'); assert cur.fetchone()['db']=='wathefni'
  cur.execute(\"SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'candidate_knowledge%%' ORDER BY 1\")
  tables=[r['table_name'] for r in cur.fetchall()]
  assert len(tables)>=3, tables
print('SCHEMA_OK', tables)
PY
  # Prove registry still has no CK tools
  python3 - <<'PY'
from pathlib import Path
text=Path('/opt/wathefni/orchestrator/action_registry.py').read_text(encoding='utf-8')
for name in ('search_candidates','get_candidate_knowledge','compare_candidates'):
  assert name not in text, name
print('REGISTRY_CK_TOOLS_ABSENT')
PY
  systemctl restart wathefni-orchestrator.service
  for i in \$(seq 1 60); do
    code=\$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health || true)
    test \"\$code\" = 200 && break
    sleep 1
  done
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  # worker remains stopped (flag off)
  systemctl stop wathefni-ck-index.service || true
  echo DEPLOY_DARK_OK
  echo EVIDENCE=$REMOTE_EVIDENCE
  echo BACKUP=$REMOTE_BACKUP
" 

# Persist stamp paths locally for qualify step
mkdir -p "$REPO_ROOT/ops/evidence/candidate-knowledge-production-dark"
cat > "$REPO_ROOT/ops/evidence/candidate-knowledge-production-dark/LATEST_PATHS.txt" <<EOF
STAMP=$STAMP
REMOTE_BACKUP=$REMOTE_BACKUP
REMOTE_EVIDENCE=$REMOTE_EVIDENCE
PROD_ORCH=$PROD_ORCH
EOF

log "run production-dark qualification harness"
"${SSH[@]}" "set -euo pipefail
  export PYTHONUNBUFFERED=1
  export PYTHONPATH=/opt/wathefni/orchestrator
  export CK_DARK_EVIDENCE='$REMOTE_EVIDENCE'
  export CK_DARK_BACKUP='$REMOTE_BACKUP'
  /opt/wathefni/orchestrator/.venv/bin/python3 '$REMOTE_EVIDENCE/candidate-knowledge-production-dark-qualify.py'
"

log "fetch evidence"
mkdir -p "$REPO_ROOT/ops/evidence/candidate-knowledge-production-dark/$STAMP"
scp -o BatchMode=yes -r "$VPS_HOST:$REMOTE_EVIDENCE/"* "$REPO_ROOT/ops/evidence/candidate-knowledge-production-dark/$STAMP/" || true
echo "DONE stamp=$STAMP evidence=$REPO_ROOT/ops/evidence/candidate-knowledge-production-dark/$STAMP"
