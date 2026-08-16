#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
cp -a "$ROOT/app.py.new" /opt/wathefni/orchestrator/app.py
systemctl restart wathefni-orchestrator
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf -o /dev/null http://127.0.0.1:8010/health; then break; fi
  sleep 1
done
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
echo "Restored assessments-queue-tombstone 20260801T033029Z"
