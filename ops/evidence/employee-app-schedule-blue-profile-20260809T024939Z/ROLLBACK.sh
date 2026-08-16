#!/usr/bin/env bash
set -euo pipefail
npx eas-cli@latest update:republish --group ad21acee-d77f-4f71-9b77-b6b46da78ca9 --branch canary --non-interactive
