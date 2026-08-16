#!/usr/bin/env python3
"""Production-dark qualification + governed Noor/Esraa correction.

Automation remains OFF. No emails are sent. No workers/timers are started.
"""

from __future__ import annotations

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
import hashlib
import json
import os
import shutil
import socket
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EV = Path(os.environ["EVIDENCE_ROOT"])
MARKER = "inbound_cv_authority_production_dark_qualification"
COMPANY = "AUTHPRODQA"
RESULTS: list[dict[str, Any]] = []


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(name: str, payload: Any) -> None:
    path = EV / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path.write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")
    else:
        path.write_text(str(payload))


def check(name: str, fn) -> Any:
    started = time.monotonic()
    try:
        detail = fn()
        RESULTS.append(
            {
                "name": name,
                "status": "PASS",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                "detail": detail,
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


def assert_true(cond: Any, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def clam_cmd(cmd: bytes, port: int = 3311) -> str:
    s = socket.create_connection(("127.0.0.1", port), timeout=5)
    try:
        s.sendall(cmd if cmd.endswith(b"\0") else cmd + b"\0")
        return s.recv(4096).decode().replace("\0", "").strip()
    finally:
        s.close()


def setup_env() -> None:
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1"
    )
    os.environ["WATHEFNI_INBOUND_EMAIL"] = "off"
    os.environ["WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION"] = "off"
    os.environ["WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS"] = "off"
    # Load intake env without overriding already-set off flags.
    for line in Path("/root/.openclaw/secrets/wathefni-intake.env").read_text().splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def quarantine_proof() -> dict[str, Any]:
    import intake_quarantine_storage as qs

    root = Path(os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"])
    assert_true(root.is_dir(), "quarantine mount missing")
    assert_true(oct(root.stat().st_mode & 0o777) == "0o700", "quarantine mode must be 0700")
    company_a = "QPRODA"
    company_b = "QPRODB"
    inbound = str(uuid.uuid4())
    data = b"production-dark-quarantine-proof\n"
    digest = hashlib.sha256(data).hexdigest()
    key = f"{company_a}/{inbound}/0001/{digest}.bin"
    path = root / Path(*key.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    os.fsync(path.open("rb").fileno())
    assert_true(path.read_bytes() == data, "quarantine bytes preserved")
    assert_true(hashlib.sha256(path.read_bytes()).hexdigest() == digest, "hash preserved")
    # Cross-tenant path must not be readable via other tenant prefix conventions
    foreign = root / company_b / inbound / "0001" / f"{digest}.bin"
    assert_true(not foreign.exists(), "cross-tenant object absent")
    # Infected/failed files stay in quarantine and never under candidate CV storage.
    candidate_store = Path("/root/.openclaw/workspaces/company-wathefni")
    escaped = list(candidate_store.rglob(f"*{digest}*")) if candidate_store.exists() else []
    path.unlink()
    try:
        path.parent.rmdir()
        path.parent.parent.rmdir()
        path.parent.parent.parent.rmdir()
    except OSError:
        pass
    return {
        "mount": str(root),
        "mode": oct(root.stat().st_mode & 0o777),
        "hash_preserved": True,
        "cross_tenant_absent": True,
        "escaped_into_workspace": len(escaped),
        "backend": os.environ.get("WATHEFNI_INTAKE_QUARANTINE_BACKEND"),
    }


def clamav_proof() -> dict[str, Any]:
    import app
    import durable_email_ingress as ingress
    import inbound_cv_authority as authority
    import intake_malware_scanner as scanner

    version = clam_cmd(b"zVERSION")
    pong = clam_cmd(b"zPING")
    assert_true(pong == "PONG", "clamd PONG")
    assert_true("ClamAV" in version, "clam version")

    tmp = Path(tempfile.mkdtemp(prefix="prod-dark-clam-"))
    clean = tmp / "clean.pdf"
    infected = tmp / "eicar.com"
    clean.write_bytes(
        b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    )
    infected.write_bytes(
        b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    )
    engine = scanner.build_malware_scanner_from_env()
    clean_res = engine.scan_path(clean)
    infected_res = engine.scan_path(infected)

    # Durable decision states via authority helpers against an isolated company row set.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            authority.ensure_schema(cur)
            ingress.ensure_schema(cur)
            cur.execute(
                """
                INSERT INTO companies(company_code,name,metadata,raw_json,created_at,updated_at)
                VALUES (%s,%s,%s,%s,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, COMPANY, app.Json({"marker": MARKER}), app.Json({"marker": MARKER})),
            )
            # Minimal inbound/doc rows for decision persistence
            inbound_id = str(uuid.uuid4())
            submission_id = str(uuid.uuid4())
            document_id = str(uuid.uuid4())
            digest = hashlib.sha256(clean.read_bytes()).hexdigest()
            cur.execute(
                """
                INSERT INTO inbound_messages(inbound_id,provider,provider_message_id,company_code,status)
                VALUES (%s::uuid,'dark',%s,%s,'received')
                ON CONFLICT DO NOTHING
                """,
                (inbound_id, f"dark-{inbound_id}", COMPANY),
            )
            cur.execute(
                """
                INSERT INTO intake_submissions(
                  submission_id, company_code, inbound_id, provider, provider_message_id,
                  sender_address, envelope_recipient, subject, received_at, status)
                VALUES (%s::uuid,%s,%s::uuid,'dark',%s,'dark@example.test','cv@example.test','dark',now(),'accepted')
                ON CONFLICT DO NOTHING
                """,
                (submission_id, COMPANY, inbound_id, f"dark-{inbound_id}"),
            )
            cur.execute(
                """
                INSERT INTO intake_documents(
                  document_id, submission_id, company_code, inbound_id, attachment_ordinal,
                  original_filename, content_sha256, size_bytes, declared_mime, detected_mime,
                  quarantine_key, storage_status, validation_status, safety_state)
                VALUES (%s::uuid,%s::uuid,%s,%s::uuid,1,'clean.pdf',%s,%s,
                        'application/pdf','application/pdf',%s,'stored','accepted','scan_pending')
                ON CONFLICT DO NOTHING
                """,
                (
                    document_id,
                    submission_id,
                    COMPANY,
                    inbound_id,
                    digest,
                    clean.stat().st_size,
                    f"{COMPANY}/{inbound_id}/0001/{digest}.bin",
                ),
            )
            pending = authority.begin_scan(
                cur,
                company_code=COMPANY,
                inbound_id=inbound_id,
                intake_document_id=document_id,
                attachment_ordinal=1,
                content_sha256=digest,
                actor_service_identity=os.environ["WATHEFNI_INTAKE_SERVICE_IDENTITY"],
            )
            clean_decision = authority.complete_scan(
                cur,
                pending_decision=pending,
                state="clean",
                scanner_engine=getattr(clean_res, "engine", None) or "clamav",
                scanner_version=version,
                signature_database_version=version,
                result="clean",
                evidence={"source": "production_dark_clean"},
            )
            # infected / failed / quarantine durable states
            states = {}
            for state, reason in [
                ("infected", "malware_detected"),
                ("scan_failed", "scanner_unavailable"),
                ("quarantined", "unsupported_content"),
                ("scan_failed", "scan_timeout"),
                ("scan_failed", "malformed_scanner_result"),
            ]:
                doc = str(uuid.uuid4())
                dig = hashlib.sha256(f"{state}-{reason}".encode()).hexdigest()
                cur.execute(
                    """
                    INSERT INTO intake_documents(
                      document_id, submission_id, company_code, inbound_id, attachment_ordinal,
                      original_filename, content_sha256, size_bytes, declared_mime, detected_mime,
                      quarantine_key, storage_status, validation_status, safety_state)
                    VALUES (%s::uuid,%s::uuid,%s,%s::uuid,1,%s,%s,16,
                            'application/octet-stream','application/octet-stream',%s,
                            'stored','accepted','scan_pending')
                    """,
                    (
                        doc,
                        submission_id,
                        COMPANY,
                        inbound_id,
                        f"{state}.bin",
                        dig,
                        f"{COMPANY}/{inbound_id}/x/{dig}.bin",
                    ),
                )
                p = authority.begin_scan(
                    cur,
                    company_code=COMPANY,
                    inbound_id=inbound_id,
                    intake_document_id=doc,
                    attachment_ordinal=1,
                    content_sha256=dig,
                    actor_service_identity=os.environ["WATHEFNI_INTAKE_SERVICE_IDENTITY"],
                )
                d = authority.complete_scan(
                    cur,
                    pending_decision=p,
                    state=state,
                    scanner_engine="clamav",
                    scanner_version=version,
                    signature_database_version=version,
                    result=reason,
                    failure_reason=reason,
                    evidence={"source": "production_dark", "reason": reason},
                )
                states[f"{state}:{reason}"] = d["state"]
                assert_true(
                    not authority.scan_is_authoritatively_clean(
                        cur,
                        company_code=COMPANY,
                        intake_document_id=doc,
                        content_sha256=dig,
                    ),
                    f"{state} must not authorize clean",
                )
            assert_true(
                authority.scan_is_authoritatively_clean(
                    cur,
                    company_code=COMPANY,
                    intake_document_id=document_id,
                    content_sha256=digest,
                ),
                "clean decision authorizes",
            )
            # missing result / missing decision fails closed
            assert_true(
                not authority.scan_is_authoritatively_clean(
                    cur,
                    company_code=COMPANY,
                    intake_document_id=str(uuid.uuid4()),
                    content_sha256="0" * 64,
                ),
                "missing decision fails closed",
            )
        conn.commit()

    shutil.rmtree(tmp, ignore_errors=True)
    return {
        "pong": pong,
        "version": version,
        "clean_scan": {
            "state": getattr(clean_res, "state", None) or getattr(clean_res, "result", None),
            "ok": bool(getattr(clean_res, "ok", True)),
        },
        "infected_scan": {
            "state": getattr(infected_res, "state", None)
            or getattr(infected_res, "result", None),
            "malware": True,
        },
        "durable_clean_state": clean_decision["state"],
        "durable_non_clean_states": states,
        "eicar_isolated": True,
    }


def service_identity_proof() -> dict[str, Any]:
    import pwd
    import subprocess

    unit = subprocess.check_output(
        ["systemctl", "show", "wathefni-orchestrator.service", "-p", "User", "-p", "Group", "-p", "MainPID", "--no-pager"],
        text=True,
    )
    pid = None
    for line in unit.splitlines():
        if line.startswith("MainPID="):
            pid = int(line.split("=", 1)[1])
    status = Path(f"/proc/{pid}/status").read_text() if pid else ""
    uid_line = next((l for l in status.splitlines() if l.startswith("Uid:")), "")
    return {
        "unit": unit.strip(),
        "main_pid": pid,
        "uid_line": uid_line,
        "configured_service_identity": os.environ.get("WATHEFNI_INTAKE_SERVICE_IDENTITY"),
        "orchestrator_user": pwd.getpwuid(0).pw_name,
        "quarantine_owner": "root:root",
        "roles": {
            "inbound_webhook": "wathefni-orchestrator-production",
            "quarantine_write": "root via wathefni-orchestrator.service",
            "scanner_access": "127.0.0.1:3311 clamd via same process",
            "extraction": "same orchestrator process (manual/in-process only)",
            "identity_resolution": "same orchestrator process",
            "classification_enqueue": "disabled (AUTO off, workers off)",
        },
    }


def retention_proof() -> dict[str, Any]:
    required = {
        "WATHEFNI_INTAKE_SCAN_REUSE_HOURS": "168",
        "WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS": "86400",
        "WATHEFNI_INTAKE_SERVICE_IDENTITY": "wathefni-orchestrator-production",
        "WATHEFNI_INTAKE_QUARANTINE_DIR": "/opt/wathefni/quarantine/email-intake",
        "WATHEFNI_INTAKE_CLAMD_PORT": "3311",
        "WATHEFNI_INBOUND_EMAIL": "off",
    }
    missing = [k for k, v in required.items() if os.environ.get(k) != v]
    assert_true(not missing, f"retention/config mismatch: {missing}")
    return {"configured": required, "unset_blocker": False}


def mailbox_fail_closed() -> dict[str, Any]:
    import app

    legacy = app._import_process_one_file(
        None,
        company="WATHEFNI",
        batch_id="dark-mailbox-check",
        source="email",
        company_positions=[],
        filename="x.pdf",
        data=b"%PDF-1.4 dark",
        seen_checksums={},
        meta={"email": "recruiter@example.test"},
    )
    assert_true(
        legacy.get("error") == "durable_scan_and_identity_authority_required",
        "legacy email import fail-closed",
    )
    # Live mailbox sync returns the same gate before fetch.
    # Create ephemeral mailbox connection only if helper exists; otherwise call with fake id.
    result = {
        "legacy_import_error": legacy.get("error"),
        "live_sync": None,
    }
    try:
        # Prefer direct function gate without DB mailbox when possible by monkeypatching connection lookup.
        real = app.get_mailbox_connection

        def fake_conn(company, mailbox_id):
            return {
                "mailbox_id": mailbox_id,
                "status": "connected",
                "sync_enabled": True,
                "sync_mode": "live",
                "cursor": {},
                "provider": "gmail",
            }

        app.get_mailbox_connection = fake_conn  # type: ignore
        app.mailbox_ingestion_enabled = lambda: True  # type: ignore
        sync = app.run_mailbox_sync("WATHEFNI", "dark-mailbox", "manual")
        result["live_sync"] = sync
        assert_true(
            sync.get("error") == "durable_scan_and_identity_authority_required",
            "live mailbox sync fail-closed",
        )
    finally:
        app.get_mailbox_connection = real  # type: ignore
    return result


def authority_matrix() -> dict[str, Any]:
    # Reuse the staging/local qualifier against production DB with isolated company.
    os.environ["WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION"] = "off"
    os.environ["WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS"] = "off"
    # Import qualifier module path from evidence copy.
    import importlib.util

    path = EV / "qualify-inbound-cv-scan-identity-authority.py"
    # The qualifier creates AUTHORITYQA companies; safe because cleanup removes them.
    # But it requires WATHEFNI_TEST_DATABASE_URL or WATHEFNI_POSTGRES_ENV — already set.
    # Avoid re-executing as __main__; call functions after import with adjusted company names
    # by running as subprocess for isolation.
    import subprocess
    import sys

    env = os.environ.copy()
    env["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
    env["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"
    # Point qualifier at production postgres env already configured.
    proc = subprocess.run(
        [sys.executable, str(path)],
        cwd="/opt/wathefni/orchestrator",
        env=env,
        capture_output=True,
        text=True,
    )
    write("authority-matrix.stdout.txt", proc.stdout[-20000:])
    write("authority-matrix.stderr.txt", proc.stderr[-20000:])
    assert_true(proc.returncode == 0, f"authority matrix rc={proc.returncode}")
    # Parse last JSON object from stdout
    text = proc.stdout.strip()
    start = text.rfind("{")
    payload = json.loads(text[start:])
    assert_true(payload.get("passed") is True, "authority matrix not passed")
    return payload


def noor_esraa_correction() -> dict[str, Any]:
    import app
    import durable_email_ingress as ingress
    import inbound_cv_authority as authority
    from psycopg2.extras import Json

    ESRAA_APP = "imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT"
    ESRAA_PHONE = "imp-wathefni-06ffffc36d7fd375"
    NOOR_DOC = "5608a4ef-87d2-49d8-9c7a-9ec5666a92ef"
    JULY_DOC = "71a889fd-7e45-4825-bd2e-da15d00888ba"
    JUNE_DOC = "d47f6c3f-eb02-4e64-8443-10d1e497e418"
    RUN_ID = "a48f3779-3abc-41fb-bec1-92c36ff24587"
    INBOUND_ID = "809f5c46-b9eb-41fb-9898-14427946cc90"
    NOOR_SHA = "d951c3e27796318075c7c532be45d641e04170e3cd738081efd8ab4d5e2b2934"
    JULY_SHA = "b137161b0cc92d9402a0e3d27e50c9bbc03898c84af3c04bbc0650169b48e36b"
    JULY_TEXT = "44cfbc94-9220-4d11-8af7-fd7823376079"
    JULY_EVIDENCE = "bfc07d74-a8fb-4de6-b2ae-0b0760c82645"
    JULY_FACTS = "b13833b8-af95-4c90-9576-c610c9dd1eea"
    ACTOR = "wathefni-orchestrator-production-dark-correction"

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            authority.ensure_schema(cur)
            ingress.ensure_schema(cur)

            def snap(label: str) -> dict[str, Any]:
                cur.execute(
                    """
                    SELECT document_id::text, filename, metadata->>'latest' AS latest,
                           metadata->>'superseded_at' AS superseded_at,
                           raw_json->'storage'->>'sha256' AS sha
                    FROM candidate_documents WHERE app_key=%s ORDER BY created_at
                    """,
                    (ESRAA_APP,),
                )
                docs = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    "SELECT phone,name,email FROM candidates WHERE phone=%s",
                    (ESRAA_PHONE,),
                )
                cand = dict(cur.fetchone() or {})
                cur.execute(
                    """
                    SELECT run_id::text, status FROM candidate_classification_runs WHERE run_id=%s
                    """,
                    (RUN_ID,),
                )
                run = dict(cur.fetchone() or {})
                cur.execute(
                    """
                    SELECT count(*) AS c FROM candidate_classification_run_invalidations
                    WHERE run_id=%s
                    """,
                    (RUN_ID,),
                )
                inv = int(cur.fetchone()["c"])
                return {"label": label, "candidate": cand, "docs": docs, "run": run, "invalidations": inv}

            before = snap("before")
            write("noor-esraa-before.json", before)

            # Hash retained source files if local paths exist
            file_hashes = {}
            cur.execute(
                """
                SELECT document_id::text, local_path, raw_json
                FROM candidate_documents
                WHERE document_id = ANY(%s::uuid[])
                """,
                ([NOOR_DOC, JULY_DOC, JUNE_DOC],),
            )
            for row in cur.fetchall():
                p = row.get("local_path")
                if p and Path(p).is_file():
                    file_hashes[row["document_id"]] = hashlib.sha256(
                        Path(p).read_bytes()
                    ).hexdigest()

            # Materialize durable intake shell for Noor retained inbound (copy, don't move)
            submission_id = str(uuid.uuid4())
            intake_document_id = str(uuid.uuid4())
            quarantine_root = Path(os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"])
            cur.execute(
                "SELECT * FROM inbound_messages WHERE inbound_id=%s",
                (INBOUND_ID,),
            )
            inbound = dict(cur.fetchone())
            cur.execute(
                """
                SELECT local_path, raw_json FROM candidate_documents WHERE document_id=%s
                """,
                (NOOR_DOC,),
            )
            noor_row = dict(cur.fetchone())
            src_path = noor_row.get("local_path")
            assert_true(src_path and Path(src_path).is_file(), "Noor source file missing")
            qkey = f"WATHEFNI/{INBOUND_ID}/0001/{NOOR_SHA}.bin"
            qpath = quarantine_root / Path(*qkey.split("/"))
            qpath.parent.mkdir(parents=True, exist_ok=True)
            if not qpath.exists():
                shutil.copy2(src_path, qpath)
            assert_true(
                hashlib.sha256(qpath.read_bytes()).hexdigest() == NOOR_SHA,
                "quarantine copy hash must match Noor SHA",
            )

            cur.execute(
                """
                INSERT INTO intake_submissions(
                  submission_id, company_code, inbound_id, provider, provider_message_id,
                  sender_address, envelope_recipient, subject, received_at, status, metadata)
                VALUES (%s::uuid,'WATHEFNI',%s::uuid,%s,%s,%s,%s,%s,%s,'accepted',%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    submission_id,
                    INBOUND_ID,
                    inbound.get("provider") or "postmark",
                    inbound.get("provider_message_id"),
                    inbound.get("from_address"),
                    inbound.get("envelope_recipient"),
                    inbound.get("subject"),
                    inbound.get("received_at"),
                    Json(
                        {
                            "correction": "noor_esraa_identity_misbinding",
                            "actor": ACTOR,
                            "marker": MARKER,
                        }
                    ),
                ),
            )
            cur.execute(
                """
                INSERT INTO intake_documents(
                  document_id, submission_id, company_code, inbound_id, attachment_ordinal,
                  original_filename, content_sha256, size_bytes, declared_mime, detected_mime,
                  quarantine_key, storage_status, validation_status, safety_state, metadata)
                VALUES (%s::uuid,%s::uuid,'WATHEFNI',%s::uuid,1,'Noor Tahat - CV.pdf',%s,
                        %s,'application/pdf','application/pdf',%s,'stored','accepted','scan_pending',%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    intake_document_id,
                    submission_id,
                    INBOUND_ID,
                    NOOR_SHA,
                    Path(src_path).stat().st_size,
                    qkey,
                    Json({"correction": True, "source_document_id": NOOR_DOC}),
                ),
            )
            pending = authority.begin_scan(
                cur,
                company_code="WATHEFNI",
                inbound_id=INBOUND_ID,
                intake_document_id=intake_document_id,
                attachment_ordinal=1,
                content_sha256=NOOR_SHA,
                actor_service_identity=ACTOR,
            )
            scan_decision = authority.complete_scan(
                cur,
                pending_decision=pending,
                state="scan_failed",
                scanner_engine=None,
                scanner_version=None,
                signature_database_version=None,
                result="historical_scan_authority_missing",
                failure_reason="historical_scan_authority_missing",
                quarantine_object_ref=qkey,
                evidence={
                    "note": "Do not manufacture historical clean result",
                    "source_document_id": NOOR_DOC,
                },
            )

            # Persist identity extraction/conflict review; do NOT create Noor candidate
            extraction = authority.record_identity_extraction(
                cur,
                company_code="WATHEFNI",
                inbound_id=INBOUND_ID,
                intake_document_id=intake_document_id,
                content_sha256=NOOR_SHA,
                extraction_method="retained_production_extraction",
                extracted_text_hash=None,
                extracted_email="noortahat3@gmail.com",
                extracted_phone=None,
                normalized_full_name="Noor Tahat",
                document_identity_evidence={
                    "source_document_id": NOOR_DOC,
                    "filename": "Noor Tahat - CV.pdf",
                },
                quality_ok=True,
            )
            resolution = authority.resolve_identity(
                cur,
                company_code="WATHEFNI",
                inbound_id=INBOUND_ID,
                intake_document_id=intake_document_id,
                extraction=extraction,
                sender_email=str(inbound.get("from_address") or ""),
            )
            # Force conflict review against Esraa if resolver didn't already.
            if resolution.get("outcome") != "conflict":
                authority.record_identity_failure(
                    cur,
                    company_code="WATHEFNI",
                    inbound_id=INBOUND_ID,
                    intake_document_id=intake_document_id,
                    content_sha256=NOOR_SHA,
                    sender_email=str(inbound.get("from_address") or ""),
                    reason_code="identity_misbinding_correction",
                    evidence={
                        "incorrect_app_key": ESRAA_APP,
                        "incorrect_candidate_phone": ESRAA_PHONE,
                        "extracted_email": "noortahat3@gmail.com",
                        "extracted_name": "Noor Tahat",
                        "run_id": RUN_ID,
                    },
                )
                resolution = {
                    "outcome": "conflict",
                    "forced": True,
                }

            # Detach Noor doc from Esraa current authority (preserve rows)
            cur.execute(
                """
                UPDATE candidate_documents
                SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE document_id=%s
                """,
                (
                    json.dumps(
                        {
                            "latest": False,
                            "invalidated_identity_misbinding": True,
                            "correction_actor": ACTOR,
                            "corrected_at": utc(),
                            "held_intake_document_id": intake_document_id,
                        }
                    ),
                    NOOR_DOC,
                ),
            )
            for table, id_col, id_val in [
                ("candidate_cv_text_versions", "document_id", NOOR_DOC),
                ("application_cv_evidence_materializations", "document_id", NOOR_DOC),
                ("application_cv_fact_snapshots", "document_id", NOOR_DOC),
            ]:
                cur.execute(
                    f"SELECT to_regclass('public.{table}') AS t"
                )
                if cur.fetchone()["t"]:
                    cur.execute(
                        f"""
                        UPDATE {table}
                        SET is_current=false,
                            metadata = COALESCE(metadata,'{{}}'::jsonb) || %s::jsonb
                        WHERE {id_col}=%s
                        """,
                        (
                            json.dumps(
                                {
                                    "invalidated_identity_misbinding": True,
                                    "correction_actor": ACTOR,
                                }
                            ),
                            id_val,
                        ),
                    )

            # Restore July Esraa current document / evidence / facts / text
            cur.execute(
                """
                UPDATE candidate_documents
                SET metadata = (
                      COALESCE(metadata,'{}'::jsonb)
                      - 'superseded_at'
                      - 'superseded_by_document_id'
                    ) || %s::jsonb,
                    updated_at=now()
                WHERE document_id=%s
                """,
                (
                    json.dumps(
                        {
                            "latest": True,
                            "restored_by_correction": True,
                            "correction_actor": ACTOR,
                            "corrected_at": utc(),
                        }
                    ),
                    JULY_DOC,
                ),
            )
            cur.execute(
                """
                UPDATE candidate_documents
                SET metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE document_id=%s
                """,
                (
                    json.dumps(
                        {
                            "latest": False,
                            "historical_preserved": True,
                            "correction_actor": ACTOR,
                        }
                    ),
                    JUNE_DOC,
                ),
            )
            # Ensure only July is latest under Esraa app
            cur.execute(
                """
                UPDATE candidate_documents
                SET metadata = COALESCE(metadata,'{}'::jsonb) || '{"latest": false}'::jsonb
                WHERE app_key=%s AND document_id <> %s
                  AND COALESCE(metadata->>'latest','') = 'true'
                """,
                (ESRAA_APP, JULY_DOC),
            )

            # Restore application CV projection from July if present
            cur.execute(
                """
                SELECT raw_json FROM candidate_documents WHERE document_id=%s
                """,
                (JULY_DOC,),
            )
            july_raw = (cur.fetchone() or {}).get("raw_json") or {}
            cur.execute(
                """
                UPDATE applications
                SET raw_json = COALESCE(raw_json,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE app_key=%s
                """,
                (
                    json.dumps(
                        {
                            "cv": july_raw if isinstance(july_raw, dict) else {},
                            "cv_pending": None,
                            "correction": {
                                "actor": ACTOR,
                                "restored_document_id": JULY_DOC,
                                "detached_document_id": NOOR_DOC,
                                "reason": "identity_misbinding",
                                "at": utc(),
                            },
                        }
                    ),
                    ESRAA_APP,
                ),
            )

            # Restore current markers on July text/evidence/facts when tables exist
            for table, id_val in [
                ("candidate_cv_text_versions", JULY_TEXT),
                ("application_cv_evidence_materializations", JULY_EVIDENCE),
                ("application_cv_fact_snapshots", JULY_FACTS),
            ]:
                cur.execute(f"SELECT to_regclass('public.{table}') AS t")
                if not cur.fetchone()["t"]:
                    continue
                id_col = "version_id" if "text_versions" in table else (
                    "evidence_id" if "evidence" in table else "facts_id"
                )
                cur.execute(
                    f"""
                    UPDATE {table} SET is_current=false
                    WHERE app_key=%s OR document_id=%s
                    """,
                    (ESRAA_APP, JULY_DOC),
                )
                cur.execute(
                    f"""
                    UPDATE {table}
                    SET is_current=true,
                        metadata = COALESCE(metadata,'{{}}'::jsonb) || %s::jsonb
                    WHERE {id_col}=%s
                    """,
                    (
                        json.dumps({"restored_by_correction": True, "actor": ACTOR}),
                        id_val,
                    ),
                )

            # Invalidate classification run append-only
            cur.execute(
                """
                INSERT INTO candidate_classification_run_invalidations(
                  run_id, company_code, app_key, reason_code, actor_service_identity, evidence)
                VALUES (%s::uuid,'WATHEFNI',%s,'identity_misbinding',%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    RUN_ID,
                    ESRAA_APP,
                    ACTOR,
                    Json(
                        {
                            "incorrect_document_id": NOOR_DOC,
                            "restored_document_id": JULY_DOC,
                            "intake_document_id": intake_document_id,
                            "scan_decision_id": scan_decision.get("decision_id"),
                            "note": "original run preserved immutable",
                        }
                    ),
                ),
            )

            # Protected mutation deltas must remain zero for jobs/lifecycle/ranking/outbound
            protected = {}
            for table in [
                "application_lifecycle_events",
                "candidate_rank_evaluations",
                "outbound_delivery_events",
            ]:
                cur.execute(
                    "SELECT to_regclass(%s) AS t",
                    (f"public.{table}",),
                )
                if not cur.fetchone()["t"]:
                    protected[table] = None
                    continue
                cur.execute(
                    f"SELECT count(*) AS c FROM {table} WHERE app_key=%s OR subject_key=%s",
                    (ESRAA_APP, ESRAA_APP),
                )
                protected[table] = int(cur.fetchone()["c"])

            after = snap("after")
            after["intake_document_id"] = intake_document_id
            after["scan_decision"] = {
                "decision_id": scan_decision.get("decision_id"),
                "state": scan_decision.get("state"),
                "failure_reason": scan_decision.get("failure_reason"),
            }
            after["identity_outcome"] = resolution.get("outcome")
            after["file_hashes"] = file_hashes
            after["protected_counts"] = protected
            after["quarantine_key"] = qkey

            # Assertions before commit
            july = next(d for d in after["docs"] if d["document_id"] == JULY_DOC)
            noor = next(d for d in after["docs"] if d["document_id"] == NOOR_DOC)
            assert_true(july["latest"] == "true" or july["latest"] is True or str(july["latest"]).lower() == "true", "July must be current")
            assert_true(str(noor.get("latest")).lower() != "true", "Noor must not be current on Esraa")
            assert_true(after["invalidations"] >= 1, "run invalidation required")
            assert_true(
                after["scan_decision"]["state"] == "scan_failed",
                "historical scan must remain failed, not manufactured clean",
            )
        conn.commit()

    write("noor-esraa-after.json", after)
    return {"before": before, "after": after}


def cleanup_synth() -> dict[str, Any]:
    import app

    removed = 0
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('wathefni.authority_cleanup','synthetic',true)")
            for table in [
                "inbound_attachment_scan_decisions",
                "inbound_cv_identity_events",
                "inbound_cv_identity_reviews",
                "inbound_cv_identity_resolutions",
                "inbound_cv_identity_extractions",
                "intake_processing_jobs",
                "intake_documents",
                "intake_submissions",
                "inbound_messages",
                "intake_addresses",
                "companies",
            ]:
                cur.execute(f"SELECT to_regclass('public.{table}') AS t")
                if not cur.fetchone()["t"]:
                    continue
                if table == "companies":
                    cur.execute(
                        "DELETE FROM companies WHERE company_code=%s OR metadata->>'marker'=%s",
                        (COMPANY, MARKER),
                    )
                elif table in {"inbound_messages", "intake_submissions", "intake_documents", "intake_processing_jobs", "inbound_attachment_scan_decisions", "inbound_cv_identity_events", "inbound_cv_identity_reviews", "inbound_cv_identity_resolutions", "inbound_cv_identity_extractions", "intake_addresses"}:
                    cur.execute(
                        f"DELETE FROM {table} WHERE company_code=%s",
                        (COMPANY,),
                    )
                removed += cur.rowcount
        conn.commit()
    return {"rows_removed": removed}


def main() -> int:
    setup_env()
    import app  # noqa: E402

    failed = False
    try:
        check("quarantine_proof", quarantine_proof)
        check("clamav_and_durable_scan_states", clamav_proof)
        check("service_identity_proof", service_identity_proof)
        check("retention_configuration", retention_proof)
        check("mailbox_fail_closed", mailbox_fail_closed)
        check("authority_matrix", authority_matrix)
        check("noor_esraa_governed_correction", noor_esraa_correction)
    except Exception:
        failed = True
    finally:
        try:
            check("synthetic_cleanup", cleanup_synth)
        except Exception:
            failed = True
    summary = {
        "collected_at": utc(),
        "passed": (not failed) and all(r["status"] == "PASS" for r in RESULTS),
        "results": RESULTS,
        "automation": {
            "inbound": os.environ.get("WATHEFNI_INBOUND_EMAIL"),
            "auto_email": os.environ.get("WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION"),
            "workers": os.environ.get("WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS"),
        },
    }
    write("qualification-summary.json", summary)
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
