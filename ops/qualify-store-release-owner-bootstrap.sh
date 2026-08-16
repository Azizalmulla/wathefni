#!/usr/bin/env bash
# Stage Setup owner-bootstrap + HTTPS app-link routes, restart staging, run clean canary.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/store-release-owner-bootstrap-$STAMP"
REMOTE_STAGE="/tmp/store-release-owner-bootstrap-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,sources,live}
if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  setup_owner_bootstrap.py
  app_links.py
  setup_console_operator_auth.py
  smoke-test-setup-owner-bootstrap.py
  smoke-test-app-links.py
)

echo "== local bootstrap + app-link units =="
"$PY" "$ORCH_SRC/smoke-test-setup-owner-bootstrap.py" | tee "$LOCAL_EVID/tests/bootstrap-unit.out"
"$PY" "$ORCH_SRC/smoke-test-app-links.py" | tee "$LOCAL_EVID/tests/app-links-unit.out"

for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG='$STG'
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
python3 -m py_compile "\$STG/app.py" "\$STG/setup_owner_bootstrap.py" "\$STG/app_links.py" "\$STG/setup_console_operator_auth.py"
echo STAGING_COPY_OK
REMOTE

echo "== restart staging =="
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/restart.out"
set -euo pipefail
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
S=000
for i in $(seq 1 20); do
  sleep 6
  S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health || true)
  [ "$S" = "200" ] && break
done
echo "staging_health=$S"
[ "$S" = "200" ] || { echo LIVE_HEALTH_FAIL; exit 1; }
R=$(curl -s -o /tmp/boot-ready.json -w "%{http_code}" http://127.0.0.1:8011/ready || true)
echo "staging_ready=$R"
[ "$R" = "200" ] || { echo LIVE_READY_FAIL; exit 1; }
L=$(curl -s -o /tmp/boot-leave.html -w "%{http_code}" http://127.0.0.1:8011/l/leave || true)
echo "staging_app_link_leave=$L"
REG=$(curl -s -o /tmp/boot-registry.json -w "%{http_code}" http://127.0.0.1:8011/l/registry.json || true)
echo "staging_app_link_registry=$REG"
AASA=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/.well-known/apple-app-site-association || true)
echo "staging_aasa=$AASA"
python3 - <<'PY'
import json
body = json.load(open("/tmp/boot-ready.json"))
print("ready_status", body.get("status"))
if body.get("status") != "ready":
    raise SystemExit("ready_not_ready")
reg = json.load(open("/tmp/boot-registry.json"))
print("destinations", len(reg.get("destinations") or []))
if not reg.get("destinations"):
    raise SystemExit("app_link_registry_empty")
PY
echo LIVE_OK
REMOTE

echo "== clean canary =="
bash "$REPO_ROOT/ops/qualify-store-release-clean-canary.sh" | tee "$LOCAL_EVID/tests/clean-canary.out"
echo "EVIDENCE=$LOCAL_EVID"
