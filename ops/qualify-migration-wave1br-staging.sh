#!/usr/bin/env bash
# Deadlock Remediation Wave 1-BR — staging proof (no production Wave 1-B resume).
# Proves: no runtime DDL, fail-closed missing schema, concurrency without relation-lock
# cycles, migration inject/retry/replay/rollback, residual zero including queues.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ControlMaster=no -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_EVID="$REPO_ROOT/ops/evidence/migration-wave1br-deadlock-remediation-$STAMP"
REMOTE_STAGE="/tmp/migration-w1br-stage"
REMOTE_EVID="/opt/wathefni/staging-evidence/migration-wave1br-deadlock-remediation/${STAMP}"

mkdir -p "$LOCAL_EVID"/{tests,docs,remote,sources}
echo "$LOCAL_EVID" > /tmp/migw1br.evid

log() { printf '\n=== %s ===\n' "$*"; }

log "stage sources"
cp -a "$ORCH_SRC/schema_contract.py" \
  "$ORCH_SRC/inbound_cv_intake.py" \
  "$ORCH_SRC/inbound_cv_processing.py" \
  "$ORCH_SRC/inbound_cv_adapters.py" \
  "$ORCH_SRC/durable_email_ingress.py" \
  "$ORCH_SRC/migration_wave1_cv_foundation.py" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/canary-prod-migration-wave1b.py" \
  "$ORCH_SRC/smoke-test-migration-wave1.py" \
  "$ORCH_SRC/ops/migrate-schema-wave1br.sh" \
  "$LOCAL_EVID/sources/" 2>/dev/null || true
cp -a "$ORCH_SRC/ops/migrate-schema-wave1br.sh" "$LOCAL_EVID/sources/"

log "push to staging orchestrator"
"${SSH[@]}" "rm -rf '$REMOTE_STAGE' && mkdir -p '$REMOTE_STAGE' '$REMOTE_EVID'/{pre,migrate,proofs,concurrency,residual}"
(
  cd "$ORCH_SRC"
  "${SCP[@]}" schema_contract.py inbound_cv_intake.py inbound_cv_processing.py \
    inbound_cv_adapters.py durable_email_ingress.py migration_wave1_cv_foundation.py \
    app.py canary-prod-migration-wave1b.py smoke-test-migration-wave1.py \
    ops/migrate-schema-wave1br.sh \
    "$VPS_HOST:$REMOTE_STAGE/"
)

log "backup + install on staging (no production touch)"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/deploy-staging.out"
set -euo pipefail
STAMP='$STAMP'
STAGE='$REMOTE_STAGE'
ORCH=/opt/wathefni/staging/orchestrator
BACKUP=/opt/wathefni/backups/staging-pre-migration-wave1br-\$STAMP
EVID='$REMOTE_EVID'
mkdir -p "\$BACKUP/modules" "\$EVID"
test -d "\$ORCH"
for f in schema_contract.py inbound_cv_intake.py inbound_cv_processing.py \
         inbound_cv_adapters.py durable_email_ingress.py migration_wave1_cv_foundation.py \
         app.py canary-prod-migration-wave1b.py smoke-test-migration-wave1.py; do
  [[ -f "\$ORCH/\$f" ]] && cp -a "\$ORCH/\$f" "\$BACKUP/modules/" || true
  cp -a "\$STAGE/\$f" "\$ORCH/\$f"
done
mkdir -p "\$ORCH/ops"
cp -a "\$STAGE/migrate-schema-wave1br.sh" "\$ORCH/ops/"
chmod +x "\$ORCH/ops/migrate-schema-wave1br.sh"
echo "\$BACKUP" | tee "\$EVID/BACKUP_PATH.txt"
sha256sum "\$ORCH/schema_contract.py" "\$ORCH/inbound_cv_intake.py" "\$ORCH/app.py" \
  "\$ORCH/migration_wave1_cv_foundation.py" | tee "\$EVID/pre/shas.txt"
