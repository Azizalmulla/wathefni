#!/bin/bash
set -euo pipefail
B=/opt/wathefni/backups/production-pre-emf-p3-apply-flow-20260805T184419Z
cp "/opt/wathefni/backups/production-pre-emf-p3-apply-flow-20260805T184419Z/employee_migration_foundation.py" /opt/wathefni/orchestrator/employee_migration_foundation.py
rm -rf /var/www/wathefni-dashboard; cp -a "/opt/wathefni/backups/production-pre-emf-p3-apply-flow-20260805T184419Z/dashboard-www" /var/www/wathefni-dashboard
rm -rf /opt/wathefni/dashboard-dist; cp -a "/opt/wathefni/backups/production-pre-emf-p3-apply-flow-20260805T184419Z/dashboard-dist" /opt/wathefni/dashboard-dist
systemctl restart wathefni-orchestrator
echo ROLLED_BACK_emf_p3_apply_flow_20260805T184419Z
