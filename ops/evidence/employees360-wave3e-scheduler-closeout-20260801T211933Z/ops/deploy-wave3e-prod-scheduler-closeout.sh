#!/usr/bin/env bash
# Wave 3E — enable production synthetic-only lifecycle timer + closeout proofs.
set -euo pipefail

STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
REMOTE_EVID="/opt/wathefni/production-evidence/employees360-wave3e-scheduler-closeout/${STAMP}"
BACKUP="/opt/wathefni/backups/production-pre-employees360-wave3e-${STAMP}"
ORCH=/opt/wathefni/orchestrator
STAGE=/tmp/wave3e-deploy

echo "STAMP=$STAMP"
mkdir -p "$REMOTE_EVID" "$BACKUP" "$STAGE"
echo "$BACKUP" > "$REMOTE_EVID/BACKUP_PATH.txt"

# Backup qualified Wave 3D timer/service state (timer not enabled)
cp -a /etc/systemd/system/wathefni-lifecycle-effective.service "$BACKUP/" 2>/dev/null || true
cp -a "$ORCH/lifecycle-effective-worker.py" "$BACKUP/" 2>/dev/null || true
systemctl is-enabled wathefni-lifecycle-effective.timer 2>/dev/null | tee "$BACKUP/timer-enabled-before.txt" || echo "not-found" | tee "$BACKUP/timer-enabled-before.txt"
systemctl is-active wathefni-lifecycle-effective.timer 2>/dev/null | tee "$BACKUP/timer-active-before.txt" || echo "inactive" | tee "$BACKUP/timer-active-before.txt"

cat > "$BACKUP/ROLLBACK.sh" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
systemctl disable --now wathefni-lifecycle-effective.timer 2>/dev/null || true
systemctl disable --now wathefni-lifecycle-effective-proof.timer 2>/dev/null || true
rm -f /etc/systemd/system/wathefni-lifecycle-effective.timer
rm -f /etc/systemd/system/wathefni-lifecycle-effective-proof.timer
rm -f /etc/systemd/system/wathefni-lifecycle-effective.service.d/kill-switch.conf
# Restore Wave 3D oneshot service (no timer)
if [[ -f "$BACKUP_DIR/wathefni-lifecycle-effective.service" ]]; then
  cp -a "$BACKUP_DIR/wathefni-lifecycle-effective.service" /etc/systemd/system/wathefni-lifecycle-effective.service
fi
if [[ -f "$BACKUP_DIR/lifecycle-effective-worker.py" ]]; then
  cp -a "$BACKUP_DIR/lifecycle-effective-worker.py" /opt/wathefni/orchestrator/lifecycle-effective-worker.py
fi
systemctl daemon-reload
systemctl reset-failed wathefni-lifecycle-effective.service 2>/dev/null || true
echo "Wave 3E timer removed; Wave 3D oneshot-only state restored"
systemctl status wathefni-lifecycle-effective.timer --no-pager 2>&1 | head -5 || true
EOS
chmod +x "$BACKUP/ROLLBACK.sh"

# Install units + worker + closeout script
cp -a "$STAGE/wathefni-lifecycle-effective.service" /etc/systemd/system/
cp -a "$STAGE/wathefni-lifecycle-effective.timer" /etc/systemd/system/
cp -a "$STAGE/wathefni-lifecycle-effective-proof.timer" /etc/systemd/system/
cp -a "$STAGE/lifecycle-effective-worker.py" "$ORCH/"
cp -a "$STAGE/canary-prod-wave3e-scheduler-closeout.py" "$ORCH/"
chmod +x "$ORCH/lifecycle-effective-worker.py" "$ORCH/canary-prod-wave3e-scheduler-closeout.py"

# Ensure worker fail-once env is available to oneshot service
mkdir -p /etc/systemd/system/wathefni-lifecycle-effective.service.d
cat > /etc/systemd/system/wathefni-lifecycle-effective.service.d/fail-once-path.conf <<EOF
[Service]
Environment=WATHEFNI_LIFECYCLE_SCHEDULER_FAIL_ONCE_FILE=/tmp/wathefni-lifecycle-fail-once
EOF

systemctl daemon-reload

# Enable PROOF (minutely) timer for unattended demonstration
systemctl enable --now wathefni-lifecycle-effective-proof.timer
sleep 2
systemctl is-enabled wathefni-lifecycle-effective-proof.timer | tee "$REMOTE_EVID/proof-timer-enabled.txt"
systemctl is-active wathefni-lifecycle-effective-proof.timer | tee "$REMOTE_EVID/proof-timer-active.txt"
systemctl show wathefni-lifecycle-effective-proof.timer -p Persistent -p UnitFileState -p ActiveState -p NextElapseUSecRealtime | tee "$REMOTE_EVID/proof-timer-show-before-restart.txt"

