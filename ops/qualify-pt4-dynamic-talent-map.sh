#!/usr/bin/env bash
# PT4 — Dynamic Talent Map qualification.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/qualify-pt-overlay.sh" pt4
