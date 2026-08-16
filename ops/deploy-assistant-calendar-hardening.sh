#!/usr/bin/env bash
# Deploy Assistant calendar hardening (schedule→interview_service + Microsoft wiring + cancel reconciliation).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-assistant-calendar-hardening-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/assistant-calendar-hardening/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/assistant-calendar-hardening-$STAMP"
PROD_ORCH=/opt/wathefni/orchestrator
REMOTE_TMP="/tmp/assistant-calendar-hardening-$STAMP"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "stamp=$STAMP"
mkdir -p "$LOCAL_EVIDENCE"
echo "$STAMP" > "$LOCAL_EVIDENCE/STAMP.txt"
echo "$REMOTE_BACKUP" > "$LOCAL_EVIDENCE/BACKUP_PATH.txt"

"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_before.txt"

log "backup"
"${SSH[@]}" "STAMP='$STAMP' BACKUP='$REMOTE_BACKUP' ORCH='$PROD_ORCH' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$BACKUP"
for f in action_registry.py tool_call_orchestrator.py interview_service.py interview_lifecycle.py assistant_capability_catalog.py; do
  cp -a "$ORCH/$f" "$BACKUP/$f.pre"
done
for f in interview_microsoft_calendar.py test_assistant_calendar_hardening.py; do
  if [ -f "$ORCH/$f" ]; then cp -a "$ORCH/$f" "$BACKUP/$f.pre"; else touch "$BACKUP/$f.MISSING"; fi
done
cat > "$BACKUP/ROLLBACK.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
for f in action_registry.py tool_call_orchestrator.py interview_service.py interview_lifecycle.py assistant_capability_catalog.py; do
  cp -a "\$ROOT/\$f.pre" "\$ORCH/\$f"
done
for f in interview_microsoft_calendar.py test_assistant_calendar_hardening.py; do
  if [ -f "\$ROOT/\$f.pre" ]; then cp -a "\$ROOT/\$f.pre" "\$ORCH/\$f"
  elif [ -f "\$ROOT/\$f.MISSING" ]; then rm -f "\$ORCH/\$f"; fi
done
systemctl restart wathefni-orchestrator.service
sleep 3
curl -sS -o /dev/null -w "rollback_health=%{http_code}\\n" http://127.0.0.1:8010/health
EOF
chmod 755 "$BACKUP/ROLLBACK.sh"
echo "$BACKUP"
REMOTE

log "upload+apply"
"${SSH[@]}" "mkdir -p $REMOTE_TMP $REMOTE_EVIDENCE"
"${SCP[@]}" \
  "$ORCH_SRC/action_registry.py" \
  "$ORCH_SRC/tool_call_orchestrator.py" \
  "$ORCH_SRC/interview_service.py" \
  "$ORCH_SRC/interview_lifecycle.py" \
  "$ORCH_SRC/assistant_capability_catalog.py" \
  "$ORCH_SRC/interview_microsoft_calendar.py" \
  "$ORCH_SRC/test_assistant_calendar_hardening.py" \
  "$ORCH_SRC/prove-m365-live-calendar.py" \
  "$VPS_HOST:$REMOTE_TMP/"

"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' EVIDENCE='$REMOTE_EVIDENCE' bash -s" <<'REMOTE'
set -euo pipefail
for f in action_registry.py tool_call_orchestrator.py interview_service.py interview_lifecycle.py assistant_capability_catalog.py interview_microsoft_calendar.py test_assistant_calendar_hardening.py prove-m365-live-calendar.py; do
  cp -a "$TMP/$f" "$ORCH/$f"
done
cd "$ORCH"
.venv/bin/python -m py_compile action_registry.py tool_call_orchestrator.py interview_service.py interview_lifecycle.py assistant_capability_catalog.py interview_microsoft_calendar.py
systemctl restart wathefni-orchestrator.service
for i in 1 2 3 4 5 6 7 8; do
  sleep 2
  code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  echo "health_try_$i=$code"
  if [ "$code" = "200" ]; then break; fi
done
echo "$code" | tee "$EVIDENCE/health_after.txt"
test "$code" = "200"

.venv/bin/python test_assistant_calendar_hardening.py 2>&1 | tee "$EVIDENCE/unit-tests.txt"
.venv/bin/python smoke-test-toolcall-orchestrator.py 2>&1 | tee "$EVIDENCE/toolcall-smoke.txt"

# Microsoft propagation re-check (expected fail until RBAC assignment succeeds)
set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/wathefni-m365.production.env
set +a
export WATHEFNI_M365_CERT_BUNDLE_PATH=/root/.openclaw/secrets/wathefni-m365.bundle.pem
export C6B_EVID="$EVIDENCE/m365-live"
mkdir -p "$C6B_EVID"
.venv/bin/python prove-m365-live-calendar.py 2>&1 | tee "$EVIDENCE/m365-live-run.log" || true
cp -a "$C6B_EVID/m365-live-calendar-results.json" "$EVIDENCE/m365-live-calendar-results.json" 2>/dev/null || true

# Schedule path proof (source contract on prod)
.venv/bin/python - <<'PY' | tee "$EVIDENCE/schedule-authority.json"
import json, inspect, action_registry as r, interview_service as s
out = {
  "schedule_uses_interview_service": "interview_service" in inspect.getsource(r._schedule_interview_executor),
  "schedule_no_run_gog": "run_gog" not in inspect.getsource(r._schedule_interview_executor),
  "microsoft_sync_wired": hasattr(s, "_sync_microsoft_for_interview"),
  "meeting_types_include_teams": "microsoft_teams" in __import__("interview_lifecycle").MEETING_TYPES,
}
print(json.dumps(out, indent=2))
PY
REMOTE

rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVIDENCE/" "$LOCAL_EVIDENCE/"
log "done stamp=$STAMP evidence=$LOCAL_EVIDENCE"
