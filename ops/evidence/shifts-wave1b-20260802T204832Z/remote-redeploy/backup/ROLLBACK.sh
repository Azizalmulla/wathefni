#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-authority-wave1b-synthetic.conf
test -d "$BACKUP_DIR"
if [[ -f "$BACKUP_DIR/app.py" ]]; then cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"; fi
if [[ ! -f "$BACKUP_DIR/modules/shifts_authority_wave1.py" ]]; then
  rm -f "$ORCH/shifts_authority_wave1.py"
else
  cp -a "$BACKUP_DIR/modules/shifts_authority_wave1.py" "$ORCH/"
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rm -rf "$DASH_DIST"
  mkdir -p "$DASH_DIST"
  cp -a "$BACKUP_DIR/dashboard-dist/." "$DASH_DIST/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo ROLLBACK_OK
