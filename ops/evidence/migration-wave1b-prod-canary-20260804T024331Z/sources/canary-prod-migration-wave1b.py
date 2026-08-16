"""Migration Wave 1-B — production WATHEFNI synthetic canary.

Proves dry-run, chunked intake, retry/resume/DLQ, duplicates, external ATS IDs,
held-by-default, no auto-admit, tenant isolation, audit/progress/rollback,
1k + 10k synthetic CVs, residual 0.

WATHEFNI-only for scale lanes. Ephemeral isolation tenants (MIGW1ALPHA/BRAVO)
are created only for isolation proof and fully removed. Never deletes the
WATHEFNI company row. Synthetic fixtures only — no real customer files.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

os.environ.setdefault("WATHEFNI_MIGRATION_WAVE1", "1")
os.environ.setdefault("WATHEFNI_MIGRATION_WAVE1_SYNTHETIC_ONLY", "1")
os.environ.setdefault("WATHEFNI_ATTENDANCE_CAPTURE_INGEST", "off")
# Canary process expands allowlist for ephemeral isolation tenants only.
os.environ["WATHEFNI_MIGRATION_WAVE1_COMPANIES"] = "WATHEFNI,MIGW1ALPHA,MIGW1BRAVO"
os.environ["WATHEFNI_MIGRATION_WAVE1"] = "1"

import app
import migration_wave1_cv_foundation as mig
from psycopg2.extras import Json

WATHEFNI = "WATHEFNI"
ISO_A = "MIGW1ALPHA"
ISO_B = "MIGW1BRAVO"
MARKER = "temporary_migration_wave1b_prod_canary"
HELD = set(app.HELD_IMPORT_STATUSES)

COUNT_CORE = int(os.environ.get("MIGW1_COUNT_CORE", "50"))
COUNT_1K = int(os.environ.get("MIGW1_COUNT_1K", "1000"))
COUNT_10K = int(os.environ.get("MIGW1_COUNT_10K", "10000"))
EVID = Path(os.environ.get("MIGW1B_EVID") or tempfile.mkdtemp(prefix="migw1b-evid-"))
STAGE_ROOT = Path(
    os.environ.get("WATHEFNI_MIGRATION_WAVE1_STAGE_ROOT")
    or (Path(os.environ.get("WATHEFNI_WORKSPACE") or "/tmp") / "migration_wave1b_canary")
)


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def assert_production() -> None:
    assert_true(os.environ.get("WATHEFNI_ENV") == "production", "WATHEFNI_ENV!=production")
    assert_true(
        (os.environ.get("WATHEFNI_EXPECTED_DATABASE_NAME") or "") == "wathefni",
        "expected db wathefni",
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database() AS db")
            db = dict(cur.fetchone())["db"]
    assert_true(db == "wathefni", f"db={db}")
    assert_true(mig.migration_wave1_enabled(), "flag off")
    assert_true(mig.migration_wave1_synthetic_only(), "synthetic_only off")
    ingest = (os.environ.get("WATHEFNI_ATTENDANCE_CAPTURE_INGEST") or "off").lower()
    assert_true(ingest in {"off", "0", "false", "no", ""}, f"ingest={ingest}")


def setup_isolation_companies() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            mig.ensure_schema(cur)
            for company in (ISO_A, ISO_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Migration Wave1B iso {company}", Json({"smoke": MARKER}), Json({"smoke": MARKER})),
                )
        conn.commit()
    app.set_company_setting(ISO_A, "intake_auto_admit_explicit", True)
    app.set_company_setting(ISO_B, "intake_auto_admit_explicit", True)


def cleanup_isolation_company(company: str) -> dict:
    """Full cleanup for ephemeral isolation tenants only — never call for WATHEFNI."""
    assert_true(company != WATHEFNI, "refuse cleanup of WATHEFNI company")
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
            cur.execute("DELETE FROM company_settings WHERE company_code=%s", (company,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
        conn.commit()
    return {"company": company, "batches": len(batches), "app_keys": len(app_keys)}


def cleanup_wathefni_canary_batches() -> dict:
    """Rollback/delete only this canary's explicit created_by scope — keep company."""
    deleted = {"batches": 0, "apps": 0}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT batch_id::text FROM migration_batches
                WHERE company_code=%s
                  AND coalesce(created_by,'') LIKE 'canary-migw1b-%%'
                """,
                (WATHEFNI,),
            )
            batch_ids = [str(r["batch_id"]) for r in cur.fetchall()]
        conn.commit()
    for bid in batch_ids:
        mig.rollback_batch(app, batch_id=bid, company_code=WATHEFNI)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for bid in batch_ids:
                cur.execute(
                    "SELECT import_batch_id::text AS id FROM migration_batches WHERE batch_id=%s",
                    (bid,),
                )
                row = cur.fetchone() or {}
                iid = row.get("id")
                if iid:
                    cur.execute(
                        "DELETE FROM import_items WHERE batch_id=%s AND company_code=%s",
                        (iid, WATHEFNI),
                    )
                    cur.execute(
                        "DELETE FROM import_batches WHERE batch_id=%s AND company_code=%s",
                        (iid, WATHEFNI),
                    )
                cur.execute("DELETE FROM migration_events WHERE batch_id=%s", (bid,))
                cur.execute("DELETE FROM migration_chunk_jobs WHERE batch_id=%s", (bid,))
                cur.execute("DELETE FROM migration_rows WHERE batch_id=%s", (bid,))
                cur.execute("DELETE FROM migration_batches WHERE batch_id=%s", (bid,))
                deleted["batches"] += 1
            if batch_ids:
                # Last-resort sweep is restricted to the exact batches selected
                # above; never delete another migration's held applications.
                cur.execute(
                    """
                    DELETE FROM applications
                    WHERE company_code=%s
                      AND raw_json->'import'->>'migration_batch_id' = ANY(%s)
                      AND coalesce(raw_json->'import'->>'authority_label','') = 'held'
                      AND status = ANY(%s)
                    RETURNING app_key
                    """,
                    (WATHEFNI, batch_ids, list(HELD)),
                )
                deleted["apps"] = cur.rowcount
        conn.commit()
    return deleted


def residual() -> dict:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)::int AS c FROM applications
                WHERE company_code=%s
                  AND coalesce(raw_json->'import'->>'migration_batch_id','') <> ''
                """,
                (WATHEFNI,),
            )
            wathefni_apps = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*)::int AS c FROM migration_rows
                WHERE company_code=%s AND status='committed'
                """,
                (WATHEFNI,),
            )
            wathefni_rows = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT count(*)::int AS c FROM companies WHERE company_code = ANY(%s)",
                ([ISO_A, ISO_B],),
            )
            iso_companies = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT count(*)::int AS c FROM applications WHERE company_code = ANY(%s)",
                ([ISO_A, ISO_B],),
            )
            iso_apps = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*)::int AS c FROM migration_batches
                WHERE company_code=%s AND coalesce(metadata->>'wave','')='migration_wave1'
                """,
                (WATHEFNI,),
            )
            wathefni_batches = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*)::int AS c
                FROM intake_processing_jobs
                WHERE company_code=%s
                  AND job_type='cv_extraction'
                  AND payload->>'workload_class'='migration'
                  AND status IN ('pending','running','retrying','waiting_quota','waiting_budget')
                """,
                (WATHEFNI,),
            )
            active_migration_queue_jobs = int(cur.fetchone()["c"])
            cur.execute(
                "SELECT count(*)::int AS c FROM candidate_documents WHERE extraction_status='deferred_migration'"
            )
            deferred_docs = int(cur.fetchone()["c"])
    total = (
        wathefni_apps
        + wathefni_rows
        + iso_companies
        + iso_apps
        + wathefni_batches
        + active_migration_queue_jobs
        + deferred_docs
    )
    return {
        "wathefni_apps": wathefni_apps,
        "wathefni_rows": wathefni_rows,
        "wathefni_batches": wathefni_batches,
        "iso_companies": iso_companies,
        "iso_apps": iso_apps,
        "active_migration_queue_jobs": active_migration_queue_jobs,
        "deferred_docs": deferred_docs,
        "total": total,
    }


def _stage(name: str, count: int, *, company: str, duplicate_every: int | None = None) -> Path:
    dest = STAGE_ROOT / name
    if dest.exists():
        shutil.rmtree(dest)
    mig.generate_synthetic_cvs(
        dest,
        count=count,
        company_code=company,
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
    assert_true(not live, f"live statuses: {live[:5]}")
    assert_true(not auto, f"auto_admit true: {auto[:5]}")
    with_ext = [r for r in rows if r.get("external_id")]
    return {"apps": len(rows), "with_external_id": len(with_ext), "held_ok": True}


def run_scale_lane(label: str, count: int, *, chunk_size: int = 100) -> dict:
    print(f"\n=== scale lane {label} count={count} company={WATHEFNI} ===")
    stage = _stage(
        f"migw1b-{label}",
        count,
        company=WATHEFNI,
        duplicate_every=max(50, count // 20) if count >= 50 else None,
    )
    created = mig.create_staged_cv_batch(
        app,
        company_code=WATHEFNI,
        stage_dir=stage,
        dry_run=False,
        chunk_size=chunk_size,
        created_by=f"canary-migw1b-{label}",
        options={
            "extraction_policy": "defer",
            "qualification_mode": "synthetic_scale",
        },
    )
    assert_true(created.get("ok"), f"create failed: {created}")
    batch_id = created["batch_id"]
    t0 = time.time()
    done = mig.run_until_idle(
        app, batch_id=batch_id, company_code=WATHEFNI, max_loops=max(200, count // 5 + 50)
    )
    elapsed = time.time() - t0
    assert_true(done.get("ok"), f"run_until_idle failed: {done}")
    prog = mig.batch_progress(app, batch_id=batch_id, company_code=WATHEFNI)
    batch = prog["batch"]
    rows = prog["rows_by_status"]
    jobs = prog["jobs_by_status"]
    assert_true(batch["status"] == "completed", f"{label} status={batch['status']} jobs={jobs} rows={rows}")
    assert_true(int(jobs.get("pending") or 0) == 0, f"{label} pending jobs")
    assert_true(int(jobs.get("dead_letter") or 0) == 0, f"{label} dead_letter: {jobs}")
    held = _assert_held(batch_id, WATHEFNI)
    committed = int(rows.get("committed") or 0)
    duplicates = int(rows.get("duplicate") or 0)
    assert_true(
        committed + duplicates + int(rows.get("failed") or 0) + int(rows.get("invalid") or 0) == count,
        f"{label} accounting {rows} != {count}",
    )
    assert_true(duplicates > 0, f"{label} expected duplicates")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*)::int AS c
                FROM intake_processing_jobs
                WHERE company_code=%s
                  AND job_type='cv_extraction'
                  AND payload->>'migration_batch_id'=%s
                """,
                (WATHEFNI, batch_id),
            )
            deferred_queue_jobs = int(cur.fetchone()["c"])
    assert_true(
        deferred_queue_jobs == 0,
        f"{label} deferred extraction created queue jobs={deferred_queue_jobs}",
    )
    rb = mig.rollback_batch(app, batch_id=batch_id, company_code=WATHEFNI)
    assert_true(rb.get("ok"), f"rollback failed: {rb}")
    out = {
        "label": label,
        "count": count,
        "batch_id": batch_id,
        "elapsed_s": round(elapsed, 2),
        "committed": committed,
        "duplicates": duplicates,
        "held": held,
        "rollback": rb.get("deleted"),
    }
    print(json.dumps(out, indent=2))
    return out


