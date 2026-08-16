#!/usr/bin/env bash
set -euo pipefail
BACKUP_DIR="${1:-$(cd "$(dirname "$0")" && pwd)}"
ORCH=/opt/wathefni/orchestrator
DASH_DIST=/opt/wathefni/dashboard-dist
DROPIN_2G=/etc/systemd/system/wathefni-orchestrator.service.d/zz-attendance-wave2g-capture-store-postgres.conf
PYBIN="$ORCH/.venv/bin/python"
test -f "$BACKUP_DIR/app.py"
cp -a "$BACKUP_DIR/app.py" "$ORCH/app.py"
if [[ -d "$BACKUP_DIR/capture_modules" ]]; then
  # restore modules that existed; remove wave2g-only postgres module if rolled back to pre-2G
  cp -a "$BACKUP_DIR/capture_modules"/. "$ORCH/" || true
  if [[ ! -f "$BACKUP_DIR/capture_modules/attendance_capture_postgres.py" ]]; then
    rm -f "$ORCH/attendance_capture_postgres.py"
  fi
fi
rm -f "$DROPIN_2G"
# Drop durable schema if present (requires empty or FORCE)
export WATHEFNI_ENV=production
export ACK_DB=wathefni
export ACK_PRODUCTION_CAPTURE_ROLLBACK=1
export FORCE_DROP=1
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
if [[ -f "$ORCH/ops/rollback-attendance-capture-wave2g-prod.sh" ]]; then
  ORCH_PYTHON="$PYBIN" bash "$ORCH/ops/rollback-attendance-capture-wave2g-prod.sh" || true
elif [[ -f /tmp/attw2g-stage/rollback-attendance-capture-wave2g-prod.sh ]]; then
  cd "$ORCH"
  ORCH_PYTHON="$PYBIN" bash /tmp/attw2g-stage/rollback-attendance-capture-wave2g-prod.sh || true
fi
if [[ -d "$BACKUP_DIR/dashboard-dist" ]] && [[ -n "$(ls -A "$BACKUP_DIR/dashboard-dist" 2>/dev/null || true)" ]]; then
  rsync -a --delete "$BACKUP_DIR/dashboard-dist/" "$DASH_DIST/"
fi
systemctl daemon-reload
systemctl restart wathefni-orchestrator
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8010/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_OK
