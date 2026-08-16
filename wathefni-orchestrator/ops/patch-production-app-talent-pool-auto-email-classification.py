#!/usr/bin/env python3
"""Idempotently attach automatic classification to canonical CV finalization."""
from __future__ import annotations

import argparse
from pathlib import Path


IMPORT_ANCHOR = "import candidate_cv_facts as _candidate_cv_facts  # noqa: E402\n"
IMPORT_LINE = "import talent_pool_auto_email_classification as _talent_pool_auto_email  # noqa: E402\n"
CALL_MARKER = "TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_CANARY"


def patch(source: str) -> str:
    if IMPORT_LINE not in source:
        if IMPORT_ANCHOR not in source:
            raise RuntimeError("candidate_cv_facts import anchor missing")
        source = source.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + IMPORT_LINE, 1)

    if CALL_MARKER in source and "SAVEPOINT talent_pool_auto_email_enqueue" not in source:
        direct = """                    # TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_CANARY
                    auto_classification = _talent_pool_auto_email.record_extraction_and_enqueue(
                        cur,
                        company_code=company_code,
                        app_key=str(app.get("app_key") or ""),
                        document_id=str(document_id),
                        extracted_text=text,
                        extraction_method=method,
                        evidence=dict(evidence_materialization["evidence"]),
                        facts_snapshot=dict(facts_snapshot),
                        provenance={
                            "source": "canonical_cv_extraction_completion",
                            "held_import": bool(held_import),
                            "import_batch_id": item.get("batch_id"),
                        },
                    )
"""
        guarded = """                    # TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_CANARY
                    cur.execute("SAVEPOINT talent_pool_auto_email_enqueue")
                    try:
                        auto_classification = _talent_pool_auto_email.record_extraction_and_enqueue(
                            cur,
                            company_code=company_code,
                            app_key=str(app.get("app_key") or ""),
                            document_id=str(document_id),
                            extracted_text=text,
                            extraction_method=method,
                            evidence=dict(evidence_materialization["evidence"]),
                            facts_snapshot=dict(facts_snapshot),
                            provenance={
                                "source": "canonical_cv_extraction_completion",
                                "held_import": bool(held_import),
                                "import_batch_id": item.get("batch_id"),
                            },
                        )
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT talent_pool_auto_email_enqueue")
                        logger.exception("talent_pool_auto_email_enqueue_failed")
                        auto_classification = {"eligible": False, "reason": "enqueue_failed"}
                    finally:
                        cur.execute("RELEASE SAVEPOINT talent_pool_auto_email_enqueue")
"""
        if direct not in source:
            raise RuntimeError("unguarded automatic classification block missing")
        source = source.replace(direct, guarded, 1)

    if CALL_MARKER not in source:
        anchor = """                            document_id,
                        ),
                    )
                    conn.commit()
                    ranking_stale = None
"""
        replacement = """                            document_id,
                        ),
                    )
                    # TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_CANARY
                    cur.execute("SAVEPOINT talent_pool_auto_email_enqueue")
                    try:
                        auto_classification = _talent_pool_auto_email.record_extraction_and_enqueue(
                            cur,
                            company_code=company_code,
                            app_key=str(app.get("app_key") or ""),
                            document_id=str(document_id),
                            extracted_text=text,
                            extraction_method=method,
                            evidence=dict(evidence_materialization["evidence"]),
                            facts_snapshot=dict(facts_snapshot),
                            provenance={
                                "source": "canonical_cv_extraction_completion",
                                "held_import": bool(held_import),
                                "import_batch_id": item.get("batch_id"),
                            },
                        )
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT talent_pool_auto_email_enqueue")
                        logger.exception("talent_pool_auto_email_enqueue_failed")
                        auto_classification = {"eligible": False, "reason": "enqueue_failed"}
                    finally:
                        cur.execute("RELEASE SAVEPOINT talent_pool_auto_email_enqueue")
                    conn.commit()
                    ranking_stale = None
"""
        if anchor not in source:
            raise RuntimeError("canonical extraction commit anchor missing")
        source = source.replace(anchor, replacement, 1)

    return source


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.write_text(patch(input_path.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
