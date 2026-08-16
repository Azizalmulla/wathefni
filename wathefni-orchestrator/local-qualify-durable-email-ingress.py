#!/usr/bin/env python3
"""Local destructive-to-synthetic-data qualification for durable email ingress.

Requires an isolated test database selected through the normal Wathefni runtime
binding. It never calls Postmark, OCR, Mistral, GPT, Voyage, or outbound delivery.
All test tenants, rows, and quarantine objects are removed in ``finally``.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

ROOT = Path(tempfile.mkdtemp(prefix="wathefni-durable-ingress-qualification-"))
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if database_url:
    parsed_database = urlparse(database_url)
    env_file = ROOT / "postgres.test.env"
    env_file.write_text(f"WATHEFNI_DATABASE_URL={database_url}\n")
    os.environ["WATHEFNI_POSTGRES_ENV"] = str(env_file)
    os.environ["WATHEFNI_ENV"] = "test"
    os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = parsed_database.hostname or "127.0.0.1"
    os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = str(parsed_database.port or 5432)
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = parsed_database.path.lstrip("/")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-ingress-local-v1"
    )
elif not os.environ.get("WATHEFNI_POSTGRES_ENV"):
    raise RuntimeError(
        "Set WATHEFNI_POSTGRES_ENV or WATHEFNI_TEST_DATABASE_URL to an isolated test database."
    )
os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "local-qualification-secret")
os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(ROOT / "quarantine")
os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
os.environ["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"
os.environ["WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS"] = "60"
os.environ["WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS"] = "3"

import app  # noqa: E402
import durable_email_ingress as ingress  # noqa: E402


UTC = timezone.utc
COMPANIES = (
    "DURABLEONE",
    "DURABLETWO",
    "DURABLEFAIL",
    "DURABLEQUEUEA",
    "DURABLEQUEUEB",
    "DURABLEQUOTA",
    "DURABLELOADA",
    "DURABLELOADB",
)
MARKER = "durable_email_ingress_local_qualification"
RESULTS: list[dict[str, Any]] = []


def check(name: str, operation: Callable[[], Any]) -> Any:
    started = time.monotonic()
    try:
        detail = operation()
        RESULTS.append(
            {
                "name": name,
                "status": "PASS",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "detail": app.json_safe(detail),
            }
        )
        print(f"[PASS] {name}")
        return detail
    except Exception as exc:
        RESULTS.append(
            {
                "name": name,
                "status": "FAIL",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "detail": f"{type(exc).__name__}: {exc}",
            }
        )
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        raise


def assert_true(value: Any, message: str) -> None:
    if not value:
        raise AssertionError(message)


def pdf_bytes(label: str, *, encrypted: bool = False, pages: int = 1) -> bytes:
    page_objects = b"\n".join(
        f"{index + 3} 0 obj<</Type/Page/Parent 2 0 R>>endobj".encode()
        for index in range(max(1, pages))
    )
    encrypt = b"\n/Encrypt 90 0 R" if encrypted else b""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        + f"2 0 obj<</Type/Pages/Count {max(1, pages)}>>endobj\n".encode()
        + page_objects
        + encrypt
        + f"\n% synthetic {label}\n%%EOF\n".encode()
    )


def attachment(
    name: str, data: bytes, content_type: str = "application/pdf"
) -> dict[str, Any]:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "Name": name,
        "Content": encoded,
        "ContentType": content_type,
        "ContentLength": len(encoded),
    }


def payload(
    message_id: str,
    local_part: str,
    attachments: list[dict[str, Any]],
    *,
    sender: str = "Shared Agency <agency@example.test>",
    domain: str = "inbound.wathefni.test",
) -> dict[str, Any]:
    recipient = f"{local_part}@{domain}"
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": app._parse_email_address(sender), "Name": "Shared Agency"},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": f"Synthetic CV {message_id}",
        "Date": "Sat, 25 Jul 2026 08:00:00 +0300",
        "Attachments": attachments,
        "Headers": [
            {
                "Name": "Authentication-Results",
                "Value": "example.test; spf=pass; dkim=pass; dmarc=pass",
            }
        ],
    }


def scalar(sql: str, params: tuple[Any, ...] = ()) -> int:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone() or {}
    return int(next(iter(row.values())) or 0)


def setup() -> None:
    app.ensure_schema(force=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in COMPANIES:
                cur.execute(
                    """
                    INSERT INTO companies
                      (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (
                        company,
                        company,
                        app.Json({"marker": MARKER}),
                        app.Json({"marker": MARKER}),
                    ),
                )
            routes = {
                "one": "DURABLEONE",
                "two": "DURABLETWO",
                "fail": "DURABLEFAIL",
                "queue-a": "DURABLEQUEUEA",
                "queue-b": "DURABLEQUEUEB",
                "quota": "DURABLEQUOTA",
                "load-a": "DURABLELOADA",
                "load-b": "DURABLELOADB",
            }
            for local, company in routes.items():
                cur.execute(
                    """
                    INSERT INTO intake_addresses
                      (company_code, local_part, domain, label, metadata)
                    VALUES (%s,%s,'inbound.wathefni.test',%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (company, local, f"Synthetic {company}", app.Json({"marker": MARKER})),
                )
        conn.commit()


def cleanup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('wathefni.authority_cleanup','synthetic',true)"
            )
            cur.execute(
                "SELECT app_key, surrogate_phone FROM import_items WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
            rows = [dict(row) for row in cur.fetchall()]
            app_keys = sorted({row["app_key"] for row in rows if row.get("app_key")})
            phones = sorted(
                {row["surrogate_phone"] for row in rows if row.get("surrogate_phone")}
            )
            if app_keys:
                cur.execute("DELETE FROM semantic_documents WHERE entity_key = ANY(%s)", (app_keys,))
                cur.execute("DELETE FROM candidate_documents WHERE app_key = ANY(%s)", (app_keys,))
                cur.execute("DELETE FROM file_registry WHERE subject_key = ANY(%s)", (app_keys,))
                cur.execute("DELETE FROM applications WHERE app_key = ANY(%s)", (app_keys,))
            if phones:
                cur.execute("DELETE FROM candidates WHERE phone = ANY(%s)", (phones,))
            cur.execute(
                "DELETE FROM intake_processing_jobs WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
            cur.execute(
                "DELETE FROM intake_submissions WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
            cur.execute(
                "DELETE FROM import_batches WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
            cur.execute(
                """
                DELETE FROM inbound_messages
                WHERE company_code = ANY(%s)
                   OR envelope_recipient LIKE '%%@inbound.wathefni.test'
                """,
                (list(COMPANIES),),
            )
            cur.execute(
                "DELETE FROM intake_quota_usage WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
            cur.execute(
                "DELETE FROM intake_tenant_queue_state WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
            cur.execute(
                "DELETE FROM intake_addresses WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
            cur.execute(
                "DELETE FROM companies WHERE company_code = ANY(%s)",
                (list(COMPANIES),),
            )
        conn.commit()
    shutil.rmtree(ROOT, ignore_errors=True)


def receive(value: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    return app.process_postmark_inbound(value, **kwargs)


def run_stage(job_type: str, limit: int = 100) -> dict[str, Any]:
    return app.run_durable_email_ingress_worker(
        limit=limit,
        worker_id=f"qualify-{job_type}-{uuid.uuid4().hex[:6]}",
        job_types=[job_type],
    )


def make_due(company: str | None = None) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE intake_processing_jobs SET available_at=now()-interval '1 second'
                WHERE (%s::text IS NULL OR company_code=%s)
                  AND status IN ('retrying','waiting_quota','waiting_budget')
                """,
                (company, company),
            )
        conn.commit()


