#!/usr/bin/env python3
"""Isolated local/staging qualification for inbound CV scan + identity authority.

No provider email is sent, no classification worker is run, and all synthetic
tenant data plus quarantine objects are removed in ``finally``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


ROOT = Path(tempfile.mkdtemp(prefix="wathefni-inbound-authority-"))
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if database_url:
    parsed = urlparse(database_url)
    env_file = ROOT / "postgres.test.env"
    env_file.write_text(f"WATHEFNI_DATABASE_URL={database_url}\n")
    os.environ["WATHEFNI_POSTGRES_ENV"] = str(env_file)
    os.environ.setdefault("WATHEFNI_ENV", "test")
    os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = parsed.hostname or "127.0.0.1"
    os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = str(parsed.port or 5432)
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = parsed.path.lstrip("/")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-inbound-authority-v1"
    )
elif not os.environ.get("WATHEFNI_POSTGRES_ENV"):
    raise RuntimeError(
        "Set WATHEFNI_POSTGRES_ENV or WATHEFNI_TEST_DATABASE_URL to an isolated database."
    )

os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(ROOT / "quarantine")
os.environ.setdefault("WATHEFNI_INTAKE_MALWARE_SCANNER", "test_clean")
os.environ.setdefault("WATHEFNI_INTAKE_ALLOW_TEST_SCANNER", "1")
os.environ.setdefault("WATHEFNI_INTAKE_SERVICE_IDENTITY", "authority-qualification")
os.environ["WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION"] = "off"
os.environ["WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS"] = "off"

import app  # noqa: E402
import durable_email_ingress as ingress  # noqa: E402
import inbound_cv_authority as authority  # noqa: E402


COMPANY_A = "AUTHORITYQA"
COMPANY_B = "AUTHORITYQB"
COMPANIES = [COMPANY_A, COMPANY_B]
MARKER = "inbound_cv_scan_identity_authority_qualification"
RESULTS: list[dict[str, Any]] = []
CREATED_DOCS: list[str] = []


def assert_true(value: Any, message: str) -> None:
    if not value:
        raise AssertionError(message)


def check(name: str, fn: Callable[[], Any]) -> Any:
    started = time.monotonic()
    try:
        detail = fn()
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


def _pdf(label: str) -> bytes:
    text = label.replace("(", "[").replace(")", "]")
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    return (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
        + f"4 0 obj<</Length {len(stream)}>>stream\n".encode()
        + stream
        + b"\nendstream\nendobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    )


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE EXTENSION IF NOT EXISTS pgcrypto;
                CREATE TABLE IF NOT EXISTS companies (
                  company_code text PRIMARY KEY,
                  name text,
                  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                  created_at timestamptz NOT NULL DEFAULT now(),
                  updated_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS intake_addresses (
                  intake_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  company_code text NOT NULL,
                  local_part text NOT NULL,
                  domain text,
                  label text,
                  status text NOT NULL DEFAULT 'active',
                  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
                  created_at timestamptz NOT NULL DEFAULT now(),
                  updated_at timestamptz NOT NULL DEFAULT now(),
                  UNIQUE (local_part, domain)
                );
                CREATE TABLE IF NOT EXISTS inbound_messages (
                  inbound_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  provider text NOT NULL DEFAULT 'postmark',
                  provider_message_id text NOT NULL,
                  company_code text,
                  intake_id uuid,
                  from_address text,
                  envelope_recipient text,
                  subject text,
                  received_at timestamptz,
                  attachment_count integer NOT NULL DEFAULT 0,
                  status text NOT NULL DEFAULT 'received',
                  created_at timestamptz NOT NULL DEFAULT now(),
                  updated_at timestamptz NOT NULL DEFAULT now(),
                  UNIQUE (provider, provider_message_id)
                );
                CREATE TABLE IF NOT EXISTS candidates (
                  phone text PRIMARY KEY,
                  name text,
                  email text,
                  current_status text,
                  active_company_code text,
                  profile jsonb NOT NULL DEFAULT '{}'::jsonb,
                  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                  data_source text,
                  created_at timestamptz NOT NULL DEFAULT now(),
                  updated_at timestamptz NOT NULL DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS applications (
                  app_key text PRIMARY KEY,
                  phone text NOT NULL,
                  company_code text NOT NULL,
                  position_code text,
                  status text,
                  current_step text,
                  raw_json jsonb NOT NULL DEFAULT '{}'::jsonb,
                  data_source text,
                  data_source_detail text,
                  created_at timestamptz,
                  updated_at timestamptz
                );
                """
            )
            ingress.ensure_schema(cur)
            authority.ensure_schema(cur)
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
                cur.execute(
                    """
                    INSERT INTO intake_addresses
                      (company_code, local_part, domain, label, metadata)
                    VALUES (%s,%s,'authority.test',%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        company,
                        company.lower(),
                        MARKER,
                        app.Json({"marker": MARKER}),
                    ),
                )
        conn.commit()


def seed_candidate(
    *,
    company: str,
    candidate_phone: str,
    name: str,
    email: str | None = None,
    profile_phone: str | None = None,
    app_key: str | None = None,
) -> str:
    key = app_key or f"{candidate_phone}-{company}-IMPORT"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO candidates
                  (phone,name,email,current_status,active_company_code,profile,raw_json,data_source)
                VALUES (%s,%s,%s,'needs_role',%s,%s,%s,'production')
                ON CONFLICT (phone) DO NOTHING
                """,
                (
                    candidate_phone,
                    name,
                    email,
                    company,
                    app.Json(
                        {
                            "contact": {
                                "email": email,
                                "phone": profile_phone,
                                "name": name,
                            },
                            "marker": MARKER,
                        }
                    ),
                    app.Json({"marker": MARKER}),
                ),
            )
            cur.execute(
                """
                INSERT INTO applications
                  (app_key,phone,company_code,position_code,status,current_step,
                   raw_json,data_source,data_source_detail,created_at,updated_at)
                VALUES (%s,%s,%s,'','needs_role','import_review',%s,
                        'production',%s,CURRENT_DATE,CURRENT_DATE)
                ON CONFLICT (app_key) DO NOTHING
                """,
                (
                    key,
                    candidate_phone,
                    company,
                    app.Json({"marker": MARKER}),
                    MARKER,
                ),
            )
        conn.commit()
    return key


