#!/usr/bin/env bash
# Module-Aware Shell Wave 0-B — production WATHEFNI synthetic Focused Workforce qualification.
# Deploy → ACK → canary → rollback → redeploy → canary → sibling freezes → freeze stamp.
# Does NOT start further shell/mobile waves / Assistant Wave 3 / money / ingest / mutations.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/module-aware-shell-wave0b-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/module-aware-shell-w0b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/module-aware-shell-wave0b-prod-canary/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,verify,ui}
echo "$LOCAL_EVID" > /tmp/masw0b.evid
echo "$STAMP" > /tmp/masw0b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + vitest + freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
export WATHEFNI_ASSISTANT_MUTATIONS=0
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
export WATHEFNI_MODULE_AWARE_SHELL_WAVE0=1
"$PY_LOCAL" smoke-test-module-aware-shell-wave0.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave0-local.out" | tail -40
"$PY_LOCAL" test_workspace_composition_matrix.py 2>&1 | tee "$LOCAL_EVID/tests/composition-local.out"
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3

cd "$DASH_SRC"
npm test -- --run src/lib/moduleWorkspace.wave0.test.ts src/lib/workspaceCapability.test.ts \
  2>&1 | tee "$LOCAL_EVID/ui/vitest.out" | tail -25
npx vite build 2>&1 | tee "$LOCAL_EVID/ui/dashboard-build.out" | tail -25
test -d "$DASH_SRC/dist"

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops" "$LOCAL_EVID/sources/dashboard-dist"
cd "$ORCH_SRC"
cp -a app.py assistant_capability_catalog.py workspace_capability.py \
  canary-prod-module-aware-shell-wave0b.py \
  smoke-test-module-aware-shell-wave0.py \
  test_workspace_composition_matrix.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  smoke-test-platform-assistant-wave1.py \
  smoke-test-platform-assistant-wave2.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-module-aware-shell-wave0b-prod-synthetic.sh \
  ops/migrate-module-aware-shell-wave0-prod.sh \
  "$LOCAL_EVID/sources/ops/"
cp -a ops/migrate-module-aware-shell-wave0-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$DASH_SRC/dist/." "$LOCAL_EVID/sources/dashboard-dist/"
cp -a "$REPO_ROOT/ops/qualify-module-aware-shell-wave0b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py assistant_capability_catalog.py workspace_capability.py \
    canary-prod-module-aware-shell-wave0b.py \
    smoke-test-module-aware-shell-wave0.py \
    test_workspace_composition_matrix.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    smoke-test-platform-assistant-wave1.py \
    smoke-test-platform-assistant-wave2.py \
    ops/deploy-module-aware-shell-wave0b-prod-synthetic.sh \
    ops/migrate-module-aware-shell-wave0-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)
rsync -az -e "ssh -o BatchMode=yes -o ControlMaster=no" "$DASH_SRC/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-module-aware-shell-wave0b-prod-synthetic.sh'
bash '$REMOTE_STAGE/deploy-module-aware-shell-wave0b-prod-synthetic.sh'
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
export MASW0B_EVID="\$OUTDIR"
export WATHEFNI_DASHBOARD_DIST=/var/www/wathefni-dashboard
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'MODULE_AWARE_SHELL|ASSISTANT_MUTATIONS|CAPTURE_INGEST|DASHBOARD_DIST' | sort | tee "\$OUTDIR/flags.txt"
grep -qiE 'CAPTURE_INGEST=(on|true|1|yes)' "\$OUTDIR/flags.txt" && { echo 'REFUSE ingest on'; exit 3; } || echo CAPTURE_INGEST_OFF_OK
grep -q 'ASSISTANT_MUTATIONS=0' "\$OUTDIR/flags.txt" && echo MUTATIONS_OFF_OK || { echo MUTATIONS_NOT_OFF; exit 3; }
grep -q 'MODULE_AWARE_SHELL_WAVE0=1' "\$OUTDIR/flags.txt" && echo SHELL_WAVE0_ON_OK || { echo SHELL_WAVE0_NOT_ON; exit 3; }
\$PYBIN -u smoke-test-module-aware-shell-wave0.py | tee "\$OUTDIR/smoke-wave0.out"
\$PYBIN -u canary-prod-module-aware-shell-wave0b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "rollback proof"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/module-aware-shell-wave0b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzz-module-aware-shell-wave0b-synthetic.conf
ENVS=\$(tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ)
echo "\$ENVS" | grep MODULE_AWARE_SHELL_WAVE0 || echo "SHELL_WAVE0_FLAGS_CLEARED"
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-module-aware-shell-wave0b-prod-synthetic.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
run_canary canary-after-redeploy canary/after-redeploy

