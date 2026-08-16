#!/usr/bin/env bash
# Deploy entitlement-driven workspace composition (dashboard + orchestrator mirror).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_DIST="$REPO_ROOT/apps/wathefni-dashboard/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-workspace-composition-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/workspace-composition/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/workspace-composition-$STAMP"
PROD_ORCH=/opt/wathefni/orchestrator
PROD_DASH=/var/www/wathefni-dashboard
REMOTE_TMP="/tmp/workspace-composition-$STAMP"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "stamp=$STAMP"
mkdir -p "$LOCAL_EVIDENCE"
echo "$STAMP" > "$LOCAL_EVIDENCE/STAMP.txt"
echo "$REMOTE_BACKUP" > "$LOCAL_EVIDENCE/BACKUP_PATH.txt"
test -d "$DASH_DIST" || { echo "missing dist — run npm run build first"; exit 1; }

"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_before.txt"

log "backup $REMOTE_BACKUP"
"${SSH[@]}" "STAMP='$STAMP' BACKUP='$REMOTE_BACKUP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$BACKUP/dashboard-dist"
for f in workspace_capability.py test_workspace_composition_matrix.py; do
  if [ -f "$ORCH/$f" ]; then cp -a "$ORCH/$f" "$BACKUP/$f.pre"; else touch "$BACKUP/$f.MISSING"; fi
done
rsync -a "$DASH/" "$BACKUP/dashboard-dist/"
cat > "$BACKUP/ROLLBACK.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
for f in workspace_capability.py test_workspace_composition_matrix.py; do
  if [ -f "\$ROOT/\$f.pre" ]; then
    cp -a "\$ROOT/\$f.pre" "\$ORCH/\$f"
  elif [ -f "\$ROOT/\$f.MISSING" ]; then
    rm -f "\$ORCH/\$f"
  fi
done
rsync -a --delete "\$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl restart wathefni-orchestrator.service
sleep 3
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_health=%{http_code}\\n" http://127.0.0.1:8010/health
echo "Rolled back workspace composition ${STAMP}"
EOF
chmod 755 "$BACKUP/ROLLBACK.sh"
echo "$BACKUP"
REMOTE

log "upload"
"${SSH[@]}" "mkdir -p $REMOTE_TMP/dashboard-dist $REMOTE_EVIDENCE"
"${SCP[@]}" \
  "$ORCH_SRC/workspace_capability.py" \
  "$ORCH_SRC/test_workspace_composition_matrix.py" \
  "$VPS_HOST:$REMOTE_TMP/"
rsync -az -e "ssh -o BatchMode=yes" "$DASH_DIST/" "$VPS_HOST:$REMOTE_TMP/dashboard-dist/"

log "apply"
"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' EVIDENCE='$REMOTE_EVIDENCE' bash -s" <<'REMOTE'
set -euo pipefail
cp -a "$TMP/workspace_capability.py" "$ORCH/workspace_capability.py"
cp -a "$TMP/test_workspace_composition_matrix.py" "$ORCH/test_workspace_composition_matrix.py"
cd "$ORCH"
.venv/bin/python -m py_compile workspace_capability.py
.venv/bin/python test_workspace_composition_matrix.py | tee "$EVIDENCE/matrix_test.txt"
rsync -a --delete "$TMP/dashboard-dist/" "$DASH/"
systemctl restart wathefni-orchestrator.service
for i in 1 2 3 4 5 6 7 8; do
  sleep 2
  code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  echo "health_try_$i=$code"
  if [ "$code" = "200" ]; then break; fi
done
echo "$code" | tee "$EVIDENCE/health_after.txt"
systemctl reload caddy || true
# Prove dashboard bundle references workspace authority marker
python3 - <<'PY' | tee "$EVIDENCE/dashboard_bundle_probe.txt"
from pathlib import Path
root = Path("/var/www/wathefni-dashboard/assets")
hits = []
for p in root.glob("*.js"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    if "overview.action.review" in text or "workspaceAuthority" in text or "nav.overview" in text:
        hits.append(p.name)
print("bundle_hits=" + ",".join(hits[:8]) if hits else "bundle_hits=NONE")
print("pass" if hits else "fail")
PY
REMOTE

log "pull evidence"
mkdir -p "$LOCAL_EVIDENCE/remote"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVIDENCE/" "$LOCAL_EVIDENCE/remote/" || true
echo "$STAMP" > "$LOCAL_EVIDENCE/DEPLOY_STAMP.txt"
log "done stamp=$STAMP evidence=$LOCAL_EVIDENCE"
