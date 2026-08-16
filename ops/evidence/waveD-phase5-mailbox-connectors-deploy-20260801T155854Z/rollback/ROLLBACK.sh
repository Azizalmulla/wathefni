#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/orchestrator/app.py" "$ORCH/app.py"
cp -a "$ROOT/orchestrator/inbound_intake_product.py" "$ORCH/inbound_intake_product.py"
rm -f "$ORCH/inbound_mailbox_connectors.py"
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/waveD-phase5-mailbox-connectors.conf
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl daemon-reload
systemctl start wathefni-orchestrator.service
systemctl reload caddy || true
sleep 2
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "rollback_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Rolled back waveD-phase5-mailbox"
