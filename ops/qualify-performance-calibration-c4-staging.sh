#!/usr/bin/env bash
# Wave 4 C4 — Performance Calibration / Aggregation qualify (company-scoped; global OFF).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/performance-calibration-c4-$STAMP"
REMOTE_STAGE="/tmp/performance-calibration-c4-stage"

mkdir -p "$LOCAL_EVID"/{tests,docs,sources}
log() { printf '\n=== %s ===\n' "$*"; }

log "local gates"
cd "$ORCH_SRC"
PY=.venv/bin/python; test -x "$PY" || PY=python3
"$PY" - <<'PY' 2>&1 | tee "$LOCAL_EVID/tests/gates.out"
import os, sys
sys.path.insert(0, ".")
os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_C4"]="off"
import performance_calibration_c4 as c
assert c.runtime_gate_for_company("WATHEFNI").get("ok") is not True
assert c.honesty_payload().get("aggregation_deterministic_and_replayable") is True
assert c.honesty_payload().get("forced_distribution_never_assumed") is True
assert c.honesty_payload().get("calibration_never_erases_submitted_or_pre_cal") is True
assert c.honesty_payload().get("talent_potential_hipo_9box_succession_out") is True
assert c.honesty_payload().get("assistant_mutations") is False
assert c.PASS_STAMP == "PERFORMANCE_CALIBRATION_DEV_FULL_PASS"
# pure unit: missing never silent zero without rule
scale={"scale_type":"numeric","points":[{"value":1,"normalized":0},{"value":5,"normalized":1}]}
r=c.compute_pre_calibration_result(
  components=[{"kind":"manager","key":"manager","weight":1,"missing":True}],
  weights={"manager":1}, scale_snapshot=scale, missing_rule="block_finalization")
assert r.get("blocked") is True
print("LOCAL_GATES_OK")
PY

log "stage sources"
cp -a \
  "$ORCH_SRC/performance_calibration_c4.py" \
  "$ORCH_SRC/smoke-test-performance-calibration-c4.py" \
  "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/PERFORMANCE_CALIBRATION_C4_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PERFORMANCE_CALIBRATION_DEV_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE'"
"${SCP[@]}" \
  "$ORCH_SRC/performance_calibration_c4.py" \
  "$ORCH_SRC/smoke-test-performance-calibration-c4.py" \
  "$VPS_HOST:$REMOTE_STAGE/"

log "staging copy (no global calibration unlock)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
cp -a '$REMOTE_STAGE'/*.py "\$STG/"
if grep -Rls 'WATHEFNI_PERFORMANCE_CALIBRATION_C4=on' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_SYSTEMD_PERFORMANCE_CALIBRATION_C4_ON; exit 1
fi
echo STAGING_COPY_OK_GLOBAL_PERFORMANCE_CALIBRATION_OFF
REMOTE

log "staging DB prove"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/staging-db.out"
set -euo pipefail
STG=/opt/wathefni/staging/orchestrator
PROD=/opt/wathefni/orchestrator
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
export PYTHONPATH="\$STG:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" smoke-test-performance-calibration-c4.py
echo STAGING_RC=\$?
REMOTE

GATES_OK=NO
grep -q 'LOCAL_GATES_OK' "$LOCAL_EVID/tests/gates.out" && GATES_OK=YES
DB_OK=NO
if grep -q 'PERFORMANCE_CALIBRATION_DEV_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out"; then
  DB_OK=YES
fi

VERDICT=FAIL
if [[ "$GATES_OK" == YES && "$DB_OK" == YES ]]; then
  VERDICT='PERFORMANCE_CALIBRATION_DEV_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Performance Calibration C4 — Staging Prove

- Stamp: $STAMP
- Gates: $GATES_OK
- Staging DB: $DB_OK
- Global PERFORMANCE_CALIBRATION_C4: remains **off**
- Verdict: **$VERDICT**

Stop before C5 until owner accepts.

Evidence: \`$LOCAL_EVID\`
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
if [[ "$VERDICT" != PERFORMANCE_CALIBRATION_DEV_FULL_PASS ]]; then
  exit 1
fi
exit 0
