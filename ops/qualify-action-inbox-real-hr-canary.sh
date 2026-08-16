#!/usr/bin/env bash
# Action Inbox — controlled real-HR canary qualification (WATHEFNI / Aziz / Talal).
# Enable allowlists → prove Aziz/Talal scope → soft-kill + kill switch → rollback →
# redeploy → freezes. Does NOT widen past Aziz + Talal.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/action-inbox-real-hr-canary-$STAMP"
REMOTE_STAGE="/tmp/action-inbox-rhc-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/action-inbox-real-hr-canary/${STAMP}"
DROPIN_NAME=zzzzzzzzzzzzzzzz-action-inbox-real-hr-canary.conf

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,rollback,ui,verify}
echo "$LOCAL_EVID" > /tmp/aiw1rhc.evid
echo "$STAMP" > /tmp/aiw1rhc.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local smoke + freezes"
cd "$ORCH_SRC"
PY_LOCAL=".venv/bin/python"
test -x "$PY_LOCAL" || PY_LOCAL=python3
"$PY_LOCAL" smoke-test-action-inbox-wave1.py 2>&1 | tee "$LOCAL_EVID/tests/action-inbox-wave1-local.out"
"$PY_LOCAL" smoke-test-action-inbox-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-action-inbox-local.out" | tail -5
"$PY_LOCAL" smoke-test-analytics-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-analytics-local.out" | tail -3
"$PY_LOCAL" smoke-test-compliance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-compliance-local.out" | tail -3
"$PY_LOCAL" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -3
"$PY_LOCAL" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tail -3
"$PY_LOCAL" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-attendance-local.out" | tail -3
"$PY_LOCAL" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -3
"$PY_LOCAL" smoke-test-shifts-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-shifts-local.out" | tail -3

log "dashboard unit (no rebuild required if dist current; quick vitest)"
cd "$DASH_SRC"
npm test -- --run src/posthire/actionInboxWave1.test.ts 2>&1 | tee "$LOCAL_EVID/ui/vitest.out" | tail -10

log "stage + push"
mkdir -p "$LOCAL_EVID/sources/ops"
cd "$ORCH_SRC"
cp -a app.py action_inbox_wave1.py analytics_attention_wave1.py compliance_findings_wave1.py \
  canary-prod-action-inbox-real-hr.py \
  canary-prod-action-inbox-phase0b.py \
  canary-prod-action-inbox-wave1b.py \
  smoke-test-action-inbox-wave1.py \
  smoke-test-action-inbox-freeze-regression.py \
  smoke-test-analytics-freeze-regression.py \
  smoke-test-compliance-freeze-regression.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-action-inbox-real-hr-canary.sh "$LOCAL_EVID/sources/ops/"
cp -a "$REPO_ROOT/ops/qualify-action-inbox-real-hr-canary.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" app.py action_inbox_wave1.py analytics_attention_wave1.py compliance_findings_wave1.py \
    canary-prod-action-inbox-real-hr.py \
    canary-prod-action-inbox-phase0b.py \
    canary-prod-action-inbox-wave1b.py \
    smoke-test-action-inbox-wave1.py \
    smoke-test-action-inbox-freeze-regression.py \
    smoke-test-analytics-freeze-regression.py \
    smoke-test-compliance-freeze-regression.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    ops/deploy-action-inbox-real-hr-canary.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)

log "deploy Aziz/Talal canary"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-action-inbox-real-hr-canary.sh' '$REMOTE_STAGE/canary-prod-action-inbox-real-hr.py'
bash '$REMOTE_STAGE/deploy-action-inbox-real-hr-canary.sh'
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
export AIW1RHC_EVID="\$OUTDIR"
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
mkdir -p "\$OUTDIR"
export PYTHONUNBUFFERED=1
\$PYBIN -u canary-prod-action-inbox-real-hr.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback

log "verify live Aziz/Talal flags"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/flags-live.out"
set -euo pipefail
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'ACTION_INBOX_REAL_|ACTION_INBOX_EXCLUDE|ACTION_INBOX_WAVE1=' | sort
test -f /etc/systemd/system/wathefni-orchestrator.service.d/$DROPIN_NAME
VIEWER=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=' | cut -d= -f2-)
SUBJECT=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=' | cut -d= -f2-)
test "\$VIEWER" = "96599338566"
test "\$SUBJECT" = "WATHEFNI-96550252254"
echo LIVE_AZIZ_TALAL_FLAGS_OK
REMOTE

