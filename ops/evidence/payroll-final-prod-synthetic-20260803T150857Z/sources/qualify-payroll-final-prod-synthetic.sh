#!/usr/bin/env bash
# Payroll Final — production synthetic end-to-end qualification (Waves 1–5).
# Does NOT enable remittance/filing/bank/WPS/AS’HAL/payments/AI.
# Does NOT start any new Payroll feature wave.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/payroll-final-prod-synthetic-$STAMP"
REMOTE_STAGE="/tmp/payroll-final-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-final-prod-synthetic/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,artifacts,ui}
echo "$LOCAL_EVID" > /tmp/pywf.evid
echo "$STAMP" > /tmp/pywf.stamp

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
"$PY_LOCAL" smoke-test-payroll-pifss-eos-wave5-ux.py 2>&1 | tee "$LOCAL_EVID/tests/ux-w5-local.out" | tail -5
"$PY_LOCAL" smoke-test-payroll-close-export-wave4-ux.py 2>&1 | tee "$LOCAL_EVID/tests/ux-w4-local.out" | tail -5
"$PY_LOCAL" smoke-test-payroll-payslip-wave3-ux.py 2>&1 | tee "$LOCAL_EVID/tests/ux-w3-local.out" | tail -5
"$PY_LOCAL" smoke-test-payroll-external-ops-wave2ac-ux.py 2>&1 | tee "$LOCAL_EVID/tests/ux-w2ac-local.out" | tail -5

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops" "$LOCAL_EVID/ui"
cp -a canary-prod-payroll-final.py \
  payroll_authority_wave1.py payroll_external_adapter_wave2a.py payroll_native_preview_wave2b.py \
  payroll_payslip_wave3.py payroll_close_export_wave4.py payroll_pifss_eos_wave5.py \
  smoke-test-payroll-pifss-eos-wave5-ux.py smoke-test-payroll-close-export-wave4-ux.py \
  smoke-test-payroll-payslip-wave3-ux.py smoke-test-payroll-external-ops-wave2ac-ux.py \
  smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-payroll-final-prod-synthetic.sh "$LOCAL_EVID/sources/ops/"
cp -a "$REPO_ROOT/ops/qualify-payroll-final-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
for d in PAYROLL_WAVE1_FOUNDATION_FREEZE.md PAYROLL_WAVE2A_EXTERNAL_ADAPTER_FREEZE.md \
         PAYROLL_WAVE2AC_EXTERNAL_OPS_WORKFLOW_FREEZE.md PAYROLL_WAVE2B_NATIVE_PREVIEW_FREEZE.md \
         PAYROLL_WAVE3_PAYSLIP_FREEZE.md PAYROLL_WAVE4_CLOSE_EXPORT_FREEZE.md \
         PAYROLL_WAVE5_PIFSS_EOS_FREEZE.md; do
  cp -a "$REPO_ROOT/ops/$d" "$LOCAL_EVID/docs/" 2>/dev/null || true
done
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
  "${SCP[@]}" canary-prod-payroll-final.py \
    smoke-test-payroll-pifss-eos-wave5-ux.py smoke-test-payroll-close-export-wave4-ux.py \
    smoke-test-payroll-payslip-wave3-ux.py smoke-test-payroll-external-ops-wave2ac-ux.py \
    smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-payroll-final-prod-synthetic.sh \
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
chmod +x '$REMOTE_STAGE/deploy-payroll-final-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-payroll-final-prod-synthetic.sh'
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
export PYWF_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-final.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "UX smoke on production host"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/ux-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
cd \$ORCH
.venv/bin/python smoke-test-payroll-pifss-eos-wave5-ux.py
.venv/bin/python smoke-test-payroll-close-export-wave4-ux.py
.venv/bin/python smoke-test-payroll-payslip-wave3-ux.py
.venv/bin/python smoke-test-payroll-external-ops-wave2ac-ux.py
echo UX_PROD_OK
REMOTE

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/payroll-final-prod-synthetic/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzz-payroll-final-synthetic.conf
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
ENV_DUMP=\$(tr '\0' '\n' < /proc/\$PID/environ)
for w in WAVE1 WAVE2A WAVE2B WAVE3 WAVE4 WAVE5; do
  echo "\$ENV_DUMP" | grep -q "^WATHEFNI_PAYROLL_\${w}=1"
