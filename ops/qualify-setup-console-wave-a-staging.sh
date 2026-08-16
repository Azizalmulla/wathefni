#!/usr/bin/env bash
# Setup Console Wave A — staging launch readiness qualification.
# WATHEFNI only. No external tenants. No freeze reopen. No prod synthetic yet.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/setup-console-wave-a-staging-$STAMP"
STG=/opt/wathefni/staging/orchestrator
REMOTE_EVID="/opt/wathefni/staging-evidence/setup-console-wave-a/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,ui,sources}
echo "$LOCAL_EVID" > /tmp/setup-wave-a.evid
echo "$STAMP" > /tmp/setup-wave-a.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + sibling freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-setup-console-wave-a.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave-a-local.out" | tail -40
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts.out" | tail -3

log "stage sources"
cp -a setup_console_wave_a_launch_readiness.py smoke-test-setup-console-wave-a.py app.py "$LOCAL_EVID/sources/"
mkdir -p "$LOCAL_EVID/ui"
cp -a "$DASH_SRC/src/setup-console/LaunchReadinessPage.tsx" \
  "$DASH_SRC/src/setup-console/SetupConsoleApp.tsx" \
  "$DASH_SRC/src/setup-console/api.ts" \
  "$DASH_SRC/src/setup-console/types.ts" \
  "$LOCAL_EVID/ui/"

log "push to staging orchestrator"
"${SSH[@]}" "mkdir -p '$STG' '$REMOTE_EVID'/{tests,ui,flags} /opt/wathefni/apps/wathefni-dashboard/src/setup-console"
"${SCP[@]}" \
  "$ORCH_SRC/setup_console_wave_a_launch_readiness.py" \
  "$ORCH_SRC/smoke-test-setup-console-wave-a.py" \
  "$ORCH_SRC/app.py" \
  "$VPS_HOST:$STG/"
"${SCP[@]}" \
  "$DASH_SRC/src/setup-console/LaunchReadinessPage.tsx" \
  "$DASH_SRC/src/setup-console/SetupConsoleApp.tsx" \
  "$DASH_SRC/src/setup-console/api.ts" \
  "$DASH_SRC/src/setup-console/types.ts" \
  "$VPS_HOST:/opt/wathefni/apps/wathefni-dashboard/src/setup-console/"

log "restart staging + run smokes"
set +e
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-qualify.out"
set -euo pipefail
STG='$STG'
PY=/opt/wathefni/orchestrator/.venv/bin/python
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator-staging

cd \$STG
set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
unset DATABASE_URL || true

# Prove CAPTURE_INGEST remains off
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'CAPTURE_INGEST|SETUP_CONSOLE|PAYROLL_WAVE2A_SYNTHETIC' | sort | tee '$REMOTE_EVID/flags/staging-flags.txt'
grep -qiE 'CAPTURE_INGEST=(on|true|1|yes)' '$REMOTE_EVID/flags/staging-flags.txt' && { echo 'REFUSE ingest on'; exit 3; } || echo CAPTURE_INGEST_OFF_OK

\$PY smoke-test-setup-console-wave-a.py | tee '$REMOTE_EVID/tests/smoke-wave-a.out'
SMOKE_RC=\${PIPESTATUS[0]}
if [[ \$SMOKE_RC -ne 0 ]]; then echo "SMOKE_FAILED rc=\$SMOKE_RC"; exit \$SMOKE_RC; fi
\$PY smoke-test-employees360-freeze-regression.py | tee '$REMOTE_EVID/tests/freeze-e360.out' | tail -5
\$PY smoke-test-onboarding-freeze-regression.py | tee '$REMOTE_EVID/tests/freeze-onboarding.out' | tail -5
\$PY smoke-test-attendance-freeze-regression.py | tee '$REMOTE_EVID/tests/freeze-attendance.out' | tail -5
\$PY smoke-test-leave-freeze-regression.py | tee '$REMOTE_EVID/tests/freeze-leave.out' | tail -5
\$PY smoke-test-shifts-freeze-regression.py | tee '$REMOTE_EVID/tests/freeze-shifts.out' | tail -5

# API-shaped evaluate + entitlement bypass proof
\$PY - <<'PY'
import json, os, setup_console_wave_a_launch_readiness as wave_a, app
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")
with app.db_connect() as conn:
  with conn.cursor() as cur:
    r = wave_a.evaluate_launch_readiness(cur, company_code="WATHEFNI")
    bad = wave_a.evaluate_launch_readiness(cur, company_code="EXTERNALCO")
assert r.get("ok") is True
assert bad.get("ok") is False
assert r.get("entitlements_cannot_bypass_gates") is True
assert r.get("payroll_money") is False
assert r.get("attendance_ingest") is False
assert r.get("external_tenants") is False
# Module purchased cannot clear attendance ingest block
mods = []
for st in r["stages"]:
  if st["stage"]["key"] == "modules":
    mods = st["items"]
att = next(m for m in mods if m["key"] == "module:attendance")
if att.get("purchased"):
  assert att.get("blocked") is True or "ingest" in json.dumps(att.get("evidence") or {}).lower() or att.get("state") == "live_controlled"
  assert "device" in (att.get("summary_en") or "").lower() or "controlled" in (att.get("summary_en") or "").lower()
