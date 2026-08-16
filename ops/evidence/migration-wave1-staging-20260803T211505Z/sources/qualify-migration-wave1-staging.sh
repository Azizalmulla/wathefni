#!/usr/bin/env bash
# Migration Wave 1 — Foundation + Chunked CV Intake — staging + synthetic only.
# Proves 1k + 10k synthetic CVs, retry/resume, dedupe, tenant isolation, no auto-admit,
# residual 0, sibling freezes. No real customer data. No Wave 2. No prod synthetic.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ORCH="$ROOT/wathefni-orchestrator"
STAMP="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
EVID="$ROOT/ops/evidence/migration-wave1-staging-${STAMP}"
HOST="${STAGING_HOST:-76.13.63.68}"
REMOTE_ORCH="${REMOTE_ORCH:-/opt/wathefni/staging/orchestrator}"
REMOTE_EVID="/opt/wathefni/staging-evidence/migration-wave1/${STAMP}"
VPS_HOST="root@$HOST"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")

mkdir -p "$EVID"/{sources,tests,remote,docs,verify,flags}
echo "$EVID" > /tmp/migw1.evid
echo "$STAMP" > /tmp/migw1.stamp

log() { printf '\n=== %s ===\n' "$*"; }

log "stage sources locally"
cp -a "$ORCH/migration_wave1_cv_foundation.py" \
  "$ORCH/smoke-test-migration-wave1.py" \
  "$ROOT/ops/qualify-migration-wave1-staging.sh" \
  "$EVID/sources/" 2>/dev/null || true
cp -a "$ORCH/migration_wave1_cv_foundation.py" "$ORCH/smoke-test-migration-wave1.py" "$EVID/sources/"

log "push staging orchestrator modules"
"${SSH[@]}" "mkdir -p '$REMOTE_ORCH' '$REMOTE_EVID'/{tests,flags,verify}"
rsync -az -e "ssh -o BatchMode=yes" \
  "$ORCH/migration_wave1_cv_foundation.py" \
  "$ORCH/smoke-test-migration-wave1.py" \
  "$ORCH/smoke-test-employees360-freeze-regression.py" \
  "$ORCH/smoke-test-onboarding-freeze-regression.py" \
  "$ORCH/smoke-test-attendance-freeze-regression.py" \
  "$ORCH/smoke-test-leave-freeze-regression.py" \
  "$ORCH/smoke-test-shifts-freeze-regression.py" \
  "$ORCH/smoke-test-compliance-freeze-regression.py" \
  "$ORCH/smoke-test-action-inbox-freeze-regression.py" \
  "$VPS_HOST:$REMOTE_ORCH/"

log "staging flag drop-in + health (no restart required for smoke env, but pin flag)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$EVID/flags/staging-dropin.out"
set -euo pipefail
mkdir -p /etc/systemd/system/wathefni-orchestrator-staging.service.d
cat > /etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzz-migration-wave1.conf <<'EOF'
[Service]
Environment=WATHEFNI_MIGRATION_WAVE1=1
Environment=WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Environment=WATHEFNI_ASSISTANT_MUTATIONS=0
EOF
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then echo health_ok; break; fi
  sleep 1
done
systemctl is-active wathefni-orchestrator-staging
tr '\\0' '\\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)/environ \
  | grep -E 'MIGRATION_WAVE1|CAPTURE_INGEST|ASSISTANT_MUTATIONS' | sort
REMOTE

log "sibling freezes (staging)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$EVID/tests/sibling-freezes.out"
set -euo pipefail
ORCH='$REMOTE_ORCH'
REMOTE_EVID='$REMOTE_EVID'
PY=/opt/wathefni/orchestrator/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
export WATHEFNI_ASSISTANT_MUTATIONS=0
unset DATABASE_URL || true
mkdir -p "\$REMOTE_EVID/tests"
echo '=== E360 ==='; \$PY smoke-test-employees360-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-e360.out | tail -3
echo '=== ONBOARDING ==='; \$PY smoke-test-onboarding-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-onboarding.out | tail -3
echo '=== ATTENDANCE ==='; \$PY smoke-test-attendance-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-attendance.out | tail -3
echo '=== LEAVE ==='; \$PY smoke-test-leave-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-leave.out | tail -3
echo '=== SHIFTS ==='; \$PY smoke-test-shifts-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-shifts.out | tail -3
echo '=== COMPLIANCE ==='; \$PY smoke-test-compliance-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-compliance.out | tail -3
echo '=== ACTION_INBOX ==='; \$PY smoke-test-action-inbox-freeze-regression.py | tee \$REMOTE_EVID/tests/freeze-inbox.out | tail -3
echo SIBLING_FREEZES_DONE
REMOTE

