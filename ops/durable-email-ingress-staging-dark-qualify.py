#!/usr/bin/env python3
"""Staging dark qualification for durable email ingress (no Postmark, workers stopped)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import Json, RealDictCursor

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "wathefni-orchestrator"
if ORCH.exists():
    sys.path.insert(0, str(ORCH))
else:
    sys.path.insert(0, str(ROOT))

UTC = timezone.utc
MARKER = "durable_email_ingress_staging_dark_v1"
COMPANY_A = "DARKINGA"
COMPANY_B = "DARKINGB"


def db():
    url = os.environ["WATHEFNI_DATABASE_URL"]
    return psycopg2.connect(url, cursor_factory=RealDictCursor)


def ok(name: str, detail: dict | None = None) -> dict:
    return {"name": name, "pass": True, "detail": detail or {}}


def bad(name: str, detail: dict | None = None) -> dict:
    return {"name": name, "pass": False, "detail": detail or {}}


def cleanup() -> dict:
    removed = {"rows": 0, "objects": 0}
    with db() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                for sql in (
                    "DELETE FROM intake_processing_job_events WHERE company_code=%s",
                    "DELETE FROM intake_processing_jobs WHERE company_code=%s",
                    "DELETE FROM intake_documents WHERE company_code=%s",
                    "DELETE FROM intake_submissions WHERE company_code=%s",
                    "DELETE FROM intake_quota_usage WHERE company_code=%s",
                    "DELETE FROM intake_tenant_queue_state WHERE company_code=%s",
                    "DELETE FROM inbound_messages WHERE company_code=%s",
                    "DELETE FROM intake_addresses WHERE company_code=%s",
                ):
                    cur.execute(sql, (company,))
                    removed["rows"] += cur.rowcount
        conn.commit()
    root = Path(os.environ.get("WATHEFNI_INTAKE_QUARANTINE_DIR") or "")
    if root.exists():
        for company in (COMPANY_A, COMPANY_B):
            path = root / company
            if path.exists():
                for f in path.rglob("*"):
                    if f.is_file():
                        f.unlink()
                        removed["objects"] += 1
                for d in sorted(path.rglob("*"), reverse=True):
                    if d.is_dir():
                        try:
                            d.rmdir()
                        except OSError:
                            pass
                try:
                    path.rmdir()
                except OSError:
                    pass
    return removed


def main() -> int:
    from durable_email_ingress import (
        IngressConfig,
        LocalQuarantineStore,
        ensure_schema,
        enqueue_job,
        orphan_storage_report,
        replay_dead_letter,
        run_worker_once,
        sign_quarantine_download,
        verify_quarantine_download,
        RetryableJobError,
        DeferredJob,
    )
    from intake_malware_scanner import build_malware_scanner_from_env, signature_age_hours
    from intake_quarantine_storage import build_quarantine_storage_from_env

    results: list[dict] = []
    config = IngressConfig.from_env(os.environ.get("WATHEFNI_WORKSPACE"))

    # Schema additive
    with db() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
        conn.commit()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_name = ANY(%s)
                ORDER BY 1
                """,
                (
                    [
                        "intake_submissions",
                        "intake_documents",
                        "intake_processing_jobs",
                        "intake_processing_job_events",
                        "intake_tenant_queue_state",
                        "intake_quota_usage",
                    ],
                ),
            )
            tables = [r["table_name"] for r in cur.fetchall()]
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name='intake_documents'
                  AND column_name = ANY(%s)
                ORDER BY 1
                """,
                (["scan_engine", "scan_signature_version", "scanned_at", "scan_result", "scan_evidence"],),
            )
            cols = [r["column_name"] for r in cur.fetchall()]
    results.append(
        ok("additive_schema", {"tables": tables, "scan_columns": cols})
        if len(tables) == 6 and len(cols) == 5
        else bad("additive_schema", {"tables": tables, "scan_columns": cols})
    )

    # Zero residue before synthetic (baseline)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM intake_submissions WHERE company_code IN (%s,%s)) AS submissions,
                  (SELECT count(*) FROM intake_documents WHERE company_code IN (%s,%s)) AS documents,
                  (SELECT count(*) FROM intake_processing_jobs WHERE company_code IN (%s,%s)) AS jobs,
                  (SELECT count(*) FROM inbound_messages WHERE company_code IN (%s,%s)) AS messages
                """,
                (COMPANY_A, COMPANY_B) * 4,
            )
            baseline = dict(cur.fetchone())
    results.append(
        ok("deploy_created_no_synthetic_work", baseline)
        if all(int(baseline[k] or 0) == 0 for k in baseline)
        else bad("deploy_created_no_synthetic_work", baseline)
    )

    # Storage adapter
    storage = build_quarantine_storage_from_env(os.environ.get("WATHEFNI_WORKSPACE"))
    health = storage.health()
    data = b"dark-qualify-object\n"
    digest = hashlib.sha256(data).hexdigest()
    inbound_id = str(uuid.uuid4())
    ref = storage.write(
        company_code=COMPANY_A,
        inbound_id=inbound_id,
        ordinal=1,
        content_sha256=digest,
        data=data,
    )
    verified = storage.verify(ref.key, digest, len(data))
    results.append(
        ok(
            "quarantine_storage_adapter",
            {
                "backend": storage.backend_name,
                "health": health,
                "key": ref.key,
                "verified": verified.content_sha256 == digest,
            },
        )
        if health.get("writable") and verified.content_sha256 == digest
        else bad("quarantine_storage_adapter", {"health": health})
    )

    # Scanner adapter + safe files
    scanner = build_malware_scanner_from_env()
    shealth = scanner.health()
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean.pdf"
        clean.write_bytes(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
        eicar = Path(tmp) / "eicar.com"
        eicar.write_bytes(
            b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
        )
        clean_r = scanner.scan_path(clean)
        eicar_r = scanner.scan_path(eicar)
    age = signature_age_hours(shealth.get("signature_version") or clean_r.signature_version)
    results.append(
        ok(
            "malware_scanner_adapter",
            {
                "health": shealth,
                "clean": clean_r.to_record(),
                "eicar": eicar_r.to_record(),
                "signature_age_hours": age,
            },
        )
        if shealth.get("ok")
        and clean_r.state == "clean"
        and eicar_r.state == "malware"
        and (age is None or age <= 168)
        else bad(
            "malware_scanner_adapter",
            {
                "health": shealth,
                "clean": clean_r.to_record(),
                "eicar": eicar_r.to_record(),
                "signature_age_hours": age,
            },
        )
    )

    # Signed access tenant scope
    secret = os.environ.get("WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET") or ""
    doc_id = str(uuid.uuid4())
    exp = int(time.time()) + 300
    sig = sign_quarantine_download(
        company_code=COMPANY_A, document_id=doc_id, expires_at_epoch=exp, secret=secret
    )
    same = verify_quarantine_download(
        company_code=COMPANY_A,
        document_id=doc_id,
        expires_at_epoch=exp,
        signature=sig,
        secret=secret,
        now_epoch=int(time.time()),
    )
    cross = verify_quarantine_download(
        company_code=COMPANY_B,
        document_id=doc_id,
        expires_at_epoch=exp,
        signature=sig,
        secret=secret,
        now_epoch=int(time.time()),
    )
    results.append(
        ok("signed_access_tenant_scoped", {"same": same, "cross": cross})
        if same and not cross
        else bad("signed_access_tenant_scoped", {"same": same, "cross": cross})
    )

    # Synthetic queue matrix with noop handler (no candidate/OCR)
    def handler(job: dict):
        payload = job.get("payload") or {}
        mode = payload.get("mode")
        if mode == "fail_retry":
            raise RetryableJobError("synthetic_retry")
        if mode == "defer":
            raise DeferredJob(
                "waiting_quota",
                "synthetic_quota",
                datetime.now(UTC) + timedelta(seconds=30),
            )
        return {"ok": True, "mode": mode or "success"}

    with db() as conn:
        with conn.cursor() as cur:
            for company, mode, attempts_seed in (
                (COMPANY_A, "success", 0),
                (COMPANY_A, "fail_retry", 0),
                (COMPANY_B, "success", 0),
                (COMPANY_A, "defer", 0),
            ):
                job_id = str(uuid.uuid4())
                enqueue_job(
                    cur,
                    company_code=company,
                    job_type="intake_validation",
                    subject_type="synthetic",
                    subject_id=job_id,
                    idempotency_key=f"{MARKER}:{job_id}",
                    payload={"mode": mode, "marker": MARKER},
                    priority=100,
                    max_attempts=3 if mode == "fail_retry" else 5,
                )
            # Force a near-dead-letter job
            dead_key = f"{MARKER}:dead:{uuid.uuid4()}"
            cur.execute(
                """
                INSERT INTO intake_processing_jobs
                  (job_id, company_code, job_type, subject_type, subject_id, status,
                   attempts, max_attempts, idempotency_key, payload, available_at)
                VALUES (%s,%s,'intake_validation','synthetic',%s,'retrying',2,3,%s,%s,now())
                """,
                (
                    str(uuid.uuid4()),
                    COMPANY_A,
                    str(uuid.uuid4()),
                    dead_key,
                    Json({"mode": "fail_retry", "marker": MARKER}),
                ),
            )
        conn.commit()

    # Run worker passes in-process (systemd worker stays stopped)
    pass1 = run_worker_once(
        db_connect=db,
        handler=handler,
        worker_id="dark-qualify-1",
        config=config,
        limit=20,
    )
    # Expire a lease synthetically then reclaim
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE intake_processing_jobs
                SET status='running', lease_owner='crashed-worker',
                    lease_expires_at=now() - interval '1 minute', updated_at=now()
                WHERE job_id = (
                  SELECT job_id FROM intake_processing_jobs
                  WHERE company_code=%s AND status='pending' AND idempotency_key LIKE %s
                  ORDER BY created_at DESC LIMIT 1
                )
                """,
                (COMPANY_B, f"{MARKER}:%"),
            )
            if cur.rowcount == 0:
                enqueue_job(
                    cur,
                    company_code=COMPANY_B,
                    job_type="intake_validation",
                    subject_type="synthetic",
                    subject_id=str(uuid.uuid4()),
                    idempotency_key=f"{MARKER}:lease:{uuid.uuid4()}",
                    payload={"mode": "success", "marker": MARKER},
                    priority=50,
                    max_attempts=5,
                )
                conn.commit()
                cur.execute(
                    """
                    UPDATE intake_processing_jobs
                    SET status='running', lease_owner='crashed-worker',
                        lease_expires_at=now() - interval '1 minute', updated_at=now()
                    WHERE idempotency_key LIKE %s AND company_code=%s
                    """,
                    (f"{MARKER}:lease:%", COMPANY_B),
                )
        conn.commit()

    pass2 = run_worker_once(
        db_connect=db,
        handler=handler,
        worker_id="dark-qualify-2",
        config=config,
        limit=20,
    )
    # Drive fail_retry to dead_letter
    for _ in range(5):
        run_worker_once(
            db_connect=db,
            handler=handler,
            worker_id="dark-qualify-retry",
            config=config,
            limit=20,
        )

    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, count(*) AS n
                FROM intake_processing_jobs
                WHERE company_code IN (%s,%s)
                GROUP BY status ORDER BY 1
                """,
                (COMPANY_A, COMPANY_B),
            )
            by_status = {r["status"]: int(r["n"]) for r in cur.fetchall()}
            cur.execute(
                """
                SELECT job_id::text AS job_id, company_code
                FROM intake_processing_jobs
                WHERE company_code=%s AND status='dead_letter'
                ORDER BY created_at DESC LIMIT 1
                """,
                (COMPANY_A,),
            )
            dead = cur.fetchone()
    replayed = None
    if dead:
        replayed = replay_dead_letter(
            db_connect=db,
            company_code=dead["company_code"],
            job_id=dead["job_id"],
            actor="dark_qualify",
        )
        run_worker_once(
            db_connect=db,
            handler=handler,
            worker_id="dark-qualify-replay",
            config=config,
            limit=5,
        )

    results.append(
        ok(
            "synthetic_queue_matrix",
            {
                "pass1": pass1,
                "pass2": pass2,
                "by_status": by_status,
                "replayed": replayed,
            },
        )
        if by_status.get("dead_letter", 0) >= 1 or replayed
        else bad("synthetic_queue_matrix", {"by_status": by_status})
    )

    # Orphan report (dry)
    orphans = orphan_storage_report(db_connect=db, config=config, delete=False)
    results.append(ok("orphan_report", orphans))

    # Cleanup zero residue
    removed = cleanup()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM intake_submissions WHERE company_code IN (%s,%s)) AS submissions,
                  (SELECT count(*) FROM intake_documents WHERE company_code IN (%s,%s)) AS documents,
                  (SELECT count(*) FROM intake_processing_jobs WHERE company_code IN (%s,%s)) AS jobs,
                  (SELECT count(*) FROM intake_processing_job_events WHERE company_code IN (%s,%s)) AS events,
                  (SELECT count(*) FROM inbound_messages WHERE company_code IN (%s,%s)) AS messages
                """,
                (COMPANY_A, COMPANY_B) * 5,
            )
            left = dict(cur.fetchone())
    store = LocalQuarantineStore(config.quarantine_root)
    leftover_objs = [
        k for k, _ in (store.iter_object_keys() or []) if k.startswith(COMPANY_A) or k.startswith(COMPANY_B)
    ]
    results.append(
        ok("zero_residue", {"removed": removed, "left": left, "objects": leftover_objs})
        if all(int(left[k] or 0) == 0 for k in left) and not leftover_objs
        else bad("zero_residue", {"removed": removed, "left": left, "objects": leftover_objs})
    )

    # Gates
    inbound = str(os.environ.get("WATHEFNI_INBOUND_EMAIL") or "off").lower()
    results.append(
        ok("inbound_still_off", {"WATHEFNI_INBOUND_EMAIL": inbound})
        if inbound in {"off", "0", "false", "no", ""}
        else bad("inbound_still_off", {"WATHEFNI_INBOUND_EMAIL": inbound})
    )

    failed = [r for r in results if not r["pass"]]
    report = {
        "marker": MARKER,
        "checked_at": datetime.now(UTC).isoformat(),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }
    print(json.dumps(report, indent=2, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    # Load staging env if provided
    env_file = os.environ.get("WATHEFNI_POSTGRES_ENV")
    if env_file and Path(env_file).exists():
        for line in Path(env_file).read_text().splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)
    intake_env = "/root/.openclaw/secrets/wathefni-intake.staging.env"
    if Path(intake_env).exists():
        for line in Path(intake_env).read_text().splitlines():
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k] = v
    raise SystemExit(main())
