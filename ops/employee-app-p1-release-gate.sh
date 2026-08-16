#!/usr/bin/env bash
# Employee App P1 release gate.
#
# One command that must be green before any Employee App P1 canary claim. Gates are
# split into three classes:
#
#   local    — source/static/unit gates that run anywhere (always required)
#   prod db  — synthetic-fixture smokes against the production orchestrator database
#   stg db   — the EMPAPPTESTCO harness, which creates and drops a whole company and
#              must therefore never touch production
#
# DB gates are skipped (never silently passed) when no database is reachable. A run
# that skipped DB gates prints SKIPPED and exits non-zero unless ALLOW_DB_SKIP=1,
# so a local-only run can never be mistaken for a full release qualification.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MOBILE="$ROOT/apps/wathefni-employee-mobile"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ALLOW_DB_SKIP="${ALLOW_DB_SKIP:-0}"

PASSED=(); FAILED=(); SKIPPED=()

run_gate() {
  local name="$1"; shift
  echo "── $name"
  if "$@" >/tmp/employee-app-gate.log 2>&1; then
    PASSED+=("$name")
    echo "   PASS"
  else
    FAILED+=("$name")
    echo "   FAIL"
    tail -25 /tmp/employee-app-gate.log | sed 's/^/   | /'
  fi
}

skip_gate() {
  SKIPPED+=("$1")
  echo "── $1"
  echo "   SKIPPED — $2"
}

PY_BIN="${WATHEFNI_PY:-/opt/wathefni/orchestrator/.venv/bin/python}"
[ -x "$PY_BIN" ] || PY_BIN="python3"

# Production reads/writes stay in synthetic fixtures; the EMPAPPTESTCO harness
# creates and drops a whole company, so it is staging-only by contract.
prod_env() {
  export WATHEFNI_ENV=production
  export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
  export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
  export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
  export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
  export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
  export WATHEFNI_EXPECTED_DATABASE_PORT=5432
  export WATHEFNI_EMPLOYEE_APP=on
}

staging_env() {
  export WATHEFNI_ENV=staging
  export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
  export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
  export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
  export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
  export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
  export WATHEFNI_EXPECTED_DATABASE_PORT=5432
  export WATHEFNI_EMPLOYEE_APP=on
  export WATHEFNI_SCHEMA_APPLY=1
}

# $1 = env function name (prod_env / staging_env)
db_reachable() {
  ( "$1"
    cd "$ORCH" || exit 1
    "$PY_BIN" - <<'PY'
import os, sys
sys.path.insert(0, os.getcwd())
try:
    import app as legacy
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
except Exception:
    raise SystemExit(1)
PY
  ) >/dev/null 2>&1
}

# $1 = gate name, $2 = env function name, rest = command
run_db_gate() {
  local name="$1" env_fn="$2"; shift 2
  echo "── $name"
  if ( "$env_fn"; cd "$ORCH" && "$@" ) >/tmp/employee-app-gate.log 2>&1; then
    PASSED+=("$name")
    echo "   PASS"
  else
    FAILED+=("$name")
    echo "   FAIL"
    tail -25 /tmp/employee-app-gate.log | sed 's/^/   | /'
  fi
}

echo "Employee App P1 release gate — $STAMP"
echo

# --- local gates -------------------------------------------------------------
# The orchestrator host has no mobile toolchain, so the node-dependent gates are
# skipped there rather than failed; a full qualification is the local run plus the
# host run, and neither may report PASS while anything is skipped.
MOBILE_GATES=(
  "mobile typecheck (tsc --noEmit)|bash|-c|cd '$MOBILE' && npx tsc --noEmit"
  "mobile PIN crypto selftest|node|$MOBILE/scripts/pin-crypto-selftest.js"
  "mobile entitlement composition shapes|node|$MOBILE/scripts/composition-shapes-test.js"
  "mobile documents hierarchy|node|$MOBILE/scripts/documents-hierarchy-test.js"
  "mobile push follow-through|node|$MOBILE/scripts/push-follow-through-test.js"
  "mobile feature unavailable copy|node|$MOBILE/scripts/feature-unavailable-copy-test.js"
  "mobile session refresh static proof|python3|$MOBILE/scripts/session-refresh-static-proof.py"
  # The auth wave 2 unit suites typecheck the mobile tree themselves.
  "auth wave 2 phase 1 PIN unit|python3|$ORCH/smoke-test-auth-wave2-phase1-pin-unit.py"
  "auth wave 2 phase 1 session hardening unit|python3|$ORCH/smoke-test-auth-wave2-phase1-session-hardening-unit.py"
  "auth wave 2 phase 2 biometric unit|python3|$ORCH/smoke-test-auth-wave2-phase2-biometric-unit.py"
  "auth wave 2 phase 3 auto-lock unit|python3|$ORCH/smoke-test-auth-wave2-phase3-autolock-unit.py"
  "auth wave 2 phase 4 PIN recovery unit|python3|$ORCH/smoke-test-auth-wave2-phase4-pin-recovery-unit.py"
  "auth wave 2 phase 5 device security unit|python3|$ORCH/smoke-test-auth-wave2-phase5-device-security-unit.py"
)

