#!/usr/bin/env bash
# Wave 2G — production dark persistence qualify (orchestrates VPS deploy + proofs).
# Keeps CAPTURE_INGEST=off. No customer device. No real punches.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave2g-dark-$STAMP"
REMOTE_STAGE="/tmp/attw2g-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/attendance-wave2g-dark/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,migrate,privacy}
echo "$LOCAL_EVID" > /tmp/attw2g.evid
echo "$STAMP" > /tmp/attw2g.stamp

log() { printf '\n=== %s ===\n' "$*"; }

# Build dashboard for Capture Ops UI
log "build dashboard"
cd "$REPO_ROOT/apps/wathefni-dashboard"
npm run build >/dev/null
rsync -a --delete dist/ "$LOCAL_EVID/sources/dashboard-dist/"

log "copy sources locally"
cd "$ORCH_SRC"
FILES=(
  attendance_capture_postgres.py
  attendance_capture_ops.py
  attendance_capture_ops_http.py
  attendance_capture_secrets.py
  attendance_capture_registry.py
  attendance_capture_remediation.py
  attendance_capture_health.py
  attendance_capture_pipeline.py
  attendance_capture_contract.py
  attendance_capture_agent.py
  canary-prod-attendance-wave2g.py
  smoke-test-attendance-capture-wave2f.py
)
for f in "${FILES[@]}"; do cp -a "$f" "$LOCAL_EVID/sources/"; done
cp -a ops/deploy-attendance-wave2g-prod-dark.sh "$LOCAL_EVID/sources/"
cp -a ops/migrate-attendance-capture-wave2g-prod.sh ops/rollback-attendance-capture-wave2g-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/attendance-capture-ops-ui-prod-screenshots.py" "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/attendance-capture-ops-ui-staging-screenshots.py" "$LOCAL_EVID/sources/"

log "local freezes"
ATTW2G_SKIP_FREEZE=0
.venv/bin/python smoke-test-employees360-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-employees360.out" | tail -3
.venv/bin/python smoke-test-onboarding-freeze-regression.py 2>&1 | tee "$LOCAL_EVID/tests/freeze-onboarding.out" | tail -3

log "push stage + deploy"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE/dashboard-dist' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${FILES[@]}" \
    ops/deploy-attendance-wave2g-prod-dark.sh \
    ops/migrate-attendance-capture-wave2g-prod.sh \
    ops/rollback-attendance-capture-wave2g-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$REPO_ROOT/ops/attendance-capture-ops-ui-prod-screenshots.py" "$VPS_HOST:$REMOTE_STAGE/"
rsync -az --delete -e "ssh -o BatchMode=yes" "$REPO_ROOT/apps/wathefni-dashboard/dist/" "$VPS_HOST:$REMOTE_STAGE/dashboard-dist/"

"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-attendance-wave2g-prod-dark.sh'
REMOTE

log "production canary"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
REMOTE_EVID='$REMOTE_EVID'
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
export ATTW2G_RESULTS="\$REMOTE_EVID/canary/qualification.json"
export ATTW2G_EVID="\$REMOTE_EVID"
export ATTW2G_SKIP_FREEZE=1
\$PYBIN canary-prod-attendance-wave2g.py 2>&1 | tee "\$REMOTE_EVID/canary/canary.out"

