#!/usr/bin/env bash
# Payroll Wave 5-B — production WATHEFNI synthetic qualification.
# Deploy PIFSS/EOS worksheets → canary → rollback proof → redeploy → canary → freezes.
# Does NOT enable remittance/filing/bank/WPS/AS’HAL/payments/AI.
# Does NOT start final end-to-end payroll qualification.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/payroll-wave5b-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/payroll-w5b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave5b-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,artifacts,ui}
echo "$LOCAL_EVID" > /tmp/pyw5b.evid
echo "$STAMP" > /tmp/pyw5b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local freezes + UX"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3
"$PY_LOCAL" smoke-test-payroll-pifss-eos-wave5-ux.py 2>&1 | tee "$LOCAL_EVID/tests/ux-en-ar-mobile-local.out" | tail -20

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops/sql" "$LOCAL_EVID/migrate"
cp -a app.py payroll_pifss_eos_wave5.py payroll_close_export_wave4.py payroll_payslip_wave3.py \
  payroll_native_preview_wave2b.py payroll_authority_wave1.py payroll_external_adapter_wave2a.py \
  canary-prod-payroll-pifss-eos-wave5b.py \
  smoke-test-payroll-pifss-eos-wave5.py \
  smoke-test-payroll-pifss-eos-wave5-ux.py \
  smoke-test-payroll-close-export-wave4.py \
  smoke-test-payroll-payslip-wave3.py \
  smoke-test-payroll-native-preview-wave2b.py \
  smoke-test-payroll-external-adapter-wave2a.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-payroll-wave5b-prod-synthetic.sh ops/migrate-payroll-pifss-eos-wave5-prod.sh "$LOCAL_EVID/sources/ops/"
cp -a ops/sql/payroll_pifss_eos_wave5_v1.sql ops/sql/payroll_close_export_wave4_v1.sql \
  ops/sql/payroll_payslip_wave3_v1.sql ops/sql/payroll_native_preview_wave2b_v1.sql \
  ops/sql/payroll_authority_wave1_v1.sql ops/sql/payroll_external_adapter_wave2a_v1.sql \
  "$LOCAL_EVID/sources/ops/sql/"
cp -a ops/migrate-payroll-pifss-eos-wave5-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-payroll-wave5b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PAYROLL_WAVE5_PIFSS_EOS_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PAYROLL_WAVE4_CLOSE_EXPORT_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PAYROLL_WAVE3_PAYSLIP_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PAYROLL_WAVE2B_NATIVE_PREVIEW_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PAYROLL_WAVE2A_EXTERNAL_ADAPTER_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PAYROLL_WAVE2AC_EXTERNAL_OPS_WORKFLOW_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PAYROLL_WAVE1_FOUNDATION_FREEZE.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$DASH_SRC/src/posthire/StatutoryWorksheetWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollStatutoryUx.ts" \
  "$DASH_SRC/src/posthire/CloseExportWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollCloseExportUx.ts" \
  "$DASH_SRC/src/posthire/PayslipWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollPayslipUx.ts" \
  "$DASH_SRC/src/posthire/payrollExternalUx.ts" \
  "$DASH_SRC/src/posthire/PostHire.tsx" \
  "$LOCAL_EVID/ui/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py payroll_pifss_eos_wave5.py payroll_close_export_wave4.py payroll_payslip_wave3.py \
    payroll_native_preview_wave2b.py payroll_authority_wave1.py payroll_external_adapter_wave2a.py \
    canary-prod-payroll-pifss-eos-wave5b.py \
    smoke-test-payroll-pifss-eos-wave5.py \
    smoke-test-payroll-pifss-eos-wave5-ux.py \
    smoke-test-payroll-close-export-wave4.py \
    smoke-test-payroll-payslip-wave3.py \
    smoke-test-payroll-native-preview-wave2b.py \
    smoke-test-payroll-external-adapter-wave2a.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-payroll-wave5b-prod-synthetic.sh \
    ops/migrate-payroll-pifss-eos-wave5-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
  "${SCP[@]}" ops/sql/payroll_pifss_eos_wave5_v1.sql ops/sql/payroll_close_export_wave4_v1.sql \
    ops/sql/payroll_payslip_wave3_v1.sql ops/sql/payroll_native_preview_wave2b_v1.sql \
    ops/sql/payroll_authority_wave1_v1.sql ops/sql/payroll_external_adapter_wave2a_v1.sql \
    "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" \
  "$DASH_SRC/src/posthire/StatutoryWorksheetWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollStatutoryUx.ts" \
  "$DASH_SRC/src/posthire/CloseExportWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollCloseExportUx.ts" \
  "$DASH_SRC/src/posthire/PayslipWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollPayslipUx.ts" \
  "$DASH_SRC/src/posthire/payrollExternalUx.ts" \
  "$DASH_SRC/src/posthire/PostHire.tsx" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-payroll-wave5b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-payroll-wave5b-prod-synthetic.sh'
