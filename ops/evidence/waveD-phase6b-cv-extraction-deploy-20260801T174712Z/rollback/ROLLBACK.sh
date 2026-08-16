#!/usr/bin/env bash
# Rollback Wave D6B cv_extraction repair.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/orchestrator/app.py" "$ORCH/app.py"
cp -a "$ROOT/orchestrator/inbound_cv_authority.py" "$ORCH/inbound_cv_authority.py"
systemctl start wathefni-orchestrator.service
sleep 2
curl -sS -o /dev/null -w "rollback_orch=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "rollback_dash=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Rolled back waveD-phase6b-cv-extraction"
