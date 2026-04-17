#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
set -a
source "$PROJECT_DIR/.env"
set +a

"$SCRIPT_DIR/bootstrap-profile.sh"
openclaw --profile "${OPENCLAW_PROFILE:-delivery}" gateway run --port "${OPENCLAW_GATEWAY_PORT:-18790}"
