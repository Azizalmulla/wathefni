#!/usr/bin/env python3
"""Qualify Local Hybrid PDF Engine Wave 0 against the 560-PDF corpus.

Paid OCR disabled: simulate exact pages that would be sent to Mistral.
Compares hybrid routing vs Poppler path. Does not mutate production.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CORPUS_EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-corpus-wave2-20260804")
EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/local-hybrid-pdf-engine-wave0-20260804")
RESULTS = EVID / "results"
ARTIFACTS = EVID / "artifacts"
CACHE = EVID / "cache"

import cv_extraction as cv  # noqa: E402
from local_hybrid_pdf_engine import (  # noqa: E402
    HybridEngineLimits,
    extract_pdf_hybrid,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pct(n: int, d: int) -> float:
    return round(100.0 * n / d, 2) if d else 0.0


def percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((CORPUS_EVID / "manifests/corpus_manifest.json").read_text())
    docs = manifest["documents"]
    limits = HybridEngineLimits(
        max_pages=15,
        max_bytes=25 * 1024 * 1024,
        allow_paid_ocr=False,
        cache_dir=CACHE / "simulate",
        max_projected_cost_usd=1.0,
    )

    rows: list[dict[str, Any]] = []
    false_skips: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    overheads: list[float] = []
    cat_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "n": 0, "hybrid_ocr_pages": 0, "poppler_ocr_pages": 0,
        "hybrid_native_pages": 0, "agree_ocr_set": 0, "false_skip_docs": 0,
    })

    for idx, doc in enumerate(docs):
        path = CORPUS_EVID / doc["rel_path"]
        cat = doc["category"]
        st = cat_stats[cat]
        st["n"] += 1

        assessments = cv.assess_pdf_pages(path)
        poppler_ocr = sorted(
            int(a.page_number) for a in assessments if a.disposition == "needs_ocr"
        )
        hybrid = extract_pdf_hybrid(
            path,
            limits=limits,
            document_class="cv" if "cv" in cat or cat.endswith("_cv") or "digital" in cat or "scanned" in cat or "encoding" in cat or "font" in cat or "cid" in cat else "other",
            source_channel="corpus_wave2_offline",
        )
        hybrid_ocr = [p.page_number for p in hybrid.pages if p.method == "ocr"]
        hybrid_native = [p.page_number for p in hybrid.pages if p.method == "native"]
        hybrid_failed = [p.page_number for p in hybrid.pages if p.method == "failed"]
        quality_forced = [p.page_number for p in hybrid.pages if p.quality_forced_ocr]

        # False OCR skip = hybrid kept native on a page that truly needs OCR.
        # Do NOT treat Poppler Arabic over-OCR (too_few_words) as a hybrid false-skip
        # when native Arabic Markdown is usable — Wave 0/2 explicitly preserve those.
        false_skip_pages: list[int] = []
        for p in hybrid.pages:
            if p.method != "native":
                continue
            poppler_page = next((a for a in assessments if a.page_number == p.page_number), None)
            poppler_reason = str(getattr(poppler_page, "reason", "") or "")
            truly_needs = bool(p.inspector_needs_ocr) or cat in {
                "broken_encoding",
                "scanned_image_only_cv",
                "scanned_arabic_cv",
                "rotated_scan_cv",
                "lowres_compressed_scan_cv",
            } or (
                cat == "mixed_digital_scanned"
                and poppler_reason in {"image_only_page", "scanned_or_empty"}
            ) or poppler_reason in {
                "image_only_page",
                "scanned_or_empty",
                "corrupt_or_unusable_text",
                "image_dominant_sparse_text",
            }
            # Arabic tokenization mismatch is not a true OCR need when native is usable.
            if poppler_reason == "too_few_words" and "arabic" in cat:
                truly_needs = False
            if cat == "broken_encoding":
                truly_needs = True
            if truly_needs:
                false_skip_pages.append(p.page_number)
        false_skip_pages = sorted(set(false_skip_pages))

        agree = set(poppler_ocr) == set(hybrid_ocr)
        st["hybrid_ocr_pages"] += len(hybrid_ocr)
        st["poppler_ocr_pages"] += len(poppler_ocr)
        st["hybrid_native_pages"] += len(hybrid_native)
        if agree:
            st["agree_ocr_set"] += 1
        if false_skip_pages:
            st["false_skip_docs"] += 1

        overheads.append(float(hybrid.wall_ms))
        row = {
            "doc_id": doc["doc_id"],
            "category": cat,
            "pages": doc["pages"],
            "ok": hybrid.ok,
            "error": hybrid.error,
            "wall_ms": hybrid.wall_ms,
            "poppler_ocr_pages": poppler_ocr,
            "hybrid_ocr_pages": hybrid_ocr,
            "hybrid_native_pages": hybrid_native,
            "hybrid_failed_pages": hybrid_failed,
            "quality_forced_ocr_pages": quality_forced,
            "ocr_set_agreement_with_poppler": agree,
            "false_skip_pages_vs_poppler_or_broken_gate": false_skip_pages,
            "page_decisions": [
                {
                    "page": p.page_number,
                    "method": p.method,
                    "reason": p.reason,
                    "inspector_needs_ocr": p.inspector_needs_ocr,
                    "quality_forced_ocr": p.quality_forced_ocr,
                }
                for p in hybrid.pages
            ],
            "merged_preview": (hybrid.merged_markdown or "")[:240],
            "arabic_chars_merged": sum(
                1 for ch in (hybrid.merged_markdown or "") if "\u0600" <= ch <= "\u06FF"
            ),
            "envelope_contract": hybrid.envelope.get("contract"),
            "cache_hit": hybrid.cache_hit,
        }
        rows.append(row)
        if false_skip_pages:
            false_skips.append(row)
        if not agree or false_skip_pages or quality_forced:
            disagreements.append(row)
        if (idx + 1) % 50 == 0:
            print(f"qualified {idx+1}/{len(docs)}", flush=True)

    broken = [r for r in rows if r["category"] == "broken_encoding"]
    arabic_wave0 = [
        r for r in rows
        if r["doc_id"] in {
            "wave0_cv_ar_digital_01",
            "wave0_cv_ar_digital_02",
            "wave0_cv_ar_digital_03",
        }
    ]
    scanned = [r for r in rows if "scanned" in r["category"] or r["category"] == "mixed_digital_scanned"]
    rotated = [r for r in rows if r["category"] in {"rotated_scan_cv", "lowres_compressed_scan_cv"}]

    broken_all_ocr = all(
        r["hybrid_native_pages"] == [] and len(r["hybrid_ocr_pages"]) >= 1
        for r in broken
    )
    arabic_preserved = all(
        r["hybrid_native_pages"] == [1] and r["hybrid_ocr_pages"] == [] and r["arabic_chars_merged"] >= 40
        for r in arabic_wave0
    )
    scanned_ok = all(
        set(r["hybrid_ocr_pages"])  # at least some OCR
        and not r["false_skip_pages_vs_poppler_or_broken_gate"]
        for r in scanned + rotated
    )
    # Mixed: page2 OCR, page1 often native
    mixed = [r for r in rows if r["category"] == "mixed_digital_scanned"]
    mixed_ok = all(
        2 in r["hybrid_ocr_pages"] and 1 in r["hybrid_native_pages"]
        for r in mixed
    ) if mixed else False

    zero_false_skips = len(false_skips) == 0

    summary = {
        "wave": "local_hybrid_pdf_engine_wave0_corpus_qualify",
        "created_at": utc_now(),
        "paid_ocr": False,
        "corpus_n": len(docs),
        "evaluated": len(rows),
        "ok_count": sum(1 for r in rows if r["ok"]),
        "false_skip_docs": len(false_skips),
        "zero_false_ocr_skips": zero_false_skips,
        "broken_encoding": {
            "n": len(broken),
            "all_routed_to_ocr": broken_all_ocr,
            "ocr_doc_count": sum(1 for r in broken if r["hybrid_ocr_pages"]),
            "native_doc_count": sum(1 for r in broken if r["hybrid_native_pages"]),
        },
        "arabic_wave0_three": {
            "n": len(arabic_wave0),
            "preserved_locally": arabic_preserved,
            "details": [
                {
                    "doc_id": r["doc_id"],
                    "native": r["hybrid_native_pages"],
                    "ocr": r["hybrid_ocr_pages"],
                    "arabic_chars": r["arabic_chars_merged"],
                }
                for r in arabic_wave0
            ],
        },
        "scanned_and_mixed": {
            "scanned_or_rotated_n": len(scanned) + len(rotated),
            "scanned_no_false_skip": scanned_ok,
            "mixed_n": len(mixed),
            "mixed_page_routing_ok": mixed_ok,
        },
        "ocr_set_agreement_with_poppler_pct": pct(
            sum(1 for r in rows if r["ocr_set_agreement_with_poppler"]), len(rows)
        ),
        "hybrid_ocr_pages_total": sum(len(r["hybrid_ocr_pages"]) for r in rows),
        "poppler_ocr_pages_total": sum(len(r["poppler_ocr_pages"]) for r in rows),
        "quality_forced_ocr_pages_total": sum(len(r["quality_forced_ocr_pages"]) for r in rows),
        "projected_mistral_cost_usd": round(
            sum(len(r["hybrid_ocr_pages"]) for r in rows) * 0.004, 4
        ),
        "overhead_ms": {
            "p50": percentile(overheads, 50),
            "p95": percentile(overheads, 95),
            "p99": percentile(overheads, 99),
            "max": max(overheads) if overheads else None,
            "mean": round(statistics.fmean(overheads), 3) if overheads else None,
        },
        "category_stats": {k: dict(v) for k, v in sorted(cat_stats.items())},
        "gates": {
            "zero_false_ocr_skips": zero_false_skips,
            "broken_encoding_all_ocr": broken_all_ocr,
            "arabic_wave0_preserved_local": arabic_preserved,
            "scanned_mixed_routing": bool(scanned_ok and mixed_ok),
            "envelope_contract_document_envelope_at_1": all(
                r.get("envelope_contract") == "document_envelope@1" for r in rows
            ),
        },
    }

    (RESULTS / "corpus_qualify_per_document.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False)
    )
    (RESULTS / "corpus_qualify_summary.json").write_text(json.dumps(summary, indent=2))
    (RESULTS / "false_skips.json").write_text(json.dumps(false_skips, indent=2, ensure_ascii=False))
    (RESULTS / "disagreements_vs_poppler.json").write_text(
        json.dumps(disagreements, indent=2, ensure_ascii=False)
    )

    print(json.dumps({
        "evaluated": summary["evaluated"],
        "gates": summary["gates"],
        "false_skip_docs": summary["false_skip_docs"],
        "hybrid_ocr_pages_total": summary["hybrid_ocr_pages_total"],
        "poppler_ocr_pages_total": summary["poppler_ocr_pages_total"],
        "agreement_pct": summary["ocr_set_agreement_with_poppler_pct"],
        "overhead_p95": summary["overhead_ms"]["p95"],
    }, indent=2))

    gates = summary["gates"]
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
