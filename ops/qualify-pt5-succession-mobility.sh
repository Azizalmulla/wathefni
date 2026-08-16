#!/usr/bin/env bash
# PT5 — Succession + Internal Mobility Intelligence qualification.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/qualify-pt-overlay.sh" pt5
