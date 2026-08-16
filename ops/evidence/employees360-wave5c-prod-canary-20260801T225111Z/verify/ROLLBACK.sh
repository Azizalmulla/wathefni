#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
[[ -f "$BACKUP_DIR/lifecycle-effective-worker.py" ]] && cp -a "$BACKUP_DIR/lifecycle-effective-worker.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee_lifecycle_wave3c.py" ]] && cp -a "$BACKUP_DIR/employee_lifecycle_wave3c.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee_policy_packs_wave3h.py" ]] && cp -a "$BACKUP_DIR/employee_policy_packs_wave3h.py" "$ORCH/"
[[ -f "$BACKUP_DIR/employee_org_wave4.py" ]] && cp -a "$BACKUP_DIR/employee_org_wave4.py" "$ORCH/"
rm -f "$ORCH/employee_selfservice_wave5.py"
rm -f "$ORCH/canary-prod-wave5c-ess.py"
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/employee-ess-v5.conf
# Restore prior drop-ins for lifecycle/org if present
[[ -f "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" ]] && \
  cp -a "$BACKUP_DIR/employee-lifecycle-v3-synthetic.conf" \
    /etc/systemd/system/wathefni-orchestrator.service.d/employee-lifecycle-v3-synthetic.conf
[[ -f "$BACKUP_DIR/employee-org-v4.conf" ]] && \
  cp -a "$BACKUP_DIR/employee-org-v4.conf" \
    /etc/systemd/system/wathefni-orchestrator.service.d/employee-org-v4.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
systemctl enable --now wathefni-lifecycle-effective.timer 2>/dev/null || true
sleep 2
curl -fsS http://127.0.0.1:8010/healthz || curl -fsS http://127.0.0.1:8010/health
echo "rolled back Wave 5C ESS modules/flags; Wave 3F/3H + Wave 4 + SYNTHETIC_ONLY retained"
echo "NOTE: additive employee_ess_* tables left in place; bank secret file NOT deleted (manual ops)."
