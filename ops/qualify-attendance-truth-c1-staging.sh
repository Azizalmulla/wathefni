#!/usr/bin/env bash
# Wave 2 C1 — Attendance Truth qualify (company-scoped ingest; global ingest off by default).
# Process-scoped flags inside smoke only. No systemd-global enable. Stop before C2.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-truth-c1-$STAMP"
REMOTE_STAGE="/tmp/att-truth-c1-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local unit / memory prove"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" smoke-test-attendance-truth-c1.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "freeze regression (must stay green)"
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-regression.out" || true

log "stage sources"
cp -a \
  "$ORCH_SRC/attendance_truth_c1.py" \
  "$ORCH_SRC/attendance_capture_ops.py" \
  "$ORCH_SRC/attendance_capture_ops_http.py" \
  "$ORCH_SRC/smoke-test-attendance-truth-c1.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/ATTENDANCE_TRUTH_C1_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/WATHEFNI_HCM_WAVE2_WORKFORCE_TRUTH_BUILD_CHARTER.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/attendance_truth_c1.py" \
  "$ORCH_SRC/attendance_capture_ops.py" \
  "$ORCH_SRC/attendance_capture_ops_http.py" \
  "$ORCH_SRC/smoke-test-attendance-truth-c1.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global ingest enable)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
# Refuse unexpected systemd drop-ins that globally force ingest on
if grep -Rls 'WATHEFNI_ATTENDANCE_CAPTURE_INGEST=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_INGEST_ON; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_INGEST_REMAINS_OFF
REMOTE

log "staging prove (process-scoped flags inside smoke)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-prove.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
cd "\$STG"
export WATHEFNI_ENV=staging
# Smoke sets its own process-scoped ingest/allowlist; do not export CAPTURE_INGEST=on here.
"\$PYBIN" smoke-test-attendance-truth-c1.py
echo STAGING_RC=\$?
REMOTE

UNIT_OK=NO
if grep -q 'ATTENDANCE_TRUTH_FULL_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out"; then
  UNIT_OK=YES
fi
STG_OK=NO
if grep -q 'ATTENDANCE_TRUTH_FULL_PASS' "$LOCAL_EVID/tests/staging-prove.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-prove.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-prove.out"; then
  STG_OK=YES
fi
FREEZE_OK=YES
if grep -qE 'FAIL|Traceback' "$LOCAL_EVID/tests/freeze-regression.out" 2>/dev/null; then
  # freeze smoke prints its own verdict — accept if it ends with PASS stamp
  if ! grep -qE 'FREEZE.*PASS|passed, 0 failed' "$LOCAL_EVID/tests/freeze-regression.out"; then
    FREEZE_OK=NO
  fi
fi

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$STG_OK" == YES && "$FREEZE_OK" == YES ]]; then
  VERDICT='ATTENDANCE_TRUTH_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Attendance Truth C1 — Staging Prove

- Stamp: $STAMP
- Unit: $UNIT_OK
- Staging: $STG_OK
- Freeze regression: $FREEZE_OK
- Global CAPTURE_INGEST: remains **off** (company allowlist fail-closed when temporarily process-scoped on)
- Canary: ATTTRUTH synthetic in smoke; entitlement pattern for WATHEFNI / dedicated truth tenant
- Verdict: **$VERDICT**

## Proven
1. Global ingest off / empty allowlist deny
2. Company-entitled ingest → punches → day projection
3. Correction approve ≠ apply; apply mutates projection
4. Reject does not apply

## Stop
Do **not** start C2 Leave Enforcement until owner reviews this stamp.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != ATTENDANCE_TRUTH_FULL_PASS ]]; then
  exit 1
fi
