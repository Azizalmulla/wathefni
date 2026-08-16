#!/usr/bin/env python3
"""Surgical production patch: WATHEFNI inbound-email authority cutover.

Keeps Postmark webhook, routing, ACK boundary, ClamAV, retries/DLs.
Does not enable ENFORCE. Does not change Job Stage B.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKERS = {
    "observe": "UNIFIED_INTAKE_AUTHORITY_EMAIL_OBSERVE",
    "extraction": "UNIFIED_INTAKE_AUTHORITY_EMAIL_EXTRACTION",
    "ingress_mark": "UNIFIED_INTAKE_AUTHORITY_EMAIL_RECEIPT",
}


PROCESS_OLD = '''def process_durable_email_ingress_job(job: dict[str, Any]) -> dict[str, Any]:
    job_type = str(job.get("job_type") or "")
    company = str(job.get("company_code") or "").strip().upper()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    config = durable_email_ingress_config()
    if job_type == "intake_validation":
        return _durable_email_ingress.validate_submission(
            db_connect=db_connect,
            submission_id=str(payload.get("submission_id") or job.get("subject_id") or ""),
            company_code=company,
            config=config,
        )
    if job_type == "file_safety_scan":
        return _durable_email_ingress.scan_document(
            db_connect=db_connect,
            document_id=str(payload.get("document_id") or job.get("subject_id") or ""),
            company_code=company,
            config=config,
        )
    if job_type == "cv_identity_resolution":
        return _resolve_clean_intake_document_identity(job)
    if job_type == "accepted_intake_preparation":
        return _prepare_accepted_intake_document(job)
    if job_type == "cv_extraction":
'''

PROCESS_NEW = '''def process_durable_email_ingress_job(job: dict[str, Any]) -> dict[str, Any]:
    job_type = str(job.get("job_type") or "")
    company = str(job.get("company_code") or "").strip().upper()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    config = durable_email_ingress_config()

    def _observe(status: str, result: dict[str, Any] | None = None, *, error_code: str | None = None, error_detail: str | None = None) -> None:
        # UNIFIED_INTAKE_AUTHORITY_EMAIL_OBSERVE
        try:
            import inbound_cv_processing as _inbound_cv_processing

            if not _inbound_cv_processing.stage_ledger_enabled():
                return
            with db_connect() as obs_conn:
                with obs_conn.cursor() as obs_cur:
                    _inbound_cv_processing.ensure_schema(obs_cur)
                    _inbound_cv_processing.observe_email_job_stage(
                        obs_cur,
                        job=job,
                        status=status,
                        result=result,
                        error_code=error_code,
                        error_detail=error_detail,
                    )
                obs_conn.commit()
        except Exception:
            logger.exception("unified_cv_processing_stage_observe_failed")

    def _email_authority_after_scan(result: dict[str, Any] | None) -> None:
        try:
            import inbound_cv_channel_cutover as _cutover
            if not _cutover.email_authority_enabled(company):
                return
            if not isinstance(result, dict) or str(result.get("safety_state") or "") != "clean":
                return
            document_id = str(result.get("document_id") or payload.get("document_id") or "")
            if not document_id:
                return
            with db_connect() as c_conn:
                with c_conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT d.document_id::text, d.content_sha256, d.original_filename,
                               d.detected_mime, d.claimed_mime, d.inbound_id::text,
                               d.submission_id::text,
                               s.provider_message_id, s.sender_address,
                               s.route_snapshot, s.source_provenance
                        FROM intake_documents d
                        JOIN intake_submissions s
                          ON s.submission_id=d.submission_id AND s.company_code=d.company_code
                        WHERE d.company_code=%s AND d.document_id=%s
                        """,
                        (company, document_id),
                    )
                    row = cur.fetchone()
                    if not row:
                        return
                    doc = dict(row)
                    route = doc.get("route_snapshot") if isinstance(doc.get("route_snapshot"), dict) else {}
                    prov = doc.get("source_provenance") if isinstance(doc.get("source_provenance"), dict) else {}
                    _cutover.accept_email_inbound(
                        cur,
                        company_code=company,
                        inbound_id=str(doc.get("inbound_id") or ""),
                        submission_id=str(doc.get("submission_id") or ""),
                        provider_message_id=str(doc.get("provider_message_id") or document_id),
                        documents=[
                            {
                                "document_id": document_id,
                                "content_sha256": doc.get("content_sha256"),
                                "filename": doc.get("original_filename"),
                                "detected_mime": doc.get("detected_mime"),
                                "claimed_mime": doc.get("claimed_mime"),
                                "safety_state": "clean",
                            }
                        ],
                        route_snapshot=route,
                        source_provenance=prov,
                        sender_email=str(doc.get("sender_address") or "") or None,
                        position_code=str(route.get("position_code") or "") or None,
                    )
                c_conn.commit()
        except Exception:
            logger.exception("unified_email_authority_after_scan_failed")

    if job_type == "intake_validation":
        result = _durable_email_ingress.validate_submission(
            db_connect=db_connect,
            submission_id=str(payload.get("submission_id") or job.get("subject_id") or ""),
            company_code=company,
            config=config,
        )
        _observe("completed", result if isinstance(result, dict) else None)
        return result
    if job_type == "file_safety_scan":
        result = _durable_email_ingress.scan_document(
            db_connect=db_connect,
            document_id=str(payload.get("document_id") or job.get("subject_id") or ""),
            company_code=company,
            config=config,
        )
        _observe("completed", result if isinstance(result, dict) else None)
        _email_authority_after_scan(result if isinstance(result, dict) else None)
        return result
    if job_type == "cv_identity_resolution":
        result = _resolve_clean_intake_document_identity(job)
        _observe("completed", result if isinstance(result, dict) else None)
        return result
    if job_type == "accepted_intake_preparation":
        result = _prepare_accepted_intake_document(job)
        _observe("completed", result if isinstance(result, dict) else None)
        return result
    if job_type == "cv_extraction":