# Do not restart production. Restart staging only after migrate.
systemctl is-active wathefni-orchestrator-staging || systemctl is-active wathefni-staging-orchestrator || true
echo STAGING_MODULES_INSTALLED
REMOTE
grep -q STAGING_MODULES_INSTALLED "$LOCAL_EVID/tests/deploy-staging.out"

log "deploy-time migrate on staging"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/migrate.out"
set -euo pipefail
ORCH=/opt/wathefni/staging/orchestrator
EVID='$REMOTE_EVID'
cd "\$ORCH"
# Load staging service env first, then its postgres env file (not production).
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do
  case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac
done < /proc/\$PID/environ
unset DATABASE_URL || true
set -a; source "\${WATHEFNI_POSTGRES_ENV:-/root/.openclaw/secrets/postgres.staging.env}"; set +a
unset DATABASE_URL || true
export WATHEFNI_ENV=staging
export WATHEFNI_SCHEMA_APPLY=1
export ACK_STAGING_SCHEMA_WAVE1BR=YES
# Staging shares the production venv binary path.
export ORCH_PYTHON=/opt/wathefni/orchestrator/.venv/bin/python
test -x "\$ORCH_PYTHON"
test "\${WATHEFNI_EXPECTED_DATABASE_NAME}" = "wathefni_staging"
bash "\$ORCH/ops/migrate-schema-wave1br.sh" | tee "\$EVID/migrate/migrate.out"
# Restart staging so workers boot with apply OFF
unset WATHEFNI_SCHEMA_APPLY || true
# Ensure staging unit does not carry SCHEMA_APPLY
systemctl restart wathefni-orchestrator-staging 2>/dev/null || systemctl restart wathefni-staging-orchestrator
for i in \$(seq 1 60); do
  if curl -fsS http://127.0.0.1:8011/health >/dev/null 2>&1; then
    echo staging_health_ok
    break
  fi
  sleep 1
done
ENVS=\$(tr '\\0' '\\n' < /proc/\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)/environ)
echo "\$ENVS" | grep SCHEMA_APPLY && { echo 'REFUSE staging has SCHEMA_APPLY'; exit 3; } || echo SCHEMA_APPLY_ABSENT_OK
echo MIGRATE_AND_RESTART_DONE
REMOTE
grep -q MIGRATE_SCHEMA_WAVE1BR_OK "$LOCAL_EVID/tests/migrate.out"
grep -q MIGRATE_AND_RESTART_DONE "$LOCAL_EVID/tests/migrate.out"

log "runtime proofs on staging"
"${SSH[@]}" "bash -s" <<REMOTE | tee "$LOCAL_EVID/tests/proofs.out"
set -euo pipefail
ORCH=/opt/wathefni/staging/orchestrator
EVID='$REMOTE_EVID'
cd "\$ORCH"
PID=\$(systemctl show -p MainPID --value wathefni-orchestrator-staging)
while IFS= read -r -d '' line; do case "\$line" in WATHEFNI_*=*) export "\$line" ;; esac; done < /proc/\$PID/environ
unset DATABASE_URL || true
set -a; source "\${WATHEFNI_POSTGRES_ENV:-/root/.openclaw/secrets/postgres.staging.env}"; set +a
unset DATABASE_URL || true
export WATHEFNI_ENV=staging
unset WATHEFNI_SCHEMA_APPLY || true
export WATHEFNI_MIGRATION_WAVE1=1
export WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY=1
export WATHEFNI_MIGRATION_WAVE1_COMPANIES=WATHEFNI,MIGW1ALPHA,MIGW1BRAVO
PY=/opt/wathefni/orchestrator/.venv/bin/python
test -x "\$PY"
test "\${WATHEFNI_EXPECTED_DATABASE_NAME}" = "wathefni_staging"

\$PY - <<'PY' | tee "\$EVID/proofs/no-runtime-ddl.json"
import json, os
import app
import schema_contract as sc
import inbound_cv_intake as intake
import inbound_cv_processing as processing
import durable_email_ingress as durable
import migration_wave1_cv_foundation as mig
import inbound_cv_adapters as adapters

