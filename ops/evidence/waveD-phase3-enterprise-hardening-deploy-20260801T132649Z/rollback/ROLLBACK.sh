#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$ROOT/orchestrator/app.py" "$ORCH/app.py"
cp -a "$ROOT/orchestrator/durable_email_ingress.py" "$ORCH/durable_email_ingress.py"
cp -a "$ROOT/orchestrator/inbound_intake_product.py" "$ORCH/inbound_intake_product.py"
rm -f "$ORCH/inbound_enterprise_hardening.py"
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/waveD-phase3-enterprise.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 2
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health || true
echo "Rolled back waveD-phase3-enterprise 20260801T132649Z"
