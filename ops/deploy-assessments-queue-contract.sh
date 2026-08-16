#!/usr/bin/env bash
# Deploy Assessments consistency contract to production (exact files only).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_DIST="$REPO_ROOT/apps/wathefni-dashboard/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-assessments-queue-contract-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/assessments-queue-contract/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/assessments-queue-contract-$STAMP"
PROD_ORCH="/opt/wathefni/orchestrator"
PROD_DASH="/var/www/wathefni-dashboard"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "stamp=$STAMP"
mkdir -p "$LOCAL_EVIDENCE"

# Health before
"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_before.txt"

# Backup
log "backing up to $REMOTE_BACKUP"
"${SSH[@]}" "STAMP='$STAMP' BACKUP='$REMOTE_BACKUP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$BACKUP/dashboard-dist"
for f in assessment_cohorts.py assessment_presentation.py prehire_overview.py app.py; do
  cp -a "$ORCH/$f" "$BACKUP/$f.pre"
done
if [ -f "$ORCH/assessments_queue_contract.py" ]; then
  cp -a "$ORCH/assessments_queue_contract.py" "$BACKUP/assessments_queue_contract.py.pre"
else
  touch "$BACKUP/assessments_queue_contract.py.MISSING"
fi
if [ -f "$ORCH/test_assessments_queue_contract.py" ]; then
  cp -a "$ORCH/test_assessments_queue_contract.py" "$BACKUP/test_assessments_queue_contract.py.pre"
else
  touch "$BACKUP/test_assessments_queue_contract.py.MISSING"
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
for f in assessment_cohorts.py assessment_presentation.py prehire_overview.py; do
  cp -a "$ROOT/$f.pre" "$ORCH/$f"
done
if [ -f "$ROOT/assessments_queue_contract.py.pre" ]; then
  cp -a "$ROOT/assessments_queue_contract.py.pre" "$ORCH/assessments_queue_contract.py"
elif [ -f "$ROOT/assessments_queue_contract.py.MISSING" ]; then
  rm -f "$ORCH/assessments_queue_contract.py"
fi
if [ -f "$ROOT/test_assessments_queue_contract.py.pre" ]; then
  cp -a "$ROOT/test_assessments_queue_contract.py.pre" "$ORCH/test_assessments_queue_contract.py"
elif [ -f "$ROOT/test_assessments_queue_contract.py.MISSING" ]; then
  rm -f "$ORCH/test_assessments_queue_contract.py"
