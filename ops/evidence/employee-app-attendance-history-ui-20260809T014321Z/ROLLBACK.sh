#!/usr/bin/env bash
set -euo pipefail
cd "/Users/azizalmulla/Desktop/claw/apps/wathefni-employee-mobile"
npx eas-cli@latest update:republish --group 41afc0af-2aa8-46dd-911e-c94d17941ed1 --branch canary --non-interactive
