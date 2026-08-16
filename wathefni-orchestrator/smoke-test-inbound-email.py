"""Behavior test for durable Postmark inbound intake — no provider network.

Proves that webhook-equivalent receipt persists source material and queue work
without synchronously creating candidates/applications. It then runs only the
validation, safety, and accepted-preparation workers to prove the existing held
authority is reached asynchronously.
"""

from __future__ import annotations

import base64
import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

_QUARANTINE = Path(tempfile.mkdtemp(prefix="wathefni-inbound-smoke-"))
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if database_url:
    parsed_database = urlparse(database_url)
    env_file = _QUARANTINE / "postgres.test.env"
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
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "smoke-secret-token")
os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(_QUARANTINE)
os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
os.environ["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"

import app  # noqa: E402


COMPANY_A = "INBOUNDALPHA"
COMPANY_B = "INBOUNDBRAVO"
MARKER = "temporary_durable_inbound_email_smoke"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _pdf(name: str, email: str) -> bytes:
    summary = (
        "Senior Welder with eight years of industrial inspection experience, "
        "safety compliance, NDT testing, team leadership, technical reporting, "
        "quality assurance, and bilingual client coordination."
    )
    stream = (
        f"BT /F1 12 Tf 72 720 Td ({name}) Tj "
        f"0 -18 Td (Email {email}) Tj "
        f"0 -18 Td ({summary}) Tj ET"
    ).encode()
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n"
        + f"4 0 obj<</Length {len(stream)}>>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\n"
        + b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        + b"xref\n0 6\n0000000000 65535 f \ntrailer<</Root 1 0 R/Size 6>>\nstartxref\n0\n%%EOF\n"
    )


def _payload(
    message_id: str,
    recipient: str,
    sender: str,
    attachments: list[dict],
    headers: list[dict] | None = None,
) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": sender.split("<")[0].strip()},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": "My CV",
        "Date": "Mon, 01 Jun 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": headers or [],
    }


def _att(name: str, data: bytes, ctype: str = "application/pdf") -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "Name": name,
        "Content": encoded,
        "ContentType": ctype,
        "ContentLength": len(encoded),
    }


