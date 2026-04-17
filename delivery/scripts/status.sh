#!/bin/zsh
set -euo pipefail

SCRIPT_DIR=${0:A:h}
PROJECT_DIR=${SCRIPT_DIR:h}
set -a
source "$PROJECT_DIR/.env"
set +a

openclaw --profile "${OPENCLAW_PROFILE:-delivery}" gateway health