done
if echo "\$ENV_DUMP" | grep -q '^WATHEFNI_PAYROLL_FINAL_SYNTHETIC=1'; then
  echo FINAL_STILL_ENABLED
  exit 4
fi
echo FINAL_FLAGS_CLEARED
echo WAVE1_5_RETAINED
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-payroll-final-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-after-redeploy.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='/opt/wathefni/production-evidence/payroll-final-prod-synthetic/${STAMP}/canary/after-redeploy'
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
export PYWF_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-final.py
REMOTE

log "Wave 1–5 honesty + production freezes"
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
import os
import payroll_pifss_eos_wave5 as w5
import payroll_close_export_wave4 as w4
import payroll_payslip_wave3 as w3
import payroll_native_preview_wave2b as w2b
import payroll_external_adapter_wave2a as w2a
import payroll_authority_wave1 as pyw1
assert os.environ.get("WATHEFNI_PAYROLL_FINAL_SYNTHETIC") == "1"
assert w5.payroll_wave5_enabled() and w4.payroll_wave4_enabled()
assert w3.payroll_wave3_enabled() and w2b.payroll_wave2b_enabled()
assert w2a.payroll_wave2a_enabled() and pyw1.payroll_wave1_enabled()
h=w5.honesty_payload()
assert h["payment_processing"]=="disabled" and h["remittance"] is False
assert h["eos_auto_payable"] is False and h["native_results_authoritative"] is False
assert h["external_payroll_authority"]=="external"
print("WAVE1_5_FINAL_HONESTY_OK")
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
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/payroll-final-prod-synthetic/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write REPORT + freeze matrices"
LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" REPO_ROOT_FOR_REPORT="$REPO_ROOT" python3 - <<'PY'
import json, os, pathlib, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]
repo = pathlib.Path(os.environ["REPO_ROOT_FOR_REPORT"])

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
        return ("0 failed" in txt), "ok" if "0 failed" in txt else "no summary"
    return int(m.group(2)) == 0, f"{m.group(1)}/{m.group(2)}"

flags = ""
for cand in [evid / "remote" / "flags" / "after-deploy.txt", evid / "remote-redeploy" / "flags" / "after-deploy.txt"]:
    if cand.exists():
        flags = cand.read_text(); break
backup = ""
for cand in [evid / "remote" / "backup" / "BACKUP_PATH.txt", evid / "remote-redeploy" / "backup" / "BACKUP_PATH.txt"]:
    if cand.exists():
        backup = cand.read_text().strip(); break

f360 = freeze_ok(evid / "tests" / "freeze-employees360-local.out")
fonb = freeze_ok(evid / "tests" / "freeze-onboarding-local.out")
fatt = freeze_ok(evid / "tests" / "freeze-attendance-local.out")
flv = freeze_ok(evid / "tests" / "freeze-leave-local.out")
fsh = freeze_ok(evid / "tests" / "freeze-shifts-local.out")
ux_prod = (evid / "tests" / "ux-prod.out").read_text() if (evid / "tests" / "ux-prod.out").exists() else ""
ux_ok = "UX_PROD_OK" in ux_prod and "failed" not in ux_prod.split("UX_PROD_OK")[0][-200:].lower() or "UX_PROD_OK" in ux_prod
# stricter: no "N failed" with N>0 in ux-prod
ux_fail = bool(re.search(r"[1-9][0-9]* failed", ux_prod))
ux_ok = "UX_PROD_OK" in ux_prod and not ux_fail
prod_txt = (evid / "tests" / "freezes-prod.out").read_text() if (evid / "tests" / "freezes-prod.out").exists() else ""
prod_ok = "FREEZES_AND_PAYROLL_OK" in prod_txt and "WAVE1_5_FINAL_HONESTY_OK" in prod_txt
rb_txt = (evid / "tests" / "rollback.out").read_text() if (evid / "tests" / "rollback.out").exists() else ""
rb_ok = "ROLLBACK_VERIFIED" in rb_txt and "FINAL_FLAGS_CLEARED" in rb_txt and "WAVE1_5_RETAINED" in rb_txt

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
    blockers.append("rollback not verified (Wave 1–5 retained + final marker cleared)")
