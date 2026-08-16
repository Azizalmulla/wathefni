#!/usr/bin/env bash
# Payroll Wave 5 — staging qualification (PIFSS + EOS review worksheets).
# Does NOT deploy production. Does NOT enable remittance / filing / payments / bank / WPS / AS’HAL / AI.
# Does NOT alter frozen Wave 1 / 2A / 2B / 3 / 4 contracts/flows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
DASH="$ROOT/apps/wathefni-dashboard"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/payroll-wave5-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
POSTGRES_ENV="${POSTGRES_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
ACK_DB_DEFAULT=wathefni_staging

mkdir -p "$EVID/sources" "$EVID/migrate" "$EVID/tests" "$EVID/remote" "$EVID/verify" "$EVID/docs" "$EVID/ui"
printf '%s\n' "$EVID" > /tmp/payroll-w5.evid
printf '%s\n' "$STAMP" > /tmp/payroll-w5.stamp
echo "evidence=$EVID"

cp -a "$ORCH/payroll_pifss_eos_wave5.py" "$EVID/sources/"
cp -a "$ORCH/payroll_close_export_wave4.py" "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/payroll_payslip_wave3.py" "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/payroll_native_preview_wave2b.py" "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/payroll_external_adapter_wave2a.py" "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/payroll_authority_wave1.py" "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/ops/migrate-payroll-pifss-eos-wave5.sh" "$EVID/migrate/"
cp -a "$ORCH/ops/sql/payroll_pifss_eos_wave5_v1.sql" "$EVID/migrate/"
cp -a "$ORCH/smoke-test-payroll-pifss-eos-wave5.py" "$EVID/tests/"
cp -a "$ORCH/smoke-test-payroll-pifss-eos-wave5-ux.py" "$EVID/tests/"
cp -a "$DASH/src/posthire/StatutoryWorksheetWorkspace.tsx" "$EVID/ui/" 2>/dev/null || true
cp -a "$DASH/src/posthire/payrollStatutoryUx.ts" "$EVID/ui/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE4_CLOSE_EXPORT_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE3_PAYSLIP_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE2B_NATIVE_PREVIEW_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE2A_EXTERNAL_ADAPTER_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/PAYROLL_WAVE1_FOUNDATION_FREEZE.md" "$EVID/docs/" 2>/dev/null || true
cp -a "$ROOT/ops/qualify-payroll-wave5-staging.sh" "$EVID/sources/" 2>/dev/null || true

ssh -o BatchMode=yes "root@$HOST" "test -d $REMOTE_ORCH"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/payroll_pifss_eos_wave5.py" \
  "$ORCH/payroll_close_export_wave4.py" \
  "$ORCH/payroll_payslip_wave3.py" \
  "$ORCH/payroll_native_preview_wave2b.py" \
  "$ORCH/payroll_external_adapter_wave2a.py" \
  "$ORCH/payroll_authority_wave1.py" \
  "$ORCH/smoke-test-payroll-pifss-eos-wave5.py" \
  "$ORCH/smoke-test-payroll-pifss-eos-wave5-ux.py" \
  "$ORCH/smoke-test-payroll-close-export-wave4.py" \
  "$ORCH/smoke-test-payroll-payslip-wave3.py" \
  "$ORCH/smoke-test-payroll-native-preview-wave2b.py" \
  "$ORCH/smoke-test-payroll-external-adapter-wave2a.py" \
  "$ORCH/app.py" \
  "root@$HOST:$REMOTE_ORCH/"
ssh -o BatchMode=yes "root@$HOST" "mkdir -p $REMOTE_ORCH/ops/sql /opt/wathefni/apps/wathefni-dashboard/src/posthire"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/migrate-payroll-pifss-eos-wave5.sh" \
  "root@$HOST:$REMOTE_ORCH/ops/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/ops/sql/payroll_pifss_eos_wave5_v1.sql" \
  "$ORCH/ops/sql/payroll_close_export_wave4_v1.sql" \
  "$ORCH/ops/sql/payroll_payslip_wave3_v1.sql" \
  "$ORCH/ops/sql/payroll_native_preview_wave2b_v1.sql" \
  "$ORCH/ops/sql/payroll_external_adapter_wave2a_v1.sql" \
  "$ORCH/ops/sql/payroll_authority_wave1_v1.sql" \
  "root@$HOST:$REMOTE_ORCH/ops/sql/"