# Prove survives daemon-reload + timer restart
systemctl daemon-reload
systemctl restart wathefni-lifecycle-effective-proof.timer
sleep 1
systemctl is-enabled wathefni-lifecycle-effective-proof.timer | tee "$REMOTE_EVID/proof-timer-enabled-after-restart.txt"
systemctl is-active wathefni-lifecycle-effective-proof.timer | tee "$REMOTE_EVID/proof-timer-active-after-restart.txt"
systemctl show wathefni-lifecycle-effective-proof.timer -p Persistent -p UnitFileState -p ActiveState | tee "$REMOTE_EVID/proof-timer-show-after-restart.txt"

# Run closeout under production env
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' kv; do
  case "$kv" in
    WATHEFNI_*|DATABASE_URL=*) export "$kv" ;;
  esac
done < /proc/$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
export WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
export WATHEFNI_EMPLOYEE_AUTHORITY_V2=on
export WATHEFNI_EMPLOYEE_AUTHORITY_V2_COMPANIES=WATHEFNI
export WATHEFNI_LIFECYCLE_COUNSEL_GATE=on
export WAVE3E_OUT="$REMOTE_EVID/closeout"
mkdir -p "$WAVE3E_OUT"

set +e
/opt/wathefni/orchestrator/.venv/bin/python "$ORCH/canary-prod-wave3e-scheduler-closeout.py" | tee "$REMOTE_EVID/closeout-run.log"
CLOSEOUT_EC=${PIPESTATUS[0]}
set -e
echo "$CLOSEOUT_EC" > "$REMOTE_EVID/closeout-exit-code.txt"

# Capture journal around closeout
journalctl -u wathefni-lifecycle-effective.service --since "30 min ago" --no-pager -o short-iso | tee "$REMOTE_EVID/scheduler-journal.txt" >/dev/null

# --- Rollback proof (disable/remove proof+hourly, restore 3D no-timer) ---
"$BACKUP/ROLLBACK.sh" | tee "$REMOTE_EVID/rollback-proof.log"
systemctl is-enabled wathefni-lifecycle-effective.timer 2>&1 | tee "$REMOTE_EVID/timer-enabled-after-rollback.txt" || true
systemctl is-active wathefni-lifecycle-effective.timer 2>&1 | tee "$REMOTE_EVID/timer-active-after-rollback.txt" || true
systemctl is-enabled wathefni-lifecycle-effective-proof.timer 2>&1 | tee "$REMOTE_EVID/proof-timer-enabled-after-rollback.txt" || true

# --- Final operational state: hourly Persistent timer ON (Wave 3E closeout goal) ---
cp -a "$STAGE/wathefni-lifecycle-effective.service" /etc/systemd/system/
cp -a "$STAGE/wathefni-lifecycle-effective.timer" /etc/systemd/system/
mkdir -p /etc/systemd/system/wathefni-lifecycle-effective.service.d
cat > /etc/systemd/system/wathefni-lifecycle-effective.service.d/fail-once-path.conf <<EOF
[Service]
Environment=WATHEFNI_LIFECYCLE_SCHEDULER_FAIL_ONCE_FILE=/tmp/wathefni-lifecycle-fail-once
EOF
# Ensure no kill-switch left behind
rm -f /etc/systemd/system/wathefni-lifecycle-effective.service.d/kill-switch.conf
systemctl daemon-reload
systemctl enable --now wathefni-lifecycle-effective.timer
sleep 1
systemctl is-enabled wathefni-lifecycle-effective.timer | tee "$REMOTE_EVID/final-timer-enabled.txt"
systemctl is-active wathefni-lifecycle-effective.timer | tee "$REMOTE_EVID/final-timer-active.txt"
systemctl show wathefni-lifecycle-effective.timer -p Persistent -p UnitFileState -p ActiveState -p NextElapseUSecRealtime | tee "$REMOTE_EVID/final-timer-show.txt"
systemctl list-timers 'wathefni-lifecycle*' --all --no-pager | tee "$REMOTE_EVID/list-timers.txt"
# Freeze flags
tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator)/environ \
  | grep -E 'WATHEFNI_EMPLOYEE_LIFECYCLE|WATHEFNI_EMPLOYEE_AUTHORITY|WATHEFNI_ENV' | sort \
  | tee "$REMOTE_EVID/freeze-flags.txt"
curl -fsS http://127.0.0.1:8010/health | tee "$REMOTE_EVID/health-final.txt"
sha256sum "$ORCH/lifecycle-effective-worker.py" "$ORCH/canary-prod-wave3e-scheduler-closeout.py" \
  /etc/systemd/system/wathefni-lifecycle-effective.service \
  /etc/systemd/system/wathefni-lifecycle-effective.timer | tee "$REMOTE_EVID/sha-final.txt"

echo "REMOTE_EVID=$REMOTE_EVID"
echo "CLOSEOUT_EC=$CLOSEOUT_EC"
exit "$CLOSEOUT_EC"