log "migration wave1 synthetic qualify (core + 1k + 10k)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$EVID/tests/staging-qualify.out"
set -euo pipefail
ORCH='$REMOTE_ORCH'
REMOTE_EVID='$REMOTE_EVID'
PY=/opt/wathefni/orchestrator/.venv/bin/python
cd \$ORCH
set -a; source /root/.openclaw/secrets/postgres.staging.env; set +a
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
export WATHEFNI_ENV=staging
export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
export WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
export WATHEFNI_EXPECTED_DATABASE_PORT=5432
export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging
export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1
export WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
export WATHEFNI_ASSISTANT_MUTATIONS=0
export WATHEFNI_MIGRATION_WAVE1=1
export WATHEFNI_MIGRATION_WAVE1_STAGE_ROOT=/opt/wathefni/staging/workspace
export MIGW1_COUNT_CORE=50
export MIGW1_COUNT_1K=1000
export MIGW1_COUNT_10K=10000
export PYTHONUNBUFFERED=1
unset DATABASE_URL || true
mkdir -p "\$REMOTE_EVID/tests"
\$PY -u smoke-test-migration-wave1.py 2>&1 | tee "\$REMOTE_EVID/tests/smoke-migration-wave1.out"
grep -q MIGRATION_WAVE1_SMOKE_PASS "\$REMOTE_EVID/tests/smoke-migration-wave1.out"
echo MIGW1_SMOKE_OK
# residual companies gone
\$PY - <<'PY'
import app, json
companies=("MIGW1ALPHA","MIGW1BRAVO")
with app.db_connect() as conn:
  with conn.cursor() as cur:
    cur.execute("SELECT current_database() db")
    db=dict(cur.fetchone())["db"]
    out={"db":db,"companies":{},"residual_total":0}
    for c in companies:
      cur.execute("SELECT count(*)::int c FROM applications WHERE company_code=%s",(c,))
      a=int(cur.fetchone()["c"])
      cur.execute("SELECT count(*)::int c FROM migration_batches WHERE company_code=%s",(c,))
      b=int(cur.fetchone()["c"])
      cur.execute("SELECT count(*)::int c FROM companies WHERE company_code=%s",(c,))
      co=int(cur.fetchone()["c"])
      out["companies"][c]={"applications":a,"migration_batches":b,"company_row":co}
      out["residual_total"]+=a+b+co
print(json.dumps(out, indent=2))
assert out["residual_total"]==0, out
print("RESIDUAL_0_OK")
PY
REMOTE

log "pull remote evidence"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVID/" "$EVID/remote/" || true
cp -a "$EVID/tests/staging-qualify.out" "$EVID/verify/" 2>/dev/null || true

log "write GATE + REPORT"
python3 - "$EVID" "$STAMP" <<'PY'
from pathlib import Path
import json, re, sys
evid = Path(sys.argv[1])
stamp = sys.argv[2]
qual = (evid / "tests" / "staging-qualify.out").read_text(errors="replace")
freezes = (evid / "tests" / "sibling-freezes.out").read_text(errors="replace")
pass_ok = "MIGRATION_WAVE1_SMOKE_PASS" in qual and "RESIDUAL_0_OK" in qual and "MIGW1_SMOKE_OK" in qual
freeze_ok = "SIBLING_FREEZES_DONE" in freezes
lanes = {}
for m in re.finditer(r'"label": "(1k|10k)".*?"elapsed_s": ([0-9.]+).*?"committed": ([0-9]+).*?"duplicates": ([0-9]+)', qual, re.S):
    lanes[m.group(1)] = {"elapsed_s": float(m.group(2)), "committed": int(m.group(3)), "duplicates": int(m.group(4))}