fi
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl restart wathefni-orchestrator.service
sleep 3
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_health=%{{http_code}}\\n" http://127.0.0.1:8010/health
echo "Rolled back assessments queue contract {stamp}"
""")
path.chmod(0o755)
print(path.parent)
PY
REMOTE

# Upload modules + patches + proof + dist
log "uploading modules"
REMOTE_TMP="/tmp/assessments-queue-contract-$STAMP"
"${SSH[@]}" "mkdir -p $REMOTE_TMP"
"${SCP[@]}" \
  "$ORCH_SRC/assessments_queue_contract.py" \
  "$ORCH_SRC/assessment_cohorts.py" \
  "$ORCH_SRC/assessment_presentation.py" \
  "$ORCH_SRC/prehire_overview.py" \
  "$ORCH_SRC/test_assessments_queue_contract.py" \
  /tmp/patch-dashboard_assessments_payload.py \
  /tmp/patch-dashboard_prehire_assessments.py \
  "$SCRIPT_DIR/prove-assessments-queue-contract-live.py" \
  "$VPS_HOST:$REMOTE_TMP/"

log "uploading dashboard dist"
"${SSH[@]}" "mkdir -p $REMOTE_TMP/dashboard-dist"
rsync -az -e "ssh -o BatchMode=yes" "$DASH_DIST/" "$VPS_HOST:$REMOTE_TMP/dashboard-dist/"

# Apply on server
log "applying on production"
"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' EVIDENCE='$REMOTE_EVIDENCE' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$EVIDENCE"

cp -a "$TMP/assessments_queue_contract.py" "$ORCH/assessments_queue_contract.py"
cp -a "$TMP/assessment_cohorts.py" "$ORCH/assessment_cohorts.py"
cp -a "$TMP/assessment_presentation.py" "$ORCH/assessment_presentation.py"
cp -a "$TMP/prehire_overview.py" "$ORCH/prehire_overview.py"
cp -a "$TMP/test_assessments_queue_contract.py" "$ORCH/test_assessments_queue_contract.py"
cp -a "$TMP/prove-assessments-queue-contract-live.py" "$EVIDENCE/prove-assessments-queue-contract-live.py"

python3 <<PY
from pathlib import Path
import re
import os

tmp = Path(os.environ["TMP"])
orch = Path("/opt/wathefni/orchestrator/app.py")
text = orch.read_text()
fn = (tmp / "patch-dashboard_assessments_payload.py").read_text()
if not fn.endswith("\n"):
    fn += "\n"
route = (tmp / "patch-dashboard_prehire_assessments.py").read_text()
if not route.endswith("\n"):
    route += "\n"

m = re.search(r"\ndef dashboard_assessments_payload\(", text)
if not m:
    raise SystemExit("dashboard_assessments_payload not found")
rest = text[m.end():]
m2 = re.search(r"\ndef dashboard_", rest)
if not m2:
    raise SystemExit("next dashboard_ def not found")
start = m.start() + 1
end = m.end() + m2.start()
text = text[:start] + fn + text[end:]

rm = re.search(
    r'@app\.get\("/dashboard/prehire/assessments"\)\ndef dashboard_prehire_assessments\([\s\S]*?return payload\n',
    text,
)
if not rm:
    raise SystemExit("assessments route not found")
text = text[:rm.start()] + route + text[rm.end():]

old = '''    overview = _prehire_overview.build_overview_authority(
        company=company,
        db_connect=db_connect,
        get_company_settings=get_company_settings,
        assessments_enabled=assessments_enabled,
        interviews_enabled="interviews" in enabled_modules,
    )'''
new = '''    overview = _prehire_overview.build_overview_authority(
        company=company,
        db_connect=db_connect,
        get_company_settings=get_company_settings,
        assessments_enabled=assessments_enabled,
        interviews_enabled="interviews" in enabled_modules,
        visibility_sql=detail_vis_sql or None,
        visibility_params=detail_vis_params or None,
    )'''
if old in text:
    text = text.replace(old, new, 1)
    print("overview_visibility_patched=1")
elif "visibility_sql=detail_vis_sql or None" in text and "build_overview_authority" in text:
    print("overview_visibility_already=1")
else:
    print("overview_visibility_patched=0")

orch.write_text(text)
print("app.py patched ok")
PY

rsync -a --delete "$TMP/dashboard-dist/" "$DASH/"
systemctl restart wathefni-orchestrator.service
sleep 4
systemctl reload caddy || true
curl -sS -o /dev/null -w "health_after=%{http_code}\n" http://127.0.0.1:8010/health | tee "$EVIDENCE/health_after.txt"

cd "$ORCH"
python3 -m unittest test_assessments_queue_contract -v 2>&1 | tee "$EVIDENCE/unit-tests.txt"

python3 "$EVIDENCE/prove-assessments-queue-contract-live.py" "$EVIDENCE/live-proof.json" | tee "$EVIDENCE/live-proof-summary.json"
python3 - <<PY
import json
from pathlib import Path
import os
p = Path(os.environ["EVIDENCE"]) / "live-proof.json"
data = json.loads(p.read_text())
print("LIVE_VERDICT", data.get("verdict"))
raise SystemExit(0 if data.get("verdict") == "PASS" else 1)
PY
REMOTE

# Pull evidence
mkdir -p "$LOCAL_EVIDENCE"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVIDENCE/"* "$LOCAL_EVIDENCE/" || true
echo "$STAMP" > "$LOCAL_EVIDENCE/STAMP.txt"
echo "$REMOTE_BACKUP" > "$LOCAL_EVIDENCE/BACKUP_PATH.txt"
log "done evidence=$LOCAL_EVIDENCE backup=$REMOTE_BACKUP"
