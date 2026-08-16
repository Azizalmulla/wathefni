#!/usr/bin/env bash
# Platform Assistant Wave 2 — Safe Ops Queue Reads — staging-only qualification.
# Leave + Attendance grounded reads. Mutations off. No Wave 3 / Payroll / Shifts / WhatsApp widen.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/platform-assistant-wave2-staging-$STAMP"
STG=/opt/wathefni/staging/orchestrator
REMOTE_EVID="/opt/wathefni/staging-evidence/platform-assistant-wave2/${STAMP}"
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-platform-assistant-wave2.conf

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,remote,flags}
echo "$LOCAL_EVID" > /tmp/paw2.evid
echo "$STAMP" > /tmp/paw2.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + sibling freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
export WATHEFNI_PLATFORM_ASSISTANT_WAVE1=1
export WATHEFNI_PLATFORM_ASSISTANT_WAVE2=1
export WATHEFNI_ASSISTANT_MUTATIONS=0
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
"$PY_LOCAL" smoke-test-platform-assistant-wave2.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave2-local.out" | tail -40
"$PY_LOCAL" smoke-test-platform-assistant-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave1-local.out" | tail -15
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts.out" | tail -3

log "stage sources"
cp -a platform_assistant_wave2_safe_ops_reads.py platform_assistant_spine_wave1.py \
  smoke-test-platform-assistant-wave2.py smoke-test-platform-assistant-wave1.py \
  action_registry.py assistant_capability_catalog.py tool_call_orchestrator.py \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-platform-assistant-wave2-staging.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push to staging"
"${SSH[@]}" "mkdir -p '$STG' '$REMOTE_EVID'/{tests,flags} /etc/systemd/system/wathefni-orchestrator-staging.service.d"
"${SCP[@]}" \
  "$ORCH_SRC/platform_assistant_wave2_safe_ops_reads.py" \
  "$ORCH_SRC/platform_assistant_spine_wave1.py" \
  "$ORCH_SRC/smoke-test-platform-assistant-wave2.py" \
  "$ORCH_SRC/smoke-test-platform-assistant-wave1.py" \
  "$ORCH_SRC/action_registry.py" \
  "$ORCH_SRC/assistant_capability_catalog.py" \
  "$ORCH_SRC/tool_call_orchestrator.py" \
  "$VPS_HOST:$STG/"

log "staging drop-in + restart + qualify"
set +e
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-qualify.out"
set -euo pipefail
STG='$STG'
DROPIN='$DROPIN'
REMOTE_EVID='$REMOTE_EVID'
PY=/opt/wathefni/orchestrator/.venv/bin/python

cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE1=1
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES=WATHEFNI
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE2=1
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE2_COMPANIES=WATHEFNI
Environment=WATHEFNI_ASSISTANT_KILL=0
Environment=WATHEFNI_ASSISTANT_MUTATIONS=0
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF
systemctl daemon-reload
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

tr '\0' '\n' < /proc/\$PID/environ | grep -E 'PLATFORM_ASSISTANT|ASSISTANT_KILL|ASSISTANT_MUTATIONS|CAPTURE_INGEST' | sort | tee \$REMOTE_EVID/flags/staging-flags.txt
grep -qiE 'CAPTURE_INGEST=(on|true|1|yes)' \$REMOTE_EVID/flags/staging-flags.txt && { echo 'REFUSE ingest on'; exit 3; } || echo CAPTURE_INGEST_OFF_OK
grep -q 'PLATFORM_ASSISTANT_WAVE2=1' \$REMOTE_EVID/flags/staging-flags.txt && echo WAVE2_FLAG_OK || { echo WAVE2_FLAG_MISSING; exit 3; }
grep -q 'ASSISTANT_MUTATIONS=0' \$REMOTE_EVID/flags/staging-flags.txt && echo MUTATIONS_OFF_OK || { echo MUTATIONS_FLAG_MISSING; exit 3; }

\$PY smoke-test-platform-assistant-wave2.py | tee \$REMOTE_EVID/tests/smoke-wave2.out
SMOKE_RC=\${PIPESTATUS[0]}
if [[ \$SMOKE_RC -ne 0 ]]; then echo "SMOKE_FAILED rc=\$SMOKE_RC"; exit \$SMOKE_RC; fi