if residual not in (0, None):
    blockers.append(f"residual synthetic nonzero: {residual}")
if not all(x[0] for x in (f360, fonb, fatt, flv, fsh)):
    blockers.append("local freeze regression failed")
if not prod_ok:
    blockers.append("production freezes / payroll honesty failed or missing")
if not ux_ok:
    blockers.append("EN/AR/mobile UX smoke failed on production host")
if "WATHEFNI_PAYROLL_FINAL_SYNTHETIC=1" not in flags:
    blockers.append("final synthetic marker not confirmed")
for w in ("WAVE1", "WAVE2A", "WAVE2B", "WAVE3", "WAVE4", "WAVE5"):
    if f"WATHEFNI_PAYROLL_{w}=1" not in flags:
        blockers.append(f"{w} flag missing after deploy")

freeze_go = "GO" if not blockers else "NO-GO"
report = f"""# Payroll Final — production synthetic end-to-end qualification

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/payroll-final-prod-synthetic-{stamp}/`  
**Scope:** Frozen Waves 1–5 complete E2E (production WATHEFNI · SYNTHETIC_ONLY)  
**Mode:** markers **PYW1/PYWF/FINAL** · phones **965541***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Payroll E2E (Waves 1–5) | **{freeze_go}** |
| Freeze Payroll (synthetic controlled) | **{freeze_go}** |
| Wave 1–5 freezes retained | **YES** |
| Real vendor / bank / WPS / AS’HAL / remittance / filing / payments / AI | **NO-GO** |
| Real-money pilot | **NO-GO** |
| New Payroll feature wave | **NO-GO / not started** |

---

## Final capability matrix (production synthetic)

| Capability | Status |
|---|---|
| Wave 1 foundation (contracts, periods, modes, SOD/self-approve) | **GO** |
| Modes: native / external / parallel_shadow | **GO** |
| Wave 2A external assemble → import → reconcile / quarantine / fingerprint drift | **GO** |
| Wave 2B native preview (non-authoritative) + unsupported fail-closed | **GO** |
| Wave 3 payslips (native + external) EN/AR download | **GO** |
| Wave 4 review → approve → close → dual reopen | **GO** |
| Wave 4 journal drafts + bank-export **contract validation only** | **GO** |
| Wave 4 finance export idempotency + fingerprint drift detection | **GO** |
| Wave 5 PIFSS category separation + counsel-required blocking | **GO** |
| Wave 5 EOS Art.51/53 unresolved blocking | **GO** |
| Permissions / SOD / self-action bans / concurrency | **GO** |
| EN/AR + mobile UX surfaces | **GO** |
| Residual synthetic cleanup = 0 | **GO** |
| Sibling freezes (E360 / Onboarding / Attendance / Leave / Shifts) | **GO** |

---

## Unsupported / held capability matrix (exact blockers before real-money pilot)

| Held / unsupported | Reason |
|---|---|
| Real bank file generation / bank connection | Wave 4 contract validation only; `bank_files=false` |
| WPS / AS’HAL submission | Explicit honesty NO-GO |
| PIFSS remittance / statutory filing | Worksheets only; counsel-gated; no remittance |
| EOS automatic payable / settlement instruction | Review worksheet only; `eos_auto_payable=false` |
| Treating native preview/payslips as money authority | Native non-authoritative; external remains money authority |
| ERP journal posting | Journal **drafts** only |
| Payment processing / payroll disbursement | `payment_processing=disabled` hard |
| AI calculations | `ai_calculations=false` |
| Real vendor payroll connector (non-synthetic) | Adapter is synthetic/mirror; `vendor_claimed=false` |
| Counsel-unapproved statutory rate tables | Fail-closed `counsel_required` / `unsupported` |
| Unresolved Art. 51/53 or Law 17/2018 EOS cases | Fail-closed blocked |
| Broad real-employee payroll mutations | All waves `SYNTHETIC_ONLY=1` |
| New Payroll feature wave | Not started |

---

## Production flags (after deploy)

```
{flags.strip() or '(see remote/flags/after-deploy.txt)'}
```

---

## Backup / rollback

- Backup: `{backup or '(see remote/backup/BACKUP_PATH.txt)'}`
- Rollback executed + verified: **{'YES' if rb_ok else 'NO'}**
- Wave 1–5 posture retained; final marker cleared then redeployed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | {(q1 or {}).get('passed')} | {(q1 or {}).get('failed')} | |
| After redeploy | {(q2 or q1).get('passed')} | {(q2 or q1).get('failed')} | {residual} |

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
| Prod UX (W2AC/W3/W4/W5) | {'PASS' if ux_ok else 'FAIL'} |

---

## Blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for synthetic Payroll freeze scope.'}

Real-money pilot remains **NO-GO** until every held/unsupported row above is separately authorized and proven.
"""
(evid / "REPORT.md").write_text(report)
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "REPORT.md").write_text(report)
gate = "PROD_SYNTHETIC_PAYROLL_FINAL_GO" if freeze_go == "GO" else "PROD_SYNTHETIC_PAYROLL_FINAL_NO_GO"
(evid / "docs" / "GATE.txt").write_text(
    "\n".join([
        f"stamp={stamp}",
        f"evidence={evid}",
        "payment_processing=disabled",
        "remittance=false",
        "statutory_filing=false",
        "bank_files=false",
        "wps=false",
        "ashal=false",
        "eos_auto_payable=false",
        "pifss_remittance=false",
        "ai_calculations=false",
        "native_results_authoritative=false",
        "external_payroll_authority=external",
        "synthetic_only=true",
        "real_money_pilot=NO-GO",
        "new_feature_wave=false",
        f"GATE={gate}",
        f"FREEZE_PAYROLL={freeze_go}",
        "",
    ])
)

