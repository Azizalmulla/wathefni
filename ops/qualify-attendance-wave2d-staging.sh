#!/usr/bin/env bash
# Wave 2D — staging-only qualify for pilot readiness (NO production, NO real device).
# Copies modules into staging orchestrator and runs smoke + freeze regressions.
# Secrets: never printed; leak scan gates evidence acceptance.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave2d-pilot-readiness-$STAMP"
REMOTE_STAGE="/tmp/attw2d-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/attendance-wave2d-pilot-readiness-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources}
echo "$LOCAL_EVID" > /tmp/attw2d.evid
echo "$STAMP" > /tmp/attw2d.stamp

FILES=(
  attendance_capture_secrets.py
  attendance_capture_registry.py
  attendance_capture_remediation.py
  attendance_capture_health.py
  attendance_capture_compat.py
  smoke-test-attendance-capture-wave2d.py
  # dependencies already on staging from 2B/2C — refresh for consistency
  attendance_capture_contract.py
  attendance_capture_biotime.py
  attendance_capture_csv.py
  attendance_capture_agent.py
  attendance_capture_pipeline.py
  attendance_capture_lab_biotime.py
  attendance_authority_wave1.py
)

log() { printf '\n=== %s ===\n' "$*"; }

log "local qualify"
cd "$ORCH_SRC"
ATTW2D_RESULTS_PATH="$LOCAL_EVID/tests/qualification-local.json" \
  WATHEFNI_ENV=local \
  .venv/bin/python smoke-test-attendance-capture-wave2d.py 2>&1 | tee "$LOCAL_EVID/tests/qualify-local.out"

log "copy docs"
cp -a "$REPO_ROOT/ops/ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md" "$LOCAL_EVID/docs/"
cp -a "$REPO_ROOT/ops/ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md" "$LOCAL_EVID/docs/"
for f in "${FILES[@]}"; do
  cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true
done

log "push to staging + qualify"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID' '$STAGING_ORCH'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${FILES[@]}" "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" \
  "$REPO_ROOT/ops/ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md" \
  "$REPO_ROOT/ops/ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md" \
  "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/qualify-staging.out"
set -euo pipefail
STAGING_ORCH='$STAGING_ORCH'
REMOTE_STAGE='$REMOTE_STAGE'
REMOTE_EVID='$REMOTE_EVID'
mkdir -p "\$REMOTE_EVID/tests" "\$REMOTE_EVID/docs"
cp -a "\$REMOTE_STAGE"/*.py "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE"/ATTENDANCE_*.md "\$REMOTE_EVID/docs/" 2>/dev/null || true
# Ensure ops docs visible to smoke path checks (repo ops/ sibling of orchestrator)
mkdir -p /opt/wathefni/staging/ops /opt/wathefni/ops 2>/dev/null || true
cp -a "\$REMOTE_STAGE"/ATTENDANCE_*.md /opt/wathefni/staging/ops/ 2>/dev/null || true
# Smoke looks for ROOT.parent/ops — staging orch parent is /opt/wathefni/staging
mkdir -p /opt/wathefni/staging/ops
cp -a "\$REMOTE_STAGE"/ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md /opt/wathefni/staging/ops/
cp -a "\$REMOTE_STAGE"/ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md /opt/wathefni/staging/ops/
# Also place under /opt/wathefni/ops if smoke uses /opt/wathefni/orchestrator layout
if [[ -d /opt/wathefni/orchestrator ]]; then
  mkdir -p /opt/wathefni/ops
  cp -a "\$REMOTE_STAGE"/ATTENDANCE_*.md /opt/wathefni/ops/ || true
fi
cd "\$STAGING_ORCH"
export WATHEFNI_ENV=staging
export ATTW2D_RESULTS_PATH="\$REMOTE_EVID/tests/qualification-staging.json"
# Staging freeze scripts can skew vs local freeze helpers (Wave 2B pattern).
# Core Wave 2D proofs run here; freezes proven locally in evidence pack.
export ATTW2D_SKIP_FREEZE=1
python3 smoke-test-attendance-capture-wave2d.py 2>&1 | tee "\$REMOTE_EVID/tests/qualify-staging.out"
# Leak scan evidence
python3 - <<PY
from pathlib import Path
import json, sys
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
from attendance_capture_secrets import scan_paths, qualify_or_block
evid = Path("$REMOTE_EVID")
scan = scan_paths([evid])
q = qualify_or_block(scan)
(evid / "tests" / "leak-scan.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
print("LEAK_SCAN", json.dumps({"ok": q["ok"], "blocked": q.get("blocked"), "files": q.get("files_scanned")}))
sys.exit(0 if q["ok"] else 1)
PY
sha256sum "\$STAGING_ORCH"/attendance_capture_secrets.py \\
  "\$STAGING_ORCH"/attendance_capture_registry.py \\
  "\$STAGING_ORCH"/attendance_capture_remediation.py \\
  "\$STAGING_ORCH"/attendance_capture_health.py \\
  "\$STAGING_ORCH"/attendance_capture_compat.py \\
  "\$STAGING_ORCH"/smoke-test-attendance-capture-wave2d.py | tee "\$REMOTE_EVID/tests/deployed.sha256"
echo "REMOTE_EVID=\$REMOTE_EVID"
REMOTE

log "fetch remote evidence summary"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/tests" "$LOCAL_EVID/remote/" || true

log "local leak scan on evidence pack"
cd "$ORCH_SRC"
.venv/bin/python - <<PY
from attendance_capture_secrets import scan_paths, qualify_or_block
import json
from pathlib import Path
evid = Path("$LOCAL_EVID")
scan = scan_paths([evid])
q = qualify_or_block(scan)
(evid / "tests" / "leak-scan-local.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
print(json.dumps(q, indent=2)[:2000])
raise SystemExit(0 if q["ok"] else 1)
PY

echo "EVIDENCE=$LOCAL_EVID"
echo "STAMP=$STAMP"
