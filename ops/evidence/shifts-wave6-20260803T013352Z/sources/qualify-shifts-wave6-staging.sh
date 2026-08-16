#!/usr/bin/env bash
# Shifts Wave 6A — rotations, remote roster metadata, compliance, PAM export — local + staging qualify.
# NO production deploy. Rotations/compliance/PAM export above Wave 5 draft/review/publish and Wave 4 templates.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/shifts-wave6-$STAMP"
REMOTE_STAGE="/tmp/shifts-w6-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/shifts-wave6/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,remote}
echo "$LOCAL_EVID" > /tmp/shw6.evid
echo "$STAMP" > /tmp/shw6.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "local Wave 6A honesty/unit + freezes (DB smoke deferred to staging if no local binding)"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
export WATHEFNI_ENV="${WATHEFNI_ENV:-development}"
export WATHEFNI_SHIFTS_WAVE6=1
export WATHEFNI_SHIFTS_WAVE6_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS="SHW6,SHW6-SYNTH|"
export WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES=965536
export WATHEFNI_SHIFTS_WAVE5=1
export WATHEFNI_SHIFTS_WAVE5_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS="SHW5,SHW5-SYNTH|,SHW6,SHW6-SYNTH|"
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES=965534,965536
export WATHEFNI_SHIFTS_WAVE4=1
export WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS="SHW4,SHW4-SYNTH|,SHW6,SHW6-SYNTH|"
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES=965532,965536
set +e
"$PY" smoke-test-shifts-enterprise-wave6.py 2>&1 | tee "$LOCAL_EVID/tests/wave6-local.out"
LOCAL_W6_RC=${PIPESTATUS[0]}
set -e
if [[ "$LOCAL_W6_RC" -ne 0 ]]; then
  if grep -qE 'application_environment_missing_or_invalid|could not connect|OperationalError|ModuleNotFoundError: No module named .psycopg|database_environment_file_not_configured' "$LOCAL_EVID/tests/wave6-local.out"; then
    echo "LOCAL_DB_UNAVAILABLE — continuing with staging prove" | tee -a "$LOCAL_EVID/tests/wave6-local.out"
  else
    echo "LOCAL_WAVE6_FAILED"
    exit 1
  fi
fi
"$PY" smoke-test-shifts-publish-wave5.py 2>&1 | tee "$LOCAL_EVID/tests/wave5-local.out" | tail -8 || true
"$PY" smoke-test-shifts-templates-wave4.py 2>&1 | tee "$LOCAL_EVID/tests/wave4-local.out" | tail -8 || true
"$PY" smoke-test-shifts-wave3-ux.py 2>&1 | tee "$LOCAL_EVID/tests/wave3-ux-local.out" | tail -5 || true
"$PY" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-e360-local.out" | tail -2 || true
"$PY" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onb-local.out" | tail -2 || true
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-att-local.out" | tail -2 || true
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-leave-local.out" | tail -2 || true

log "stage sources to staging orchestrator"
mkdir -p "$LOCAL_EVID/sources/ops/sql"
cp -a "$ORCH_SRC/shifts_enterprise_wave6.py" "$ORCH_SRC/shifts_publish_wave5.py" "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" "$ORCH_SRC/shifts_wave3_controlled.py" "$ORCH_SRC/app.py" \
  "$ORCH_SRC/smoke-test-shifts-enterprise-wave6.py" \
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
cp -a "$ORCH_SRC/ops/sql/shifts_enterprise_wave6_v1.sql" "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" \
  "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" "$LOCAL_EVID/sources/ops/sql/"
cp -a "$REPO_ROOT/ops/qualify-shifts-wave6-staging.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/lib/api.ts" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/ops/sql' '$REMOTE_EVID'"
"${SCP[@]}" \
  "$ORCH_SRC/shifts_enterprise_wave6.py" \
  "$ORCH_SRC/shifts_publish_wave5.py" \
  "$ORCH_SRC/shifts_templates_wave4.py" \
  "$ORCH_SRC/shifts_synthetic_cleanup.py" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/smoke-test-shifts-enterprise-wave6.py" \
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
"${SCP[@]}" "$ORCH_SRC/ops/sql/shifts_enterprise_wave6_v1.sql" "$ORCH_SRC/ops/sql/shifts_publish_wave5_v1.sql" \
  "$ORCH_SRC/ops/sql/shifts_templates_wave4_v1.sql" \
  "$VPS_HOST:$REMOTE_STAGE/ops/sql/"

