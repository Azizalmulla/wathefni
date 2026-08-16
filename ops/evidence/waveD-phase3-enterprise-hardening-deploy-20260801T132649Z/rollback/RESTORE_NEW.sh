#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$ROOT/restore-new/app.py" "$ORCH/app.py"
cp -a "$ROOT/restore-new/durable_email_ingress.py" "$ORCH/durable_email_ingress.py"
cp -a "$ROOT/restore-new/inbound_intake_product.py" "$ORCH/inbound_intake_product.py"
cp -a "$ROOT/restore-new/inbound_enterprise_hardening.py" "$ORCH/inbound_enterprise_hardening.py"
cp -a "$ROOT/restore-new/waveD-phase3-enterprise.conf" /etc/systemd/system/wathefni-orchestrator.service.d/waveD-phase3-enterprise.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 2
curl -sS -o /dev/null -w "restore_health=%{http_code}\n" http://127.0.0.1:8010/health || true
echo "Restored waveD-phase3-enterprise 20260801T132649Z"
