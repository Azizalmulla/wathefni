#!/usr/bin/env bash
# Deploy Wathefni Assistant grounded HR operating copilot (orchestrator + dashboard).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_DIST="$REPO_ROOT/apps/wathefni-dashboard/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-assistant-copilot-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/assistant-copilot/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/assistant-copilot-$STAMP"
PROD_ORCH=/opt/wathefni/orchestrator
PROD_DASH=/var/www/wathefni-dashboard
REMOTE_TMP="/tmp/assistant-copilot-$STAMP"

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
for f in app.py action_registry.py tool_call_orchestrator.py assistant_policy.py; do
  cp -a "$ORCH/$f" "$BACKUP/$f.pre"
done
for f in assistant_capability_catalog.py test_assistant_capability_catalog.py test_assistant_workflow_contract.py; do
  if [ -f "$ORCH/$f" ]; then cp -a "$ORCH/$f" "$BACKUP/$f.pre"; else touch "$BACKUP/$f.MISSING"; fi
done
rsync -a "$DASH/" "$BACKUP/dashboard-dist/"
cat > "$BACKUP/ROLLBACK.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
for f in app.py action_registry.py tool_call_orchestrator.py assistant_policy.py; do
  cp -a "\$ROOT/\$f.pre" "\$ORCH/\$f"
done
for f in assistant_capability_catalog.py test_assistant_capability_catalog.py test_assistant_workflow_contract.py; do
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
echo "Rolled back assistant copilot ${STAMP}"
EOF
chmod 755 "$BACKUP/ROLLBACK.sh"
echo "$BACKUP"
REMOTE

log "upload"
"${SSH[@]}" "mkdir -p $REMOTE_TMP/dashboard-dist $REMOTE_EVIDENCE"
"${SCP[@]}" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/action_registry.py" \
  "$ORCH_SRC/tool_call_orchestrator.py" \
  "$ORCH_SRC/assistant_policy.py" \
  "$ORCH_SRC/assistant_capability_catalog.py" \
  "$ORCH_SRC/test_assistant_capability_catalog.py" \
  "$ORCH_SRC/test_assistant_workflow_contract.py" \
  "$ORCH_SRC/smoke-test-toolcall-orchestrator.py" \
  "$SCRIPT_DIR/prove-assistant-copilot-live.py" \
  "$VPS_HOST:$REMOTE_TMP/"
rsync -az -e "ssh -o BatchMode=yes" "$DASH_DIST/" "$VPS_HOST:$REMOTE_TMP/dashboard-dist/"

log "apply"
"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' EVIDENCE='$REMOTE_EVIDENCE' bash -s" <<'REMOTE'
set -euo pipefail
for f in app.py action_registry.py tool_call_orchestrator.py assistant_policy.py assistant_capability_catalog.py test_assistant_capability_catalog.py test_assistant_workflow_contract.py smoke-test-toolcall-orchestrator.py; do
  cp -a "$TMP/$f" "$ORCH/$f"
done
cp -a "$TMP/prove-assistant-copilot-live.py" "$EVIDENCE/"
# Syntax check critical modules
cd "$ORCH"
.venv/bin/python -m py_compile app.py action_registry.py tool_call_orchestrator.py assistant_policy.py assistant_capability_catalog.py
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
.venv/bin/python test_assistant_capability_catalog.py 2>&1 | tee "$EVIDENCE/capability-tests.txt" || \
  .venv/bin/python - <<'PY' | tee "$EVIDENCE/capability-tests.txt"
import test_assistant_capability_catalog as t
t.test_capability_matrix_hides_denied_and_unconfigured()
t.test_capability_matrix_marks_provider_not_configured()
t.test_module_off_hides_assessments()
t.test_reports_policy_classifiers()
t.test_capability_prompt_block_lists_statuses()
print("capability unit PASS")
PY

.venv/bin/python smoke-test-toolcall-orchestrator.py 2>&1 | tee "$EVIDENCE/toolcall-smoke.txt"

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
# shellcheck disable=SC1091
source /root/.openclaw/secrets/voyage.env || true
set +a
export WATHEFNI_ENV=production
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env

.venv/bin/python "$EVIDENCE/prove-assistant-copilot-live.py" 2>&1 | tee "$EVIDENCE/live-proof.jsonl"
# Also write structured JSON if the prover emits a final JSON line
tail -n 1 "$EVIDENCE/live-proof.jsonl" > "$EVIDENCE/live-proof.json" || true

# Asset markers from dashboard
python3 - <<'PY' | tee "$EVIDENCE/asset-markers.json"
import json, pathlib, re
root = pathlib.Path("/var/www/wathefni-dashboard/assets")
text = ""
for p in root.glob("AdminAIPage-*.js"):
    text += p.read_text(errors="ignore")
markers = {
    "assistant_profiler": "assistant:" in text or "dashboardPerfMarkProfilerCommit" in text,
    "rtl_dir": "rtl" in text,
    "overlay_a11y": "aria-modal" in text,
    "workflow_card": "workflowCard" in text or "WorkflowCard" in text,
    "stop_control": "onCancel" in text or "Stop" in text,
    "files": sorted(p.name for p in root.glob("AdminAIPage-*.js")),
}
print(json.dumps(markers, indent=2))
PY
REMOTE

log "fetch evidence"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVIDENCE/" "$LOCAL_EVIDENCE/"
"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_after_local.txt"

log "done stamp=$STAMP backup=$REMOTE_BACKUP evidence=$LOCAL_EVIDENCE"
