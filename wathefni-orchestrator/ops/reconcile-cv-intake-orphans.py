#!/usr/bin/env python3
"""One-shot production reconcile for known CV intake orphans.

Safe, idempotent, tenant-scoped. Does not raise concurrency.
Does not restore the legacy prehire CV timer.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow importing orchestrator modules when run from /opt/wathefni/orchestrator.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVIDENCE = Path(
    os.environ.get("WATHEFNI_RECONCILE_EVIDENCE_DIR")
    or f"/opt/wathefni/var/evidence/cv-intake-canonical-harden-{STAMP}"
)


def main() -> int:
    import app as app_mod
    import durable_email_ingress as dei
    import unified_candidates as uc
    from psycopg2.extras import Json

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report: dict = {"stamp": STAMP, "actions": [], "attention_before": None, "attention_after": None}

    app_mod.ensure_schema()
    company = "WATHEFNI"
    app_processed = "imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT"
    app_stuck = "imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT"
    submission_orphan = "f01ed86e-eca3-48ec-aee8-5c2cbc925fbe"

    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            report["attention_before"] = uc.intake_operations_summary(cur, company_code=company)

            # 1) 837eb9b1 — already processed; no mutation beyond verification.
            cur.execute(
                """
                SELECT app_key, status,
                       raw_json->'cv'->'processing'->>'status' AS proc_status,
                       raw_json->'cv'->'processing'->>'text_extracted' AS text_extracted
                FROM applications
                WHERE company_code=%s AND app_key=%s
                """,
                (company, app_processed),
            )
            row_a = dict(cur.fetchone() or {})
            report["actions"].append(
                {
                    "target": app_processed,
                    "action": "verify_processed_held",
                    "row": row_a,
                    "mutated": False,
                    "note": "General candidate with no job; must not count as HR attention",
                }
            )

            # 2) 06ffffc3 — documents already extraction_status=ok; sync application flags.
            cur.execute(
                """
                SELECT document_id::text AS document_id, extraction_status, extraction_method,
                       extraction_chars, filename, updated_at
                FROM candidate_documents
                WHERE app_key=%s
                ORDER BY updated_at DESC NULLS LAST, created_at DESC
                """,
                (app_stuck,),
            )
            docs = [dict(r) for r in cur.fetchall()]
            ok_docs = [d for d in docs if str(d.get("extraction_status") or "") == "ok"]
            if ok_docs:
                best = ok_docs[0]
                cur.execute(
                    "SELECT raw_json FROM applications WHERE company_code=%s AND app_key=%s FOR UPDATE",
                    (company, app_stuck),
                )
                app_row = cur.fetchone()
                raw = dict((app_row or {}).get("raw_json") or {})
                cv = dict(raw.get("cv") or {})
                processing = dict(cv.get("processing") or {})
                before_status = processing.get("status")
                processing.update(
                    {
                        "file_received": True,
                        "file_stored": True,
                        "text_extracted": True,
                        "profile_parsed": bool(raw.get("candidate_profile") or processing.get("profile_parsed")),
                        "status": "processed",
                        "reconciled_from_document_id": best["document_id"],
                        "reconciled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "extraction_method": best.get("extraction_method"),
                        "extraction_chars": best.get("extraction_chars"),
                    }
                )
                cv["processing"] = processing
                raw["cv"] = cv
                cur.execute(
                    """
                    UPDATE applications
                    SET raw_json=%s, updated_at=now()
                    WHERE company_code=%s AND app_key=%s
                    """,
                    (Json(raw), company, app_stuck),
                )
                report["actions"].append(
                    {
                        "target": app_stuck,
                        "action": "sync_processed_from_ok_documents",
                        "before_status": before_status,
                        "after_status": "processed",
                        "document_id": best["document_id"],
                        "ok_document_count": len(ok_docs),
                        "mutated": True,
                        "note": "Avoided duplicate extraction; trustworthy candidate_documents already ok",
                    }
                )
            else:
                # Fallback: enqueue missing canonical extraction for latest pending doc.
                pending = docs[0] if docs else None
                job_id = None
                if pending:
                    job_id = app_mod.ensure_application_cv_extraction_job(
                        cur,
                        company_code=company,
                        document_id=str(pending["document_id"]),
                        app_key=app_stuck,
                        source_channel="reconcile",
                        priority=50,
                    )
                report["actions"].append(
                    {
                        "target": app_stuck,
                        "action": "enqueue_missing_extraction",
                        "document_id": (pending or {}).get("document_id"),
                        "job_id": job_id,
                        "mutated": bool(job_id),
                    }
                )

            # 3) f01ed86e — durable submission with zero jobs → enqueue validation.
            cur.execute(
                """
                SELECT submission_id::text AS submission_id, status, company_code,
                       (SELECT count(*) FROM intake_processing_jobs j
                          WHERE j.company_code=s.company_code
                            AND (
                              j.subject_id=s.submission_id::text
                              OR j.payload->>'submission_id'=s.submission_id::text
                              OR j.idempotency_key=concat('submission:', s.submission_id::text, ':validate')
                            )
                       ) AS job_count
                FROM intake_submissions s
                WHERE submission_id=%s::uuid
                """,
                (submission_orphan,),
            )
            sub = dict(cur.fetchone() or {})
            job_id = None
            if sub and int(sub.get("job_count") or 0) == 0:
                config = app_mod.durable_email_ingress_config()
                job_id = dei.enqueue_job(
                    cur,
                    company_code=str(sub.get("company_code") or company),
                    job_type="intake_validation",
                    subject_type="intake_submission",
                    subject_id=str(sub["submission_id"]),
                    idempotency_key=f"submission:{sub['submission_id']}:validate",
                    payload={"submission_id": str(sub["submission_id"]), "reconcile": True},
                    priority=50,
                    max_attempts=config.max_attempts,
                )
                cur.execute(
                    """
                    UPDATE intake_submissions
                    SET status='durable', updated_at=now()
                    WHERE submission_id=%s::uuid
                    """,
                    (sub["submission_id"],),
                )
            report["actions"].append(
                {
                    "target": submission_orphan,
                    "action": "enqueue_intake_validation",
                    "before": sub,
                    "job_id": job_id,
                    "mutated": bool(job_id),
                }
            )

            # Replay safety: second ensure/enqueue must be idempotent.
            cur.execute(
                """
                SELECT document_id::text AS document_id
                FROM candidate_documents
                WHERE app_key=%s
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """,
                (app_processed,),
            )
            replay_doc = cur.fetchone()
            replay_ids = []
            if replay_doc:
                for _ in range(2):
                    replay_ids.append(
                        app_mod.ensure_application_cv_extraction_job(
                            cur,
                            company_code=company,
                            document_id=str(replay_doc["document_id"]),
                            app_key=app_processed,
                            source_channel="idempotency_proof",
                            priority=100,
                        )
                    )
            report["actions"].append(
                {
                    "target": "idempotency_proof",
                    "document_id": (replay_doc or {}).get("document_id"),
                    "job_ids": replay_ids,
                    "idempotent": len(set(replay_ids)) == 1 if replay_ids else None,
                }
            )

            report["attention_after"] = uc.intake_operations_summary(cur, company_code=company)
        conn.commit()

    out = EVIDENCE / "reconcile-report.json"
    out.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"ok": True, "evidence": str(out), "attention_after": report["attention_after"]}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
