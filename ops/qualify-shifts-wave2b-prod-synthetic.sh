#!/usr/bin/env bash
# Shifts Wave 2B — production WATHEFNI synthetic schedule-integrity canary qualify.
# Deploy → canary → rollback → redeploy → canary → cleanup/fingerprint → Wave1 + freezes.
# Does NOT enable real-employee mutations, templates, recurring, publish, open shifts, or Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave2b-$STAMP"
REMOTE_STAGE="/tmp/shifts-w2b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave2b-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,pre,cleanup,rollback,artifacts,jobs}
echo "$LOCAL_EVID" > /tmp/shw2b.evid
echo "$STAMP" > /tmp/shw2b.stamp
echo "$STAMP" > /tmp/w2b-stamp.txt

log() { printf '\n=== %s ===\n' "$*"; }

log "local freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3

log "stage sources"
cd "$ORCH_SRC"
mkdir -p "$LOCAL_EVID/sources/ops/sql" "$LOCAL_EVID/sources/ops/runbooks" "$LOCAL_EVID/migrate"
cp -a app.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py \
  canary-prod-shifts-wave2b.py \
  smoke-test-shifts-authority-wave1.py \
  smoke-test-shifts-schedule-integrity-wave2.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-shifts-wave2b-prod-synthetic.sh \
  ops/migrate-shifts-schedule-integrity-wave2-prod.sh \
  ops/run-shifts-wave2b-jobs.sh \
  "$LOCAL_EVID/sources/ops/"
cp -a ops/sql/shifts_schedule_integrity_wave2_v1.sql "$LOCAL_EVID/sources/ops/sql/"
cp -a ops/runbooks/shifts-wave2b-operator-jobs.md "$LOCAL_EVID/sources/ops/runbooks/"
cp -a ops/migrate-shifts-schedule-integrity-wave2-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave2b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py shifts_authority_wave1.py shifts_schedule_integrity_wave2.py \
    canary-prod-shifts-wave2b.py \
    smoke-test-shifts-authority-wave1.py \
    smoke-test-shifts-schedule-integrity-wave2.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    ops/deploy-shifts-wave2b-prod-synthetic.sh \
    ops/migrate-shifts-schedule-integrity-wave2-prod.sh \
    ops/run-shifts-wave2b-jobs.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
  "${SCP[@]}" ops/sql/shifts_schedule_integrity_wave2_v1.sql "$VPS_HOST:$REMOTE_STAGE/"
  "${SCP[@]}" ops/runbooks/shifts-wave2b-operator-jobs.md "$VPS_HOST:$REMOTE_STAGE/"
)

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-shifts-wave2b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-shifts-wave2b-prod-synthetic.sh'
REMOTE

run_canary() {
  local label="$1"
  local outdir="$2"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='/opt/wathefni/production-evidence/shifts-wave2b-prod-canary/${STAMP}/$outdir'
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
export SHW2B_EVID="\$OUTDIR"
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-shifts-wave2b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/shifts-wave2b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-integrity-wave2b-synthetic.conf
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep SHIFTS_INTEGRITY || echo "SHIFTS_INTEGRITY_FLAGS_CLEARED"
# Wave 1B synthetic posture should still be present after Wave 2B rollback
tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep SHIFTS_AUTHORITY_WAVE1 || echo "WAVE1_FLAG_MISSING"
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-shifts-wave2b-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
run_canary canary-after-redeploy canary/after-redeploy

log "Wave 1 regression + production freezes"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/wave1-and-freezes-prod.out"
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
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
export PYTHONUNBUFFERED=1
echo '=== WAVE1 SMOKE ==='
\$PY -u smoke-test-shifts-authority-wave1.py
echo '=== E360 ==='
\$PY smoke-test-employees360-freeze-regression.py
echo '=== ONBOARDING ==='
\$PY smoke-test-onboarding-freeze-regression.py
echo '=== ATTENDANCE ==='
\$PY smoke-test-attendance-freeze-regression.py
echo '=== LEAVE ==='
\$PY smoke-test-leave-freeze-regression.py
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
# Also copy redeploy backup path reference if present
"${SSH[@]}" "ls -la /opt/wathefni/production-evidence/shifts-wave2b-prod-canary/" | tee "$LOCAL_EVID/remote/evidence-index.txt" || true

log "write REPORT"
LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" python3 - <<'PY'
import json, os, pathlib, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]

def load_qual(part):
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
prod = evid / "tests" / "wave1-and-freezes-prod.out"
prod_txt = prod.read_text() if prod.exists() else ""
prod_ok = prod.exists() and prod_txt.count("0 failed") >= 4 and "SMOKE_FAILED" not in prod_txt
w1m = re.search(r"(\d+) passed, (\d+) failed", prod_txt.split("=== E360 ===")[0] if "=== E360 ===" in prod_txt else "")
w1 = (int(w1m.group(2)) == 0, f"{w1m.group(1)}/{w1m.group(2)}") if w1m else (False, "missing")

