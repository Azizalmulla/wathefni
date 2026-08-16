#!/usr/bin/env bash
# Deploy Reports correctness contract (orchestrator + dashboard).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_DIST="$REPO_ROOT/apps/wathefni-dashboard/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-reports-correctness-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/reports-correctness/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/reports-correctness-$STAMP"
PROD_ORCH=/opt/wathefni/orchestrator
PROD_DASH=/var/www/wathefni-dashboard
REMOTE_TMP="/tmp/reports-correctness-$STAMP"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "stamp=$STAMP"
mkdir -p "$LOCAL_EVIDENCE"
echo "$STAMP" > "$LOCAL_EVIDENCE/STAMP.txt"
echo "$REMOTE_BACKUP" > "$LOCAL_EVIDENCE/BACKUP_PATH.txt"
test -d "$DASH_DIST" || { echo "missing dist"; exit 1; }

"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_before.txt"

log "backup $REMOTE_BACKUP"
"${SSH[@]}" "STAMP='$STAMP' BACKUP='$REMOTE_BACKUP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$BACKUP/dashboard-dist"
for f in app.py reports_metrics.py reports_v1.py; do
  cp -a "$ORCH/$f" "$BACKUP/$f.pre"
done
if [ -f "$ORCH/test_reports_metrics_contract.py" ]; then
  cp -a "$ORCH/test_reports_metrics_contract.py" "$BACKUP/test_reports_metrics_contract.py.pre"
else
  touch "$BACKUP/test_reports_metrics_contract.py.MISSING"
fi
rsync -a "$DASH/" "$BACKUP/dashboard-dist/"
cat > "$BACKUP/ROLLBACK.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "\$ROOT/app.py.pre" "\$ORCH/app.py"
cp -a "\$ROOT/reports_metrics.py.pre" "\$ORCH/reports_metrics.py"
cp -a "\$ROOT/reports_v1.py.pre" "\$ORCH/reports_v1.py"
if [ -f "\$ROOT/test_reports_metrics_contract.py.pre" ]; then
  cp -a "\$ROOT/test_reports_metrics_contract.py.pre" "\$ORCH/test_reports_metrics_contract.py"
elif [ -f "\$ROOT/test_reports_metrics_contract.py.MISSING" ]; then
  rm -f "\$ORCH/test_reports_metrics_contract.py"
fi
rsync -a --delete "\$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl restart wathefni-orchestrator.service
sleep 3
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_health=%{http_code}\\n" http://127.0.0.1:8010/health
echo "Rolled back reports correctness ${STAMP}"
EOF
chmod 755 "$BACKUP/ROLLBACK.sh"
echo "$BACKUP"
REMOTE

# Extract reports route handlers from local app.py for surgical patch
python3 <<'PY'
from pathlib import Path
import re
text = Path("/Users/azizalmulla/Desktop/claw/wathefni-orchestrator/app.py").read_text()
# Capture from dashboard_prehire_reports through end of dashboard_prehire_report_export
m = re.search(
    r'@app\.get\("/dashboard/prehire/reports"\)\ndef dashboard_prehire_reports\([\s\S]*?\n(?=@app\.get\("/dashboard/prehire/audit"\))',
    text,
)
if not m:
    raise SystemExit('reports routes not found')
Path('/tmp/patch-dashboard_prehire_reports.py').write_text(m.group(0))
print('route_chars', len(m.group(0)))
PY

log "upload"
"${SSH[@]}" "mkdir -p $REMOTE_TMP/dashboard-dist $REMOTE_EVIDENCE"
"${SCP[@]}" \
  "$ORCH_SRC/reports_metrics.py" \
  "$ORCH_SRC/reports_v1.py" \
  "$ORCH_SRC/test_reports_metrics_contract.py" \
  /tmp/patch-dashboard_prehire_reports.py \
  "$SCRIPT_DIR/prove-reports-correctness-live.py" \
  "$VPS_HOST:$REMOTE_TMP/"
rsync -az -e "ssh -o BatchMode=yes" "$DASH_DIST/" "$VPS_HOST:$REMOTE_TMP/dashboard-dist/"

log "apply"
"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' EVIDENCE='$REMOTE_EVIDENCE' bash -s" <<'REMOTE'
set -euo pipefail
cp -a "$TMP/reports_metrics.py" "$ORCH/reports_metrics.py"
cp -a "$TMP/reports_v1.py" "$ORCH/reports_v1.py"
cp -a "$TMP/test_reports_metrics_contract.py" "$ORCH/test_reports_metrics_contract.py"
cp -a "$TMP/prove-reports-correctness-live.py" "$EVIDENCE/"

python3 <<'PY'
from pathlib import Path
import re, os
tmp = Path(os.environ["TMP"])
orch = Path("/opt/wathefni/orchestrator/app.py")
text = orch.read_text()
route = (tmp / "patch-dashboard_prehire_reports.py").read_text()
if not route.endswith("\n"):
    route += "\n"
rm = re.search(
    r'@app\.get\("/dashboard/prehire/reports"\)\ndef dashboard_prehire_reports\([\s\S]*?\n(?=@app\.get\("/dashboard/prehire/audit"\))',
    text,
)
if not rm:
    raise SystemExit("prod reports routes not found")
text = text[: rm.start()] + route + text[rm.end() :]
compile(text, str(orch), "exec")
orch.write_text(text)
print("app.py reports routes patched")
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
.venv/bin/python -m unittest test_reports_metrics_contract -v 2>&1 | tee "$EVIDENCE/unit-tests.txt"

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
# shellcheck disable=SC1091
source /root/.openclaw/secrets/voyage.env
set +a
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
"$ORCH/.venv/bin/python" "$EVIDENCE/prove-reports-correctness-live.py" "$EVIDENCE/live-proof.json" | tee "$EVIDENCE/live-proof-summary.json"

# Asset markers
python3 <<'PY'
import json, os, re
from pathlib import Path
dash = Path("/var/www/wathefni-dashboard")
joined = "\n".join(p.read_text(errors="ignore") for p in (dash / "assets").glob("*.js"))
proof = {
    "has_interview_debt_label": "Candidates needing interview scheduling" in joined,
    "has_ar_interview_debt": "مرشحون يحتاجون جدولة مقابلة" in joined,
    "has_active_by_role": "Active applications by role" in joined,
    "no_interviews_needing_action": "Interviews needing action" not in joined,
    "has_profiler_marks": all(m in joined for m in ("reports_page_load", "reports_refresh", "reports_export", "reports:")),
    "has_rtl": "dir" in joined and "rtl" in joined,
}
Path(os.environ["EVIDENCE"]).joinpath("asset-markers.json").write_text(json.dumps(proof, indent=2) + "\n")
print(json.dumps(proof, indent=2))
fails = [k for k, v in proof.items() if k.startswith("has_") and not v]
fails += [k for k, v in proof.items() if k.startswith("no_") and not v]
if fails:
    raise SystemExit(f"asset marker fail: {fails}")
PY
REMOTE

"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/live-proof.json" "$LOCAL_EVIDENCE/live-proof.json"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/live-proof-summary.json" "$LOCAL_EVIDENCE/live-proof-summary.json" || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/asset-markers.json" "$LOCAL_EVIDENCE/asset-markers.json"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/health_after.txt" "$LOCAL_EVIDENCE/health_after.txt"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVIDENCE/unit-tests.txt" "$LOCAL_EVIDENCE/unit-tests.txt"

log "done stamp=$STAMP"
cat "$LOCAL_EVIDENCE/live-proof-summary.json" 2>/dev/null || cat "$LOCAL_EVIDENCE/live-proof.json"
