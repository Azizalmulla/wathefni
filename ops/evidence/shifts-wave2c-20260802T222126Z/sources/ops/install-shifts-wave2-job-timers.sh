#!/usr/bin/env bash
# Install Shifts Wave 2 operator job systemd units — DISABLED BY DEFAULT.
# Does NOT enable timers. Does NOT enable real-employee mutations.
set -euo pipefail
ORCH="${ORCH:-/opt/wathefni/orchestrator}"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"
SRC="${STAGE_DIR:-$ORCH/ops}"
EVID="${REMOTE_EVID:-/tmp/shifts-w2c-timers}"
mkdir -p "$EVID"

UNITS=(
  wathefni-shifts-reminder-drain.service
  wathefni-shifts-reminder-drain.timer
  wathefni-shifts-lifecycle-recon.service
  wathefni-shifts-lifecycle-recon.timer
  wathefni-shifts-leave-recon.service
  wathefni-shifts-leave-recon.timer
)

for u in "${UNITS[@]}"; do
  test -f "$SRC/$u" || { echo "missing $SRC/$u" >&2; exit 1; }
  cp -a "$SRC/$u" "$UNIT_DIR/$u"
done

# Ensure job runner is present under orchestrator ops/
mkdir -p "$ORCH/ops" "$ORCH/ops/runbooks"
if [[ -f "$SRC/run-shifts-wave2b-jobs.sh" ]]; then
  cp -a "$SRC/run-shifts-wave2b-jobs.sh" "$ORCH/ops/"
  chmod +x "$ORCH/ops/run-shifts-wave2b-jobs.sh"
fi
if [[ -f "$SRC/shifts-wave2b-operator-jobs.md" ]]; then
  cp -a "$SRC/shifts-wave2b-operator-jobs.md" "$ORCH/ops/runbooks/" 2>/dev/null \
    || cp -a "$SRC/shifts-wave2b-operator-jobs.md" "$ORCH/ops/" 
fi

systemctl daemon-reload

# Explicitly leave timers disabled (qualification requires disabled after prove).
for t in wathefni-shifts-reminder-drain.timer \
         wathefni-shifts-lifecycle-recon.timer \
         wathefni-shifts-leave-recon.timer; do
  systemctl disable "$t" 2>/dev/null || true
  systemctl stop "$t" 2>/dev/null || true
done

{
  echo "stamp=$(date -u +%Y%m%dT%H%M%SZ)"
  echo "installed=1"
  for t in wathefni-shifts-reminder-drain.timer \
           wathefni-shifts-lifecycle-recon.timer \
           wathefni-shifts-leave-recon.timer; do
    echo "=== $t ==="
    systemctl is-enabled "$t" 2>&1 || true
    systemctl is-active "$t" 2>&1 || true
  done
} | tee "$EVID/timers-installed-disabled.txt"

echo "SHIFTS_W2C_TIMERS_INSTALLED_DISABLED"
