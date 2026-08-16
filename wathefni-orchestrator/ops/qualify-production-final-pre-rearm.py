#!/usr/bin/env python3
"""Production-dark final pre-rearm qualification.

No email is sent, no worker/timer is started, and retention cleanup is dry-run
only. Synthetic database rows are removed in ``finally``.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


ORCH = Path("/opt/wathefni/orchestrator")
sys.path = [p for p in sys.path if Path(p).resolve() != Path(__file__).resolve().parent]
sys.path.insert(0, str(ORCH))

from psycopg2.extras import Json  # noqa: E402

import app  # noqa: E402
import inbound_retention_policy as retention  # noqa: E402
import talent_pool_classification as classification  # noqa: E402


UTC = timezone.utc
COMPANY = "WATHEFNI"
MARKER = f"final-pre-rearm-{uuid.uuid4()}"
ACTOR = "wathefni-final-pre-rearm-qualification"
ESRAA_APP = "imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT"
NOOR_DOC = "5608a4ef-87d2-49d8-9c7a-9ec5666a92ef"
JULY_DOC = "71a889fd-7e45-4825-bd2e-da15d00888ba"
INVALID_RUN = "a48f3779-3abc-41fb-bec1-92c36ff24587"
EVIDENCE_ROOT = Path(os.environ["EVIDENCE_ROOT"])
OUT = EVIDENCE_ROOT / "final-pre-rearm-qualification.json"


def _insert_synthetic(cur: object) -> dict[str, object]:
    now = datetime.now(UTC)
    inbound_id = str(uuid.uuid4())
    submission_id = str(uuid.uuid4())
    message_id = f"{MARKER}-message"
    cur.execute(
        """
        SELECT intake_id::text FROM intake_addresses
        WHERE company_code='WATHEFNI'
        ORDER BY created_at LIMIT 1
        """
    )
    intake = cur.fetchone()
    if not intake:
        raise RuntimeError("wathefni_intake_address_missing")
    intake_id = intake["intake_id"]
    cur.execute(
        """
        INSERT INTO inbound_messages(
          inbound_id, provider, provider_message_id, company_code, intake_id,
          from_address, envelope_recipient, subject, received_at,
          attachment_count, status, durable_at, total_attachment_bytes)
        VALUES (%s,'qualification',%s,'WATHEFNI',%s,
                'qualification@example.invalid','qualification@inbound.wathefni.ai',
                %s,now(),6,'durable',now(),6)
        """,
        (inbound_id, message_id, intake_id, MARKER),
    )
    cur.execute(
        """
        INSERT INTO intake_submissions(
          submission_id, inbound_id, company_code, intake_id, provider,
          provider_message_id, envelope_recipient, sender_address, subject,
          received_at, attachment_count, accepted_attachment_count,
          total_attachment_bytes, status)
        VALUES (%s,%s,'WATHEFNI',%s,'qualification',%s,
                'qualification@inbound.wathefni.ai',
                'qualification@example.invalid',%s,now(),6,6,6,'durable')
        """,
        (submission_id, inbound_id, intake_id, message_id, MARKER),
    )

    cases = [
        ("eligible_clean", "clean", 31, None),
        ("young_clean", "clean", 29, None),
        ("legal_hold", "infected", 100, "hold"),
        ("open_review", "scan_failed", 100, "open"),
        ("eligible_failed", "scan_failed", 91, None),
        ("resolved_review", "scan_failed", 120, "resolved"),
    ]
    docs: dict[str, str] = {}
    resolution_ids: list[str] = []
    for ordinal, (label, state, age_days, special) in enumerate(cases, start=1):
        document_id = str(uuid.uuid4())
        docs[label] = document_id
        digest = f"{ordinal:064x}"
        key = f"WATHEFNI/{inbound_id}/{ordinal:04d}/{digest}.bin"
        cur.execute(
            """
            INSERT INTO intake_documents(
              document_id, submission_id, inbound_id, company_code,
              attachment_ordinal, original_filename, claimed_mime, detected_mime,
              size_bytes, content_sha256, quarantine_key, storage_status,
              safety_state, metadata, created_at, updated_at)
            VALUES (%s,%s,%s,'WATHEFNI',%s,%s,'application/pdf',
                    'application/pdf',1,%s,%s,'stored',%s,%s,now(),now())
            """,
            (
                document_id,
                submission_id,
                inbound_id,
                ordinal,
                f"{label}.pdf",
                digest,
                key,
                "clean" if state == "clean" else "quarantined",
                Json({"qualification_marker": MARKER}),
            ),
        )
        completed = now - timedelta(days=age_days)
        cur.execute(
            """
            INSERT INTO inbound_attachment_scan_decisions(
              company_code, inbound_id, intake_document_id, attachment_ordinal,
              content_sha256, scanner_policy_version, attempt_no, state,
              scanner_engine, scanner_version, signature_database_version,
              scan_started_at, scan_completed_at, result, failure_reason,
              quarantine_object_ref, actor_service_identity, evidence)
            VALUES ('WATHEFNI',%s,%s,%s,%s,'inbound-cv-scan-v1',1,%s,
                    'qualification','test','test',%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                inbound_id,
                document_id,
                ordinal,
                digest,
                state,
                completed,
                completed,
                state,
                None if state == "clean" else "qualification_nonclean",
                key,
                ACTOR,
                Json({"qualification_marker": MARKER}),
            ),
        )
        if special in {"open", "resolved"}:
            resolution_id = str(uuid.uuid4())
            resolution_ids.append(resolution_id)
            cur.execute(
                """
                INSERT INTO inbound_cv_identity_resolutions(
                  resolution_id, company_code, inbound_id, intake_document_id,
                  content_sha256, identity_policy_version,
                  sender_email_provenance, normalized_full_name, outcome,
                  confidence, candidate_matches, strong_keys, weak_keys,
                  reason_codes, ownership_confirmed, actor_service_identity,
                  created_at)
                VALUES (%s,'WATHEFNI',%s,%s,%s,'inbound-cv-identity-v1',
                        'qualification@example.invalid','qualification person',
                        'possible_match',0,'[]','[]','[]',%s,false,%s,%s)
                """,
                (
                    resolution_id,
                    inbound_id,
                    document_id,
                    digest,
                    Json(["qualification_review"]),
                    ACTOR,
                    completed,
                ),
            )
            review_id = str(uuid.uuid4())
            resolved_at = (
                now - timedelta(days=91) if special == "resolved" else None
            )
            cur.execute(
                """
                INSERT INTO inbound_cv_identity_reviews(
                  review_id, company_code, resolution_id, intake_document_id,
                  status, review_type, possible_candidate_phones,
                  possible_app_keys, reason_codes, created_at, resolved_at,
                  resolved_by, resolution_note)
                VALUES (%s,'WATHEFNI',%s,%s,%s,'qualification',
                        '[]','[]',%s,%s,%s,%s,%s)
                """,
                (
                    review_id,
                    resolution_id,
                    document_id,
                    "resolved" if special == "resolved" else "open",
                    Json(["qualification_review"]),
                    completed,
                    resolved_at,
                    ACTOR if resolved_at else None,
                    "qualification" if resolved_at else None,
                ),
            )
        if special == "hold":
            cur.execute(
                """
                INSERT INTO inbound_retention_legal_holds(
                  company_code, intake_document_id, content_sha256,
                  reason, placed_by)
                VALUES ('WATHEFNI',%s,%s,'qualification legal hold',%s)
                """,
                (document_id, digest, ACTOR),
            )
    synthetic_run_id = str(uuid.uuid4())
    synthetic_suggestion_id = str(uuid.uuid4())
    synthetic_app_key = f"{MARKER}-APP"
    cur.execute(
        """
        INSERT INTO candidate_classification_runs(
          run_id, company_code, app_key, document_version_id,
          extraction_version_id, taxonomy_version, classifier_version,
          idempotency_key, status, input_bundle_hash)
        VALUES (%s,'WATHEFNI',%s,'synthetic-document','synthetic-extraction',
                'talent-taxonomy-v1','talent-pool-classifier-v1',%s,
                'classified','synthetic-hash')
        """,
        (synthetic_run_id, synthetic_app_key, f"{MARKER}-idempotency"),
    )
    cur.execute(
        """
        INSERT INTO candidate_classification_suggestions(
          suggestion_id, run_id, company_code, app_key, node_id, node_type,
          confidence_score, confidence_band, evidence, state)
        VALUES (%s,%s,'WATHEFNI',%s,'fn.technology','career_function',
                0.99,'High',%s,'active')
        """,
        (
            synthetic_suggestion_id,
            synthetic_run_id,
            synthetic_app_key,
            Json([{"quote": MARKER}]),
        ),
    )
    cur.execute(
        """
        INSERT INTO candidate_classification_run_invalidations(
          company_code, run_id, reason_code, invalidated_by, evidence)
        VALUES ('WATHEFNI',%s,'qualification_identity_misbinding',%s,%s)
        """,
        (synthetic_run_id, ACTOR, Json({"qualification_marker": MARKER})),
    )
    return {
        "inbound_id": inbound_id,
        "submission_id": submission_id,
        "docs": docs,
        "resolution_ids": resolution_ids,
        "synthetic_run_id": synthetic_run_id,
        "synthetic_app_key": synthetic_app_key,
    }


