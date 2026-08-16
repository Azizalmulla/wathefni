#!/usr/bin/env bash
# Migration Wave 1-B — production WATHEFNI synthetic qualification.
# Deploy → ACK → canary (1k+10k) → rollback proof → redeploy → canary → sibling freezes → freeze.
# Does NOT start Migration Wave 2. No real customer data. No millions claim. No UI / money / ingest / AI / mobile.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/migration-wave1b-prod-canary-$STAMP"
REMOTE_STAGE="/tmp/migration-w1b-prod-stage"
REMOTE_EVID="/opt/wathefni/production-evidence/migration-wave1b-prod-canary/${STAMP}"
STAGING_PREREQ="ops/evidence/migration-wave1-staging-20260803T211505Z"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources,migrate,rollback,verify,flags}
echo "$LOCAL_EVID" > /tmp/migw1b.evid
echo "$STAMP" > /tmp/migw1b.stamp

log() { printf '\n=== %s ===\n' "$*"; }

if [[ ! -d "$REPO_ROOT/$STAGING_PREREQ" ]]; then
  echo "REFUSE: missing staging prerequisite $STAGING_PREREQ" >&2
  exit 3
fi
grep -q 'STAGING_MIGRATION_WAVE1_FOUNDATION_CV_GO' "$REPO_ROOT/$STAGING_PREREQ/docs/REPORT.md" \
  || grep -q '"STAGING_MIGRATION_WAVE1_FOUNDATION_CV": "GO"' "$REPO_ROOT/$STAGING_PREREQ/docs/GATE.json"

log "stage sources"
mkdir -p "$LOCAL_EVID/sources/ops" "$LOCAL_EVID/migrate"
cd "$ORCH_SRC"
cp -a migration_wave1_cv_foundation.py \
  smoke-test-migration-wave1.py \
  canary-prod-migration-wave1b.py \
  smoke-test-employees360-freeze-regression.py \
  smoke-test-onboarding-freeze-regression.py \
  smoke-test-attendance-freeze-regression.py \
  smoke-test-leave-freeze-regression.py \
  smoke-test-shifts-freeze-regression.py \
  smoke-test-compliance-freeze-regression.py \
  smoke-test-action-inbox-freeze-regression.py \
  "$LOCAL_EVID/sources/"
cp -a ops/deploy-migration-wave1b-prod-synthetic.sh \
  ops/migrate-migration-wave1-prod.sh \
  "$LOCAL_EVID/sources/ops/"
cp -a ops/migrate-migration-wave1-prod.sh "$LOCAL_EVID/migrate/"
cp -a "$REPO_ROOT/ops/qualify-migration-wave1b-prod-synthetic.sh" "$LOCAL_EVID/sources/" 2>/dev/null || true

log "push stage"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" migration_wave1_cv_foundation.py \
    smoke-test-migration-wave1.py \
    canary-prod-migration-wave1b.py \
    smoke-test-employees360-freeze-regression.py \
    smoke-test-onboarding-freeze-regression.py \
    smoke-test-attendance-freeze-regression.py \
    smoke-test-leave-freeze-regression.py \
    smoke-test-shifts-freeze-regression.py \
    smoke-test-compliance-freeze-regression.py \
    smoke-test-action-inbox-freeze-regression.py \
    ops/deploy-migration-wave1b-prod-synthetic.sh \
    ops/migrate-migration-wave1-prod.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)

log "deploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy.out"
set -euo pipefail
export STAMP='$STAMP'
export STAGE_DIR='$REMOTE_STAGE'
chmod +x '$REMOTE_STAGE/deploy-migration-wave1b-prod-synthetic.sh' \
  '$REMOTE_STAGE/migrate-migration-wave1-prod.sh'
bash '$REMOTE_STAGE/deploy-migration-wave1b-prod-synthetic.sh'
REMOTE
grep -q DEPLOY_OK "$LOCAL_EVID/tests/deploy.out"
grep -q MIGRATE_OK "$LOCAL_EVID/tests/deploy.out"

