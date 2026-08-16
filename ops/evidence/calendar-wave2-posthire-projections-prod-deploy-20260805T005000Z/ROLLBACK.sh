#!/usr/bin/env bash
set -euo pipefail
BK_DIR="$(cd "$(dirname "$0")" && pwd)"
rsync -a --delete "$BK_DIR/dashboard-dist/" /opt/wathefni/dashboard-dist/
if [[ -d "$BK_DIR/www" ]] && [[ -n "$(ls -A "$BK_DIR/www" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BK_DIR/www/" /var/www/wathefni-dashboard/
fi
if [[ -f "$BK_DIR/orchestrator/app.py" ]]; then
  cp -a "$BK_DIR/orchestrator/app.py" /opt/wathefni/orchestrator/app.py
fi
if [[ -f "$BK_DIR/orchestrator/calendar_posthire_projections.py" ]]; then
  cp -a "$BK_DIR/orchestrator/calendar_posthire_projections.py" /opt/wathefni/orchestrator/calendar_posthire_projections.py
elif [[ -f /opt/wathefni/orchestrator/calendar_posthire_projections.py ]]; then
  rm -f /opt/wathefni/orchestrator/calendar_posthire_projections.py
fi
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-calendar-wave2-projections.conf
rm -f "$DROPIN"
if [[ -f "$BK_DIR/flags/zzzz-calendar-wave2-projections.conf" ]]; then
  cp -a "$BK_DIR/flags/zzzz-calendar-wave2-projections.conf" "$DROPIN"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1 && break; sleep 1; done
echo ROLLBACK_OK calendar-wave2-projections