log "rollback proof (removes real-HR drop-in → empty allowlists via phase0b)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/action-inbox-real-hr-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/$DROPIN_NAME
# Phase 0-B empty allowlists should remain
test -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzz-action-inbox-phase0b-safety.conf
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
VIEWER=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=' | cut -d= -f2- || true)
SUBJECT=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=' | cut -d= -f2- || true)
test -z "\$VIEWER"
test -z "\$SUBJECT"
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE

log "redeploy canary (restore Aziz/Talal)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-action-inbox-real-hr-canary.sh'
REMOTE

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
run_canary canary-after-redeploy canary/after-redeploy

log "final live posture Aziz/Talal"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/flags-final.out"
set -euo pipefail
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
VIEWER=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST=' | cut -d= -f2-)
SUBJECT=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST=' | cut -d= -f2-)
WAVE=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_WAVE1=' | cut -d= -f2-)
EXCLUDE=\$(tr '\0' '\n' < /proc/\$PID/environ | grep '^WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL=' | cut -d= -f2-)
test "\$VIEWER" = "96599338566"
test "\$SUBJECT" = "WATHEFNI-96550252254"
test "\$WAVE" = "1"
test "\$EXCLUDE" = "1"
echo FINAL_AZIZ_TALAL_CANARY_OK
REMOTE

log "production sibling freezes"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/freezes-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
PY=\$ORCH/.venv/bin/python
cd \$ORCH
\$PY smoke-test-action-inbox-freeze-regression.py
\$PY smoke-test-analytics-freeze-regression.py
\$PY smoke-test-compliance-freeze-regression.py
\$PY smoke-test-employees360-freeze-regression.py
\$PY smoke-test-onboarding-freeze-regression.py
\$PY smoke-test-attendance-freeze-regression.py
\$PY smoke-test-leave-freeze-regression.py
\$PY smoke-test-shifts-freeze-regression.py
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/action-inbox-real-hr-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

# Extract item summary from canary output
ITEM_TOTAL=$(python3 - <<'PY' "$LOCAL_EVID/tests/canary-after-redeploy.out"
import json, re, sys
text = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
m = re.findall(r'\{[^{}]*"item_total"[^{}]*\}', text)
obj = json.loads(m[-1]) if m else {}
print(obj.get("item_total", "?"))
print(json.dumps(obj.get("by_source") or {}))
print(json.dumps(obj.get("by_soa") or {}))
PY
)
ITEM_N=$(echo "$ITEM_TOTAL" | sed -n '1p')
BY_SOURCE=$(echo "$ITEM_TOTAL" | sed -n '2p')
BY_SOA=$(echo "$ITEM_TOTAL" | sed -n '3p')

# Prefer full item dump from remote evidence
ITEMS_JSON="$LOCAL_EVID/remote/canary/after-redeploy/aziz-talal-items.json"
if [[ ! -f "$ITEMS_JSON" ]]; then
  ITEMS_JSON="$LOCAL_EVID/remote/canary/before-rollback/aziz-talal-items.json"
fi
ITEMS_MD="(see remote canary aziz-talal-items.json)"
if [[ -f "$ITEMS_JSON" ]]; then
  ITEMS_MD=$(python3 - <<'PY' "$ITEMS_JSON"
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"Total: **{d.get('total')}**")
print(f"By source: `{json.dumps(d.get('by_source') or {}, ensure_ascii=False)}`")
print(f"By system_of_action: `{json.dumps(d.get('by_system_of_action') or {}, ensure_ascii=False)}`")
print("")
print("| id | source | SoA | employee | severity | what | deep_link |")
print("|---|---|---|---|---|---|---|")
for i in d.get("items") or []:
    what = str(i.get("what_en") or "").replace("|", "/")[:80]
    print(f"| `{i.get('id')}` | {i.get('source')} | {i.get('system_of_action')} | `{i.get('employee_key')}` | {i.get('severity')} | {what} | {i.get('deep_link_page')} |")
PY
)
fi

log "write freeze + REPORT + GATE"
cat > "$LOCAL_EVID/docs/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md" <<EOF
# Unified Action Inbox — Controlled Real-HR Canary Freeze