'''

EXTRACTION_HOOK = '''
                    # UNIFIED_INTAKE_AUTHORITY_EMAIL_EXTRACTION
                    cur.execute("SAVEPOINT unified_cv_version_dual_write")
                    try:
                        import inbound_cv_processing as _inbound_cv_processing
                        import inbound_cv_channel_cutover as _inbound_cv_cutover

                        evidence_row = dict(evidence_materialization.get("evidence") or {})
                        sha = str(
                            evidence_row.get("source_content_sha256") or source_sha or ""
                        )
                        _inbound_cv_processing.dual_write_cv_version(
                            cur,
                            company_code=company_code,
                            content_sha256=sha,
                            legacy_document_id=str(document_id),
                            legacy_app_key=str(app.get("app_key") or "") or None,
                            legacy_text_version_id=(
                                str(auto_classification.get("version_id") or "")
                                if isinstance(auto_classification, dict)
                                and auto_classification.get("version_id")
                                else None
                            ),
                            extracted_text_hash=str(evidence_row.get("extracted_text_hash") or "")
                            or None,
                            extraction_method=method,
                            evidence_id=str(evidence_row.get("evidence_id") or "") or None,
                            facts_id=str(facts_snapshot.get("facts_id") or "") or None,
                            provenance={
                                "source": "canonical_cv_extraction_completion",
                                "classification_eligible": bool(
                                    isinstance(auto_classification, dict)
                                    and auto_classification.get("eligible")
                                ),
                            },
                        )
                        if _inbound_cv_cutover.email_authority_enabled(str(company_code or "")):
                            _inbound_cv_cutover.after_email_extraction(
                                cur,
                                company_code=str(company_code or ""),
                                content_sha256=sha,
                                legacy_document_id=str(document_id),
                                legacy_app_key=str(app.get("app_key") or "") or None,
                                extracted_text_hash=str(evidence_row.get("extracted_text_hash") or "")
                                or None,
                                extraction_method=method,
                                evidence_id=str(evidence_row.get("evidence_id") or "") or None,
                                facts_id=str(facts_snapshot.get("facts_id") or "") or None,
                                phone=str(app.get("phone") or "") or None,
                            )
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT unified_cv_version_dual_write")
                        logger.exception("unified_email_authority_extraction_failed")
                    finally:
                        cur.execute("RELEASE SAVEPOINT unified_cv_version_dual_write")
'''


def patch_app(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    actions: list[str] = []

    if MARKERS["observe"] not in text:
        if PROCESS_OLD not in text:
            raise SystemExit("process_durable_email_ingress_job anchor missing")
        text = text.replace(PROCESS_OLD, PROCESS_NEW, 1)
        actions.append("observe")

    if MARKERS["extraction"] not in text:
        needle = (
            'cur.execute("RELEASE SAVEPOINT talent_pool_auto_email_enqueue")\n'
            "                    conn.commit()\n"
            "                    ranking_stale = None\n"
        )
        if needle not in text:
            raise SystemExit("talent_pool release/commit anchor missing")
        text = text.replace(
            needle,
            'cur.execute("RELEASE SAVEPOINT talent_pool_auto_email_enqueue")\n'
            + EXTRACTION_HOOK
            + "                    conn.commit()\n"
            "                    ranking_stale = None\n",
            1,
        )
        actions.append("extraction")

    path.write_text(text, encoding="utf-8")
    return actions


def patch_ingress(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    actions: list[str] = []
    if MARKERS["ingress_mark"] in text:
        return ["ingress_already"]
    old = (
        "                # Wave 1: optional production-dark envelope dual-write.\n"
        "                # Live email tables, jobs, scanning, and identity remain authoritative.\n"
        "                _inbound_cv_intake.dual_write_email_receipt(\n"
    )
    new = (
        "                # Wave 1 envelope dual-write. Postmark webhook/routing/ACK/ClamAV/\n"
        "                # retries remain. When EMAIL authority flag is ON for the tenant,\n"
        "                # accepted processing is unified (see inbound_cv_channel_cutover).\n"
        "                # UNIFIED_INTAKE_AUTHORITY_EMAIL_RECEIPT\n"
        "                _inbound_cv_intake.dual_write_email_receipt(\n"
    )
    if old not in text:
        raise SystemExit("durable_email_ingress dual_write comment anchor missing")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")
    actions.append("ingress_mark")
    return actions


def main() -> int:
    app_py = Path(sys.argv[1] if len(sys.argv) > 1 else "app.py")
    ingress = Path(sys.argv[2] if len(sys.argv) > 2 else "durable_email_ingress.py")
    actions = patch_app(app_py) + patch_ingress(ingress)
    print(json.dumps({"ok": True, "app": str(app_py), "ingress": str(ingress), "actions": actions}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
