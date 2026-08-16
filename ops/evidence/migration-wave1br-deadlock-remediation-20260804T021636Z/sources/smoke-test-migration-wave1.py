"""Migration Wave 1 — Foundation + chunked CV intake (synthetic).

Proves: dry-run, commit, held-by-default (no auto-admit), checksum dedupe
without auto-merge, external ATS id preservation, chunk retry/resume, DLQ
replay, tenant isolation, progress/audit/rollback, residual 0.

Scale via env:
  MIGW1_COUNT_CORE=50     (local/core contract; default 50)
  MIGW1_COUNT_1K=1000     (set to run 1k lane; 0 to skip)
  MIGW1_COUNT_10K=10000   (set to run 10k lane; 0 to skip)

Requires WATHEFNI_MIGRATION_WAVE1=1 and staging/local postgres.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("WATHEFNI_MIGRATION_WAVE1", "1")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")
os.environ["WATHEFNI_MIGRATION_WAVE1"] = "1"

import app
import migration_wave1_cv_foundation as mig
from psycopg2.extras import Json

COMPANY_A = "MIGW1ALPHA"
COMPANY_B = "MIGW1BRAVO"
MARKER = "temporary_migration_wave1_smoke"
HELD = set(app.HELD_IMPORT_STATUSES)

COUNT_CORE = int(os.environ.get("MIGW1_COUNT_CORE", "50"))
COUNT_1K = int(os.environ.get("MIGW1_COUNT_1K", "0"))
COUNT_10K = int(os.environ.get("MIGW1_COUNT_10K", "0"))
STAGE_ROOT = Path(
    os.environ.get("WATHEFNI_MIGRATION_WAVE1_STAGE_ROOT")
    or tempfile.mkdtemp(prefix="migw1-stage-")
)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def setup_companies() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            mig.ensure_schema(cur)
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Migration Wave1 {company}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
        conn.commit()
    # Auto-admit ON at company settings — Wave1 path must still force OFF.
    # Must run after companies are committed (settings writes use a separate connection).
    app.set_company_setting(COMPANY_A, "intake_auto_admit_explicit", True)
    app.set_company_setting(COMPANY_B, "intake_auto_admit_explicit", True)


def cleanup_company(company: str) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT batch_id::text, import_batch_id::text FROM migration_batches WHERE company_code=%s",
                (company,),
            )
            batches = [dict(r) for r in cur.fetchall()]
            app_keys: list[str] = []
            for b in batches:
                cur.execute(
                    "SELECT app_key FROM migration_rows WHERE batch_id=%s AND app_key IS NOT NULL",
                    (b["batch_id"],),
                )
                app_keys.extend(str(r["app_key"]) for r in cur.fetchall() if r.get("app_key"))
            if app_keys:
                cur.execute("DELETE FROM candidate_documents WHERE app_key = ANY(%s)", (app_keys,))
                cur.execute(
                    "DELETE FROM file_registry WHERE company_code=%s AND subject_key = ANY(%s)",
                    (company, app_keys),
                )
                cur.execute(
                    "DELETE FROM application_lifecycle_events WHERE app_key = ANY(%s) OR company_code=%s",
                    (app_keys, company),
                )
                cur.execute(
                    "SELECT DISTINCT phone FROM applications WHERE company_code=%s AND app_key = ANY(%s)",
                    (company, app_keys),
                )
                phones = [str(r["phone"]) for r in cur.fetchall() if r.get("phone")]
                cur.execute(
                    "DELETE FROM applications WHERE company_code=%s AND app_key = ANY(%s)",
                    (company, app_keys),
                )
                if phones:
                    cur.execute(
                        """
                        DELETE FROM candidates c
                        WHERE c.phone = ANY(%s)
                          AND NOT EXISTS (SELECT 1 FROM applications a WHERE a.phone=c.phone)
                        """,
                        (phones,),
                    )
            for b in batches:
                if b.get("import_batch_id"):
                    cur.execute(
                        "DELETE FROM import_items WHERE batch_id=%s AND company_code=%s",
                        (b["import_batch_id"], company),
                    )
                    cur.execute(
                        "DELETE FROM import_batches WHERE batch_id=%s AND company_code=%s",
                        (b["import_batch_id"], company),
                    )
            cur.execute("DELETE FROM migration_events WHERE company_code=%s", (company,))
            cur.execute("DELETE FROM migration_chunk_jobs WHERE company_code=%s", (company,))
            cur.execute("DELETE FROM migration_rows WHERE company_code=%s", (company,))
            cur.execute("DELETE FROM migration_batches WHERE company_code=%s", (company,))
            # Sweep any leftover smoke apps by marker
            cur.execute(
                """
                DELETE FROM applications
                WHERE company_code=%s
                  AND (
                    coalesce(raw_json->'import'->>'migration_batch_id','') <> ''
                    OR coalesce(data_source_detail,'') LIKE 'bulk_import:%%'
                  )
                  AND status = ANY(%s)
                RETURNING app_key
                """,
                (company, list(HELD)),
            )
            leftover = cur.rowcount
        conn.commit()
    return {"batches": len(batches), "app_keys": len(app_keys), "leftover_deleted": leftover}


def teardown() -> None:
    for company in (COMPANY_A, COMPANY_B):
        cleanup_company(company)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM company_settings WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()
    # Stage dirs under STAGE_ROOT for these companies
    for sub in STAGE_ROOT.glob("migw1-*"):
        shutil.rmtree(sub, ignore_errors=True)


def _stage(name: str, count: int, *, duplicate_every: int | None = None) -> Path:
    dest = STAGE_ROOT / name
    if dest.exists():
        shutil.rmtree(dest)
    mig.generate_synthetic_cvs(
        dest,
        count=count,
        company_code=COMPANY_A,
        with_external_ids=True,
        duplicate_every=duplicate_every,
    )
    return dest


def _assert_held(batch_id: str, company: str) -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.app_key, a.status,
                       a.raw_json->'import'->>'external_id' AS external_id,
                       a.raw_json->'import'->>'auto_admit' AS auto_admit
                FROM migration_rows r
                JOIN applications a ON a.app_key=r.app_key AND a.company_code=r.company_code
                WHERE r.batch_id=%s AND r.company_code=%s AND r.status='committed'
                """,
                (batch_id, company),
            )
            rows = [dict(x) for x in cur.fetchall()]
    live = [r for r in rows if r["status"] not in HELD]
    auto = [r for r in rows if str(r.get("auto_admit") or "").lower() in {"true", "1"}]
    assert_true(not live, f"live statuses after wave1: {live[:5]}")
    assert_true(not auto, f"auto_admit stamped true: {auto[:5]}")
    with_ext = [r for r in rows if r.get("external_id")]
    return {"apps": len(rows), "with_external_id": len(with_ext), "held_ok": True}


