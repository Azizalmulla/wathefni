#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-onboarding-wave4-hr-mutate.conf
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
cp -a "$BACKUP_DIR/action_registry.py" "$ORCH/action_registry.py"
cp -a "$BACKUP_DIR/onboarding_wave2.py" "$ORCH/onboarding_wave2.py" 2>/dev/null || true
rm -f "$DROPIN"
rm -f "$ORCH/canary-prod-onboarding-wave4.py"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 3
systemctl is-active wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo "ROLLBACK_OK"
