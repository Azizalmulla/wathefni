#!/usr/bin/env bash
# Rollback Auth Wave 2 Phase 3 smart auto-lock canary OTA.
# Does not wipe PIN/session. Does not revoke Wave 1 devices.
set -euo pipefail
PRIOR_GROUP="${PRIOR_GROUP:-3d4d10ca-1852-473b-b912-a32de97d5245}"
echo "Republish prior canary group to roll back Phase 3 JS:"
echo "  eas update:republish --group $PRIOR_GROUP --branch canary --non-interactive"
echo "Or publish a new update from a tree without EXPO_PUBLIC_LOCAL_AUTO_LOCK / auto-lock wiring."
echo "Native binary with screen-detector: keep prior biometric builds if needed:"
echo "  iOS 24c71b0a-6b09-4bb3-8d0d-c1e5dcbdc076"
echo "  Android e7eefb47-abfb-4b0e-8387-bf02b75805cc"
