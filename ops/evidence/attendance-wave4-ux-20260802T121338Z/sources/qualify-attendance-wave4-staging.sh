#!/usr/bin/env bash
# Attendance Wave 4 — staging UX qualify (local + staging).
# NO production deploy. NO real punch ingest / devices / QR / GPS / kiosk / payroll money impact.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave4-ux-$STAMP"
REMOTE_STAGE="/tmp/attw4-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/attendance-wave4-ux-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
STAGING_DASH="/opt/wathefni/staging/dashboard-dist"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,audit}
echo "$LOCAL_EVID" > /tmp/attw4.evid
echo "$STAMP" > /tmp/attw4.stamp

log() { printf '\n=== %s ===\n' "$*"; }

ORCH_FILES=(
  attendance_ops_wave3.py
  attendance_ops_postgres.py
  attendance_ops_http.py
  smoke-test-attendance-ops-wave3.py
)

log "local Wave 3 ops smoke (regression)"
cd "$ORCH_SRC"
ATTW3_RESULTS_PATH="$LOCAL_EVID/tests/qualification-local.json" \
  WATHEFNI_ENV=local \
  .venv/bin/python smoke-test-attendance-ops-wave3.py 2>&1 | tee "$LOCAL_EVID/tests/qualify-local.out" | tail -20

log "local freezes"
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding.out" | tail -5

log "build dashboard"
cd "$REPO_ROOT/apps/wathefni-dashboard"
npm run build 2>&1 | tee "$LOCAL_EVID/tests/dashboard-build.out" | tail -30
rsync -a --delete dist/ "$LOCAL_EVID/sources/dashboard-dist/"

# Bundle marker checks — customer copy present, wave jargon absent from built PostHire chunk
MARKER_OUT="$LOCAL_EVID/tests/bundle-markers.txt"
{
  echo "stamp=$STAMP"
  CHUNK=$(ls dist/assets/PostHire-*.js 2>/dev/null | head -1 || true)
  echo "chunk=${CHUNK:-none}"
  if [[ -n "${CHUNK:-}" ]]; then
    for needle in "Attendance operations" "عمليات الحضور" "Connector health" "صحة الموصلات" "Day detail" "تفاصيل اليوم" "Approved — ready to apply" "Payroll excluded"; do
      if grep -qF "$needle" "$CHUNK"; then echo "FOUND $needle"; else echo "MISSING $needle"; fi
    done
    # Customer Attendance surfaces must not ship wave/authority jargon in NEW copy keys
    for bad in "authority mode" "dark mode (no real"; do
      if grep -qF "$bad" "$CHUNK"; then echo "JARGON $bad"; else echo "CLEAN no:$bad"; fi
    done
    # Note: Employees 360 org-units still contain legacy "Wave 4" product strings (frozen module).
    echo "NOTE employees360_may_contain_legacy_Wave4_strings"
    shasum -a 256 "$CHUNK" | awk '{print "sha256_posthire="$1}'
  fi
} | tee "$MARKER_OUT"

log "copy sources"
for f in "${ORCH_FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/attendance-wave4-ui-staging-screenshots.py" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-attendance-wave4-staging.sh" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/AttendanceOpsPanel.tsx" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/AttendanceDailyBoard.tsx" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/attendanceUx.ts" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/apps/wathefni-dashboard/src/posthire/AttendanceCaptureOps.tsx" "$LOCAL_EVID/sources/"

log "push to staging"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'/{tests,screenshots,sources,docs}"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${ORCH_FILES[@]}" "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$REPO_ROOT/ops/attendance-wave4-ui-staging-screenshots.py" "$VPS_HOST:$REMOTE_STAGE/"
rsync -az --delete -e "ssh -o BatchMode=yes" "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/qualify-staging.out"
set -euo pipefail
STAGING_ORCH='$STAGING_ORCH'
STAGING_DASH='$STAGING_DASH'
REMOTE_STAGE='$REMOTE_STAGE'
REMOTE_EVID='$REMOTE_EVID'
STAMP='$STAMP'

