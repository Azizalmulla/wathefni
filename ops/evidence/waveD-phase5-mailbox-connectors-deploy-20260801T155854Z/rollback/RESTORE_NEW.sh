#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/restore-new-orchestrator/app.py" "$ORCH/app.py"
cp -a "$ROOT/restore-new-orchestrator/inbound_intake_product.py" "$ORCH/inbound_intake_product.py"
cp -a "$ROOT/restore-new-orchestrator/inbound_mailbox_connectors.py" "$ORCH/inbound_mailbox_connectors.py"
cp -a "$ROOT/waveD-phase5-mailbox-connectors.conf" /etc/systemd/system/wathefni-orchestrator.service.d/waveD-phase5-mailbox-connectors.conf
rsync -a --delete "$ROOT/restore-new-dist/" /var/www/wathefni-dashboard/
systemctl daemon-reload
systemctl start wathefni-orchestrator.service
systemctl reload caddy || true
sleep 2
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "restore_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Restored waveD-phase5-mailbox"
