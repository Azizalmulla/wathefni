#!/usr/bin/env python3
"""Idempotent CV Extraction V2 backfill for existing CVs.

Reuses preserved source files, native text, and OCR evidence.
Reruns OCR+Document AI annotation only when existing evidence is insufficient.
Does not create duplicate CV versions, extraction runs, or fact snapshots.
Preserves prior application-cv-facts-v1 snapshots.

Publishes to candidate-profile-facts-v2 only when WATHEFNI_CV_PROFILE_FACTS_V2=true.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any


def _load_proc_env(pid: str) -> None:
    for item in pathlib.Path(f"/proc/{pid}/environ").read_bytes().split(b"\0"):
        if not item or b"=" not in item:
            continue
        k, v = item.split(b"=", 1)
        os.environ.setdefault(k.decode(), v.decode(errors="replace"))


def _resolve_local_path(cur: Any, *, company: str, app_key: str, document_id: str) -> tuple[str | None, str | None]:
    mime = None
    path = None
    try:
        cur.execute(
            """
            SELECT local_path, storage_url, original_filename, mime_type
            FROM file_registry
            WHERE company_code=%s AND subject_type='application' AND subject_key=%s
              AND (
                lower(coalesce(document_type,'')) LIKE '%%cv%%'
                OR lower(coalesce(file_kind,'')) LIKE '%%cv%%'
              )
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            (company, app_key),
        )
        row = cur.fetchone()
        if row:
            path = row.get("local_path")
            mime = row.get("mime_type") or mime
            if not path and row.get("storage_url"):
                url = str(row["storage_url"])
                if url.startswith("local://"):
                    rel = url[len("local://") :]
                    workspace = os.environ.get("WATHEFNI_WORKSPACE") or ""
                    path = str(pathlib.Path(workspace) / rel) if workspace else rel
                else:
                    path = url
            name = str(row.get("original_filename") or "").lower()
            if not mime:
                if name.endswith(".pdf"):
                    mime = "application/pdf"
                elif name.endswith(".docx"):
                    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                elif name.endswith((".png", ".jpg", ".jpeg", ".webp")):
                    mime = f"image/{name.rsplit('.', 1)[-1].replace('jpg', 'jpeg')}"
    except Exception:
        pass
    if path and not pathlib.Path(path).is_file():
        # Try workspace-relative if absolute missing
        workspace = os.environ.get("WATHEFNI_WORKSPACE") or ""
        if workspace and not str(path).startswith("/"):
            candidate = pathlib.Path(workspace) / path
            if candidate.is_file():
                path = str(candidate)
    return (str(path) if path else None, mime)


def _load_text(cur: Any, app_key: str) -> str:
    try:
        cur.execute(
            """
            SELECT left(coalesce(content, ''), 50000) AS content
            FROM semantic_documents
            WHERE entity_type='application' AND entity_key=%s
            LIMIT 1
            """,
            (app_key,),
        )
        row = cur.fetchone()
        if row and row.get("content"):
            return str(row["content"])
    except Exception:
        pass
    # Fallback: candidate_cv_text_versions if present
    try:
        cur.execute(
            """
            SELECT left(coalesce(text, content, ''), 50000) AS content
            FROM candidate_cv_text_versions
            WHERE app_key=%s
            ORDER BY created_at DESC NULLS LAST
            LIMIT 1
            """,
            (app_key,),
        )
        row = cur.fetchone()
        if row and row.get("content"):
            return str(row["content"])
    except Exception:
        pass
    return ""


