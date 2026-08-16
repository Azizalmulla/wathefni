#!/usr/bin/env python3
"""Wave 1 qualify — dual-path canary on approved synthetic staging CV PDFs.

Runs authoritative Poppler extract + V2, then hybrid alternate + V2.
Does not create candidate records. Does not make hybrid authoritative.
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

CORPUS = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-corpus-wave2-20260804")
EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/local-hybrid-pdf-engine-wave1-20260804")
RESULTS = EVID / "results"

# Representative approved synthetic subset covering required categories.
SELECTED = [
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
    os.environ[FLAG] = "staging_canary"
    # Ensure OCR can run for scanned pages in hybrid alternate.
    os.environ.setdefault("WATHEFNI_CV_MISTRAL_OCR", "true")

    import cv_extraction as cv
    import cv_extraction_v2 as cv2
    import local_hybrid_pdf_engine_canary as canary

    if not canary.canary_enabled():
        print("flag_not_enabled")
        return 2

    rows: list[dict[str, Any]] = []
    for filename, category in SELECTED:
        path = CORPUS / "corpus" / filename
        if not path.exists():
            # staging_subset copy path
            alt = CORPUS / "staging_subset" / "pdfs" / filename
            path = alt if alt.exists() else path
        if not path.exists():
            rows.append({"file": filename, "ok": False, "error": "missing_file", "category": category})
            continue

        print(f"qualify {filename} ...", flush=True)
        t0 = time.perf_counter()
        auth = cv.extract_cv_document(
            path,
            mime_type="application/pdf",
            company_code="WATHEFNI",
        )
        auth_v2 = cv2.run_v2_extraction(
            local_path=path,
            mime_type="application/pdf",
            extracted_text=auth.text or "",
            blocks=list(auth.blocks or []),
            prefer_reuse_text=False,
        )
        canary_result = canary.run_cv_hybrid_alternate_canary(
            path=path,
            mime_type="application/pdf",
            company_code="WATHEFNI",
            authoritative_extraction=auth,
            authoritative_v2=auth_v2,
            document_id=None,
            app_key=f"canary-{path.stem}",
            db_execute=None,
            allow_paid_ocr=bool(cv.mistral_ocr_enabled() and cv.mistral_api_key()),
        )
        rows.append(
            {
                "file": filename,
                "category": category,
                "wall_ms": int((time.perf_counter() - t0) * 1000),
                "auth_method": auth.method,
                "auth_error": auth.error,
                "auth_quality_ok": auth.quality_ok,
                "auth_v2_ok": bool(auth_v2.get("ok")),
                "auth_v2_path": auth_v2.get("path"),
                "canary": {
                    "ok": canary_result.get("ok"),
                    "error": canary_result.get("error"),
                    "acceptance": canary_result.get("acceptance"),
                    "ocr_pages": canary_result.get("ocr_pages"),
                    "mistral_calls_and_cost": canary_result.get("mistral_calls_and_cost"),
                    "latency_ms": canary_result.get("latency_ms"),
                    "layout": canary_result.get("layout"),
                    "v2_compare": canary_result.get("v2_compare"),
                    "page_methods": canary_result.get("page_methods"),
                    "document_envelope_contract": (canary_result.get("document_envelope") or {}).get("contract"),
                },
            }
        )
        (RESULTS / f"{path.stem}.canary.json").write_text(
            json.dumps(canary_result, indent=2, ensure_ascii=False, default=str)
        )

    acceptances = [r.get("canary", {}).get("acceptance") or {} for r in rows if r.get("canary")]
    summary = {
        "wave": "local_hybrid_pdf_engine_wave1_staging_canary_qualify",
        "created_at": utc_now(),
        "flag": f"{FLAG}=staging_canary",
        "hybrid_authoritative": False,
        "docs": len(rows),
        "docs_ok": sum(1 for r in rows if (r.get("canary") or {}).get("ok")),
        "acceptance_all_pass_docs": sum(1 for a in acceptances if a.get("all_pass")),
        "false_ocr_skip_docs": sum(
            1 for a in acceptances if a.get("zero_false_ocr_skips") is False
        ),
        "structured_regression_docs": sum(
            1 for a in acceptances if a.get("zero_structured_field_accuracy_reduction") is False
        ),
        "ranking_evidence_regression_docs": sum(
            1 for a in acceptances if a.get("zero_missing_ranking_evidence") is False
        ),
        "v2_completion_regression_docs": sum(
            1 for a in acceptances if a.get("v2_completion_same_or_better") is False
        ),
        "gates": {
            "zero_false_ocr_skips": all(a.get("zero_false_ocr_skips") for a in acceptances) if acceptances else False,
            "zero_structured_field_accuracy_reduction": all(
                a.get("zero_structured_field_accuracy_reduction") for a in acceptances
            )
            if acceptances
            else False,
            "zero_missing_ranking_evidence": all(a.get("zero_missing_ranking_evidence") for a in acceptances)
            if acceptances
            else False,
            "v2_completion_same_or_better": all(a.get("v2_completion_same_or_better") for a in acceptances)
            if acceptances
            else False,
            "all_docs_canary_ok": all((r.get("canary") or {}).get("ok") for r in rows if "canary" in r),
        },
        "rows": rows,
    }
    summary["gates"]["all_pass"] = all(summary["gates"].values())
    (RESULTS / "canary_qualify_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({"docs": summary["docs"], "gates": summary["gates"]}, indent=2))
    return 0 if summary["gates"]["all_pass"] else 2


FLAG = "WATHEFNI_LOCAL_HYBRID_PDF_ENGINE"

if __name__ == "__main__":
    raise SystemExit(main())