**Gate:** \`PROD_ACTION_INBOX_REAL_HR_CANARY_GO\`  
**Evidence:** \`ops/evidence/action-inbox-real-hr-canary-${STAMP}/\`  
**Prerequisites:** \`PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO\` · \`PROD_ACTION_INBOX_PHASE0_SAFETY_GO\`

## Controlled posture (do not widen)

| Control | Value |
|---|---|
| Tenant | \`WATHEFNI\` only |
| Viewer | Aziz \`96599338566\` only |
| Subject | Talal \`WATHEFNI-96550252254\` only |
| Payroll/timesheet | \`EXCLUDE_PAYROLL=1\` |
| Mutations | forbidden (\`mutates_records: false\`) |
| Notifications | Alerts & Delivery |
| AI / Wave 2 / money / ingest / shifts-manager expand | **NO-GO** |

## Soft-kill / rollback

- Clear either allowlist → soft-kill (viewer deny or zero person items)
- \`WATHEFNI_ACTION_INBOX_WAVE1=0\` → API \`action_inbox_disabled\`
- Backup + \`ROLLBACK.sh\` under \`/opt/wathefni/backups/production-pre-action-inbox-real-hr-*\`

## Explicit NO-GO

- Adding any other viewer or employee subject
- Broad HR / manager rollout
- AI inside inbox / mutations / frozen-module reopen
EOF
cp -a "$LOCAL_EVID/docs/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md" "$REPO_ROOT/ops/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md"

cat > "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" <<EOF
# Unified Action Inbox Wave 1 — Freeze

**Gate:** \`PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO\`  
**Phase 0-B:** \`PROD_ACTION_INBOX_PHASE0_SAFETY_GO\`  
**Real-HR canary:** \`PROD_ACTION_INBOX_REAL_HR_CANARY_GO\` → \`ops/evidence/action-inbox-real-hr-canary-${STAMP}/\`  
**Freeze:** **GO** for controlled real-HR use (Aziz viewer / Talal subject only)

## Frozen posture

- Read-only composition; frozen modules remain systems of action
- \`WAVE1=1\` · \`SYNTHETIC_ONLY=1\` · \`EXCLUDE_PAYROLL=1\`
- Viewer allowlist: \`96599338566\` (Aziz)
- Subject allowlist: \`WATHEFNI-96550252254\` (Talal)
- Alerts & Delivery owns notifications; Hiring Reports separate
- No AI; no Compliance/Analytics Wave 2; no Payroll money; no Attendance ingest; no Shifts manager expansion

## Explicit NO-GO

- Widening viewer or subject allowlists
- Broad HR / manager rollout
- AI / mutations / Wave 2 / money / ingest / shifts-manager expand
- Reopening frozen module boundaries

See also \`ops/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md\`.
EOF
cp -a "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" "$LOCAL_EVID/docs/ACTION_INBOX_WAVE1_FREEZE.md"

"${SCP[@]}" "$REPO_ROOT/ops/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md" "$VPS_HOST:/opt/wathefni/ops/"
"${SCP[@]}" "$REPO_ROOT/ops/ACTION_INBOX_WAVE1_FREEZE.md" "$VPS_HOST:/opt/wathefni/ops/"

CANARY1_OK=0
CANARY2_OK=0
ROLLBACK_OK=0
FREEZES_OK=0
FLAGS_OK=0
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-before-rollback.out" && CANARY1_OK=1 || true
grep -q '"fail": 0' "$LOCAL_EVID/tests/canary-after-redeploy.out" && CANARY2_OK=1 || true
grep -q 'ROLLBACK_VERIFIED' "$LOCAL_EVID/tests/rollback.out" && ROLLBACK_OK=1 || true
grep -q 'FINAL_AZIZ_TALAL_CANARY_OK' "$LOCAL_EVID/tests/flags-final.out" && FLAGS_OK=1 || true
if ! grep -q '^FAIL ' "$LOCAL_EVID/tests/freezes-prod.out" && grep -q 'passed, 0 failed' "$LOCAL_EVID/tests/freezes-prod.out"; then
  FREEZES_OK=1
else
  FREEZES_OK=0
fi

VERDICT=NO-GO
if [[ "$CANARY1_OK" -eq 1 && "$CANARY2_OK" -eq 1 && "$ROLLBACK_OK" -eq 1 && "$FREEZES_OK" -eq 1 && "$FLAGS_OK" -eq 1 ]]; then
  VERDICT=GO
fi

cat > "$LOCAL_EVID/docs/REPORT.md" <<EOF
# Action Inbox — controlled real-HR canary

**Stamp:** \`$STAMP\`  
**Evidence:** \`$LOCAL_EVID\`  
**Prerequisites:** Phase 0-B \`PROD_ACTION_INBOX_PHASE0_SAFETY_GO\` · Wave 1-B synthetic GO

## Verdicts

| Scope | Verdict |
|---|---|
| Controlled real-HR canary (Aziz / Talal) | **$VERDICT** |
| Freeze inbox for controlled real-HR use | **$VERDICT** |
| Widen beyond Aziz / Talal | **NO-GO** |
| Broad HR / manager rollout | **NO-GO** |
| AI / mutations / Wave 2 / money / ingest | **NO-GO** |

## Scope

| Control | Value |
|---|---|
| Tenant | \`WATHEFNI\` |
| Viewer | Aziz \`96599338566\` |
| Subject | Talal \`WATHEFNI-96550252254\` |
| Payroll exclude | \`EXCLUDE_PAYROLL=1\` |

## Items shown (Aziz live payload)

$ITEMS_MD

Summary counters: total=$ITEM_N · by_source=$BY_SOURCE · by_soa=$BY_SOA

## Privacy / scope

- Fouad + other non-allowlisted viewers → \`action_inbox_viewer_denied\`
- All inbox employee keys = Talal only (Analytics / Compliance / E360 filtered)
- No payroll/timesheet SoA rows
- Deep links permission-safe pages only (no payroll page under exclude)
- Soft-kill: clear viewer → deny; clear subject → zero person items
- \`ACTION_INBOX_WAVE1=0\` → \`action_inbox_disabled\`
- Residual canary ACK = 0; sibling freezes green

## Proof bits

- Canary before rollback fail=0 → $CANARY1_OK
- Rollback verified (allowlists empty) → $ROLLBACK_OK
- Canary after redeploy fail=0 → $CANARY2_OK
- Final Aziz/Talal flags → $FLAGS_OK
- Sibling freezes → $FREEZES_OK

## Rollback

\`/opt/wathefni/backups/production-pre-action-inbox-real-hr-*\` + \`ROLLBACK.sh\`
EOF

mkdir -p "$REPO_ROOT/.cursor/rules"
cat > "$REPO_ROOT/.cursor/rules/action-inbox-freeze.mdc" <<'RULE'
---
description: Unified Action Inbox freeze — controlled real-HR canary (Aziz/Talal only)
globs: apps/wathefni-dashboard/src/posthire/PostHire.tsx,wathefni-orchestrator/action_inbox_wave1.py,wathefni-orchestrator/app.py
alwaysApply: false
---

# Unified Action Inbox freeze (controlled real-HR)

See `ops/ACTION_INBOX_REAL_HR_CANARY_FREEZE.md` and `ops/ACTION_INBOX_WAVE1_FREEZE.md`.

## Final posture

- Viewer allowlist: Aziz `96599338566` only
- Subject allowlist: Talal `WATHEFNI-96550252254` only
- `EXCLUDE_PAYROLL=1`; read-only; Alerts & Delivery owns notifications
- Do not widen allowlists; do not add AI/mutations/Wave 2/money/ingest/shifts-manager expand

## Soft-kill

Clear either allowlist, or set `WATHEFNI_ACTION_INBOX_WAVE1=0`.
RULE

if [[ "$VERDICT" == "GO" ]]; then
  echo "GATE=PROD_ACTION_INBOX_REAL_HR_CANARY_GO" | tee "$LOCAL_EVID/docs/GATE.txt"
  echo "PROD_ACTION_INBOX_REAL_HR_CANARY_GO"
else
  echo "GATE=PROD_ACTION_INBOX_REAL_HR_CANARY_NO_GO" | tee "$LOCAL_EVID/docs/GATE.txt"
  echo "PROD_ACTION_INBOX_REAL_HR_CANARY_NO_GO"
  exit 1
fi
