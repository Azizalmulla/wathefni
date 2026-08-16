#!/usr/bin/env bash
# Payroll Wave 4 — staging qualification (close + finance export foundation).
# Does NOT deploy production. Does NOT enable real bank / WPS / PIFSS / EOS / payments / AI.
# Does NOT alter frozen Wave 1 / 2A / 2B / 3 contracts/flows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave4-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs" "$EVID/ui"
printf '%s\n' "$EVID" > /tmp/payroll-w4.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w4.stamp
echo "evidence=$EVID"

cp -a "$ORCH/payroll_close_export_wave4.py" "$EVID/sources/"
cp -a "$ORCH/payroll_payslip_wave3.py" "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/payroll_native_preview_wave2b.py" "$EVID/sources/"
cp -a "$ORCH/payroll_external_adapter_wave2a.py" "$EVID/sources/"
cp -a "$ORCH/payroll_authority_wave1.py" "$EVID/sources/"
cp -a "$ORCH/ops/migrate-payroll-close-export-wave4.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/payroll_close_export_wave4_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-payroll-close-export-wave4.py" "$EVID/tests/"
cp -a "$ORCH/smoke-test-payroll-close-export-wave4-ux.py" "$EVID/tests/"
cp -a "$DASH/src/posthire/CloseExportWorkspace.tsx" "$EVID/ui/" 2>/dev/null || true
cp -a "$DASH/src/posthire/payrollCloseExportUx.ts" "$EVID/ui/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE3_PAYSLIP_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE2B_NATIVE_PREVIEW_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE2A_EXTERNAL_ADAPTER_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE1_FOUNDATION_FREEZE.md" "$EVID/docs/" 2>/dev/null || true

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_close_export_wave4.py" \
  "$ORCH/payroll_payslip_wave3.py" \
  "$ORCH/payroll_native_preview_wave2b.py" \
  "$ORCH/payroll_external_adapter_wave2a.py" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/smoke-test-payroll-close-export-wave4.py" \
  "$ORCH/smoke-test-payroll-close-export-wave4-ux.py" \
  "$ORCH/smoke-test-payroll-payslip-wave3.py" \
  "$ORCH/smoke-test-payroll-native-preview-wave2b.py" \
  "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql /opt/wathefni/apps/wathefni-dashboard/src/posthire"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-payroll-close-export-wave4.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/payroll_close_export_wave4_v1.sql" \
  "$ORCH/ops/sql/payroll_payslip_wave3_v1.sql" \
  "$ORCH/ops/sql/payroll_native_preview_wave2b_v1.sql" \
  "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" \
  "$ORCH/ops/sql/payroll_authority_wave1_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/posthire/CloseExportWorkspace.tsx" \
  "$DASH/src/posthire/payrollCloseExportUx.ts" \
  "$DASH/src/posthire/PayslipWorkspace.tsx" \
  "$DASH/src/posthire/payrollPayslipUx.ts" \
  "$DASH/src/posthire/payrollExternalUx.ts" \
  "$DASH/src/posthire/PostHire.tsx" \
  "root@$HOST:/opt/wathefni/apps/wathefni-dashboard/src/posthire/"

# Enable Wave 4 on staging via drop-in (does not touch prior payroll drop-ins)
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
# Capture pre-wave4 drop-in list for rollback proof
ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/ | tee /tmp/payroll-w4-dropins-before.txt
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzz-payroll-wave4-close-export.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE4=1
Environment=WATHEFNI_PAYROLL_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS=PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
EOF
# Ensure prior waves remain enabled for sources
if [[ ! -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-payroll-wave2b-preview.conf ]]; then
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-payroll-wave2b-preview.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE2B=1
Environment=WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS=PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,PYW3,PYW4
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES=965541,965539
EOF
fi
if [[ ! -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzz-payroll-wave3-payslip.conf ]]; then
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzz-payroll-wave3-payslip.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE3=1
Environment=WATHEFNI_PAYROLL_WAVE3_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS=PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,PYW4
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
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
export WATHEFNI_PAYROLL_WAVE4=1
export WATHEFNI_PAYROLL_WAVE4_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-payroll-close-export-wave4.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-payroll-close-export-wave4.sh | tee /tmp/payroll-w4-migrate.out
"\$PY" smoke-test-payroll-close-export-wave4.py | tee /tmp/payroll-w4-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w4-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-close-export-wave4-ux.py | tee /tmp/payroll-w4-ux.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w4-ux.out; then
  echo UX_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-payslip-wave3.py | tee /tmp/payroll-w3-regression-w4.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w3-regression-w4.out; then
  echo W3_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-native-preview-wave2b.py | tee /tmp/payroll-w2b-regression-w4.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2b-regression-w4.out; then
  echo W2B_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/payroll-w2a-regression-w4.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2a-regression-w4.out; then
  echo W2A_REGRESSION_FAILED
  exit 1
