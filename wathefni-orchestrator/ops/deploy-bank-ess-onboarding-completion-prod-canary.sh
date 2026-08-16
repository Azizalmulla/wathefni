#!/usr/bin/env bash
# Bank ESS v1 + canonical onboarding completion — production canary deploy.
#
# Ships the completion contract (single authority) and Bank ESS employee/HR
# surfaces. Bank ESS is gated to synthetic canary employees only:
# WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST is set to the qualification canaries,
# and WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST stays EMPTY so no real
# employee bank record can be created or changed by this deploy.
set -euo pipefail

STAMP="${STAMP:?STAMP required}"
ORCH=/opt/wathefni/orchestrator
BACKUP="/opt/wathefni/backups/production-pre-bank-ess-onboarding-${STAMP}"
EVID="/opt/wathefni/production-evidence/bank-ess-onboarding-completion/${STAMP}"
STAGE="${STAGE_DIR:-/tmp/bank-ess-onboarding-stage}"
# Must sort AFTER every existing drop-in, or the canary allowlist additions are
# overridden by zzzz-onboarding-lifecycle-wave2a / zzzzzzzzzzzzz-shifts-wave6c.
DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzzzz-bank-ess-onboarding-completion.conf
LEGACY_DROPIN=/etc/systemd/system/wathefni-orchestrator.service.d/zz-bank-ess-onboarding-completion.conf

# Synthetic qualification canaries (ESS synthetic phone prefix 965549).
CANARY_KEYS="WATHEFNI-9655497001,WATHEFNI-9655497002,WATHEFNI-9655497003"

FILES="app.py onboarding_completion_contract.py employee_bank_ess.py onboarding_wave2.py onboarding_lifecycle_wave2a.py employee_selfservice_wave5.py calendar_posthire_projections.py operator_mobile_data.py test-onboarding-completion-contract.py ops-smoke-bank-ess-onboarding-qual-matrix.py"

mkdir -p "$EVID"/{preflight,verify,flags,tests,qual} "$BACKUP"
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# --- preflight ---
{
  echo "stamp=$STAMP"
  echo "time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs before ==="
  cd "$ORCH"
  for f in $FILES; do [ -f "$f" ] && sha256sum "$f" || echo "absent $f"; done
  echo "=== bank/ess/onboarding flags before ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'BANK|ESS|ONBOARDING|EMPLOYEE_APP' | sort || true
} | tee "$EVID/preflight/before-deploy.txt"

# --- backup ---
cd "$ORCH"
for f in $FILES; do [ -f "$f" ] && cp -a "$f" "$BACKUP/"; done
cp -a "$DROPIN" "$BACKUP/dropin-before.conf" 2>/dev/null || echo "no prior dropin" > "$BACKUP/dropin-before.conf"
log "backup at $BACKUP"

# --- install staged files ---
for f in $FILES; do
  [ -f "$STAGE/$f" ] || { echo "MISSING STAGED $f" >&2; exit 2; }
  install -m 0644 "$STAGE/$f" "$ORCH/$f"
done

set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.env
set +a
export WATHEFNI_ENV=production
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1

# --- compile + pure-logic contract tests before restart ---
{
  cd "$ORCH"
  ./.venv/bin/python -m py_compile $FILES && echo "py_compile OK"
  ./.venv/bin/python test-onboarding-completion-contract.py
} | tee "$EVID/tests/contract-unit.txt"

# --- flags: canary-scoped ---
cat > "$DROPIN" <<EOF
[Service]
# Canonical onboarding completion contract (legacy columns still mirrored).
Environment=WATHEFNI_ONBOARDING_COMPLETION_CONTRACT=on
Environment=WATHEFNI_ONBOARDING_COMPLETION_CONTRACT_COMPANIES=WATHEFNI
# Bank ESS v1 — synthetic qualification canaries only.
Environment=WATHEFNI_BANK_ESS_V1=on
Environment=WATHEFNI_BANK_ESS_V1_COMPANIES=WATHEFNI
Environment=WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST=${CANARY_KEYS}
Environment=WATHEFNI_BANK_ESS_SCHEME=kw_iban
Environment=WATHEFNI_BANK_ESS_ENFORCE_VALIDATION=off
# /app sessions for the canaries (real employees keep their existing access).
Environment=WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST=WATHEFNI-96550252254,WATHEFNI-96599338566,${CANARY_KEYS}
Environment=WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566,WATHEFNI-96550252254,${CANARY_KEYS}
EOF
cp -a "$DROPIN" "$EVID/flags/dropin-after.conf"
rm -f "$LEGACY_DROPIN"

systemctl daemon-reload
systemctl restart wathefni-orchestrator
sleep 6

# --- verify ---
{
  systemctl is-active wathefni-orchestrator
  echo "=== SHAs after ==="
  cd "$ORCH"; for f in $FILES; do sha256sum "$f"; done
  echo "=== flags after (process) ==="
  PID=$(systemctl show -p MainPID --value wathefni-orchestrator)
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E 'BANK|ESS|ONBOARDING|EMPLOYEE_APP' | sort
  echo "=== health ==="
  curl -sS -m 20 http://127.0.0.1:8010/health || true
  echo
  echo "=== bank real allowlist MUST be empty ==="
  tr '\0' '\n' < /proc/"$PID"/environ | grep -E '^WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST=' || echo "(unset)"
} | tee "$EVID/verify/after-deploy.txt"

log "deployed. evidence=$EVID backup=$BACKUP"