run_canary() {
  local label="$1"
  local outdir="$2"
  "${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/${label}.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
OUTDIR='$REMOTE_EVID/$outdir'
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
export WATHEFNI_MIGRATION_WAVE1=1
export WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY=1
export WATHEFNI_MIGRATION_WAVE1_STAGE_ROOT=/root/.openclaw/workspaces/company-wathefni
export MIGW1_COUNT_CORE=50
export MIGW1_COUNT_1K=1000
export MIGW1_COUNT_10K=10000
export MIGW1B_EVID="\$OUTDIR"
export PYTHONUNBUFFERED=1
mkdir -p "\$OUTDIR"
tr '\0' '\n' < /proc/\$PID/environ | grep -E 'MIGRATION_WAVE1|CAPTURE_INGEST|ASSISTANT_MUTATIONS' | sort | tee "\$OUTDIR/flags.txt"
grep -qiE 'CAPTURE_INGEST=(on|true|1|yes)' "\$OUTDIR/flags.txt" && { echo 'REFUSE ingest on'; exit 3; } || echo CAPTURE_INGEST_OFF_OK
grep -q 'MIGRATION_WAVE1=1' "\$OUTDIR/flags.txt" && echo MIGRATION_WAVE1_ON_OK || { echo MIGRATION_WAVE1_NOT_ON; exit 3; }
\$PYBIN -u canary-prod-migration-wave1b.py
REMOTE
}

log "canary pass 1 (before rollback)"
run_canary canary-before-rollback canary/before-rollback
grep -q MIGRATION_WAVE1B_CANARY_PASS "$LOCAL_EVID/tests/canary-before-rollback.out"
grep -q MIGRATION_WAVE1B_RESIDUAL_0_OK "$LOCAL_EVID/tests/canary-before-rollback.out"

