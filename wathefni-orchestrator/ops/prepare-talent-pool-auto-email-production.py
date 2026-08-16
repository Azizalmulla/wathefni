#!/usr/bin/env python3
"""Prepare immutable Esraa version evidence without enqueueing historical work."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, os.environ.get("WATHEFNI_ORCHESTRATOR_DIR", "/opt/wathefni/orchestrator"))

import app
import talent_pool_auto_email_classification as auto


def _source_sha(row: dict[str, Any]) -> str:
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    storage = raw.get("storage") if isinstance(raw.get("storage"), dict) else {}
    return str(storage.get("sha256") or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-key", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result: dict[str, Any] = {"app_key": args.app_key, "versions": []}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            auto.ensure_schema(cur)
            cur.execute(
                """
                SELECT * FROM candidate_documents
                WHERE app_key=%s AND document_type='cv'
                ORDER BY created_at
                """,
                (args.app_key,),
            )
            documents = [dict(row) for row in cur.fetchall()]
            if len(documents) < 2:
                raise RuntimeError("expected_multiple_esraa_cv_versions")
            current = [
                row
                for row in documents
                if isinstance(row.get("metadata"), dict) and row["metadata"].get("latest") is True
            ]
            if len(current) != 1:
                raise RuntimeError("exactly_one_current_document_required")

            for row in documents:
                metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                is_current = str(row["document_id"]) == str(current[0]["document_id"])
                source_sha = _source_sha(row)
                if not source_sha:
                    raise RuntimeError(f"source_sha_missing:{row['document_id']}")
                finalization_id = evidence_id = facts_id = None
                text_hash = None
                text_content = None
                status = "legacy_source_preserved_text_unavailable"
                if is_current:
                    cur.execute(
                        """
                        SELECT evidence_id, extraction_finalization_id, facts_id, extracted_text_hash
                        FROM application_cv_evidence_materializations
                        WHERE company_code='WATHEFNI' AND app_key=%s
                          AND document_id=%s AND is_current=true AND status='ready'
                        LIMIT 1
                        """,
                        (args.app_key, row["document_id"]),
                    )
                    evidence = dict(cur.fetchone() or {})
                    if not evidence:
                        raise RuntimeError("current_evidence_missing")
                    text_content = Path(str(row.get("text_path") or "")).read_text(encoding="utf-8")
                    text_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
                    if text_hash != str(evidence.get("extracted_text_hash") or ""):
                        raise RuntimeError("current_text_evidence_hash_mismatch")
                    finalization_id = str(evidence["extraction_finalization_id"])
                    evidence_id = str(evidence["evidence_id"])
                    facts_id = str(evidence["facts_id"])
                    status = "ready"
                else:
                    semantic = metadata.get("semantic") if isinstance(metadata.get("semantic"), dict) else {}
                    text_hash = str(semantic.get("content_hash") or "") or None

                preserved = auto.preserve_existing_version_without_enqueue(
                    cur,
                    company_code="WATHEFNI",
                    app_key=args.app_key,
                    document_id=str(row["document_id"]),
                    source_content_sha256=source_sha,
                    extracted_text_hash=text_hash,
                    extraction_finalization_id=finalization_id,
                    evidence_id=evidence_id,
                    facts_id=facts_id,
                    extraction_method=row.get("extraction_method"),
                    text_content=text_content,
                    status=status,
                    is_current=is_current,
                    provenance={
                        "source": "production_canary_version_authority_remediation",
                        "source_file_preserved": Path(str(row.get("local_path") or "")).exists(),
                        "legacy_profile_snapshot_present": isinstance(metadata.get("profile"), dict),
                        "legacy_semantic_hash_present": bool(text_hash),
                        "historical_ocr_rerun": False,
                        "historical_classification_enqueued": False,
                    },
                )
                result["versions"].append(
                    {
                        **preserved,
                        "source_content_sha256": source_sha,
                        "extracted_text_hash": text_hash,
                        "filename": row.get("filename"),
                        "created_at": row.get("created_at"),
                    }
                )

            protected: dict[str, int] = {}
            for table in (
                "application_lifecycle_events",
                "candidate_rank_evaluations",
                "outbound_delivery_events",
                "intake_admission_events",
            ):
                cur.execute("SELECT to_regclass(%s) AS table_name", (f"public.{table}",))
                if (cur.fetchone() or {}).get("table_name"):
                    cur.execute(f"SELECT count(*) AS count FROM {table}")
                    protected[table] = int((cur.fetchone() or {}).get("count") or 0)
                else:
                    protected[table] = -1
            result["protected_mutation_baseline"] = protected
        conn.commit()
    Path(args.output).write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
