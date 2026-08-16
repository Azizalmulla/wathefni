#!/usr/bin/env bash
# Apply the production Caddyfile so /ready and /health reach the orchestrator.
# Backs up the live file first. Reloads Caddy only after `caddy validate`.
set -euo pipefail
VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/api.wathefni.ai.Caddyfile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

rsync -az -e "ssh -o BatchMode=yes -o ConnectTimeout=30" "$SRC" "$VPS_HOST:/tmp/api.wathefni.ai.Caddyfile"

"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
STAMP='$STAMP'
cp -a /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak-store-ready-\$STAMP
cp -a /tmp/api.wathefni.ai.Caddyfile /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
echo CADDY_RELOAD_OK
REMOTE

echo "Caddy applied. Probing public /ready..."
curl -sS -o /tmp/prod-ready.json -w "prod_ready=%{http_code}\n" --max-time 20 https://api.wathefni.ai/ready
python3 - <<'PY'
import json, pathlib
p=pathlib.Path("/tmp/prod-ready.json")
print(p.read_text()[:400] if p.exists() else "no body")
PY
curl -sS -o /dev/null -w "prod_health=%{http_code}\n" --max-time 20 https://api.wathefni.ai/health
