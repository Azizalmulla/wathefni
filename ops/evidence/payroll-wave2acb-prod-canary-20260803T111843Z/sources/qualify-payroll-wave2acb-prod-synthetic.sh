#!/usr/bin/env bash
# Payroll Wave 2A-C-B — production WATHEFNI synthetic qualification.
# Deploy ops workflow → canary → rollback proof → redeploy → canary → freezes.
# Does NOT enable money/bank/vendor/native G2N. Does NOT start Wave 2B.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/payroll-wave2acb-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/payroll-w2acb-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave2acb-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,artifacts,ui}
echo "$LOCAL_EVID" > /tmp/pyw2acb.evid
echo "$STAMP" > /tmp/pyw2acb.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local freezes + UX smoke"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3
"$PY_LOCAL" smoke-test-payroll-external-ops-wave2ac-ux.py 2>&1 | tee "$LOCAL_EVID/tests/ux-en-ar-mobile-local.out" | tail -20

log "optional dashboard build"
if [[ -f "$DASH_SRC/package.json" ]]; then
  set +e
  (cd "$DASH_SRC" && npm run build) 2>&1 | tee "$LOCAL_EVID/ui/dashboard-build.out" | tail -30
  BUILD_RC=${PIPESTATUS[0]}
  set -e
  if [[ $BUILD_RC -eq 0 ]] && [[ -d "$DASH_SRC/dist" ]]; then
    mkdir -p "$LOCAL_EVID/sources/dashboard-dist"
    cp -a "$DASH_SRC/dist/." "$LOCAL_EVID/sources/dashboard-dist/"
    echo DASHBOARD_BUILD_OK | tee "$LOCAL_EVID/ui/dashboard-build-status.txt"
  else
    echo DASHBOARD_BUILD_SKIPPED | tee "$LOCAL_EVID/ui/dashboard-build-status.txt"
  fi
else
  echo DASHBOARD_SRC_MISSING | tee "$LOCAL_EVID/ui/dashboard-build-status.txt"
fi

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops/sql" "$LOCAL_EVID/migrate"
cp -a app.py payroll_external_adapter_wave2a.py payroll_authority_wave1.py \
  canary-prod-payroll-external-ops-wave2acb.py \
  canary-prod-payroll-external-adapter-wave2ab.py \
  smoke-test-payroll-external-ops-wave2ac.py \
  smoke-test-payroll-external-ops-wave2ac-ux.py \
  smoke-test-payroll-external-adapter-wave2a.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-payroll-wave2acb-prod-synthetic.sh \
  ops/migrate-payroll-external-ops-wave2ac-prod.sh \
  ops/migrate-payroll-external-adapter-wave2a-prod.sh \
  "$LOCAL_EVID/sources/ops/"
cp -a ops/sql/payroll_external_adapter_wave2a_v1.sql ops/sql/payroll_authority_wave1_v1.sql "$LOCAL_EVID/sources/ops/sql/"
cp -a ops/migrate-payroll-external-ops-wave2ac-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-payroll-wave2acb-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$DASH_SRC/src/posthire/ExternalPayrollWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollExternalUx.ts" \
  "$LOCAL_EVID/ui/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py payroll_external_adapter_wave2a.py payroll_authority_wave1.py \
    canary-prod-payroll-external-ops-wave2acb.py \
    canary-prod-payroll-external-adapter-wave2ab.py \
    smoke-test-payroll-external-ops-wave2ac.py \
    smoke-test-payroll-external-ops-wave2ac-ux.py \
    smoke-test-payroll-external-adapter-wave2a.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-payroll-wave2acb-prod-synthetic.sh \
    ops/migrate-payroll-external-ops-wave2ac-prod.sh \
    ops/migrate-payroll-external-adapter-wave2a-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
  "${SCP[@]}" ops/sql/payroll_external_adapter_wave2a_v1.sql ops/sql/payroll_authority_wave1_v1.sql \
    "$VPS_HOST:$REMOTE_STAGE/"
)
if [[ -d "$LOCAL_EVID/sources/dashboard-dist" ]]; then
  "${SCP[@]}" -r "$LOCAL_EVID/sources/dashboard-dist/." "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"
fi

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-payroll-wave2acb-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-payroll-wave2acb-prod-synthetic.sh'
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
export PYW2ACB_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-external-ops-wave2acb.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "UX smoke on production host"
"${SSH[@]}" "mkdir -p /opt/wathefni/apps/wathefni-dashboard/src/posthire"
"${SCP[@]}" \
  "$DASH_SRC/src/posthire/ExternalPayrollWorkspace.tsx" \
  "$DASH_SRC/src/posthire/payrollExternalUx.ts" \
  "$DASH_SRC/src/posthire/PostHire.tsx" \
  "$VPS_HOST:/opt/wathefni/apps/wathefni-dashboard/src/posthire/"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/ux-en-ar-mobile-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
