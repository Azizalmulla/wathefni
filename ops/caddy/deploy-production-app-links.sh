#!/usr/bin/env bash
# Mount HTTPS app-link routes on the production orchestrator without replacing app.py.
# Copies app_links.py and appends include_router only if missing, then restarts :8010.
set -euo pipefail
VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID="$REPO_ROOT/ops/evidence/store-release-prod-app-links-$STAMP"
mkdir -p "$EVID"

rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "$ORCH_SRC/app_links.py" "$VPS_HOST:/tmp/app_links.py"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$EVID/deploy.out"
set -euo pipefail
PROD=/opt/wathefni/orchestrator
cp -a "\$PROD/app.py" "\$PROD/app.py.bak-app-links-$STAMP"
cp -a /tmp/app_links.py "\$PROD/app_links.py"
python3 -m py_compile "\$PROD/app_links.py"
if ! grep -q 'import app_links' "\$PROD/app.py"; then
  cat >> "\$PROD/app.py" <<'PY'

try:
    import app_links as _app_links
    app.include_router(_app_links.router)
except Exception as _app_links_exc:
    import logging as _logging
    _logging.getLogger("wathefni").warning("app_links router not mounted: %s", _app_links_exc)
PY
fi
python3 -m py_compile "\$PROD/app.py"
systemctl restart wathefni-orchestrator
S=000
for i in \$(seq 1 20); do
  sleep 6
  S=\$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  [ "\$S" = "200" ] && break
done
echo "prod_health=\$S"
[ "\$S" = "200" ] || { echo PROD_HEALTH_FAIL; exit 1; }
R=\$(curl -s -o /tmp/prod-ready.json -w "%{http_code}" http://127.0.0.1:8010/ready || true)
echo "prod_local_ready=\$R"
L=\$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/l/leave || true)
echo "prod_local_leave=\$L"
A=\$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/.well-known/apple-app-site-association || true)
echo "prod_local_aasa=\$A"
echo PROD_APP_LINKS_LIVE
REMOTE

echo "EVIDENCE=$EVID"
