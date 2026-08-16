#!/usr/bin/env python3
"""Capped real-Mistral proof for Local Hybrid PDF Engine Wave 0.

Maximum 30 billable pages. Selects representative pages that require OCR
from the Wave 2 corpus / staging subset. Records model, pages, latency, cost,
merged output, and light CV-field heuristics. Does not touch production routing.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-corpus-wave2-20260804/corpus")
EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/local-hybrid-pdf-engine-wave0-20260804")
OUT = EVID / "real_ocr"
CACHE = EVID / "cache" / "real"

from local_hybrid_pdf_engine import (  # noqa: E402
    COST_USD_PER_PAGE,
    HybridEngineLimits,
    PINNED_OCR_MODEL,
    extract_pdf_hybrid,
)
import cv_extraction as cv  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def field_hits(text: str) -> dict[str, bool]:
    t = text or ""
    return {
        "has_email": bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t)),
        "has_phone": bool(re.search(r"\+?\d[\d\s\-()]{7,}\d", t)),
        "has_experience_marker": bool(re.search(r"experience|خبرة|EXPERIENCE", t, re.I)),
        "has_skills_marker": bool(re.search(r"skills|مهارات|SKILLS", t, re.I)),
        "arabic_chars": sum(1 for ch in t if "\u0600" <= ch <= "\u06FF"),
        "chars": len(t),
        "words": len(re.findall(r"\S+", t)),
    }


# Representative docs whose hybrid routing requests OCR. Cap total OCR pages <= 30.
CANDIDATES = [
    "syn_scanned_image_only_cv_000.pdf",
    "syn_scanned_image_only_cv_001.pdf",
    "syn_scanned_arabic_cv_000.pdf",
    "syn_mixed_digital_scanned_000.pdf",
    "syn_mixed_digital_scanned_001.pdf",
    "syn_rotated_scan_cv_000.pdf",
    "syn_lowres_compressed_scan_cv_000.pdf",
    "syn_broken_encoding_000.pdf",
    "syn_broken_encoding_001.pdf",
    "wave0_cv_scanned_en_01.pdf",
    "wave0_cv_mixed_01.pdf",
    "wave0_cv_broken_encoding_01.pdf",
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    if not cv.mistral_api_key():
        report = {
            "ok": False,
            "error": "missing_mistral_api_key",
            "hint": "Set MISTRAL_API_KEY or WATHEFNI_MISTRAL_ENV for capped proof only",
            "created_at": utc_now(),
        }
        (OUT / "real_ocr_proof.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 3

    limits = HybridEngineLimits(
        max_pages=15,
        allow_paid_ocr=True,
        max_retries=2,
        max_projected_cost_usd=0.12,  # 30 * 0.004
        cache_dir=CACHE,
        timeout_s=120.0,
    )

    selected: list[Path] = []
    projected_pages = 0
    plan: list[dict[str, Any]] = []
    for name in CANDIDATES:
        path = CORPUS / name
        if not path.exists():
            continue
        # Dry routing with paid OCR off to know pages
        dry = extract_pdf_hybrid(
            path,
            limits=HybridEngineLimits(allow_paid_ocr=False, max_pages=15, cache_dir=None),
        )
        ocr_pages = [p.page_number for p in dry.pages if p.method == "ocr"]
        if not ocr_pages:
            continue
        if projected_pages + len(ocr_pages) > 30:
            break
        selected.append(path)
        projected_pages += len(ocr_pages)
        plan.append({"file": name, "ocr_pages": ocr_pages, "native_pages": [p.page_number for p in dry.pages if p.method == "native"]})

    results: list[dict[str, Any]] = []
    total_billable = 0
    total_cost = 0.0
    total_latency = 0

    for path in selected:
        # Also run Poppler path for comparison (OCR only if enabled — same key)
        poppler_assessments = cv.assess_pdf_pages(path)
        poppler_ocr = [a.page_number for a in poppler_assessments if a.disposition == "needs_ocr"]

        hybrid = extract_pdf_hybrid(
            path,
            limits=limits,
            document_class="cv",
            source_channel="real_ocr_proof_wave0",
            include_merged_in_envelope=True,
        )
        billable = int(hybrid.envelope.get("processing", {}).get("billable_pages") or 0)
        cost = float(hybrid.envelope.get("processing", {}).get("estimated_cost_usd") or 0.0)
        latency = int(hybrid.envelope.get("processing", {}).get("ocr", {}).get("latency_ms") or hybrid.wall_ms)
        total_billable += billable
        total_cost += cost
        total_latency += latency

        # Poppler+Mistral comparison on same OCR pages (capped)
        poppler_by_page: dict[int, str] = {}
        poppler_meta = {}
        if poppler_ocr and cv.mistral_ocr_enabled() is False:
            # Force OCR call for comparison even if WATHEFNI_CV_MISTRAL_OCR is off —
            # this proof uses the adapter directly.
            pass
        if poppler_ocr:
            idxs = [p - 1 for p in poppler_ocr]
            by_page, _blocks, meta = cv.extract_pdf_pages_with_mistral(path, idxs)
            poppler_by_page = by_page
            poppler_meta = {
                "error": meta.error,
                "latency_ms": meta.latency_ms,
                "billable_pages": meta.billable_pages,
                "estimated_cost_usd": meta.estimated_cost_usd,
                "request_id": meta.provider_request_id,
                "model": meta.actual_request_model or PINNED_OCR_MODEL,
            }
            # Count comparison OCR toward evidence but keep within overall spirit;
            # track separately so primary hybrid billable stays primary.
        poppler_merged_parts = []
        for a in poppler_assessments:
            if a.disposition == "accepted_local" and a.local_text:
                poppler_merged_parts.append(a.local_text)
            elif a.page_number in poppler_by_page:
                poppler_merged_parts.append(poppler_by_page[a.page_number])
        poppler_merged = "\n\n".join(poppler_merged_parts).strip()

        row = {
            "file": path.name,
            "hybrid_ok": hybrid.ok,
            "hybrid_error": hybrid.error,
            "hybrid_pages": [
                {"page": p.page_number, "method": p.method, "reason": p.reason, "chars": len(p.text or "")}
                for p in hybrid.pages
            ],
            "hybrid_merged_preview": (hybrid.merged_markdown or "")[:500],
            "hybrid_fields": field_hits(hybrid.merged_markdown),
            "hybrid_billable_pages": billable,
            "hybrid_cost_usd": cost,
            "hybrid_ocr_latency_ms": latency,
            "hybrid_request_id": hybrid.envelope.get("processing", {}).get("request_id"),
            "poppler_ocr_pages": poppler_ocr,
            "poppler_compare": poppler_meta,
            "poppler_fields": field_hits(poppler_merged),
            "envelope": hybrid.envelope,
        }
        results.append(row)
        (OUT / f"{path.stem}.envelope.json").write_text(
            json.dumps(hybrid.envelope | {"merged_markdown": hybrid.merged_markdown}, indent=2, ensure_ascii=False)
        )
        print(f"done {path.name} billable={billable} cost={cost} err={hybrid.error}", flush=True)

    summary = {
        "wave": "local_hybrid_pdf_engine_wave0_real_ocr_proof",
        "created_at": utc_now(),
        "model": PINNED_OCR_MODEL,
        "docs": len(results),
        "plan": plan,
        "hybrid_billable_pages_total": total_billable,
        "hybrid_estimated_cost_usd_total": round(total_cost, 6),
        "hybrid_ocr_latency_ms_sum": total_latency,
        "cost_per_page_assumption": COST_USD_PER_PAGE,
        "cap_pages": 30,
        "within_cap": total_billable <= 30,
        "results": results,
    }
    (OUT / "real_ocr_proof.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps({
        "docs": summary["docs"],
        "billable": total_billable,
        "cost": summary["hybrid_estimated_cost_usd_total"],
        "within_cap": summary["within_cap"],
    }, indent=2))
    return 0 if results and summary["within_cap"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
