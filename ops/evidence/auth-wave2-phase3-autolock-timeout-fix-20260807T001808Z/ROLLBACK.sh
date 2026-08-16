#!/usr/bin/env bash
set -euo pipefail
echo "Republish prior Phase 3 OTA group:"
echo "  eas update:republish --group fda08e77-f7a1-464c-8596-00cc4e4c6461 --branch canary --non-interactive"
