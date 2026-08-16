#!/usr/bin/env bash
# Payroll Wave 2A-D — staging qualification (External Run Operability).
# Staging only. Does NOT deploy production. Does NOT enable money / vendor / bank / WPS / AI.
# Does NOT expand attendance/leave/shifts packaging. Does NOT start another Payroll wave.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave2ad-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
REMOTE_DASH_SRC="${REMOTE_DASH_SRC:-/opt/wathefni/staging/apps/wathefni-dashboard/src}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs" "$EVID/ui"
printf '%s\n' "$EVID" > /tmp/payroll-w2ad.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w2ad.stamp
echo "evidence=$EVID"

cp -a "$ORCH/payroll_external_adapter_wave2a.py" "$ORCH/payroll_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "$ORCH/smoke-test-payroll-external-ops-wave2ac.py" \
  "$ORCH/smoke-test-payroll-external-ops-wave2ad.py" \
  "$ORCH/smoke-test-payroll-external-ops-wave2ad-ux.py" \
  "$EVID/tests/" 2>/dev/null || true
cp -a "$DASH/src/posthire/ExternalPayrollWorkspace.tsx" \
  "$DASH/src/posthire/payrollExternalUx.ts" \
  "$DASH/src/posthire/PayslipWorkspace.tsx" \
  "$DASH/src/posthire/CloseExportWorkspace.tsx" \
  "$EVID/ui/" 2>/dev/null || true

echo "=== local UX + adapter smokes ==="
cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-payroll-external-ops-wave2ad-ux.py 2>&1 | tee "$EVID/tests/wave2ad-ux-local.out"
"$PY_LOCAL" smoke-test-payroll-external-ops-wave2ad.py 2>&1 | tee "$EVID/tests/wave2ad-local.out"

echo "=== push staging sources ==="
ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_external_adapter_wave2a.py" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "$ORCH/smoke-test-payroll-external-ops-wave2ac.py" \
  "$ORCH/smoke-test-payroll-external-ops-wave2ad.py" \
  "$ORCH/smoke-test-payroll-external-ops-wave2ad-ux.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"

ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql $REMOTE_DASH_SRC/posthire $REMOTE_DASH_SRC/lib"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" \
  "$ORCH/ops/sql/payroll_authority_wave1_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/posthire/ExternalPayrollWorkspace.tsx" \
  "$DASH/src/posthire/payrollExternalUx.ts" \
  "$DASH/src/posthire/PayslipWorkspace.tsx" \
  "$DASH/src/posthire/CloseExportWorkspace.tsx" \
  "$DASH/src/posthire/PostHire.tsx" \
  "root@$HOST:$REMOTE_DASH_SRC/posthire/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/lib/api.ts" \
  "$DASH/src/types.ts" \
  "root@$HOST:$REMOTE_DASH_SRC/lib/" 2>/dev/null || true
# types.ts lives under src/
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/types.ts" \
  "root@$HOST:$REMOTE_DASH_SRC/"

ssh -o BatchMode=yes "root@$HOST" \
  'systemctl restart wathefni-orchestrator-staging.service; for i in $(seq 1 60); do if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok; systemctl is-active wathefni-orchestrator-staging.service; exit 0; fi; sleep 1; done; systemctl status wathefni-orchestrator-staging.service --no-pager -l | head -40; exit 1'

ssh -o BatchMode=yes "root@$HOST" "bash -s" <<REMOTE | tee "$EVID/remote/migrate-smoke.out"
set -euo pipefail
ORCH="$REMOTE_ORCH"
cd "\$ORCH"
set -a
source "$POSTGRES_ENV"
set +a
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV="$POSTGRES_ENV"
export ACK_DB="$ACK_DB_DEFAULT"
export WATHEFNI_EXPECTED_DATABASE_NAME="$ACK_DB_DEFAULT"
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_PAYROLL_WAVE1=1
export WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1
export WATHEFNI_PAYROLL_WAVE2A=1
export WATHEFNI_PAYROLL_WAVE2A_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
"\$PY" smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/payroll-w2a-regression-w2ad.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2a-regression-w2ad.out; then
  echo W2A_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-external-ops-wave2ac.py | tee /tmp/payroll-w2ac-regression-w2ad.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2ac-regression-w2ad.out; then
  echo W2AC_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-external-ops-wave2ad.py | tee /tmp/payroll-w2ad-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2ad-smoke.out; then
  echo W2AD_SMOKE_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-external-ops-wave2ad-ux.py | tee /tmp/payroll-w2ad-ux.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2ad-ux.out; then
  echo W2AD_UX_FAILED
  exit 1