rsync -az -e "ssh -o BatchMode=yes" \
  "$DASH/src/posthire/StatutoryWorksheetWorkspace.tsx" \
  "$DASH/src/posthire/payrollStatutoryUx.ts" \
  "$DASH/src/posthire/CloseExportWorkspace.tsx" \
  "$DASH/src/posthire/payrollCloseExportUx.ts" \
  "$DASH/src/posthire/PayslipWorkspace.tsx" \
  "$DASH/src/posthire/payrollPayslipUx.ts" \
  "$DASH/src/posthire/payrollExternalUx.ts" \
  "$DASH/src/posthire/PostHire.tsx" \
  "root@$HOST:/opt/wathefni/apps/wathefni-dashboard/src/posthire/"

# Enable Wave 5 on staging via drop-in (does not touch prior payroll drop-ins)
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
ls /etc/systemd/system/wathefni-orchestrator-staging.service.d/ | tee /tmp/payroll-w5-dropins-before.txt
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzzz-payroll-wave5-pifss-eos.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE5=1
Environment=WATHEFNI_PAYROLL_WAVE5_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_KEY_MARKERS=PYW5,PYW5-SYNTH|,PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4,W5
Environment=WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
EOF
# Ensure prior waves remain enabled for sources / regressions
if [[ ! -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-payroll-wave2b-preview.conf ]]; then
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzz-payroll-wave2b-preview.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE2B=1
Environment=WATHEFNI_PAYROLL_WAVE2B_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS=PYW2B,PYW2B-SYNTH|,PYW1,PYW1-SYNTH|,PYW3,PYW4,PYW5
Environment=WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES=965541,965539
EOF
fi
if [[ ! -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzz-payroll-wave3-payslip.conf ]]; then
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzz-payroll-wave3-payslip.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE3=1
Environment=WATHEFNI_PAYROLL_WAVE3_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_KEY_MARKERS=PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,PYW4,PYW5
Environment=WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
EOF
fi
if [[ ! -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzz-payroll-wave4-close-export.conf ]]; then
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzz-payroll-wave4-close-export.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE4=1
Environment=WATHEFNI_PAYROLL_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_KEY_MARKERS=PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4,PYW5
Environment=WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
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
export WATHEFNI_PAYROLL_WAVE5=1
export WATHEFNI_PAYROLL_WAVE5_COMPANIES=WATHEFNI
export WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY=1
PY="/opt/wathefni/orchestrator/.venv/bin/python"
test -x "\$PY" || PY=python3
chmod +x ops/migrate-payroll-pifss-eos-wave5.sh
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$PY" bash ops/migrate-payroll-pifss-eos-wave5.sh | tee /tmp/payroll-w5-migrate.out
"\$PY" smoke-test-payroll-pifss-eos-wave5.py | tee /tmp/payroll-w5-smoke.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w5-smoke.out; then
  echo SMOKE_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-pifss-eos-wave5-ux.py | tee /tmp/payroll-w5-ux.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w5-ux.out; then
  echo UX_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-close-export-wave4.py | tee /tmp/payroll-w4-regression-w5.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w4-regression-w5.out; then
  echo W4_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-payslip-wave3.py | tee /tmp/payroll-w3-regression-w5.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w3-regression-w5.out; then
  echo W3_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-native-preview-wave2b.py | tee /tmp/payroll-w2b-regression-w5.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2b-regression-w5.out; then
  echo W2B_REGRESSION_FAILED
  exit 1
fi
"\$PY" smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/payroll-w2a-regression-w5.out
if grep -E '[1-9][0-9]* failed' /tmp/payroll-w2a-regression-w5.out; then
  echo W2A_REGRESSION_FAILED
  exit 1
fi
"\$PY" - <<'PY'
import payroll_pifss_eos_wave5 as w
h=w.honesty_payload()
assert h["payment_processing"]=="disabled" and h["posts_payment"] is False
assert h["remittance"] is False and h["statutory_filing"] is False
assert h["automatic_legal_compliance_claim"] is False
assert h["pifss_worksheets"] is True and h["pifss_remittance"] is False
assert h["eos_worksheets"] is True and h["eos_auto_payable"] is False
assert h["bank_files"] is False and h["wps"] is False and h["ashal"] is False
assert h["ai_calculations"] is False
assert h["native_results_authoritative"] is False and h["external_payroll_authority"]=="external"
inv=w.freeze_invariants()
assert inv["missing_rule_fail_closed"] and inv["approved_history_immutable"]
assert inv["category_separation"] and inv["effective_dated_rules"]
assert inv["dual_approval_override"] and inv["no_remittance"] and inv["no_auto_payable"]
print("HONESTY_OK")
PY
echo STAGING_PAYROLL_W5_OK
REMOTE

# Rollback proof: remove Wave 5 drop-in, restart, assert flags cleared, then restore
ssh -o BatchMode=yes "root@$HOST" "bash -s" <<'REMOTE' | tee "$EVID/remote/rollback.out"
set -euo pipefail
rm -f /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzzz-payroll-wave5-pifss-eos.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then break; fi
  sleep 1