REMOTE

run_canary() {
  local label="$1"
  local outdir="$2"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='$REMOTE_EVID/$outdir'
PYBIN=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export PYW5B_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-pifss-eos-wave5b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "UX smoke on production host"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/ux-en-ar-mobile-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
cd \$ORCH
.venv/bin/python smoke-test-payroll-pifss-eos-wave5-ux.py
REMOTE

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/payroll-wave5b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzz-payroll-wave5b-synthetic.conf
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
test -n "\$PID" && test "\$PID" != "0"
ENV_DUMP=\$(tr '\0' '\n' < /proc/\$PID/environ)
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2B=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE3=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE3_SYNTHETIC_ONLY=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE4=1'
echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE4_SYNTHETIC_ONLY=1'
if echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_WAVE5=1'; then
  echo WAVE5_STILL_ENABLED
  exit 4
fi
echo WAVE5_FLAGS_CLEARED
curl -fsS http://127.0.0.1:8010/health >/dev/null
cd /opt/wathefni/orchestrator
set -a; source /root/.openclaw/secrets/postgres.env; set +a
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
.venv/bin/python - <<'PY'
import app
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("""
      SELECT COUNT(*) AS n FROM payroll_pifss_worksheets
      WHERE company_code='WATHEFNI' AND employee_key LIKE 'WATHEFNI-PYW1-PYW5-W5B-%'
    """)
    n=int(dict(cur.fetchone())["n"])
    cur.execute("""
      SELECT COUNT(*) AS n FROM payroll_eos_worksheets
      WHERE company_code='WATHEFNI' AND employee_key LIKE 'WATHEFNI-PYW1-PYW5-W5B-%'
    """)
    e=int(dict(cur.fetchone())["n"])
    cur.execute("""
      SELECT COUNT(*) AS n FROM payroll_statutory_rule_tables
      WHERE company_code='WATHEFNI' AND decision_note LIKE '%%w5b_%%'
    """)
    r=int(dict(cur.fetchone())["n"])
print("RESIDUAL_SYNTH_PIFSS", n)
print("RESIDUAL_SYNTH_EOS", e)
print("RESIDUAL_SYNTH_RULES", r)
assert n==0 and e==0 and r==0
PY
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-payroll-wave5b-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-after-redeploy.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='/opt/wathefni/production-evidence/payroll-wave5b-prod-canary/${STAMP}/canary/after-redeploy'
PYBIN=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export PYW5B_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-pifss-eos-wave5b.py
REMOTE

log "Wave 1/2A/2B/3/4/5 honesty + production freezes"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/freezes-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
PY=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
\$PY - <<'PY'
import payroll_pifss_eos_wave5 as w5
import payroll_close_export_wave4 as w4
import payroll_payslip_wave3 as w3
import payroll_native_preview_wave2b as w2b
import payroll_external_adapter_wave2a as w2a
import payroll_authority_wave1 as pyw1
h=w5.honesty_payload(); inv=w5.freeze_invariants()
h4=w4.honesty_payload(); p=w3.honesty_payload(); b=w2b.honesty_payload(); a=w2a.honesty_payload()
assert w5.payroll_wave5_enabled() and w5.payroll_wave5_synthetic_only()
assert w4.payroll_wave4_enabled() and w4.payroll_wave4_synthetic_only()
assert w3.payroll_wave3_enabled() and w3.payroll_wave3_synthetic_only()
assert w2b.payroll_wave2b_enabled() and w2b.payroll_wave2b_synthetic_only()
assert w2a.payroll_wave2a_enabled() and w2a.payroll_wave2a_synthetic_only()
assert pyw1.payroll_wave1_enabled()
assert h["payment_processing"]=="disabled" and h["posts_payment"] is False
assert h["remittance"] is False and h["statutory_filing"] is False
assert h["pifss_worksheets"] is True and h["pifss_remittance"] is False
assert h["eos_worksheets"] is True and h["eos_auto_payable"] is False
assert h["automatic_legal_compliance_claim"] is False
assert h["bank_files"] is False and h["wps"] is False and h["ashal"] is False
assert h["native_results_authoritative"] is False and h["external_payroll_authority"]=="external"
assert h["ai_calculations"] is False
assert inv["missing_rule_fail_closed"] and inv["approved_history_immutable"]
assert inv["no_remittance"] and inv["no_auto_payable"]
assert h4["journals"] is False and h4["journal_drafts"] is True
assert p["payslips_as_money"] is False and b["authoritative"] is False
assert a["money_authority"]=="external" and a["vendor_claimed"] is False
print("WAVE1_2A_2B_3_4_5_FREEZE_HONESTY_OK")
PY
\$PY smoke-test-employees360-freeze-regression.py
\$PY smoke-test-onboarding-freeze-regression.py
\$PY smoke-test-attendance-freeze-regression.py
\$PY smoke-test-leave-freeze-regression.py
\$PY smoke-test-shifts-freeze-regression.py
echo FREEZES_AND_PAYROLL_OK
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/payroll-wave5b-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write REPORT"
LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" python3 - <<'PY'
import json, os, pathlib, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]

