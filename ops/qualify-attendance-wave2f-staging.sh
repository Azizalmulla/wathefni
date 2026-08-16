#!/usr/bin/env bash
# Wave 2F — staging-only durable capture-ops qualify (NO production, NO real device).
# Migrates capture schema on wathefni_staging, enables CAPTURE_STORE=postgres on staging
# orchestrator only, proves restart/concurrency via smoke, captures authenticated UI shots.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/attendance-wave2f-durable-$STAMP"
REMOTE_STAGE="/tmp/attw2f-stage-$STAMP"
REMOTE_EVID="/opt/wathefni/staging-evidence/attendance-wave2f-durable-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,screenshots,migrate}
echo "$LOCAL_EVID" > /tmp/attw2f.evid
echo "$STAMP" > /tmp/attw2f.stamp

FILES=(
  attendance_capture_postgres.py
  attendance_capture_ops.py
  attendance_capture_ops_http.py
  attendance_capture_secrets.py
  attendance_capture_registry.py
  attendance_capture_remediation.py
  attendance_capture_health.py
  attendance_capture_compat.py
  attendance_capture_contract.py
  attendance_capture_biotime.py
  attendance_capture_csv.py
  attendance_capture_agent.py
  attendance_capture_pipeline.py
  attendance_capture_lab_biotime.py
  attendance_authority_wave1.py
  attendance_authority_postgres.py
  smoke-test-attendance-capture-wave2f.py
)

MIGRATE_FILES=(
  ops/migrate-attendance-capture-wave2f.sh
  ops/rollback-attendance-capture-wave2f.sh
)

log() { printf '\n=== %s ===\n' "$*"; }

log "local structural + optional smoke"
cd "$ORCH_SRC"
.venv/bin/python - <<'PY' | tee "$LOCAL_EVID/tests/qualify-local-import.out"
import attendance_capture_postgres as p
import attendance_capture_ops as o
assert "attendance_capture_sites" in p.WAVE2F_SCHEMA_DDL
assert "WAVE2F_ROLLBACK_DDL" in dir(p)
print("IMPORT_OK", p.CAPTURE_OPS_VERSION)
print("store_default", o.capture_store_mode())
PY
for f in "${FILES[@]}"; do
  cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true
done
cp -a "$ORCH_SRC/ops/migrate-attendance-capture-wave2f.sh" "$LOCAL_EVID/migrate/"
cp -a "$ORCH_SRC/ops/rollback-attendance-capture-wave2f.sh" "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/attendance-capture-ops-ui-staging-screenshots.py" "$LOCAL_EVID/sources/" 2>/dev/null || true

# Optional local postgres smoke (skip if no DB binding)
if [[ -n "${WATHEFNI_POSTGRES_ENV:-}" ]] || [[ -n "${WATHEFNI_DATABASE_URL:-}" ]]; then
  ATTW2F_RESULTS_PATH="$LOCAL_EVID/tests/qualification-local.json" \
    WATHEFNI_ENV="${WATHEFNI_ENV:-local}" \
    ATTW2F_SKIP_FREEZE="${ATTW2F_SKIP_FREEZE:-0}" \
    .venv/bin/python smoke-test-attendance-capture-wave2f.py 2>&1 | tee "$LOCAL_EVID/tests/qualify-local.out" || true
else
  echo "LOCAL_SMOKE_SKIPPED_NO_DB" | tee "$LOCAL_EVID/tests/qualify-local.out"
fi

log "push to staging"
"${SSH[@]}" "mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID' '$STAGING_ORCH' '$STAGING_ORCH/ops'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" "${FILES[@]}" "$VPS_HOST:$REMOTE_STAGE/"
  "${SCP[@]}" ops/migrate-attendance-capture-wave2f.sh ops/rollback-attendance-capture-wave2f.sh "$VPS_HOST:$REMOTE_STAGE/"
)
"${SCP[@]}" "$REPO_ROOT/ops/attendance-capture-ops-ui-staging-screenshots.py" "$VPS_HOST:$REMOTE_STAGE/" 2>/dev/null || true