def _intake(company: str, local_part: str, domain: str | None = "inbound.wathefni.ai") -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO intake_addresses (company_code, local_part, domain)
                VALUES (%s,%s,%s) RETURNING intake_id::text
                """,
                (company, local_part, domain),
            )
            intake_id = cur.fetchone()["intake_id"]
        conn.commit()
    return intake_id


def setup() -> None:
    app.ensure_schema(force=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    """
                    INSERT INTO companies
                      (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (
                        company,
                        f"Inbound {company}",
                        app.Json({"smoke": MARKER}),
                        app.Json({"smoke": MARKER}),
                    ),
                )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('wathefni.authority_cleanup','synthetic',true)"
            )
            cur.execute(
                "SELECT app_key, surrogate_phone FROM import_items WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
            rows = [dict(row) for row in cur.fetchall()]
            app_keys = [row["app_key"] for row in rows if row.get("app_key")]
            phones = [row["surrogate_phone"] for row in rows if row.get("surrogate_phone")]
            if app_keys:
                cur.execute("DELETE FROM candidate_documents WHERE app_key = ANY(%s)", (app_keys,))
                cur.execute("DELETE FROM file_registry WHERE subject_key = ANY(%s)", (app_keys,))
                cur.execute("DELETE FROM applications WHERE app_key = ANY(%s)", (app_keys,))
            if phones:
                cur.execute("DELETE FROM candidates WHERE phone = ANY(%s)", (phones,))
            cur.execute(
                "DELETE FROM intake_processing_jobs WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
            cur.execute(
                "DELETE FROM intake_submissions WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
            cur.execute(
                "DELETE FROM import_batches WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
            cur.execute(
                """
                DELETE FROM inbound_messages
                WHERE company_code = ANY(%s)
                   OR (company_code IS NULL AND envelope_recipient LIKE %s)
                """,
                ([COMPANY_A, COMPANY_B], "%inbound.wathefni.ai"),
            )
            cur.execute(
                "DELETE FROM intake_quota_usage WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
            cur.execute(
                "DELETE FROM intake_tenant_queue_state WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
            cur.execute(
                "DELETE FROM intake_addresses WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
            cur.execute(
                "DELETE FROM companies WHERE company_code = ANY(%s)",
                ([COMPANY_A, COMPANY_B],),
            )
        conn.commit()
    shutil.rmtree(_QUARANTINE, ignore_errors=True)


def check_secret() -> None:
    secret = app.inbound_postmark_secret()
    basic = "Basic " + base64.b64encode(f"wathefni:{secret}".encode()).decode()
    assert_true(app._verify_postmark_secret(basic, None), "basic auth password must verify")
    assert_true(app._verify_postmark_secret(None, secret), "query token must verify")
    assert_true(
        not app._verify_postmark_secret(
            "Basic " + base64.b64encode(b"x:wrong").decode(), None
        ),
        "wrong secret rejected",
    )
    assert_true(not app._verify_postmark_secret(None, None), "no secret rejected")


def _run_stage(job_type: str, limit: int = 50) -> dict:
    return app.run_durable_email_ingress_worker(
        limit=limit,
        worker_id=f"smoke-{job_type}",
        job_types=[job_type],
    )


def run_checks() -> None:
    check_secret()
    _intake(COMPANY_A, "alpha")
    _intake(COMPANY_B, "bravo")

    ali_pdf = _pdf("Ali Hassan", "ali@example.com")
    p1 = _payload(
        "pm-durable-1",
        "alpha@inbound.wathefni.ai",
        "Agency Desk <agency@example.com>",
        [
            _att("Ali_CV.pdf", ali_pdf),
            _att("logo.bin", b"not a cv", "application/octet-stream"),
        ],
    )
    r1 = app.process_postmark_inbound(p1)
    assert_true(r1["durable"] is True and r1["status"] == "queued", "receipt durable")
    assert_true(r1["accepted_attachment_count"] == 2, "both sources quarantined")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM applications WHERE company_code=%s",
                (COMPANY_A,),
            )
            assert_true(cur.fetchone()["c"] == 0, "webhook creates zero applications")
            cur.execute(
                "SELECT count(*) AS c FROM candidates WHERE active_company_code=%s",
                (COMPANY_A,),
            )
            assert_true(cur.fetchone()["c"] == 0, "webhook creates zero candidates")
            cur.execute(
                """
                SELECT count(*) AS c FROM intake_documents
                WHERE company_code=%s AND storage_status='stored'
                """,
                (COMPANY_A,),
            )
            assert_true(cur.fetchone()["c"] == 2, "source manifests stored")
            cur.execute(
                """
                SELECT count(*) AS c FROM intake_processing_jobs
                WHERE company_code=%s AND job_type='intake_validation'
                """,
                (COMPANY_A,),
            )
            assert_true(cur.fetchone()["c"] == 1, "outbox work committed")

    assert_true(_run_stage("intake_validation")["processed"] == 1, "validation async")
    assert_true(_run_stage("file_safety_scan")["processed"] == 2, "safety async")
    assert_true(
        _run_stage("cv_identity_resolution")["processed"] == 1,
        "only durably clean CV reaches identity resolution",
    )
    assert_true(
        _run_stage("accepted_intake_preparation")["processed"] == 1,
        "only clean CV reaches accepted preparation",
    )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.app_key, a.status, a.phone, c.email
                FROM applications a JOIN candidates c ON c.phone=a.phone
                WHERE a.company_code=%s
                """,
                (COMPANY_A,),
            )
            imported = dict(cur.fetchone())
            assert_true(imported["status"] == "needs_role", "existing held authority preserved")
            assert_true(
                imported["email"] == "ali@example.com",
                "candidate email comes from CV, never agency sender",
            )
            expected_token = hashlib.sha1(
                f"{COMPANY_A}:ali@example.com".encode()
            ).hexdigest()[:16]
            assert_true(
                imported["phone"] == f"imp-{COMPANY_A.lower()}-{expected_token}",
                "governed surrogate uses extracted CV identity, not sender",
            )
            cur.execute(
                """
                SELECT safety_state FROM intake_documents
                WHERE company_code=%s AND original_filename='logo.bin'
                """,
                (COMPANY_A,),
            )
            assert_true(
                cur.fetchone()["safety_state"] == "unsupported_type",
                "unsupported file terminates without looping",
            )
            cur.execute(
                """
                SELECT count(*) AS c FROM outbound_delivery_events
                WHERE subject_key=%s
                """,
                (imported["app_key"],),
            )
            assert_true(cur.fetchone()["c"] == 0, "no sender/candidate message")
            cur.execute(
                """
                SELECT document_id::text AS document_id,
                       COALESCE((metadata->>'latest')::boolean,false) AS latest
                FROM candidate_documents WHERE app_key=%s
                """,
                (imported["app_key"],),
            )
            first_pending = dict(cur.fetchone())
            assert_true(
                first_pending["latest"] is False,
                "new CV is not current before canonical extraction",
            )

    assert_true(
        _run_stage("cv_extraction")["processed"] == 1,
        "canonical extraction promotes first governed CV",
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE((metadata->>'latest')::boolean,false) AS latest
                FROM candidate_documents WHERE document_id=%s
                """,
                (first_pending["document_id"],),
            )
            assert_true(
                cur.fetchone()["latest"] is True,
                "first CV becomes current only after extraction",
            )

    newer = app.process_postmark_inbound(
        _payload(
            "pm-durable-1-newer",
            "alpha@inbound.wathefni.ai",
            "Recruiter Desk <same-sender@example.com>",
            [_att("Ali_CV_v2.pdf", _pdf("Ali Hassan Updated", "ali@example.com"))],
        )
    )
    assert_true(newer["status"] == "queued", "legitimate newer CV queued")
    assert_true(_run_stage("intake_validation")["processed"] == 1, "newer validation")
    assert_true(_run_stage("file_safety_scan")["processed"] == 1, "newer scan")
    assert_true(_run_stage("cv_identity_resolution")["processed"] == 1, "newer identity")
    assert_true(
        _run_stage("accepted_intake_preparation")["processed"] == 1,
        "newer CV safely binds to existing candidate",
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id::text AS document_id,
                       COALESCE((metadata->>'latest')::boolean,false) AS latest,
                       metadata->>'superseded_at' AS superseded_at
                FROM candidate_documents
                WHERE app_key=%s
                ORDER BY created_at, document_id
                """,
                (imported["app_key"],),
            )
            versions = [dict(row) for row in cur.fetchall()]
            assert_true(len(versions) == 2, "newer CV inserts a second immutable row")
            assert_true(
                sum(1 for row in versions if row["latest"]) == 1
                and any(
                    row["document_id"] == first_pending["document_id"] and row["latest"]
                    for row in versions
                ),
                "prior CV remains current until newer extraction succeeds",
            )
            second_pending = next(
                row
                for row in versions
                if row["document_id"] != first_pending["document_id"]
            )
            assert_true(
                second_pending["latest"] is False,
                "newer CV is pending and cannot supersede before extraction",
            )
    assert_true(
        _run_stage("cv_extraction")["processed"] == 1,
        "canonical extraction promotes legitimate newer CV",
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT document_id::text AS document_id,
                       COALESCE((metadata->>'latest')::boolean,false) AS latest,
                       metadata->>'superseded_at' AS superseded_at
                FROM candidate_documents WHERE app_key=%s
                """,
                (imported["app_key"],),
            )
            promoted = {row["document_id"]: dict(row) for row in cur.fetchall()}
            assert_true(
                promoted[second_pending["document_id"]]["latest"] is True,
                "newer CV is current after successful extraction",
            )
            assert_true(
                promoted[first_pending["document_id"]]["latest"] is False
                and promoted[first_pending["document_id"]]["superseded_at"],
                "prior CV is preserved and auditably superseded",
            )

    conflict_receipt = app.process_postmark_inbound(
        _payload(
            "pm-durable-identity-conflict",
            "alpha@inbound.wathefni.ai",
            "Recruiter Desk <same-sender@example.com>",
            [_att("Noor_CV.pdf", _pdf("Noor Tahat", "ali@example.com"))],
        )
    )
    assert_true(conflict_receipt["status"] == "queued", "conflict source retained")
    assert_true(_run_stage("intake_validation")["processed"] == 1, "conflict validation")
    assert_true(_run_stage("file_safety_scan")["processed"] == 1, "conflict scan")
    assert_true(_run_stage("cv_identity_resolution")["processed"] == 1, "conflict identity")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.outcome, r.normalized_full_name, r.extracted_email,
                       r.candidate_matches, r.reason_codes
                FROM inbound_cv_identity_resolutions r
                JOIN intake_documents d ON d.document_id=r.intake_document_id
                WHERE d.inbound_id=%s
                """,
                (conflict_receipt["inbound_id"],),
            )
            conflict_decision = dict(cur.fetchone())
            assert_true(
                conflict_decision["outcome"] == "conflict",
                f"expected conflict decision: {conflict_decision}",
            )
    assert_true(
        _run_stage("held_intake_materialization")["processed"] == 1,
        "identity conflict materializes Held review application",
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.outcome, r.ownership_confirmed, d.app_key,
                       d.candidate_document_id::text AS candidate_document_id,
                       d.metadata->>'held_terminal_reason' AS terminal_reason,
                       a.status AS app_status,
                       COALESCE((a.raw_json->'import'->>'identity_review_warning')::boolean,false) AS warned
                FROM inbound_cv_identity_resolutions r
                JOIN intake_documents d
                  ON d.document_id=r.intake_document_id
                LEFT JOIN applications a
                  ON a.app_key=d.app_key AND a.company_code=d.company_code
                WHERE d.inbound_id=%s
                """,
                (conflict_receipt["inbound_id"],),
            )
            conflict_row = dict(cur.fetchone())
            assert_true(
                conflict_row["outcome"] == "conflict"
                and conflict_row["ownership_confirmed"] is False
                and conflict_row["app_key"]
                and conflict_row["app_status"] in {"needs_role", "import_review"}
                and conflict_row["warned"] is True
                and conflict_row["app_key"] != imported["app_key"],
                "conflict materializes a separate Held identity-review app without binding ownership",
            )
            cur.execute(
                """
                SELECT count(*) AS docs,
                       count(*) FILTER (
                         WHERE COALESCE((metadata->>'latest')::boolean,false)
                       ) AS current_docs
                FROM candidate_documents WHERE app_key=%s
                """,
                (imported["app_key"],),
            )
            doc_counts = dict(cur.fetchone())
            assert_true(
                int(doc_counts["docs"]) == 2 and int(doc_counts["current_docs"]) == 1,
                "identity conflict cannot supersede the legitimate current CV",
            )

    duplicate = app.process_postmark_inbound(p1)
    assert_true(duplicate.get("duplicate") is True, "MessageID idempotent")

    bravo = app.process_postmark_inbound(
        _payload(
            "pm-durable-2",
            "bravo@inbound.wathefni.ai",
            "Agency Desk <agency@example.com>",
            [_att("B_CV.pdf", _pdf("B Person", "b@example.com"))],
        )
    )
    assert_true(bravo["company_code"] == COMPANY_B, "recipient tenant is authority")

    unknown = app.process_postmark_inbound(
        _payload(
            "pm-durable-3",
            "nobody@inbound.wathefni.ai",
            "X <x@example.com>",
            [_att("X.pdf", _pdf("X", "x@example.com"))],
        )
    )
    assert_true(unknown.get("ignored") == "unknown_recipient", "unknown route durable reject")

    spam = app.process_postmark_inbound(
        _payload(
            "pm-durable-4",
            "alpha@inbound.wathefni.ai",
            "Spammer <spam@example.com>",
            [_att("Spam.pdf", _pdf("Spam", "spam@example.com"))],
            headers=[{"Name": "X-Spam-Status", "Value": "Yes"}],
        )
    )
    assert_true(spam["status"] == "quarantined", "spam source quarantined")
    _run_stage("intake_validation")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT safety_state FROM intake_documents
                WHERE company_code=%s AND inbound_id=%s
                """,
                (COMPANY_A, spam["inbound_id"]),
            )
            assert_true(cur.fetchone()["safety_state"] == "quarantined", "spam never scanned")

    no_attachment = app.process_postmark_inbound(
        _payload(
            "pm-durable-5",
            "alpha@inbound.wathefni.ai",
            "Z <z@example.com>",
            [],
        )
    )
    assert_true(no_attachment["durable"] is True, "empty submission remains auditable")

    _intake(COMPANY_A, "hashslug", None)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            hit = app.resolve_intake_address(
                cur,
                "serverhash+hashslug@inbound.postmarkapp.com",
                "hashslug",
            )
            assert_true(
                hit and hit["company_code"] == COMPANY_A,
                "mailbox hash resolves tenant",
            )


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("durable inbound email smoke tests passed")


if __name__ == "__main__":
    main()
