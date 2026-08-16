#!/usr/bin/env python3
"""Governed Noor/Esraa correction under production-dark scan/identity authority."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ORCH = Path("/opt/wathefni/orchestrator")
sys.path = [p for p in sys.path if Path(p).resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(ORCH))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_production_maintenance(operation='correct-noor-esraa-identity')
from psycopg2.extras import Json

EV = Path(os.environ["EVIDENCE_ROOT"])
ACTOR = "wathefni-orchestrator-production-dark-correction"
ESRAA_APP = "imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT"
ESRAA_PHONE = "imp-wathefni-06ffffc36d7fd375"
NOOR_DOC = "5608a4ef-87d2-49d8-9c7a-9ec5666a92ef"
JULY_DOC = "71a889fd-7e45-4825-bd2e-da15d00888ba"
JUNE_DOC = "d47f6c3f-eb02-4e64-8443-10d1e497e418"
RUN_ID = "a48f3779-3abc-41fb-bec1-92c36ff24587"
INBOUND_ID = "809f5c46-b9eb-41fb-9898-14427946cc90"
NOOR_SHA = "d951c3e27796318075c7c532be45d641e04170e3cd738081efd8ab4d5e2b2934"
JULY_TEXT = "44cfbc94-9220-4d11-8af7-fd7823376079"
JULY_EVIDENCE = "bfc07d74-a8fb-4de6-b2ae-0b0760c82645"
JULY_FACTS = "b13833b8-af95-4c90-9576-c610c9dd1eea"
INTAKE_ID = "2493b577-09e3-45c2-b923-b0c382c251df"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def write(name: str, payload) -> None:
    (EV / name).write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")


def main() -> int:
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
    os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-production-isolation-v1"
    )
    os.environ["WATHEFNI_INBOUND_EMAIL"] = "off"
    os.environ["WATHEFNI_INTAKE_SERVICE_IDENTITY"] = ACTOR
    for line in Path("/root/.openclaw/secrets/wathefni-intake.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

    import app
    import durable_email_ingress as ingress
    import inbound_cv_authority as authority

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            authority.ensure_schema(cur)
            ingress.ensure_schema(cur)

            def snap() -> dict:
                cur.execute(
                    """
                    SELECT document_id::text, filename, metadata->>'latest' AS latest,
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
                cand = dict(cur.fetchone())
                cur.execute(
                    """
                    SELECT count(*) AS c FROM candidate_classification_run_invalidations
                    WHERE run_id=%s AND reason_code='identity_misbinding'
                    """,
                    (RUN_ID,),
                )
                inv = int(cur.fetchone()["c"])
                def protected_count(table: str) -> int:
                    cur.execute(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema='public' AND table_name=%s
                        """,
                        (table,),
                    )
                    cols = {r["column_name"] for r in cur.fetchall()}
                    if not cols:
                        return 0
                    key = next(
                        (c for c in ("app_key", "subject_key", "application_key") if c in cols),
                        None,
                    )
                    if not key:
                        return 0
                    cur.execute(f"SELECT count(*) AS c FROM {table} WHERE {key}=%s", (ESRAA_APP,))
                    return int(cur.fetchone()["c"])

                return {
                    "candidate": cand,
                    "docs": docs,
                    "invalidations": inv,
                    "lifecycle": protected_count("application_lifecycle_events"),
                    "ranking": protected_count("candidate_rank_evaluations"),
                    "outbound": protected_count("outbound_delivery_events"),
                }

            before = snap()
            write("noor-esraa-before.json", before)

            cur.execute(
                "SELECT local_path FROM candidate_documents WHERE document_id=%s",
                (NOOR_DOC,),
            )
            src = cur.fetchone()["local_path"]
            assert Path(src).is_file(), "Noor source missing"
            assert hashlib.sha256(Path(src).read_bytes()).hexdigest() == NOOR_SHA

            quarantine_root = Path(os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"])
            qkey = f"WATHEFNI/{INBOUND_ID}/0001/{NOOR_SHA}.bin"
            qpath = quarantine_root / Path(*qkey.split("/"))
            qpath.parent.mkdir(parents=True, exist_ok=True)
            if not qpath.exists():
                shutil.copy2(src, qpath)
            assert hashlib.sha256(qpath.read_bytes()).hexdigest() == NOOR_SHA

            cur.execute(
                "SELECT provider, provider_message_id, from_address, envelope_recipient, subject, received_at FROM inbound_messages WHERE inbound_id=%s",
                (INBOUND_ID,),
            )
            inbound = dict(cur.fetchone())

            # One durable submission per inbound_id (unique). Reuse if present.
            cur.execute(
                "SELECT submission_id::text FROM intake_submissions WHERE inbound_id=%s",
                (INBOUND_ID,),
            )
            existing_sub = cur.fetchone()
            if existing_sub:
                submission_id = existing_sub["submission_id"]
            else:
                submission_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO intake_submissions(
                      submission_id, inbound_id, company_code, intake_id, provider,
                      provider_message_id, envelope_recipient, sender_address, subject,
                      received_at, attachment_count, accepted_attachment_count,
                      total_attachment_bytes, status, source_provenance)
                    VALUES (%s::uuid,%s::uuid,'WATHEFNI',%s::uuid,%s,%s,%s,%s,%s,%s,1,1,%s,'durable',%s)
                    """,
                    (
                        submission_id,
                        INBOUND_ID,
                        INTAKE_ID,
                        inbound.get("provider") or "postmark",
                        inbound.get("provider_message_id"),
                        inbound.get("envelope_recipient") or "",
                        inbound.get("from_address"),
                        inbound.get("subject"),
                        inbound.get("received_at"),
                        Path(src).stat().st_size,
                        Json(
                            {
                                "correction": "noor_esraa_identity_misbinding",
                                "actor": ACTOR,
                            }
                        ),
                    ),
                )

            cur.execute(
                """
                SELECT document_id::text FROM intake_documents
                WHERE company_code='WATHEFNI' AND inbound_id=%s AND content_sha256=%s
                """,
                (INBOUND_ID, NOOR_SHA),
            )
            existing_doc = cur.fetchone()
            if existing_doc:
                intake_document_id = existing_doc["document_id"]
            else:
                intake_document_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO intake_documents(
                      document_id, submission_id, inbound_id, company_code,
                      attachment_ordinal, original_filename, claimed_mime, detected_mime,
                      size_bytes, content_sha256, quarantine_key, storage_status,
                      safety_state, metadata)
                    VALUES (%s::uuid,%s::uuid,%s::uuid,'WATHEFNI',1,'Noor Tahat - CV.pdf',
                            'application/pdf','application/pdf',%s,%s,%s,'stored',
                            'scan_pending',%s)
                    """,
                    (
                        intake_document_id,
                        submission_id,
                        INBOUND_ID,
                        Path(src).stat().st_size,
                        NOOR_SHA,
                        qkey,
                        Json(
                            {
                                "correction": True,
                                "source_document_id": NOOR_DOC,
                                "actor": ACTOR,
                            }
                        ),
                    ),
                )

            # Historical scan remains failed — never manufacture clean.
            if not authority.latest_scan_decision(
                cur, company_code="WATHEFNI", intake_document_id=intake_document_id
            ):
                pending = authority.begin_scan(
                    cur,
                    company_code="WATHEFNI",
                    inbound_id=INBOUND_ID,
                    intake_document_id=intake_document_id,
                    attachment_ordinal=1,
                    content_sha256=NOOR_SHA,
                    quarantine_object_ref=qkey,
                )
                scan_decision = authority.complete_scan(
                    cur,
                    pending_decision=pending,
                    state="scan_failed",
                    scanner_engine=None,
                    signature_version=None,
                    failure_reason="historical_scan_authority_missing",
                    evidence={
                        "note": "Do not manufacture historical clean result",
                        "source_document_id": NOOR_DOC,
                        "actor": ACTOR,
                    },
                )
            else:
                scan_decision = authority.latest_scan_decision(
                    cur, company_code="WATHEFNI", intake_document_id=intake_document_id
                )

            extraction = authority.record_identity_extraction(
                cur,
                company_code="WATHEFNI",
                inbound_id=INBOUND_ID,
                intake_document_id=intake_document_id,
                content_sha256=NOOR_SHA,
                extraction_status="retained",
                extraction_method="retained_production_extraction",
                extracted_text=None,
                extracted_identity={
                    "email": "noortahat3@gmail.com",
                    "full_name": "Noor Tahat",
                    "phone": None,
                },
                document_identity_evidence={
                    "source_document_id": NOOR_DOC,
                    "filename": "Noor Tahat - CV.pdf",
                    "incorrect_app_key": ESRAA_APP,
                },
            )
            resolution = authority.resolve_identity(
                cur,
                company_code="WATHEFNI",
                inbound_id=INBOUND_ID,
                intake_document_id=intake_document_id,
                content_sha256=NOOR_SHA,
                sender_email=str(inbound.get("from_address") or ""),
                extracted_identity=extraction.get("extracted_identity")
                or {
                    "email": "noortahat3@gmail.com",
                    "full_name": "Noor Tahat",
                },
            )

            # Detach Noor from Esraa current authority; preserve rows.
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
            for table in [
                "candidate_cv_text_versions",
                "application_cv_evidence_materializations",
                "application_cv_fact_snapshots",
            ]:
                cur.execute(
                    f"""
                    UPDATE {table}
                    SET is_current=false,
                        provenance = COALESCE(provenance,'{{}}'::jsonb) || %s::jsonb
                    WHERE document_id=%s
                    """,
                    (
                        json.dumps(
                            {
                                "invalidated_identity_misbinding": True,
                                "actor": ACTOR,
                            }
                        ),
                        NOOR_DOC,
                    ),
                )

            # Restore July as Esraa current.
            cur.execute(
                """
                UPDATE candidate_documents
                SET metadata = (COALESCE(metadata,'{}'::jsonb)
                      - 'superseded_at' - 'superseded_by_document_id') || %s::jsonb,
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
            cur.execute(
                """
                UPDATE candidate_documents
                SET metadata = COALESCE(metadata,'{}'::jsonb) || '{"latest": false}'::jsonb
                WHERE app_key=%s AND document_id <> %s
                  AND COALESCE(metadata->>'latest','') = 'true'
                """,
                (ESRAA_APP, JULY_DOC),
            )

            cur.execute(
                "SELECT raw_json FROM candidate_documents WHERE document_id=%s",
                (JULY_DOC,),
            )
            july_raw = cur.fetchone()["raw_json"] or {}
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
                            "correction": {
                                "actor": ACTOR,
                                "reason": "identity_misbinding",
                                "restored_document_id": JULY_DOC,
                                "detached_document_id": NOOR_DOC,
                                "at": utc(),
                            },
                        }
                    ),
                    ESRAA_APP,
                ),
            )

            # Restore July text/evidence/facts current markers.
            for table, id_col, id_val in [
                ("candidate_cv_text_versions", "version_id", JULY_TEXT),
                ("application_cv_evidence_materializations", "evidence_id", JULY_EVIDENCE),
                ("application_cv_fact_snapshots", "facts_id", JULY_FACTS),
            ]:
                cur.execute(
                    f"""
                    UPDATE {table} SET is_current=false
                    WHERE app_key=%s AND document_id=%s
                    """,
                    (ESRAA_APP, JULY_DOC),
                )
                cur.execute(
                    f"""
                    UPDATE {table}
                    SET is_current=true,
                        provenance = COALESCE(provenance,'{{}}'::jsonb) || %s::jsonb
                    WHERE {id_col}=%s
                    """,
                    (
                        json.dumps({"restored_by_correction": True, "actor": ACTOR}),
                        id_val,
                    ),
                )

            cur.execute(
                """
                INSERT INTO candidate_classification_run_invalidations(
                  company_code, run_id, reason_code, source_document_id,
                  invalidated_by, evidence)
                VALUES ('WATHEFNI', %s::uuid, 'identity_misbinding', %s, %s, %s)
                ON CONFLICT (company_code, run_id, reason_code) DO NOTHING
                """,
                (
                    RUN_ID,
                    NOOR_DOC,
                    ACTOR,
                    Json(
                        {
                            "incorrect_app_key": ESRAA_APP,
                            "restored_document_id": JULY_DOC,
                            "intake_document_id": intake_document_id,
                            "scan_decision_id": scan_decision.get("decision_id"),
                            "scan_state": scan_decision.get("state"),
                            "identity_outcome": resolution.get("outcome"),
                            "note": "original run preserved immutable",
                        }
                    ),
                ),
            )

            after = snap()
            after.update(
                {
                    "intake_document_id": intake_document_id,
                    "submission_id": submission_id,
                    "scan_decision": {
                        "decision_id": scan_decision.get("decision_id"),
                        "state": scan_decision.get("state"),
                        "failure_reason": scan_decision.get("failure_reason"),
                    },
                    "identity_outcome": resolution.get("outcome"),
                    "quarantine_key": qkey,
                }
            )
            write("noor-esraa-after.json", after)

            july = next(d for d in after["docs"] if d["document_id"] == JULY_DOC)
            noor = next(d for d in after["docs"] if d["document_id"] == NOOR_DOC)
            assert str(july.get("latest")).lower() == "true", "July must be current"
            assert str(noor.get("latest")).lower() != "true", "Noor must not be current"
            assert after["invalidations"] >= 1, "invalidation missing"
            assert after["scan_decision"]["state"] == "scan_failed"
            assert after["lifecycle"] == before["lifecycle"]
            assert after["ranking"] == before["ranking"]
            assert after["outbound"] == before["outbound"]
            assert after["candidate"]["name"] == "Esraa Aziz"
            # No Noor candidate created from unproven historical scan
            cur.execute(
                "SELECT count(*) AS c FROM candidates WHERE email='noortahat3@gmail.com'"
            )
            assert int(cur.fetchone()["c"]) == 0, "must not mint Noor candidate without clean scan"

        conn.commit()

    print(json.dumps({"ok": True, "after": after}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