def _residual(company: str) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)::int AS c FROM applications
                WHERE company_code=%s
                  AND coalesce(raw_json->'import'->>'migration_batch_id','') <> ''
                """,
                (company,),
            )
            apps = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT count(*)::int AS c FROM migration_rows WHERE company_code=%s AND status='committed'",
                (company,),
            )
            rows = int(cur.fetchone()["c"])
    return apps + rows


def run_scale_lane(label: str, count: int, *, chunk_size: int = 100) -> dict:
    print(f"\n=== scale lane {label} count={count} ===")
    stage = _stage(f"migw1-{label}", count, duplicate_every=max(50, count // 20) if count >= 50 else None)
    created = mig.create_staged_cv_batch(
        app,
        company_code=COMPANY_A,
        stage_dir=stage,
        dry_run=False,
        chunk_size=chunk_size,
        created_by="smoke-migw1",
        options={
            "extraction_policy": "defer",
            "qualification_mode": "synthetic_scale",
        },
    )
    assert_true(created.get("ok"), f"create failed: {created}")
    batch_id = created["batch_id"]
    t0 = time.time()
    done = mig.run_until_idle(app, batch_id=batch_id, company_code=COMPANY_A, max_loops=max(200, count // 5 + 50))
    elapsed = time.time() - t0
    assert_true(done.get("ok"), f"run_until_idle failed: {done}")
    prog = mig.batch_progress(app, batch_id=batch_id, company_code=COMPANY_A)
    batch = prog["batch"]
    rows = prog["rows_by_status"]
    jobs = prog["jobs_by_status"]
    assert_true(batch["status"] == "completed", f"{label} batch status={batch['status']} jobs={jobs} rows={rows}")
    assert_true(int(jobs.get("pending") or 0) == 0, f"{label} pending jobs")
    assert_true(int(jobs.get("dead_letter") or 0) == 0, f"{label} dead_letter not empty: {jobs}")
    assert_true(int(rows.get("pending") or 0) == 0, f"{label} pending rows")
    held = _assert_held(batch_id, COMPANY_A)
    committed = int(rows.get("committed") or 0)
    duplicates = int(rows.get("duplicate") or 0)
    assert_true(committed + duplicates + int(rows.get("failed") or 0) + int(rows.get("invalid") or 0) == count,
                f"{label} row accounting {rows} != {count}")
    assert_true(duplicates > 0 or count < 50, f"{label} expected duplicates from duplicate_every")
    rb = mig.rollback_batch(app, batch_id=batch_id, company_code=COMPANY_A)
    assert_true(rb.get("ok"), f"rollback failed: {rb}")
    residual = _residual(COMPANY_A)
    assert_true(residual == 0, f"{label} residual after rollback={residual}")
    out = {
        "label": label,
        "count": count,
        "batch_id": batch_id,
        "elapsed_s": round(elapsed, 2),
        "committed": committed,
        "duplicates": duplicates,
        "held": held,
        "rollback": rb.get("deleted"),
        "residual": residual,
    }
    print(json.dumps(out, indent=2))
    return out


def run_core() -> dict:
    print("=== core contract ===")
    assert_true(mig.migration_wave1_enabled(), "flag off")
    honesty = mig.honesty_payload()
    assert_true(honesty["auto_admit"] is False, "honesty auto_admit")
    assert_true(honesty["millions_claim"] is False, "honesty millions")
    assert_true(honesty["real_customer_data"] is False, "honesty real data")

    # Dry-run
    stage_dry = _stage("migw1-dry", 12, duplicate_every=4)
    dry = mig.create_staged_cv_batch(
        app, company_code=COMPANY_A, stage_dir=stage_dry, dry_run=True, chunk_size=5, created_by="smoke"
    )
    assert_true(dry.get("ok"), f"dry create: {dry}")
    dry_done = mig.run_until_idle(app, batch_id=dry["batch_id"], company_code=COMPANY_A)
    assert_true(dry_done.get("ok"), f"dry run: {dry_done}")
    dry_prog = mig.batch_progress(app, batch_id=dry["batch_id"], company_code=COMPANY_A)
    assert_true(dry_prog["batch"]["status"] == "completed", f"dry status {dry_prog}")
    assert_true(int(dry_prog["rows_by_status"].get("valid") or 0) > 0, "dry valid missing")
    assert_true(int(dry_prog["rows_by_status"].get("duplicate") or 0) > 0, "dry dupes missing")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::int AS c FROM applications WHERE company_code=%s",
                (COMPANY_A,),
            )
            assert_true(int(cur.fetchone()["c"]) == 0, "dry-run must not create applications")

    # Commit + external ids + no auto-admit despite company setting ON
    stage = _stage("migw1-core", COUNT_CORE, duplicate_every=10)
    created = mig.create_staged_cv_batch(
        app,
        company_code=COMPANY_A,
        stage_dir=stage,
        dry_run=False,
        chunk_size=10,
        created_by="smoke",
        options={"extraction_policy": "enqueue"},
    )
    assert_true(created.get("ok"), f"create: {created}")
    batch_id = created["batch_id"]

    # Resume: process one chunk, then finish
    w1 = mig.run_worker(
        app,
        company_code=COMPANY_A,
        batch_id=batch_id,
        limit=1,
        worker_id="smoke-resume-1",
    )
    assert_true(len(w1.get("processed") or []) == 1, f"resume first chunk: {w1}")
    mid = mig.batch_progress(app, batch_id=batch_id, company_code=COMPANY_A)
    assert_true(int(mid["jobs_by_status"].get("completed") or 0) == 1, f"mid jobs {mid['jobs_by_status']}")
    assert_true(int(mid["jobs_by_status"].get("pending") or 0) > 0, "expected remaining pending for resume")
    done = mig.run_until_idle(app, batch_id=batch_id, company_code=COMPANY_A)
    assert_true(done.get("ok"), f"resume finish: {done}")
    prog = mig.batch_progress(app, batch_id=batch_id, company_code=COMPANY_A)
    assert_true(prog["batch"]["status"] == "completed", f"core status {prog}")
    held = _assert_held(batch_id, COMPANY_A)
    assert_true(held["with_external_id"] > 0, "external_id not preserved")
    assert_true(int(prog["rows_by_status"].get("duplicate") or 0) > 0, "checksum dups missing")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)::int AS c,
                       count(*) FILTER (
                         WHERE status IN ('pending','running','retrying','waiting_quota','waiting_budget')
                       )::int AS active,
                       min(priority)::int AS min_priority,
                       max(priority)::int AS max_priority
                FROM intake_processing_jobs
                WHERE company_code=%s
                  AND job_type='cv_extraction'
                  AND payload->>'migration_batch_id'=%s
                  AND payload->>'workload_class'='migration'
                """,
                (COMPANY_A, batch_id),
            )
            tagged = dict(cur.fetchone())
    assert_true(int(tagged["c"]) == held["apps"], f"migration job tags missing: {tagged}")
    assert_true(
        int(tagged["min_priority"]) == mig.MIGRATION_EXTRACTION_PRIORITY
        and int(tagged["max_priority"]) == mig.MIGRATION_EXTRACTION_PRIORITY,
        f"migration priority not isolated: {tagged}",
    )

    # Exception queue surfaces duplicates
    exq = mig.exception_queue(app, batch_id=batch_id, company_code=COMPANY_A)
    assert_true(exq["count"] > 0, "exception queue empty")
    assert_true(any(e["status"] == "duplicate" for e in exq["exceptions"]), "no duplicate exceptions")

    # Audit events present
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::int AS c FROM migration_events WHERE batch_id=%s AND company_code=%s",
                (batch_id, COMPANY_A),
            )
            ev = int(cur.fetchone()["c"])
    assert_true(ev >= 2, f"audit events too few: {ev}")

    # Retry + DLQ: inject fail until attempts exhaust on a fresh tiny batch
    stage_r = _stage("migw1-retry", 8)
    created_r = mig.create_staged_cv_batch(
        app,
        company_code=COMPANY_A,
        stage_dir=stage_r,
        dry_run=False,
        chunk_size=8,
        created_by="smoke-retry",
        options={"extraction_policy": "defer"},
    )
    rid = created_r["batch_id"]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE migration_chunk_jobs SET max_attempts=2 WHERE batch_id=%s",
                (rid,),
            )
        conn.commit()
    os.environ["WATHEFNI_MIGRATION_WAVE1_INJECT_DB_ERROR_UNTIL"] = "2"
    try:
        for _ in range(8):
            out = mig.run_worker(
                app,
                company_code=COMPANY_A,
                batch_id=rid,
                limit=1,
                worker_id="smoke-inject",
            )
            p = mig.batch_progress(app, batch_id=rid, company_code=COMPANY_A)
            print("inject_loop", json.dumps({"worker": out, "jobs": p.get("jobs_by_status")}, default=str))
            if int(p["jobs_by_status"].get("dead_letter") or 0) > 0:
                break
            time.sleep(0.2)
        assert_true(
            int(mig.batch_progress(app, batch_id=rid, company_code=COMPANY_A)["jobs_by_status"].get("dead_letter") or 0) > 0,
            "expected dead_letter after inject",
        )
    finally:
        os.environ["WATHEFNI_MIGRATION_WAVE1_INJECT_DB_ERROR_UNTIL"] = "0"
    replay = mig.replay_dead_letters(app, batch_id=rid, company_code=COMPANY_A)
    assert_true(replay.get("replayed", 0) >= 1, f"replay: {replay}")
    fin = mig.run_until_idle(app, batch_id=rid, company_code=COMPANY_A)
    assert_true(fin.get("ok"), f"after replay: {fin}")
    assert_true(
        mig.batch_progress(app, batch_id=rid, company_code=COMPANY_A)["batch"]["status"] == "completed",
        "retry batch not completed",
    )

    # Tenant isolation: B must not see A's batch or apps
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::int AS c FROM migration_batches WHERE batch_id=%s AND company_code=%s",
                (batch_id, COMPANY_B),
            )
            assert_true(int(cur.fetchone()["c"]) == 0, "cross-tenant batch leak")
            cur.execute(
                "SELECT count(*)::int AS c FROM applications WHERE company_code=%s AND app_key IN "
                "(SELECT app_key FROM migration_rows WHERE batch_id=%s AND app_key IS NOT NULL)",
                (COMPANY_B, batch_id),
            )
            assert_true(int(cur.fetchone()["c"]) == 0, "cross-tenant app leak")
    b_prog = mig.batch_progress(app, batch_id=batch_id, company_code=COMPANY_B)
    assert_true(b_prog.get("ok") is False, "B should not load A's batch")

    # Stage company B small batch and confirm isolation both ways
    stage_b = STAGE_ROOT / "migw1-bravo"
    if stage_b.exists():
        shutil.rmtree(stage_b)
    mig.generate_synthetic_cvs(stage_b, count=5, company_code=COMPANY_B, with_external_ids=True)
    b_created = mig.create_staged_cv_batch(
        app,
        company_code=COMPANY_B,
        stage_dir=stage_b,
        dry_run=False,
        chunk_size=5,
        created_by="smoke-b",
        options={"extraction_policy": "defer"},
    )
    mig.run_until_idle(app, batch_id=b_created["batch_id"], company_code=COMPANY_B)
    _assert_held(b_created["batch_id"], COMPANY_B)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)::int AS c
                FROM intake_processing_jobs
                WHERE payload->>'migration_batch_id' = ANY(%s)
                """,
                ([rid, b_created["batch_id"]],),
            )
            deferred_queue_jobs = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT DISTINCT d.extraction_status
                FROM migration_rows r
                JOIN candidate_documents d ON d.app_key=r.app_key
                WHERE r.batch_id=%s AND r.status='committed'
                """,
                (b_created["batch_id"],),
            )
            deferred_document_statuses = {
                str(r["extraction_status"]) for r in cur.fetchall()
            }
    assert_true(
        deferred_queue_jobs == 0,
        f"deferred migration created extraction jobs={deferred_queue_jobs}",
    )
    assert_true(
        deferred_document_statuses == {"deferred_migration"},
        f"deferred document status mismatch={deferred_document_statuses}",
    )

    # Rollback core + residual
    rb = mig.rollback_batch(app, batch_id=batch_id, company_code=COMPANY_A)
    assert_true(rb.get("ok"), f"rollback core: {rb}")
    assert_true(
        int((rb.get("residual") or {}).get("queue_jobs_active") or 0) == 0,
        f"queue residual after rollback: {rb}",
    )
    assert_true(
        int((rb.get("extraction_jobs") or {}).get("cancelled") or 0) == int(tagged["active"]),
        f"rollback did not cancel all extraction jobs: {rb}",
    )
    rb_b = mig.rollback_batch(app, batch_id=b_created["batch_id"], company_code=COMPANY_B)
    assert_true(rb_b.get("ok"), f"rollback b: {rb_b}")
    mig.rollback_batch(app, batch_id=rid, company_code=COMPANY_A)
    residual = _residual(COMPANY_A) + _residual(COMPANY_B)
    assert_true(residual == 0, f"core residual={residual}")

    return {
        "dry_run": dry_prog["rows_by_status"],
        "core_batch": batch_id,
        "held": held,
        "exception_queue": exq["count"],
        "audit_events": ev,
        "retry_replayed": replay.get("replayed"),
        "tagged_extraction_jobs": int(tagged["c"]),
        "migration_queue_priority": int(tagged["min_priority"]),
        "deferred_queue_jobs": deferred_queue_jobs,
        "deferred_document_statuses": sorted(deferred_document_statuses),
        "rollback_cancelled_extraction_jobs": int(
            (rb.get("extraction_jobs") or {}).get("cancelled") or 0
        ),
        "rollback_queue_residual": int(
            (rb.get("residual") or {}).get("queue_jobs_active") or 0
        ),
        "rollback_attempts": rb.get("rollback_attempts"),
        "residual": residual,
    }


def main() -> None:
    print("MIGRATION_WAVE1_SMOKE_START")
    print(json.dumps({"core": COUNT_CORE, "1k": COUNT_1K, "10k": COUNT_10K, "stage_root": str(STAGE_ROOT)}))
    setup_companies()
    results: dict = {"honesty": mig.honesty_payload()}
    try:
        results["core"] = run_core()
        if COUNT_1K > 0:
            results["lane_1k"] = run_scale_lane("1k", COUNT_1K)
        if COUNT_10K > 0:
            results["lane_10k"] = run_scale_lane("10k", COUNT_10K, chunk_size=100)
        results["ok"] = True
        results["verdict"] = "PASS"
        print(json.dumps(results, indent=2, default=str))
        print("MIGRATION_WAVE1_SMOKE_PASS")
    except Exception as exc:
        results["ok"] = False
        results["verdict"] = "FAIL"
        results["error"] = str(exc)
        print(json.dumps(results, indent=2, default=str))
        print(f"MIGRATION_WAVE1_SMOKE_FAIL: {exc}")
        raise
    finally:
        teardown()
        print("MIGRATION_WAVE1_SMOKE_TEARDOWN_DONE")


if __name__ == "__main__":
    main()
