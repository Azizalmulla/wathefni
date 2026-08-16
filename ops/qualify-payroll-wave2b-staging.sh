#!/usr/bin/env bash
# Payroll Wave 2B — staging qualification (native preview engine).
# Does NOT deploy production. Does NOT enable money / bank / PIFSS / payslips.
# Does NOT alter frozen Wave 1 or Wave 2A contracts/flows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave2b-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs"
printf '%s\n' "$EVID" > /tmp/payroll-w2b.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w2b.stamp
echo "evidence=$EVID"

cp -a "$ORCH/payroll_native_preview_wave2b.py" "$EVID/sources/"
cp -a "$ORCH/payroll_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/payroll_external_adapter_wave2a.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-payroll-native-preview-wave2b.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/payroll_native_preview_wave2b_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-payroll-native-preview-wave2b.py" "$EVID/tests/"

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_native_preview_wave2b.py" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/payroll_external_adapter_wave2a.py" \
  "$ORCH/smoke-test-payroll-native-preview-wave2b.py" \
  "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-payroll-native-preview-wave2b.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/payroll_native_preview_wave2b_v1.sql" \
  "$ORCH/ops/sql/payroll_authority_wave1_v1.sql" \
  "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"

# Enable Wave 2B on staging via drop-in (does not touch Wave 2A drop-in)
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-payroll-wave2b-preview.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE2B=1
Environment=WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS=PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES=965541,965539
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo health_ok; systemctl is-active wathefni-orchestrator-staging.service; exit 0; fi
  sleep 1
done
systemctl status wathefni-orchestrator-staging.service --no-pager -l | head -40
exit 1
REMOTE

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
export WATHEFNI_PAYROLL_WAVE2B=1
export WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-payroll-native-preview-wave2b.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-payroll-native-preview-wave2b.sh | tee /tmp/payroll-w2b-migrate.out
"\$PY" smoke-test-payroll-native-preview-wave2b.py | tee /tmp/payroll-w2b-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2b-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
# Prove Wave 2A regression still green (external flows unchanged)
"\$PY" smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/payroll-w2a-regression-w2b.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2a-regression-w2b.out; then
  echo W2A_REGRESSION_FAILED
  exit 1
fi
# Honesty surface
"\$PY" - <<'PY'
import payroll_native_preview_wave2b as w
h=w.honesty_payload()
assert h["authoritative"] is False and h["payment_processing"]=="disabled"
assert h["preview_only"] is True and h["ai_calculations"] is False
assert "pifss" in h["unsupported_rules"]
print("HONESTY_OK")
PY
echo STAGING_PAYROLL_W2B_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2b-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2b-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-regression-w2b.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -5
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -5

{
  echo "# Payroll Wave 2B staging qualify"
  echo "stamp=$STAMP"
  echo "evidence=$EVID"
  echo "payment_processing=disabled"
  echo "authoritative=false"
  echo "preview_only=true"
  echo "ai_calculations=false"
  echo "external_flows_unchanged=true"
  echo "payslips=false"
  echo "production_deploy=false"
  echo "prod_synthetic_gate=NO-GO (staging-only wave; requires Wave 2B-B prod synthetic path)"
} | tee "$EVID/docs/GATE.txt"

cat > "$EVID/REPORT.md" <<EOF
# Payroll Wave 2B — Staging Qualify Report

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/payroll-wave2b-${STAMP}/\`  
**Scope:** Native payroll preview engine (deterministic, non-authoritative)

## Verdict

| Gate | Result |
|------|--------|
| Staging Wave 2B native preview | **GO** (if smoke green — see tests/) |
| Production synthetic qualification | **NO-GO** |

## Proven

- Full-month salary, mid-month join/exit proration
- Unpaid leave deduction, fixed allowance/deduction, one-time adjustments
- Missing/overlapping contract fail-closed
- Idempotent calculation + recalculation after input change
- KWD 3dp ROUND_HALF_UP
- Unsupported PIFSS/OT/sick/EOS/holiday blocked as review_only
- Rollback + audit events
- Wave 2A external regression green; sibling freezes

## Holds

- \`payment_processing=disabled\`, previews non-authoritative
- No bank/WPS/PIFSS remittance/EOS/journals/payslips/payments
- No AI calculations; no Wave 1/2A contract changes
- No payslip or payment execution started
EOF

echo "QUALIFY_DONE evidence=$EVID"