staging_go = pass_ok and freeze_ok
gate = {
  "stamp": stamp,
  "scope": "migration_wave1_foundation_cv_chunked",
  "environment": "staging",
  "synthetic_only": True,
  "real_customer_data": False,
  "millions_claim": False,
  "migration_wave2_started": False,
  "proof": {
    "smoke_pass": pass_ok,
    "sibling_freezes": freeze_ok,
    "lanes": lanes,
  },
  "gates": {
    "STAGING_MIGRATION_WAVE1_FOUNDATION_CV": "GO" if staging_go else "NO-GO",
    "PROD_SYNTHETIC_MIGRATION_WAVE1_FOUNDATION_CV": "NO-GO",
    "REAL_CUSTOMER_MIGRATION": "NO-GO",
    "MILLIONS_CV_CUTOVER": "NO-GO",
    "MIGRATION_WAVE2": "NO-GO_NOT_STARTED",
  },
}
(evid / "docs" / "GATE.json").write_text(json.dumps(gate, indent=2) + "\n")
gate_name = "STAGING_MIGRATION_WAVE1_FOUNDATION_CV_GO" if staging_go else "STAGING_MIGRATION_WAVE1_FOUNDATION_CV_NO_GO"
report = f"""# Migration Wave 1 — Foundation + Chunked CV Intake (staging)

**Stamp:** {stamp}
**Evidence:** `ops/evidence/migration-wave1-staging-{stamp}/`
**Gate:** `{gate_name}`

## Scope shipped
- Shared migration batch / row / chunk-job / event contract
- Dry-run + exception queue
- Durable chunked CV intake with retry + DLQ replay
- Staged folder / object-storage-style intake under workspace stage root
- Optional external ATS candidate ID preservation (sidecar / meta.json)
- Held-by-default authority; auto-admit forced OFF on Wave 1 path
- Checksum deduplication without auto-merge
- Progress, audit events, rollback; residual 0 after teardown

## Explicit out of scope
Real customer data, millions claim, Migration Center UI, employee/leave/compensation migration,
Payroll money, Attendance ingest, AI assistant expand, mobile, Migration Wave 2, production synthetic.

## Proof
- Staging smoke: core + 1 000 + 10 000 synthetic CVs — {"PASS" if pass_ok else "FAIL"}
- Retry / resume / DLQ replay covered in core lane
- Duplicate handling + tenant isolation + no auto-admit asserted
- Residual 0 after rollback/teardown
- Sibling freezes: {"green" if freeze_ok else "FAIL"}
- Lanes: {json.dumps(lanes)}

## Production synthetic qualification
**NO-GO** until a separate Wave 1-B authorization. Staging GO does not authorize prod synthetic.

## Next (not this wave)
Migration Wave 2 — **not started**.
"""
(evid / "docs" / "REPORT.md").write_text(report)
print(json.dumps(gate, indent=2))
print("STAGING_GO" if staging_go else "STAGING_NO_GO")
if not staging_go:
    raise SystemExit(1)
PY

# Freeze draft
cat > "$ROOT/ops/MIGRATION_WAVE1_FOUNDATION_CV_FREEZE.md" <<EOF
# Migration Wave 1 — Foundation + Chunked CV Intake Freeze

**Status:** staging qualified  
**Stamp:** ${STAMP}  
**Evidence:** \`ops/evidence/migration-wave1-staging-${STAMP}/\`  
**Gate:** \`STAGING_MIGRATION_WAVE1_FOUNDATION_CV_GO\`

## Frozen surface
- Contract: \`migration_wave1_foundation_cv_chunked\` v1.0.0
- Module: \`wathefni-orchestrator/migration_wave1_cv_foundation.py\`
- Flag: \`WATHEFNI_MIGRATION_WAVE1=1\` (staging)
- Stage root: \`WATHEFNI_MIGRATION_WAVE1_STAGE_ROOT\` / workspace \`migration_wave1_stage/\`
- Authority: **held-by-default**; Wave 1 path forces \`auto_admit_enabled=False\`
- Dedupe: content SHA-256; **no identity auto-merge**
- Jobs: \`migration_chunk_jobs\` with lease, retry, dead-letter, replay
- Rollback: deletes held applications + import artifacts for the migration batch

## Proven on staging (synthetic only)
- Core contract (dry-run, resume, retry/DLQ, tenant isolation, external ATS ids)
- 1 000 synthetic CVs
- 10 000 synthetic CVs
- Residual 0 after rollback/teardown
- Sibling freezes green

## Explicit NO-GO / unchanged
- Production synthetic Wave 1-B — **NO-GO** until separately authorized
- Real customer CV migration — **NO-GO**
- Millions-of-CVs cutover — **NO-GO** (not claimed)
- Full Migration Center UI — **not this wave**
- Employee / leave / compensation migration — **not this wave**
- Payroll money — unchanged / off this path
- Attendance \`CAPTURE_INGEST\` — remains **off**
- AI assistant / mobile — not widened
- Migration Wave 2 — **not started**

## Honesty
Synthetic fixtures only. No real customer files. No millions claim.
EOF

cp -a "$ROOT/ops/MIGRATION_WAVE1_FOUNDATION_CV_FREEZE.md" "$EVID/docs/"

log "done"
echo "EVIDENCE=$EVID"
echo "STAMP=$STAMP"
