#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzz-payroll-wave5b-synthetic.conf
DASH_SRC=/opt/wathefni/apps/wathefni-dashboard/src/posthire
test -d "$BACKUP_DIR"
if [[ -d "$BACKUP_DIR/modules" ]]; then
  cp -a "$BACKUP_DIR/modules"/. "$ORCH/" 2>/dev/null || true
fi
HAD=$(cat "$BACKUP_DIR/had_wave5_module.txt" 2>/dev/null || echo 0)
if [[ "$HAD" != "1" ]]; then
  rm -f "$ORCH/payroll_pifss_eos_wave5.py"
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/systemd-dropins" ]]; then
  for f in "$BACKUP_DIR"/systemd-dropins/*; do
    [[ -f "$f" ]] || continue
    base=$(basename "$f")
    [[ "$base" == "zzzzzzzzzzzzzzzzzzz-payroll-wave5b-synthetic.conf" ]] && continue
    cp -a "$f" /etc/systemd/system/wathefni-orchestrator.service.d/"$base"
  done
fi
rm -f "$DROPIN"
if [[ -d "$BACKUP_DIR/dashboard-posthire" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-posthire" 2>/dev/null || true)" ]]; then
  mkdir -p "$DASH_SRC"
  cp -a "$BACKUP_DIR/dashboard-posthire"/. "$DASH_SRC/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
ENV_DUMP=$(tr '\0' '\n' < /proc/"$(systemctl show -p MainPID --value wathefni-orchestrator)"/environ)
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2B=1'
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE3=1'
echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE4=1'
if echo "$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE5=1'; then
  echo "REFUSE: WAVE5 still enabled after rollback" >&2
  exit 4
fi
echo ROLLBACK_OK
