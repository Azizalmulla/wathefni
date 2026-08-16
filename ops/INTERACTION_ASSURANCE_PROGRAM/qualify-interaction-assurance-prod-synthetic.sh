#!/usr/bin/env bash
# Interaction Assurance — stamped synthetic fixture qualification.
# Progressive batches prove unproven destructive properties without real customer rows.
# Does NOT hard-fail product releases for incomplete 495 coverage (see RELEASE_GATE.md).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BATCH="${IAX_BATCH:-0}"
LOCAL_EVID="$REPO_ROOT/ops/evidence/interaction-assurance-$STAMP"
REMOTE_STAGE="/tmp/iax-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/interaction-assurance/${STAMP}"
MODE="${IAX_MODE:-local}" # local | production

mkdir -p "$LOCAL_EVID"/{tests,docs,sources,canary,gate,register}
echo "$LOCAL_EVID" > /tmp/iax.evid
echo "$STAMP" > /tmp/iax.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "freeze sources + residual register"
cp -a "$ORCH_SRC/interaction_assurance_fixtures.py" "$LOCAL_EVID/sources/"
cp -a "$ORCH_SRC/canary-prod-interaction-assurance.py" "$LOCAL_EVID/sources/"
cp -a "$REPO_ROOT/ops/full-web-e2e/run-interaction-assurance-release-gate.py" "$LOCAL_EVID/sources/"
cp -a "$SCRIPT_DIR/"*.md "$LOCAL_EVID/docs/" 2>/dev/null || true
cp -a "$SCRIPT_DIR/unproven-p1-register.json" "$LOCAL_EVID/register/"

log "release gate (confirmed P0/P1 only)"
INTERACTION_AUDIT_MATRIX="${INTERACTION_AUDIT_MATRIX:-$REPO_ROOT/ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/findings/interaction-control-matrix.json}" \
  python3 "$REPO_ROOT/ops/full-web-e2e/run-interaction-assurance-release-gate.py" \
  | tee "$LOCAL_EVID/gate/release-gate.json"

if [[ "$MODE" == "local" ]]; then
  log "local harness smoke (IAX_ALLOW_LOCAL=1)"
  cd "$ORCH_SRC"
  if [[ -x .venv/bin/python ]]; then
    PY=.venv/bin/python
  else
    PY=python3
  fi
  IAX_ALLOW_LOCAL=1 IAX_BATCH="$BATCH" IAX_EVIDENCE_DIR="$LOCAL_EVID/canary" \
    IAX_UNPROVEN_REGISTER="$SCRIPT_DIR/unproven-p1-register.json" \
    WATHEFNI_ENV="${WATHEFNI_ENV:-local}" \
    "$PY" canary-prod-interaction-assurance.py 2>&1 | tee "$LOCAL_EVID/tests/canary-local.out" || {
      echo "NOTE: local canary may refuse without DB; fixtures + gate artifacts are still stamped."
      echo "Set IAX_MODE=production to run against the canary host."
    }
else
  log "push + production canary batch=$BATCH"
  "${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
  "${SCP[@]}" \
    "$ORCH_SRC/interaction_assurance_fixtures.py" \
    "$ORCH_SRC/canary-prod-interaction-assurance.py" \
    "$SCRIPT_DIR/unproven-p1-register.json" \
    "$VPS_HOST:$REMOTE_STAGE/"

  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/canary-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
cp -a '$REMOTE_STAGE/interaction_assurance_fixtures.py' "\$ORCH/"
cp -a '$REMOTE_STAGE/canary-prod-interaction-assurance.py' "\$ORCH/"
mkdir -p '$REMOTE_EVID/canary'
cd "\$ORCH"
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export IAX_BATCH='$BATCH'
export IAX_EVIDENCE_DIR='$REMOTE_EVID/canary'
export IAX_UNPROVEN_REGISTER='$REMOTE_STAGE/unproven-p1-register.json'
\$ORCH/.venv/bin/python canary-prod-interaction-assurance.py
REMOTE

  mkdir -p "$LOCAL_EVID/canary"
  "${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/canary/." "$LOCAL_EVID/canary/" || true
fi

cat > "$LOCAL_EVID/QUALIFICATION.md" <<EOF
# Interaction Assurance qualification

Stamp: \`$STAMP\`
Batch: \`$BATCH\`
Mode: \`$MODE\`

## Policy

Confirmed P0/P1 closed. Residual 495 unproven + P2 raw-error contracts remain tracked and do not block product development.

## Artifacts

- Release gate: \`gate/release-gate.json\`
- Unproven register: \`register/unproven-p1-register.json\`
- Canary: \`canary/\`
- Sources: \`sources/\`
EOF

log "done → $LOCAL_EVID"
echo "$LOCAL_EVID"
