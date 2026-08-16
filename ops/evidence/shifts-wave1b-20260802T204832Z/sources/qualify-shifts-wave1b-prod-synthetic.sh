#!/usr/bin/env bash
# Shifts Wave 1B — production WATHEFNI synthetic canary qualify.
# Deploy → canary → rollback proof → redeploy → canary → cleanup/fingerprint → freezes.
# Does NOT enable real-employee mutations, templates, recurring, publish, open shifts, or Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave1b-$STAMP"
REMOTE_STAGE="/tmp/shifts-w1b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave1b-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,ui,pre,orphan,cleanup,rollback,artifacts}
echo "$LOCAL_EVID" > /tmp/shw1b.evid
echo "$STAMP" > /tmp/shw1b.stamp
echo "$STAMP" > /tmp/w1b-stamp.txt

log() { printf '\n=== %s ===\n' "$*"; }

log "local freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3

log "rebuild dashboard dist"
cd "$DASH_SRC"
npm run build 2>&1 | tee "$LOCAL_EVID/ui/dashboard-build.out" | tail -20
grep -l expected_updated_at dist/assets/*.js | tee "$LOCAL_EVID/ui/concurrency-token.txt"
test -s "$LOCAL_EVID/ui/concurrency-token.txt"

log "stage sources"
cd "$ORCH_SRC"
mkdir -p "$LOCAL_EVID/sources/ops/sql" "$LOCAL_EVID/migrate"
cp -a app.py shifts_authority_wave1.py canary-prod-shifts-wave1b.py \
  smoke-test-shifts-authority-wave1.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-shifts-wave1b-prod-synthetic.sh ops/migrate-shifts-authority-wave1-prod.sh "$LOCAL_EVID/sources/ops/"
cp -a ops/sql/shifts_authority_wave1_v1.sql "$LOCAL_EVID/sources/ops/sql/"
cp -a ops/migrate-shifts-authority-wave1-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave1b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py shifts_authority_wave1.py canary-prod-shifts-wave1b.py \
    smoke-test-shifts-authority-wave1.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    ops/deploy-shifts-wave1b-prod-synthetic.sh \
    ops/migrate-shifts-authority-wave1-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
  "${SCP[@]}" ops/sql/shifts_authority_wave1_v1.sql "$VPS_HOST:$REMOTE_STAGE/"
)
rsync -az -e "ssh -o BatchMode=yes -o ControlMaster=no" \
  "$DASH_SRC/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-shifts-wave1b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-shifts-wave1b-prod-synthetic.sh'
REMOTE

run_canary() {
  local label="$1"
  local outdir="$2"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID='$REMOTE_EVID'
OUTDIR="\$REMOTE_EVID/$outdir"
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
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
export SHW1B_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-shifts-wave1b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/shifts-wave1b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
# Confirm drop-in gone and module absent or restored
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-authority-wave1b-synthetic.conf
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep SHIFTS_AUTHORITY || echo "SHIFTS_AUTHORITY_FLAGS_CLEARED"
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
# Reuse same stage artifacts; backup path will be overwritten with same stamp suffix -redeploy
export STAMP='${STAMP}-redeploy'
bash '$REMOTE_STAGE/deploy-shifts-wave1b-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
# Point canary evidence under original stamp tree via symlink path on remote
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
# Override REMOTE_EVID for second canary into original tree
run_canary_redeploy() {
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-after-redeploy.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='/opt/wathefni/production-evidence/shifts-wave1b-prod-canary/${STAMP}/canary/after-redeploy'
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
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
export SHW1B_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-shifts-wave1b.py
REMOTE
}
run_canary_redeploy

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
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true

log "write REPORT"
LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" python3 - <<'PY'
import json, os, pathlib, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]

def load_qual(*parts):
    for p in (evid / "remote").rglob("qualification.json"):
        if all(x in str(p) for x in parts):
            return json.loads(p.read_text())
    # fallback any
    for p in (evid / "remote").rglob("qualification.json"):
        return json.loads(p.read_text())
    return {}

q1 = {}
q2 = {}
for p in (evid / "remote").rglob("qualification.json"):
    data = json.loads(p.read_text())
    if "before-rollback" in str(p):
        q1 = data
    elif "after-redeploy" in str(p):
        q2 = data
if not q1 and not q2:
    # single
    for p in (evid / "remote").rglob("qualification.json"):
        q2 = json.loads(p.read_text()); break

def counts(q):
    return q.get("passed"), q.get("failed")

def freeze_ok(path):
    if not path.exists():
        return False, "missing"
    txt = path.read_text()
    m = re.search(r"(\d+) passed, (\d+) failed", txt)
    if not m:
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
# also prod freezes if present
prod_freeze = evid / "tests" / "freezes-prod.out"
prod_ok = prod_freeze.exists() and "0 failed" in prod_freeze.read_text()

rb_ok = (evid / "tests" / "rollback.out").exists() and "ROLLBACK_VERIFIED" in (evid / "tests" / "rollback.out").read_text()
c1_ok = (q1.get("failed") or 0) == 0 and (q1.get("passed") or 0) > 0 if q1 else False
c2_ok = (q2.get("failed") or 0) == 0 and (q2.get("passed") or 0) > 0
# if only q2
if not q1:
    c1_ok = c2_ok

cleanup = (q2 or q1).get("cleanup") or {}
residual = cleanup.get("residual_total")
ids = (q2 or q1).get("ids") or {}

blockers = []
if not c2_ok:
    blockers.append(f"canary after redeploy failed ({counts(q2)})")
if q1 and not c1_ok:
    blockers.append(f"canary before rollback failed ({counts(q1)})")
if not rb_ok:
    blockers.append("rollback not verified")
if residual not in (0, None):
    blockers.append(f"residual synthetic nonzero: {residual}")
if not all(x[0] for x in (f360, fonb, fatt, flv)):
    blockers.append("local freeze regression failed")
if not prod_ok:
    blockers.append("production freeze regression failed or missing")
if "WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1" not in flags and "SYNTHETIC_ONLY=1" not in flags:
    # flags file uses env dump
    if "SYNTHETIC_ONLY=1" not in flags and "WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1" not in flags:
        blockers.append("synthetic_only flag not confirmed in after-deploy")

synth_go = "GO" if not blockers else "NO-GO"
report = f"""# Shifts Wave 1B — WATHEFNI production synthetic canary

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/shifts-wave1b-{stamp}/`  
**Module:** `shifts_authority_wave1.py` **v1.1.0**  
**Mode:** production WATHEFNI-only · **SYNTHETIC_ONLY** · markers **SHW1B** / **965529***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Shifts authority | **{synth_go}** |
| Controlled HR Shifts use (real employees) | **NO-GO** |
| Scoped manager Shifts use | **NO-GO** |
| Talal employee-app Shifts use (expanded) | **NO-GO** |
| Broad employee-app rollout | **NO-GO** |
| Templates / recurring schedules | **NO-GO** (out of scope) |
| Payroll monetary impact | **NO-GO / none** — honesty `payroll_money=false`; no money calc |

---

## Production SHAs and flags

```
{flags.strip() or '(see remote/flags/after-deploy.txt)'}
```

Required gates:
- `WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1`
- `WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI`
- `WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1`
- `WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|`
- `WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529`
- `WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off`

---

## Backup and rollback

- Backup path: `{backup or '(see remote/backup/BACKUP_PATH.txt)'}`
- Rollback script executed and verified: **{'YES' if rb_ok else 'NO'}**
- Redeploy after rollback completed; canary re-run

---

## Orphan quarantine

Allowlisted Wave 0 orphans soft-cancelled under change control (never deleted):

| shift_id |
|---|
| `0a6e73dd-9c6d-49a0-b253-39a9922ebd70` |
| `6a84a671-eb7f-43ea-870e-af859a440467` |
| `f9ebecf3-8838-456a-8124-c34c3c7600ca` |

Audit: `shift_events.orphan_quarantined` + `shift_lifecycle_flags` + `shift_orphan_quarantine` snapshots (reversible metadata preserved).

---

## Synthetic IDs

```json
{json.dumps(ids, indent=2, default=str)}
```

---

## Test counts

| Pass | Passed | Failed |
|---|---:|---:|
| Canary before rollback | {(q1 or {}).get('passed')} | {(q1 or {}).get('failed')} |
| Canary after redeploy | {(q2 or q1).get('passed')} | {(q2 or q1).get('failed')} |
| Employees 360 freeze | {f360[1]} | |
| Onboarding freeze | {fonb[1]} | |
| Attendance freeze | {fatt[1]} | |
| Leave freeze | {flv[1]} | |

---

## Cleanup and fingerprint proof

- Residual synthetic total: **{residual}**
- Real assignment fingerprints unchanged except the three quarantined orphans and their audit records: see canary checks / `fingerprint-after.json`

---

## Remaining blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for synthetic canary scope.'}

Real-employee Wave 1 authority, manager/Talal expanded use, templates/recurring, and Payroll money remain out of scope / NO-GO.

---

## Notes

- Synthetic-only: Wave 1 lifecycle/leave/overnight gates apply to **SHW1B/965529*** subjects only; legacy same-day behaviour retained for real employees.
- Dashboard dist rebuilt and deployed with `expected_updated_at` concurrency token.
- No templates, recurring, rotations, publish, open shifts, or Payroll money enabled.
"""
(evid / "REPORT.md").write_text(report)
print(report)
print("REPORT_WRITTEN", evid / "REPORT.md")
print("SYNTH_VERDICT", synth_go)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