def create_document(
    *,
    company: str,
    label: str,
    content: bytes | None = None,
    sender: str = "shared-recruiter@example.test",
) -> dict[str, Any]:
    data = content or _pdf(label)
    digest = hashlib.sha256(data).hexdigest()
    inbound_id = str(uuid.uuid4())
    submission_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    ordinal = 1
    store = ingress.LocalQuarantineStore(Path(os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"]))
    quarantine_key, _reused = store.write(
        company_code=company,
        inbound_id=inbound_id,
        ordinal=ordinal,
        content_sha256=digest,
        data=data,
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT intake_id::text FROM intake_addresses WHERE company_code=%s LIMIT 1",
                (company,),
            )
            intake_id = cur.fetchone()["intake_id"]
            message_id = f"authority-{label}-{uuid.uuid4()}"
            cur.execute(
                """
                INSERT INTO inbound_messages
                  (inbound_id,provider,provider_message_id,company_code,intake_id,
                   from_address,envelope_recipient,subject,received_at,
                   attachment_count,status,durable_at,total_attachment_bytes)
                VALUES (%s,'postmark',%s,%s,%s,%s,%s,%s,now(),1,'queued',now(),%s)
                """,
                (
                    inbound_id,
                    message_id,
                    company,
                    intake_id,
                    sender,
                    f"{company.lower()}@authority.test",
                    label,
                    len(data),
                ),
            )
            cur.execute(
                """
                INSERT INTO intake_submissions
                  (submission_id,inbound_id,company_code,intake_id,provider,
                   provider_message_id,envelope_recipient,sender_address,subject,
                   received_at,attachment_count,accepted_attachment_count,
                   total_attachment_bytes,status)
                VALUES (%s,%s,%s,%s,'postmark',%s,%s,%s,%s,now(),1,1,%s,'durable')
                """,
                (
                    submission_id,
                    inbound_id,
                    company,
                    intake_id,
                    message_id,
                    f"{company.lower()}@authority.test",
                    sender,
                    label,
                    len(data),
                ),
            )
            cur.execute(
                """
                INSERT INTO intake_documents
                  (document_id,submission_id,inbound_id,company_code,
                   attachment_ordinal,original_filename,claimed_mime,detected_mime,
                   size_bytes,content_sha256,quarantine_key,storage_status,safety_state,
                   metadata)
                VALUES (%s,%s,%s,%s,%s,%s,'application/pdf','application/pdf',
                        %s,%s,%s,'stored','scan_pending',%s)
                """,
                (
                    document_id,
                    submission_id,
                    inbound_id,
                    company,
                    ordinal,
                    f"{label}.pdf",
                    len(data),
                    digest,
                    quarantine_key,
                    app.Json({"marker": MARKER}),
                ),
            )
        conn.commit()
    CREATED_DOCS.append(document_id)
    return {
        "company": company,
        "inbound_id": inbound_id,
        "submission_id": submission_id,
        "document_id": document_id,
        "digest": digest,
        "quarantine_key": quarantine_key,
        "sender": sender,
    }


def scan(
    document: dict[str, Any],
    state: str,
    reason: str | None = None,
) -> dict[str, Any]:
    config = ingress.IngressConfig.from_env(os.environ.get("WATHEFNI_WORKSPACE"))

    def injected(_path: Path, _config: ingress.IngressConfig) -> tuple[str, str | None]:
        return state, reason

    try:
        ingress.scan_document(
            db_connect=app.db_connect,
            document_id=document["document_id"],
            company_code=document["company"],
            config=config,
            scanner=injected,
        )
    except ingress.RetryableJobError:
        if state != "unavailable":
            raise
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            latest = authority.latest_scan_decision(
                cur,
                company_code=document["company"],
                intake_document_id=document["document_id"],
            )
    return latest or {}


def resolve(
    document: dict[str, Any],
    *,
    name: str | None,
    email: str | None,
    phone: str | None,
    extraction_method: str = "poppler",
) -> dict[str, Any]:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            assert_true(
                authority.scan_is_authoritatively_clean(
                    cur,
                    company_code=document["company"],
                    intake_document_id=document["document_id"],
                    content_sha256=document["digest"],
                ),
                "identity extraction requires durable clean scan",
            )
            identity = {"full_name": name, "email": email, "phone": phone}
            authority.record_identity_extraction(
                cur,
                company_code=document["company"],
                inbound_id=document["inbound_id"],
                intake_document_id=document["document_id"],
                content_sha256=document["digest"],
                extraction_status="completed",
                extraction_method=extraction_method,
                extracted_text=f"{name or ''}\n{email or ''}\n{phone or ''}",
                extracted_identity=identity,
                document_identity_evidence={
                    "method": extraction_method,
                    "content_sha256": document["digest"],
                },
            )
            decision = authority.resolve_identity(
                cur,
                company_code=document["company"],
                inbound_id=document["inbound_id"],
                intake_document_id=document["document_id"],
                content_sha256=document["digest"],
                sender_email=document["sender"],
                extracted_identity=identity,
            )
        conn.commit()
    return decision


def protected_counts() -> dict[str, int]:
    tables = [
        "jobs",
        "interviews",
        "offers",
        "candidate_rank_evaluations",
        "outbound_delivery_events",
        "intake_admission_events",
        "talent_pool_classification_jobs",
        "candidate_classification_runs",
    ]
    result: dict[str, int] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",))
                if not (cur.fetchone() or {}).get("table_name"):
                    result[table] = 0
                    continue
                cur.execute(
                    f"SELECT count(*) AS c FROM {table} WHERE company_code = ANY(%s)",
                    (COMPANIES,),
                )
                result[table] = int(cur.fetchone()["c"])
    return result


def qualification_matrix() -> dict[str, Any]:
    baseline = protected_counts()
    legacy_email = app._import_process_one_file(
        None,
        company=COMPANY_A,
        batch_id="legacy-mailbox-authority-check",
        source="email",
        company_positions=[],
        filename="Forwarded Candidate CV.pdf",
        data=b"%PDF-1.4 legacy mailbox must fail closed",
        seen_checksums={},
        meta={"email": "recruiter@example.test"},
    )
    assert_true(
        legacy_email.get("status") == "failed"
        and legacy_email.get("error")
        == "durable_scan_and_identity_authority_required",
        "legacy mailbox import fails closed before sender-based identity mutation",
    )

    own = create_document(company=COMPANY_A, label="candidate-own", sender="own@example.test")
    assert_true(scan(own, "clean")["state"] == "clean", "clean scan durable")
    own_decision = resolve(
        own, name="Own Candidate", email="own@example.test", phone="50000001"
    )
    assert_true(own_decision["outcome"] == "new_candidate", "own CV new candidate")

    forwarded = create_document(
        company=COMPANY_A, label="hr-forward", sender="hr@example.test"
    )
    scan(forwarded, "clean")
    forwarded_decision = resolve(
        forwarded,
        name="Forwarded Candidate",
        email="forwarded@example.test",
        phone="50000002",
    )
    assert_true(
        forwarded_decision["extracted_email"] == "forwarded@example.test"
        and forwarded_decision["sender_email_provenance"] == "hr@example.test",
        "sender is provenance only",
    )

    recruiter_results = []
    for index in (1, 2, 3):
        item = create_document(
            company=COMPANY_A,
            label=f"recruiter-{index}",
            sender="shared-recruiter@example.test",
        )
        scan(item, "clean")
        recruiter_results.append(
            resolve(
                item,
                name=f"Recruiter Candidate {index}",
                email=f"recruiter{index}@example.test",
                phone=f"5000010{index}",
            )
        )
    assert_true(
        len({row["selected_candidate_phone"] for row in recruiter_results}) == 3,
        "same sender yields distinct CV identities",
    )

    email_app = seed_candidate(
        company=COMPANY_A,
        candidate_phone="seed-email",
        name="Email Match",
        email="email.match@example.test",
    )
    exact_email = create_document(company=COMPANY_A, label="exact-email")
    scan(exact_email, "clean")
    exact_email_decision = resolve(
        exact_email,
        name="Email Match",
        email="email.match@example.test",
        phone=None,
    )
    assert_true(
        exact_email_decision["outcome"] == "safe_exact_reuse"
        and exact_email_decision["selected_app_key"] == email_app,
        "exact tenant CV email safely reuses",
    )

    phone_app = seed_candidate(
        company=COMPANY_A,
        candidate_phone="seed-phone",
        name="Phone Match",
        profile_phone="+96550000999",
    )
    exact_phone = create_document(company=COMPANY_A, label="exact-phone")
    scan(exact_phone, "clean")
    exact_phone_decision = resolve(
        exact_phone,
        name="Phone Match",
        email=None,
        phone="+96550000999",
    )
    assert_true(
        exact_phone_decision["outcome"] == "safe_exact_reuse"
        and exact_phone_decision["selected_app_key"] == phone_app,
        "exact tenant CV phone safely reuses",
    )

    seed_candidate(
        company=COMPANY_A,
        candidate_phone="seed-name",
        name="Name Only Person",
    )
    name_only = create_document(company=COMPANY_A, label="name-only")
    scan(name_only, "clean")
    name_only_decision = resolve(
        name_only, name="Name Only Person", email=None, phone=None
    )
    assert_true(
        name_only_decision["outcome"] == "possible_match",
        "name-only does not auto-merge",
    )

    conflict = create_document(company=COMPANY_A, label="identity-conflict")
    scan(conflict, "clean")
    conflict_decision = resolve(
        conflict,
        name="Different Human",
        email="email.match@example.test",
        phone=None,
    )
    assert_true(
        conflict_decision["outcome"] == "conflict"
        and not conflict_decision["ownership_confirmed"],
        "conflicting CV identity fails closed",
    )

    legitimate = create_document(company=COMPANY_A, label="legitimate-newer")
    scan(legitimate, "clean")
    legitimate_decision = resolve(
        legitimate,
        name="Email Match",
        email="email.match@example.test",
        phone=None,
    )
    assert_true(
        legitimate_decision["outcome"] == "safe_exact_reuse",
        "legitimate newer CV safely reuses candidate",
    )

    scanned = create_document(company=COMPANY_A, label="scanned-cv")
    scan(scanned, "clean")
    scanned_decision = resolve(
        scanned,
        name="Scanned Candidate",
        email="scanned@example.test",
        phone="50000222",
        extraction_method="mistral_ocr",
    )
    assert_true(
        scanned_decision["outcome"] == "new_candidate",
        "OCR-derived identity follows same authority",
    )

    duplicate_source = create_document(
        company=COMPANY_A, label="duplicate-source", content=_pdf("duplicate bytes")
    )
    first_scan = scan(duplicate_source, "clean")
    resolve(
        duplicate_source,
        name="Duplicate Person",
        email="duplicate@example.test",
        phone="50000333",
    )
    duplicate = create_document(
        company=COMPANY_A, label="duplicate-resend", content=_pdf("duplicate bytes")
    )
    second_scan = scan(duplicate, "clean")
    duplicate_decision = resolve(
        duplicate,
        name="Duplicate Person",
        email="duplicate@example.test",
        phone="50000333",
    )
    assert_true(
        str(second_scan.get("reused_from_decision_id"))
        == str(first_scan.get("decision_id"))
        and duplicate_decision["selected_candidate_phone"]
        == authority._provisional_phone(
            COMPANY_A,
            email="duplicate@example.test",
            phone="50000333",
            content_sha256=duplicate["digest"],
        ),
        "duplicate reuses bounded clean scan and deterministic identity",
    )

    infected = create_document(company=COMPANY_A, label="infected")
    infected_scan = scan(infected, "malware", "eicar_test_signature")
    unavailable = create_document(company=COMPANY_A, label="scanner-unavailable")
    unavailable_scan = scan(unavailable, "unavailable", "scanner_unavailable")
    timeout = create_document(company=COMPANY_A, label="scan-timeout")
    timeout_scan = scan(timeout, "unavailable", "scan_timeout")
    malformed = create_document(company=COMPANY_A, label="malformed-result")
    malformed_scan = scan(malformed, "unavailable", "malformed_scanner_result")
    missing = create_document(company=COMPANY_A, label="missing-result")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            missing_authorized = authority.scan_is_authoritatively_clean(
                cur,
                company_code=COMPANY_A,
                intake_document_id=missing["document_id"],
                content_sha256=missing["digest"],
            )
            cur.execute(
                """
                SELECT count(*) AS c FROM inbound_cv_identity_extractions
                WHERE intake_document_id = ANY(%s::uuid[])
                """,
                (
                    [
                        infected["document_id"],
                        unavailable["document_id"],
                        timeout["document_id"],
                        malformed["document_id"],
                        missing["document_id"],
                    ],
                ),
            )
            unsafe_extractions = int(cur.fetchone()["c"])
    assert_true(infected_scan["state"] == "infected", "infected durable state")
    assert_true(
        unavailable_scan["state"] == "scan_failed"
        and timeout_scan["state"] == "scan_failed"
        and malformed_scan["state"] == "scan_failed",
        "unavailable timeout malformed all fail closed",
    )
    assert_true(
        not missing_authorized and unsafe_extractions == 0,
        "missing/unproven and infected files never reach extraction",
    )

    cross_app = seed_candidate(
        company=COMPANY_A,
        candidate_phone="cross-tenant-a",
        name="Cross Tenant",
        email="cross@example.test",
    )
    cross = create_document(company=COMPANY_B, label="cross-tenant")
    scan(cross, "clean")
    cross_decision = resolve(
        cross,
        name="Cross Tenant",
        email="cross@example.test",
        phone=None,
    )
    assert_true(
        cross_decision["outcome"] == "new_candidate"
        and cross_decision["selected_app_key"] != cross_app,
        "identity matching is tenant scoped",
    )

    unclear = create_document(company=COMPANY_A, label="unclear")
    scan(unclear, "clean")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            authority.record_identity_extraction(
                cur,
                company_code=COMPANY_A,
                inbound_id=unclear["inbound_id"],
                intake_document_id=unclear["document_id"],
                content_sha256=unclear["digest"],
                extraction_status="failed",
                extraction_method="ocr",
                extracted_text=None,
                extracted_identity={},
                document_identity_evidence={"quality_ok": False},
                error_code="low_quality_text",
            )
            unclear_decision = authority.record_identity_failure(
                cur,
                company_code=COMPANY_A,
                inbound_id=unclear["inbound_id"],
                intake_document_id=unclear["document_id"],
                content_sha256=unclear["digest"],
                sender_email=unclear["sender"],
                reason_code="low_quality_text",
            )
        conn.commit()
    assert_true(
        unclear_decision["outcome"] == "possible_match"
        and not unclear_decision["ownership_confirmed"],
        "unclear CV is held for review",
    )

    after = protected_counts()
    assert_true(after == baseline, "protected mutation counts unchanged")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS c FROM intake_processing_jobs
                WHERE company_code = ANY(%s)
                  AND job_type IN ('cv_extraction','profile_structuring','embedding')
                """,
                (COMPANIES,),
            )
            unsafe_jobs = int(cur.fetchone()["c"])
            cur.execute(
                """
                SELECT count(*) AS c FROM inbound_cv_identity_reviews
                WHERE company_code=%s AND status='open'
                """,
                (COMPANY_A,),
            )
            reviews = int(cur.fetchone()["c"])
    assert_true(unsafe_jobs == 0, "no downstream extraction/embedding jobs created")
    assert_true(reviews >= 3, "weak/conflict/unclear review records created")

    return {
        "sender_provenance_only": True,
        "legacy_mailbox_import": legacy_email["error"],
        "recruiter_distinct_candidates": len(recruiter_results),
        "exact_email_outcome": exact_email_decision["outcome"],
        "exact_phone_outcome": exact_phone_decision["outcome"],
        "name_only_outcome": name_only_decision["outcome"],
        "conflict_outcome": conflict_decision["outcome"],
        "cross_tenant_outcome": cross_decision["outcome"],
        "scanned_cv_outcome": scanned_decision["outcome"],
        "scan_states": {
            "clean": own_decision["outcome"],
            "infected": infected_scan["state"],
            "unavailable": unavailable_scan["state"],
            "timeout": timeout_scan["state"],
            "malformed": malformed_scan["state"],
            "missing_authorized": missing_authorized,
        },
        "unsafe_extractions": unsafe_extractions,
        "unsafe_downstream_jobs": unsafe_jobs,
        "identity_reviews": reviews,
        "protected_before": baseline,
        "protected_after": after,
    }


def schema_check() -> dict[str, Any]:
    expected = {
        "inbound_attachment_scan_decisions",
        "inbound_cv_identity_extractions",
        "inbound_cv_identity_resolutions",
        "inbound_cv_identity_reviews",
        "inbound_cv_identity_events",
        "candidate_identity_keys",
        "candidate_classification_run_invalidations",
    }
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema='public' AND table_name = ANY(%s)
                """,
                (sorted(expected),),
            )
            actual = {row["table_name"] for row in cur.fetchall()}
            cur.execute(
                """
                SELECT state FROM (
                  VALUES ('pending_scan'),('clean'),('infected'),
                         ('scan_failed'),('quarantined')
                ) expected(state)
                """
            )
            states = [row["state"] for row in cur.fetchall()]
    assert_true(actual == expected, "all additive authority tables present")
    return {"tables": sorted(actual), "scan_states": states}


def cleanup() -> dict[str, Any]:
    removed = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('wathefni.authority_cleanup','synthetic',true)"
            )
            cur.execute(
                "SELECT app_key, phone FROM applications WHERE company_code = ANY(%s)",
                (COMPANIES,),
            )
            apps = [dict(row) for row in cur.fetchall()]
            app_keys = [row["app_key"] for row in apps]
            phones = [row["phone"] for row in apps]
            if app_keys:
                for table in (
                    "candidate_documents",
                    "file_registry",
                    "semantic_documents",
                ):
                    cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",))
                    if not (cur.fetchone() or {}).get("table_name"):
                        continue
                    column = "app_key" if table == "candidate_documents" else (
                        "subject_key" if table == "file_registry" else "entity_key"
                    )
                    cur.execute(
                        f"DELETE FROM {table} WHERE {column} = ANY(%s)",
                        (app_keys,),
                    )
                    removed += cur.rowcount
                cur.execute("DELETE FROM applications WHERE app_key = ANY(%s)", (app_keys,))
                removed += cur.rowcount
            cur.execute(
                "DELETE FROM intake_processing_jobs WHERE company_code = ANY(%s)",
                (COMPANIES,),
            )
            removed += cur.rowcount
            cur.execute(
                "DELETE FROM inbound_messages WHERE company_code = ANY(%s)",
                (COMPANIES,),
            )
            removed += cur.rowcount
            cur.execute(
                "DELETE FROM intake_addresses WHERE company_code = ANY(%s)",
                (COMPANIES,),
            )
            removed += cur.rowcount
            cur.execute(
                "DELETE FROM intake_tenant_queue_state WHERE company_code = ANY(%s)",
                (COMPANIES,),
            )
            removed += cur.rowcount
            cur.execute(
                "DELETE FROM intake_quota_usage WHERE company_code = ANY(%s)",
                (COMPANIES,),
            )
            removed += cur.rowcount
            if phones:
                cur.execute(
                    """
                    DELETE FROM candidates c
                    WHERE c.phone = ANY(%s)
                      AND NOT EXISTS (
                        SELECT 1 FROM applications a WHERE a.phone=c.phone
                      )
                    """,
                    (phones,),
                )
                removed += cur.rowcount
            cur.execute(
                "DELETE FROM companies WHERE company_code = ANY(%s)", (COMPANIES,)
            )
            removed += cur.rowcount
        conn.commit()
    shutil.rmtree(ROOT, ignore_errors=True)
    return {"rows_removed": removed}