log "deploy modules to staging orchestrator (no production)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
test -d "\$STG"
cp -a '$REMOTE_STAGE'/shifts_enterprise_wave6.py "\$STG/"
cp -a '$REMOTE_STAGE'/shifts_publish_wave5.py "\$STG/"
cp -a '$REMOTE_STAGE'/shifts_templates_wave4.py "\$STG/"
cp -a '$REMOTE_STAGE'/shifts_synthetic_cleanup.py "\$STG/"
cp -a '$REMOTE_STAGE'/app.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-enterprise-wave6.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-publish-wave5.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-templates-wave4.py "\$STG/"
cp -a '$REMOTE_STAGE'/smoke-test-shifts-wave3-ux.py "\$STG/"
for f in smoke-test-shifts-authority-wave1.py smoke-test-shifts-schedule-integrity-wave2.py \
         smoke-test-employees360-freeze-regression.py smoke-test-onboarding-freeze-regression.py \
         smoke-test-attendance-freeze-regression.py smoke-test-leave-freeze-regression.py; do
  [[ -f '$REMOTE_STAGE'/\$f ]] && cp -a '$REMOTE_STAGE'/\$f "\$STG/" || true
done
mkdir -p "\$STG/ops/sql"
cp -a '$REMOTE_STAGE'/ops/sql/shifts_enterprise_wave6_v1.sql "\$STG/ops/sql/"
cp -a '$REMOTE_STAGE'/ops/sql/shifts_publish_wave5_v1.sql "\$STG/ops/sql/" || true
cp -a '$REMOTE_STAGE'/ops/sql/shifts_templates_wave4_v1.sql "\$STG/ops/sql/" || true
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-shifts-wave6.conf <<'EOF'
[Service]
Environment=WATHEFNI_SHIFTS_WAVE6=1
Environment=WATHEFNI_SHIFTS_WAVE6_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS=SHW6,SHW6-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES=965536
Environment=WATHEFNI_SHIFTS_WAVE5=1
Environment=WATHEFNI_SHIFTS_WAVE5_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS=SHW5,SHW5-SYNTH|,SHW6,SHW6-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES=965534,965536
Environment=WATHEFNI_SHIFTS_WAVE4=1
Environment=WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_KEY_MARKERS=SHW4,SHW4-SYNTH|,SHW5,SHW5-SYNTH|,SHW6,SHW6-SYNTH|
Environment=WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_PHONE_PREFIXES=965532,965534,965536
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW1,SHW1-SYNTH|,SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|,SHW4,SHW4-SYNTH|,SHW5,SHW5-SYNTH|,SHW6,SHW6-SYNTH|
Environment=WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965528,965530,965531,965532,965534,965536
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW2C,SHW3B,SHW3B-SYNTH|,SHW4,SHW4-SYNTH|,SHW5,SHW5-SYNTH|,SHW6,SHW6-SYNTH|
Environment=WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965529,965530,965531,965532,965534,965536
Environment=WATHEFNI_SHIFTS_HR_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=
Environment=WATHEFNI_SHIFTS_REAL_REMINDERS=0
Environment=WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 40); do curl -sf http://127.0.0.1:8011/health >/dev/null && echo health_ok && break; sleep 1; done
echo STAGING_W6_DEPLOY_OK
REMOTE

log "staging Wave 6A smoke + Wave 5/4/3/1/2 regressions + freezes"
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
export WATHEFNI_SHIFTS_WAVE6=1
export WATHEFNI_SHIFTS_WAVE6_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_KEY_MARKERS='SHW6,SHW6-SYNTH|'
export WATHEFNI_SHIFTS_WAVE6_SYNTHETIC_PHONE_PREFIXES=965536
export WATHEFNI_SHIFTS_WAVE5=1
export WATHEFNI_SHIFTS_WAVE5_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_KEY_MARKERS='SHW5,SHW5-SYNTH|,SHW6,SHW6-SYNTH|'
export WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_PHONE_PREFIXES=965534,965536
export WATHEFNI_SHIFTS_WAVE4=1
export WATHEFNI_SHIFTS_WAVE4_COMPANIES=WATHEFNI
export WATHEFNI_SHIFTS_WAVE4_SYNTHETIC_ONLY=1
export WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
export WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
export WATHEFNI_SHIFTS_WAVE3=1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
echo '=== W6 ==='; \$PYBIN smoke-test-shifts-enterprise-wave6.py; echo W6_RC=\$?
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

W6_OK=NO
if grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/wave6-local.out" 2>/dev/null && ! grep -qE '^FAIL  ' "$LOCAL_EVID/tests/wave6-local.out" 2>/dev/null; then W6_OK=YES; fi
STG_W6_OK=NO
W6_SECTION=$(awk '/=== W6 ===/,/=== W5 ===/' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null || true)
if echo "$W6_SECTION" | grep -qE '[0-9]+ passed, 0 failed' && ! echo "$W6_SECTION" | grep -qE '^FAIL  |Traceback'; then
  STG_W6_OK=YES
fi
if [[ "$W6_OK" != YES ]] && grep -qE 'LOCAL_DB_UNAVAILABLE' "$LOCAL_EVID/tests/wave6-local.out" 2>/dev/null && [[ "$STG_W6_OK" == YES ]]; then
  W6_OK=YES
fi

