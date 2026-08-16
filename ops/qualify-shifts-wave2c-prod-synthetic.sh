#!/usr/bin/env bash
# Shifts Wave 2C — canary compatibility + qualification closure (production synthetic).
# Deploys shared cleanup + disabled-by-default job timers; proves Wave1B/Wave2B residual 0,
# cross-marker isolation, interrupted cleanup idempotency, fingerprints, freezes.
# Does NOT enable real-employee mutations, activate recurring timers for real records,
# build dashboard UX, templates/recurring, or Payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave2c-$STAMP"
REMOTE_STAGE="/tmp/shifts-w2c-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/shifts-wave2c-compat/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,artifacts}
echo "$LOCAL_EVID" > /tmp/shw2c.evid
echo "$STAMP" > /tmp/shw2c.stamp
echo "$STAMP" > /tmp/w2c-stamp.txt

log() { printf '\n=== %s ===\n' "$*"; }

require_pass() {
  local file="$1"
  local label="$2"
  if grep -E '^[0-9]+ passed, 0 failed' "$file" >/dev/null 2>&1; then
    echo "OK $label"
  else
    echo "FAIL $label — see $file" >&2
    tail -40 "$file" >&2 || true
    exit 1
  fi
}

log "local freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
require_pass "$LOCAL_EVID/tests/freeze-employees360-local.out" "e360-local"
require_pass "$LOCAL_EVID/tests/freeze-onboarding-local.out" "onboarding-local"
require_pass "$LOCAL_EVID/tests/freeze-attendance-local.out" "attendance-local"
require_pass "$LOCAL_EVID/tests/freeze-leave-local.out" "leave-local"

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops/runbooks" "$LOCAL_EVID/sources/ops/sql"
cp -a \
  shifts_synthetic_cleanup.py \
  prove-shifts-wave2c-compat.py \
  canary-prod-shifts-wave1b.py \
  canary-prod-shifts-wave2b.py \
  shifts_schedule_integrity_wave2.py \
  shifts_authority_wave1.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/install-shifts-wave2-job-timers.sh ops/run-shifts-wave2b-jobs.sh \
  ops/wathefni-shifts-reminder-drain.service ops/wathefni-shifts-reminder-drain.timer \
  ops/wathefni-shifts-lifecycle-recon.service ops/wathefni-shifts-lifecycle-recon.timer \
  ops/wathefni-shifts-leave-recon.service ops/wathefni-shifts-leave-recon.timer \
  "$LOCAL_EVID/sources/ops/"
cp -a ops/runbooks/shifts-wave2b-operator-jobs.md "$LOCAL_EVID/sources/ops/runbooks/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave2c-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'/{canary,prove,timers,flags,preflight}"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" \
    shifts_synthetic_cleanup.py \
    prove-shifts-wave2c-compat.py \
    canary-prod-shifts-wave1b.py \
    canary-prod-shifts-wave2b.py \
    ops/install-shifts-wave2-job-timers.sh \
    ops/run-shifts-wave2b-jobs.sh \
    ops/wathefni-shifts-reminder-drain.service \
    ops/wathefni-shifts-reminder-drain.timer \
    ops/wathefni-shifts-lifecycle-recon.service \
    ops/wathefni-shifts-lifecycle-recon.timer \
    ops/wathefni-shifts-leave-recon.service \
    ops/wathefni-shifts-leave-recon.timer \
    ops/runbooks/shifts-wave2b-operator-jobs.md \
    "$VPS_HOST:$REMOTE_STAGE/"
)

log "deploy modules + install disabled timers"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
STAGE='$REMOTE_STAGE'
EVID='$REMOTE_EVID'
mkdir -p "\$ORCH/ops/runbooks" "\$EVID"
cp -a "\$STAGE/shifts_synthetic_cleanup.py" "\$ORCH/"
cp -a "\$STAGE/prove-shifts-wave2c-compat.py" "\$ORCH/"
cp -a "\$STAGE/canary-prod-shifts-wave1b.py" "\$ORCH/"
cp -a "\$STAGE/canary-prod-shifts-wave2b.py" "\$ORCH/"
cp -a "\$STAGE/run-shifts-wave2b-jobs.sh" "\$ORCH/ops/run-shifts-wave2b-jobs.sh"
chmod +x "\$ORCH/ops/run-shifts-wave2b-jobs.sh"
cp -a "\$STAGE/shifts-wave2b-operator-jobs.md" "\$ORCH/ops/runbooks/shifts-wave2b-operator-jobs.md"
cp -a "\$STAGE/install-shifts-wave2-job-timers.sh" "\$ORCH/ops/install-shifts-wave2-job-timers.sh"
chmod +x "\$ORCH/ops/install-shifts-wave2-job-timers.sh"
# preflight flags
{
  echo "stamp=$STAMP"
  tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep -E 'SHIFTS_|CAPTURE_INGEST' | sort
  sha256sum "\$ORCH/shifts_synthetic_cleanup.py" "\$ORCH/canary-prod-shifts-wave1b.py" "\$ORCH/canary-prod-shifts-wave2b.py"
} | tee "\$EVID/flags/before.txt"
export STAGE_DIR="\$STAGE"
export ORCH="\$ORCH"
export REMOTE_EVID="\$EVID/timers"
bash "\$ORCH/ops/install-shifts-wave2-job-timers.sh"
# also keep unit copies under orch/ops for documentation
cp -a "\$STAGE"/wathefni-shifts-*.service "\$STAGE"/wathefni-shifts-*.timer "\$ORCH/ops/" || true
echo DEPLOY_W2C_OK
REMOTE