assert not sc.schema_apply_allowed()
sc.reset_counters()
app._SCHEMA_READY = False
# Startup-equivalent validate path
app.ensure_schema(force=True)
# Hot-path require calls that previously executed DDL
with app.db_connect() as conn:
    with conn.cursor() as cur:
        intake.require_schema(cur)
        processing.require_schema(cur)
        durable.require_schema(cur)
        mig.require_schema(cur)
        # Adapter observe path must not apply
        adapters.observe_shared_stages_for_document(
            cur,
            company_code="WATHEFNI",
            subject_id="00000000-0000-0000-0000-000000000001",
            content_sha256="a"*64,
            mime_or_suffix=".pdf",
            local_text_ok=True,
            needs_ocr=False,
            channel="manual_upload",
            environ={"WATHEFNI_UNIFIED_INTAKE_SHARED_PROCESSING": "0"},
        )
    conn.commit()
c = sc.counters()
out = {"counters": c, "apply_allowed": sc.schema_apply_allowed()}
assert c["apply_calls"] == 0, out
assert c["blocked_apply_attempts"] == 0, out
print(json.dumps(out, indent=2))
print("NO_RUNTIME_DDL_OK")
PY

\$PY - <<'PY' | tee "\$EVID/proofs/fail-closed.json"
import json, os
import schema_contract as sc

# Simulate missing relation detection without dropping production/staging tables:
# call require_relations with a fake table name.
import app
with app.db_connect() as conn:
    with conn.cursor() as cur:
        try:
            sc.require_relations(cur, ["wave1br_missing_relation_probe_zzz"], module="fail_closed_probe")
            raise SystemExit("expected SchemaNotMigratedError")
        except sc.SchemaNotMigratedError as exc:
            print(json.dumps({"ok": True, "error": str(exc), "missing": exc.missing}, indent=2))
print("FAIL_CLOSED_OK")
PY

\$PY - <<'PY' | tee "\$EVID/proofs/concurrency-and-migration.json"
import json, os, time, threading, tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import app
import schema_contract as sc
import migration_wave1_cv_foundation as mig

os.environ.setdefault("WATHEFNI_MIGRATION_WAVE1", "1")
os.environ.setdefault("WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY", "1")
os.environ["WATHEFNI_MIGRATION_WAVE1_COMPANIES"] = "WATHEFNI,MIGW1ALPHA,MIGW1BRAVO"
assert not sc.schema_apply_allowed()
sc.reset_counters()

stage = Path(tempfile.mkdtemp(prefix="w1br-conc-"))
mig.generate_synthetic_cvs(stage / "core", count=40, company_code="WATHEFNI", with_external_ids=True, duplicate_every=10)
mig.generate_synthetic_cvs(stage / "1k", count=200, company_code="WATHEFNI", with_external_ids=True, duplicate_every=20)

stop = threading.Event()
lock_samples = []

def sibling_noise():
    while not stop.is_set():
        try:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    # Validate-only schema path + ordinary DML peers
                    app._SCHEMA_READY = False
                    # Do not call ensure_schema repeatedly with force in tight loop;
                    # emulate request/worker validate once then reads.
                    sc.require_core_runtime_schema(cur)
                    cur.execute("SELECT count(*)::int AS c FROM hr_turns")
                    cur.fetchone()
                    cur.execute("SELECT count(*)::int AS c FROM applications WHERE company_code=%s", ("WATHEFNI",))
                    cur.fetchone()
                    cur.execute(
                        """
                        SELECT count(*)::int AS blocked FROM pg_locks WHERE NOT granted
                        """
                    )
                    lock_samples.append(int(cur.fetchone()["blocked"]))
                conn.commit()
        except Exception as exc:  # noqa: BLE001
            lock_samples.append({"err": str(exc)[:160]})
        time.sleep(0.05)

noise = threading.Thread(target=sibling_noise, daemon=True)
noise.start()

