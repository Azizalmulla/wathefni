#!/usr/bin/env bash
# Shifts Wave 5 — local + staging qualify (NO production deploy).
# Draft/review/publish, open shifts, coverage above Wave 4 templates.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave5-$STAMP"
REMOTE_STAGE="/tmp/shifts-w5-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/shifts-wave5/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,remote}
echo "$LOCAL_EVID" > /tmp/shw5.evid
echo "$STAMP" > /tmp/shw5.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local Wave 5 honesty/unit + freezes (DB smoke deferred to staging if no local binding)"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
export WATHEFNI_ENV="${WATHEFNI_ENV:-development}"
export WATHEFNI_SHIFTS_WAVE5=1
export WATHEFNI_SHIFTS_WAVE5_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE4=1
export WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
set +e
"$PY" smoke-test-shifts-publish-wave5.py 2>&1 | tee "$LOCAL_EVID/tests/wave5-local.out"
LOCAL_W5_RC=${PIPESTATUS[0]}
set -e
if [[ "$LOCAL_W5_RC" -ne 0 ]]; then
  if grep -q 'application_environment_missing_or_invalid\|could not connect\|OperationalError\|ModuleNotFoundError: No module named .psycopg' "$LOCAL_EVID/tests/wave5-local.out"; then
    echo "LOCAL_DB_UNAVAILABLE — continuing with staging prove" | tee -a "$LOCAL_EVID/tests/wave5-local.out"
  else
    echo "LOCAL_WAVE5_FAILED"
    exit 1
  fi
fi
"$PY" smoke-test-shifts-templates-wave4.py 2>&1 | tee "$LOCAL_EVID/tests/wave4-local.out" | tail -8 || true
"$PY" smoke-test-shifts-wave3-ux.py 2>&1 | tee "$LOCAL_EVID/tests/wave3-ux-local.out" | tail -5 || true
"$PY" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -2 || true
"$PY" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onb-local.out" | tail -2 || true
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-att-local.out" | tail -2 || true
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -2 || true

log "stage sources to staging orchestrator"
mkdir -p "$LOCAL_EVID/sources/ops/sql"
cp -a "$ORCH_SRC/shifts_publish_wave5.py" "$ORCH_SRC/shifts_templates_wave4.py" "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/shifts_wave3_controlled.py" "$ORCH_SRC/app.py" \
  "$ORCH_SRC/smoke-test-shifts-publish-wave5.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave5-staging.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/lib/api.ts" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/shifts_publish_wave5.py" \
  "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/smoke-test-shifts-publish-wave5.py" \
  "$ORCH_SRC/smoke-test-shifts-templates-wave4.py" \
  "$ORCH_SRC/smoke-test-shifts-wave3-ux.py" \
  "$ORCH_SRC/smoke-test-shifts-authority-wave1.py" \
  "$ORCH_SRC/smoke-test-shifts-schedule-integrity-wave2.py" \
  "$ORCH_SRC/smoke-test-employees360-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-attendance-freeze-regression.py" \
  "$ORCH_SRC/smoke-test-leave-freeze-regression.py" \
  "$VPS_HOST:$REMOTE_STAGE/"
"${SCP[@]}" "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" \
  "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

log "deploy modules to staging orchestrator (no production)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
test -d "\$STG"
cp -a '$REMOTE_STAGE'/shifts_publish_wave5.py "\$STG/"
cp -a '$REMOTE_STAGE'/shifts_templates_wave4.py "\$STG/"
cp -a '$REMOTE_STAGE'/shifts_synthetic_cleanup.py "\$STG/"
cp -a '$REMOTE_STAGE'/app.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-publish-wave5.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-templates-wave4.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-wave3-ux.py "\$STG/"
for f in smoke-test-shifts-authority-wave1.py smoke-test-shifts-schedule-integrity-wave2.py \
         smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py; do
  [[ -f '$REMOTE_STAGE'/\$f ]] && cp -a '$REMOTE_STAGE'/\$f "\$STG/" || true
