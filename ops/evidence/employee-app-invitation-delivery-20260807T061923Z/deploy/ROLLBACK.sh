#!/usr/bin/env bash
set -euo pipefail
# Run on VPS as root.
# Note: keep outbound_delivery.py company_code fix unless you intentionally
# reintroduce the activation-delivery audit bug.
STAMP=20260807T061923Z
BACKUP=/opt/wathefni/backups/invitation-$STAMP
test -f "$BACKUP/app.py"
cp -a "$BACKUP/app.py" /opt/wathefni/orchestrator/app.py
rm -f /opt/wathefni/orchestrator/employee_app_invitation.py
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/employee-app-auto-invite.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator
echo "Rolled back invitation delivery wave $STAMP (outbound company_code fix retained)"