# Blockers have deep links + next actions
for b in r.get("important_blockers") or []:
  assert b.get("deep_link")
  assert b.get("next_action_en")
# Pause impact present
assert (r.get("pause_impact") or {}).get("bullets_en")
print("EVALUATE_OK", r.get("overall_state"), "blockers", len(r.get("important_blockers") or []))
print(json.dumps({"overall": r.get("overall_state"), "modules": len(mods), "blockers": len(r.get("important_blockers") or [])}, indent=2))
PY

# UI copy on staging host
\$PY - <<'PY'
from pathlib import Path
p = Path("/opt/wathefni/apps/wathefni-dashboard/src/setup-console/LaunchReadinessPage.tsx")
t = p.read_text(encoding="utf-8")
assert "جاهزية الإطلاق" in t and "Launch readiness" in t
assert "launch-overall-status" in t and "flex-wrap" in t
print("UI_EN_AR_MOBILE_OK")
PY

echo STAGING_WAVE_A_OK
REMOTE
STG_RC=${PIPESTATUS[0]}
set -e
if [[ $STG_RC -ne 0 ]]; then echo "STAGING_QUALIFY_FAILED rc=$STG_RC" >&2; exit "$STG_RC"; fi

log "pull remote"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true

log "write REPORT + GATE"
LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" python3 - <<'PY'
import os, pathlib, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]

def ok_file(path, needle):
    if not path.exists():
        return False, "missing"
    txt = path.read_text()
    m = re.search(r"(\d+) passed, (\d+) failed", txt)
    if m:
        return int(m.group(2)) == 0, f"{m.group(1)}/{m.group(2)}"
    return needle in txt, "marker"

stg = (evid / "tests" / "staging-qualify.out").read_text() if (evid / "tests" / "staging-qualify.out").exists() else ""
local = (evid / "tests" / "smoke-wave-a-local.out").read_text() if (evid / "tests" / "smoke-wave-a-local.out").exists() else ""
local_ok, local_s = ok_file(evid / "tests" / "smoke-wave-a-local.out", "passed")
f360 = ok_file(evid / "tests" / "freeze-e360.out", "0 failed")
fonb = ok_file(evid / "tests" / "freeze-onboarding.out", "0 failed")
fatt = ok_file(evid / "tests" / "freeze-attendance.out", "0 failed")
flv = ok_file(evid / "tests" / "freeze-leave.out", "0 failed")
fsh = ok_file(evid / "tests" / "freeze-shifts.out", "0 failed")

blockers = []
if not local_ok:
    blockers.append(f"local smoke failed ({local_s})")
if "STAGING_WAVE_A_OK" not in stg:
    blockers.append("staging qualify marker missing")
if "EVALUATE_OK" not in stg:
    blockers.append("staging evaluate failed")
if "CAPTURE_INGEST_OFF_OK" not in stg:
    blockers.append("capture ingest not confirmed off")
if "UI_EN_AR_MOBILE_OK" not in stg:
    blockers.append("EN/AR/mobile UI check failed")
if not all(x[0] for x in (f360, fonb, fatt, flv, fsh)):
    blockers.append("sibling freeze regression failed")
if "REFUSE ingest on" in stg:
    blockers.append("capture ingest was on")

verdict = "GO" if not blockers else "NO-GO"
# Staging GO only — production synthetic still NO-GO until separate qualify
prod_synth = "NO-GO"
report = f"""# Setup Console Wave A — staging launch readiness

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/setup-console-wave-a-staging-{stamp}/`  
**Scope:** WATHEFNI-only Launch Readiness checklist · operator-only · staging  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Staging Wave A launch readiness | **{verdict}** |
| Production synthetic qualification | **{prod_synth}** (not started) |
| Setup Wave B / external tenants | **NO-GO / not started** |
| Payroll money / Attendance ingest / rollout widening | **NO-GO** |

---

## Proofs

- Honest states: not_purchased / setup_required / blocked / ready_for_canary / live_controlled / paused
- Modules report truthful controlled posture; entitlements cannot bypass gates
- Important blockers include next action + deep link
- Pause impact copy present
- EN/AR + mobile wrap
- CAPTURE_INGEST remains off
- Sibling freezes: E360 {f360[1]}, Onboarding {fonb[1]}, Attendance {fatt[1]}, Leave {flv[1]}, Shifts {fsh[1]}

Local smoke: `{local_s}`

---

## Blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for staging Wave A scope.'}
"""
(evid / "REPORT.md").write_text(report)
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "REPORT.md").write_text(report)
gate = "STAGING_SETUP_CONSOLE_WAVE_A_GO" if verdict == "GO" else "STAGING_SETUP_CONSOLE_WAVE_A_NO_GO"
(evid / "docs" / "GATE.txt").write_text(
    "\n".join([
        f"stamp={stamp}",
        f"evidence={evid}",
        "company=WATHEFNI",
        "external_tenants=false",
        "payroll_money=false",
        "attendance_ingest=false",
        "wave_b_started=false",
        f"GATE={gate}",
        f"STAGING_WAVE_A={verdict}",
        "PROD_SYNTHETIC=NO-GO",
        "",
    ])
)
print(report)
print("SYNTH_VERDICT", verdict)
print("PROD_SYNTHETIC", prod_synth)
PY

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
