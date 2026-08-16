#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-payroll-wave2bb-synthetic.conf
test -d "$BACKUP_DIR"
# Restore pre-Wave-2B-B code; remove Wave 2B drop-in; keep Wave 1 + Wave 2A drop-ins
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
HAD=$(cat "$BACKUP_DIR/had_wave2b_module.txt" 2>/dev/null || echo 0)
if [[ "$HAD" != "1" ]]; then
  rm -f "$ORCH/payroll_native_preview_wave2b.py"
fi
rm -f "$DROPIN"
# Restore other drop-ins from backup (Wave 1 / Wave 2A retained)
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  # Do not wipe directory; re-copy known freeze drop-ins and ensure Wave 2B drop-in gone
  for f in "$BACKUP_DIR"/systemd-dropins/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    [[ "$base" == "zzzzzzzzzzzzzzzz-payroll-wave2bb-synthetic.conf" ]] && continue
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
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1'
if tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2B=1'; then
  echo "REFUSE: WAVE2B still enabled after rollback" >&2
  exit 4
fi
echo ROLLBACK_OK
# Preview schema tables remain additive; canary cleans synthetic rows.
