#!/usr/bin/env bash
# Rollback Wave D6A durable→Held materialization repair.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/orchestrator/app.py" "$ORCH/app.py"
cp -a "$ROOT/orchestrator/durable_email_ingress.py" "$ORCH/durable_email_ingress.py"
systemctl start wathefni-orchestrator.service
sleep 2
curl -sS -o /dev/null -w "rollback_orch=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "rollback_dash=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Rolled back waveD-phase6a-held-materialization"
