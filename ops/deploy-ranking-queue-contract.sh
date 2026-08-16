#!/usr/bin/env bash
# Deploy Ranking consistency contract (exact files only).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_DIST="$REPO_ROOT/apps/wathefni-dashboard/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-ranking-queue-contract-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/ranking-queue-contract/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/ranking-queue-contract-$STAMP"
PROD_ORCH=/opt/wathefni/orchestrator
PROD_DASH=/var/www/wathefni-dashboard
REMOTE_TMP="/tmp/ranking-queue-contract-$STAMP"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "stamp=$STAMP"
mkdir -p "$LOCAL_EVIDENCE"
"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_before.txt"

log "backup $REMOTE_BACKUP"
"${SSH[@]}" "STAMP='$STAMP' BACKUP='$REMOTE_BACKUP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$BACKUP/dashboard-dist"
for f in candidate_ranking.py app.py test_candidate_ranking.py; do
  cp -a "$ORCH/$f" "$BACKUP/$f.pre"
done
if [ -f "$ORCH/ranking_queue_contract.py" ]; then
  cp -a "$ORCH/ranking_queue_contract.py" "$BACKUP/ranking_queue_contract.py.pre"
else
  touch "$BACKUP/ranking_queue_contract.py.MISSING"
fi
if [ -f "$ORCH/test_ranking_queue_contract.py" ]; then
  cp -a "$ORCH/test_ranking_queue_contract.py" "$BACKUP/test_ranking_queue_contract.py.pre"
else
  touch "$BACKUP/test_ranking_queue_contract.py.MISSING"
fi
rsync -a "$DASH/" "$BACKUP/dashboard-dist/"
python3 - <<'PY'
from pathlib import Path
import os
stamp = os.environ["STAMP"]
path = Path(os.environ["BACKUP"]) / "ROLLBACK.sh"
path.write_text(f"""#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$ROOT/app.py.pre" "$ORCH/app.py"
cp -a "$ROOT/candidate_ranking.py.pre" "$ORCH/candidate_ranking.py"
cp -a "$ROOT/test_candidate_ranking.py.pre" "$ORCH/test_candidate_ranking.py"
if [ -f "$ROOT/ranking_queue_contract.py.pre" ]; then
  cp -a "$ROOT/ranking_queue_contract.py.pre" "$ORCH/ranking_queue_contract.py"
elif [ -f "$ROOT/ranking_queue_contract.py.MISSING" ]; then
  rm -f "$ORCH/ranking_queue_contract.py"
fi
if [ -f "$ROOT/test_ranking_queue_contract.py.pre" ]; then
  cp -a "$ROOT/test_ranking_queue_contract.py.pre" "$ORCH/test_ranking_queue_contract.py"
elif [ -f "$ROOT/test_ranking_queue_contract.py.MISSING" ]; then
  rm -f "$ORCH/test_ranking_queue_contract.py"
fi
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl restart wathefni-orchestrator.service
sleep 3
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_health=%{{http_code}}\\n" http://127.0.0.1:8010/health
echo "Rolled back ranking queue contract {stamp}"
""")
path.chmod(0o755)
print(path.parent)
PY
REMOTE

# Extract only the rank route from local app for surgical patch helpers are in candidate_ranking;
# deploy full candidate_ranking + ranking_queue_contract; patch app.py route via python on server using local snippet.
python3 <<'PY'
from pathlib import Path
import re
text = Path("/Users/azizalmulla/Desktop/claw/wathefni-orchestrator/app.py").read_text()
# Extract dashboard_prehire_rank function through next @app
m = re.search(r'@app\.get\("/dashboard/prehire/rank"\)\ndef dashboard_prehire_rank\([\s\S]*?\n\n\n@app\.', text)
if not m:
    # try double newline before next decorator
    m = re.search(r'@app\.get\("/dashboard/prehire/rank"\)\ndef dashboard_prehire_rank\([\s\S]*?\n(?=@app\.)', text)
if not m:
    raise SystemExit('rank route not found')
route = m.group(0)
if not route.endswith('\n'):
    route += '\n'
# strip trailing @app. if captured
if route.rstrip().endswith('@app.'):
    route = route.rsplit('@app.', 1)[0]
Path('/tmp/patch-dashboard_prehire_rank.py').write_text(route)
print('route_chars', len(route))
PY

