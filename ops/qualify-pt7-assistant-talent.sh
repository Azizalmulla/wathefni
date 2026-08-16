#!/usr/bin/env bash
# PT7 — Wathefni Assistant Talent Intelligence qualification + comprehensive PT1–PT7 regression.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/qualify-pt-overlay.sh" pt7