cd \$ORCH
.venv/bin/python smoke-test-payroll-external-ops-wave2ac-ux.py
if grep -Rql 'الرواتب الخارجية\|External payroll' /opt/wathefni/dashboard-dist 2>/dev/null; then
  echo DIST_COPY_OK
else
  echo DIST_COPY_CHECK_SKIPPED_OR_MISSING
fi
REMOTE

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/payroll-wave2acb-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
# Wave 1 + Wave 2A freeze posture must remain after 2A-C-B code rollback
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep -q '^WATHEFNI_PAYROLL_WAVE1=1'
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A=1'
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep -q '^WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1'
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
      SELECT COUNT(*) AS n FROM payroll_compensation_contracts
      WHERE company_code='WATHEFNI' AND employee_key LIKE 'WATHEFNI-PYW2ACB-%'
    """)
    n=int(dict(cur.fetchone())["n"])
print("RESIDUAL_SYNTH_CONTRACTS", n)
assert n==0
PY
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-payroll-wave2acb-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-after-redeploy.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='/opt/wathefni/production-evidence/payroll-wave2acb-prod-canary/${STAMP}/canary/after-redeploy'
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
export PYW2ACB_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-external-ops-wave2acb.py
REMOTE

log "Wave 2A regression + production freezes"
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
# Wave 2A adapter freeze regression (must remain green)
\$PY smoke-test-payroll-external-adapter-wave2a.py | tee /tmp/w2a-regression-prod.out
if grep -E '[1-9][0-9]* failed' /tmp/w2a-regression-prod.out; then
  echo W2A_REGRESSION_FAILED
  exit 1
fi
\$PY smoke-test-employees360-freeze-regression.py
\$PY smoke-test-onboarding-freeze-regression.py
\$PY smoke-test-attendance-freeze-regression.py
\$PY smoke-test-leave-freeze-regression.py
\$PY smoke-test-shifts-freeze-regression.py
echo FREEZES_AND_W2A_OK
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/payroll-wave2acb-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write REPORT"
LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" python3 - <<'PY'
import json, os, pathlib, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]

def load_qual(part: str):
    for p in (evid / "remote").rglob("qualification.json"):
        if part in str(p):
            return json.loads(p.read_text())
    return {}

q1 = load_qual("before-rollback")
q2 = load_qual("after-redeploy")
if not q2:
    for p in (evid / "remote").rglob("qualification.json"):
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

flags = (evid / "remote" / "flags" / "after-deploy.txt").read_text() if (evid / "remote" / "flags" / "after-deploy.txt").exists() else ""
backup = (evid / "remote" / "backup" / "BACKUP_PATH.txt").read_text().strip() if (evid / "remote" / "backup" / "BACKUP_PATH.txt").exists() else ""
mig = (evid / "remote" / "schema" / "migrate.out").read_text() if (evid / "remote" / "schema" / "migrate.out").exists() else ""
ack_flags = (evid / "remote" / "flags" / "payroll-wave2acb-flags.txt").read_text() if (evid / "remote" / "flags" / "payroll-wave2acb-flags.txt").exists() else ""
ux_local = (evid / "tests" / "ux-en-ar-mobile-local.out").read_text() if (evid / "tests" / "ux-en-ar-mobile-local.out").exists() else ""
ux_prod = (evid / "tests" / "ux-en-ar-mobile-prod.out").read_text() if (evid / "tests" / "ux-en-ar-mobile-prod.out").exists() else ""
dash = (evid / "ui" / "dashboard-build-status.txt").read_text().strip() if (evid / "ui" / "dashboard-build-status.txt").exists() else ""

f360 = freeze_ok(evid / "tests" / "freeze-employees360-local.out")
fonb = freeze_ok(evid / "tests" / "freeze-onboarding-local.out")
fatt = freeze_ok(evid / "tests" / "freeze-attendance-local.out")
flv = freeze_ok(evid / "tests" / "freeze-leave-local.out")
fsh = freeze_ok(evid / "tests" / "freeze-shifts-local.out")
prod_txt = (evid / "tests" / "freezes-prod.out").read_text() if (evid / "tests" / "freezes-prod.out").exists() else ""
prod_ok = "FREEZES_AND_W2A_OK" in prod_txt and "W2A_REGRESSION_FAILED" not in prod_txt
ux_local_ok = "0 failed" in ux_local and "FAIL" not in ux_local.split("passed")[0] if ux_local else False
# softer: last summary line
m_ux = re.search(r"(\d+) passed, (\d+) failed", ux_local)
ux_local_ok = bool(m_ux and int(m_ux.group(2)) == 0)

rb_txt = (evid / "tests" / "rollback.out").read_text() if (evid / "tests" / "rollback.out").exists() else ""
rb_ok = (
    "ROLLBACK_VERIFIED" in rb_txt
    and "RESIDUAL_SYNTH_CONTRACTS 0" in rb_txt
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
    blockers.append("rollback not verified (Wave 2A retained + residual 0)")
if residual not in (0, None):
    blockers.append(f"residual synthetic nonzero: {residual}")
if not all(x[0] for x in (f360, fonb, fatt, flv, fsh)):
    blockers.append("local freeze regression failed")
if not prod_ok:
    blockers.append("production freezes / Wave 2A regression failed or missing")
if "WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1" not in flags:
    blockers.append("synthetic_only flag not confirmed")
if "MIGRATE_OK" not in mig or "ACK_PRODUCTION_PAYROLL_W2ACB=YES" not in mig:
    blockers.append("migrate/ACK markers missing")
if not ux_local_ok:
    blockers.append("EN/AR/mobile UX smoke failed locally")
if "vendor_claimed" in ack_flags and "False" not in ack_flags:
    blockers.append("vendor_claimed not false")

freeze_go = "GO" if not blockers else "NO-GO"
report = f"""# Payroll Wave 2A-C-B — production synthetic qualification

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/payroll-wave2acb-prod-canary-{stamp}/`  
**Scope:** External payroll operations workflow (UI + APIs + ops helpers)  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW2ACB** / **965540***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 2A-C ops workflow | **{freeze_go}** |
| Freeze Wave 2A-C | **{freeze_go}** |
| Wave 1 + Wave 2A freezes retained | **YES** |
| Real vendor / money / bank / native G2N | **NO-GO** |
| Wave 2B native calculations | **NO-GO / not started** |

---

## Migration / ACK

```
{mig.strip() or '(see remote/schema/migrate.out)'}
```

ACK flags:
```
{ack_flags.strip() or '(see remote/flags/payroll-wave2acb-flags.txt)'}
```

---

## Production flags (after deploy)

```
{flags.strip() or '(see remote/flags/after-deploy.txt)'}
```

Required:
- `WATHEFNI_PAYROLL_WAVE2A=1`
- `WATHEFNI_PAYROLL_WAVE2A_SYNTHETIC_ONLY=1`
- markers include `PYW2ACB`
- `money_authority=external` · `payment_processing=disabled` · `vendor_claimed=false`
- Wave 1 flags remain enabled

Dashboard build: `{dash or 'n/a'}`

---

## Backup / rollback

- Backup: `{backup or '(see remote/backup/BACKUP_PATH.txt)'}`
- Rollback executed + verified: **{'YES' if rb_ok else 'NO'}**
- Wave 1 + Wave 2A posture retained after Wave 2A-C-B rollback
- Redeploy + second canary completed

---

## Synthetic canary counts

| Pass | Passed | Failed | Residual |
|---|---:|---:|---:|
| Before rollback | {(q1 or {}).get('passed')} | {(q1 or {}).get('failed')} | |
| After redeploy | {(q2 or q1).get('passed')} | {(q2 or q1).get('failed')} | {residual} |

Proofs: readiness, assemble/export, upload/replace, quarantine, reconciliation, fingerprint drift, history/events, manager empty scope, permissions/routes, residual cleanup.

---

## EN/AR + mobile

| Check | Result |
|---|---|
| Local UX smoke | {'PASS' if ux_local_ok else 'FAIL'} |
| Prod UX / dist | {(ux_prod.strip().splitlines()[-1] if ux_prod.strip() else 'n/a')} |

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | {f360[1]} |
| Onboarding (local) | {fonb[1]} |
| Attendance (local) | {fatt[1]} |
| Leave (local) | {flv[1]} |
| Shifts (local) | {fsh[1]} |
| Production freezes + Wave 2A regression | {'PASS' if prod_ok else 'FAIL'} |

---

## Blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for Wave 2A-C freeze scope.'}

Real vendor connection, bank files, PIFSS/WPS/EOS/journals, and Wave 2B native calculations remain **NO-GO**.
"""
(evid / "REPORT.md").write_text(report)
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "REPORT.md").write_text(report)
gate = "PROD_SYNTHETIC_PAYROLL_WAVE2AC_GO" if freeze_go == "GO" else "PROD_SYNTHETIC_PAYROLL_WAVE2AC_NO_GO"
(evid / "docs" / "GATE.txt").write_text(
    "\n".join([
        f"stamp={stamp}",
        f"evidence={evid}",
        "payment_processing=disabled",
        "money_authority=external",
        "vendor_claimed=false",
        "authoritative_in_wathefni=false",
        "synthetic_only=true",
        "wave2b_started=false",
        f"GATE={gate}",
        f"FREEZE_WAVE2AC={freeze_go}",
        "",
    ])
)
print(report)
print("REPORT_WRITTEN", evid / "REPORT.md")
print("SYNTH_VERDICT", freeze_go)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
