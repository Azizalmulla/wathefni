#!/bin/bash
set -euo pipefail
B=/opt/wathefni/backups/production-pre-emf-p3-canonical-apply-20260805T194534Z
cp "/opt/wathefni/backups/production-pre-emf-p3-canonical-apply-20260805T194534Z/employee_migration_foundation.py" /opt/wathefni/orchestrator/employee_migration_foundation.py
cp "/opt/wathefni/backups/production-pre-emf-p3-canonical-apply-20260805T194534Z/app.py" /opt/wathefni/orchestrator/app.py
rm -rf /var/www/wathefni-dashboard; cp -a "/opt/wathefni/backups/production-pre-emf-p3-canonical-apply-20260805T194534Z/dashboard-www" /var/www/wathefni-dashboard
rm -rf /opt/wathefni/dashboard-dist; cp -a "/opt/wathefni/backups/production-pre-emf-p3-canonical-apply-20260805T194534Z/dashboard-dist" /opt/wathefni/dashboard-dist
systemctl restart wathefni-orchestrator
echo ROLLED_BACK_emf_p3_canonical_apply_20260805T194534Z