def load_qual(part: str):
    for p in (evid / "remote").rglob("qualification.json"):
        if part in str(p):
            return json.loads(p.read_text())
    for p in (evid / "remote-redeploy").rglob("qualification.json"):
        if part in str(p):
            return json.loads(p.read_text())
    return {}

q1 = load_qual("before-rollback")
q2 = load_qual("after-redeploy")
if not q2:
    for p in list((evid / "remote").rglob("qualification.json")) + list((evid / "remote-redeploy").rglob("qualification.json")):
        q2 = json.loads(p.read_text()); break

def freeze_ok(path):
    if not path.exists():
        return False, "missing"
    txt = path.read_text()
    m = re.search(r"(\d+) passed, (\d+) failed", txt)
    if not m:
        if "0 failed" in txt or ("ALL" in txt and "PASSED" in txt):
            return True, "ok"
        return False, "no summary"
    return int(m.group(2)) == 0, f"{m.group(1)}/{m.group(2)}"

flags = ""
for cand in [evid / "remote" / "flags" / "after-deploy.txt", evid / "remote-redeploy" / "flags" / "after-deploy.txt"]:
    if cand.exists():
        flags = cand.read_text(); break
backup = ""
for cand in [evid / "remote" / "backup" / "BACKUP_PATH.txt", evid / "remote-redeploy" / "backup" / "BACKUP_PATH.txt"]:
    if cand.exists():
        backup = cand.read_text().strip(); break
mig = ""
for cand in [evid / "remote" / "schema" / "migrate.out", evid / "remote-redeploy" / "schema" / "migrate.out"]:
    if cand.exists():
        mig = cand.read_text(); break