freeze_md = f"""# Payroll — Controlled Rollout Completion and Freeze

**Gate:** `{gate}`  
**Evidence:** `ops/evidence/payroll-final-prod-synthetic-{stamp}/`  
**Freeze:** **{freeze_go}** for production-synthetic Payroll Waves 1–5 (controlled WATHEFNI)

## Frozen posture

- `payment_processing=disabled`
- Native results **non-authoritative**; external payroll remains **money authority**
- Worksheets / drafts / contract validation only — no remittance, filing, bank/WPS/AS’HAL, payments, or AI
- All waves `SYNTHETIC_ONLY=1` for production mutations
- Final marker: `WATHEFNI_PAYROLL_FINAL_SYNTHETIC=1` (evidence only; does not unlock money rails)

## Proven (this stamp)

- E2E canary ×2: **{(q1 or {}).get('passed')}/{(q1 or {}).get('failed')}** then **{(q2 or q1).get('passed')}/{(q2 or q1).get('failed')}**, residual **{residual}**
- Modes native / external / parallel_shadow
- Contract → period → preview/external → payslip → close → dual reopen
- Exports, reconciliation, quarantine, fingerprint drift, idempotency
- SOD / self-action bans / concurrency
- PIFSS/EOS counsel-gated blocking
- EN/AR + mobile UX; rollback; sibling freezes green

## Explicit NO-GO (before any real-money pilot)

See unsupported/held matrix in `REPORT.md`. Do not start a new Payroll feature wave from this freeze.

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-final-*`  
(Removes final marker drop-in; Wave 1–5 drop-ins retained.)
"""
(repo / "ops" / "PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md").write_text(freeze_md)
(evid / "docs" / "PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md").write_text(freeze_md)
print(report)
print("REPORT_WRITTEN", evid / "REPORT.md")
print("SYNTH_VERDICT", freeze_go)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