def run_core() -> dict:
    print("=== core contract (prod synthetic) ===")
    honesty = mig.honesty_payload()
    assert_true(honesty["auto_admit"] is False, "honesty auto_admit")
    assert_true(honesty["millions_claim"] is False, "honesty millions")
    assert_true(honesty["real_customer_data"] is False, "honesty real data")

    # Allowlist refuse
    bad = mig.create_staged_cv_batch(
        app, company_code="NOTALLOWED", stage_dir=STAGE_ROOT, dry_run=True
    )
    # stage may be missing — either way must refuse allowlist first if dir exists,
    # or we create empty then... ensure refuse path:
    assert_true(
        bad.get("error") in {"company_not_allowlisted", "stage_dir_missing", "no_cv_files"},
        f"unexpected: {bad}",
    )
    # Force allowlist check with a temp stage
    tmp = STAGE_ROOT / "allowlist-check"
    mig.generate_synthetic_cvs(tmp, count=1, company_code="NOTALLOWED")
    bad2 = mig.create_staged_cv_batch(app, company_code="NOTALLOWED", stage_dir=tmp, dry_run=True)
    assert_true(bad2.get("error") == "company_not_allowlisted", f"allowlist: {bad2}")

    # Dry-run on WATHEFNI
    stage_dry = _stage("migw1b-dry", 12, company=WATHEFNI, duplicate_every=4)
    dry = mig.create_staged_cv_batch(
        app,
        company_code=WATHEFNI,
        stage_dir=stage_dry,
        dry_run=True,
        chunk_size=5,
        created_by="canary-migw1b-dry",
    )
    assert_true(dry.get("ok"), f"dry create: {dry}")
    dry_done = mig.run_until_idle(app, batch_id=dry["batch_id"], company_code=WATHEFNI)
    assert_true(dry_done.get("ok"), f"dry run: {dry_done}")
    dry_prog = mig.batch_progress(app, batch_id=dry["batch_id"], company_code=WATHEFNI)
    assert_true(dry_prog["batch"]["status"] == "completed", f"dry status {dry_prog}")
    assert_true(int(dry_prog["rows_by_status"].get("valid") or 0) > 0, "dry valid missing")
    assert_true(int(dry_prog["rows_by_status"].get("duplicate") or 0) > 0, "dry dupes missing")

    # Commit + resume on WATHEFNI
    stage = _stage("migw1b-core", COUNT_CORE, company=WATHEFNI, duplicate_every=10)
    created = mig.create_staged_cv_batch(
        app,
        company_code=WATHEFNI,
        stage_dir=stage,
        dry_run=False,
        chunk_size=10,
        created_by="canary-migw1b-core",
        options={"extraction_policy": "enqueue"},
    )
    assert_true(created.get("ok"), f"create: {created}")
    batch_id = created["batch_id"]
    w1 = mig.run_worker(
        app,
        company_code=WATHEFNI,
        batch_id=batch_id,
        limit=1,
        worker_id="canary-resume-1",
    )
    assert_true(len(w1.get("processed") or []) == 1, f"resume first: {w1}")
    mid = mig.batch_progress(app, batch_id=batch_id, company_code=WATHEFNI)
    assert_true(int(mid["jobs_by_status"].get("completed") or 0) == 1, f"mid {mid['jobs_by_status']}")
    assert_true(int(mid["jobs_by_status"].get("pending") or 0) > 0, "expected remaining pending")
    done = mig.run_until_idle(app, batch_id=batch_id, company_code=WATHEFNI)
    assert_true(done.get("ok"), f"resume finish: {done}")
    prog = mig.batch_progress(app, batch_id=batch_id, company_code=WATHEFNI)
    assert_true(prog["batch"]["status"] == "completed", f"core status {prog}")
    held = _assert_held(batch_id, WATHEFNI)
    assert_true(held["with_external_id"] > 0, "external_id not preserved")
    assert_true(int(prog["rows_by_status"].get("duplicate") or 0) > 0, "checksum dups missing")
    exq = mig.exception_queue(app, batch_id=batch_id, company_code=WATHEFNI)
    assert_true(exq["count"] > 0, "exception queue empty")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::int AS c FROM migration_events WHERE batch_id=%s AND company_code=%s",
                (batch_id, WATHEFNI),
            )
            ev = int(cur.fetchone()["c"])
    assert_true(ev >= 2, f"audit events too few: {ev}")

    # Retry + DLQ
    stage_r = _stage("migw1b-retry", 8, company=WATHEFNI)
    created_r = mig.create_staged_cv_batch(
        app,
        company_code=WATHEFNI,
        stage_dir=stage_r,
        dry_run=False,
        chunk_size=8,
        created_by="canary-migw1b-retry",
        options={"extraction_policy": "defer"},
    )
    rid = created_r["batch_id"]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE migration_chunk_jobs SET max_attempts=2 WHERE batch_id=%s", (rid,))
        conn.commit()
    os.environ["WATHEFNI_MIGRATION_WAVE1_INJECT_FAIL_UNTIL"] = "2"
    try:
        for _ in range(8):
            mig.run_worker(
                app,
                company_code=WATHEFNI,
                batch_id=rid,
                limit=1,
                worker_id="canary-inject",
            )
            p = mig.batch_progress(app, batch_id=rid, company_code=WATHEFNI)
            if int(p["jobs_by_status"].get("dead_letter") or 0) > 0:
                break
            time.sleep(0.2)
        assert_true(
            int(mig.batch_progress(app, batch_id=rid, company_code=WATHEFNI)["jobs_by_status"].get("dead_letter") or 0)
            > 0,
            "expected dead_letter",
        )
    finally:
        os.environ["WATHEFNI_MIGRATION_WAVE1_INJECT_FAIL_UNTIL"] = "0"
    replay = mig.replay_dead_letters(app, batch_id=rid, company_code=WATHEFNI)
    assert_true(replay.get("replayed", 0) >= 1, f"replay: {replay}")
    fin = mig.run_until_idle(app, batch_id=rid, company_code=WATHEFNI)
    assert_true(fin.get("ok"), f"after replay: {fin}")

    # Tenant isolation via ephemeral companies
    stage_a = _stage("migw1b-iso-a", 5, company=ISO_A)
    a_created = mig.create_staged_cv_batch(
        app,
        company_code=ISO_A,
        stage_dir=stage_a,
        dry_run=False,
        chunk_size=5,
        created_by="canary-iso-a",
        options={"extraction_policy": "defer"},
    )
    mig.run_until_idle(app, batch_id=a_created["batch_id"], company_code=ISO_A)
    _assert_held(a_created["batch_id"], ISO_A)
    b_prog = mig.batch_progress(app, batch_id=a_created["batch_id"], company_code=ISO_B)
    assert_true(b_prog.get("ok") is False, "ISO_B must not load ISO_A batch")
    w_prog = mig.batch_progress(app, batch_id=a_created["batch_id"], company_code=WATHEFNI)
    assert_true(w_prog.get("ok") is False, "WATHEFNI must not load ISO_A batch")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*)::int AS c FROM applications WHERE company_code=%s AND app_key IN "
                "(SELECT app_key FROM migration_rows WHERE batch_id=%s AND app_key IS NOT NULL)",
                (WATHEFNI, a_created["batch_id"]),
            )
            assert_true(int(cur.fetchone()["c"]) == 0, "cross-tenant app leak to WATHEFNI")

    stage_b = _stage("migw1b-iso-b", 5, company=ISO_B)
    b_created = mig.create_staged_cv_batch(
        app,
        company_code=ISO_B,
        stage_dir=stage_b,
        dry_run=False,
        chunk_size=5,
        created_by="canary-iso-b",
        options={"extraction_policy": "defer"},
    )
    mig.run_until_idle(app, batch_id=b_created["batch_id"], company_code=ISO_B)
    _assert_held(b_created["batch_id"], ISO_B)

    # Rollback core batches on WATHEFNI + iso
    for bid in (batch_id, rid, dry["batch_id"]):
        mig.rollback_batch(app, batch_id=bid, company_code=WATHEFNI)
    mig.rollback_batch(app, batch_id=a_created["batch_id"], company_code=ISO_A)
    mig.rollback_batch(app, batch_id=b_created["batch_id"], company_code=ISO_B)

    return {
        "dry_run": dry_prog["rows_by_status"],
        "core_batch": batch_id,
        "held": held,
        "exception_queue": exq["count"],
        "audit_events": ev,
        "retry_replayed": replay.get("replayed"),
    }