fi
"\$PY" - <<'PY'
import payroll_close_export_wave4 as w
h=w.honesty_payload()
assert h["payment_processing"]=="disabled" and h["posts_payment"] is False
assert h["bank_files"] is False and h["bank_connection"] is False
assert h["wps"] is False and h["ashal"] is False
assert h["journals"] is False and h["journal_drafts"] is True
assert h["bank_export_contract"] is True
assert h["pifss"] is False and h["eos"] is False and h["ai_calculations"] is False
assert h["native_results_authoritative"] is False and h["external_payroll_authority"]=="external"
inv=w.freeze_invariants()
assert inv["closed_runs_immutable"] and inv["reopen_requires_dual_approval"]
assert inv["sod_approve_close_export"] and inv["journal_must_balance"]
print("HONESTY_OK")
PY
echo STAGING_PAYROLL_W4_OK
REMOTE

# Rollback proof: remove Wave 4 drop-in, restart, assert flags cleared, then restore
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<'REMOTE' | tee "$EVID/remote/rollback.out"
set -euo pipefail
rm -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzz-payroll-wave4-close-export.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then break; fi
  sleep 1
done
# Confirm Wave 4 env cleared from process
if systemctl show wathefni-orchestrator-staging.service -p Environment --value | grep -q 'WATHEFNI_PAYROLL_WAVE4=1'; then
  echo ROLLBACK_FAILED_WAVE4_STILL_SET
  exit 1
fi
echo WAVE4_FLAGS_CLEARED
# Redeploy drop-in for continued staging use after qualify
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzz-payroll-wave4-close-export.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE4=1
Environment=WATHEFNI_PAYROLL_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS=PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo REDEPLOY_OK; exit 0; fi
  sleep 1
done
exit 1
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w4-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w4-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w4-ux.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w3-regression-w4.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2b-regression-w4.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-regression-w4.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w4-dropins-before.txt" "$EVID/remote/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-payroll-close-export-wave4-ux.py 2>&1 | tee "$EVID/tests/ux-local.out" | tail -20
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -5
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -5

{
  echo "# Payroll Wave 4 staging qualify"
  echo "stamp=$STAMP"
  echo "evidence=$EVID"
  echo "payment_processing=disabled"
  echo "bank_files=false"
  echo "bank_connection=false"
  echo "wps=false"
  echo "ashal=false"
  echo "journals=false"
  echo "journal_drafts=true"
  echo "bank_export_contract=true"
  echo "pifss=false"
  echo "eos=false"
  echo "ai_calculations=false"
  echo "native_results_authoritative=false"
  echo "external_payroll_authority=external"
  echo "production_deploy=false"
  echo "prod_synthetic_gate=NO-GO (staging-only wave; requires Wave 4-B prod synthetic path)"
  echo "GATE=STAGING_PAYROLL_WAVE4_CLOSE_EXPORT_GO"
} | tee "$EVID/docs/GATE.txt"

cat > "$EVID/REPORT.md" <<EOF
# Payroll Wave 4 — Staging Qualify Report

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/payroll-wave4-${STAMP}/\`  
**Scope:** Close + finance export foundation (journal drafts + bank-export contract validation)

## Verdict

| Gate | Result |
|------|--------|
| Staging Wave 4 close/export foundation | **GO** (if smoke green — see tests/) |
| Production synthetic qualification | **NO-GO** |

## Honesty

- \`payment_processing=disabled\`
- Journal drafts only (no ERP posting)
- Bank-export **contract validation only** (no real bank format/connection)
- No WPS/AS'HAL, PIFSS, EOS, payments, or AI
- Native results remain preview/non-authoritative
- External payroll remains money authority

## Proven

- Review → approve → close workflow
- Immutable closed-run snapshot
- SOD for approve / close / export
- Controlled reopen with dual approval
- Balanced journal validation + invalid mappings fail closed
- Export history / approvals / fingerprints / reconciliation
- Export idempotency + fingerprint drift
- Rollback (Wave 4 drop-in cleared then restored)
- Prior payroll wave regressions + sibling freezes

## Explicit NO-GO

- Production synthetic / production deploy of Wave 4
- Real bank integrations, WPS/AS'HAL submission
- PIFSS or EOS calculations
- Payment execution / AI
EOF

cp -a "$EVID/REPORT.md" "$EVID/docs/REPORT.md"
echo "REPORT_WRITTEN $EVID/REPORT.md"
echo "QUALIFY_DONE evidence=$EVID"
