#!/bin/bash
set -euo pipefail
B=/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z
cp "/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z/employee_migration_foundation.py" /opt/wathefni/orchestrator/employee_migration_foundation.py
cp "/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z/app.py" /opt/wathefni/orchestrator/app.py
if [ -d "/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z/dashboard-www" ]; then rm -rf /var/www/wathefni-dashboard; cp -a "/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z/dashboard-www" /var/www/wathefni-dashboard; fi
if [ -d "/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z/dashboard-dist" ]; then rm -rf /opt/wathefni/dashboard-dist; cp -a "/opt/wathefni/backups/production-pre-emf-p3-20260805T154331Z/dashboard-dist" /opt/wathefni/dashboard-dist; fi
systemctl restart wathefni-orchestrator
echo ROLLED_BACK_emf_p3_20260805T154331Z
