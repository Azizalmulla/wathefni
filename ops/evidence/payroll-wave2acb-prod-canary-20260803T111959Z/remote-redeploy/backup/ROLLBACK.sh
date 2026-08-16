#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-payroll-wave2ab-synthetic.conf
DASH_DIST=/opt/wathefni/dashboard-dist
DASH_DIST_LEGACY=/opt/wathefni/apps/wathefni-dashboard/dist
test -d "$BACKUP_DIR"
# Restore Wave 2A-C-B code; keep Wave 2A freeze drop-in from backup (still WAVE2A=1)
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
if [[ -f "$BACKUP_DIR/payroll-wave2ab-synthetic.conf" ]]; then
  cp -a "$BACKUP_DIR/payroll-wave2ab-synthetic.conf" "$DROPIN"
elif [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  cp -a "$BACKUP_DIR/systemd-dropins"/. /etc/systemd/system/wathefni-orchestrator.service.d/ || true
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_DIST"
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
if [[ -d "$BACKUP_DIR/dashboard-dist-legacy" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist-legacy" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_DIST_LEGACY"
  rsync -a --delete "$BACKUP_DIR/dashboard-dist-legacy/" "$DASH_DIST_LEGACY/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
# Wave 1 + Wave 2A must remain after 2A-C-B rollback
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
echo ROLLBACK_OK
