#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzz-payroll-final-synthetic.conf
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/posthire
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  # Restore canary only; do not wipe wave modules if backup incomplete
  [[ -f "$BACKUP_DIR/modules/canary-prod-payroll-final.py" ]] && \
    cp -a "$BACKUP_DIR/modules/canary-prod-payroll-final.py" "$ORCH/" 2>/dev/null || true
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  for f in "$BACKUP_DIR"/systemd-dropins/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    [[ "$base" == "zzzzzzzzzzzzzzzzzzzz-payroll-final-synthetic.conf" ]] && continue
    cp -a "$f" /etc/systemd/system/wathefni-orchestrator.service.d/"$base"
  done
fi
rm -f "$DROPIN"
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
ENV_DUMP=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ)
for w in WAVE1 WAVE2A WAVE2B WAVE3 WAVE4 WAVE5; do
  echo "$ENV_DUMP" | grep -q "^WATHEFNI_PAYROLL_${w}=1"
done
if echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_FINAL_SYNTHETIC=1'; then
  echo "REFUSE: FINAL marker still enabled after rollback" >&2
  exit 4
fi
echo ROLLBACK_OK