done
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/shifts_publish_wave5_v1.sql "\$STG/ops/sql/"
cp -a '$REMOTE_STAGE'/ops/sql/shifts_templates_wave4_v1.sql "\$STG/ops/sql/" || true
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-shifts-wave5.conf <<'EOF'
[Service]
Environment=WATHEFNI_SHIFTS_WAVE5=1
Environment=WATHEFNI_SHIFTS_WAVE5_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS=SHW5,SHW5-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES=965534
Environment=WATHEFNI_SHIFTS_WAVE4=1
Environment=WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS=SHW4,SHW4-SYNTH|,SHW5,SHW5-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES=965532,965534
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW1,SHW1-SYNTH|,SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|,SHW4,SHW4-SYNTH|,SHW5,SHW5-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965528,965530,965531,965532,965534
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW2C,SHW3B,SHW3B-SYNTH|,SHW4,SHW4-SYNTH|,SHW5,SHW5-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965529,965530,965531,965532,965534
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break; sleep 1; done
echo STAGING_W5_DEPLOY_OK
REMOTE

log "staging Wave 5 smoke + Wave 1–4 regressions + freezes"
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
export WATHEFNI_SHIFTS_WAVE5=1
export WATHEFNI_SHIFTS_WAVE5_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS=SHW5,SHW5-SYNTH|
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES=965534
export WATHEFNI_SHIFTS_WAVE4=1
export WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
export WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
export WATHEFNI_SHIFTS_WAVE3=1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
echo '=== W5 ==='; \$PYBIN smoke-test-shifts-publish-wave5.py; echo W5_RC=\$?
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

W5_OK=NO
if grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/wave5-local.out" 2>/dev/null && ! grep -qE '^FAIL  ' "$LOCAL_EVID/tests/wave5-local.out" 2>/dev/null; then W5_OK=YES; fi
STG_W5_OK=NO
if grep -q 'W5_RC=0' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null; then
  STG_W5_OK=YES
fi
# Require a clean W5 summary line with 0 failed and no FAIL markers in the W5 section
W5_SECTION=$(awk '/=== W5 ===/,/=== W4 ===/' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null || true)
if echo "$W5_SECTION" | grep -qE '[0-9]+ passed, 0 failed' && ! echo "$W5_SECTION" | grep -qE '^FAIL  |Traceback'; then
  STG_W5_OK=YES
else
  STG_W5_OK=NO
fi
if [[ "$W5_OK" != YES ]] && grep -q 'LOCAL_DB_UNAVAILABLE' "$LOCAL_EVID/tests/wave5-local.out" 2>/dev/null && [[ "$STG_W5_OK" == YES ]]; then
  W5_OK=YES
fi
W4_OK=NO
W4_SECTION=$(awk '/=== W4 ===/,/=== W3 UX ===/' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null || true)
if echo "$W4_SECTION" | grep -qE '[0-9]+ passed, 0 failed' && ! echo "$W4_SECTION" | grep -qE '^FAIL  |Traceback'; then W4_OK=YES; fi
W3_OK=NO
W3_SECTION=$(awk '/=== W3 UX ===/,/=== W1 ===/' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null || true)
if echo "$W3_SECTION" | grep -qE '[0-9]+ passed, 0 failed' && ! echo "$W3_SECTION" | grep -qE '^FAIL  |Traceback'; then W3_OK=YES; fi
W1_OK=NO
if grep -q 'W1_RC=0' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null; then W1_OK=YES; fi
W1_SECTION=$(awk '/=== W1 ===/,/=== W2 ===/' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null || true)
if echo "$W1_SECTION" | grep -qE 'passed, 0 failed' && ! echo "$W1_SECTION" | grep -qE 'FAIL  |Traceback'; then W1_OK=YES; else W1_OK=NO; fi
W2_OK=NO
if grep -q 'W2_RC=0' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null; then W2_OK=YES; fi
W2_SECTION=$(awk '/=== W2 ===/,/=== E360 ===/' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null || true)
if echo "$W2_SECTION" | grep -qE 'passed, 0 failed' && ! echo "$W2_SECTION" | grep -qE 'FAIL  |Traceback|IndexError'; then W2_OK=YES; else W2_OK=NO; fi

