#!/usr/bin/env bash
set -euo pipefail
# Frontend-only rollback. Does not restart the orchestrator or touch Setup
# Console configuration, entitlements, allowlists, or production data.
rsync -a --delete /opt/wathefni/backups/production-pre-hr-web-ux-phase85-hardening-20260821T210427Z/dashboard-dist/ /opt/wathefni/dashboard-dist/
echo ROLLBACK_OK hr-web-ux-phase85-hardening stamp=20260821T210427Z
echo restored_index=$(grep -o 'dashboard-[A-Za-z0-9_-]*\.js' /opt/wathefni/dashboard-dist/index.html | head -1)
