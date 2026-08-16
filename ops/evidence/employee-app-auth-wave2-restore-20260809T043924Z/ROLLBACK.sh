#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../apps/wathefni-employee-mobile"
npx -y eas-cli@latest update:republish --group cf1cd9a5-39fc-4e8f-a603-fb6679b90b63 --branch canary --non-interactive
echo "OTA rolled back to cf1cd9a5-39fc-4e8f-a603-fb6679b90b63 (Bank hierarchy; Auth Wave 2 flags may be off on that tip)"
