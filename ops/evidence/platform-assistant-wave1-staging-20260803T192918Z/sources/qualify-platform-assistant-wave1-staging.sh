#!/usr/bin/env bash
# Platform Assistant Wave 1 — Spine Contract — staging-only qualification.
# WATHEFNI · HR dashboard-first · no WhatsApp widening · no mutations · no Wave 2.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/platform-assistant-wave1-staging-$STAMP"
STG=/opt/wathefni/staging/orchestrator
REMOTE_EVID="/opt/wathefni/staging-evidence/platform-assistant-wave1/${STAMP}"
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-platform-assistant-wave1.conf

mkdir -p "$LOCAL_EVID"/{tests,docs,ui,sources,remote,flags}
echo "$LOCAL_EVID" > /tmp/paw1.evid
echo "$STAMP" > /tmp/paw1.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + sibling freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-platform-assistant-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/smoke-wave1-local.out" | tail -40
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts.out" | tail -3

log "stage sources"
cp -a platform_assistant_spine_wave1.py smoke-test-platform-assistant-wave1.py \
  action_registry.py assistant_capability_catalog.py tool_call_orchestrator.py app.py \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-platform-assistant-wave1-staging.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push to staging orchestrator"
"${SSH[@]}" "mkdir -p '$STG' '$REMOTE_EVID'/{tests,flags,schema} /etc/systemd/system/wathefni-orchestrator-staging.service.d"
"${SCP[@]}" \
  "$ORCH_SRC/platform_assistant_spine_wave1.py" \
  "$ORCH_SRC/smoke-test-platform-assistant-wave1.py" \
  "$ORCH_SRC/action_registry.py" \
  "$ORCH_SRC/assistant_capability_catalog.py" \
  "$ORCH_SRC/tool_call_orchestrator.py" \
  "$ORCH_SRC/app.py" \
  "$VPS_HOST:$STG/"

log "staging drop-in + restart + qualify"
set +e
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-qualify.out"
set -euo pipefail
STG='$STG'
DROPIN='$DROPIN'
REMOTE_EVID='$REMOTE_EVID'
PY=/opt/wathefni/orchestrator/.venv/bin/python

# Refuse if production capture ingest somehow referenced — staging must stay off too
cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE1=1
Environment=WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES=WATHEFNI
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
grep -q 'PLATFORM_ASSISTANT_WAVE1=1' \$REMOTE_EVID/flags/staging-flags.txt && echo WAVE1_FLAG_OK || { echo WAVE1_FLAG_MISSING; exit 3; }
grep -q 'ASSISTANT_MUTATIONS=0' \$REMOTE_EVID/flags/staging-flags.txt && echo MUTATIONS_OFF_OK || { echo MUTATIONS_FLAG_MISSING; exit 3; }

\$PY smoke-test-platform-assistant-wave1.py | tee \$REMOTE_EVID/tests/smoke-wave1.out
SMOKE_RC=\${PIPESTATUS[0]}
if [[ \$SMOKE_RC -ne 0 ]]; then echo "SMOKE_FAILED rc=\$SMOKE_RC"; exit \$SMOKE_RC; fi

\$PY smoke-test-employees360-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-e360.out | tail -5
\$PY smoke-test-onboarding-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-onboarding.out | tail -5
\$PY smoke-test-attendance-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-attendance.out | tail -5
\$PY smoke-test-leave-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-leave.out | tail -5
\$PY smoke-test-shifts-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-shifts.out | tail -5

\$PY - <<'PY'
import os, json
import platform_assistant_spine_wave1 as spine
import action_registry as registry
import app
from types import SimpleNamespace

assert spine.platform_assistant_wave1_enabled()
assert not spine.assistant_mutations_allowed()
assert not spine.assistant_kill_engaged()
assert spine.wave1_enabled_for_company("WATHEFNI")
assert not spine.wave1_enabled_for_company("ACME")

class Req:
    metadata = {
        "channel": "web_dashboard",
        "dashboard": True,
        "company_code": "WATHEFNI",
        "permissions": ["analytics.read", "employees.read", "employee.read", "settings.read", "leave.manage"],
        "admin_user": {"phone": "96599338566", "role": "hr_admin", "user_id": "staging-paw1"},
        "access": {"role": "hr_admin"},
        "locale": "en",
    }
    raw_text = "What needs attention?"