done
if systemctl show wathefni-orchestrator-staging.service -p Environment --value | grep -q 'WATHEFNI_PAYROLL_WAVE5=1'; then
  echo ROLLBACK_FAILED_WAVE5_STILL_SET
  exit 1
fi
echo WAVE5_FLAGS_CLEARED
# Redeploy drop-in for continued staging use after qualify
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzzz-payroll-wave5-pifss-eos.conf <<'EOF'
[Service]
Environment=WATHEFNI_PAYROLL_WAVE5=1
Environment=WATHEFNI_PAYROLL_WAVE5_COMPANIES=WATHEFNI
Environment=WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY=1
Environment=WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_KEY_MARKERS=PYW5,PYW5-SYNTH|,PYW4,PYW4-SYNTH|,PYW3,PYW3-SYNTH|,PYW2B,PYW2B-SYNTH|,PYW2A,PYW2ACB,PYW1,PYW1-SYNTH|,W2BB,W3B,W4,W5
Environment=WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_PHONE_PREFIXES=965541,965540,965539
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then echo REDEPLOY_OK; exit 0; fi
  sleep 1
done
exit 1
REMOTE

scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w5-migrate.out" "$EVID/migrate/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w5-smoke.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w5-ux.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w4-regression-w5.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w3-regression-w5.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2b-regression-w5.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w2a-regression-w5.out" "$EVID/tests/" 2>/dev/null || true
scp -o BatchMode=yes "root@$HOST:/tmp/payroll-w5-dropins-before.txt" "$EVID/remote/" 2>/dev/null || true

cd "$ORCH"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-payroll-pifss-eos-wave5-ux.py 2>&1 | tee "$EVID/tests/ux-local.out" | tail -20
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-employees360.out" | tail -5
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onboarding.out" | tail -5
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-attendance.out" | tail -5
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -5
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-shifts.out" | tail -5

{
  echo "# Payroll Wave 5 staging qualify"
  echo "stamp=$STAMP"
  echo "evidence=$EVID"
  echo "payment_processing=disabled"
  echo "remittance=false"
  echo "statutory_filing=false"
  echo "automatic_legal_compliance_claim=false"
  echo "pifss_worksheets=true"
  echo "pifss_remittance=false"
  echo "eos_worksheets=true"
  echo "eos_auto_payable=false"
  echo "bank_files=false"
  echo "wps=false"
  echo "ashal=false"
  echo "ai_calculations=false"
  echo "native_results_authoritative=false"
  echo "external_payroll_authority=external"
  echo "production_deploy=false"
  echo "prod_synthetic_gate=NO-GO (staging-only wave; requires Wave 5-B prod synthetic path)"
  echo "GATE=STAGING_PAYROLL_WAVE5_PIFSS_EOS_GO"
} | tee "$EVID/docs/GATE.txt"

cat > "$EVID/REPORT.md" <<EOF
# Payroll Wave 5 — Staging Qualify Report

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/payroll-wave5-${STAMP}/\`  
**Scope:** Non-authoritative PIFSS + EOS review worksheets (staging only)

## Verdict

| Gate | Result |
|------|--------|
| Staging Wave 5 PIFSS/EOS worksheets | **GO** (if smoke green — see tests/) |
| Production synthetic qualification | **NO-GO** |

## Honesty

- \`payment_processing=disabled\`
- Review worksheets only (no remittance / statutory filing)
- No automatic legal-compliance claim
- No bank / WPS / AS'HAL execution
- EOS never emits automatic payable instruction
- Native results remain non-authoritative
- External payroll remains money authority

## Proven

- Kuwaiti / GCC-national / expatriate category separation
- Missing / unsupported rule fail-closed (\`counsel_required\` / \`unsupported\`)
- Effective-dated counsel-approved rule-table versioning
- Evidence + dual-approval manual override exception path
- Recalculation after source/rule changes (supersede + new draft)
- Approved worksheet history retained (immutable payload; supersede on recalc)
- Rollback (Wave 5 drop-in cleared then restored)
- Prior payroll wave regressions + sibling freezes

## Explicit NO-GO

- Production synthetic / production deploy of Wave 5
- Remittance, payments, or real statutory filing
- Bank / WPS / AS'HAL execution
- Treating worksheets as payable / compliance authority
EOF

cp -a "$EVID/REPORT.md" "$EVID/docs/REPORT.md"
echo "REPORT_WRITTEN $EVID/REPORT.md"
echo "QUALIFY_DONE evidence=$EVID"