def zero_residue() -> dict[str, int]:
    tables = [
        "companies",
        "intake_addresses",
        "inbound_messages",
        "intake_submissions",
        "intake_documents",
        "intake_processing_jobs",
        "inbound_attachment_scan_decisions",
        "inbound_cv_identity_extractions",
        "inbound_cv_identity_resolutions",
        "inbound_cv_identity_reviews",
        "inbound_cv_identity_events",
        "candidate_identity_keys",
        "applications",
    ]
    counts: dict[str, int] = {}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for table in tables:
                column = "company_code"
                cur.execute(
                    f"SELECT count(*) AS c FROM {table} WHERE {column} = ANY(%s)",
                    (COMPANIES,),
                )
                counts[table] = int(cur.fetchone()["c"])
    assert_true(all(value == 0 for value in counts.values()), "zero synthetic residue")
    return counts


def main() -> int:
    failed = False
    cleanup_result: dict[str, Any] = {}
    try:
        check("setup", setup)
        check("additive_schema_and_exact_scan_states", schema_check)
        check("full_scan_and_identity_authority_matrix", qualification_matrix)
    except Exception:
        failed = True
    finally:
        try:
            cleanup_result = cleanup()
            check("zero_synthetic_residue", zero_residue)
        except Exception as exc:
            failed = True
            RESULTS.append(
                {
                    "name": "cleanup",
                    "status": "FAIL",
                    "detail": f"{type(exc).__name__}: {exc}",
                }
            )
    summary = {
        "environment": os.environ.get("WATHEFNI_ENV"),
        "results": RESULTS,
        "cleanup": cleanup_result,
        "passed": not failed and all(row["status"] == "PASS" for row in RESULTS),
    }
    print(json.dumps(summary, indent=2, default=str, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