# Schema + audit
with app.db_connect() as conn:
    with conn.cursor() as cur:
        spine.ensure_assistant_spine_audit_schema(cur)
        ev = spine.record_assistant_event(
            cur,
            company_code="WATHEFNI",
            event_type="assistant.wave1_staging_qualify",
            channel="web_dashboard",
            detail={"stamp": os.environ.get("STAMP") or "staging"},
        )
        conn.commit()
        cur.execute("SELECT count(*) AS c FROM assistant_spine_events WHERE event_id=%s::uuid", (ev["event_id"],))
        assert int(dict(cur.fetchone())["c"]) == 1

# Tools filtered
tools = registry.build_tool_schemas(app, Req())
names = {str((t.get("function") or {}).get("name") or "") for t in tools}
assert "summarize_action_inbox" in names
assert "approve_leave_request" not in names
assert "export_payroll" not in names

# Inbox + setup readiness executors
ctx = SimpleNamespace(
    request=Req(),
    action={"company_code": "WATHEFNI", "permissions": Req.metadata["permissions"]},
    state={},
    graph_state={},
    intent={},
    legacy=app,
)
inbox = spine.execute_summarize_action_inbox(ctx)
assert isinstance(inbox.get("grounding"), dict)
g = inbox["grounding"]
assert g.get("data_freshness")
assert g.get("authority_state")
assert g.get("mutates_records") is False or inbox.get("mutates_records") is False
assert g.get("citations") is not None

ready = spine.execute_get_launch_readiness_summary(ctx)
assert ready.get("grounding", {}).get("citations")
assert ready.get("grounding", {}).get("payload", {}).get("payroll_money") is False
assert ready.get("grounding", {}).get("payload", {}).get("attendance_ingest") is False

# Master kill proof (process-local env; does not flip systemd)
os.environ["WATHEFNI_ASSISTANT_KILL"] = "1"
assert spine.assistant_kill_engaged()
kill = spine.master_kill_turn_result(locale="en")
assert kill.get("intent") == "assistant_killed"
os.environ["WATHEFNI_ASSISTANT_KILL"] = "0"

# Mutation kill proof
denial = spine.mutation_kill_denial(tool_name="approve_leave_request", locale="ar")
assert denial.get("status") == "mutations_disabled"
assert "تعديل" in (denial.get("message") or "") or "معط" in (denial.get("message") or "")

# Disabled-module style: spine tools require wave1 company
ctx_acme = SimpleNamespace(
    request=Req(),
    action={"company_code": "ACME", "permissions": Req.metadata["permissions"]},
    state={}, graph_state={}, intent={}, legacy=app,
)
bad = spine.execute_summarize_action_inbox(ctx_acme)
assert (bad.get("grounding") or {}).get("fallback_key") == "tenant_denied"

print("STAGING_SPINE_EVAL_OK", json.dumps({
    "inbox_authority": g.get("authority_state"),
    "inbox_confidence": g.get("confidence"),
    "ready_overall": (ready.get("grounding") or {}).get("payload", {}).get("overall_state"),
    "mutations_allowed": spine.assistant_mutations_allowed(),
}, ensure_ascii=False))
PY

echo STAGING_PLATFORM_ASSISTANT_WAVE1_OK
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

def ok_file(path, needle="passed"):
    if not path.exists():
        return False, "missing"
    txt = path.read_text()
    m = re.search(r"(\d+) passed, (\d+) failed", txt)
    if m:
        return int(m.group(2)) == 0, f"{m.group(1)}/{m.group(2)}"
    return needle in txt, "marker"

stg = (evid / "tests" / "staging-qualify.out").read_text() if (evid / "tests" / "staging-qualify.out").exists() else ""
local_ok, local_s = ok_file(evid / "tests" / "smoke-wave1-local.out")
f360 = ok_file(evid / "tests" / "freeze-e360.out", "0 failed")
fonb = ok_file(evid / "tests" / "freeze-onboarding.out", "0 failed")
fatt = ok_file(evid / "tests" / "freeze-attendance.out", "0 failed")
flv = ok_file(evid / "tests" / "freeze-leave.out", "0 failed")
fsh = ok_file(evid / "tests" / "freeze-shifts.out", "0 failed")

blockers = []
if not local_ok:
    blockers.append(f"local smoke failed ({local_s})")
if "STAGING_PLATFORM_ASSISTANT_WAVE1_OK" not in stg:
    blockers.append("staging qualify marker missing")
if "STAGING_SPINE_EVAL_OK" not in stg:
    blockers.append("staging spine eval failed")
if "CAPTURE_INGEST_OFF_OK" not in stg:
    blockers.append("capture ingest not confirmed off")
if "MUTATIONS_OFF_OK" not in stg:
    blockers.append("mutations kill not confirmed")
