#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/app.py.pre" /opt/wathefni/orchestrator/app.py
cp -a "$ROOT/prehire_overview.py.pre" /opt/wathefni/orchestrator/prehire_overview.py
systemctl start wathefni-orchestrator.service
sleep 2
curl -sf http://127.0.0.1:8010/health
echo
echo CODE_ROLLBACK_OK