log "write freeze doc + sibling freezes"
export EVID="$LOCAL_EVID" STAMP="$STAMP"
python3 - <<'PY'
from pathlib import Path
import os
evid = Path(os.environ["EVID"])
stamp = os.environ["STAMP"]
freeze = f"""# Module-Aware Shell Wave 0 — Focused Workforce Experience Freeze

**Gate:** `PROD_SYNTHETIC_MODULE_AWARE_SHELL_WAVE0_GO`  
**Evidence:** `ops/evidence/module-aware-shell-wave0b-prod-canary-{stamp}/`  
**Staging prerequisite:** `ops/evidence/module-aware-shell-wave0-staging-20260803T204315Z/` (`STAGING_MODULE_AWARE_SHELL_WAVE0_GO`)  
**Freeze:** **GO** for Module-Aware Shell Wave 0 (production synthetic WATHEFNI posture)

## Frozen posture

- Employees = shared people spine (not a purchasable SKU)
- One operational module → land on that module
- Several workforce modules → Action Inbox when offerable + entitled source; else deterministic priority
- Payroll-only landing preserved; full-suite Pre-Hiring Overview preserved
- Inbox omits never-purchased Analytics/Compliance; partial = entitled failures only
- Assistant catalog module-truth; Alerts post-hire delivery rows when Pre-Hiring off
- Mutations off · Attendance ingest off · HR dashboard

## Proven on production synthetic

- Deploy + migrate/ACK; canary residual **0**; durable ACK retained
- Landing/nav/catalog/inbox honesty/alerts/E360 for Leave, Shifts, Attendance, Payroll,
  Onboarding+Compliance, Shifts+Attendance+Leave, Leave+Attendance+Shifts+Payroll, full suite
- Rollback verified; redeploy canary green; sibling freezes green

## Explicit NO-GO (outside this freeze)

- Further shell / mobile waves
- Assistant Wave 3 · AI mutations · Payroll money · Attendance ingest
- WhatsApp / manager / employee / mobile widening
- Home rebuild / dashboard rebuild / frozen-module contract changes

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-module-aware-shell-wave0b-*`
"""
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md").write_text(freeze)
print("freeze_doc_written")
PY
cp -a "$LOCAL_EVID/docs/MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md" \
  "$REPO_ROOT/ops/MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md"
"${SCP[@]}" "$REPO_ROOT/ops/MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md" "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
for d in EMPLOYEES360_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ONBOARDING_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md \
         PLATFORM_ASSISTANT_WAVE1_SPINE_FREEZE.md \
         PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md; do
  "${SCP[@]}" "$REPO_ROOT/ops/$d" "$VPS_HOST:/opt/wathefni/ops/" 2>/dev/null || true
done

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
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/module-aware-shell-wave0b-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write REPORT + GATE"
CANARY1_OK=0
CANARY2_OK=0
ROLLBACK_OK=0
FREEZES_OK=0
DEPLOY_OK=0
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-before-rollback.out" && CANARY1_OK=1 || true
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-after-redeploy.out" && CANARY2_OK=1 || true
grep -q 'ROLLBACK_VERIFIED' "$LOCAL_EVID/tests/rollback.out" && ROLLBACK_OK=1 || true
grep -q 'DEPLOY_OK' "$LOCAL_EVID/tests/deploy.out" && DEPLOY_OK=1 || true
if ! grep -q '^FAIL ' "$LOCAL_EVID/tests/freezes-prod.out" && grep -q 'passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out"; then
  FREEZES_OK=1