log "staging migrate + restart + smoke + screenshots"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/qualify-staging.out"
set -euo pipefail
STAGING_ORCH='$STAGING_ORCH'
REMOTE_STAGE='$REMOTE_STAGE'
REMOTE_EVID='$REMOTE_EVID'
mkdir -p "\$REMOTE_EVID"/{tests,docs,screenshots,migrate}
cp -a "\$REMOTE_STAGE"/*.py "\$STAGING_ORCH/"
cp -a "\$REMOTE_STAGE"/migrate-attendance-capture-wave2f.sh "\$STAGING_ORCH/ops/" 2>/dev/null || mkdir -p "\$STAGING_ORCH/ops" && cp -a "\$REMOTE_STAGE"/migrate-attendance-capture-wave2f.sh "\$STAGING_ORCH/ops/"
cp -a "\$REMOTE_STAGE"/rollback-attendance-capture-wave2f.sh "\$STAGING_ORCH/ops/"
cp -a "\$REMOTE_STAGE"/migrate-*.sh "\$REMOTE_EVID/migrate/" 2>/dev/null || true
cp -a "\$REMOTE_STAGE"/rollback-*.sh "\$REMOTE_EVID/migrate/" 2>/dev/null || true

# Staging-only systemd drop-in for durable store (never production)
DROPIN=/etc/systemd/system/wathefni-orchestrator-staging.service.d/attendance-capture-wave2f.conf
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > "\$DROPIN" <<'EOF'
[Service]
Environment=WATHEFNI_ATTENDANCE_CAPTURE_OPS=on
Environment=WATHEFNI_ATTENDANCE_CAPTURE_OPS_COMPANIES=WATHEFNI,ATTW2F,ATTW2FX
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_AUTHORITY=on
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
Environment=WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env
EOF

cd "\$STAGING_ORCH"
export WATHEFNI_ENV=staging
export ACK_DB=wathefni_staging
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
PYBIN=/opt/wathefni/orchestrator/.venv/bin/python
export ORCH_PYTHON="\$PYBIN"
chmod +x ops/migrate-attendance-capture-wave2f.sh ops/rollback-attendance-capture-wave2f.sh

# Ensure Wave 2F schema hook exists in staging app.py (additive; no full app replace).
\$PYBIN - <<'PATCH'
from pathlib import Path
p = Path("/opt/wathefni/staging/orchestrator/app.py")
text = p.read_text(encoding="utf-8")
needle = "attendance_capture_postgres"
if needle not in text:
    old = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
        conn.commit()"""
    new = """            _attendance_authority_pg.ensure_attendance_authority_postgres_schema(cur)
            # Wave 2F additive capture-ops tables (dark; activated by CAPTURE_STORE=postgres).
            try:
                import attendance_capture_postgres as _attendance_capture_pg

                _attendance_capture_pg.ensure_attendance_capture_postgres_schema(cur)
            except Exception:
                pass
        conn.commit()"""
    if old not in text:
        raise SystemExit("app.py schema hook site not found")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("APP_PATCHED_WAVE2F_SCHEMA")
else:
    print("APP_ALREADY_HAS_WAVE2F_SCHEMA")
PATCH

ORCH_PYTHON="\$PYBIN" bash ops/migrate-attendance-capture-wave2f.sh 2>&1 | tee "\$REMOTE_EVID/tests/migrate.out"

systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
for i in \$(seq 1 90); do
  if curl -sf http://127.0.0.1:8011/health >/dev/null; then break; fi
  sleep 1
done
curl -sf http://127.0.0.1:8011/health | tee "\$REMOTE_EVID/tests/health-after-restart.json"

export ATTW2F_RESULTS_PATH="\$REMOTE_EVID/tests/qualification-staging.json"
export ATTW2F_SKIP_FREEZE=1
\$PYBIN smoke-test-attendance-capture-wave2f.py 2>&1 | tee "\$REMOTE_EVID/tests/qualify-staging-smoke.out"

# Host/API restart survival: seed via HTTP, restart service, re-read
\$PYBIN - <<'PY' | tee "\$REMOTE_EVID/tests/restart-http-proof.out"
import json, os, sys, time, urllib.request, uuid
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")
import app

COMPANY = "WATHEFNI"
tag = uuid.uuid4().hex[:6]

with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            \"\"\"SELECT * FROM dashboard_users WHERE company_code=%s AND status='active' AND role='owner'
               ORDER BY updated_at DESC NULLS LAST LIMIT 1\"\"\",
            (COMPANY,),
        )
        user = cur.fetchone()
token, _ = app.create_dashboard_session(dict(user))

def http(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:8011{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Wathefni-Company": COMPANY,
            "X-Company-Code": COMPANY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except Exception as exc:
        if hasattr(exc, "code"):
            raw = exc.read().decode() if hasattr(exc, "read") else ""
            try:
                return int(exc.code), json.loads(raw) if raw else {"raw": raw}
            except Exception:
                return int(exc.code), {"raw": raw[:500]}
        raise

st, seed = http("POST", "/dashboard/posthire/attendance/capture-ops/seed-synthetic", {"tag": f"W2F-RST-{tag}"})
print("SEED", st, {k: seed.get(k) for k in ("ok", "error", "ingest_enabled")})
assert st == 200 and seed.get("ok"), seed
st, before = http("GET", "/dashboard/posthire/attendance/capture-ops")
print("BEFORE", st, before.get("store_mode"), before.get("counts"))
assert before.get("store_mode") == "postgres"
sites_before = before.get("counts", {}).get("sites", 0)
open_before = before.get("counts", {}).get("open_remediation", 0)

os.system("systemctl restart wathefni-orchestrator-staging.service")
for _ in range(90):
    if os.system("curl -sf http://127.0.0.1:8011/health >/dev/null") == 0:
        break
    time.sleep(1)

st, after = http("GET", "/dashboard/posthire/attendance/capture-ops")
print("AFTER", st, after.get("store_mode"), after.get("counts"))
assert after.get("store_mode") == "postgres"
assert after.get("counts", {}).get("sites", 0) >= sites_before
assert after.get("counts", {}).get("open_remediation", 0) >= open_before
print("RESTART_HTTP_PROOF_OK")
PY

# Authenticated screenshots
export CAPTURE_UI_SHOTS="\$REMOTE_EVID/screenshots"
\$PYBIN "\$REMOTE_STAGE/attendance-capture-ops-ui-staging-screenshots.py" 2>&1 | tee "\$REMOTE_EVID/tests/screenshots.out" || true

# Leak scan
\$PYBIN - <<PY
from pathlib import Path
import json, sys
sys.path.insert(0, "/opt/wathefni/staging/orchestrator")
from attendance_capture_secrets import scan_paths, qualify_or_block
evid = Path("$REMOTE_EVID")
scan = scan_paths([evid])
q = qualify_or_block(scan)
(evid / "tests" / "leak-scan.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
print("LEAK_SCAN", json.dumps({"ok": q["ok"], "blocked": q.get("blocked"), "files": q.get("files_scanned")}))
sys.exit(0 if q["ok"] else 1)
PY

sha256sum "\$STAGING_ORCH"/attendance_capture_postgres.py \\
  "\$STAGING_ORCH"/attendance_capture_ops.py \\
  "\$STAGING_ORCH"/smoke-test-attendance-capture-wave2f.py | tee "\$REMOTE_EVID/tests/deployed.sha256"
echo "REMOTE_EVID=\$REMOTE_EVID"
REMOTE

log "fetch remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/tests" "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/screenshots" "$LOCAL_EVID/" || true
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/migrate" "$LOCAL_EVID/remote/" || true

log "local leak scan"
cd "$ORCH_SRC"
.venv/bin/python - <<PY
from attendance_capture_secrets import scan_paths, qualify_or_block
import json
from pathlib import Path
evid = Path("$LOCAL_EVID")
scan = scan_paths([evid])
q = qualify_or_block(scan)
(evid / "tests" / "leak-scan-local.json").write_text(json.dumps(q, indent=2), encoding="utf-8")
print(json.dumps({"ok": q["ok"], "blocked": q.get("blocked")}, indent=2))
raise SystemExit(0 if q["ok"] else 1)
PY

echo "EVIDENCE=$LOCAL_EVID"
echo "STAMP=$STAMP"
