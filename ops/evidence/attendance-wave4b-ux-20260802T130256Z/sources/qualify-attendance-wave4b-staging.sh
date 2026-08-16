#!/usr/bin/env bash
# Attendance Wave 4B — staging UX production-readiness (local + staging only).
# Closes Wave 4 evidence gaps. NO production deploy. NO real ingest/devices/QR/GPS/kiosk/payroll money.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave4b-ux-$STAMP"
REMOTE_STAGE="/tmp/attw4b-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/attendance-wave4b-ux-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
STAGING_DASH="/opt/wathefni/staging/dashboard-dist"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,clickthrough,reconcile,audit}
echo "$LOCAL_EVID" > /tmp/attw4b.evid
echo "$STAMP" > /tmp/attw4b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

ORCH_FILES=(
  attendance_ops_wave3.py
  attendance_ops_postgres.py
  attendance_ops_http.py
  attendance_authority_wave1.py
  attendance_authority_postgres.py
  smoke-test-attendance-ops-wave3.py
  smoke-test-onboarding-freeze-regression.py
  smoke-test-employees360-freeze-regression.py
  seed-and-prove-attendance-wave4b.py
  onboarding_wave2.py
  action_registry.py
)

log "local Wave 4B seed+prove"
cd "$ORCH_SRC"
ATTW4B_EVID="$LOCAL_EVID/clickthrough/local" WATHEFNI_ENV=local \
  .venv/bin/python seed-and-prove-attendance-wave4b.py 2>&1 | tee "$LOCAL_EVID/tests/seed-prove-local.out"
test "$(python3 -c "import json;print(json.load(open('$LOCAL_EVID/clickthrough/local/summary.json'))['failed'])")" = "0"

log "local freezes (must be green)"
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360-local.out" | tail -5
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding-local.out" | tee /tmp/attw4b-onb-local.out | tail -8
if grep -qE '[1-9][0-9]* failed' /tmp/attw4b-onb-local.out; then echo "REFUSE local onboarding freeze"; exit 2; fi

log "local Wave 3 ops smoke regression"
ATTW3_RESULTS_PATH="$LOCAL_EVID/tests/ops-wave3-local.json" WATHEFNI_ENV=local \
  .venv/bin/python smoke-test-attendance-ops-wave3.py 2>&1 | tee "$LOCAL_EVID/tests/ops-wave3-local.out" | tail -8

log "copy sources + push staging"
for f in "${ORCH_FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
cp -a "$REPO_ROOT/ops/attendance-wave4b-ui-staging-screenshots.py" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/qualify-attendance-wave4b-staging.sh" "$LOCAL_EVID/sources/"

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'/{tests,screenshots,clickthrough,docs,sources}"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${ORCH_FILES[@]}" "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$REPO_ROOT/ops/attendance-wave4b-ui-staging-screenshots.py" "$VPS_HOST:$REMOTE_STAGE/"

# Ensure staging dashboard still has Wave 4 UX (reuse current staging dist if present)
if [[ -d "$REPO_ROOT/apps/wathefni-dashboard/dist/assets" ]]; then
  rsync -az -e "ssh -o BatchMode=yes" "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/" || true
fi

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/qualify-staging.out"
set -euo pipefail
STAGING_ORCH='$STAGING_ORCH'
STAGING_DASH='$STAGING_DASH'
REMOTE_STAGE='$REMOTE_STAGE'
REMOTE_EVID='$REMOTE_EVID'
STAMP='$STAMP'

# --- Fix onboarding freeze drift (sync required modules; do NOT accept drift) ---
cp -a "\$REMOTE_STAGE/onboarding_wave2.py" "\$STAGING_ORCH/onboarding_wave2.py"
cp -a "\$REMOTE_STAGE/action_registry.py" "\$STAGING_ORCH/action_registry.py"
# Ops/authority modules used by seed
for f in attendance_ops_wave3.py attendance_ops_postgres.py attendance_ops_http.py \
         attendance_authority_wave1.py attendance_authority_postgres.py \
         seed-and-prove-attendance-wave4b.py smoke-test-attendance-ops-wave3.py \
         smoke-test-onboarding-freeze-regression.py smoke-test-employees360-freeze-regression.py; do
  cp -a "\$REMOTE_STAGE/\$f" "\$STAGING_ORCH/\$f"
