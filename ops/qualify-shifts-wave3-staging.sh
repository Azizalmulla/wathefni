#!/usr/bin/env bash
# Shifts Wave 3 — staging UX qualify (NO production deploy).
# Runs Wave 3 UX smoke + frozen-module regressions locally.
# Optional: push sources to staging for API prove — does not enable real mutations,
# timers, templates, recurring, or Payroll money.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVID="$REPO_ROOT/ops/evidence/shifts-wave3-$STAMP"
mkdir -p "$EVID"/{tests,sources,screenshots,docs}
echo "$STAMP" > /tmp/w3-stamp.txt
PY="$ORCH/.venv/bin/python"
test -x "$PY" || PY=python3

cd "$ORCH"
cp -a shifts_wave3_controlled.py smoke-test-shifts-wave3-ux.py "$EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/ShiftsWorkspace.tsx" \
  "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/shiftsUx.ts" "$EVID/sources/" || true

"$PY" smoke-test-shifts-wave3-ux.py 2>&1 | tee "$EVID/tests/wave3-ux-smoke.out"
"$PY" smoke-test-employees360-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-e360.out" | tail -3
"$PY" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-onb.out" | tail -3
"$PY" smoke-test-attendance-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-att.out" | tail -3
"$PY" smoke-test-leave-freeze-regression.py 2>&1 | tee "$EVID/tests/freeze-leave.out" | tail -3

echo "Wave 3 local qualify evidence: $EVID"
echo "NO production deploy performed."
