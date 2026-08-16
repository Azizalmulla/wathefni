#!/usr/bin/env bash
# Rollback Onboarding Wave 1B app.py only. Does not touch SEED/HR_MUTATE drop-ins.
set -euo pipefail
BACKUP_DIR="${1:?backup dir}"
ORCH=/opt/wathefni/orchestrator
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
systemctl restart wathefni-orchestrator
sleep 2
systemctl is-active wathefni-orchestrator
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo "ROLLBACK_OK"
