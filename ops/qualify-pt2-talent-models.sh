#!/usr/bin/env bash
# PT2 — Configurable Talent Models + WHY Graph qualification.
# Does not begin PT3 until this script exits 0. Does not resume R7.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"
MOBILE_SRC="$REPO_ROOT/apps/wathefni-employee-mobile"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/pt2-talent-models-$STAMP"
REMOTE_STAGE="/tmp/pt2-talent-models-stage"
STG=/opt/wathefni/staging/orchestrator

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live,dashboard,mobile,inventories}
export LOCAL_EVID
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  talent_surfaces.py
  talent_http.py
  talent_profile_c5.py
  talent_succession_c6.py
  talent_evidence_index_pt1.py
  talent_models_pt2.py
  okr_operating_pt1.py
  performance_goals_c1.py
  smoke-test-pt2-talent-models.py
  smoke-test-pt2-talent-models-db.py
  smoke-test-pt1-okr-evidence.py
  smoke-test-r5c-talent-surface.py
  smoke-test-wave4-product-acceptance.py
)

log "1/7 dashboard vitest + employee composition"
cd "$DASH_SRC"
if [[ -x "$DASH_SRC/node_modules/.bin/vitest" ]]; then
  npx vitest run \
    src/lib/workspaceCapability.test.ts \
    src/lib/dashboardNavigation.test.ts \
    src/lib/moduleWorkspace.test.ts \
    src/pages/shared/dataState.test.tsx \
    2>&1 | tee "$LOCAL_EVID/dashboard/named.out"
  npx vitest run 2>&1 | tee "$LOCAL_EVID/dashboard/full.out"
else
  echo "vitest missing" | tee "$LOCAL_EVID/dashboard/named.out"
  exit 1
fi
cd "$MOBILE_SRC"
node scripts/composition-shapes-test.js 2>&1 | tee "$LOCAL_EVID/mobile/composition.out"

log "2/7 local PT2 + PT1 predecessor + Wave 4 C5/C6 contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-pt2-talent-models.py 2>&1 | tee "$LOCAL_EVID/tests/pt2-unit.out"
"$PY" smoke-test-pt1-okr-evidence.py 2>&1 | tee "$LOCAL_EVID/regression/pt1-unit.out"
"$PY" smoke-test-r5c-talent-surface.py 2>&1 | tee "$LOCAL_EVID/regression/r5c-talent-surface.out"
"$PY" smoke-test-wave4-product-acceptance.py 2>&1 | tee "$LOCAL_EVID/regression/wave4-product-acceptance.out"

log "3/7 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/" 2>/dev/null || true; done
cp -a "$DASH_SRC/src/posthire/TalentWorkspace.tsx" "$LOCAL_EVID/dashboard/TalentWorkspace.tsx"

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/talent_models_pt2.py'
python3 -m py_compile '$STG/talent_models_pt2.py' '$STG/talent_http.py' '$STG/talent_surfaces.py'
echo STAGING_COPY_OK
REMOTE

staging_py() {
  local script="$1" out="$2"
  "${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$out"
set -euo pipefail
STG=$STG
PROD=/opt/wathefni/orchestrator
PYBIN=\$PROD/.venv/bin/python
export PYTHONPATH="\$STG:\$PROD\${PYTHONPATH:+:\$PYTHONPATH}"
cd "\$STG"
export WATHEFNI_ENV=staging
export WATHEFNI_DATA_SAFETY_ACK=non-production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_DELIVERY_MODE=dry_run
set -a; source "\$WATHEFNI_POSTGRES_ENV"; set +a
unset DATABASE_URL || true
"\$PYBIN" "$script"
echo STAGING_RC=\$?
REMOTE
}

log "4/7 staging DB journeys"
staging_py smoke-test-pt2-talent-models-db.py "$LOCAL_EVID/tests/staging-db.out"

log "5/7 live deployed staging service"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
S=000
for i in $(seq 1 15); do
  sleep 8
  S=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/health)
  [ "$S" = "200" ] && break
done
echo "staging_health=$S"
[ "$S" = "200" ] || { echo "LIVE_SERVICE 0 passed, 1 failed"; exit 0; }

python3 - <<'PY'
import urllib.request, urllib.error
P = F = 0
def ck(label, cond, detail=None):
    global P, F
    if cond:
        P += 1
        print(f"      PASS  {label}")
    else:
        F += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")

def fetch(path, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:8011" + path, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")