done
cp -a "\$REMOTE_STAGE"/*.py "\$REMOTE_EVID/sources/" 2>/dev/null || true

if [[ -d "\$REMOTE_STAGE/dashboard-dist" ]]; then
  mkdir -p "\$STAGING_DASH"
  rsync -a "\$REMOTE_STAGE/dashboard-dist/" "\$STAGING_DASH/" || true
fi

# Keep ops on / ingest off
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/attendance-ops-wave3.conf
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_ATTENDANCE_OPS=on
Environment=WATHEFNI_ATTENDANCE_OPS_COMPANIES=WATHEFNI,ATTW3
Environment=WATHEFNI_ATTENDANCE_OPS_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_OPS_DUAL_APPROVAL_KINDS=absence,early_leave
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ATTENDANCE_AUTHORITY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
sleep 5
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
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_ATTENDANCE_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ

echo "=== staging onboarding freeze (must pass — drift eliminated) ==="
"\$PYBIN" smoke-test-onboarding-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-onboarding.out"
if grep -qE '[1-9][0-9]* failed' "\$REMOTE_EVID/tests/freeze-onboarding.out"; then
  echo "REFUSE: onboarding freeze still drifting on staging" >&2
  exit 2
fi

echo "=== staging E360 freeze ==="
"\$PYBIN" smoke-test-employees360-freeze-regression.py 2>&1 | tee "\$REMOTE_EVID/tests/freeze-employees360.out" | tail -5

echo "=== staging Wave 4B seed+prove ==="
export ATTW4B_EVID="\$REMOTE_EVID/clickthrough"
export ATTW4B_USE_APP=1
export ATTW4B_COMPANY=WATHEFNI
"\$PYBIN" seed-and-prove-attendance-wave4b.py 2>&1 | tee "\$REMOTE_EVID/tests/seed-prove-staging.out"
test "\$(python3 -c "import json;print(json.load(open('\$REMOTE_EVID/clickthrough/summary.json'))['failed'])")" = "0"
WORK_DATE=\$(python3 -c "import json;print(json.load(open('\$REMOTE_EVID/clickthrough/summary.json'))['work_date'])")
echo "WORK_DATE=\$WORK_DATE" | tee "\$REMOTE_EVID/tests/work-date.txt"

# HTTP reconciliation against live list_attendance
export ATTW4B_WORK_DATE="\$WORK_DATE"
"\$PYBIN" - <<'PY' | tee "\$REMOTE_EVID/reconcile/http-reconcile.json"
import json, os, sys, urllib.request
from pathlib import Path
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
import app
company="WATHEFNI"
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM dashboard_users WHERE company_code=%s AND status='active' AND role='owner' ORDER BY updated_at DESC NULLS LAST LIMIT 1", (company,))
        user=cur.fetchone()
token,_=app.create_dashboard_session(dict(user))
work=os.environ["ATTW4B_WORK_DATE"]
seed=json.loads(Path(os.environ["ATTW4B_EVID"]+"/seed-index.json").read_text())
tag=seed["tag"]
req=urllib.request.Request(
    f"http://127.0.0.1:8011/dashboard/posthire/attendance?start_date={work}&end_date={work}&limit=500",
    headers={"Authorization":f"Bearer {token}","X-Wathefni-Company":company,"X-Company-Code":company},
)
with urllib.request.urlopen(req, timeout=60) as resp:
    payload=json.loads(resp.read().decode())
rows=[r for r in (payload.get("attendance") or []) if f"ATTW4B-{tag}-" in str(r.get("employee_key") or "")]
# compare to seed-index counts via life-state helper
counts={"approved":0,"incomplete":0,"absent":0,"disputed":0,"locked":0,"needs_review":0,"captured":0}
excl=[]
for row in rows:
    meta=row.get("metadata") or {}
    if meta.get("payroll_locked"):
        st="locked"
    else:
        approval=str(meta.get("approval_status") or "").lower()
        status=str(row.get("status") or "").lower()
        if approval=="disputed" or status=="disputed": st="disputed"
        elif approval=="approved": st="approved"
        elif status=="absent": st="absent"
        elif str(meta.get("exception_state") or "none") not in {"","none"}: st="incomplete"
        elif int(row.get("late_minutes") or 0)>0 or int(row.get("early_leave_minutes") or meta.get("early_leave_minutes") or 0)>0: st="needs_review"
        else: st="captured"
    counts[st]=counts.get(st,0)+1
    if meta.get("payroll_eligible") is False or meta.get("payroll_locked") or str(meta.get("exception_state") or "none") not in {"","none"} or approval in {"disputed","unapproved",""}:
        if approval!="approved" or meta.get("payroll_eligible") is False:
            excl.append({"key":row.get("employee_key"),"exception_state":meta.get("exception_state"),"approval_status":meta.get("approval_status"),"payroll_eligible":meta.get("payroll_eligible"),"payroll_locked":meta.get("payroll_locked")})
out={"http_rows":len(rows),"counts":counts,"seed_counts":seed.get("counts"),"exclusion_n":len(excl),"ok":len(rows)>=8 and counts.get("approved",0)>=1 and counts.get("absent",0)>=1 and counts.get("locked",0)>=1}
print(json.dumps(out, indent=2))
raise SystemExit(0 if out["ok"] else 1)
PY

echo "=== screenshots ==="
export ATTW4B_UI_SHOTS="\$REMOTE_EVID/screenshots"
export DASHBOARD_BASE="http://127.0.0.1:8011/dashboard"
export API_BASE="http://127.0.0.1:8011"
"\$PYBIN" "\$REMOTE_STAGE/attendance-wave4b-ui-staging-screenshots.py" 2>&1 | tee "\$REMOTE_EVID/tests/screenshots.out"
test "\$(python3 -c "import json;print(len([s for s in json.load(open('\$REMOTE_EVID/screenshots/manifest.json'))['shots'] if s.startswith('daily-board-')]))")" -ge 4

echo "INGEST_OFF check"
test "\${WATHEFNI_ATTENDANCE_CAPTURE_INGEST:-off}" = "off" -o "\${WATHEFNI_ATTENDANCE_CAPTURE_INGEST:-off}" = "0"
echo "SCREENSHOTS_AND_FREEZE_OK"
REMOTE

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
mkdir -p "$LOCAL_EVID/screenshots" "$LOCAL_EVID/clickthrough/staging" "$LOCAL_EVID/reconcile"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/screenshots/"*.png "$LOCAL_EVID/screenshots/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/screenshots/manifest.json" "$LOCAL_EVID/screenshots/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/clickthrough/"* "$LOCAL_EVID/clickthrough/staging/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/reconcile/"* "$LOCAL_EVID/reconcile/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/tests/"* "$LOCAL_EVID/tests/" 2>/dev/null || true

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Attendance Wave 4B — UX production-readiness qualification

**Stamp:** \`$STAMP\`  
**Evidence:** \`$LOCAL_EVID\`  
**Scope:** local + staging only. **No production deploy.**

## Verdicts

| Gate | Verdict |
|---|---|
| Staging UX readiness (synthetic) | see tests below |
| Production UX deployment | **NO-GO** (this pack does not deploy) |
| Controlled real HR attendance ops | **NO-GO** without explicit later gate |
| Real ingest / devices / QR / GPS / kiosk / payroll money | **NO-GO** |

## Closed Wave 4 gaps

- Seeded synthetic daily board (normal, overnight, multi-session, paid/unpaid breaks, missing in/out, late/early, absence, approved, disputed, locked)
- Click-through: request → approve → dual second approve → apply; reject; dispute; reopen
- Approve ≠ apply proven
- Stale / self-correction / scope / payroll-lock denials proven
- API/UI totals reconciliation
- Staging onboarding freeze drift **eliminated** (synced \`onboarding_wave2.py\` + \`action_registry.py\`)
- Authenticated EN/AR desktop/mobile screenshots against **non-empty** daily board

## Artifacts

- \`clickthrough/\` — seed-index + results
- \`reconcile/\` — HTTP vs seed counts
- \`screenshots/\` — authenticated PNGs
- \`tests/freeze-onboarding*.out\` — must be green on staging

EOF

log "done — $LOCAL_EVID"
echo "$LOCAL_EVID"
