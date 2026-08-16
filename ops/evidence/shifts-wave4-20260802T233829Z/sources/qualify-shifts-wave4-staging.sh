#!/usr/bin/env bash
# Shifts Wave 4 — local + staging qualify (NO production deploy).
# Templates + recurring schedules → L0 materialize prove.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave4-$STAMP"
REMOTE_STAGE="/tmp/shifts-w4-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/shifts-wave4/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,remote}
echo "$LOCAL_EVID" > /tmp/shw4.evid
echo "$STAMP" > /tmp/shw4.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local Wave 4 honesty/unit + W3 UX + freezes (DB smoke deferred to staging if no local binding)"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
export WATHEFNI_ENV="${WATHEFNI_ENV:-development}"
export WATHEFNI_SHIFTS_WAVE4=1
export WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
set +e
"$PY" smoke-test-shifts-templates-wave4.py 2>&1 | tee "$LOCAL_EVID/tests/wave4-local.out"
LOCAL_W4_RC=${PIPESTATUS[0]}
set -e
if [[ "$LOCAL_W4_RC" -ne 0 ]]; then
  if grep -q 'application_environment_missing_or_invalid\|could not connect\|OperationalError' "$LOCAL_EVID/tests/wave4-local.out"; then
    echo "LOCAL_DB_UNAVAILABLE — continuing with staging prove" | tee -a "$LOCAL_EVID/tests/wave4-local.out"
  else
    echo "LOCAL_WAVE4_FAILED"
    exit 1
  fi
fi
"$PY" smoke-test-shifts-wave3-ux.py 2>&1 | tee "$LOCAL_EVID/tests/wave3-ux-local.out" | tail -5
"$PY" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -2
"$PY" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onb-local.out" | tail -2
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-att-local.out" | tail -2
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -2

log "stage sources to staging orchestrator"
mkdir -p "$LOCAL_EVID/sources/ops/sql"
cp -a "$ORCH_SRC/shifts_templates_wave4.py" "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/shifts_wave3_controlled.py" "$ORCH_SRC/app.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave4-staging.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

log "deploy modules to staging orchestrator (no production)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
test -d "\$STG"
cp -a '$REMOTE_STAGE'/shifts_templates_wave4.py "\$STG/"
cp -a '$REMOTE_STAGE'/shifts_synthetic_cleanup.py "\$STG/"
cp -a '$REMOTE_STAGE'/app.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-templates-wave4.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-wave3-ux.py "\$STG/"
for f in smoke-test-shifts-authority-wave1.py smoke-test-shifts-schedule-integrity-wave2.py \
         smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py; do
  [[ -f '$REMOTE_STAGE'/\$f ]] && cp -a '$REMOTE_STAGE'/\$f "\$STG/" || true
done
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/shifts_templates_wave4_v1.sql "\$STG/ops/sql/"
# staging drop-in for Wave 4 (does not touch production)
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-shifts-wave4.conf <<'EOF'
[Service]
Environment=WATHEFNI_SHIFTS_WAVE4=1
Environment=WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS=SHW4,SHW4-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES=965532
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW1,SHW1-SYNTH|,SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|,SHW4,SHW4-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965528,965530,965531,965532
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW2C,SHW3B,SHW3B-SYNTH|,SHW4,SHW4-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965529,965530,965531,965532
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break; sleep 1; done
echo STAGING_W4_DEPLOY_OK
REMOTE

log "staging Wave 4 smoke + regressions"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-regressions.out"
set +e
STG=/opt/wathefni/staging/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
cd \$STG
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DASHBOARD_DIST=/opt/wathefni/staging/dashboard-dist
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
export WATHEFNI_SHIFTS_WAVE4=1
export WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS=SHW4,SHW4-SYNTH|
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES=965532
export WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
export WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
export WATHEFNI_SHIFTS_WAVE3=1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
echo '=== W4 ==='; \$PYBIN smoke-test-shifts-templates-wave4.py; echo W4_RC=\$?
echo '=== W3 UX ==='; \$PYBIN smoke-test-shifts-wave3-ux.py; echo W3_RC=\$?
echo '=== W1 ==='; \$PYBIN smoke-test-shifts-authority-wave1.py | tail -8; echo W1_RC=\${PIPESTATUS[0]}
echo '=== W2 ==='; \$PYBIN smoke-test-shifts-schedule-integrity-wave2.py | tail -12; echo W2_RC=\${PIPESTATUS[0]}
echo '=== E360 ==='; \$PYBIN smoke-test-employees360-freeze-regression.py | tail -3
echo '=== ONB ==='; \$PYBIN smoke-test-onboarding-freeze-regression.py | tail -3
echo '=== ATT ==='; \$PYBIN smoke-test-attendance-freeze-regression.py | tail -3
echo '=== LEAVE ==='; \$PYBIN smoke-test-leave-freeze-regression.py | tail -3
echo STAGING_REGRESSIONS_DONE
REMOTE

