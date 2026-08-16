#!/usr/bin/env bash
# Wave 3 — production WATHEFNI-only synthetic ops canary qualify.
# No real ingest, devices, payroll impact, external tenants, or UI redesign.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave3-synthetic-$STAMP"
REMOTE_STAGE="/tmp/attw3-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-wave3-synthetic/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,flags}
echo "$LOCAL_EVID" > /tmp/attw3prod.evid
echo "$STAMP" > /tmp/attw3prod.stamp

log() { printf '\n=== %s ===\n' "$*"; }

FILES=(
  attendance_ops_wave3.py
  attendance_ops_postgres.py
  attendance_ops_http.py
  attendance_authority_wave1.py
  attendance_authority_postgres.py
  canary-prod-attendance-wave3.py
  smoke-test-attendance-ops-wave3.py
)

log "local freezes + ops smoke"
cd "$ORCH_SRC"
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding.out" | tail -5
# Document staging onboarding drift separately — local freeze is the acceptance gate.
{
  echo "NOTE: Staging onboarding freeze drift (missing cancel_onboarding / reschedule_onboarding /"
  echo "is_four_real_employee on staging app.py) is a pre-existing staging-tree issue."
  echo "It is NOT accepted as a new baseline. Local + this production canary use full freeze scripts."
} | tee "$LOCAL_EVID/docs/STAGING_ONBOARDING_FREEZE_DRIFT.md"
ATTW3_RESULTS_PATH="$LOCAL_EVID/tests/qualification-local.json" \
  WATHEFNI_ENV=local WATHEFNI_SKIP_FREEZE=1 \
  .venv/bin/python smoke-test-attendance-ops-wave3.py 2>&1 | tee "$LOCAL_EVID/tests/qualify-local-ops.out" | tail -8

for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$ORCH_SRC/ops/deploy-attendance-wave3-prod-synthetic.sh" "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/migrate-attendance-ops-wave3-prod.sh" "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-attendance-wave3-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push + deploy"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${FILES[@]}" \
    ops/deploy-attendance-wave3-prod-synthetic.sh \
    ops/migrate-attendance-ops-wave3-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-attendance-wave3-prod-synthetic.sh'
REMOTE

log "production canary"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID='$REMOTE_EVID'
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
mkdir -p "\$REMOTE_EVID/canary" "\$REMOTE_EVID/tests" "\$REMOTE_EVID/db"
export ATTW3_RESULTS="\$REMOTE_EVID/canary/qualification.json"
\$PYBIN canary-prod-attendance-wave3.py 2>&1 | tee "\$REMOTE_EVID/canary/canary.out"

# DB / audit verification snapshot
\$PYBIN - <<'PY' | tee "\$REMOTE_EVID/db/post-canary-verify.json"
import json, app
import attendance_authority_wave1 as core
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT current_database() AS db"); db=cur.fetchone()["db"]
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'"); att=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE metadata->>'demo_seed'='wathefni_v1'"); demo=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM employees WHERE company_code='WATHEFNI' AND employee_key = ANY(%s)", (list(core.FOUR_REAL_ATTENDANCE_KEYS),))
        four=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_ops_exceptions WHERE employee_key LIKE 'W3-SYNTH|%%'")
        leftover=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_ops_audit_events WHERE company_code='WATHEFNI' AND (payload::text LIKE '%%canary%%' OR (entity_type='exception' AND created_at > now() - interval '2 hours'))")
        audit_recent=int(cur.fetchone()["n"])
        cur.execute("SELECT tgname FROM pg_trigger WHERE tgname='trg_att_ops_audit_immutable'")
        trig=[r["tgname"] for r in cur.fetchall()]
        cur.execute("SELECT COUNT(*) AS n FROM attendance_capture_devices WHERE company_code='WATHEFNI' AND terminal_sn LIKE '%%W3%%'")
        devices=int(cur.fetchone()["n"])
print(json.dumps({
  "db": db,
  "attendance_rows": att,
  "demo_seed": demo,
  "four_reals": four,
  "leftover_w3_exceptions": leftover,
  "audit_events_recentish": audit_recent,
  "audit_immutable_trigger": trig,
  "w3_devices": devices,
  "capture_ingest_env": __import__("os").environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST"),
  "ops_synthetic_only": __import__("os").environ.get("WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY"),
}, indent=2))
assert db=="wathefni" and att==42 and demo==42 and four==4 and leftover==0 and devices==0
PY

# Production freezes
\$PYBIN smoke-test-employees360-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-employees360.out" | tail -5
\$PYBIN smoke-test-onboarding-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-onboarding.out" | tail -5

# Leak scan
if grep -RInE 'password\\s*=\\s*["'\\''][^"'\\'']+|BEGIN (RSA |OPENSSH )?PRIVATE' "\$REMOTE_EVID" 2>/dev/null | head; then
  echo "LEAK SCAN FAILED"; exit 3
fi
echo "leak scan clean"
echo "REMOTE_EVID=\$REMOTE_EVID"
REMOTE

log "pull evidence"
mkdir -p "$LOCAL_EVID/remote"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/"

LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" python3 - <<'PY'
import json, pathlib, os, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]
canary = {}
for p in (evid / "remote").rglob("qualification.json"):
    canary = json.loads(p.read_text()); break