rb_ok = (evid / "tests" / "rollback.out").exists() and "ROLLBACK_VERIFIED" in (evid / "tests" / "rollback.out").read_text()
c1_ok = (q1.get("failed") or 0) == 0 and (q1.get("passed") or 0) > 0 if q1 else False
c2_ok = (q2.get("failed") or 0) == 0 and (q2.get("passed") or 0) > 0
if not q1:
    c1_ok = c2_ok

cleanup = (q2 or q1).get("cleanup") or {}
residual = cleanup.get("total", cleanup.get("residual_total"))
ids = (q2 or q1).get("ids") or {}
fps = (q2 or q1).get("fingerprints") or {}

blockers = []
if not c2_ok:
    blockers.append(f"canary after redeploy failed ({q2.get('passed')}/{q2.get('failed')})")
if q1 and not c1_ok:
    blockers.append(f"canary before rollback failed ({q1.get('passed')}/{q1.get('failed')})")
if not rb_ok:
    blockers.append("rollback not verified")
if residual not in (0, None):
    blockers.append(f"residual synthetic nonzero: {residual}")
if not all(x[0] for x in (f360, fonb, fatt, flv)):
    blockers.append("local freeze regression failed")
if not prod_ok:
    blockers.append("production Wave1/freeze regression failed or incomplete")
if "WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1" not in flags:
    blockers.append("Wave2 synthetic_only flag not confirmed")
if "WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1" not in flags:
    blockers.append("Wave2 enable flag not confirmed")

synth_go = "GO" if not blockers else "NO-GO"
report = f"""# Shifts Wave 2B — WATHEFNI production synthetic schedule-integrity canary

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/shifts-wave2b-{stamp}/`  
**Module:** `shifts_schedule_integrity_wave2.py` **v2.0.0** (+ Wave 1 authority 1.1.0)  
**Mode:** production WATHEFNI-only · **SYNTHETIC_ONLY** · markers **SHW2B** / **965530***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Schedule Integrity | **{synth_go}** |
| Controlled HR scheduling | **NO-GO** |
| Scoped manager scheduling | **NO-GO** |
| Talal employee-app scheduling | **NO-GO** |
| Broad employee-app rollout | **NO-GO** |
| Templates and recurring schedules | **NO-GO** (out of scope) |
| Payroll monetary impact | **NO-GO / none** — `payroll_money=false`; no money calculations |

---

## Production SHAs and flags

```
{flags.strip() or '(see remote/flags/after-deploy.txt)'}
```

Required gates:
- `WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1` · `COMPANIES=WATHEFNI` · `SYNTHETIC_ONLY=1`
- Wave 1 markers extended: `SHW1B,SHW1B-SYNTH|,SHW2B,SHW2B-SYNTH|` / phones `965529,965530`
- `WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1`
- `WATHEFNI_SHIFTS_INTEGRITY_COMPANIES=WATHEFNI`
- `WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1`
- `WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2B,SHW2B-SYNTH|`
- `WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965530`
- `WATHEFNI_SHIFTS_INTEGRITY_JOBS=1`
- `WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off`

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-integrity-wave2b-synthetic.conf`

---

## Backup and rollback

- Backup path: `{backup or '(see remote/backup/BACKUP_PATH.txt)'}`
- Rollback verified: **{'YES' if rb_ok else 'NO'}**
- Redeploy after rollback completed; canary re-run

---

## Job schedules, locking, runbooks

See `ops/runbooks/shifts-wave2b-operator-jobs.md` and `ops/run-shifts-wave2b-jobs.sh`.

| Job | Lock | Bound |
|---|---|---|
| Reminder drain | `820260201` | limit ≤200 |
| Lifecycle recon | `820260202` | flag-only, synthetic filter |
| Leave recon | `820260203` | flag-only, synthetic filter |

Kill switch: `WATHEFNI_SHIFTS_INTEGRITY_JOBS=0`. Concurrent overlaps return `job_lock_held`.

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
| Wave 1 smoke (prod) | {w1[1]} | |
| Employees 360 freeze (local) | {f360[1]} | |
| Onboarding freeze (local) | {fonb[1]} | |
| Attendance freeze (local) | {fatt[1]} | |
| Leave freeze (local) | {flv[1]} | |

---

## Cleanup and fingerprint proof

- Residual synthetic total: **{residual}**
- Fingerprint summary: `{json.dumps({k: fps.get(k) for k in ('before_count','after_count','drift','extra','changed','extras') if k in fps}, default=str)}`
- Cleanup details: `{json.dumps(cleanup, indent=2, default=str)[:2000]}`

---

## Remaining blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for synthetic Schedule Integrity canary closure.'}

Still **NO-GO** (separate auth required): real-employee HR scheduling, scoped manager scheduling, Talal employee-app scheduling, broad employee-app, templates/recurring/rotations/publishing/open shifts/PAM, Payroll money.

---

## Bottom line

Production synthetic Schedule Integrity canary: **{synth_go}**.
"""
(evid / "REPORT.md").write_text(report)
print(report)
print("REPORT_WRITTEN", evid / "REPORT.md")
if blockers:
    raise SystemExit(1)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
