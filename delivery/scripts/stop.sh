#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
set -a
source "$PROJECT_DIR/.env"
set +a

PORT="${OPENCLAW_GATEWAY_PORT:-18790}"
PIDS="$(lsof -ti tcp:${PORT} || true)"
if [ -n "$PIDS" ]; then
  kill $PIDS
  echo "Stopped delivery gateway on port ${PORT}"
else
  echo "No delivery gateway process found on port ${PORT}"
fi