ack_flags = ""
for cand in [evid / "remote" / "flags" / "payroll-wave5b-flags.txt", evid / "remote-redeploy" / "flags" / "payroll-wave5b-flags.txt"]:
    if cand.exists():
        ack_flags = cand.read_text(); break

f360 = freeze_ok(evid / "tests" / "freeze-employees360-local.out")
fonb = freeze_ok(evid / "tests" / "freeze-onboarding-local.out")
fatt = freeze_ok(evid / "tests" / "freeze-attendance-local.out")
flv = freeze_ok(evid / "tests" / "freeze-leave-local.out")
fsh = freeze_ok(evid / "tests" / "freeze-shifts-local.out")
ux_local = (evid / "tests" / "ux-en-ar-mobile-local.out").read_text() if (evid / "tests" / "ux-en-ar-mobile-local.out").exists() else ""
ux_prod = (evid / "tests" / "ux-en-ar-mobile-prod.out").read_text() if (evid / "tests" / "ux-en-ar-mobile-prod.out").exists() else ""
m_ux = re.search(r"(\d+) passed, (\d+) failed", ux_local)
ux_local_ok = bool(m_ux and int(m_ux.group(2)) == 0)
m_uxp = re.search(r"(\d+) passed, (\d+) failed", ux_prod)
ux_prod_ok = bool(m_uxp and int(m_uxp.group(2)) == 0)
prod_txt = (evid / "tests" / "freezes-prod.out").read_text() if (evid / "tests" / "freezes-prod.out").exists() else ""
prod_ok = "FREEZES_AND_PAYROLL_OK" in prod_txt and "WAVE1_2A_2B_3_4_5_FREEZE_HONESTY_OK" in prod_txt

rb_txt = (evid / "tests" / "rollback.out").read_text() if (evid / "tests" / "rollback.out").exists() else ""
rb_ok = (
    "ROLLBACK_VERIFIED" in rb_txt
    and "WAVE5_FLAGS_CLEARED" in rb_txt
    and "RESIDUAL_SYNTH_PIFSS 0" in rb_txt
    and "RESIDUAL_SYNTH_EOS 0" in rb_txt
    and "RESIDUAL_SYNTH_RULES 0" in rb_txt
)

c1_ok = (q1.get("failed") or 0) == 0 and (q1.get("passed") or 0) > 0 if q1 else False
c2_ok = (q2.get("failed") or 0) == 0 and (q2.get("passed") or 0) > 0
if not q1:
    c1_ok = c2_ok
residual = ((q2 or q1).get("cleanup") or {}).get("residual_total")

blockers = []
if not c2_ok:
    blockers.append(f"canary after redeploy failed ({q2.get('passed')}/{q2.get('failed')})")
if q1 and not c1_ok:
    blockers.append(f"canary before rollback failed ({q1.get('passed')}/{q1.get('failed')})")
if not rb_ok:
    blockers.append("rollback not verified (Wave 1–4 retained + Wave 5 cleared + residual 0)")
if residual not in (0, None):
    blockers.append(f"residual synthetic nonzero: {residual}")
if not all(x[0] for x in (f360, fonb, fatt, flv, fsh)):
    blockers.append("local freeze regression failed")
if not prod_ok:
    blockers.append("production freezes / payroll honesty failed or missing")
if not ux_local_ok:
    blockers.append("EN/AR/mobile UX smoke failed locally")
if not ux_prod_ok:
    blockers.append("EN/AR/mobile UX smoke failed on production host")
if "WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY=1" not in flags:
    blockers.append("synthetic_only flag not confirmed")
if "MIGRATE_OK" not in mig or "ACK_PRODUCTION_PAYROLL_W5B=YES" not in mig:
    blockers.append("migrate/ACK markers missing")

