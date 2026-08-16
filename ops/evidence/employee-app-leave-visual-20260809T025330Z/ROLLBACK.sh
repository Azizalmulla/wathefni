#!/usr/bin/env bash
set -euo pipefail
npx eas-cli@latest update:republish --group edab3610-a184-42c2-bb6b-9d1ca37d73b1 --branch canary --non-interactive