cp -a "\$REMOTE_STAGE"/*.py "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE"/attendance-wave4-ui-staging-screenshots.py "\$REMOTE_EVID/sources/" 2>/dev/null || true
cp -a "\$REMOTE_STAGE"/*.py "\$REMOTE_EVID/sources/" 2>/dev/null || true

# Backup + swap staging dashboard only (never /var/www)
if [[ -d "\$STAGING_DASH" ]]; then
  cp -a "\$STAGING_DASH" "\$STAGING_DASH.bak-wave4-\$STAMP"
fi
mkdir -p "\$STAGING_DASH"
rsync -a --delete "\$REMOTE_STAGE/dashboard-dist/" "\$STAGING_DASH/"
echo "staging dashboard updated: \$STAGING_DASH"

# Ensure ops flags remain on; ingest remains off
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/attendance-ops-wave3.conf
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_ATTENDANCE_OPS=on
Environment=WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI,ATTW3
Environment=WATHEFNI_ATTENDANCE_OPS_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
sleep 4
systemctl is-active wathefni-orchestrator-staging

cd "\$STAGING_ORCH"
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
if [[ ! -x "\$PYBIN" ]]; then PYBIN=/opt/wathefni/staging/orchestrator/.venv/bin/python; fi
if [[ ! -x "\$PYBIN" ]]; then PYBIN=\$(command -v python3); fi
echo "PYBIN=\$PYBIN"
# Prefer live staging process env for attendance flags
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_ATTENDANCE_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ

ATTW3_RESULTS_PATH="\$REMOTE_EVID/tests/qualification-staging.json" \
  "\$PYBIN" smoke-test-attendance-ops-wave3.py 2>&1 | tee "\$REMOTE_EVID/tests/ops-smoke.out" | tail -30

"\$PYBIN" smoke-test-employees360-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-employees360.out" | tail -5
"\$PYBIN" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-onboarding.out" | tail -5

# Ingest still off
"\$PYBIN" - <<'PY'
import os
assert str(os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST") or "off").lower() in {"", "0", "false", "off", "no"}
print("INGEST_OFF_OK")
PY

export ATTW4_UI_SHOTS="\$REMOTE_EVID/screenshots"
export DASHBOARD_BASE="http://127.0.0.1:8011/dashboard"
export API_BASE="http://127.0.0.1:8011"
"\$PYBIN" "\$REMOTE_STAGE/attendance-wave4-ui-staging-screenshots.py" 2>&1 | tee "\$REMOTE_EVID/tests/screenshots.out" | tail -40

"\$PYBIN" - <<'PY'
import json, pathlib
evid = pathlib.Path("$REMOTE_EVID")
shots = list((evid / "screenshots").glob("*.png"))
manifest = evid / "screenshots" / "manifest.json"
core = [p for p in shots if p.name.startswith("attendance-overview-")]
print(json.dumps({"shot_count": len(shots), "overview_core": len(core), "manifest": manifest.exists()}, indent=2))
assert len(core) >= 4, "need EN/AR × desktop/mobile overview shots"
print("SCREENSHOTS_OK")
PY
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
mkdir -p "$LOCAL_EVID/screenshots"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/screenshots/*.png" "$LOCAL_EVID/screenshots/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/screenshots/manifest.json" "$LOCAL_EVID/screenshots/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/tests/*" "$LOCAL_EVID/tests/" 2>/dev/null || true

# Audit decisions doc
cat > "$LOCAL_EVID/audit/page-by-page.md" <<'EOF'
# Attendance Wave 4 — page-by-page audit decisions

| Surface | Decision | Rationale |
|---|---|---|
| Attendance overview | **Refine in place** | Keep PostHire Attendance shell; add life-state stats (captured/late/absent/needs review/payroll excluded) aligned to E360 QuietStat chrome |
| Daily attendance table | **Enrich columns** | Scheduled, actual, worked minutes, late/early, life-state pills; day-detail expand for sessions/breaks/payroll exclusion |
| Exception queue | **New AttendanceOpsPanel** | True ops queue from `/dashboard/attendance/ops/*` with owner/due/next action; cream board language |
| Employee attendance detail | **Inline expand** | Day detail row under table (sessions, breaks, payroll reason, version) — no separate route |
| Correction review | **Ops Corrections tab** | Before/after snapshots; Approve ≠ Apply; dual-approval strip |
| Disputes / reopen | **Ops Disputes tab + reopen evidence** | Raise/resolve dispute; reopen requires evidence note |
| Approval / dual-approval | **Visible states** | Case status labels + ApprovalStrip when pending second approver |
| Payroll lock / exclusion | **BlockedReason copy** | Customer-facing exclusion reasons; locked tab for excluded queue items |
| Capture connector health | **Polish CaptureOpsPanel** | Rename to Connector health; remove wave/dark jargon; ingest-off banner retained |
| EN/AR + RTL | **useEmployees360Locale** | Same locale rail as E360 / pre-hire |
| Loading / empty / error / stale / permission | **Covered** | Ops + capture panels + attendance page states |
EOF

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Attendance Wave 4 — UX refinement & staging qualification

**Stamp:** \`$STAMP\`  
**Evidence:** \`$LOCAL_EVID\`  
**Scope:** local + staging only. Production UX deploy **not** performed by this runner.

## Separate verdicts

| Gate | Verdict |
|---|---|
| Staging UX (WATHEFNI synthetic) | see tests + screenshots below |
| Production UX deployment | **NO-GO until staging GO recorded** |
| Controlled real HR attendance ops (no devices) | **NO-GO** — Wave 4 is UX + synthetic ops only |
| Real punch ingest / biometric / QR / GPS / kiosk | **NO-GO** — \`CAPTURE_INGEST=off\` |
| Real payroll money impact | **NO-GO** |

## Hard bans preserved

- No real punch ingestion
- No biometric devices, QR, GPS, kiosk, or broad employee clocking
- No edits to frozen Employees 360 / Onboarding / pre-hire modules beyond Attendance PostHire surfaces

## Implemented UX

- \`AttendanceOpsPanel\` — exception queue, corrections (approve≠apply), disputes, locked/excluded
- \`AttendanceDailyBoard\` — overview stats + enriched daily table + day detail
- \`attendanceUx.ts\` — life states + payroll exclusion copy (EN/AR)
- Capture panel retitled **Connector health** (customer copy)
- API clients for \`/dashboard/attendance/ops/*\`
- Ops \`list_queue\` now returns \`cases\` + \`disputes\` for durable UI reload

## Screenshots

See \`screenshots/\` (authenticated EN/AR × desktop/mobile).

## Remaining blockers

Documented after remote pull — fill from \`tests/\` outputs.
EOF

log "done — evidence at $LOCAL_EVID"
echo "$LOCAL_EVID"