def qualification() -> None:
    single = check(
        "one email with one CV reaches durability only",
        lambda: receive(
            payload(
                "qual-single",
                "one",
                [attachment("Single.pdf", pdf_bytes("single"))],
            )
        ),
    )
    assert_true(single["accepted_attachment_count"] == 1, "single attachment missing")
    assert_true(
        scalar(
            "SELECT count(*) FROM applications WHERE company_code=%s",
            ("DURABLEONE",),
        )
        == 0,
        "candidate application created synchronously",
    )

    several_payload = payload(
        "qual-several",
        "one",
        [
            attachment("Candidate-A.pdf", pdf_bytes("candidate-a")),
            attachment("Candidate-B.pdf", pdf_bytes("candidate-b")),
            attachment("Candidate-A-copy.pdf", pdf_bytes("candidate-a")),
        ],
    )
    several = check(
        "one email with several CVs and duplicate attachment",
        lambda: receive(several_payload),
    )
    assert_true(several["accepted_attachment_count"] == 3, "multi-CV sources lost")
    assert_true(
        sum(1 for row in several["documents"] if row["duplicate_of_document_id"]) == 1,
        "duplicate source not linked",
    )

    duplicate_delivery = check(
        "duplicate Postmark delivery",
        lambda: receive(several_payload),
    )
    assert_true(duplicate_delivery.get("duplicate") is True, "delivery not idempotent")

    check("async validation", lambda: run_stage("intake_validation"))
    check("async safety scan", lambda: run_stage("file_safety_scan"))
    check("async accepted preparation", lambda: run_stage("accepted_intake_preparation"))
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(DISTINCT a.phone) AS people, count(*) AS applications,
                       count(*) FILTER (WHERE c.email IS NOT NULL) AS sender_email_keys
                FROM applications a JOIN candidates c ON c.phone=a.phone
                WHERE a.company_code=%s
                """,
                ("DURABLEONE",),
            )
            agency = dict(cur.fetchone())
    check(
        "shared agency sender does not collapse candidate identity",
        lambda: (
            assert_true(agency["people"] == 3, f"expected 3 unique CV subjects: {agency}"),
            assert_true(
                agency["sender_email_keys"] == 0,
                "agency sender became candidate email",
            ),
            agency,
        )[-1],
    )

    unknown = check(
        "unknown recipient durable rejection",
        lambda: receive(
            payload(
                "qual-unknown",
                "missing",
                [attachment("Unknown.pdf", pdf_bytes("unknown"))],
            )
        ),
    )
    assert_true(unknown.get("ignored") == "unknown_recipient", "unknown route accepted")

    def cross_tenant_attempt() -> str:
        first = receive(
            payload(
                "qual-cross-tenant",
                "one",
                [attachment("Tenant-A.pdf", pdf_bytes("tenant-a"))],
            )
        )
        assert_true(first["company_code"] == "DURABLEONE", "first tenant wrong")
        try:
            receive(
                payload(
                    "qual-cross-tenant",
                    "two",
                    [attachment("Tenant-B.pdf", pdf_bytes("tenant-b"))],
                )
            )
        except ingress.IngressValidationError as exc:
            assert_true(
                exc.code == "provider_message_route_conflict",
                f"wrong conflict: {exc.code}",
            )
            return exc.code
        raise AssertionError("cross-tenant MessageID replay accepted")

    check("cross-tenant recipient attempt fails closed", cross_tenant_attempt)

    failed_message_id = "qual-db-failure"

    def database_failure_before_durability() -> dict[str, Any]:
        def failpoint(name: str) -> None:
            if name == "before_commit":
                raise RuntimeError("synthetic_db_commit_failure")

        try:
            receive(
                payload(
                    failed_message_id,
                    "fail",
                    [attachment("Failure.pdf", pdf_bytes("failure"))],
                ),
                failpoint=failpoint,
            )
        except ingress.IngressDurabilityError as exc:
            assert_true(exc.http_status == 503, "failure is not retryable HTTP")
        else:
            raise AssertionError("pre-commit failure acknowledged")
        assert_true(
            scalar(
                "SELECT count(*) FROM inbound_messages WHERE provider_message_id=%s",
                (failed_message_id,),
            )
            == 0,
            "rolled-back message remained durable",
        )
        retried = receive(
            payload(
                failed_message_id,
                "fail",
                [attachment("Failure.pdf", pdf_bytes("failure"))],
            )
        )
        assert_true(retried["durable"], "provider retry did not recover")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT metadata->>'object_reused' AS reused
                    FROM intake_documents WHERE inbound_id=%s
                    """,
                    (retried["inbound_id"],),
                )
                reused = cur.fetchone()["reused"]
        assert_true(str(reused).lower() == "true", "orphan object was not reused")
        return retried

    check("database failure before durability returns retryable failure", database_failure_before_durability)

    class FailingStore(ingress.LocalQuarantineStore):
        def write(self, **_kwargs: Any) -> tuple[str, bool]:
            raise OSError("synthetic_storage_unavailable")

    def storage_failure_before_durability() -> str:
        config = app.durable_email_ingress_config()
        try:
            receive(
                payload(
                    "qual-storage-failure",
                    "fail",
                    [attachment("Storage.pdf", pdf_bytes("storage"))],
                ),
                quarantine_store=FailingStore(config.quarantine_root),
            )
        except ingress.IngressDurabilityError as exc:
            assert_true(exc.http_status == 503, "storage failure not retryable")
            assert_true(
                scalar(
                    "SELECT count(*) FROM inbound_messages WHERE provider_message_id=%s",
                    ("qual-storage-failure",),
                )
                == 0,
                "storage failure left acknowledged ledger",
            )
            return exc.code
        raise AssertionError("storage failure acknowledged")

    check("storage failure before durability", storage_failure_before_durability)

    post_ack = receive(payload("qual-post-ack", "fail", []))

    def fail_after_ack() -> dict[str, Any]:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE intake_processing_jobs
                    SET priority=-100, available_at=now()
                    WHERE job_id=%s
                    """,
                    (post_ack["job_id"],),
                )
            conn.commit()

        def failing_handler(_job: dict[str, Any]) -> dict[str, Any]:
            raise ingress.RetryableJobError(
                "synthetic_after_ack_failure", "candidate@example.test /secret/path"
            )

        result = ingress.run_worker_once(
            db_connect=app.db_connect,
            handler=failing_handler,
            worker_id="qualify-post-ack-failure",
            config=app.durable_email_ingress_config(),
            limit=1,
            allowed_job_types=["intake_validation"],
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, last_error_code, last_error_detail
                    FROM intake_processing_jobs WHERE job_id=%s
                    """,
                    (post_ack["job_id"],),
                )
                queued = dict(cur.fetchone())
        assert_true(queued["status"] == "retrying", "post-ack failure disappeared")
        assert_true("[redacted-email]" in queued["last_error_detail"], "PII not redacted")
        return result

    check("failure after durable acknowledgment retries", fail_after_ack)

    def worker_crash_and_lease_recovery() -> dict[str, Any]:
        config = replace(app.durable_email_ingress_config(), lease_seconds=30)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                crash_job = ingress.enqueue_job(
                    cur,
                    company_code="DURABLEQUEUEA",
                    job_type="retention_privacy",
                    subject_type="synthetic",
                    subject_id="crash",
                    idempotency_key="qualification:crash-recovery",
                    payload={},
                    priority=1,
                    max_attempts=3,
                )
                cur.execute(
                    """
                    INSERT INTO intake_tenant_queue_state (company_code)
                    VALUES ('DURABLEQUEUEA') ON CONFLICT DO NOTHING
                    """
                )
            conn.commit()
        claimed = ingress.claim_next_job(
            db_connect=app.db_connect,
            worker_id="crashed-worker",
            config=config,
            allowed_job_types=["retention_privacy"],
        )
        assert_true(claimed and claimed["job_id"] == crash_job, "crash job not claimed")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE intake_processing_jobs
                    SET lease_expires_at=now()-interval '1 second'
                    WHERE job_id=%s
                    """,
                    (crash_job,),
                )
            conn.commit()
        recovered = ingress.claim_next_job(
            db_connect=app.db_connect,
            worker_id="recovery-worker",
            config=config,
            allowed_job_types=["retention_privacy"],
        )
        assert_true(recovered and recovered["job_id"] == crash_job, "expired lease not reclaimed")
        ingress.complete_job(
            db_connect=app.db_connect,
            job=recovered,
            worker_id="recovery-worker",
            result={"recovered": True},
        )
        return {"job_id": crash_job, "attempts": recovered["attempts"]}

    check("worker crash and lease recovery", worker_crash_and_lease_recovery)

    def retry_dead_letter_and_replay() -> dict[str, Any]:
        config = replace(
            app.durable_email_ingress_config(),
            max_attempts=2,
            retry_base_seconds=1,
            retry_max_seconds=1,
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                job_id = ingress.enqueue_job(
                    cur,
                    company_code="DURABLEQUEUEA",
                    job_type="sender_acknowledgment",
                    subject_type="synthetic",
                    subject_id="dead",
                    idempotency_key="qualification:dead-letter",
                    payload={},
                    priority=1,
                    max_attempts=2,
                )
            conn.commit()

        def always_fail(_job: dict[str, Any]) -> dict[str, Any]:
            raise ingress.RetryableJobError("synthetic_retry", "safe detail")

        for attempt in range(2):
            ingress.run_worker_once(
                db_connect=app.db_connect,
                handler=always_fail,
                worker_id=f"dead-letter-{attempt}",
                config=config,
                limit=1,
                allowed_job_types=["sender_acknowledgment"],
            )
            make_due("DURABLEQUEUEA")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status, attempts FROM intake_processing_jobs WHERE job_id=%s",
                    (job_id,),
                )
                dead = dict(cur.fetchone())
        assert_true(dead["status"] == "dead_letter", f"not dead-lettered: {dead}")
        replay = ingress.replay_dead_letter(
            db_connect=app.db_connect,
            company_code="DURABLEQUEUEA",
            job_id=job_id,
            actor="synthetic-operator",
        )
        assert_true(replay["status"] == "pending", "dead letter replay failed")
        return {"dead": dead, "replay": replay}

    check("retry, dead-letter, redacted evidence and explicit replay", retry_dead_letter_and_replay)

    safety_cases = [
        (
            "password protected file",
            "qual-password",
            attachment("Protected.pdf", pdf_bytes("protected", encrypted=True)),
            "password_protected",
        ),
        (
            "unsupported type",
            "qual-unsupported",
            attachment("Legacy.rtf", b"{\\rtf1 synthetic}", "application/rtf"),
            "unsupported_type",
        ),
        (
            "MIME mismatch",
            "qual-mime",
            attachment("Mismatch.pdf", b"plain text", "application/pdf"),
            "mime_mismatch",
        ),
    ]
    for label, message_id, item, expected in safety_cases:
        received = receive(payload(message_id, "two", [item]))
        run_stage("intake_validation")
        run_stage("file_safety_scan")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT safety_state FROM intake_documents WHERE inbound_id=%s",
                    (received["inbound_id"],),
                )
                state = cur.fetchone()["safety_state"]
        check(label, lambda state=state, expected=expected: assert_true(state == expected, state))

    old_file_limit = os.environ.get("WATHEFNI_INTAKE_MAX_FILE_BYTES")
    os.environ["WATHEFNI_INTAKE_MAX_FILE_BYTES"] = "1024"
    oversize = check(
        "oversize file remains durable with terminal safety state",
        lambda: receive(
            payload(
                "qual-oversize",
                "two",
                [attachment("Oversize.pdf", b"%PDF-1.4\n" + b"x" * 2048 + b"\n%%EOF\n")],
            )
        ),
    )
    if old_file_limit is None:
        os.environ.pop("WATHEFNI_INTAKE_MAX_FILE_BYTES", None)
    else:
        os.environ["WATHEFNI_INTAKE_MAX_FILE_BYTES"] = old_file_limit
    assert_true(oversize["documents"][0]["safety_state"] == "too_large", "oversize lost")

    scanner_received = receive(
        payload(
            "qual-scanner-unavailable",
            "two",
            [attachment("Scanner.pdf", pdf_bytes("scanner"))],
        )
    )
    run_stage("intake_validation")
    old_scanner = os.environ.get("WATHEFNI_INTAKE_MALWARE_SCANNER")
    os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "unavailable"
    scanner_result = run_stage("file_safety_scan")
    os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = old_scanner or "test_clean"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT safety_state FROM intake_documents WHERE inbound_id=%s
                """,
                (scanner_received["inbound_id"],),
            )
            scanner_state = cur.fetchone()["safety_state"]
    check(
        "scanner unavailable fails closed",
        lambda: (
            assert_true(scanner_state == "scan_pending", "scanner failure advanced file"),
            assert_true(
                any(row["status"] in {"retrying", "dead_letter"} for row in scanner_result["outcomes"]),
                "scanner failure not visible",
            ),
            scanner_result,
        )[-1],
    )

    def quota_waiting() -> dict[str, Any]:
        old = os.environ.get("WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA")
        os.environ["WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA"] = "1"
        try:
            first = receive(payload("qual-quota-1", "quota", []))
            second = receive(payload("qual-quota-2", "quota", []))
        finally:
            if old is None:
                os.environ.pop("WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA", None)
            else:
                os.environ["WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA"] = old
        assert_true(first["status"] == "queued", "first quota item blocked")
        assert_true(second["status"] == "waiting_quota", "quota item silently dropped")
        return {"first": first["status"], "second": second["status"]}

    check("tenant quota exhaustion is visible and non-terminal", quota_waiting)

    def tenant_fairness() -> list[str]:
        config = replace(app.durable_email_ingress_config(), per_tenant_concurrency=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for index in range(6):
                    for company in ("DURABLEQUEUEA", "DURABLEQUEUEB"):
                        ingress.enqueue_job(
                            cur,
                            company_code=company,
                            job_type="retention_privacy",
                            subject_type="fairness",
                            subject_id=f"{company}-{index}",
                            idempotency_key=f"qualification:fairness:{company}:{index}",
                            payload={},
                            priority=100,
                            max_attempts=3,
                        )
            conn.commit()
        order: list[str] = []
        for index in range(12):
            claimed = ingress.claim_next_job(
                db_connect=app.db_connect,
                worker_id=f"fairness-{index}",
                config=config,
                allowed_job_types=["retention_privacy"],
            )
            assert_true(claimed is not None, "fairness queue starved")
            order.append(claimed["company_code"])
            ingress.complete_job(
                db_connect=app.db_connect,
                job=claimed,
                worker_id=f"fairness-{index}",
                result={},
            )
        assert_true(set(order[:4]) == {"DURABLEQUEUEA", "DURABLEQUEUEB"}, order)
        assert_true(order.count("DURABLEQUEUEA") == 6, order)
        assert_true(order.count("DURABLEQUEUEB") == 6, order)
        return order

    check("tenant fairness under burst load", tenant_fairness)

    def thousand_message_burst() -> dict[str, Any]:
        before_candidates = scalar(
            "SELECT count(*) FROM candidates WHERE active_company_code = ANY(%s)",
            (["DURABLELOADA", "DURABLELOADB"],),
        )
        before_ocr = scalar(
            "SELECT count(*) FROM cv_extraction_runs WHERE company_code = ANY(%s)",
            (["DURABLELOADA", "DURABLELOADB"],),
        )
        started = time.monotonic()
        for index in range(1000):
            local = "load-a" if index % 2 == 0 else "load-b"
            receive(payload(f"qual-load-{index:04d}", local, []))
        elapsed = time.monotonic() - started
        durable = scalar(
            """
            SELECT count(*) FROM inbound_messages
            WHERE provider_message_id LIKE 'qual-load-%%' AND durable_at IS NOT NULL
            """
        )
        submissions = scalar(
            """
            SELECT count(*) FROM intake_submissions
            WHERE provider_message_id LIKE 'qual-load-%%'
            """
        )
        jobs = scalar(
            """
            SELECT count(*) FROM intake_processing_jobs
            WHERE idempotency_key LIKE 'submission:%%:validate'
              AND company_code = ANY(%s)
            """,
            (["DURABLELOADA", "DURABLELOADB"],),
        )
        after_candidates = scalar(
            "SELECT count(*) FROM candidates WHERE active_company_code = ANY(%s)",
            (["DURABLELOADA", "DURABLELOADB"],),
        )
        after_ocr = scalar(
            "SELECT count(*) FROM cv_extraction_runs WHERE company_code = ANY(%s)",
            (["DURABLELOADA", "DURABLELOADB"],),
        )
        assert_true(durable == 1000, f"durable={durable}")
        assert_true(submissions == 1000, f"submissions={submissions}")
        assert_true(jobs == 1000, f"jobs={jobs}")
        assert_true(after_candidates == before_candidates, "synchronous candidates created")
        assert_true(after_ocr == before_ocr, "synchronous OCR ran")
        return {
            "messages": durable,
            "submissions": submissions,
            "jobs": jobs,
            "elapsed_seconds": round(elapsed, 3),
            "messages_per_second": round(1000 / max(elapsed, 0.001), 2),
            "synchronous_candidates": 0,
            "synchronous_ocr_runs": 0,
        }

    check("thousands-message synthetic burst without synchronous OCR", thousand_message_burst)

    def observability() -> dict[str, Any]:
        summary = ingress.operations_summary(
            db_connect=app.db_connect,
            config=app.durable_email_ingress_config(),
            include_orphans=True,
        )
        assert_true(summary["messages"]["durable_messages"] >= 1000, "durable metric missing")
        assert_true(summary["jobs"], "queue metrics missing")
        assert_true(summary["safety_states"], "safety metrics missing")
        assert_true(summary["quota_usage"], "quota metrics missing")
        return {
            "messages": summary["messages"],
            "job_states": summary["jobs"],
            "safety_states": summary["safety_states"],
            "orphan_storage": summary["orphan_storage"],
        }

    check("operator observability", observability)

    def signed_download_scope() -> dict[str, Any]:
        expires = int(time.time()) + 300
        secret = "synthetic-signing-secret"
        signature = ingress.sign_quarantine_download(
            company_code="DURABLEONE",
            document_id=single["documents"][0]["document_id"],
            expires_at_epoch=expires,
            secret=secret,
        )
        valid = ingress.verify_quarantine_download(
            company_code="DURABLEONE",
            document_id=single["documents"][0]["document_id"],
            expires_at_epoch=expires,
            signature=signature,
            secret=secret,
            now_epoch=int(time.time()),
        )
        cross_tenant = ingress.verify_quarantine_download(
            company_code="DURABLETWO",
            document_id=single["documents"][0]["document_id"],
            expires_at_epoch=expires,
            signature=signature,
            secret=secret,
            now_epoch=int(time.time()),
        )
        assert_true(valid and not cross_tenant, "signed URL not tenant scoped")
        return {"valid_tenant": valid, "cross_tenant": cross_tenant}

    check("signed quarantine access is tenant scoped", signed_download_scope)

    def orphan_sweep() -> dict[str, Any]:
        # The pre-commit failure produced an orphan. The provider retry reused its
        # stable key, so create one explicit unreferenced object for sweep proof.
        orphan = (
            app.durable_email_ingress_config().quarantine_root
            / "DURABLEFAIL"
            / str(uuid.uuid4())
            / "0001"
            / f"{'a' * 64}.bin"
        )
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_bytes(b"orphan")
        old = time.time() - 120
        os.utime(orphan, (old, old))
        report = ingress.orphan_storage_report(
            db_connect=app.db_connect,
            config=app.durable_email_ingress_config(),
            delete=True,
            now=datetime.now(UTC),
        )
        assert_true(report["deleted_objects"] >= 1, "orphan was not swept")
        assert_true(not orphan.exists(), "orphan residue remains")
        return report

    check("orphan quarantine sweep", orphan_sweep)


def zero_residue_check() -> dict[str, Any]:
    database_rows = {}
    tables = {
        "jobs": "intake_processing_jobs",
        "submissions": "intake_submissions",
        "inbound": "inbound_messages",
        "batches": "import_batches",
        "applications": "applications",
        "candidates": "candidates",
        "quota": "intake_quota_usage",
    }
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for label, table in tables.items():
                company_column = (
                    "active_company_code" if table == "candidates" else "company_code"
                )
                cur.execute(
                    f"SELECT count(*) AS count FROM {table} WHERE {company_column} = ANY(%s)",
                    (list(COMPANIES),),
                )
                database_rows[label] = int(cur.fetchone()["count"])
            cur.execute(
                """
                SELECT count(*) AS count FROM inbound_messages
                WHERE envelope_recipient LIKE '%%@inbound.wathefni.test'
                """
            )
            database_rows["inbound_test_domain"] = int(cur.fetchone()["count"])
    files = sum(1 for path in ROOT.rglob("*") if path.is_file()) if ROOT.exists() else 0
    assert_true(all(value == 0 for value in database_rows.values()), database_rows)
    assert_true(files == 0, f"quarantine files remain: {files}")
    return {"database_rows": database_rows, "quarantine_files": files}


def main() -> None:
    setup()
    try:
        qualification()
    finally:
        cleanup()
    check("zero synthetic residue", zero_residue_check)
    failures = [row for row in RESULTS if row["status"] != "PASS"]
    print(
        app.json.dumps(
            {
                "status": "PASS" if not failures else "FAIL",
                "checks": len(RESULTS),
                "failures": len(failures),
                "results": RESULTS,
            },
            ensure_ascii=False,
            default=str,
        )
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
