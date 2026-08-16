#!/usr/bin/env bash
# Payroll Wave 3 — staging qualification (payslips display).
# Does NOT deploy production. Does NOT enable money / bank / PIFSS / payments.
# Does NOT alter frozen Wave 1 / 2A / 2B contracts/flows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave3-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs" "$EVID/ui"
printf '%s\n' "$EVID" > /tmp/payroll-w3.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w3.stamp
echo "evidence=$EVID"

cp -a "$ORCH/payroll_payslip_wave3.py" "$EVID/sources/"
cp -a "$ORCH/payroll_native_preview_wave2b.py" "$EVID/sources/"
cp -a "$ORCH/payroll_external_adapter_wave2a.py" "$EVID/sources/"
cp -a "$ORCH/payroll_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-payroll-payslip-wave3.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/payroll_payslip_wave3_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-payroll-payslip-wave3.py" "$EVID/tests/"
cp -a "$ORCH/smoke-test-payroll-payslip-wave3-ux.py" "$EVID/tests/"
cp -a "$DASH/src/posthire/PayslipWorkspace.tsx" "$EVID/ui/" 2>/dev/null || true
cp -a "$DASH/src/posthire/payrollPayslipUx.ts" "$EVID/ui/" 2>/dev/null || true

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_payslip_wave3.py" \
  "$ORCH/payroll_native_preview_wave2b.py" \
  "$ORCH/payroll_external_adapter_wave2a.py" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/smoke-test-payroll-payslip-wave3.py" \
  "$ORCH/smoke-test-payroll-payslip-wave3-ux.py" \
  "$ORCH/smoke-test-payroll-native-preview-wave2b.py" \
  "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql /opt/wathefni/apps/wathefni-dashboard/src/posthire"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-payroll-payslip-wave3.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/payroll_payslip_wave3_v1.sql" \
  "$ORCH/ops/sql/payroll_native_preview_wave2b_v1.sql" \
  "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" \
  "$ORCH/ops/sql/payroll_authority_wave1_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/posthire/PayslipWorkspace.tsx" \
  "$DASH/src/posthire/payrollPayslipUx.ts" \
  "$DASH/src/posthire/payrollExternalUx.ts" \
  "$DASH/src/posthire/PostHire.tsx" \
  "root@$HOST:/opt/wathefni/apps/wathefni-dashboard/src/posthire/"

# Enable Wave 3 on staging via drop-in (does not touch Wave 2B/2A drop-ins)
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzz-payroll-wave3-payslip.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE3=1
Environment=WATHEFNI_PAYROLL_WAVE3_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS=PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
EOF
# Ensure Wave 2B remains enabled for native source
if [[ ! -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-payroll-wave2b-preview.conf ]]; then
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-payroll-wave2b-preview.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE2B=1
Environment=WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS=PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,PYW3
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES=965541,965539
EOF
fi
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
export WATHEFNI_PAYROLL_WAVE3=1
export WATHEFNI_PAYROLL_WAVE3_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-payroll-payslip-wave3.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-payroll-payslip-wave3.sh | tee /tmp/payroll-w3-migrate.out
"\$PY" smoke-test-payroll-payslip-wave3.py | tee /tmp/payroll-w3-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w3-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-payslip-wave3-ux.py | tee /tmp/payroll-w3-ux.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w3-ux.out; then
  echo UX_FAILED
  exit 1
fi
# Prior wave regressions (staging smokes refuse prod DB by design)
"\$PY" smoke-test-payroll-native-preview-wave2b.py | tee /tmp/payroll-w2b-regression-w3.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2b-regression-w3.out; then
  echo W2B_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/payroll-w2a-regression-w3.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2a-regression-w3.out; then
  echo W2A_REGRESSION_FAILED
  exit 1
fi
"\$PY" - <<'PY'
import payroll_payslip_wave3 as w
h=w.honesty_payload()
assert h["payment_processing"]=="disabled" and h["payslips_as_money"] is False
assert h["native_payslips_authoritative"] is False and h["external_payslips_authority"]=="external"
assert h["ai_calculations"] is False and h["bank_files"] is False
print("HONESTY_OK")
PY
echo STAGING_PAYROLL_W3_OK
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w3-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w3-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w3-ux.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2b-regression-w3.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-regression-w3.out" "$EVID/tests/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-payroll-payslip-wave3-ux.py 2>&1 | tee "$EVID/tests/ux-local.out" | tail -20
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -5
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -5

{
  echo "# Payroll Wave 3 staging qualify"
  echo "stamp=$STAMP"
  echo "evidence=$EVID"
  echo "payment_processing=disabled"
  echo "payslips_as_money=false"
  echo "native_payslips_authoritative=false"
  echo "external_payslips_authority=external"
  echo "ai_calculations=false"
  echo "bank_files=false"
  echo "production_deploy=false"
  echo "prod_synthetic_gate=NO-GO (staging-only wave; requires Wave 3-B prod synthetic path)"
} | tee "$EVID/docs/GATE.txt"

cat > "$EVID/REPORT.md" <<EOF
# Payroll Wave 3 — Staging Qualify Report

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/payroll-wave3-${STAMP}/\`  
**Scope:** Payslip documents (native preview + external mirror)

## Verdict

| Gate | Result |
|------|--------|
| Staging Wave 3 payslips | **GO** (if smoke green — see tests/) |
| Production synthetic qualification | **NO-GO** |

## Proven

- Native preview payslip generation (non-authoritative)
- External import payslip generation (external money authority)
- Permission / employee-scope enforcement
- Duplicate/idempotent generation
- Replace + revoke with history retained
- EN/AR download + mobile UX
- Wave 2A/2B regression + sibling freezes

## Holds

- \`payment_processing=disabled\`, payslips are not money
- No bank/WPS/PIFSS/EOS/journals/payments/AI
- No frozen Wave 1/2A/2B contract or flow changes
- Bank files and payment execution not started
EOF

echo "QUALIFY_DONE evidence=$EVID"