status, _ = fetch("/health")
ck("live health", status == 200, status)
for path in (
    "/dashboard/posthire/talent/models",
    "/dashboard/posthire/talent/models/classifications",
    "/dashboard/posthire/talent/models/why/x",
    "/dashboard/posthire/talent/workspace",
):
    status, _ = fetch(path)
    ck(f"live {path} not public", status in (401, 403, 503), status)
print(f"    LIVE_SERVICE {P} passed, {F} failed")
PY
REMOTE

log "6/7 inventories"
cd "$REPO_ROOT"
python3 - <<PY
from pathlib import Path
evid = Path("$LOCAL_EVID")
inv = evid / "inventories"
inv.mkdir(parents=True, exist_ok=True)
th = Path("wathefni-orchestrator/talent_http.py").read_text(encoding="utf-8")
src = Path("wathefni-orchestrator/talent_models_pt2.py").read_text(encoding="utf-8")
routes = [line.strip() for line in th.splitlines() if "_bind(" in line or "@app.get" in line or "@app.post" in line]
(inv / "api-inventory.md").write_text(
    "# PT2 API inventory\\n\\n" + "\\n".join(f"- {r}" for r in routes) + "\\n",
    encoding="utf-8",
)
(inv / "authority.md").write_text(
    "# PT2 authority\\n\\n- overlay: talent_models_pt2\\n- C5/C6 unchanged\\n- published versions immutable\\n",
    encoding="utf-8",
)
print("INVENTORIES_OK", len(routes), "immutable" if "published_version_immutable" in src else "MISSING_IMMUTABLE")
PY

log "7/7 verdict"
DASH_OK=NO
if grep -qE 'Test Files[[:space:]]+[0-9]+ passed' "$LOCAL_EVID/dashboard/full.out" \
   && ! grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/full.out"; then DASH_OK=YES; fi
if grep -qE '[1-9][0-9]* failed' "$LOCAL_EVID/dashboard/named.out"; then DASH_OK=NO; fi

MOBILE_OK=NO
if grep -qE 'PASS employee app composition|passed' "$LOCAL_EVID/mobile/composition.out" \
   && ! grep -qE '^FAIL  |^[[:space:]]*FAIL  ' "$LOCAL_EVID/mobile/composition.out"; then
  MOBILE_OK=YES
fi

UNIT_OK=NO
grep -q 'PT2_TALENT_MODELS_WHY_UNIT_PASS' "$LOCAL_EVID/tests/pt2-unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/pt2-unit.out" && UNIT_OK=YES

PRED_OK=NO
grep -q 'PT1_OKR_EVIDENCE_UNIT_PASS' "$LOCAL_EVID/regression/pt1-unit.out" && PRED_OK=YES

WAVE_OK=NO
if grep -q 'R5C_TALENT_SURFACE_UNIT_PASS' "$LOCAL_EVID/regression/r5c-talent-surface.out" \
   && grep -q 'WAVE4_PRODUCT_UNIT_PASS' "$LOCAL_EVID/regression/wave4-product-acceptance.out" \
   && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/regression/r5c-talent-surface.out" \
   && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/regression/wave4-product-acceptance.out"; then
  WAVE_OK=YES
fi

DB_OK=NO
grep -q 'PT2_TALENT_MODELS_WHY_DB_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES

DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES

VERDICT=FAIL
if [[ "$DASH_OK" == YES && "$MOBILE_OK" == YES && "$UNIT_OK" == YES && "$PRED_OK" == YES && "$WAVE_OK" == YES && "$DB_OK" == YES && "$LIVE_OK" == YES && "$DEPLOY_OK" == YES ]]; then
  VERDICT='PT2_TALENT_MODELS_WHY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# PT2 — Configurable Talent Models + WHY Graph

- Stamp: $STAMP
- Dashboard vitest: $DASH_OK
- Employee composition: $MOBILE_OK
- Local PT2 unit: $UNIT_OK
- PT1 predecessor unit: $PRED_OK
- Wave 4 C5/C6 + R5C contracts: $WAVE_OK
- Staging deploy: $DEPLOY_OK
- Staging DB journeys: $DB_OK
- Live deployed staging service: $LIVE_OK
- Verdict: **$VERDICT**

Scope: PT2 overlay only. Derived High Potential signal ≠ designated HiPo.
Do not begin PT3 unless this verdict is FULL_PASS. Do not resume R7.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" != FAIL ]]