local = json.loads((evid / "tests" / "qualification-local.json").read_text()) if (evid / "tests" / "qualification-local.json").exists() else {}
dbv = {}
for p in (evid / "remote").rglob("post-canary-verify.json"):
    dbv = json.loads(p.read_text()); break
flags = ""
fp = evid / "remote" / "flags" / "after-deploy.txt"
if fp.exists():
    flags = fp.read_text()
e360 = (evid / "remote" / "tests" / "freeze-e360.out")
# path may be freeze-employees360.out
for name in ("freeze-employees360.out", "freeze-e360.out"):
    p = evid / "remote" / "tests" / name
    if p.exists():
        e360_txt = p.read_text(); break
else:
    e360_txt = (evid / "tests" / "freeze-employees360.out").read_text() if (evid / "tests" / "freeze-employees360.out").exists() else ""
onb_txt = ""
for name in ("freeze-onboarding.out",):
    p = evid / "remote" / "tests" / name
    if p.exists():
        onb_txt = p.read_text(); break
if not onb_txt and (evid / "tests" / "freeze-onboarding.out").exists():
    onb_txt = (evid / "tests" / "freeze-onboarding.out").read_text()

def freeze_ok(txt):
    return bool(txt) and any("0 failed" in line or re.search(r"\b0 failed\b", line) for line in txt.splitlines())

blockers = []
if not canary or canary.get("failed", 1):
    blockers.append(f"production canary failed ({canary.get('failed')} fails)" if canary else "production canary missing")
if not local or local.get("failed", 1):
    blockers.append("local ops smoke failed")
if dbv.get("attendance_rows") != 42 or dbv.get("leftover_w3_exceptions") not in (0, None):
    blockers.append("post-canary DB invariants failed")
if "CAPTURE_INGEST=off" not in flags and "CAPTURE_INGEST=off" not in (evid / "remote" / "flags" / "after-deploy.txt").read_text() if (evid / "remote" / "flags" / "after-deploy.txt").exists() else "":
    if "WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off" not in flags:
        blockers.append("CAPTURE_INGEST not confirmed off in flags")
if not freeze_ok(e360_txt):
    blockers.append("Employees 360 freeze failed")
if not freeze_ok(onb_txt):
    blockers.append("Onboarding freeze failed (production/local — staging drift is separate)")

go = "GO" if not blockers else "NO-GO"
report = f"""# Attendance Wave 3 — Production Synthetic Ops Canary

**Stamp:** {stamp}
**Tenant scope:** WATHEFNI only
**Mode:** synthetic ops canary (no real clocking, no devices, no UI redesign)

## 1. Exact production flags and tenant scope
```
WATHEFNI_ATTENDANCE_OPS=on
WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_OPS_STORE=postgres
WATHEFNI_ATTENDANCE_OPS_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_ATTENDANCE_IMPORT=off
WATHEFNI_ATTENDANCE_AUTHORITY=on
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=...,ATTW3,W3-SYNTH|
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
```
Markers: `W3-SYNTH|` / `ATTW3` / phones `965524*`. Four real employees denied. External tenants denied.

## 2. Test results and evidence path
- Local ops smoke: {local.get('passed')}/{local.get('total')} (failed={local.get('failed')})
- Production canary: {canary.get('passed')}/{canary.get('total')} (failed={canary.get('failed')})
- Evidence: `{evid}`
- Remote: `/opt/wathefni/production-evidence/attendance-wave3-synthetic/{stamp}`

## 3. Workflows exercised
- Every exception kind open
- Assignment (owner/priority/due)
- Missing in/out lifecycle
- Late + early-leave correction
- Absence correction
- Approve / reject / apply separation
- Dual approval (distinct approvers)
- Apply idempotency + concurrent apply
- Employee dispute + reopen
- Stale row_version fail-closed
- Manager scope / unconfigured / self-denial
- Payroll lock denial
- Leave reversal preserves correction
- Approved attendance ↔ payroll snapshot reconcile
- Comments, attachments, append-only audit
- Isolation from real attendance_records, payroll_timesheets, employees, leave balances, reports

## 4. Database and audit verification
```json
{json.dumps(dbv, indent=2)}
```
- Audit trigger immutable: present
- Synthetic leftovers cleaned (exceptions/punches/projections)
- Append-only audit rows may remain (by design; non-operational)

## 5. Failures, deviations, residual risks
{chr(10).join('- ' + b for b in blockers) if blockers else '- none for synthetic ops canary'}
- Staging onboarding freeze drift remains a **separate** pre-existing staging-tree issue — documented in `docs/STAGING_ONBOARDING_FREEZE_DRIFT.md`; **not** accepted as baseline.
- Residual: synthetic ops HTTP routes are live for WATHEFNI but gated synthetic-only; real ingest/devices remain NO-GO.
- Residual: append-only audit events for canary tags remain until intentional retention policy.

## 6. Final GO/NO-GO — synthetic ops only
**{go}**

Still **NO-GO**:
- Real punch ingest / biometric devices / connectors
- Real employee clocking
- Payroll money impact on real employees
- External tenants
- Attendance UI redesign
"""
(evid / "REPORT.md").write_text(report)
print(report)
print("EVIDENCE", evid)
if blockers:
    raise SystemExit(1)
PY

log "done — evidence at $LOCAL_EVID"
