#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/restore-new-orchestrator/app.py" "$PROD/app.py"
cp -a "$ROOT/restore-new-orchestrator/tenant_email_authority.py" "$PROD/tenant_email_authority.py"
cp -a "$ROOT/restore-new-orchestrator/durable_email_ingress.py" "$PROD/durable_email_ingress.py"
cp -a "$ROOT/restore-new-orchestrator/inbound_intake_product.py" "$PROD/inbound_intake_product.py"
install -m 644 "$ROOT/waveD-phase2-inbound-allowlist.conf" /etc/systemd/system/wathefni-orchestrator.service.d/waveD-phase2-inbound-allowlist.conf
rsync -a --delete "$ROOT/restore-new-dist/" /var/www/wathefni-dashboard/
systemctl daemon-reload
systemctl start wathefni-orchestrator.service
systemctl reload caddy || true
sleep 2
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "restore_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Restored waveD-phase2-inbound 20260801T045628Z"
