#!/usr/bin/env bash
# Employee App runtime access — deploy-time flag reconcile.
#
# Runtime access is fail-closed on employees.app_access_enabled. That column was added
# after the first canary activations, so employees who were granted access before it
# existed still read as false. This migrator enables exactly the employees holding a
# live session (only an HR grant can produce one; HR disable revokes them), so the
# fail-closed repair cannot sign a legitimately granted employee out.
#
# Idempotent. Runs under the Wave 1-BR deploy advisory lock. Runtime API/workers must
# NOT set WATHEFNI_SCHEMA_APPLY.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_NAME="${WATHEFNI_ENV:?WATHEFNI_ENV required}"
case "$ENV_NAME" in
  staging)
    : "${ACK_STAGING_EMPLOYEE_APP_ACCESS_RECONCILE:?Set ACK_STAGING_EMPLOYEE_APP_ACCESS_RECONCILE=YES}"
    [[ "$ACK_STAGING_EMPLOYEE_APP_ACCESS_RECONCILE" == "YES" ]] || { echo "REFUSE ACK"; exit 2; }
    ;;
  production)
    : "${ACK_PRODUCTION_EMPLOYEE_APP_ACCESS_RECONCILE:?Set ACK_PRODUCTION_EMPLOYEE_APP_ACCESS_RECONCILE=YES}"
    [[ "$ACK_PRODUCTION_EMPLOYEE_APP_ACCESS_RECONCILE" == "YES" ]] || { echo "REFUSE ACK"; exit 2; }
    ;;
  *)
    echo "REFUSE: WATHEFNI_ENV must be staging or production"
    exit 2
    ;;
esac

export WATHEFNI_SCHEMA_APPLY=1
PYBIN="${ORCH_PYTHON:-python3}"

"$PYBIN" - <<'PY'
import json
import os
import sys

sys.path.insert(0, ".")
import app
import employee_app_access as access
import schema_contract as sc

assert sc.schema_apply_allowed(), "WATHEFNI_SCHEMA_APPLY must be on for migrate"
print("contract", sc.SCHEMA_CONTRACT_VERSION)
print("lock_id", sc.DEPLOY_ADVISORY_LOCK_ID)


def _bundle(cur):
    access.ensure_access_schema(cur)
    reconciled = access.reconcile_access_flag_for_live_sessions(cur)
    sc.record_apply(cur, module="employee_app_access.reconcile_live_sessions")
    return reconciled


with app.db_connect() as conn:
    with conn.cursor() as cur:
        reconciled = sc.with_deploy_advisory_lock(cur, _bundle)
    conn.commit()

print("reconciled_count", len(reconciled))
print("reconciled", json.dumps(reconciled))

# Prove idempotency and that no live session is left without the flag.
os.environ.pop("WATHEFNI_SCHEMA_APPLY", None)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS n FROM employees e
             WHERE e.app_access_enabled IS NOT TRUE
               AND EXISTS (
                     SELECT 1 FROM employee_sessions s
                      WHERE s.company_code = e.company_code
                        AND s.employee_key = e.employee_key
                        AND s.status = 'active'
                        AND s.expires_at > now()
                   )
            """
        )
        remaining = int(dict(cur.fetchone())["n"])
    conn.commit()
print("live_sessions_without_flag", remaining)
assert remaining == 0, "reconcile left live sessions without access"
print("MIGRATE_EMPLOYEE_APP_ACCESS_RECONCILE_OK")
PY
