#!/usr/bin/env bash
# Production Readiness R2 — Security & Secret Hardening qualification.
#
# Proves the R1 security blocker set (P0-2, P0-3, P0-4, P0-5, P1-22) against an
# isolated staging environment, three ways:
#
#   1. local unit contracts        — pure logic, no database
#   2. staging database negatives  — real route handlers, two isolated tenants
#   3. live deployed service       — the restarted staging process over HTTP
#
# Global posture is unchanged: break-glass stays disabled, Wave 4/6 stay off.
# FULL_PASS here does not authorise production rollout.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/production-readiness-r2-security-$STAMP"
REMOTE_STAGE="/tmp/r2-security-stage"
STG=/opt/wathefni/staging/orchestrator
BASE=http://127.0.0.1:8011

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,regression,live}
log() { printf '\n=== %s ===\n' "$*"; }

if [[ -x "$ORCH_SRC/.venv/bin/python" ]]; then PY="$ORCH_SRC/.venv/bin/python"; else PY="$(command -v python3)"; fi

FILES=(
  app.py
  security_rate_limit.py
  security_link_secrets.py
  security_internal_authority.py
  smoke-test-r2-security.py
  smoke-test-r2-security-db.py
  smoke-test-browser-assessment.py
)

log "1/6 local unit contracts"
cd "$ORCH_SRC"
"$PY" smoke-test-r2-security.py 2>&1 | tee "$LOCAL_EVID/tests/unit.out"

log "2/6 stage sources"
for f in "${FILES[@]}"; do cp -a "$ORCH_SRC/$f" "$LOCAL_EVID/sources/"; done
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R2_SECURITY_FULL_PASS.md" "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$REPO_ROOT/ops/PRODUCTION_READINESS_R2_SECURITY_FREEZE_AMENDMENT.md" "$LOCAL_EVID/docs/" 2>/dev/null || true

"${SSH[@]}" "mkdir -p '$REMOTE_STAGE'"
# app.py is ~3.6 MB on a slow uplink; rsync sends only the delta on reruns.
rsync -az --compress-level=9 -e "ssh -o BatchMode=yes -o ConnectTimeout=30" \
  "${FILES[@]/#/$ORCH_SRC/}" "$VPS_HOST:$REMOTE_STAGE/"