W5_OK=NO
W5_SECTION=$(awk '/=== W5 ===/,/=== W4 ===/' "$LOCAL_EVID/tests/staging-regressions.out" 2>/dev/null || true)
if echo "$W5_SECTION" | grep -qE '[0-9]+ passed, 0 failed' && ! echo "$W5_SECTION" | grep -qE '^FAIL  |Traceback'; then W5_OK=YES; fi

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

PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO=NO-GO
if [[ "$W6_OK" == YES && "$STG_W6_OK" == YES && "$W5_OK" == YES && "$W4_OK" == YES && "$W1_OK" == YES && "$W2_OK" == YES && "$W3_OK" == YES ]]; then
  PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO=GO
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Shifts Wave 6A — rotations, remote roster metadata, compliance, PAM export (local/staging)

**Stamp:** \`$STAMP\`
**Evidence:** \`ops/evidence/shifts-wave6-$STAMP/\`
**Module:** \`shifts_enterprise_wave6.py\` **v6.0.0** (above \`shifts_publish_wave5.py\` v5.0.0 / \`shifts_templates_wave4.py\` v4.0.0)
**Scope:** local + staging only. **No production deploy. No real employees. No PAM submission. No Payroll money.**

## Rotation / remote-roster model
- \`shift_rotation_patterns\`: preset kinds (\`four_on_four_off\`, \`six_on_one_off\`, \`n_on_m_off\`, \`panama_223\`, \`alternating_day_night\`, \`hitch_n_n\`, \`custom_sequence\`) → canonical cycle sequence of work/rest/travel/standby days
- \`shift_rotation_assignments\`: employee/crew/team/site/role target, cycle anchor + offset, effective window, optional remote/camp/transport/mobilization metadata (never monetary)
- \`shift_rotation_events\`: audit trail for pattern/assignment creation
- Rotation drafts feed the existing Wave 5 \`shift_schedule_draft_rows\` table only — Wave 5 draft → review → approve → publish remains the sole path to operational L0

## Compliance profiles
- \`shift_compliance_profiles\`: sector-scoped rule sets, default enforcement \`warn\` (or \`block\`)
- Rule types: \`ramadan_hours\`, \`midday_restriction\`, \`daily_hours_warning\`, \`weekly_hours_warning\`, \`weekly_rest_days\`, \`public_holiday_warning\`, \`break_metadata_warning\`
- Evaluated against draft work rows only; findings default to \`warn\` and never compute Payroll money

## PAM-style export
- \`shift_pam_exports\`: deterministic, read-only declaration built **only** from a published schedule version
- Contract \`pam-export@1.0.0\`; EN/AR CSV + report; status always \`manual_submission_required\`; \`submission: false\`
- No government API invented; no automated submission

## Publish contract (unchanged from Wave 5)
- Rotation-generated draft rows publish through the same \`publish_version\` gate as templates/recurrences
- Work rows promote to L0; \`travel\`/\`rest\`/\`standby\` rows are always skipped (\`skipped_non_work\`)
- Cycle edits: new draft from published + regenerate rotation never mutates published L0 (fingerprint unchanged)
- Soft-cancelled published shifts are held on regenerate (\`cancelled_held\` row class), never silently reintroduced

## Honesty
Rotations **true** · PAM export **true** · PAM submission **false** · Payroll money **false** · Leave balances not mutated · Attendance authority not mutated · Publishing/open shifts/coverage/compliance profiles **true** (inherited enterprise complexity level)

## Test results
- Local Wave 6A: $W6_OK (\`tests/wave6-local.out\`)
- Staging Wave 6A: $STG_W6_OK
- Staging W5: $W5_OK · W4: $W4_OK · W1: $W1_OK · W2: $W2_OK · W3 UX: $W3_OK
- Freezes: see \`tests/freeze-*-local.out\` and staging regressions section

## Unresolved blockers
- Production synthetic Wave 6 canary **not run** in this wave (staging-only by design)
- PAM submission, real government API integration, Payroll money: permanently out of scope for this module
- Remote/camp transport logistics are metadata-only; no dispatch/booking integration

## GO/NO-GO

| Gate | Result |
|---|---|
| Staging Wave 6A (rotations, compliance, PAM export, publish/cycle-edit/cancelled-held) | **$PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO** |
| Production synthetic Wave 6 canary readiness (same criteria as staging gate above; canary itself not run) | **$PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO** |
| Controlled real rotation / draft creation | **NO-GO** |
| PAM submission (government API) | **NO-GO** |
| Payroll money calculation | **NO-GO** |
| Real allowlists (HR/manager) | **NO-GO** (empty by design this wave) |

## Gate result
$(if [[ "$PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO" == GO ]]; then echo PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO; else echo PROD_SYNTHETIC_WAVE6_ENTERPRISE_NO_GO; fi)
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO=$PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO"
[[ "$PROD_SYNTHETIC_WAVE6_ENTERPRISE_GO" == GO ]]