if "WAVE1_FLAG_OK" not in stg:
    blockers.append("wave1 flag missing")
if not all(x[0] for x in (f360, fonb, fatt, flv, fsh)):
    blockers.append("sibling freeze regression failed")

verdict = "GO" if not blockers else "NO-GO"
prod_synth = "NO-GO"
report = f"""# Platform Assistant Wave 1 — Spine Contract (staging)

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/platform-assistant-wave1-staging-{stamp}/`  
**Scope:** WATHEFNI · HR dashboard-first · read/prepare only · mutations killed  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Staging Platform Assistant Wave 1 Spine | **{verdict}** |
| Production synthetic qualification | **{prod_synth}** (not started) |
| Assistant Wave 2 | **NO-GO / not started** |
| WhatsApp widening / mobile / manager-employee assistants | **NO-GO** |
| Payroll money / Attendance ingest / CK wiring | **NO-GO** |

---

## Proofs

- Master kill + mutation kill (`ASSISTANT_MUTATIONS=0`)
- Module registration contract (Action Inbox · Employees 360 · Setup readiness)
- Grounded envelope: source citations, freshness, authority labels
- Stale / partial / unavailable / blocked EN/AR fallbacks
- Tenant isolation (non-WATHEFNI denied); WhatsApp spine tools hidden
- Default post-hire entry: Unified Action Inbox
- Audit events table `assistant_spine_events`
- No mutation tools offered under Wave 1 default
- Sibling freezes: E360 {f360[1]}, Onboarding {fonb[1]}, Attendance {fatt[1]}, Leave {flv[1]}, Shifts {fsh[1]}

Local smoke: `{local_s}`

---

## Blockers

{chr(10).join('- ' + b for b in blockers) if blockers else '- None for staging Wave 1 spine scope.'}
"""
(evid / "REPORT.md").write_text(report)
(evid / "docs").mkdir(exist_ok=True)
(evid / "docs" / "REPORT.md").write_text(report)
gate = "STAGING_PLATFORM_ASSISTANT_WAVE1_SPINE_GO" if verdict == "GO" else "STAGING_PLATFORM_ASSISTANT_WAVE1_SPINE_NO_GO"
(evid / "docs" / "GATE.txt").write_text(
    "\n".join([
        f"stamp={stamp}",
        f"evidence={evid}",
        "company=WATHEFNI",
        "channel=hr_dashboard",
        "mutations=off",
        "whatsapp_widening=false",
        "wave2_started=false",
        "payroll_money=false",
        "attendance_ingest=false",
        f"GATE={gate}",
        f"STAGING_WAVE1={verdict}",
        "PROD_SYNTHETIC=NO-GO",
        "",
    ])
)
freeze = f"""# Platform Assistant Wave 1 — Spine Contract Freeze (staging)

**Gate:** `{gate}`  
**Evidence:** `ops/evidence/platform-assistant-wave1-staging-{stamp}/`  
**Production synthetic:** **NO-GO** until separate Wave 1-B qualify  
**Assistant Wave 2:** **NO-GO / not started**

## Scope frozen

- One platform assistant spine for **WATHEFNI**, HR dashboard-first
- Master kill `WATHEFNI_ASSISTANT_KILL` · mutation kill `WATHEFNI_ASSISTANT_MUTATIONS` (default off under Wave 1)
- Module registration contract · grounded envelopes · assistant audit events · EN/AR fallbacks
- Read/prepare only: Unified Action Inbox (default post-hire entry), Employees 360, Setup Launch Readiness
- No WhatsApp widening · no mobile · no manager/employee assistants · no CK wiring · no AI in frozen module UIs · no new mutation tools

## Explicit NO-GO

- Production synthetic without Wave 1-B
- Assistant Wave 2 / safe-reads widen
- Payroll money · Attendance ingest · frozen-module contract changes
"""
(evid / "docs" / "PLATFORM_ASSISTANT_WAVE1_SPINE_FREEZE.md").write_text(freeze)
pathlib.Path(os.environ.get("REPO_FREEZE") or str(evid / "docs" / "PLATFORM_ASSISTANT_WAVE1_SPINE_FREEZE.md"))
print(report)
print("SYNTH_VERDICT", verdict)
print("PROD_SYNTHETIC", prod_synth)
PY

cp -a "$LOCAL_EVID/docs/PLATFORM_ASSISTANT_WAVE1_SPINE_FREEZE.md" \
  "$REPO_ROOT/ops/PLATFORM_ASSISTANT_WAVE1_SPINE_FREEZE.md"

echo "QUALIFY_DONE evidence=$LOCAL_EVID"
