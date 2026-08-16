#!/usr/bin/env bash
# Wave 2B operator job runner — synthetic-scoped, locked, kill-switch aware.
set -euo pipefail
ORCH="${ORCH:-/opt/wathefni/orchestrator}"
cd "$ORCH"
JOB="${1:-}"
shift || true
LIMIT=50
while [[ $# -gt 0 ]]; do
  case "$1" in
    --limit) LIMIT="${2:-50}"; shift 2 ;;
    *) shift ;;
  esac
done
: "${JOB:?usage: run-shifts-wave2b-jobs.sh <reminder|lifecycle|leave|terminal-failures> [--limit N]}"

PYBIN="${ORCH_PYTHON:-$ORCH/.venv/bin/python}"
test -x "$PYBIN" || PYBIN=python3

if PID=$(systemctl show -p MainPID --value wathefni-orchestrator 2>/dev/null); then
  if [[ -n "$PID" && "$PID" != "0" && -r "/proc/$PID/environ" ]]; then
    while IFS= read -r -d '' line; do
      case "$line" in WATHEFNI_*=*) export "$line" ;; esac
    done < "/proc/$PID/environ"
  fi
fi
set -a
# shellcheck disable=SC1091
source "${WATHEFNI_POSTGRES_ENV:-/root/.openclaw/secrets/postgres.env}"
set +a
export WATHEFNI_ENV="${WATHEFNI_ENV:-production}"
export WATHEFNI_EXPECTED_DATABASE_NAME="${WATHEFNI_EXPECTED_DATABASE_NAME:-wathefni}"
export W2B_JOB="$JOB"
export W2B_LIMIT="$LIMIT"

"$PYBIN" - <<'PY'
import json, os, sys
sys.path.insert(0, ".")
import app
import shifts_schedule_integrity_wave2 as w2

job = os.environ["W2B_JOB"]
limit = int(os.environ.get("W2B_LIMIT") or "50")
assert os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") == "wathefni"
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db")
        assert dict(cur.fetchone())["db"] == "wathefni"
        if job == "reminder":
            out = app.run_shift_reminder_scan(account_id=None, dry_run=False, limit=limit, hours_ahead=2)
        elif job == "lifecycle":
            out = w2.run_lifecycle_reconciliation_job(cur, company_code="WATHEFNI", limit=limit)
        elif job == "leave":
            out = w2.run_leave_reconciliation_job(cur, company_code="WATHEFNI", limit=limit)
        elif job == "terminal-failures":
            rows = w2.filter_reminders_synthetic_only(
                w2.list_terminal_reminder_failures(cur, company_code="WATHEFNI", limit=limit)
            )
            out = {"ok": True, "job": "terminal_failures", "count": len(rows), "rows": rows}
        else:
            raise SystemExit(f"unknown job {job}")
    conn.commit()
print(json.dumps(out, indent=2, default=str))
PY
