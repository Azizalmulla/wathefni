#!/usr/bin/env bash
# Live store-build checks that the local config gate cannot see.
set -euo pipefail
VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID="$REPO_ROOT/ops/evidence/store-build-live-$STAMP"
mkdir -p "$EVID/live"
if [[ -x "$REPO_ROOT/wathefni-orchestrator/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/wathefni-orchestrator/.venv/bin/python"
else
  PY="$(command -v python3)"
fi

"$PY" "$REPO_ROOT/ops/store-build-gate.py" 2>&1 | tee "$EVID/store-build-gate.out"

{
  echo "== staging /health /ready =="
  "${SSH[@]}" 'curl -sS -o /tmp/store-ready.json -w "staging_health=%{http_code}\n" http://127.0.0.1:8011/health; curl -sS -o /tmp/store-ready.json -w "staging_ready=%{http_code}\n" http://127.0.0.1:8011/ready; python3 -c "import json; b=json.load(open(\"/tmp/store-ready.json\")); print(\"staging_ready_status\", b.get(\"status\")); print(\"staging_migrations_ok\", (b.get(\"migrations\") or {}).get(\"ok\"))"'
  echo "== production api /ready (read-only) =="
  curl -sS -o /tmp/prod-ready.json -w "prod_ready=%{http_code}\n" --max-time 20 https://api.wathefni.ai/ready || echo "prod_ready=UNREACHABLE"
  python3 - <<'PY' || true
import json, pathlib
p = pathlib.Path("/tmp/prod-ready.json")
if p.is_file() and p.stat().st_size:
    try:
        b = json.loads(p.read_text())
        print("prod_ready_status", b.get("status"))
        print("prod_migrations_ok", (b.get("migrations") or {}).get("ok"))
    except Exception as exc:
        print("prod_ready_parse", type(exc).__name__)
PY
} 2>&1 | tee "$EVID/live/ready.out"

echo "EVIDENCE=$EVID"
if grep -q "STORE_BUILD_GATE_PASS" "$EVID/store-build-gate.out" \
  && grep -q "staging_ready=200" "$EVID/live/ready.out"; then
  echo STORE_BUILD_LIVE_CONFIG_OK
  if grep -q "prod_ready=200" "$EVID/live/ready.out"; then
    echo STORE_BUILD_PROD_READY_OK
  else
    echo STORE_BUILD_PROD_READY_UNPROVEN
  fi
  exit 0
fi
echo STORE_BUILD_LIVE_RED
exit 1
