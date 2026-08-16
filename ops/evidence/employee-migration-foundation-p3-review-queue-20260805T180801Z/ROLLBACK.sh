#!/bin/bash
set -euo pipefail
B=/opt/wathefni/backups/production-pre-emf-p3-review-queue-20260805T180801Z
cp "/opt/wathefni/backups/production-pre-emf-p3-review-queue-20260805T180801Z/employee_migration_foundation.py" /opt/wathefni/orchestrator/employee_migration_foundation.py
rm -rf /var/www/wathefni-dashboard; cp -a "/opt/wathefni/backups/production-pre-emf-p3-review-queue-20260805T180801Z/dashboard-www" /var/www/wathefni-dashboard
rm -rf /opt/wathefni/dashboard-dist; cp -a "/opt/wathefni/backups/production-pre-emf-p3-review-queue-20260805T180801Z/dashboard-dist" /opt/wathefni/dashboard-dist
systemctl restart wathefni-orchestrator
echo ROLLED_BACK_emf_p3_review_queue_20260805T180801Z
