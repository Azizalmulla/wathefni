#!/usr/bin/env bash
set -euo pipefail
npx eas-cli@latest update:republish --group c8d7076b-8ad1-42fe-9b3a-908dd382bb0d --branch canary --non-interactive