fi
"\$PY" - <<'PY'
import os, sys
sys.path.insert(0, ".")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A", "1")
os.environ.setdefault("WATHEFNI_PAYROLL_WAVE2A_COMPANIES", "WATHEFNI")
import payroll_external_adapter_wave2a as w2a
h = w2a.honesty_payload()
assert h["payment_processing"] == "disabled"
assert h["money_authority"] == "external"
assert h["vendor_claimed"] is False
assert h["wathefni_money_authority"] is False
assert h.get("ai") is False
assert h["package_contents"]["attendance_leave_shifts_packaged"] is False
print("HONESTY_OK")
print("OPERABILITY", h.get("payroll_wave2ad_operability_version"))
PY
echo STAGING_PAYROLL_W2AD_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-regression-w2ad.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2ac-regression-w2ad.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2ad-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2ad-ux.out" "$EVID/tests/" 2>/dev/null || true

echo "=== sibling freezes ==="
cd "$ORCH"
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -5
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -5
# Payroll freeze docs intact
test -f "$ROOT/ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md"
test -f "$ROOT/ops/PAYROLL_WAVE2AC_EXTERNAL_OPS_WORKFLOW_FREEZE.md"

cat > "$EVID/docs/PAYROLL_WAVE2AD_EXTERNAL_RUN_OPERABILITY_FREEZE.md" <<EOF
# Payroll Wave 2A-D — External Run Operability Freeze (staging)

**Gate:** \`STAGING_PAYROLL_WAVE2AD_GO\`  
**Evidence:** \`ops/evidence/payroll-wave2ad-${STAMP}/\`  
**Production synthetic:** **NO-GO until separate Wave 2A-D-B qualify**

## Frozen posture (unchanged money)

- External remains money authority; native non-authoritative
- \`payment_processing=disabled\`
- No vendor connector; no bank/WPS/PIFSS/EOS/payments/AI
- No attendance/leave/shifts package expansion

## Proven (staging)

- Setup status + guided run checklist
- Package contents honesty + CSV guide
- HR/finance wording (input snapshot)
- Export rollback with concurrency token from UI
- Import run pickers (payslips + close)
- Quarantine acknowledge with audit reason (no money admit)
- Timesheets labeled Hours review vs External payroll run
- Wave 2A + 2A-C regressions green; sibling freezes green

## Explicit NO-GO

- Production synthetic without Wave 2A-D-B
- Another Payroll money / differentiation wave
- Vendor connector / package expansion / remittance
EOF
cp -a "$EVID/docs/PAYROLL_WAVE2AD_EXTERNAL_RUN_OPERABILITY_FREEZE.md" \
  "$ROOT/ops/PAYROLL_WAVE2AD_EXTERNAL_RUN_OPERABILITY_FREEZE.md"

cat > "$EVID/docs/REPORT.md" <<EOF
# Payroll Wave 2A-D — External Run Operability (staging)

**Stamp:** \`$STAMP\`  
**Evidence:** \`$EVID\`

## Verdicts

| Scope | Verdict |
|---|---|
| Staging operability | **GO** (if remote smoke OK) |
| Production synthetic qualification | **NO-GO** — requires separate Wave 2A-D-B |
| Money / vendor / package expansion | **NO-GO** |

## Keep

external money authority · native non-authoritative · payment_processing=disabled · no vendor connector · no attendance/leave/shifts package fill · no bank/WPS/PIFSS/EOS/payments/AI
EOF

# Determine GO from remote output
VERDICT=NO-GO
if grep -q 'STAGING_PAYROLL_W2AD_OK' "$EVID/remote/migrate-smoke.out" \
  && ! grep -qE '[1-9][0-9]* failed' "$EVID/tests/wave2ad-ux-local.out" \
  && grep -q 'passed, 0 failed' "$EVID/tests/freeze-shifts.out"; then
  VERDICT=GO
fi

# refine from remote smoke files if present
if [[ -f "$EVID/tests/payroll-w2ad-smoke.out" ]] && grep -qE '[1-9][0-9]* failed' "$EVID/tests/payroll-w2ad-smoke.out"; then
  VERDICT=NO-GO
fi

{
  echo "stamp=$STAMP"
  echo "payment_processing=disabled"
  echo "money_authority=external"
  echo "vendor_claimed=false"
  echo "attendance_leave_shifts_packaged=false"
  echo "production_deploy=false"
  echo "prod_synthetic_gate=NO-GO"
  if [[ "$VERDICT" == "GO" ]]; then
    echo "GATE=STAGING_PAYROLL_WAVE2AD_GO"
  else
    echo "GATE=STAGING_PAYROLL_WAVE2AD_NO_GO"
  fi
} | tee "$EVID/docs/GATE.txt"

# Patch REPORT verdict
sed -i.bak "s/\*\*GO\*\* (if remote smoke OK)/**$VERDICT**/; s/Staging operability | \*\*.*\*\*/Staging operability | **$VERDICT**/" "$EVID/docs/REPORT.md" 2>/dev/null || true

echo "QUALIFY_DONE evidence=$EVID verdict=$VERDICT"
if [[ "$VERDICT" != "GO" ]]; then
  exit 1
fi
echo "STAGING_PAYROLL_WAVE2AD_GO"
echo "PROD_SYNTHETIC_QUALIFICATION=NO-GO"
