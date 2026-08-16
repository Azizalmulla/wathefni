#!/usr/bin/env python3
"""One isolated staging scanned-CV scan/OCR/identity authority qualification."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

COMPANY = "AUTHSCAN"
MARKER = "temporary_scanned_cv_authority_qualification"

import app  # noqa: E402


def assert_true(value: object, message: str) -> None:
    if not value:
        raise AssertionError(message)


def pdf_bytes() -> bytes:
    lines = [
        "Scanned Authority Candidate",
        "Email scanned.authority@example.test",
        "Phone +965 5000 7788",
        "Senior engineer with ten years of operations, safety, quality, and reporting experience.",
    ]
    commands = ["BT /F1 14 Tf 72 720 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -24 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = " ".join(commands).encode()
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
        + b"trailer<</Root 1 0 R/Size 6>>\n%%EOF\n"
    )


def run_stage(job_type: str) -> dict:
    return app.run_durable_email_ingress_worker(
        limit=20,
        worker_id=f"scanned-authority-{job_type}",
        job_types=[job_type],
    )


def cleanup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('wathefni.authority_cleanup','synthetic',true)"
            )
            cur.execute(
                "DELETE FROM intake_processing_jobs WHERE company_code=%s",
                (COMPANY,),
            )
            cur.execute("DELETE FROM inbound_messages WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM intake_addresses WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM intake_quota_usage WHERE company_code=%s", (COMPANY,))
            cur.execute(
                "DELETE FROM intake_tenant_queue_state WHERE company_code=%s",
                (COMPANY,),
            )
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def main() -> int:
    if os.environ.get("WATHEFNI_ENV") != "staging":
        raise SystemExit("refusing non-staging environment")
    if str(os.environ.get("WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS") or "").lower() != "off":
        raise SystemExit("classification workers must remain off")
    temp = Path(tempfile.mkdtemp(prefix="wathefni-scanned-authority-"))
    os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(temp / "quarantine")
    message_id = f"scanned-authority-{uuid.uuid4()}"
    result: dict = {}
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO companies
                      (company_code,name,metadata,raw_json,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (
                        COMPANY,
                        COMPANY,
                        app.Json({"marker": MARKER}),
                        app.Json({"marker": MARKER}),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO intake_addresses
                      (company_code,local_part,domain,label,metadata)
                    VALUES (%s,'authscan','inbound.wathefni.ai',%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (COMPANY, MARKER, app.Json({"marker": MARKER})),
                )
            conn.commit()

        pdf = temp / "source.pdf"
        png_root = temp / "scanned"
        pdf.write_bytes(pdf_bytes())
        subprocess.run(
            ["pdftoppm", "-png", "-singlefile", "-r", "170", str(pdf), str(png_root)],
            check=True,
            capture_output=True,
        )
        png = png_root.with_suffix(".png")
        payload = {
            "MessageID": message_id,
            "OriginalRecipient": "authscan@inbound.wathefni.ai",
            "From": "Recruiter Forwarder <recruiter@example.test>",
            "FromFull": {
                "Email": "recruiter@example.test",
                "Name": "Recruiter Forwarder",
            },
            "ToFull": [
                {
                    "Email": "authscan@inbound.wathefni.ai",
                    "Name": "",
                    "MailboxHash": "",
                }
            ],
            "Subject": "Scanned CV",
            "Date": "Sun, 26 Jul 2026 02:00:00 +0000",
            "Headers": [],
            "Attachments": [
                {
                    "Name": "Scanned_Authority_Candidate.png",
                    "Content": base64.b64encode(png.read_bytes()).decode("ascii"),
                    "ContentType": "image/png",
                }
            ],
        }
        receipt = app.process_postmark_inbound(payload)
        assert_true(receipt.get("durable"), "source receipt durable")
        validation = run_stage("intake_validation")
        safety = run_stage("file_safety_scan")
        identity = run_stage("cv_identity_resolution")
        assert_true(validation["processed"] == 1, "validation completed")
        assert_true(safety["processed"] == 1, "real safety scan completed")
        assert_true(identity["processed"] == 1, "canonical OCR identity completed")

        eicar_payload = {
            **payload,
            "MessageID": f"infected-authority-{uuid.uuid4()}",
            "Subject": "Infected qualification attachment",
            "Attachments": [
                {
                    "Name": "infected.pdf",
                    "Content": base64.b64encode(
                        b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$"
                        b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
                    ).decode("ascii"),
                    "ContentType": "application/pdf",
                }
            ],
        }
        infected_receipt = app.process_postmark_inbound(eicar_payload)
        assert_true(run_stage("intake_validation")["processed"] == 1, "infected validation")
        assert_true(run_stage("file_safety_scan")["processed"] == 1, "infected scan")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT sd.state, sd.scanner_engine, sd.scanner_version,
                           sd.signature_database_version, sd.scan_started_at,
                           sd.scan_completed_at, sd.actor_service_identity,
                           e.extraction_status, e.extraction_method,
                           e.extracted_identity, r.outcome,
                           r.sender_email_provenance, r.extracted_email,
                           r.extracted_phone, r.normalized_full_name,
                           d.app_key, d.candidate_document_id::text
                    FROM intake_documents d
                    JOIN LATERAL (
                      SELECT * FROM inbound_attachment_scan_decisions x
                      WHERE x.intake_document_id=d.document_id
                      ORDER BY x.attempt_no DESC LIMIT 1
                    ) sd ON true
                    JOIN inbound_cv_identity_extractions e
                      ON e.intake_document_id=d.document_id
                    JOIN inbound_cv_identity_resolutions r
                      ON r.intake_document_id=d.document_id
                    WHERE d.inbound_id=%s
                    """,
                    (receipt["inbound_id"],),
                )
                row = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT sd.state, sd.scanner_engine, sd.failure_reason,
                           count(e.extraction_id) AS identity_extractions
                    FROM intake_documents d
                    JOIN LATERAL (
                      SELECT * FROM inbound_attachment_scan_decisions x
                      WHERE x.intake_document_id=d.document_id
                      ORDER BY x.attempt_no DESC LIMIT 1
                    ) sd ON true
                    LEFT JOIN inbound_cv_identity_extractions e
                      ON e.intake_document_id=d.document_id
                    WHERE d.inbound_id=%s
                    GROUP BY sd.state, sd.scanner_engine, sd.failure_reason
                    """,
                    (infected_receipt["inbound_id"],),
                )
                infected_row = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT
                      (SELECT count(*) FROM applications WHERE company_code=%s) AS apps,
                      (SELECT count(*) FROM candidates WHERE active_company_code=%s) AS candidates,
                      (SELECT count(*) FROM talent_pool_classification_jobs WHERE company_code=%s) AS classification_jobs
                    """,
                    (COMPANY, COMPANY, COMPANY),
                )
                mutations = dict(cur.fetchone())
        assert_true(row["state"] == "clean", "durable scan is clean")
        assert_true(row["scanner_engine"] == "clamav", "real ClamAV authority")
        assert_true(row["scan_completed_at"], "scan completion durable")
        assert_true(
            str(row["extraction_method"] or "").lower()
            not in {"pdftotext", "text", ""},
            f"scanned image required OCR: {row['extraction_method']}",
        )
        assert_true(
            row["extracted_email"] == "scanned.authority@example.test",
            f"OCR identity email: {row['extracted_identity']}",
        )
        assert_true(
            row["sender_email_provenance"] == "recruiter@example.test",
            "sender remains provenance only",
        )
        assert_true(
            infected_row["state"] == "infected"
            and infected_row["scanner_engine"] == "clamav"
            and int(infected_row["identity_extractions"] or 0) == 0,
            f"infected file fails before extraction: {infected_row}",
        )
        assert_true(row["outcome"] == "new_candidate", "scanned CV identity outcome")
        assert_true(
            not row["app_key"] and not row["candidate_document_id"],
            "identity stage alone creates no candidate document",
        )
        assert_true(
            all(int(value or 0) == 0 for value in mutations.values()),
            f"no protected downstream mutations: {mutations}",
        )
        result = {
            "passed": True,
            "receipt": {
                "inbound_id": receipt["inbound_id"],
                "durable": receipt["durable"],
            },
            "scan": {
                key: row[key]
                for key in (
                    "state",
                    "scanner_engine",
                    "scanner_version",
                    "signature_database_version",
                    "scan_started_at",
                    "scan_completed_at",
                    "actor_service_identity",
                )
            },
            "infected_scan": infected_row,
            "extraction": {
                "status": row["extraction_status"],
                "method": row["extraction_method"],
                "identity": row["extracted_identity"],
            },
            "identity": {
                "outcome": row["outcome"],
                "sender_email_provenance": row["sender_email_provenance"],
                "extracted_email": row["extracted_email"],
                "extracted_phone": row["extracted_phone"],
                "normalized_full_name": row["normalized_full_name"],
            },
            "protected_mutations": mutations,
        }
    finally:
        cleanup()
        shutil.rmtree(temp, ignore_errors=True)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM companies WHERE company_code=%s) AS companies,
                  (SELECT count(*) FROM inbound_messages WHERE company_code=%s) AS messages,
                  (SELECT count(*) FROM intake_processing_jobs WHERE company_code=%s) AS jobs
                """,
                (COMPANY, COMPANY, COMPANY),
            )
            residue = dict(cur.fetchone())
    assert_true(all(int(value or 0) == 0 for value in residue.values()), "zero residue")
    result["zero_residue"] = residue
    print(json.dumps(result, indent=2, default=str, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
