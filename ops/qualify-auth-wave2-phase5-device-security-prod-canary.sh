#!/usr/bin/env bash
# Auth Wave 2 Phase 5 — surgical production canary deploy (app.py + dashboard).
# Additive device-security routes only. No Phase 6. Rollback = restore app.py.bak.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID="$ROOT/ops/evidence/auth-wave2-phase5-device-security-$STAMP"
REMOTE_BAK="/opt/wathefni/backups/production-pre-auth-wave2-phase5-$STAMP"
REMOTE_EVID="/opt/wathefni/production-evidence/auth-wave2-phase5/$STAMP"

mkdir -p "$EVID"/{deploy,prove,mobile,docs,dashboard}
printf '%s\n' "$EVID" > /tmp/p5_evid.txt
printf '%s\n' "$STAMP" > /tmp/p5_stamp.txt

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }

log "local unit"
python3 "$ORCH/smoke-test-auth-wave2-phase5-device-security-unit.py" | tee "$EVID/prove/unit.txt"

log "build dashboard"
(
  cd "$DASH"
  npm run build
) | tee "$EVID/dashboard/build.txt"

log "remote backup + stage"
"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
mkdir -p '$REMOTE_BAK' '$REMOTE_EVID'/{preflight,verify}
cp -a /opt/wathefni/orchestrator/app.py '$REMOTE_BAK/app.py'
if [ -d /var/www/wathefni-dashboard ]; then
  tar -C /var/www/wathefni-dashboard -czf '$REMOTE_BAK/dashboard-www.tgz' . || true
fi
{
  echo stamp=$STAMP
  systemctl is-active wathefni-orchestrator
  sha256sum /opt/wathefni/orchestrator/app.py
  curl -sS -o /dev/null -w 'health:%{http_code}\n' http://127.0.0.1:8000/health || true
} | tee '$REMOTE_EVID/preflight/before.txt'
REMOTE

log "push app.py"
"${SCP[@]}" "$ORCH/app.py" "$VPS_HOST:/opt/wathefni/orchestrator/app.py"
"${SCP[@]}" "$ORCH/smoke-test-auth-wave2-phase5-device-security-unit.py" "$VPS_HOST:/opt/wathefni/orchestrator/"

log "compile + restart"
"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
cd /opt/wathefni/orchestrator
./.venv/bin/python -m py_compile app.py
echo py_compile_ok | tee '$REMOTE_EVID/verify/py_compile.txt'
systemctl restart wathefni-orchestrator
sleep 2
systemctl is-active wathefni-orchestrator
curl -sS -o /dev/null -w 'health:%{http_code}\n' http://127.0.0.1:8010/health || true
# Unauth device-security must not 404 (auth dependency → 401/403)
code=$(curl -sS -o /tmp/p5-ds.json -w '%{http_code}' http://127.0.0.1:8010/app/device-security || true)
echo "device_security_http=$code"
head -c 300 /tmp/p5-ds.json; echo
test "$code" != "404"
# HR app-access route exists (401/403 without dash session — not 404)
code2=$(curl -sS -o /tmp/p5-hr.json -w '%{http_code}' http://127.0.0.1:8010/dashboard/posthire/employees/WATHEFNI-96599338566/app-access || true)
echo "app_access_http=$code2"
test "$code2" != "404"
{
  echo stamp=$STAMP
  sha256sum /opt/wathefni/orchestrator/app.py
  echo device_security_http=\$code
  echo app_access_http=\$code2
} | tee '$REMOTE_EVID/verify/after.txt'
REMOTE

log "push dashboard dist"
rsync -az --delete -e "ssh -o BatchMode=yes" "$DASH/dist/" "$VPS_HOST:/var/www/wathefni-dashboard/"
"${SSH[@]}" "sha256sum /var/www/wathefni-dashboard/index.html | tee '$REMOTE_EVID/verify/dashboard-index.sha256'"

# Pull remote verify locally
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/verify/after.txt" "$EVID/deploy/after.txt" || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/preflight/before.txt" "$EVID/deploy/before.txt" || true

# Public edge check
{
  echo "public_device_security=$(curl -sS -o /tmp/p5-pub.json -w '%{http_code}' https://api.wathefni.ai/app/device-security || true)"
  head -c 200 /tmp/p5-pub.json; echo
} | tee "$EVID/deploy/public-edge.txt"

cp "$ROOT/ops/AUTH_WAVE2_PHASE5_DEVICE_SECURITY_CONTRACT.md" "$EVID/docs/"
echo "EVID=$EVID"
echo "REMOTE_BAK=$REMOTE_BAK"
echo "PHASE5_DEPLOY_OK"