created_core = mig.create_staged_cv_batch(
    app, company_code="WATHEFNI", stage_dir=stage / "core", dry_run=False,
    chunk_size=10, created_by="w1br-core", options={"extraction_policy": "defer"},
)
assert created_core.get("ok"), created_core
# inject fail -> DLQ -> replay
os.environ["WATHEFNI_MIGRATION_WAVE1_INJECT_FAIL_UNTIL"] = "2"
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("UPDATE migration_chunk_jobs SET max_attempts=2 WHERE batch_id=%s", (created_core["batch_id"],))
    conn.commit()
for _ in range(12):
    mig.run_worker(app, company_code="WATHEFNI", batch_id=created_core["batch_id"], limit=1, worker_id="w1br-inject")
    prog = mig.batch_progress(app, batch_id=created_core["batch_id"], company_code="WATHEFNI")
    if int(prog["jobs_by_status"].get("dead_letter") or 0) > 0:
        break
    time.sleep(0.1)
os.environ["WATHEFNI_MIGRATION_WAVE1_INJECT_FAIL_UNTIL"] = "0"
replay = mig.replay_dead_letters(app, batch_id=created_core["batch_id"], company_code="WATHEFNI")
fin_core = mig.run_until_idle(app, batch_id=created_core["batch_id"], company_code="WATHEFNI", max_loops=100)
assert fin_core.get("ok"), fin_core

created_1k = mig.create_staged_cv_batch(
    app, company_code="WATHEFNI", stage_dir=stage / "1k", dry_run=False,
    chunk_size=50, created_by="w1br-1k", options={"extraction_policy": "defer"},
)
assert created_1k.get("ok"), created_1k

# Concurrent batch-scoped workers on 1k while noise continues
def worker_loop(wid: str):
    return mig.run_worker(
        app,
        company_code="WATHEFNI",
        batch_id=created_1k["batch_id"],
        limit=20,
        worker_id=wid,
    )

t0 = time.time()
# Burst concurrent workers then drain
for _round in range(30):
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = [pool.submit(worker_loop, f"w1br-w{i}-{_round}") for i in range(3)]
        for f in as_completed(futs):
            f.result()
    prog = mig.batch_progress(app, batch_id=created_1k["batch_id"], company_code="WATHEFNI")
    jobs = prog.get("jobs_by_status") or {}
    pending = int(jobs.get("pending") or 0) + int(jobs.get("failed") or 0) + int(jobs.get("leased") or 0)
    if pending == 0 or prog["batch"]["status"] in {"completed", "failed", "rolled_back"}:
        break
elapsed = time.time() - t0
fin = mig.run_until_idle(app, batch_id=created_1k["batch_id"], company_code="WATHEFNI", max_loops=80)
assert fin.get("ok"), fin
prog_1k = mig.batch_progress(app, batch_id=created_1k["batch_id"], company_code="WATHEFNI")
assert prog_1k["batch"]["status"] == "completed", prog_1k

# deadlock exhaustion check: no dead_letter from natural deadlocks on 1k
assert int(prog_1k["jobs_by_status"].get("dead_letter") or 0) == 0, prog_1k

rb1 = mig.rollback_batch(app, batch_id=created_core["batch_id"], company_code="WATHEFNI")
rb2 = mig.rollback_batch(app, batch_id=created_1k["batch_id"], company_code="WATHEFNI")
assert rb1.get("ok") and rb2.get("ok"), (rb1, rb2)

stop.set()
noise.join(timeout=2)

