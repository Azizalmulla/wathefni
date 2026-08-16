#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PROD=/opt/wathefni/orchestrator
systemctl stop wathefni-orchestrator.service || true
cp -a "$ROOT/orchestrator/app.py.pre" "$PROD/app.py"
cp -a "$ROOT/orchestrator/tenant_email_authority.py.pre" "$PROD/tenant_email_authority.py"
cp -a "$ROOT/orchestrator/durable_email_ingress.py.pre" "$PROD/durable_email_ingress.py"
rm -f "$PROD/inbound_intake_product.py"
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/waveD-phase2-inbound-allowlist.conf
rsync -a --delete "$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl daemon-reload
systemctl start wathefni-orchestrator.service
systemctl reload caddy || true
sleep 2
curl -sS -o /dev/null -w "rollback_health=%{http_code}\n" http://127.0.0.1:8010/health || true
curl -sS -o /dev/null -w "rollback_dashboard=%{http_code}\n" https://api.wathefni.ai/dashboard/ --max-time 20 || true
echo "Rolled back waveD-phase2-inbound 20260801T045628Z"