def main() -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    print("MIGRATION_WAVE1B_CANARY_START")
    meta = {
        "core": COUNT_CORE,
        "1k": COUNT_1K,
        "10k": COUNT_10K,
        "stage_root": str(STAGE_ROOT),
        "evid": str(EVID),
        "db_expected": "wathefni",
    }
    print(json.dumps(meta))
    assert_production()
    # Wave 1-BR: runtime must never mutate schema during qualification.
    try:
        import schema_contract as _sc

        assert_true(not _sc.schema_apply_allowed(), "WATHEFNI_SCHEMA_APPLY must be unset")
        _sc.reset_counters()
    except ImportError:
        _sc = None  # type: ignore[assignment]
    preflight_residual = residual()
    assert_true(
        preflight_residual["total"] == 0,
        f"refuse pre-existing migration canary residual: {preflight_residual}",
    )
    setup_isolation_companies()
    results: dict = {"honesty": mig.honesty_payload(), "fail": 0, "pass": 0}
    try:
        results["core"] = run_core()
        results["pass"] += 1
        if COUNT_1K > 0:
            results["lane_1k"] = run_scale_lane("1k", COUNT_1K)
            results["pass"] += 1
        if COUNT_10K > 0:
            results["lane_10k"] = run_scale_lane("10k", COUNT_10K, chunk_size=100)
            results["pass"] += 1
        if _sc is not None:
            counters = _sc.counters()
            results["schema_counters"] = counters
            assert_true(counters.get("apply_calls", 0) == 0, f"runtime DDL detected: {counters}")
            assert_true(not _sc.schema_apply_allowed(), "SCHEMA_APPLY enabled mid-canary")
        results["ok"] = True
        results["verdict"] = "PASS"
        print(json.dumps(results, indent=2, default=str))
        print("MIGRATION_WAVE1B_CANARY_PASS")
        (EVID / "canary-result.json").write_text(json.dumps(results, indent=2, default=str))
    except Exception as exc:
        results["ok"] = False
        results["verdict"] = "FAIL"
        results["fail"] = 1
        results["error"] = str(exc)
        print(json.dumps(results, indent=2, default=str))
        print(f"MIGRATION_WAVE1B_CANARY_FAIL: {exc}")
        (EVID / "canary-result.json").write_text(json.dumps(results, indent=2, default=str))
        raise
    finally:
        cleanup_wathefni_canary_batches()
        cleanup_isolation_company(ISO_A)
        cleanup_isolation_company(ISO_B)
        res = residual()
        print(json.dumps({"residual": res}, indent=2))
        (EVID / "residual.json").write_text(json.dumps(res, indent=2))
        if res["total"] != 0:
            print(f"MIGRATION_WAVE1B_RESIDUAL_FAIL: {res}")
            raise SystemExit(2)
        print("MIGRATION_WAVE1B_RESIDUAL_0_OK")
        for sub in STAGE_ROOT.glob("migw1b-*"):
            shutil.rmtree(sub, ignore_errors=True)
        shutil.rmtree(STAGE_ROOT / "allowlist-check", ignore_errors=True)
        print("MIGRATION_WAVE1B_CANARY_TEARDOWN_DONE")


if __name__ == "__main__":
    main()