# HTTP restart proof with authenticated seed (token arg-order fixed)
\$PYBIN - <<'PY' | tee "\$REMOTE_EVID/tests/restart-http-proof.out"
import json, os, sys, time, urllib.request, uuid
sys.path.insert(0, "/opt/wathefni/orchestrator")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
import app
COMPANY="WATHEFNI"
tag=uuid.uuid4().hex[:6]
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""SELECT * FROM dashboard_users WHERE company_code=%s AND status='active' AND role='owner'
                       ORDER BY updated_at DESC NULLS LAST LIMIT 1""", (COMPANY,))
        user=cur.fetchone()
token,_=app.create_dashboard_session(dict(user))

def http(method, path, token, body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(
        f"http://127.0.0.1:8010{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "X-Company-Code": COMPANY, "X-Wathefni-Company": COMPANY, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw=resp.read().decode(); return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:
        raw=exc.read().decode() if hasattr(exc,"read") else str(exc)
        return getattr(exc,"code",None), raw

st, seed = http("POST", "/dashboard/posthire/attendance/capture-ops/seed-synthetic", token, {"tag": f"W2G-RST-{tag}"})
print("SEED", st, seed.get("ok") if isinstance(seed, dict) else seed)
assert st == 200 and isinstance(seed, dict) and seed.get("ok"), seed
st, before = http("GET", "/dashboard/posthire/attendance/capture-ops", token)
assert before.get("store_mode") == "postgres"
sites_before = before.get("counts", {}).get("sites", 0)
open_before = before.get("counts", {}).get("open_remediation", 0)
print("BEFORE", before.get("store_mode"), before.get("counts"))
os.system("systemctl restart wathefni-orchestrator")
for _ in range(90):
    if os.system("curl -sf http://127.0.0.1:8010/health >/dev/null") == 0: break
    time.sleep(1)
token2,_=app.create_dashboard_session(dict(user))
st, after = http("GET", "/dashboard/posthire/attendance/capture-ops", token2)
print("AFTER", after.get("store_mode"), after.get("counts"))
assert after.get("store_mode") == "postgres"
assert after.get("counts", {}).get("sites", 0) >= sites_before
assert after.get("counts", {}).get("open_remediation", 0) >= open_before
print("RESTART_HTTP_PROOF_OK")
PY

# Authenticated UI screenshots
export CAPTURE_UI_SHOTS="\$REMOTE_EVID/ui"
mkdir -p "\$CAPTURE_UI_SHOTS"
\$PYBIN '$REMOTE_STAGE/attendance-capture-ops-ui-prod-screenshots.py' 2>&1 | tee "\$REMOTE_EVID/ui/screenshots.out"

# Zero all capture tables (synthetic cleanup) — FK-safe full wipe of dark lab tables
\$PYBIN - <<'PY' | tee "\$REMOTE_EVID/cleanup/zero-tables.out"
import app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
        tables = [
            "attendance_capture_replay_ledger","attendance_capture_idempotency","attendance_capture_audit_events",
            "attendance_capture_remediation","attendance_capture_quarantine","attendance_capture_mappings",
            "attendance_capture_health_events","attendance_capture_health","attendance_capture_checkpoints",
            "attendance_capture_credentials","attendance_capture_connectors","attendance_capture_devices",
            "attendance_capture_sites",
        ]
        for t in tables:
            cur.execute(f"DELETE FROM {t}")
        counts={}
        for t in tables:
            cur.execute(f"SELECT COUNT(*) AS n FROM {t}")
            counts[t]=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'")
        demo=int(cur.fetchone()["n"])
    conn.commit()
print("counts_after", counts)
print("demo_rows", demo)
assert all(v==0 for v in counts.values()), counts
assert demo==42
print("CLEANUP_ZERO_OK")
PY

# Leak scan
\$PYBIN - <<PY
from pathlib import Path
import json, sys
sys.path.insert(0, "/opt/wathefni/orchestrator")
from attendance_capture_secrets import scan_paths, qualify_or_block
evid = Path("$REMOTE_EVID")
q = qualify_or_block(scan_paths([evid]))
(evid / "privacy" / "leak-scan.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
print("LEAK_SCAN", {"ok": q["ok"], "blocked": q.get("blocked"), "files": q.get("files_scanned")})
sys.exit(0 if q["ok"] else 1)
PY

# Rollback + redeploy proof
BACKUP=\$(cat \$REMOTE_EVID/backup/BACKUP_PATH.txt)
echo "ROLLBACK_PATH=\$BACKUP"
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP" 2>&1 | tee "\$REMOTE_EVID/rollback/rollback.out"
# Confirm store memory / schema dropped
\$PYBIN - <<'PY' | tee "\$REMOTE_EVID/rollback/post-rollback-store.json"
import json, os, sys, subprocess
sys.path.insert(0,"/opt/wathefni/orchestrator")
pid=subprocess.check_output(["systemctl","show","-p","MainPID","--value","wathefni-orchestrator"], text=True).strip()
with open(f"/proc/{pid}/environ","rb") as f:
    for item in f.read().split(b"\0"):
        if b"=" in item and item.startswith(b"WATHEFNI_"):
            k,v=item.decode().split("=",1)
            os.environ[k]=v
import attendance_capture_ops as ops
ops.reset_capture_ops_for_tests()
import app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('attendance_capture_sites') AS r")
        present=cur.fetchone()["r"]
print(json.dumps({"store_mode": ops.capture_store_mode(), "capture_store_env": os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_STORE"), "sites_table": present}, indent=2))
PY

# Redeploy
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-attendance-wave2g-prod-dark.sh' 2>&1 | tee "\$REMOTE_EVID/rollback/redeploy.out"

# Quick post-redeploy canary subset + zero cleanup
cd \$ORCH
export ATTW2G_RESULTS="\$REMOTE_EVID/canary/qualification-after-redeploy.json"
export ATTW2G_EVID="\$REMOTE_EVID"
export ATTW2G_SKIP_FREEZE=1
\$PYBIN canary-prod-attendance-wave2g.py 2>&1 | tee "\$REMOTE_EVID/canary/canary-after-redeploy.out"
\$PYBIN - <<'PY' | tee "\$REMOTE_EVID/cleanup/zero-tables-final.out"
import app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('wathefni.allow_capture_cleanup','1', true)")
        tables=["attendance_capture_replay_ledger","attendance_capture_idempotency","attendance_capture_audit_events","attendance_capture_remediation","attendance_capture_quarantine","attendance_capture_mappings","attendance_capture_health_events","attendance_capture_health","attendance_capture_checkpoints","attendance_capture_credentials","attendance_capture_connectors","attendance_capture_devices","attendance_capture_sites"]
        for t in tables:
            cur.execute(f"DELETE FROM {t}")
        counts={}
        for t in tables:
            cur.execute(f"SELECT COUNT(*) AS n FROM {t}"); counts[t]=int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM attendance_records WHERE company_code='WATHEFNI'"); demo=int(cur.fetchone()["n"])
    conn.commit()
assert all(v==0 for v in counts.values()), counts
assert demo==42
print("FINAL_CLEANUP_ZERO_OK", counts, "demo", demo)
PY
echo REMOTE_EVID=\$REMOTE_EVID
REMOTE

log "fetch remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/preflight" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/verify" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/flags" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/canary" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/tests" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/schema" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/backup" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/cleanup" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/rollback" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/privacy" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/ui" "$LOCAL_EVID/screenshots-remote/" || true
mkdir -p "$LOCAL_EVID/screenshots"
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/ui/"*.png "$LOCAL_EVID/screenshots/" 2>/dev/null || true
"${SCP[@]}" "$VPS_HOST:$REMOTE_EVID/ui/manifest.json" "$LOCAL_EVID/screenshots/" 2>/dev/null || true

log "local leak scan"
cd "$ORCH_SRC"
.venv/bin/python - <<PY
from attendance_capture_secrets import scan_paths, qualify_or_block
import json
from pathlib import Path
evid = Path("$LOCAL_EVID")
q = qualify_or_block(scan_paths([evid]))
(evid / "privacy" / "leak-scan-local.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
print(json.dumps({"ok": q["ok"], "blocked": q.get("blocked"), "files": q.get("files_scanned")}, indent=2))
raise SystemExit(0 if q["ok"] else 1)
PY

echo "EVIDENCE=$LOCAL_EVID"
echo "STAMP=$STAMP"
echo "REMOTE_EVID=$REMOTE_EVID"