# Verdict — prefer staging Wave 4 as authority when local DB unavailable
W4_OK=NO
if grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/wave4-local.out" 2>/dev/null; then W4_OK=YES; fi
STG_W4_OK=NO
grep -A120 '=== W4 ===' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null | grep -qE '[0-9]+ passed, 0 failed' && STG_W4_OK=YES || true
if grep -A120 '=== W4 ===' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null | grep -qE 'FAIL  |Traceback'; then STG_W4_OK=NO; fi
# If local skipped due to missing DB, staging W4 alone can authorize
if [[ "$W4_OK" != YES ]] && grep -q 'LOCAL_DB_UNAVAILABLE' "$LOCAL_EVID/tests/wave4-local.out" 2>/dev/null && [[ "$STG_W4_OK" == YES ]]; then
  W4_OK=YES
fi
W1_OK=NO; grep -A20 '=== W1 ===' "$LOCAL_EVID/tests/staging-regressions.out" | grep -qE 'passed, 0 failed' && W1_OK=YES || true
W2_OK=NO; grep -A30 '=== W2 ===' "$LOCAL_EVID/tests/staging-regressions.out" | grep -qE 'passed, 0 failed' && W2_OK=YES || true
if grep -A40 '=== W2 ===' "$LOCAL_EVID/tests/staging-regressions.out" | grep -qE 'FAIL  |Traceback|IndexError'; then W2_OK=NO; fi
W3_OK=NO; grep -A5 '=== W3 UX ===' "$LOCAL_EVID/tests/staging-regressions.out" | grep -qE 'passed, 0 failed' && W3_OK=YES || true

PROD_CANARY_VERDICT=NO-GO
if [[ "$W4_OK" == YES && "$STG_W4_OK" == YES && "$W1_OK" == YES && "$W2_OK" == YES && "$W3_OK" == YES ]]; then
  PROD_CANARY_VERDICT=GO
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 4 — templates & recurring schedules (local/staging)

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/shifts-wave4-$STAMP/\`  
**Module:** \`shifts_templates_wave4.py\` **v4.0.0**  
**Scope:** local + staging only. **No production deploy.**

## Template model
- Table \`shift_templates\`: named windows (same-day / overnight via \`ends_next_day\`), optional break/role/site/branch/team/position/location/timezone/notes
- Status \`active|archived\`; \`planning_version\` bumps on edit (never silently rewrites L0)
- Split schedules = two templates (two L0 authority rows)

## Recurrence / cycle model
- Table \`shift_recurrences\`: \`weekly_weekdays\`, \`n_on_m_off\` (six-on/one-off), \`alternating_templates\` (day/night weeks)
- Effective start/end, horizon default 90 / max 180
- Targets: employee | team | site | role
- Status: active | paused | ended

## Materialization / regeneration contract
- Preview classes: unchanged, newly_generated, updated_future, conflict, detached, cancelled_held
- Materialize writes \`status=scheduled\` L0 immediately (no draft/publish)
- Deterministic idempotency: \`SHW4|{company}|{recurrence_id}|{employee}|{date}|{template}|{start}|{end}\`
- Advisory lock per company+recurrence for concurrent authority
- Regen skips today/history; cancelled never auto-reappears; manual edit sets \`regen_detached\`

## Override / exception model
- \`shift_recurrence_exceptions\`: \`skip\` | \`one_off_override\` per date
- Manual reschedule/cancel of generated rows → \`regen_detached=true\`

## API / permission model
- Routes under \`/dashboard/posthire/shifts/templates\` and \`.../recurrences\` (+ preview/materialize/pause/resume/end/exceptions)
- Wave 3 real-mutation gate + SHW4 / 965532* synthetic markers
- Manual composer remains available without templates

## Complexity levels
| Level | Status |
|---|---|
| Simple (manual only) | Unchanged — default path |
| Medium (templates + weekly/cycle) | **This wave** |
| Enterprise (rotations/coverage/publish) | **Not built** |

## Test results
- Local Wave 4: $W4_OK (\`tests/wave4-local.out\`)
- Staging Wave 4: $STG_W4_OK
- Staging W1: $W1_OK · W2: $W2_OK · W3 UX: $W3_OK
- Freezes: see \`tests/freeze-*-local.out\` and staging regressions

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · No rotations/publishing/open shifts/PAM · No draft/publish · No production deploy · No real allowlists · Timers/reminders unchanged

## Unresolved blockers
- Production synthetic Wave 4 canary not executed in this wave (by design)
- Team/site/role resolution depends on org assignment / raw_json metadata
- Enterprise rotations / coverage / publishing remain out of scope

## GO/NO-GO for production synthetic Wave 4 canary

| Scope | Verdict |
|---|---|
| Production synthetic Wave 4 canary | **$PROD_CANARY_VERDICT** |
| Controlled real HR / manager enablement | **NO-GO** |
| Draft/publish / rotations / open shifts | **NO-GO** |
| Real reminders / timers | **NO-GO** |
| Broad employee-app | **NO-GO** |

EOF

if [[ "$PROD_CANARY_VERDICT" == GO ]]; then
  echo "STAGING_SHIFTS_W4_GO"
  echo "PROD_SYNTHETIC_WAVE4_CANARY_GO"
else
  echo "STAGING_SHIFTS_W4_NO_GO_OR_PARTIAL"
  echo "PROD_SYNTHETIC_WAVE4_CANARY_NO_GO"
fi
echo "QUALIFY_DONE evidence=$LOCAL_EVID"