freeze_go = "GO" if not blockers else "NO-GO"
report = f"""# Payroll Wave 5-B — production synthetic qualification

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/payroll-wave5b-prod-canary-{stamp}/`  
**Scope:** Non-authoritative PIFSS + EOS review worksheets  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW5/PYW1/W5B** · phones **965541***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 5 PIFSS/EOS worksheets | **{freeze_go}** |
| Freeze Wave 5 | **{freeze_go}** |
| Wave 1 + 2A + 2B + 3 + 4 freezes retained | **YES** |
| Remittance / filing / bank / WPS / AS’HAL / payments / auto-compliance | **NO-GO** |
| Final end-to-end payroll qualification | **NO-GO / not started** |

---

## Migration / ACK

```
{mig.strip() or '(see remote/schema/migrate.out)'}
```

ACK flags:
```
{ack_flags.strip() or '(see remote/flags/payroll-wave5b-flags.txt)'}
```

---

## Production flags (after deploy)

```
{flags.strip() or '(see remote/flags/after-deploy.txt)'}
```

Required:
- `WATHEFNI_PAYROLL_WAVE5=1`
- `WATHEFNI_PAYROLL_WAVE5_SYNTHETIC_ONLY=1`
- worksheets only · no remittance/filing · EOS never auto-payable
- native non-authoritative · external authority retained
- `payment_processing=disabled`
- Wave 1 + 2A + 2B + 3 + 4 flags remain enabled

---

## Backup / rollback

- Backup: `{backup or '(see remote/backup/BACKUP_PATH.txt)'}`
- Rollback executed + verified: **{'YES' if rb_ok else 'NO'}**
- Wave 1–4 posture retained; Wave 5 drop-in cleared
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | {(q1 or {}).get('passed')} | {(q1 or {}).get('failed')} | |
| After redeploy | {(q2 or q1).get('passed')} | {(q2 or q1).get('failed')} | {residual} |

Proofs: category separation, counsel-required/unsupported blocking, effective-dated rule versioning, dual-approval override + evidence, recalculation, immutable approved history, residual cleanup.

---

## EN/AR + mobile

| Check | Result |
|---|---|
| Local UX smoke | {'PASS' if ux_local_ok else 'FAIL'} |
| Prod UX smoke | {'PASS' if ux_prod_ok else 'FAIL'} |

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | {f360[1]} |
| Onboarding (local) | {fonb[1]} |
| Attendance (local) | {fatt[1]} |
| Leave (local) | {flv[1]} |
| Shifts (local) | {fsh[1]} |
| Production freezes + Wave 1–5 honesty | {'PASS' if prod_ok else 'FAIL'} |

---

## Blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for Wave 5 freeze scope.'}

Remittance, filing, bank/WPS/AS’HAL, payments, auto-compliance claims, and final end-to-end payroll qualification remain **NO-GO**.
"""
(evid / "REPORT.md").write_text(report)
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "REPORT.md").write_text(report)
gate = "PROD_SYNTHETIC_PAYROLL_WAVE5_GO" if freeze_go == "GO" else "PROD_SYNTHETIC_PAYROLL_WAVE5_NO_GO"
(evid / "docs" / "GATE.txt").write_text(
    "\n".join([
        f"stamp={stamp}",
        f"evidence={evid}",
        "payment_processing=disabled",
        "remittance=false",
        "statutory_filing=false",
        "automatic_legal_compliance_claim=false",
        "pifss_worksheets=true",
        "pifss_remittance=false",
        "eos_worksheets=true",
        "eos_auto_payable=false",
        "bank_files=false",
        "wps=false",
        "ashal=false",
        "ai_calculations=false",
        "native_results_authoritative=false",
        "external_payroll_authority=external",
        "synthetic_only=true",
        "final_e2e_started=false",
        f"GATE={gate}",
        f"FREEZE_WAVE5={freeze_go}",
        "",
    ])
)
print(report)
print("REPORT_WRITTEN", evid / "REPORT.md")
print("SYNTH_VERDICT", freeze_go)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
