#!/bin/bash
set -euo pipefail
B=/opt/wathefni/backups/production-pre-emf-p3-name-guard-20260805T160200Z
cp "$B/employee_migration_foundation.py" /opt/wathefni/orchestrator/employee_migration_foundation.py
cp "$B/app.py" /opt/wathefni/orchestrator/app.py
rm -rf /var/www/wathefni-dashboard; cp -a "$B/dashboard-www" /var/www/wathefni-dashboard
rm -rf /opt/wathefni/dashboard-dist; cp -a "$B/dashboard-dist" /opt/wathefni/dashboard-dist
systemctl restart wathefni-orchestrator
echo ROLLED_BACK_emf_p3_name_guard_20260805T160200Z