PROD_SYNTHETIC_CANARY_VERDICT=NO-GO
if [[ "$W5_OK" == YES && "$STG_W5_OK" == YES && "$W4_OK" == YES && "$W1_OK" == YES && "$W2_OK" == YES && "$W3_OK" == YES ]]; then
  PROD_SYNTHETIC_CANARY_VERDICT=GO
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 5 — draft/review/publish, open shifts, coverage (local/staging)

**Stamp:** \`$STAMP\`  
**Evidence:** \`ops/evidence/shifts-wave5-$STAMP/\`  
**Module:** \`shifts_publish_wave5.py\` **v5.0.0**  
**Scope:** local + staging only. **No production deploy. No real employees.**

## Schedule-period & version model
- \`shift_schedule_periods\`: date range, timezone, site/branch/team scope, \`require_publish\`, \`row_version\`
- \`shift_schedule_versions\`: immutable published lineage (\`based_on\` / \`rollback_of\`), fingerprint, review_diff, coverage_snapshot, publish idempotency key
- \`shift_schedule_draft_rows\`: draft-only planned rows; never operational until publish
- L0 provenance columns: \`schedule_period_id\`, \`schedule_version_id\`, \`schedule_source\`

## State machine
\`draft\` → \`in_review\` → \`approved\` → \`published\` (via publish endpoint)  
Also: back to \`draft\`, \`cancelled\`; prior published → \`superseded\` (non-destructive)

## Publish & rollback contract
- Advisory lock per company+period; optimistic \`expected_row_version\`; idempotency key
- Drafts never write Attendance/Leave/reminders/Payroll
- Publish materializes/promotes L0; unchanged cloned rows retarget provenance (no duplicate)
- Historical/started (\`shift_date < today\`) locked/skipped
- Rollback = new audited draft from prior published version → approve → publish
- Conflict bulk acknowledge/cancel on draft rows before publish

## Open-shift model
- Unassigned needs by date/time/role/site/branch/team; same-day + overnight
- Claim → scoped approve/reject; self-approval denied; one winner; losers rejected
- Direct HR/manager assign; gates via Wave 4 conflict evaluator → canonical L0

## Coverage model
- Min staffing by role/team/branch/site + time band; effective dates; overnight windows
- Classes: covered | understaffed | overstaffed | unresolved_open_shift | unavailable_employee
- Default \`warn\`; \`block\` can stop publish. No money calculations.

## Permission / approval matrix
- HR owner: period CRUD, draft, review, publish, rollback, open-shift decide, coverage CRUD
- Manager scoped: draft/submit, scoped open-shift decide, coverage read
- Employee: claim only; self-approval false
- Simple companies: direct L0 with \`require_publish=false\`
- Medium/enterprise: \`require_publish=true\`

## UX architecture
- Calendar-aligned Shifts workspace extended with publish/open/coverage surfaces when Wave 5 enabled
- Draft vs published status, review-diff before publish; optional for simple companies

## Test results
- Local Wave 5: $W5_OK (\`tests/wave5-local.out\`)
- Staging Wave 5: $STG_W5_OK
- Staging W4: $W4_OK · W1: $W1_OK · W2: $W2_OK · W3 UX: $W3_OK
- Freezes: see \`tests/freeze-*-local.out\` and staging regressions

## Unresolved blockers
- Production synthetic Wave 5 canary **not run** in this wave (staging-only by design)
- Advanced rotations / remote hitches / PAM / real reminders / Payroll money: out of scope
- Dashboard publish panel is thin; full EN/AR polish may continue iteratively

## GO/NO-GO — production synthetic Wave 5 canary
**Verdict: $PROD_SYNTHETIC_CANARY_VERDICT**

| Gate | Result |
|---|---|
| Staging Wave 5 prove | $STG_W5_OK |
| Wave 1–4 regressions | W1=$W1_OK W2=$W2_OK W3=$W3_OK W4=$W4_OK |
| Production synthetic canary (this wave) | **NOT RUN** — staging qualifies readiness only |
| Real employees / reminders / Payroll | **NO-GO** |

EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "PROD_SYNTHETIC_WAVE5_CANARY_VERDICT=$PROD_SYNTHETIC_CANARY_VERDICT"
[[ "$PROD_SYNTHETIC_CANARY_VERDICT" == GO ]]
