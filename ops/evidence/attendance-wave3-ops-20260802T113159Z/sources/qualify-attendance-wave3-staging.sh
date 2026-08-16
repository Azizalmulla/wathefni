#!/usr/bin/env bash
# Wave 3 — staging-only qualify for HR/manager attendance operations.
# NO production deploy, NO real clocking, NO devices, NO QR/GPS/kiosk.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave3-ops-$STAMP"
REMOTE_STAGE="/tmp/attw3-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/attendance-wave3-ops-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources}
echo "$LOCAL_EVID" > /tmp/attw3.evid
echo "$STAMP" > /tmp/attw3.stamp

FILES=(
  attendance_ops_wave3.py
  attendance_ops_postgres.py
  attendance_ops_http.py
  smoke-test-attendance-ops-wave3.py
  attendance_authority_wave1.py
  attendance_authority_postgres.py
)

log() { printf '\n=== %s ===\n' "$*"; }

log "local qualify"
cd "$ORCH_SRC"
ATTW3_RESULTS_PATH="$LOCAL_EVID/tests/qualification-local.json" \
  WATHEFNI_ENV=local \
  .venv/bin/python smoke-test-attendance-ops-wave3.py 2>&1 | tee "$LOCAL_EVID/tests/qualify-local.out"

for f in "${FILES[@]}"; do
  cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true