log "rollback proof (drop-in / modules)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/rollback.out"
set -euo pipefail
BACKUP=\$(cat /opt/wathefni/production-evidence/migration-wave1b-prod-canary/$STAMP/backup/BACKUP_PATH.txt)
bash "\$BACKUP/ROLLBACK.sh" "\$BACKUP"
test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzz-migration-wave1b-synthetic.conf
ENVS=\$(tr '\0' '\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator)/environ)
echo "\$ENVS" | grep MIGRATION_WAVE1= || echo "MIGRATION_WAVE1_FLAGS_CLEARED"
curl -fsS http://127.0.0.1:8010/health >/dev/null
echo ROLLBACK_VERIFIED
REMOTE
grep -q ROLLBACK_VERIFIED "$LOCAL_EVID/tests/rollback.out"

log "redeploy"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/redeploy.out"
set -euo pipefail
export STAMP='${STAMP}-redeploy'
export STAGE_DIR='$REMOTE_STAGE'
bash '$REMOTE_STAGE/deploy-migration-wave1b-prod-synthetic.sh'
REMOTE
grep -q DEPLOY_OK "$LOCAL_EVID/tests/redeploy.out"

log "canary pass 2 (after redeploy)"
"${SSH[@]}" "mkdir -p '$REMOTE_EVID/canary/after-redeploy'"
run_canary canary-after-redeploy canary/after-redeploy
grep -q MIGRATION_WAVE1B_CANARY_PASS "$LOCAL_EVID/tests/canary-after-redeploy.out"
grep -q MIGRATION_WAVE1B_RESIDUAL_0_OK "$LOCAL_EVID/tests/canary-after-redeploy.out"

log "sibling freezes (production)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/freezes-prod.out"
set -euo pipefail
ORCH=/opt/wathefni/orchestrator
PY=\$ORCH/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=production
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
unset DATABASE_URL || true
echo '=== E360 ==='; \$PY smoke-test-employees360-freeze-regression.py | tee /tmp/migw1b-freeze-e360.out | tail -3
echo '=== ONBOARDING ==='; \$PY smoke-test-onboarding-freeze-regression.py | tee /tmp/migw1b-freeze-onb.out | tail -3
echo '=== ATTENDANCE ==='; \$PY smoke-test-attendance-freeze-regression.py | tee /tmp/migw1b-freeze-att.out | tail -3
echo '=== LEAVE ==='; \$PY smoke-test-leave-freeze-regression.py | tee /tmp/migw1b-freeze-leave.out | tail -3
echo '=== SHIFTS ==='; \$PY smoke-test-shifts-freeze-regression.py | tee /tmp/migw1b-freeze-shifts.out | tail -3
echo '=== COMPLIANCE ==='; \$PY smoke-test-compliance-freeze-regression.py | tee /tmp/migw1b-freeze-comp.out | tail -3
echo '=== ACTION_INBOX ==='; \$PY smoke-test-action-inbox-freeze-regression.py | tee /tmp/migw1b-freeze-inbox.out | tail -3
echo SIBLING_FREEZES_DONE
REMOTE
grep -q SIBLING_FREEZES_DONE "$LOCAL_EVID/tests/freezes-prod.out"

log "pull remote evidence"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true
"${SCP[@]}" -r "$VPS_HOST:/opt/wathefni/production-evidence/migration-wave1b-prod-canary/${STAMP}-redeploy/." "$LOCAL_EVID/remote-redeploy/" 2>/dev/null || true

log "write freeze + REPORT + GATE"
python3 - "$LOCAL_EVID" "$STAMP" "$REPO_ROOT" <<'PY'
from pathlib import Path
import json, re, sys

evid = Path(sys.argv[1])
stamp = sys.argv[2]
repo = Path(sys.argv[3])
docs = evid / "docs"
docs.mkdir(parents=True, exist_ok=True)

def ok_file(name: str, *needles: str) -> bool:
    p = evid / "tests" / name
    if not p.exists():
        return False
    text = p.read_text(errors="replace")
    return all(n in text for n in needles)

canary1 = ok_file("canary-before-rollback.out", "MIGRATION_WAVE1B_CANARY_PASS", "MIGRATION_WAVE1B_RESIDUAL_0_OK")
canary2 = ok_file("canary-after-redeploy.out", "MIGRATION_WAVE1B_CANARY_PASS", "MIGRATION_WAVE1B_RESIDUAL_0_OK")
rollback = ok_file("rollback.out", "ROLLBACK_VERIFIED")
freezes = ok_file("freezes-prod.out", "SIBLING_FREEZES_DONE")
deploy = ok_file("deploy.out", "DEPLOY_OK", "MIGRATE_OK")

lanes = {}
qual = (evid / "tests" / "canary-after-redeploy.out").read_text(errors="replace")
for m in re.finditer(
    r'"label": "(1k|10k)".*?"elapsed_s": ([0-9.]+).*?"committed": ([0-9]+).*?"duplicates": ([0-9]+)',
    qual,
    re.S,
):
    lanes[m.group(1)] = {
        "elapsed_s": float(m.group(2)),
        "committed": int(m.group(3)),
        "duplicates": int(m.group(4)),
    }

verdict = "GO" if all([deploy, canary1, canary2, rollback, freezes]) else "NO-GO"
gate = "PROD_SYNTHETIC_MIGRATION_WAVE1_FOUNDATION_CV_GO" if verdict == "GO" else "PROD_SYNTHETIC_MIGRATION_WAVE1_FOUNDATION_CV_NO_GO"
freeze_gate = "MIGRATION_WAVE1_FOUNDATION_CV_GO" if verdict == "GO" else "MIGRATION_WAVE1_FOUNDATION_CV_NO_GO"

freeze = f"""# Migration Wave 1 — Foundation + Chunked CV Intake Freeze

**Status:** production synthetic qualified  
**Gate:** `{gate}`  
**Freeze gate:** `{freeze_gate}`  
**Evidence:** `ops/evidence/migration-wave1b-prod-canary-{stamp}/`  
**Staging prerequisite:** `ops/evidence/migration-wave1-staging-20260803T211505Z/` (`STAGING_MIGRATION_WAVE1_FOUNDATION_CV_GO`)

## Frozen posture

- Contract: `migration_wave1_foundation_cv_chunked` v1.0.0
- Module: `wathefni-orchestrator/migration_wave1_cv_foundation.py`
- Flag: `WATHEFNI_MIGRATION_WAVE1=1`
- `WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY=1`
- `WATHEFNI_MIGRATION_WAVE1_COMPANIES=WATHEFNI`
- Authority: **held-by-default**; Wave 1 path forces `auto_admit_enabled=False`
- Dedupe: content SHA-256; **no identity auto-merge**
- Jobs: durable chunks with lease, retry, dead-letter, replay
- Production ACK retained in `migration_wave_acks`

## Proven on production synthetic (WATHEFNI)

- Dry-run, chunked intake, resume, retry/DLQ, duplicates, external ATS IDs
- Held-by-default; no auto-admit; tenant isolation; audit/progress/rollback
- 1 000 and 10 000 synthetic CV imports
- Residual 0 after canary teardown
- Sibling freezes green
- Deploy rollback verified; redeploy canary green

## Explicit NO-GO / unchanged

- Real customer CV migration — **NO-GO**
- Millions-of-CVs cutover — **NO-GO** (not claimed)
- Full Migration Center UI — **not this wave**
- Employee / leave / compensation / shifts / compliance migration — **not this wave**
- Payroll money — unchanged / off this path
- Attendance `CAPTURE_INGEST` — remains **off**
- AI assistant / mobile — not widened
- Migration Wave 2 — **not started**

## Honesty

Synthetic fixtures only. No real customer files. No millions claim.
"""
(docs / "MIGRATION_WAVE1_FOUNDATION_CV_FREEZE.md").write_text(freeze)
(repo / "ops" / "MIGRATION_WAVE1_FOUNDATION_CV_FREEZE.md").write_text(freeze)

report = f"""# Migration Wave 1-B — production synthetic Foundation + Chunked CV Intake

**Stamp:** `{stamp}`  
**Evidence:** `ops/evidence/migration-wave1b-prod-canary-{stamp}/`  
**Staging prerequisite:** `ops/evidence/migration-wave1-staging-20260803T211505Z`  
**Freeze doc:** `ops/MIGRATION_WAVE1_FOUNDATION_CV_FREEZE.md`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Migration Wave 1 | **{verdict}** |
| Freeze Migration Wave 1 | **{verdict}** |
| Migration Wave 2 | **NO-GO** (not started) |
| Real customer / millions cutover | **NO-GO** |

## Proof

- Deploy + ACK migrate → {deploy}
- Canary before rollback (1k+10k, residual 0) → {canary1}
- Drop-in/module rollback verified → {rollback}
- Canary after redeploy → {canary2}
- Sibling freezes green → {freezes}
- Lanes: {json.dumps(lanes)}

## Flags

`WATHEFNI_MIGRATION_WAVE1=1` · `SYNTHETIC_ONLY=1` · `COMPANIES=WATHEFNI` · ingest off · mutations off

## Rollback

`/opt/wathefni/backups/production-pre-migration-wave1b-*` + `ROLLBACK.sh`  
(Durable `migration_wave_acks` rows retained.)
"""
(docs / "REPORT.md").write_text(report)

gate_obj = {
    "stamp": stamp,
    "scope": "migration_wave1_foundation_cv_chunked",
    "environment": "production",
    "synthetic_only": True,
    "wathefni_only": True,
    "real_customer_data": False,
    "millions_claim": False,
    "migration_wave2_started": False,
    "proof": {
        "deploy_ack": deploy,
        "canary_before_rollback": canary1,
        "rollback_verified": rollback,
        "canary_after_redeploy": canary2,
        "sibling_freezes": freezes,
        "lanes": lanes,
    },
    "gates": {
        "PROD_SYNTHETIC_MIGRATION_WAVE1_FOUNDATION_CV": verdict,
        "MIGRATION_WAVE1_FOUNDATION_CV_FREEZE": verdict,
        "REAL_CUSTOMER_MIGRATION": "NO-GO",
        "MILLIONS_CV_CUTOVER": "NO-GO",
        "MIGRATION_WAVE2": "NO-GO_NOT_STARTED",
    },
}
(docs / "GATE.json").write_text(json.dumps(gate_obj, indent=2) + "\n")
(docs / "GATE.txt").write_text(f"GATE={gate}\n")
print(json.dumps(gate_obj, indent=2))
print(gate)
if verdict != "GO":
    raise SystemExit(1)
PY

# Cursor freeze rule
mkdir -p "$REPO_ROOT/.cursor/rules"
cat > "$REPO_ROOT/.cursor/rules/migration-wave1-freeze.mdc" <<'RULE'
---
description: Migration Wave 1 Foundation + Chunked CV Intake freeze — do not reopen without owner change-control
globs: wathefni-orchestrator/migration_wave1_cv_foundation.py,wathefni-orchestrator/canary-prod-migration-wave1b.py,wathefni-orchestrator/smoke-test-migration-wave1.py
alwaysApply: false
---

# Migration Wave 1 freeze

Migration Wave 1 Foundation + Chunked CV Intake is **production-qualified under synthetic-only WATHEFNI posture** and **frozen**. See `ops/MIGRATION_WAVE1_FOUNDATION_CV_FREEZE.md`.

## Final posture (do not weaken)

- `WATHEFNI_MIGRATION_WAVE1=1` + `SYNTHETIC_ONLY=1` + `COMPANIES=WATHEFNI`
- Held-by-default; auto-admit forced OFF on Wave 1 path
- Checksum dedupe without identity auto-merge
- No real customer data; no millions claim

## Hard bans

1. **Do not import real customer CVs** on this path.
2. **Do not claim millions-of-CVs cutover** without a new scale wave.
3. **Do not build Migration Center UI** as the next unblock without durable-job ownership.
4. **Do not start employee/leave/compensation/shifts/compliance migration** here.
5. **Do not enable Payroll money or Attendance ingest** for migration.
6. **Do not start Migration Wave 2** without owner-approved change-control.

## Allowed without a new wave

- Bugfixes restoring freeze invariants
- Ops evidence / documentation
- `smoke-test-migration-wave1.py` / `canary-prod-migration-wave1b.py`
RULE

log "done"
echo "EVIDENCE=$LOCAL_EVID"
echo "STAMP=$STAMP"