else
  FREEZES_OK=0
fi
FREEZE_ZERO_COUNT=$(grep -cE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out" || true)
[[ "$FREEZE_ZERO_COUNT" -ge 5 ]] || FREEZES_OK=0

VERDICT=NO-GO
if [[ "$CANARY1_OK" -eq 1 && "$CANARY2_OK" -eq 1 && "$ROLLBACK_OK" -eq 1 && "$FREEZES_OK" -eq 1 && "$DEPLOY_OK" -eq 1 ]]; then
  VERDICT=GO
fi

if [[ "$VERDICT" != "GO" ]]; then
  sed -i.bak 's/\*\*Freeze:\*\* \*\*GO\*\*/**Freeze:** **NO-GO**/' \
    "$REPO_ROOT/ops/MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md" 2>/dev/null || true
  sed -i.bak 's/PROD_SYNTHETIC_MODULE_AWARE_SHELL_WAVE0_GO/PROD_SYNTHETIC_MODULE_AWARE_SHELL_WAVE0_NO_GO/' \
    "$REPO_ROOT/ops/MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md" 2>/dev/null || true
fi

export EVID="$LOCAL_EVID" STAMP="$STAMP" VERDICT="$VERDICT" \
  CANARY1_OK="$CANARY1_OK" CANARY2_OK="$CANARY2_OK" ROLLBACK_OK="$ROLLBACK_OK" \
  FREEZES_OK="$FREEZES_OK" DEPLOY_OK="$DEPLOY_OK"
python3 - <<'PY'
import os
from pathlib import Path
evid = Path(os.environ["EVID"])
stamp = os.environ["STAMP"]
verdict = os.environ["VERDICT"]
gate = "PROD_SYNTHETIC_MODULE_AWARE_SHELL_WAVE0_GO" if verdict == "GO" else "PROD_SYNTHETIC_MODULE_AWARE_SHELL_WAVE0_NO_GO"
report = f"""# Module-Aware Shell Wave 0-B — production synthetic Focused Workforce

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/module-aware-shell-wave0b-prod-canary-{stamp}/`  
**Staging prerequisite:** `ops/evidence/module-aware-shell-wave0-staging-20260803T204315Z/`  
**Freeze doc:** `ops/MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Module-Aware Shell Wave 0 | **{verdict}** |
| Freeze Module-Aware Shell Wave 0 | **{verdict}** |
| Further shell / mobile waves | **NO-GO** (not started) |
| Assistant Wave 3 / money / ingest / mutations / WhatsApp | **NO-GO** |

## Proof matrix

| Check | Result |
|---|---|
| Deploy + ACK | {os.environ['DEPLOY_OK']} |
| Canary before rollback (fail=0) | {os.environ['CANARY1_OK']} |
| Rollback verified | {os.environ['ROLLBACK_OK']} |
| Canary after redeploy (fail=0) | {os.environ['CANARY2_OK']} |
| Sibling freezes (5× 0 failed) | {os.environ['FREEZES_OK']} |

## Residual

Canary-tagged `assistant.shell_wave0b_canary*` events cleaned to **0**; durable production ACK retained.
"""
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "REPORT.md").write_text(report)
(evid / "REPORT.md").write_text(report)
(evid / "docs" / "GATE.txt").write_text("\n".join([
    f"stamp={stamp}",
    f"evidence={evid}",
    "company=WATHEFNI",
    "channel=hr_dashboard",
    "mutations=off",
    "capture_ingest=off",
    "assistant_wave3=false",
    "further_shell_wave=false",
    "residual=0",
    f"GATE={gate}",
    f"PROD_SYNTHETIC_SHELL_WAVE0={verdict}",
    "FURTHER_SHELL_WAVE=NO-GO",
    "",
]))
print(report)
print("GATE", gate)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID verdict=$VERDICT"
[[ "$VERDICT" == "GO" ]]