"${SSH[@]}" "bash -s" <<REMOTE 2>&1 | tee "$LOCAL_EVID/tests/staging-deploy.out"
set -euo pipefail
cp -a '$REMOTE_STAGE'/*.py '$STG/'
test -f '$STG/security_rate_limit.py'
test -f '$STG/security_internal_authority.py'
# Break-glass must not be globally enabled by a deploy.
if grep -Rls 'WATHEFNI_BREAK_GLASS_ENABLED=1' /etc/systemd/system/wathefni-orchestrator-staging.service.d 2>/dev/null; then
  echo UNEXPECTED_BREAK_GLASS_ENABLED; exit 1
fi
echo STAGING_COPY_OK_BREAK_GLASS_OFF
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

log "3/6 staging database negative paths (two isolated tenants)"
staging_py smoke-test-r2-security-db.py "$LOCAL_EVID/tests/staging-db.out"

log "4/6 live deployed service"
"${SSH[@]}" "bash -s" <<'REMOTE' 2>&1 | tee "$LOCAL_EVID/live/live-service.out"
set -uo pipefail
SEC=/root/.openclaw/secrets/r2-security.staging.env
if [[ ! -f "$SEC" ]]; then
  umask 077
  A=$(openssl rand -hex 20); B2=$(openssl rand -hex 20)
  {
    echo "WATHEFNI_ASSESSMENT_LINK_SECRET=$(openssl rand -hex 32)"
    echo "WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET=$(openssl rand -hex 32)"
    echo "WATHEFNI_INTERNAL_TOKEN=$(openssl rand -hex 24)"
    echo "WATHEFNI_INTERNAL_WORKER_TOKEN=$(openssl rand -hex 24)"
    echo "WATHEFNI_BREAK_GLASS_TOKEN=$(openssl rand -hex 24)"
    # JSON values must be quoted: unquoted braces+commas are mangled by shell
    # brace expansion when the file is sourced.
    printf 'WATHEFNI_INTERNAL_TENANT_TOKENS=%s\n' "'{\"R2STGALPHA\":\"$A\",\"R2STGBETA\":\"$B2\"}'"
  } > "$SEC"
  chmod 600 "$SEC"
fi
D=/etc/systemd/system/wathefni-orchestrator-staging.service.d
mkdir -p "$D"
cat > "$D/zzzzz-r2-security.conf" <<CONF
[Service]
# R2: dedicated link signing secrets, internal principals, dedicated worker
# secret, break-glass secret. Break-glass itself stays DISABLED.
EnvironmentFile=-/root/.openclaw/secrets/r2-security.staging.env
CONF
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

set -a; source "$SEC"; set +a
B=http://127.0.0.1:8011
ALPHA_TOK=$(python3 -c "import json,os;print(json.loads(os.environ['WATHEFNI_INTERNAL_TENANT_TOKENS'])['R2STGALPHA'])")
P=0; F=0
ck(){ if [ "$2" = "$3" ]; then P=$((P+1)); echo "      PASS  $1"; else F=$((F+1)); echo "      FAIL  $1 :: got=$2 want=$3"; fi; }
code(){ curl -s -o /tmp/r2body -w "%{http_code}" "$@"; }

echo "    P0-2 public link signing"
READY=$(curl -s $B/ready)
ck "/ready reports public link capabilities available" \
   "$(echo "$READY" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("public_link_capabilities_available"))')" "True"
if echo "$READY" | grep -q "$WATHEFNI_VIDEO_INTERVIEW_LINK_SECRET"; then ck "/ready exposes no secret" leaked clean; else ck "/ready exposes no secret" clean clean; fi
IV=$(python3 -c "import uuid;print(uuid.uuid4())")
FORGED=$(python3 - "$IV" <<'PY'
import base64, hashlib, hmac, sys, time
iv = sys.argv[1]; exp = int(time.time()) + 600; payload = f"{iv}:{exp}"
sig = hmac.new(b"wathefni-video-interview-dev-secret", payload.encode(), hashlib.sha256).digest()
print(base64.urlsafe_b64encode(f"{payload}:".encode() + sig).decode().rstrip("="))
PY
)
ck "link forged with the removed dev constant is refused" "$(code "$B/video-interview/$IV/state?token=$FORGED")" 403

echo "    P0-4 internal worker endpoint from loopback"
ck "no token from 127.0.0.1" "$(code -X POST $B/internal/video-interviews/process-transcripts)" 403
ck "wrong worker token" "$(code -X POST -H "X-Internal-Token: nope" $B/internal/video-interviews/process-transcripts)" 403
ck "shared platform token is not worker authority" "$(code -X POST -H "X-Internal-Token: $WATHEFNI_INTERNAL_TOKEN" $B/internal/video-interviews/process-transcripts)" 403
WRC=$(code -X POST -H "X-Internal-Token: $WATHEFNI_INTERNAL_WORKER_TOKEN" $B/internal/video-interviews/process-transcripts)
if [ "$WRC" != "403" ]; then ck "dedicated worker token accepted" ok ok; else ck "dedicated worker token accepted" denied accepted; fi

echo "    P0-5 internal principals and tenant scope"
ck "unknown internal token" "$(code -H "X-Internal-Token: guessed" "$B/orchestrator/audit/turns")" 401
ck "platform token cannot do an unscoped read" "$(code -H "X-Internal-Token: $WATHEFNI_INTERNAL_TOKEN" "$B/orchestrator/audit/turns")" 400
ck "platform token with an explicit company" "$(code -H "X-Internal-Token: $WATHEFNI_INTERNAL_TOKEN" "$B/orchestrator/audit/turns?company_code=R2STGALPHA")" 200
ck "tenant token reading another tenant" "$(code -H "X-Internal-Token: $ALPHA_TOK" "$B/orchestrator/audit/turns?company_code=R2STGBETA")" 403
ck "tenant token reading itself" "$(code -H "X-Internal-Token: $ALPHA_TOK" "$B/orchestrator/audit/turns")" 200
ck "destructive sweep with only the internal token" "$(code -X POST -H "X-Internal-Token: $WATHEFNI_INTERNAL_TOKEN" "$B/orchestrator/debug/intake-quarantine/sweep?apply=true")" 403
if grep -q break_glass_disabled /tmp/r2body; then ck "break-glass disabled by default in a real deployment" yes yes; else ck "break-glass disabled by default in a real deployment" no yes; fi

echo "    P0-3 / P1-22 throttling on the deployed process"
LOGIN=0
for i in $(seq 1 14); do
  RC=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
       -d '{"company_code":"R2LIVE","email":"live@r2.test","password":"wrong-password"}' $B/dashboard/auth/login)
  [ "$RC" = "429" ] && { LOGIN=1; break; }
done
ck "dashboard login brute force trips the limiter" "$LOGIN" 1
GT=$(python3 -c "import uuid;print(uuid.uuid4().hex)")
CAL=0
for i in $(seq 1 60); do
  RC=$(curl -s -o /dev/null -w "%{http_code}" "$B/calendar/guest/$GT/state")
  [ "$RC" = "429" ] && { CAL=1; break; }
done
ck "calendar guest-token throttle trips" "$CAL" 1

echo "    LIVE_SERVICE $P passed, $F failed"
REMOTE

log "5/6 regressions"
REG_OK=YES
set +e
for t in smoke-test-wave6-product-acceptance smoke-test-job-architecture-c1 smoke-test-learning-development-c2 \
         smoke-test-benefits-administration-c3 smoke-test-employee-relations-c4 smoke-test-engagement-c5 \
         smoke-test-compensation-planning-c6 smoke-test-workforce-planning-c7 smoke-test-wave5-product-acceptance \
         smoke-test-wave4-product-acceptance smoke-test-wave3-product-acceptance smoke-test-wave2-product-acceptance \
         smoke-test-wave1-product-acceptance; do
  "$PY" "$ORCH_SRC/$t.py" >"$LOCAL_EVID/regression/$t.out" 2>&1
  echo "$t rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
done
"$PY" -m unittest test_interaction_authority_contracts >"$LOCAL_EVID/regression/interaction-authority-contracts.out" 2>&1
echo "interaction_authority_contracts rc=$?" >> "$LOCAL_EVID/regression/summary.txt"
set -e
staging_py smoke-test-internal-auth.py "$LOCAL_EVID/regression/internal-auth-staging.out"
for f in "$LOCAL_EVID"/regression/smoke-test-*.out; do
  grep -qE '^[[:space:]]*FAIL  |Traceback' "$f" && REG_OK=NO
  grep -qE '[0-9]+ passed' "$f" || REG_OK=NO
done
grep -q 'OK' "$LOCAL_EVID/regression/interaction-authority-contracts.out" || REG_OK=NO
grep -q 'ALL CHECKS PASSED' "$LOCAL_EVID/regression/internal-auth-staging.out" || REG_OK=NO

log "6/6 verdict"
UNIT_OK=NO
grep -q 'R2_SECURITY_UNIT_PASS' "$LOCAL_EVID/tests/unit.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/unit.out" && UNIT_OK=YES

DB_OK=NO
grep -q 'R2_SECURITY_FULL_PASS' "$LOCAL_EVID/tests/staging-db.out" \
  && grep -qE '[0-9]+ passed, 0 failed' "$LOCAL_EVID/tests/staging-db.out" \
  && ! grep -qE '^[[:space:]]*FAIL  |Traceback' "$LOCAL_EVID/tests/staging-db.out" && DB_OK=YES

LIVE_OK=NO
grep -qE 'LIVE_SERVICE [0-9]+ passed, 0 failed' "$LOCAL_EVID/live/live-service.out" \
  && ! grep -qE '^[[:space:]]*FAIL  ' "$LOCAL_EVID/live/live-service.out" && LIVE_OK=YES

DEPLOY_OK=NO
grep -q 'STAGING_COPY_OK_BREAK_GLASS_OFF' "$LOCAL_EVID/tests/staging-deploy.out" && DEPLOY_OK=YES

VERDICT=FAIL
if [[ "$UNIT_OK" == YES && "$DB_OK" == YES && "$LIVE_OK" == YES && "$REG_OK" == YES && "$DEPLOY_OK" == YES ]]; then
  VERDICT='PRODUCTION_READINESS_R2_SECURITY_FULL_PASS'
fi

cat > "$LOCAL_EVID/REPORT.md" <<EOF
# Production Readiness R2 — Security & Secret Hardening

- Stamp: $STAMP
- Local unit contracts: $UNIT_OK
- Staging deploy (break-glass off): $DEPLOY_OK
- Staging DB negative paths (two isolated tenants): $DB_OK
- Live deployed staging service: $LIVE_OK
- Waves 1–6 + authority contract + internal-auth regressions: $REG_OK
- Verdict: **$VERDICT**

Scope: R1 blockers P0-2, P0-3, P0-4, P0-5, P1-22 only.
Break-glass remains disabled by default. Wave 4/6 remain global-OFF and company-gated.
FULL_PASS is not authorisation for production rollout; R3 Production Data Safety is next.
EOF

echo
echo "EVIDENCE=$LOCAL_EVID"
echo "VERDICT=$VERDICT"
[[ "$VERDICT" == "PRODUCTION_READINESS_R2_SECURITY_FULL_PASS" ]]
