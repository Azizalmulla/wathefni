#!/usr/bin/env bash
# Stage A: install Candidate Knowledge into staging service (not production).
set -euo pipefail

HOST="${WATHEFNI_STAGING_HOST:-root@76.13.63.68}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
REMOTE_ORCH="/opt/wathefni/staging/orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP="/opt/wathefni/staging/backups/ck-phase8-${STAMP}"

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

echo "== Stage A backup =="
ssh -o BatchMode=yes "$HOST" "mkdir -p '$BACKUP/orchestrator' && cp -a $REMOTE_ORCH/candidate_knowledge*.py $REMOTE_ORCH/ranking_evidence*.py '$BACKUP/orchestrator/' 2>/dev/null || true; sudo -u postgres pg_dump -d wathefni_staging -s -t candidate_knowledge_chunks -t candidate_knowledge_index_jobs -t candidate_knowledge_access_events > '$BACKUP/ck-schema.sql' || true; echo backup=$BACKUP"

echo "== Deploy modules =="
(
  cd "$ORCH"
  scp -o BatchMode=yes "${MODULES[@]}" "$HOST:$REMOTE_ORCH/"
)

echo "== Flags + systemd + schema + restart =="
ssh -o BatchMode=yes "$HOST" "bash -s" <<'REMOTE'
set -euo pipefail
BACKUP_NOTE=/opt/wathefni/staging/var/ck-phase8-install.txt
mkdir -p /opt/wathefni/staging/var

cat > /opt/wathefni/staging/var/ck-flags.env <<'EOF'
WATHEFNI_CANDIDATE_KNOWLEDGE=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TENANTS=WATHEFNI,SYN_CK_P8
WATHEFNI_CANDIDATE_KNOWLEDGE_SCHEMA=on
WATHEFNI_CANDIDATE_KNOWLEDGE_INDEX_WORKERS=on
WATHEFNI_CANDIDATE_KNOWLEDGE_TOOLS=off
WATHEFNI_CANDIDATE_KNOWLEDGE_RANKING_READER=off
WATHEFNI_CK_SHADOW_TOOLS_ENABLED=0
WATHEFNI_CK_RANKING_SHADOW=0
WATHEFNI_CK_EMBEDDINGS_ENABLED=0
WATHEFNI_CK_VOYAGE_ENABLED=0
WATHEFNI_CK_SEMANTIC_SEARCH=0
CK_WORKER_CONCURRENCY=2
WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
EOF

cat > /etc/systemd/system/wathefni-ck-index-staging.service <<'EOF'
[Unit]
Description=Wathefni Candidate Knowledge Index Worker (STAGING)
After=network.target postgresql.service wathefni-orchestrator-staging.service

[Service]
Type=simple
WorkingDirectory=/opt/wathefni/staging/orchestrator
Environment=WATHEFNI_ENV=staging
Environment=WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
Environment=WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
Environment=PYTHONPATH=/opt/wathefni/staging/orchestrator
EnvironmentFile=-/root/.openclaw/secrets/postgres.staging.env
EnvironmentFile=-/root/.openclaw/secrets/voyage.env
EnvironmentFile=-/opt/wathefni/staging/var/ck-flags.env
ExecStart=/usr/bin/python3 /opt/wathefni/staging/orchestrator/candidate_knowledge_index_worker.py
Restart=on-failure
RestartSec=5
Nice=10

[Install]
WantedBy=multi-user.target
EOF

if ! grep -q 'ck-flags.env' /etc/systemd/system/wathefni-orchestrator-staging.service; then
  cp /etc/systemd/system/wathefni-orchestrator-staging.service /etc/systemd/system/wathefni-orchestrator-staging.service.bak-ck-phase8
  printf '\nEnvironmentFile=-/opt/wathefni/staging/var/ck-flags.env\n' >> /etc/systemd/system/wathefni-orchestrator-staging.service
fi

systemctl daemon-reload

cd /opt/wathefni/staging/orchestrator
PYTHONPATH=/opt/wathefni/staging/orchestrator python3 <<'PY'
from pathlib import Path
import os, psycopg2
from psycopg2.extras import RealDictCursor
from candidate_knowledge_postgres_index_store import PostgresCandidateKnowledgeIndexStore

vals = {}
for p in ("/root/.openclaw/secrets/postgres.staging.env", "/opt/wathefni/staging/var/ck-flags.env"):
    for line in Path(p).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        vals[k.strip()] = v.strip().strip('"').strip("'")
os.environ.update(vals)
url = vals["WATHEFNI_DATABASE_URL"]

class Ctx:
    def __enter__(self):
        self.conn = psycopg2.connect(url, cursor_factory=RealDictCursor)
        self.conn.autocommit = True
        self.cur = self.conn.cursor()
        return self.cur
    def __exit__(self, *a):
        self.cur.close()
        self.conn.close()

store = PostgresCandidateKnowledgeIndexStore(connect=Ctx)
store.ensure_schema()
store.ensure_schema()
with Ctx() as cur:
    cur.execute("SELECT current_database() AS db")
    assert cur.fetchone()["db"] == "wathefni_staging"
    cur.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name LIKE 'candidate_knowledge%%' ORDER BY 1"
    )
    tables = [r["table_name"] for r in cur.fetchall()]
    assert len(tables) >= 3, tables
print("schema_ok", tables)
PY

systemctl restart wathefni-orchestrator-staging.service
sleep 2
curl -fsS -o /dev/null -w "health_after_orch=%{http_code}\n" http://127.0.0.1:8011/health
systemctl enable wathefni-ck-index-staging.service >/dev/null 2>&1 || true
systemctl restart wathefni-ck-index-staging.service
sleep 2
systemctl is-active wathefni-orchestrator-staging.service
systemctl is-active wathefni-ck-index-staging.service

python3 - <<'PY'
from pathlib import Path
text = Path("/opt/wathefni/staging/orchestrator/action_registry.py").read_text(encoding="utf-8")
for name in ("search_candidates", "get_candidate_knowledge", "compare_candidates"):
    assert name not in text, name
print("action_registry_ck_tools_absent")
PY

systemctl stop wathefni-ck-index-staging.service
sleep 1
systemctl start wathefni-ck-index-staging.service
sleep 1
systemctl is-active wathefni-ck-index-staging.service
echo "STAGE_A_INSTALL_DONE" | tee "$BACKUP_NOTE"
REMOTE

echo "Stage A deploy finished."
