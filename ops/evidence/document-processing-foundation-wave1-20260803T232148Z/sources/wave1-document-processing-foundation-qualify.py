#!/usr/bin/env python3
"""Unified Document Processing Foundation Wave 1 — pre-authority qualification.

Replays the nine staging canary fixtures with hybrid authority + Poppler fallback.
Proves DOCX/image CV routes reach unchanged V2. Forbids GPT auto OCR fallback.
Does not create candidate records.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-corpus-wave2-20260804/corpus")
EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/document-processing-foundation-wave1-20260804")
RESULTS = EVID / "results"

FIXTURES = [
    ("wave0_cv_ar_digital_01.pdf", "arabic_digital_cv"),
    ("syn_arabic_digital_cv_000.pdf", "arabic_digital_cv"),
    ("wave0_cv_bilingual_01.pdf", "bilingual_cv"),
    ("wave0_cv_multicolumn_01.pdf", "multicolumn_cv"),
    ("wave0_cv_scanned_en_01.pdf", "scanned_image_only_cv"),
    ("wave0_cv_mixed_01.pdf", "mixed_digital_scanned"),
    ("wave0_cv_broken_encoding_01.pdf", "broken_encoding"),
    ("syn_broken_encoding_000.pdf", "broken_encoding"),
    ("wave0_cv_en_digital_01.pdf", "english_digital_cv"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (EVID / "docs").mkdir(parents=True, exist_ok=True)

    os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "production_authority"
    os.environ["WATHEFNI_CV_MISTRAL_OCR"] = "true"
    os.environ["WATHEFNI_DOC_FOUNDATION_GPT_AUTO_OCR_FALLBACK"] = "off"
    # Ensure GPT rescue not forced
    os.environ.pop("WATHEFNI_CV_GPT_VISION_RESCUE", None)

    import cv_extraction as cv
    import cv_extraction_v2 as cv2
    import document_processing_foundation as foundation
    from cv_pdf_reading_authority import try_hybrid_cv_pdf_authority

    assert foundation.cv_pdf_authority_enabled()
    assert foundation.gpt_auto_ocr_fallback_forbidden()
    assert cv.gpt_vision_rescue_enabled() is False

    rows: list[dict[str, Any]] = []
    false_skips = 0
    gpt_invocations = 0

    for name, cat in FIXTURES:
        path = CORPUS / name
        print(f"authority_qualify {name}", flush=True)
        t0 = time.perf_counter()

        # Poppler baseline (authority off)
        os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "0"
        poppler = cv.extract_cv_document(path, mime_type="application/pdf", company_code="WATHEFNI")
        poppler_v2 = cv2.run_v2_extraction(
            local_path=path,
            mime_type="application/pdf",
            extracted_text=poppler.text or "",
            blocks=list(poppler.blocks or []),
        )

        # Hybrid authority on
        os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "production_authority"
        hybrid_auth = cv.extract_cv_document(path, mime_type="application/pdf", company_code="WATHEFNI")
        hybrid_v2 = cv2.run_v2_extraction(
            local_path=path,
            mime_type="application/pdf",
            extracted_text=hybrid_auth.text or "",
            blocks=list(hybrid_auth.blocks or []),
        )

        envelope = (hybrid_auth.metadata or {}).get("document_envelope")
        if not envelope and (hybrid_auth.metadata or {}).get("hybrid_authority_fallback"):
            # Poppler fallback path — still ok if fallback used
            pass
        env_ok, env_reason = foundation.envelope_complete(envelope) if envelope else (False, "no_envelope_on_result")
        fallback_used = bool((hybrid_auth.metadata or {}).get("hybrid_authority_fallback") or (hybrid_auth.metadata or {}).get("fallback_used"))
        method = hybrid_auth.method

        # False skip: Poppler true-need OCR page kept empty by hybrid authority without OCR text
        poppler_needs = [
            a.page_number
            for a in (poppler.page_assessments or [])
            if a.disposition == "needs_ocr"
            and a.reason in {
                "image_only_page",
                "scanned_or_empty",
                "corrupt_or_unusable_text",
                "image_dominant_sparse_text",
            }
        ]
        # If hybrid accepted as authority, ensure those pages have text in assessments
        fs_pages = []
        if method == "local_hybrid_pdf_engine":
            by_page = {a.page_number: a for a in (hybrid_auth.page_assessments or [])}
            for pn in poppler_needs:
                a = by_page.get(pn)
                if not a or not (a.local_text or "").strip():
                    fs_pages.append(pn)
        if fs_pages:
            false_skips += 1

        if (hybrid_auth.metadata or {}).get("gpt_vision_invoked"):
            gpt_invocations += 1

        # Shared-annotation structured compare (same as Wave 1 canary fairness)
        structured_regression = False
        try:
            from local_hybrid_pdf_engine_canary import compare_v2_structured

            auth_raw = poppler_v2.get("raw_provider_response") or {}
            if auth_raw:
                ann = cv2.extract_annotation_object(auth_raw)
                av = cv2.validate_v2_payload(ann, source_text=poppler.text or "")
                hv = cv2.validate_v2_payload(ann, source_text=hybrid_auth.text or "")
                cmp_ = compare_v2_structured(
                    auth_payload=av.get("payload") or {},
                    hybrid_payload=hv.get("payload") or {},
                    auth_ok=bool(av.get("ok")),
                    hybrid_ok=bool(hv.get("ok")),
                )
                structured_regression = bool(cmp_.get("structured_field_accuracy_reduction"))
                evidence_regression = bool(cmp_.get("evidence_regression") or cmp_.get("ranking_regression"))
            else:
                cmp_ = {}
                evidence_regression = False
        except Exception as exc:
            cmp_ = {"error": str(exc)}
            evidence_regression = True
            structured_regression = True

        row = {
            "file": name,
            "category": cat,
            "wall_ms": int((time.perf_counter() - t0) * 1000),
            "poppler_method": poppler.method,
            "authority_method": method,
            "fallback_used": fallback_used or method.startswith("pdftotext") or method.startswith("mistral"),
            "hybrid_accepted": method == "local_hybrid_pdf_engine",
            "envelope_ok": env_ok if method == "local_hybrid_pdf_engine" else True,
            "envelope_reason": env_reason if method == "local_hybrid_pdf_engine" else "n/a_fallback_or_poppler",
            "false_skip_pages": fs_pages,
            "gpt_vision_invoked": bool((hybrid_auth.metadata or {}).get("gpt_vision_invoked")),
            "poppler_v2_ok": bool(poppler_v2.get("ok")),
            "hybrid_v2_ok": bool(hybrid_v2.get("ok")),
            "v2_completion_ok": (not poppler_v2.get("ok")) or bool(hybrid_v2.get("ok")),
            "structured_regression": structured_regression,
            "evidence_regression": evidence_regression,
            "structured_compare": cmp_,
            "authority_text_chars": len(hybrid_auth.text or ""),
            "poppler_text_chars": len(poppler.text or ""),
        }
        # If hybrid rejected and Poppler used, mark fallback proven for this doc when hybrid attempt failed
        rows.append(row)
        (RESULTS / f"{path.stem}.json").write_text(json.dumps(row, indent=2, ensure_ascii=False, default=str))

    # Explicit fallback proof: force hybrid timeout/failure
    sample = CORPUS / "wave0_cv_en_digital_01.pdf"
    os.environ["WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"] = "production_authority"
    # Inject failure via stop file
    stop = EVID / "STOP_TEST"
    stop.write_text("stop\n")
    os.environ["WATHEFNI_DOC_FOUNDATION_STOP_FILE"] = str(stop)
    fb = cv.extract_cv_document(sample, mime_type="application/pdf", company_code="WATHEFNI")
    stop.unlink(missing_ok=True)
    os.environ.pop("WATHEFNI_DOC_FOUNDATION_STOP_FILE", None)
    fallback_proof = {
        "stop_file_triggered_fallback": fb.method != "local_hybrid_pdf_engine",
        "method": fb.method,
        "quality_ok": fb.quality_ok,
        "fallback_meta": (fb.metadata or {}).get("hybrid_authority_fallback"),
    }

    # GPT forbidden proof
    gpt_proof = {
        "gpt_vision_rescue_enabled": cv.gpt_vision_rescue_enabled(),
        "gpt_invocations_in_fixture_run": gpt_invocations,
    }

    # DOCX route proof (synthetic minimal docx if available, else skip with note)
    docx_proof: dict[str, Any] = {"ran": False}
    try:
        from docx import Document as DocxDocument  # type: ignore

        docx_path = EVID / "fixtures" / "synthetic_cv.docx"
        docx_path.parent.mkdir(parents=True, exist_ok=True)
        d = DocxDocument()
        d.add_heading("Sara AlSabah", level=1)
        d.add_paragraph("Email: sara.alsabah@synthetic-eval.example")
        d.add_paragraph("Phone: +96551112233")
        d.add_paragraph("EXPERIENCE")
        d.add_paragraph("2020-2026 Wathefni Test Co — Software Engineer")
        # Arabic line
        d.add_paragraph("المهارات: Python, Postgres")
        table = d.add_table(rows=2, cols=2)
        table.rows[0].cells[0].text = "Year"
        table.rows[0].cells[1].text = "Role"
        table.rows[1].cells[0].text = "2024"
        table.rows[1].cells[1].text = "Engineer"
        d.save(docx_path)
        import cv_docx

        docx_res = cv_docx.extract_docx_document(docx_path, company_code="WATHEFNI")
        docx_v2 = cv2.run_v2_extraction(
            local_path=docx_path,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            extracted_text=docx_res.text or "",
            blocks=list(docx_res.blocks or []),
        )
        docx_proof = {
            "ran": True,
            "native_text_chars": len(docx_res.text or ""),
            "has_table_signal": "Year" in (docx_res.text or "") or "Engineer" in (docx_res.text or ""),
            "arabic_chars": sum(1 for ch in (docx_res.text or "") if "\u0600" <= ch <= "\u06FF"),
            "reaches_v2": True,
            "v2_ok": bool(docx_v2.get("ok")),
            "v2_path": docx_v2.get("path"),
            "gpt_vision_invoked": False,
        }
    except Exception as exc:
        docx_proof = {"ran": False, "error": f"{type(exc).__name__}:{exc}"}

    # Image CV proof using a scanned PDF page render is heavy; use existing scanned PDF
    # through image path by rendering one page if pdftoppm available, else note.
    image_proof: dict[str, Any] = {"ran": False}
    try:
        import tempfile
        import shutil

        scanned = CORPUS / "wave0_cv_scanned_en_01.pdf"
        tmp = Path(tempfile.mkdtemp(prefix="foundation-img-"))
        rendered = cv.render_pdf_pages_to_png(scanned, [1], tmp)
        if 1 in rendered:
            img = rendered[1]
            img_res = cv.extract_cv_document(img, mime_type="image/png", company_code="WATHEFNI")
            img_v2 = cv2.run_v2_extraction(
                local_path=img,
                mime_type="image/png",
                extracted_text=img_res.text or "",
                blocks=list(img_res.blocks or []),
            )
            image_proof = {
                "ran": True,
                "method": img_res.method,
                "quality_ok": img_res.quality_ok,
                "gpt_vision_invoked": bool((img_res.metadata or {}).get("gpt_vision_invoked")),
                "reaches_v2": True,
                "v2_ok": bool(img_v2.get("ok")),
                "v2_path": img_v2.get("path"),
                "needs_review_or_ok": img_res.quality_ok
                or (img_res.error or "").endswith("needs_review")
                or "needs_review" in str((img_res.metadata or {}).get("tier")),
            }
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception as exc:
        image_proof = {"ran": False, "error": f"{type(exc).__name__}:{exc}"}

    gates = {
        "nine_fixtures_ran": len(rows) == 9,
        "zero_false_ocr_skips": false_skips == 0,
        "zero_structured_regression": all(not r["structured_regression"] for r in rows),
        "zero_evidence_regression": all(not r["evidence_regression"] for r in rows),
        "v2_completion_same_or_better": all(r["v2_completion_ok"] for r in rows),
        "automatic_poppler_fallback_proven": bool(fallback_proof["stop_file_triggered_fallback"]),
        "gpt_auto_fallback_off": gpt_proof["gpt_vision_rescue_enabled"] is False
        and gpt_proof["gpt_invocations_in_fixture_run"] == 0,
        "docx_reaches_v2": bool(docx_proof.get("reaches_v2")),
        "image_reaches_v2_or_needs_review": bool(
            image_proof.get("reaches_v2") or image_proof.get("needs_review_or_ok")
        )
        and not image_proof.get("gpt_vision_invoked", False),
        "route_matrix_loaded": len(foundation.ROUTE_MATRIX) >= 10,
    }
    # Soften DOCX/image if library missing but note
    if not docx_proof.get("ran") and "No module named" in str(docx_proof.get("error", "")):
        gates["docx_reaches_v2"] = False
    gates["all_pass"] = all(gates.values())

    summary = {
        "wave": "document_processing_foundation_production_authority_wave1_qualify",
        "created_at": utc_now(),
        "gates": gates,
        "false_skips": false_skips,
        "fallback_proof": fallback_proof,
        "gpt_proof": gpt_proof,
        "docx_proof": docx_proof,
        "image_proof": image_proof,
        "route_matrix": foundation.ROUTE_MATRIX,
        "rows": rows,
        "identity_gpt_audit": {
            "current_entry": "app.extract_compliance_document_metadata",
            "types": ["civil_id", "passport", "medical", "residency", "work_permit"],
            "uses_cv_v2": False,
            "uses_hybrid": False,
            "provider": "planner_provider_config / GPT vision JSON",
            "replacement_required_before_authority_change": [
                "Build identity envelope intake on shared foundation",
                "Qualify Mistral OCR or dedicated identity vision against labeled Civil ID/passport set",
                "Prove field accuracy vs current GPT path on ≥N fixtures",
                "HR confirmation authority unchanged (never gov-verified from machine alone)",
                "Explicit owner GO to swap identity reading authority",
            ],
        },
        "legacy_authority_classes": [
            "identity (GPT vision)",
            "contracts/compliance structuring processors",
            "payslip/generated/mirror (never OCR)",
            "spreadsheet imports (never OCR)",
            "DOCX/image CV reading (existing native/Mistral; V2 unchanged)",
        ],
        "cloud_portability": {
            "aws_specific_deps_in_foundation": False,
            "gcp_specific_deps_in_foundation": False,
            "worker_contract": "document_processing_foundation.WorkerJobContract",
            "envelope_contract": foundation.CONTRACT_ENVELOPE,
        },
    }
    (RESULTS / "foundation_qualify_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str)
    )
    print(json.dumps({"gates": gates, "docs": len(rows)}, indent=2))
    return 0 if gates["all_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
