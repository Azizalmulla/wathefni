#!/usr/bin/env bash
set -euo pipefail
npx eas-cli@latest update:republish --group ece7fa6a-14ae-4283-8f03-6d0a12d37b4b --branch canary --non-interactive