load_prod_env() {
  cat <<'EOF'
ORCH=/opt/wathefni/orchestrator
cd $ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "$line" in WATHEFNI_*=*) export "$line" ;; esac
done < /proc/$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
export PYTHONUNBUFFERED=1
PYBIN=$ORCH/.venv/bin/python
EOF
}

log "Wave 1B canary under Wave 2 schema"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-wave1b.out"
set -euo pipefail
$(load_prod_env)
export SHW1B_EVID='$REMOTE_EVID/canary/wave1b'
mkdir -p "\$SHW1B_EVID"
\$PYBIN -u canary-prod-shifts-wave1b.py
REMOTE
require_pass "$LOCAL_EVID/tests/canary-wave1b.out" "wave1b-canary"

log "Wave 2B canary"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-wave2b.out"
set -euo pipefail
$(load_prod_env)
export SHW2B_EVID='$REMOTE_EVID/canary/wave2b'
mkdir -p "\$SHW2B_EVID"
\$PYBIN -u canary-prod-shifts-wave2b.py
REMOTE
require_pass "$LOCAL_EVID/tests/canary-wave2b.out" "wave2b-canary"

log "Wave 2C compat prove (isolation / interrupt / timers)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/prove-wave2c.out"
set -euo pipefail
$(load_prod_env)
export SHW2C_EVID='$REMOTE_EVID/prove'
mkdir -p "\$SHW2C_EVID"
\$PYBIN -u prove-shifts-wave2c-compat.py
REMOTE
require_pass "$LOCAL_EVID/tests/prove-wave2c.out" "wave2c-prove"

log "prod freezes"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/freezes-prod.out"
set -euo pipefail
$(load_prod_env)
echo '=== E360 ==='
\$PYBIN smoke-test-employees360-freeze-regression.py
echo '=== ONBOARDING ==='
\$PYBIN smoke-test-onboarding-freeze-regression.py
echo '=== ATTENDANCE ==='
\$PYBIN smoke-test-attendance-freeze-regression.py
echo '=== LEAVE ==='
\$PYBIN smoke-test-leave-freeze-regression.py
REMOTE
python3 - <<'PY'
from pathlib import Path
import re, sys
stamp = Path("/tmp/w2c-stamp.txt").read_text().strip()
p = Path(f"/Users/azizalmulla/Desktop/claw/ops/evidence/shifts-wave2c-{stamp}/tests/freezes-prod.out")
text = p.read_text()
summaries = re.findall(r"(\d+) passed, (\d+) failed", text)
if len(summaries) < 4:
    print("expected 4 freeze summaries, got", summaries, file=sys.stderr)
    sys.exit(1)
for i, (a, b) in enumerate(summaries[-4:]):
    if int(b) != 0:
        print(f"freeze suite {i} failed: {a}/{b}", file=sys.stderr)
        sys.exit(1)
print("OK freezes-prod", summaries[-4:])
PY

log "pull remote evidence"
"${SSH[@]}" "bash -s" <<REMOTE
set -euo pipefail
EVID='$REMOTE_EVID'
{
  echo '=== timers final ==='
  for t in wathefni-shifts-reminder-drain.timer wathefni-shifts-lifecycle-recon.timer wathefni-shifts-leave-recon.timer; do
    echo "\$t enabled=\$(systemctl is-enabled \$t 2>&1 || true) active=\$(systemctl is-active \$t 2>&1 || true)"
  done
  echo '=== flags ==='
  tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ | grep -E 'SHIFTS_|CAPTURE_INGEST' | sort
} | tee "\$EVID/timers/final-state.txt"
# assert disabled
for t in wathefni-shifts-reminder-drain.timer wathefni-shifts-lifecycle-recon.timer wathefni-shifts-leave-recon.timer; do
  en=\$(systemctl is-enabled \$t 2>&1 || true)
  echo "\$en" | grep -q disabled
done
echo TIMERS_STILL_DISABLED
REMOTE
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/"

log "verify residual gates from pulled evidence"
python3 - <<'PY'
from pathlib import Path
import json
stamp = Path("/tmp/w2c-stamp.txt").read_text().strip()
evid = Path(f"/Users/azizalmulla/Desktop/claw/ops/evidence/shifts-wave2c-{stamp}")
q1 = evid / "remote/canary/wave1b/qualification.json"
q2 = evid / "remote/canary/wave2b/qualification.json"
qp = evid / "remote/prove/qualification.json"
d1 = json.loads(q1.read_text()) if q1.exists() else {}
d2 = json.loads(q2.read_text()) if q2.exists() else {}
dp = json.loads(qp.read_text()) if qp.exists() else {}
for label, d in (("wave1b", d1), ("wave2b", d2)):
    if not d:
        raise SystemExit(f"missing qualification for {label}")
    c = d.get("cleanup") or {}
    total = c.get("residual_total", c.get("total"))
    if total != 0:
        raise SystemExit(f"{label} residual not zero: {total} :: {c}")
    if d.get("failed"):
        raise SystemExit(f"{label} failed={d.get('failed')}")
if not dp or dp.get("failed"):
    raise SystemExit(f"prove failed or missing: {dp.get('failed')}")
print("QUALIFY_GATES_OK")
print("wave1b", d1.get("passed"), d1.get("failed"), "residual", (d1.get("cleanup") or {}).get("residual_total"))
print("wave2b", d2.get("passed"), d2.get("failed"), "residual", (d2.get("cleanup") or {}).get("residual_total", (d2.get("cleanup") or {}).get("total")))
print("prove", dp.get("passed"), dp.get("failed"))
PY

echo
echo "Wave 2C qualify complete. Evidence: $LOCAL_EVID"
echo "Write REPORT.md next if not already present."
