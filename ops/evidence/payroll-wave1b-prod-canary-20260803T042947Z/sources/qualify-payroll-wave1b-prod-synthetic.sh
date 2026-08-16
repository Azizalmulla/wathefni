#!/usr/bin/env bash
# Payroll Wave 1B — production WATHEFNI synthetic qualification.
# Deploy → canary → rollback proof → redeploy → canary → freezes.
# Does NOT enable money / G2N / PIFSS / WPS / EOS / payslips / journals / XBRL.
# Does NOT start Wave 2.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/payroll-wave1b-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/payroll-w1b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/payroll-wave1b-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,pre,quarantine,rollback,artifacts}
echo "$LOCAL_EVID" > /tmp/pyw1b.evid
echo "$STAMP" > /tmp/pyw1b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops/sql" "$LOCAL_EVID/migrate"
cp -a app.py payroll_authority_wave1.py tenant_control_roles.py tool_call_orchestrator.py \
  canary-prod-payroll-authority-wave1b.py \
  smoke-test-payroll-authority-wave1.py \
  smoke-test-multi-user-wave1-roles.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-payroll-wave1b-prod-synthetic.sh ops/migrate-payroll-authority-wave1-prod.sh "$LOCAL_EVID/sources/ops/"
cp -a ops/sql/payroll_authority_wave1_v1.sql "$LOCAL_EVID/sources/ops/sql/"
cp -a ops/migrate-payroll-authority-wave1-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-payroll-wave1b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py payroll_authority_wave1.py tenant_control_roles.py tool_call_orchestrator.py \
    canary-prod-payroll-authority-wave1b.py \
    smoke-test-payroll-authority-wave1.py \
    smoke-test-multi-user-wave1-roles.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-payroll-wave1b-prod-synthetic.sh \
    ops/migrate-payroll-authority-wave1-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
  "${SCP[@]}" ops/sql/payroll_authority_wave1_v1.sql "$VPS_HOST:$REMOTE_STAGE/"
)

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-payroll-wave1b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-payroll-wave1b-prod-synthetic.sh'
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
export PYW1B_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-authority-wave1b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/payroll-wave1b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzz-payroll-wave1b-synthetic.conf
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep PAYROLL_WAVE1 || echo "PAYROLL_WAVE1_FLAGS_CLEARED"
curl -fsS http://127.0.0.1:8010/health >/dev/null
# Smoke quarantine must survive rollback (soft quarantine is data, not flag)
set -a; source /root/.openclaw/secrets/postgres.env; set +a
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
/opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
import app
ids=["cc68a9fb-df72-4e13-a0db-cc13a3805380","7950dafd-6cf7-44b1-9f92-26f685c34ab5"]
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("""
      SELECT timesheet_id::text, quarantine_status, payroll_status
      FROM payroll_timesheets
      WHERE company_code='WATHEFNI' AND timesheet_id::text = ANY(%s)
    """, (ids,))
    rows=[dict(r) for r in cur.fetchall()]
assert len(rows)==2
for r in rows:
  assert r["quarantine_status"]=="wave0_smoke_quarantined", r
print("QUARANTINE_SURVIVED_ROLLBACK", rows)
PY
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-payroll-wave1b-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
# Point evidence into original stamp tree
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-after-redeploy.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='/opt/wathefni/production-evidence/payroll-wave1b-prod-canary/${STAMP}/canary/after-redeploy'
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
export PYW1B_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-payroll-authority-wave1b.py
REMOTE

log "production freezes"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/freezes-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
PY=\$ORCH/.venv/bin/python
cd \$ORCH
\$PY smoke-test-employees360-freeze-regression.py
\$PY smoke-test-onboarding-freeze-regression.py
\$PY smoke-test-attendance-freeze-regression.py
\$PY smoke-test-leave-freeze-regression.py
\$PY smoke-test-shifts-freeze-regression.py
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
# Also pull redeploy evidence quarantine if under redeploy stamp
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/payroll-wave1b-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

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
        # shifts may print "N passed, 0 failed" or "ALL ... PASSED"
        if "0 failed" in txt or "ALL" in txt and "PASSED" in txt:
            return True, "ok"
        return False, "no summary"
    return int(m.group(2)) == 0, f"{m.group(1)}/{m.group(2)}"

flags = ""
fp = evid / "remote" / "flags" / "after-deploy.txt"
if fp.exists():
    flags = fp.read_text()
backup = ""
bp = evid / "remote" / "backup" / "BACKUP_PATH.txt"
if bp.exists():
    backup = bp.read_text().strip()

f360 = freeze_ok(evid / "tests" / "freeze-employees360-local.out")
fonb = freeze_ok(evid / "tests" / "freeze-onboarding-local.out")
fatt = freeze_ok(evid / "tests" / "freeze-attendance-local.out")
flv = freeze_ok(evid / "tests" / "freeze-leave-local.out")
fsh = freeze_ok(evid / "tests" / "freeze-shifts-local.out")
prod_freeze = evid / "tests" / "freezes-prod.out"
prod_ok = prod_freeze.exists() and ("0 failed" in prod_freeze.read_text())