# cleanup batch metadata (preserve nothing required for this staging proof)
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT batch_id::text FROM migration_batches
            WHERE company_code='WATHEFNI' AND coalesce(created_by,'') LIKE 'w1br-%%'
            """
        )
        bids = [r["batch_id"] for r in cur.fetchall()]
        for bid in bids:
            cur.execute(
                "SELECT import_batch_id::text AS id FROM migration_batches WHERE batch_id=%s",
                (bid,),
            )
            row = cur.fetchone() or {}
            iid = row.get("id")
            if iid:
                cur.execute("DELETE FROM import_items WHERE batch_id=%s", (iid,))
                cur.execute("DELETE FROM import_batches WHERE batch_id=%s", (iid,))
            cur.execute("DELETE FROM migration_events WHERE batch_id=%s", (bid,))
            cur.execute("DELETE FROM migration_chunk_jobs WHERE batch_id=%s", (bid,))
            cur.execute("DELETE FROM migration_rows WHERE batch_id=%s", (bid,))
            cur.execute("DELETE FROM migration_batches WHERE batch_id=%s", (bid,))
        cur.execute("SELECT count(*)::int AS c FROM pg_locks WHERE NOT granted")
        ung = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT count(*)::int AS c FROM intake_processing_jobs
            WHERE company_code='WATHEFNI' AND job_type='cv_extraction'
              AND payload->>'workload_class'='migration'
              AND status IN ('pending','running','retrying','waiting_quota','waiting_budget')
            """
        )
        active_mig_q = int(cur.fetchone()["c"])
        cur.execute(
            """
            SELECT count(*)::int AS c FROM migration_batches
            WHERE company_code='WATHEFNI' AND coalesce(created_by,'') LIKE 'w1br-%%'
            """
        )
        open_batches = int(cur.fetchone()["c"])
    conn.commit()

out = {
    "elapsed_1k_s": round(elapsed, 2),
    "core_replayed": replay.get("replayed"),
    "lane_1k": prog_1k["rows_by_status"],
    "ungranted_locks_end": ung,
    "active_migration_extraction_queue": active_mig_q,
    "open_batches_after_cleanup": open_batches,
    "schema_counters": sc.counters(),
    "max_ungranted_during": max((x for x in lock_samples if isinstance(x, int)), default=0),
}
assert out["schema_counters"]["apply_calls"] == 0, out
assert out["active_migration_extraction_queue"] == 0, out
assert out["open_batches_after_cleanup"] == 0, out
print(json.dumps(out, indent=2, default=str))
print("CONCURRENCY_MIGRATION_OK")
PY

\$PY - <<'PY' | tee "\$EVID/residual/residual-zero.json"
import json
from datetime import datetime, timezone
import app
active=("pending","running","retrying","waiting_quota","waiting_budget")
out={"probe_utc": datetime.now(timezone.utc).isoformat()}
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*)::int c FROM migration_batches WHERE coalesce(created_by,'') LIKE 'w1br-%%'")
        out["w1br_batches"]=cur.fetchone()["c"]
        cur.execute("SELECT count(*)::int c FROM applications WHERE company_code='WATHEFNI' AND coalesce(raw_json->'import'->>'migration_batch_id','')<>''")
        out["migration_apps"]=cur.fetchone()["c"]
        cur.execute("SELECT count(*)::int c FROM candidate_documents WHERE extraction_status='deferred_migration'")
        out["deferred"]=cur.fetchone()["c"]
        cur.execute("SELECT count(*)::int c FROM intake_processing_jobs WHERE company_code='WATHEFNI' AND job_type='cv_extraction' AND payload->>'workload_class'='migration' AND status=ANY(%s)", (list(active),))
        out["active_mig_ext"]=cur.fetchone()["c"]
        cur.execute("SELECT count(*)::int c FROM companies WHERE company_code=ANY(%s)", (["MIGW1ALPHA","MIGW1BRAVO"],))
        out["iso"]=cur.fetchone()["c"]
out["residual_zero"]=all(int(out[k])==0 for k in ("w1br_batches","migration_apps","deferred","active_mig_ext","iso"))
print(json.dumps(out, indent=2))
assert out["residual_zero"]
print("RESIDUAL_ZERO_OK")
PY
echo STAGING_PROOFS_DONE
REMOTE

grep -q NO_RUNTIME_DDL_OK "$LOCAL_EVID/tests/proofs.out"
grep -q FAIL_CLOSED_OK "$LOCAL_EVID/tests/proofs.out"
grep -q CONCURRENCY_MIGRATION_OK "$LOCAL_EVID/tests/proofs.out"
grep -q RESIDUAL_ZERO_OK "$LOCAL_EVID/tests/proofs.out"