\$PY smoke-test-employees360-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-e360.out | tail -5
\$PY smoke-test-onboarding-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-onboarding.out | tail -5
\$PY smoke-test-attendance-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-attendance.out | tail -5
\$PY smoke-test-leave-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-leave.out | tail -5
\$PY smoke-test-shifts-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-shifts.out | tail -5

\$PY - <<'PY'
import json, os
from types import SimpleNamespace
import platform_assistant_spine_wave1 as spine
import platform_assistant_wave2_safe_ops_reads as wave2
import action_registry as registry
import app

assert wave2.platform_assistant_wave2_enabled()
assert not spine.assistant_mutations_allowed()
assert wave2.wave2_enabled_for_company("WATHEFNI")
assert not wave2.wave2_enabled_for_company("ACME")

class Req:
    metadata = {
        "channel": "web_dashboard",
        "dashboard": True,
        "company_code": "WATHEFNI",
        "permissions": ["leave.read", "attendance.read", "leave.manage", "attendance.manage"],
        "admin_user": {"phone": "96599338566", "role": "hr_admin", "user_id": "staging-paw2"},
        "access": {"role": "hr_admin"},
        "locale": "en",
    }
    raw_text = "pending leave and late attendance"

tools = registry.build_tool_schemas(app, Req())
names = {str((t.get("function") or {}).get("name") or "") for t in tools}
assert "summarize_leave_queue" in names
assert "summarize_attendance_exceptions" in names
assert "approve_leave_request" not in names
assert "mark_attendance_absent" not in names

ctx = SimpleNamespace(
    request=Req(),
    action={"company_code": "WATHEFNI", "permissions": Req.metadata["permissions"], "status": "requested"},
    state={}, graph_state={}, intent={}, legacy=app,
)
leave = wave2.execute_summarize_leave_queue(ctx)
g = leave["grounding"]
assert g.get("data_freshness") and g.get("authority_state")
assert isinstance(g.get("citations"), list)
assert all(not a.get("executes") for a in (g.get("proposed_actions") or []))
assert leave.get("mutates_records") is False

att = wave2.execute_summarize_attendance_exceptions(ctx)
ga = att["grounding"]
assert ga.get("data_freshness")
assert (ga.get("payload") or {}).get("capture_ingest") == "off" or "ingest" in (ga.get("summary_en") or "").lower()
assert all(not a.get("executes") for a in (ga.get("proposed_actions") or []))

# AR locale
Req.metadata["locale"] = "ar"
att_ar = wave2.execute_summarize_attendance_exceptions(ctx)
assert (att_ar.get("grounding") or {}).get("summary_ar")

# Tenant + permission
bad = wave2.execute_summarize_leave_queue(SimpleNamespace(
    request=Req(), action={"company_code": "ACME", "permissions": Req.metadata["permissions"]},
    state={}, graph_state={}, intent={}, legacy=app,
))
assert (bad.get("grounding") or {}).get("fallback_key") == "tenant_denied"

with app.db_connect() as conn:
    with conn.cursor() as cur:
        spine.ensure_assistant_spine_audit_schema(cur)
        ev = spine.record_assistant_event(
            cur, company_code="WATHEFNI", event_type="assistant.wave2_staging_qualify",
            channel="web_dashboard", detail={"stamp": "staging"},
        )
        conn.commit()
assert ev.get("event_id")

print("STAGING_WAVE2_EVAL_OK", json.dumps({
    "leave_authority": g.get("authority_state"),
    "leave_total": (g.get("payload") or {}).get("total"),
    "attendance_authority": ga.get("authority_state"),
    "attendance_total": (ga.get("payload") or {}).get("total"),
    "mutations_allowed": spine.assistant_mutations_allowed(),
}, ensure_ascii=False))
PY

echo STAGING_PLATFORM_ASSISTANT_WAVE2_OK
REMOTE
STG_RC=${PIPESTATUS[0]}
set -e
if [[ $STG_RC -ne 0 ]]; then echo "STAGING_QUALIFY_FAILED rc=$STG_RC" >&2; exit "$STG_RC"; fi

log "pull remote"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true

log "write REPORT + GATE + freeze draft"
LOCAL_EVID_FOR_REPORT="$LOCAL_EVID" STAMP_FOR_REPORT="$STAMP" python3 - <<'PY'
import os, pathlib, re
evid = pathlib.Path(os.environ["LOCAL_EVID_FOR_REPORT"])
stamp = os.environ["STAMP_FOR_REPORT"]