log "upload"
"${SSH[@]}" "mkdir -p $REMOTE_TMP/dashboard-dist"
"${SCP[@]}" \
  "$ORCH_SRC/ranking_queue_contract.py" \
  "$ORCH_SRC/candidate_ranking.py" \
  "$ORCH_SRC/test_ranking_queue_contract.py" \
  "$ORCH_SRC/test_candidate_ranking.py" \
  /tmp/patch-dashboard_prehire_rank.py \
  "$SCRIPT_DIR/prove-ranking-queue-contract-live.py" \
  "$VPS_HOST:$REMOTE_TMP/"
rsync -az -e "ssh -o BatchMode=yes" "$DASH_DIST/" "$VPS_HOST:$REMOTE_TMP/dashboard-dist/"

log "apply"
"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' EVIDENCE='$REMOTE_EVIDENCE' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$EVIDENCE"
cp -a "$TMP/ranking_queue_contract.py" "$ORCH/ranking_queue_contract.py"
cp -a "$TMP/candidate_ranking.py" "$ORCH/candidate_ranking.py"
cp -a "$TMP/test_ranking_queue_contract.py" "$ORCH/test_ranking_queue_contract.py"
cp -a "$TMP/test_candidate_ranking.py" "$ORCH/test_candidate_ranking.py"
cp -a "$TMP/prove-ranking-queue-contract-live.py" "$EVIDENCE/"

python3 <<'PY'
from pathlib import Path
import re, os
tmp = Path(os.environ["TMP"])
orch = Path("/opt/wathefni/orchestrator/app.py")
text = orch.read_text()
route = (tmp / "patch-dashboard_prehire_rank.py").read_text()
if not route.endswith("\n"):
    route += "\n"
rm = re.search(
    r'@app\.get\("/dashboard/prehire/rank"\)\ndef dashboard_prehire_rank\([\s\S]*?\n(?=@app\.)',
    text,
)
if not rm:
    raise SystemExit("prod rank route not found")
text = text[: rm.start()] + route + text[rm.end() :]
compile(text, str(orch), "exec")
orch.write_text(text)
print("app.py rank route patched")
PY

rsync -a --delete "$TMP/dashboard-dist/" "$DASH/"
systemctl restart wathefni-orchestrator.service
for i in 1 2 3 4 5 6 7 8; do
  sleep 2
  code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  echo "health_try_$i=$code"
  if [ "$code" = "200" ]; then break; fi
done
echo "$code" | tee "$EVIDENCE/health_after.txt"
test "$code" = "200"

cd "$ORCH"
python3 -m unittest test_ranking_queue_contract -v 2>&1 | tee "$EVIDENCE/unit-tests.txt"

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
# shellcheck disable=SC1091
source /root/.openclaw/secrets/voyage.env
set +a
# Match systemd service: voyage.env may pin voyage-4; Ranking authority requires voyage-4-large.
export WATHEFNI_ENV=production
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_VOYAGE_ENV=/root/.openclaw/secrets/voyage.env
export WATHEFNI_EMBEDDING_PROVIDER=voyage
export WATHEFNI_EMBEDDING_MODEL=voyage-4-large
export WATHEFNI_EMBEDDING_DIMENSIONS=1024
export WATHEFNI_RERANK_MODEL=rerank-2.5
"$ORCH/.venv/bin/python" "$EVIDENCE/prove-ranking-queue-contract-live.py" "$EVIDENCE/live-proof.json" | tee "$EVIDENCE/live-proof-summary.json"
"$ORCH/.venv/bin/python" - <<PY
import json
from pathlib import Path
import os
d=json.loads(Path(os.environ["EVIDENCE"], "live-proof.json").read_text())
print("LIVE_VERDICT", d.get("verdict"))
raise SystemExit(0 if d.get("verdict")=="PASS" else 1)
PY
REMOTE

mkdir -p "$LOCAL_EVIDENCE"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/live-proof.json" "$LOCAL_EVIDENCE/"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/live-proof-summary.json" "$LOCAL_EVIDENCE/"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/unit-tests.txt" "$LOCAL_EVIDENCE/"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/health_after.txt" "$LOCAL_EVIDENCE/"
echo "$STAMP" > "$LOCAL_EVIDENCE/STAMP.txt"
echo "$REMOTE_BACKUP" > "$LOCAL_EVIDENCE/BACKUP_PATH.txt"
cp "$ORCH_SRC/ranking_queue_contract.py" "$LOCAL_EVIDENCE/"
log "done evidence=$LOCAL_EVIDENCE"