def _cleanup_synthetic(cur: object, fixture: dict[str, object] | None) -> None:
    if not fixture:
        return
    cur.execute("SELECT set_config('wathefni.authority_cleanup','synthetic',true)")
    docs = list((fixture.get("docs") or {}).values())
    cur.execute(
        "DELETE FROM inbound_retention_legal_holds WHERE intake_document_id = ANY(%s::uuid[])",
        (docs,),
    )
    cur.execute(
        "DELETE FROM candidate_classification_run_invalidations WHERE run_id=%s",
        (fixture["synthetic_run_id"],),
    )
    cur.execute(
        "DELETE FROM candidate_classification_suggestions WHERE run_id=%s",
        (fixture["synthetic_run_id"],),
    )
    cur.execute(
        "DELETE FROM candidate_classification_runs WHERE run_id=%s",
        (fixture["synthetic_run_id"],),
    )
    cur.execute(
        "DELETE FROM inbound_messages WHERE inbound_id=%s",
        (fixture["inbound_id"],),
    )


def main() -> int:
    fixture: dict[str, object] | None = None
    result: dict[str, object] = {"marker": MARKER, "passed": False}
    with app.db_connect() as conn:
        try:
            with conn.cursor() as cur:
                retention.ensure_schema(cur)
                policy = retention.policy_from_env(COMPANY)
                retention.activate_policy(cur, policy, actor=ACTOR)
                conn.commit()

                active = retention.active_policy(cur, COMPANY)
                try:
                    retention.active_policy(cur, "NOT_ENABLED_TENANT")
                except retention.RetentionPolicyError as exc:
                    tenant_fail_closed = exc.code == "retention_policy_not_configured"
                else:
                    tenant_fail_closed = False
                try:
                    retention.policy_from_env(COMPANY, {})
                except retention.RetentionPolicyError as exc:
                    invalid_config_fail_closed = (
                        exc.code == "retention_policy_version_invalid"
                    )
                else:
                    invalid_config_fail_closed = False

                fixture = _insert_synthetic(cur)
                conn.commit()
                plan = retention.execute_cleanup(
                    cur,
                    company_code=COMPANY,
                    storage=None,  # type: ignore[arg-type]
                    actor=ACTOR,
                    dry_run=True,
                    now=datetime.now(UTC),
                )
                eligible_ids = {
                    item["intake_document_id"] for item in plan["eligible"]
                }
                expected_ids = {
                    fixture["docs"]["eligible_clean"],
                    fixture["docs"]["eligible_failed"],
                    fixture["docs"]["resolved_review"],
                }
                cur.execute(
                    """
                    SELECT count(*) AS c FROM inbound_retention_deletions
                    WHERE intake_document_id = ANY(%s::uuid[])
                    """,
                    (list(fixture["docs"].values()),),
                )
                deletion_rows = int(cur.fetchone()["c"])
                cur.execute(
                    """
                    SELECT count(*) AS c FROM intake_documents
                    WHERE document_id = ANY(%s::uuid[]) AND storage_status='stored'
                    """,
                    (list(fixture["docs"].values()),),
                )
                still_stored = int(cur.fetchone()["c"])

                classification.ensure_classification_schema(cur)
                synthetic_pack = classification.bulk_load_classification_rows(
                    cur,
                    company_code=COMPANY,
                    app_keys=[fixture["synthetic_app_key"]],
                )[fixture["synthetic_app_key"]]
                pack = classification.bulk_load_classification_rows(
                    cur, company_code=COMPANY, app_keys=[ESRAA_APP]
                )[ESRAA_APP]
                cur.execute(
                    """
                    SELECT r.*, i.reason_code, i.invalidated_by,
                           i.created_at AS invalidated_at
                    FROM candidate_classification_runs r
                    JOIN candidate_classification_run_invalidations i
                      ON i.company_code=r.company_code AND i.run_id=r.run_id
                    WHERE r.company_code='WATHEFNI' AND r.run_id=%s
                    """,
                    (INVALID_RUN,),
                )
                invalid_audit = dict(cur.fetchone() or {})
                section = classification.profile_classification_section(
                    run=pack.get("run"),
                    suggestions=pack.get("suggestions") or [],
                    review_events=pack.get("review_events") or [],
                    runs=[invalid_audit],
                    invalidations=pack.get("invalidations") or [],
                )
                cur.execute(
                    """
                    SELECT document_id::text, metadata->>'latest' AS latest
                    FROM candidate_documents
                    WHERE document_id = ANY(%s::uuid[])
                    """,
                    ([NOOR_DOC, JULY_DOC],),
                )
                doc_state = {
                    row["document_id"]: row["latest"] for row in cur.fetchall()
                }
                cur.execute(
                    """
                    SELECT status, review_id::text
                    FROM inbound_cv_identity_reviews
                    WHERE intake_document_id=(
                      SELECT document_id FROM intake_documents
                      WHERE content_sha256=%s AND company_code='WATHEFNI'
                      ORDER BY created_at LIMIT 1
                    )
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (
                        "d951c3e27796318075c7c532be45d641e04170e3cd738081efd8ab4d5e2b2934",
                    ),
                )
                noor_review = dict(cur.fetchone() or {})

                timer_probe = app.process_candidate_cv_document(
                    NOOR_DOC, dry_run=True, send_screening=False
                )
                result = {
                    "passed": all(
                        [
                            active.public_dict() == policy.public_dict(),
                            tenant_fail_closed,
                            invalid_config_fail_closed,
                            eligible_ids == expected_ids,
                            plan["blocked_counts"].get("legal_hold") == 1,
                            int(
                                plan["blocked_counts"].get(
                                    "identity_review_open", 0
                                )
                            )
                            >= 1,
                            deletion_rows == 0,
                            still_stored == 6,
                            not (pack["effective"].get("ai_suggested") or []),
                            not pack["projection"].get("classification_chip"),
                            section.get("current_run") is None,
                            invalid_audit.get("run_id") is not None,
                            doc_state.get(JULY_DOC) == "true",
                            doc_state.get(NOOR_DOC) != "true",
                            noor_review.get("status") == "open",
                            synthetic_pack.get("run") is None,
                            not (
                                synthetic_pack["effective"].get("ai_suggested")
                                or []
                            ),
                            not synthetic_pack["projection"].get(
                                "classification_chip"
                            ),
                            bool(synthetic_pack.get("invalidations")),
                            timer_probe.get("error")
                            in {
                                "document_current_authority_not_proven",
                                "inbound_email_authority_provenance_missing",
                            },
                        ]
                    ),
                    "policy": active.public_dict(),
                    "policy_readable": True,
                    "tenant_fail_closed": tenant_fail_closed,
                    "invalid_config_fail_closed": invalid_config_fail_closed,
                    "retention_dry_run": plan,
                    "retention_dry_run_exact_selection": sorted(eligible_ids)
                    == sorted(expected_ids),
                    "no_destructive_cleanup": {
                        "deletion_rows": deletion_rows,
                        "synthetic_objects_still_stored": still_stored,
                    },
                    "timer_probe": timer_probe,
                    "classification": {
                        "synthetic_active_invalidated_run": {
                            "current_run": synthetic_pack.get("run"),
                            "effective_ai_suggestions": len(
                                synthetic_pack["effective"].get("ai_suggested")
                                or []
                            ),
                            "chip": synthetic_pack["projection"].get(
                                "classification_chip"
                            ),
                            "invalidation_count": len(
                                synthetic_pack.get("invalidations") or []
                            ),
                            "all_suggestions_retained_for_audit": len(
                                synthetic_pack.get("all_suggestions") or []
                            ),
                        },
                        "effective_ai_suggestions": len(
                            pack["effective"].get("ai_suggested") or []
                        ),
                        "chip": pack["projection"].get("classification_chip"),
                        "current_run": section.get("current_run"),
                        "invalid_run_audit": invalid_audit,
                    },
                    "noor_esraa": {
                        "noor_latest": doc_state.get(NOOR_DOC),
                        "july_latest": doc_state.get(JULY_DOC),
                        "noor_review": noor_review,
                    },
                }
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                _cleanup_synthetic(cur, fixture)
            conn.commit()

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM inbound_messages WHERE subject=%s",
                (MARKER,),
            )
            residue = int(cur.fetchone()["c"])
    result["synthetic_residue"] = residue
    result["passed"] = bool(result.get("passed")) and residue == 0
    OUT.write_text(json.dumps(result, indent=2, default=str) + "\n")
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