def ok_file(path):
    if not path.exists():
        return False, "missing"
    txt = path.read_text()
    m = re.search(r"(\d+) passed, (\d+) failed", txt)
    if m:
        return int(m.group(2)) == 0, f"{m.group(1)}/{m.group(2)}"
    return False, "marker"

stg = (evid / "tests" / "staging-qualify.out").read_text() if (evid / "tests" / "staging-qualify.out").exists() else ""
local_ok, local_s = ok_file(evid / "tests" / "smoke-wave2-local.out")
f360 = ok_file(evid / "tests" / "freeze-e360.out")
fonb = ok_file(evid / "tests" / "freeze-onboarding.out")
fatt = ok_file(evid / "tests" / "freeze-attendance.out")
flv = ok_file(evid / "tests" / "freeze-leave.out")
fsh = ok_file(evid / "tests" / "freeze-shifts.out")

blockers = []
if not local_ok:
    blockers.append(f"local smoke failed ({local_s})")
if "STAGING_PLATFORM_ASSISTANT_WAVE2_OK" not in stg:
    blockers.append("staging qualify marker missing")
if "STAGING_WAVE2_EVAL_OK" not in stg:
    blockers.append("staging wave2 eval failed")
if "CAPTURE_INGEST_OFF_OK" not in stg:
    blockers.append("capture ingest not confirmed off")
if "MUTATIONS_OFF_OK" not in stg:
    blockers.append("mutations kill not confirmed")
if "WAVE2_FLAG_OK" not in stg:
    blockers.append("wave2 flag missing")
if not all(x[0] for x in (f360, fonb, fatt, flv, fsh)):
    blockers.append("sibling freeze regression failed")

verdict = "GO" if not blockers else "NO-GO"
report = f"""# Platform Assistant Wave 2 — Safe Ops Queue Reads (staging)

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/platform-assistant-wave2-staging-{stamp}/`  
**Scope:** WATHEFNI · HR dashboard · Leave + Attendance queues · mutations off · ingest off  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Staging Platform Assistant Wave 2 Safe Ops Reads | **{verdict}** |
| Production synthetic qualification | **NO-GO** (not started) |
| Assistant Wave 3 | **NO-GO / not started** |
| Payroll / Shifts / Onboarding / new Analytics-Compliance / WhatsApp widen | **NO-GO** |

---

## Proofs

- Grounded Leave queue + Attendance exceptions summarize
- Citations, freshness, authority; ingest-off honesty on Attendance
- Groups + prepare-only deep links; EN/AR
- Tenant / permission / disabled-module isolation; mutations off
- Sibling freezes: E360 {f360[1]}, Onboarding {fonb[1]}, Attendance {fatt[1]}, Leave {flv[1]}, Shifts {fsh[1]}

Local smoke: `{local_s}`

---

## Blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for staging Wave 2 scope.'}
"""
(evid / "REPORT.md").write_text(report)
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "REPORT.md").write_text(report)
gate = "STAGING_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO" if verdict == "GO" else "STAGING_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_NO_GO"
(evid / "docs" / "GATE.txt").write_text("\n".join([
    f"stamp={stamp}",
    f"evidence={evid}",
    "company=WATHEFNI",
    "channel=hr_dashboard",
    "mutations=off",
    "capture_ingest=off",
    "wave3_started=false",
    f"GATE={gate}",
    f"STAGING_WAVE2={verdict}",
    "PROD_SYNTHETIC=NO-GO",
    "",
]))
freeze = f"""# Platform Assistant Wave 2 — Safe Ops Queue Reads Freeze (staging)

**Gate:** `{gate}`  
**Evidence:** `ops/evidence/platform-assistant-wave2-staging-{stamp}/`  
**Production synthetic:** **NO-GO** until Wave 2-B  
**Assistant Wave 3:** **NO-GO / not started**

## Scope frozen

- Grounded read-only Leave request queue + Attendance exception queue
- WATHEFNI · HR dashboard · mutations off · Wave 1 spine reused
- Attendance labeled ingest-off / existing-record based
- Leave and Attendance remain systems of action (deep links only)

## Explicit NO-GO

- Production synthetic without Wave 2-B
- Wave 3 / Payroll / Shifts / Onboarding assistant surfaces / WhatsApp widen
- Money · ingest · mutations
"""
(evid / "docs" / "PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md").write_text(freeze)
print(report)
print("SYNTH_VERDICT", verdict)
PY

cp -a "$LOCAL_EVID/docs/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md" \
  "$REPO_ROOT/ops/PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_FREEZE.md"

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