def main() -> int:
    pid = os.environ.get("PROOF_PID") or ""
    if pid:
        _load_proc_env(pid)

    company = (os.environ.get("COMPANY_CODE") or "WATHEFNI").strip().upper()
    limit = int(os.environ["LIMIT"]) if os.environ.get("LIMIT") else None
    only_app = (os.environ.get("APP_KEY") or "").strip() or None
    force_ocr = (os.environ.get("FORCE_OCR_ANNOTATION") or "").strip().lower() in {"1", "true", "yes"}
    force_reextract = (os.environ.get("FORCE_REEXTRACT") or "").strip().lower() in {"1", "true", "yes"}
    publish = (os.environ.get("WATHEFNI_CV_PROFILE_FACTS_V2") or "").strip().lower() in {
        "1", "true", "yes", "on"
    }

    import app
    import cv_extraction_v2 as cv2
    import candidate_cv_facts as cvf

    os.environ.setdefault("WATHEFNI_CV_EXTRACTION_V2", "true")
    if publish:
        os.environ["WATHEFNI_CV_PROFILE_FACTS_V2"] = "true"

    results: list[dict[str, Any]] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cv2.ensure_schema(cur)
            params: list[Any] = [company]
            sql = """
                SELECT s.facts_id, s.company_code, s.app_key, s.document_id,
                       s.source_content_sha256, s.extracted_text_hash, s.facts_hash,
                       s.evidence_id
                FROM application_cv_fact_snapshots s
                WHERE s.is_current=true AND s.company_code=%s
            """
            if only_app:
                sql += " AND s.app_key=%s"
                params.append(only_app)
            sql += " ORDER BY s.materialized_at ASC NULLS LAST"
            if limit and limit > 0:
                sql += " LIMIT %s"
                params.append(limit)
            cur.execute(sql, tuple(params))
            rows = [dict(r) for r in cur.fetchall()]

            before_v2 = 0
            cur.execute(
                "SELECT count(*) AS n FROM application_cv_extraction_v2 WHERE company_code=%s AND is_current=true",
                (company,),
            )
            before_v2 = int((cur.fetchone() or {}).get("n") or 0)

            before_facts = 0
            cur.execute(
                "SELECT count(*) AS n FROM application_cv_fact_snapshots WHERE company_code=%s AND is_current=true",
                (company,),
            )
            before_facts = int((cur.fetchone() or {}).get("n") or 0)

            for row in rows:
                app_key = str(row["app_key"])
                document_id = str(row.get("document_id") or "")
                source_hash = str(row.get("source_content_sha256") or "unknown")
                text_hash = str(row.get("extracted_text_hash") or "unknown")

                # Idempotent skip when identical source already extracted under same contract.
                cur.execute(
                    """
                    SELECT extraction_id, extraction_hash, status, estimated_cost_usd
                    FROM application_cv_extraction_v2
                    WHERE company_code=%s AND app_key=%s AND document_id=%s
                      AND source_content_sha256=%s
                      AND contract_version=%s AND extractor_version=%s
                    LIMIT 1
                    """,
                    (
                        company,
                        app_key,
                        document_id,
                        source_hash,
                        cv2.CV_EXTRACTION_V2_CONTRACT,
                        cv2.CV_EXTRACTION_V2_EXTRACTOR,
                    ),
                )
                existing = cur.fetchone()
                if existing and not force_ocr and not force_reextract:
                    results.append(
                        {
                            "app_key": app_key,
                            "status": "idempotent_reuse",
                            "extraction_id": str(existing.get("extraction_id")),
                            "prior_status": existing.get("status"),
                        }
                    )
                    # Still refresh is_current / optional publish without re-calling Mistral.
                    cur.execute(
                        """
                        UPDATE application_cv_extraction_v2
                        SET is_current=true, published_to_profile=%s, updated_at=now()
                        WHERE extraction_id=%s::uuid
                        """,
                        (bool(publish and existing.get("status") == "ready"), existing["extraction_id"]),
                    )
                    if publish and existing.get("status") == "ready":
                        cur.execute(
                            "SELECT payload FROM application_cv_extraction_v2 WHERE extraction_id=%s::uuid",
                            (existing["extraction_id"],),
                        )
                        payload_row = cur.fetchone() or {}
                        payload = payload_row.get("payload") if isinstance(payload_row.get("payload"), dict) else {}
                        profile = cv2.project_profile_facts_v2(payload)
                        import candidate_profile_facts as cpf

                        profile["source_facts_id"] = str(row.get("facts_id"))
                        profile["source_extraction_id"] = str(existing.get("extraction_id"))
                        profile["profile_hash"] = cpf.profile_hash(profile)
                        cpf.materialize_profile_facts(
                            cur,
                            facts_id=str(row["facts_id"]),
                            company_code=company,
                            app_key=app_key,
                            profile=profile,
                            source_facts_hash=str(row.get("facts_hash") or ""),
                        )
                    continue

                text = _load_text(cur, app_key)
                local_path, mime = _resolve_local_path(
                    cur, company=company, app_key=app_key, document_id=document_id
                )
                # Native text is evidence / internal fallback input only.
                # PDF / image / DOCX all use Mistral OCR 4 + Document AI as primary.
                run = cv2.run_v2_extraction(
                    local_path=local_path,
                    mime_type=mime,
                    extracted_text=text,
                    prefer_reuse_text=False,
                    force_ocr_annotation=force_ocr or bool(local_path),
                    force_internal=(os.environ.get("WATHEFNI_CV_V2_FORCE_INTERNAL") or "").strip().lower()
                    in {"1", "true", "yes", "on"},
                )
                if not text_hash or text_hash == "unknown":
                    text_hash = cvf.text_hash(text) if text else "unknown"
                materialized = cv2.materialize_v2(
                    cur,
                    company_code=company,
                    app_key=app_key,
                    document_id=document_id or f"backfill:{app_key}",
                    evidence_id=str(row.get("evidence_id") or "") or None,
                    source_content_sha256=source_hash,
                    extracted_text_hash=text_hash,
                    run_result=run,
                    publish_to_profile=publish,
                )
                stats = (run.get("validation") or {}).get("stats") or {}
                results.append(
                    {
                        "app_key": app_key,
                        "status": "extracted",
                        "ok": run.get("ok"),
                        "path": run.get("path"),
                        "extraction_id": str(materialized.get("extraction_id")),
                        "validation_status": materialized.get("status"),
                        "stats": stats,
                        "cost_usd": (run.get("meta") or {}).get("estimated_cost_usd"),
                        "error": (run.get("meta") or {}).get("error"),
                    }
                )
                conn.commit()

            cur.execute(
                "SELECT count(*) AS n FROM application_cv_extraction_v2 WHERE company_code=%s AND is_current=true",
                (company,),
            )
            after_v2 = int((cur.fetchone() or {}).get("n") or 0)
            cur.execute(
                "SELECT count(*) AS n FROM application_cv_fact_snapshots WHERE company_code=%s AND is_current=true",
                (company,),
            )
            after_facts = int((cur.fetchone() or {}).get("n") or 0)
            conn.commit()

    payload = {
        "ok": True,
        "company_code": company,
        "processed": len(results),
        "before_v2_current": before_v2,
        "after_v2_current": after_v2,
        "before_fact_snapshots": before_facts,
        "after_fact_snapshots": after_facts,
        "no_duplicate_fact_snapshots": before_facts == after_facts,
        "publish_to_profile": publish,
        "results": results,
        "total_estimated_cost_usd": round(
            sum(float(r.get("cost_usd") or 0) for r in results), 6
        ),
    }
    print(json.dumps(payload, default=str, indent=2))
    return 0 if payload["ok"] and payload["no_duplicate_fact_snapshots"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
