#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cp -a "$ROOT/tool_call_orchestrator.py.pre" /opt/wathefni/orchestrator/tool_call_orchestrator.py
cp -a "$ROOT/assistant_capability_catalog.py.pre" /opt/wathefni/orchestrator/assistant_capability_catalog.py
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl restart wathefni-orchestrator.service
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  if [ "$code" = "200" ]; then break; fi
done
systemctl reload caddy || true
echo "Rolled back assistant-empty 20260731T132338Z"