log "pull evidence + write report"
"${SCP[@]}" -r "$VPS_HOST:$REMOTE_EVID/." "$LOCAL_EVID/remote/" || true

python3 - "$LOCAL_EVID" "$STAMP" <<'PY'
from pathlib import Path
import json, sys
evid = Path(sys.argv[1]); stamp = sys.argv[2]
docs = evid / "docs"; docs.mkdir(exist_ok=True)
proofs = (evid / "tests" / "proofs.out").read_text(errors="replace")
ok = all(x in proofs for x in ("NO_RUNTIME_DDL_OK","FAIL_CLOSED_OK","CONCURRENCY_MIGRATION_OK","RESIDUAL_ZERO_OK"))
gate = {
  "stamp": stamp,
  "STAGING_DEADLOCK_REMEDIATION_WAVE1BR": "GO" if ok else "NO-GO",
  "PROD_DEPLOY_REMEDIATION": "NO-GO_AWAITING_OWNER",
  "RERUN_MIGRATION_WAVE1B_PRODUCTION": "NO-GO_AWAITING_OWNER",
  "MIGRATION_WAVE2": "NO-GO_NOT_STARTED",
}
(docs / "GATE.json").write_text(json.dumps(gate, indent=2) + "\n")
report = f"""# Deadlock Remediation Wave 1-BR

Date stamp: `{stamp}`
Scope: staging proof only — no production remediation deploy, no Wave 1-B resume

## Containment (production abort)

See `ops/evidence/migration-wave1b-abort-20260804T0158Z/` — stalled 10k aborted; residual zero proved; orchestrator not restarted.

## Root cause

Runtime schema DDL (`CREATE TABLE IF NOT EXISTS hr_turns` / `inbound_cv_intake.ensure_schema`) competed with migration DML (`INSERT INTO candidates/applications`), producing relation-lock cycles and repeated deadlocks.

## Runtime DDL call sites converted (validate-only unless `WATHEFNI_SCHEMA_APPLY=1`)

- `schema_contract.py` — apply/require contract, advisory lock, fail-closed
- `inbound_cv_intake.ensure_schema` → apply/require
- `inbound_cv_processing.ensure_schema` → apply/require
- `durable_email_ingress.ensure_schema` → apply/require
- `inbound_cv_adapters` — `require_schema` only on hot paths
- `migration_wave1_cv_foundation.ensure_schema` → apply/require
- `app.ensure_schema` — validate core runtime tables; DDL only under apply flag + deploy advisory lock

## Replacement deployment migration

- `ops/migrate-schema-wave1br.sh` — ACK-gated, sets `WATHEFNI_SCHEMA_APPLY=1`, advisory lock `770911001`, applies schemas before workers resume

## Staging proof results

- no runtime DDL: `NO_RUNTIME_DDL_OK` in tests/proofs.out
- missing schema fail-closed: `FAIL_CLOSED_OK`
- concurrent migration DML + sibling workers: `CONCURRENCY_MIGRATION_OK`
- inject/retry/replay/rollback + residual zero: `RESIDUAL_ZERO_OK`

## Gate

**STAGING_DEADLOCK_REMEDIATION_WAVE1BR = {'GO' if ok else 'NO-GO'}**

**PROD deploy remediation = NO-GO** until owner approval  
**Rerun Migration Wave 1-B = NO-GO** until owner approval after production remediation deploy
"""
(docs / "REPORT.md").write_text(report)
# also top-level ops report
Path("/Users/azizalmulla/Desktop/claw/ops/DEADLOCK_REMEDIATION_WAVE1BR.md").write_text(report)
print("GATE", gate)
print("REPORT", docs / "REPORT.md")
raise SystemExit(0 if ok else 1)
PY

echo "LOCAL_EVID=$LOCAL_EVID"
