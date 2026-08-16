#!/usr/bin/env bash
set -euo pipefail
cd /opt/wathefni/staging/orchestrator
set -a
source /root/.openclaw/secrets/postgres.staging.env
set +a
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export ACK_DB=wathefni_staging
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
export WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=0
export WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
export WATHEFNI_SHIFTS_LEAVE_CONFLICT_MODE=require_ack
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/staging/dashboard-dist
export PYTHONUNBUFFERED=1
PY=/opt/wathefni/orchestrator/.venv/bin/python
exec "$PY" -u smoke-test-shifts-authority-wave1.py