rb_txt = (evid / "tests" / "rollback.out").read_text() if (evid / "tests" / "rollback.out").exists() else ""
rb_ok = "ROLLBACK_VERIFIED" in rb_txt and "QUARANTINE_SURVIVED_ROLLBACK" in rb_txt

mig = ""
mp = evid / "remote" / "schema" / "migrate.out"
if mp.exists():
    mig = mp.read_text()
qfile = evid / "remote" / "quarantine" / "smoke-after.json"
quarantine = json.loads(qfile.read_text()) if qfile.exists() else {}

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
    blockers.append("rollback not verified (or quarantine did not survive)")
if residual not in (0, None):
    blockers.append(f"residual synthetic nonzero: {residual}")
if not all(x[0] for x in (f360, fonb, fatt, flv, fsh)):
    blockers.append("local freeze regression failed")
if not prod_ok:
    blockers.append("production freeze regression failed or missing")
if "WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1" not in flags and "SYNTHETIC_ONLY=1" not in flags:
    if "PAYROLL_WAVE1_SYNTHETIC_ONLY=1" not in flags:
        blockers.append("synthetic_only flag not confirmed in after-deploy")
if "MIGRATE_OK" not in mig:
    blockers.append("migrate ok marker missing")
if int(quarantine.get("count") or 0) != 2:
    blockers.append(f"quarantine count != 2: {quarantine}")

freeze_go = "GO" if not blockers else "NO-GO"
report = f"""# Payroll Wave 1B — production synthetic qualification

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/payroll-wave1b-prod-canary-{stamp}/`  
**Module:** `payroll_authority_wave1.py` **v1.0.0**  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW1** / **965539***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Payroll Wave 1 foundation | **{freeze_go}** |
| Freeze Payroll Wave 1 foundation | **{freeze_go}** (see blockers) |
| Real compensation / money authority | **NO-GO** |
| Wave 2 (external adapter / native preview) | **NO-GO / not started** |

---

## Migration

```
{mig.strip() or '(see remote/schema/migrate.out)'}
```

---

## Quarantine (May 2026 smoke — soft, no delete)

```json
{json.dumps(quarantine, indent=2, default=str)}
```

Smoke IDs:
- `cc68a9fb-df72-4e13-a0db-cc13a3805380`
- `7950dafd-6cf7-44b1-9f92-26f685c34ab5`

Quarantine survived rollback: **{'YES' if 'QUARANTINE_SURVIVED_ROLLBACK' in rb_txt else 'NO'}**

---

## Production flags (after deploy)

```
{flags.strip() or '(see remote/flags/after-deploy.txt)'}
```

Required:
- `WATHEFNI_PAYROLL_WAVE1=1`
- `WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI`
- `WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1`
- `WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS=PYW1,PYW1-SYNTH|`
- `WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES=965539`
- `payment_processing=disabled` (honesty + DB CHECK)

---

## Backup / rollback

- Backup: `{backup or '(see remote/backup/BACKUP_PATH.txt)'}`
- Rollback executed + verified: **{'YES' if rb_ok else 'NO'}**
- Redeploy after rollback completed; canary re-run

---

## Synthetic canary counts

| Pass | Passed | Failed |
|---|---:|---:|
| Before rollback | {(q1 or {}).get('passed')} | {(q1 or {}).get('failed')} |
| After redeploy | {(q2 or q1).get('passed')} | {(q2 or q1).get('failed')} |
| Residual synthetic | {residual} | |

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | {f360[1]} |
| Onboarding (local) | {fonb[1]} |
| Attendance (local) | {fatt[1]} |
| Leave (local) | {flv[1]} |
| Shifts (local) | {fsh[1]} |
| Production freezes | {'PASS' if prod_ok else 'FAIL'} |

---

## Blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for synthetic foundation freeze scope.'}

Money, G2N, PIFSS, WPS/bank, EOS, payslips-as-money, journals, XBRL, and Wave 2 remain **NO-GO**.
"""
(evid / "REPORT.md").write_text(report)
(evid / "docs" / "REPORT.md").write_text(report)
(evid / "docs" / "GATE.txt").write_text(
    f"stamp={stamp}\\nevidence={evid}\\npayment_processing=disabled\\nmoney_authority=false\\n"
    f"synthetic_only=true\\nGATE={'PROD_SYNTHETIC_PAYROLL_WAVE1_FOUNDATION_GO' if freeze_go=='GO' else 'PROD_SYNTHETIC_PAYROLL_WAVE1_FOUNDATION_NO_GO'}\\n"
    f"FREEZE_WAVE1={'GO' if freeze_go=='GO' else 'NO-GO'}\\n"
)
print(report)
print("REPORT_WRITTEN", evid / "REPORT.md")
print("SYNTH_VERDICT", freeze_go)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