done
cp -a "$ORCH_SRC/ops/migrate-attendance-ops-wave3.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/qualify-attendance-wave3-staging.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push to staging + qualify"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID' '$STAGING_ORCH'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${FILES[@]}" "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$ORCH_SRC/ops/migrate-attendance-ops-wave3.sh" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/qualify-staging.out"
set -euo pipefail
STAGING_ORCH='$STAGING_ORCH'
REMOTE_STAGE='$REMOTE_STAGE'
REMOTE_EVID='$REMOTE_EVID'
mkdir -p "\$REMOTE_EVID/tests" "\$REMOTE_EVID/docs" "\$REMOTE_EVID/sources"
cp -a "\$REMOTE_STAGE"/*.py "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE"/migrate-attendance-ops-wave3.sh "\$STAGING_ORCH/ops/" 2>/dev/null || mkdir -p "\$STAGING_ORCH/ops" && cp -a "\$REMOTE_STAGE"/migrate-attendance-ops-wave3.sh "\$STAGING_ORCH/ops/"
cp -a "\$REMOTE_STAGE"/*.py "\$REMOTE_EVID/sources/"

# Patch drop-in env for ops (do not enable real clocking / capture ingest)
DROPIN=/opt/wathefni/staging/orchestrator.env.d/attendance-wave3-ops.env
mkdir -p /opt/wathefni/staging/orchestrator.env.d
cat > "\$DROPIN" <<'ENV'
WATHEFNI_ATTENDANCE_OPS=on
WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI,ATTW3
WATHEFNI_ATTENDANCE_OPS_STORE=postgres
WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
# Keep capture ingest off
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
ENV
echo "wrote \$DROPIN"

cd "\$STAGING_ORCH"
# Migrate schema against staging DB
if [[ -f /opt/wathefni/staging/orchestrator.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /opt/wathefni/staging/orchestrator.env
  set +a
fi
for f in /opt/wathefni/staging/orchestrator.env.d/*.env; do
  [[ -f "\$f" ]] || continue
  set -a
  # shellcheck disable=SC1090
  source "\$f"
  set +a
done
export WATHEFNI_ENV=staging
export ACK_DB="\${ACK_DB:-\${WATHEFNI_EXPECTED_DATABASE_NAME:-\${PGDATABASE:-wathefni_staging}}}"
if [[ "\$ACK_DB" == "wathefni" ]]; then
  echo "REFUSE production db on staging qualify"
  exit 2
fi
ORCH_PYTHON="\${ORCH_PYTHON:-./.venv/bin/python}"
if [[ ! -x "\$ORCH_PYTHON" ]]; then ORCH_PYTHON=python3; fi
ACK_DB="\$ACK_DB" WATHEFNI_ENV=staging ORCH_PYTHON="\$ORCH_PYTHON" \
  bash ops/migrate-attendance-ops-wave3.sh 2>&1 | tee "\$REMOTE_EVID/tests/migrate.out"

ATTW3_RESULTS_PATH="\$REMOTE_EVID/tests/qualification-staging.json" \
  WATHEFNI_ENV=staging \
  WATHEFNI_SKIP_FREEZE=0 \
  "\$ORCH_PYTHON" smoke-test-attendance-ops-wave3.py 2>&1 | tee "\$REMOTE_EVID/tests/qualify-staging-smoke.out"

# Leak scan
if grep -RInE 'password\\s*=\\s*["'\\''][^"'\\'']+|api[_-]?key|BEGIN (RSA |OPENSSH )?PRIVATE' "\$REMOTE_EVID" 2>/dev/null | head; then
  echo "LEAK SCAN FAILED"
  exit 3
fi
echo "leak scan clean"
echo "REMOTE_EVID=\$REMOTE_EVID"
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true

# Write REPORT
python3 - <<PY
import json, pathlib, datetime
evid = pathlib.Path("$LOCAL_EVID")
local = evid / "tests" / "qualification-local.json"
staging = evid / "remote" / "tests" / "qualification-staging.json"
def load(p):
    if p.exists():
        return json.loads(p.read_text())
    # try nested
    alt = evid / "remote" / "qualification-staging.json"
    return json.loads(alt.read_text()) if alt.exists() else {}
L = load(local) if local.exists() else {}
S = {}
if staging.exists():
    S = json.loads(staging.read_text())
else:
    for p in (evid / "remote").rglob("qualification-staging.json"):
        S = json.loads(p.read_text()); break

def summary(d, label):
    if not d:
        return f"- {label}: MISSING"
    return f"- {label}: {d.get('passed')}/{d.get('total')} passed, {d.get('failed')} failed"

blockers = []
if not L or L.get("failed", 1):
    blockers.append("local smoke incomplete or failing")
if not S or S.get("failed", 1):
    blockers.append("staging smoke incomplete or failing")

go_canary = "CONDITIONAL GO" if not blockers else "NO-GO"
# Production synthetic ops canary: only after staging green; still no real clocking.
report = f"""# Attendance Wave 3 — HR/Manager Ops Qualify

**Stamp:** $STAMP
**Scope:** local + staging only (no production deploy, no real clocking, no devices)

## Results
{summary(L, "local")}
{summary(S, "staging")}

## State model
Exception kinds: missing_check_in/out, ambiguous_punches, incomplete_session, absence, lateness, early_leave, connector_issue.

Statuses: open → assigned → in_review → pending_dual_approval → resolved|rejected|reopened → closed.

Correction cases: requested → under_review → approved|rejected → applied (separate apply; idempotent).

Disputes: open → under_review → upheld|overturned → optional reopen.

## Permission / ownership matrix
| Actor | Open/assign | Request correction | Review | Apply | Dispute | Reopen |
|-------|-------------|--------------------|--------|-------|---------|--------|
| HR | yes | yes | yes | yes | resolve | yes |
| Manager (configured, in Employees 360 scope) | yes | yes (not self) | yes (not self) | yes (not self) | resolve | limited |
| Manager unconfigured | deny | deny | deny | deny | deny | deny |
| Manager out of scope | deny | deny | deny | deny | deny | deny |
| Manager self | deny | deny | deny | deny | deny | deny |
| Employee | — | — | — | — | raise | — |

Ownership: exception.owner_phone + priority + due_at. Dual approval required for absence/early_leave (policy kinds).

## Workflow
1. Projection/connector opens exception (payroll_excluded=true).
2. Owner assigned; correction requested (authority correction row + ops case).
3. Review approve/reject **without** mutating punches.
4. Apply (idempotent) creates correction punches + new day-projection version.
5. Dispute → review → resolution; reopen with new evidence if unlocked.

## Rules enforced
- Raw punches immutable; corrections create new projection versions
- Incomplete/disputed excluded from payroll
- Locked payroll periods deny mutation
- Leave reversal preserves later manual corrections
- Optimistic concurrency (row_version) fail-closed
- Tenant isolation by company_code

## Remaining blockers
{chr(10).join('- ' + b for b in blockers) or '- none for staging ops qualification'}

## GO/NO-GO — WATHEFNI-only production **synthetic** ops canary
**{go_canary}**

Conditions for full GO later:
- Staging smoke 0 failures
- Employees 360 + Onboarding freezes green
- Production canary must keep CAPTURE_INGEST=off, AUTHORITY_SYNTHETIC_ONLY=on, OPS synthetic markers only
- No customer devices, no real clocking, no QR/GPS/kiosk

**Real clocking / customer devices / full Attendance UI redesign: NO-GO**
"""
(evid / "REPORT.md").write_text(report)
print(report)
print("EVIDENCE", evid)
PY

log "done — evidence at $LOCAL_EVID"