for entry in "${MOBILE_GATES[@]}"; do
  name="${entry%%|*}"
  IFS='|' read -r -a parts <<<"${entry#*|}"
  if command -v node >/dev/null 2>&1 && [ -d "$MOBILE/node_modules" ]; then
    run_gate "$name" "${parts[@]}"
  else
    skip_gate "$name" "no mobile node toolchain on this host"
  fi
done

run_gate "mobile capability + composition contract" python3 "$MOBILE/scripts/verify-capability-foundation.py"
run_gate "backend modules compile" python3 -m py_compile \
  "$ORCH/app.py" "$ORCH/employee_app_access.py" "$ORCH/employee_app_invitation.py" \
  "$ORCH/payroll_payslip_wave3.py" "$ORCH/payroll_payslip_official_pdf.py"
# Pure AST projection of the capability contract — no app import, no database.
run_gate "employee app capability contract" python3 "$ORCH/smoke-test-employee-app-capabilities.py"

# --- database gates ----------------------------------------------------------
export ORCH
PROD_GATES=(
  "employee app runtime access enforcement|$ORCH/smoke-test-employee-app-runtime-access.py"
  "employee app home projection contract|$ORCH/smoke-test-employee-app-home-projection.py"
  "employee app workday projection contract|$ORCH/smoke-test-employee-app-workday.py"
  "employee app profile projection contract|$ORCH/smoke-test-employee-app-profile.py"
  "employee app access eligibility matrix|$ORCH/smoke-test-employee-app-access-eligibility.py"
  "employee app invitation + delivery|$ORCH/smoke-test-employee-app-invitation.py"
  "employee payslips P0 release gate|$ROOT/ops/smoke-test-employee-payslips-p0.py"
  "employee payslips P0.1 official PDF|$ROOT/ops/smoke-test-employee-payslips-p0_1.py"
  "employee↔HR sync hardening|$ROOT/ops/smoke-test-employee-hr-sync-hardening.py"
)

if db_reachable prod_env; then
  for entry in "${PROD_GATES[@]}"; do
    run_db_gate "${entry%%|*}" prod_env "$PY_BIN" "${entry#*|}"
  done
else
  for entry in "${PROD_GATES[@]}"; do
    skip_gate "${entry%%|*}" "no production orchestrator database reachable from this host"
  done
fi

if db_reachable staging_env; then
  run_db_gate "employee app session/self-scope regression" staging_env \
    "$PY_BIN" "$ORCH/smoke-test-employee-app.py"
else
  skip_gate "employee app session/self-scope regression" \
    "no staging orchestrator database reachable from this host"
fi

echo
echo "passed=${#PASSED[@]} failed=${#FAILED[@]} skipped=${#SKIPPED[@]}"
if [ "${#FAILED[@]}" -gt 0 ]; then
  printf 'FAILED: %s\n' "${FAILED[*]}"
  echo "EMPLOYEE_APP_P1_RELEASE_GATE: FAIL"
  exit 1
fi
if [ "${#SKIPPED[@]}" -gt 0 ]; then
  printf 'SKIPPED: %s\n' "${SKIPPED[*]}"
  if [ "$ALLOW_DB_SKIP" != "1" ]; then
    echo "EMPLOYEE_APP_P1_RELEASE_GATE: INCOMPLETE (run the skipped classes on their own host before claiming a canary)"
    exit 2
  fi
  echo "EMPLOYEE_APP_P1_RELEASE_GATE: PARTIAL (skips acknowledged by ALLOW_DB_SKIP=1)"
  exit 0
fi
echo "EMPLOYEE_APP_P1_RELEASE_GATE: PASS"
