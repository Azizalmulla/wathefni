#!/usr/bin/env python3
"""Wave 2 — offline shadow evaluation of the CV PDF corpus.

Runs pdf-inspector shadow + Poppler assess_pdf_pages + quality-gate reasons.
Does NOT call paid OCR / Mistral. Does NOT create candidate records.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-corpus-wave2-20260804")
MANIFESTS = EVID / "manifests"
RESULTS = EVID / "results"
ARTIFACTS = EVID / "artifacts"
STAGING = EVID / "staging_subset"
COST_USD_PER_PAGE = 0.004

os.environ["WATHEFNI_PDF_INSPECTOR_SHADOW"] = "1"
os.environ.setdefault("WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS", "500")

import cv_extraction as cv  # noqa: E402
import pdf_inspector_shadow as sh  # noqa: E402


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
    manifest = json.loads((MANIFESTS / "corpus_manifest.json").read_text())
    docs = manifest["documents"]
    RESULTS.mkdir(parents=True, exist_ok=True)
    STAGING.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    per_doc: list[dict[str, Any]] = []
    overheads: list[float] = []
    disagreements: list[dict[str, Any]] = []
    false_skip_candidates: list[dict[str, Any]] = []
    detection_counts = Counter()
    category_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "n": 0, "agree": 0, "inspector_fewer": 0, "inspector_more": 0, "high_risk": 0,
        "timeouts": 0, "errors": 0, "poppler_ocr_pages": 0, "inspector_ocr_pages": 0,
    })

    poppler_ocr_pages_total = 0
    inspector_ocr_pages_total = 0
    success = 0
    timeout_n = 0
    error_n = 0
    fail_open_n = 0

    for idx, doc in enumerate(docs):
        path = EVID / doc["rel_path"]
        cat = doc["category"]
        st = category_stats[cat]
        st["n"] += 1
        try:
            assessments = cv.assess_pdf_pages(path)
            shadow = sh.run_pdf_inspector_shadow(path, assessments)
        except Exception as exc:
            error_n += 1
            st["errors"] += 1
            per_doc.append({
                "doc_id": doc["doc_id"],
                "category": cat,
                "ok": False,
                "error": str(exc),
            })
            continue

        insp = shadow.get("inspector") or {}
        cmp_ = shadow.get("comparison") or {}
        status = str(shadow.get("status") or "ok")
        elapsed = float(
            shadow.get("wall_ms")
            or shadow.get("elapsed_ms")
            or insp.get("wall_ms")
            or insp.get("processing_time_ms")
            or 0
        )
        if elapsed:
            overheads.append(elapsed)

        if status in {"timeout", "error", "fail_open"}:
            fail_open_n += 1
            if status == "timeout":
                timeout_n += 1
                st["timeouts"] += 1
            else:
                error_n += 1
                st["errors"] += 1
        else:
            success += 1

        poppler_pages = list(cmp_.get("poppler_pages_needing_ocr_1idx") or [])
        inspector_pages = list(cmp_.get("inspector_pages_needing_ocr_1idx") or [])
        agree = bool(cmp_.get("agreement"))
        false_skip = list(cmp_.get("false_skip_candidates_1idx") or [])
        unnecessary = list(cmp_.get("unnecessary_ocr_candidates_1idx") or [])
        high_risk = bool(cmp_.get("high_risk_false_skip_candidate"))
        dets = cmp_.get("detections") or {}
        for k, v in dets.items():
            if v:
                detection_counts[k] += 1

        st["poppler_ocr_pages"] += len(poppler_pages)
        st["inspector_ocr_pages"] += len(inspector_pages)
        poppler_ocr_pages_total += len(poppler_pages)
        inspector_ocr_pages_total += len(inspector_pages)
        if agree:
            st["agree"] += 1
        if false_skip:
            st["inspector_fewer"] += 1
        if unnecessary:
            st["inspector_more"] += 1
        if high_risk:
            st["high_risk"] += 1

        row = {
            "doc_id": doc["doc_id"],
            "filename": doc["filename"],
            "category": cat,
            "source_id": doc["source_id"],
            "pages": doc["pages"],
            "ok": True,
            "status": status,
            "elapsed_ms": elapsed,
            "poppler_ocr_pages": poppler_pages,
            "inspector_ocr_pages": inspector_pages,
            "agreement": agree,
            "false_skip_candidates_1idx": false_skip,
            "unnecessary_ocr_candidates_1idx": unnecessary,
            "high_risk_false_skip_candidate": high_risk,
            "inspector_type": insp.get("pdf_type"),
            "inspector_confidence": insp.get("confidence"),
            "has_encoding_issues": insp.get("has_encoding_issues"),
            "markdown_quality": insp.get("markdown_quality"),
            "detections": dets,
            "poppler_quality_gates": cmp_.get("poppler_quality_gates"),
            "influences_ocr_routing": cmp_.get("influences_ocr_routing"),
        }
        per_doc.append(row)

        if not agree or high_risk or any(dets.get(k) for k in (
            "mojibake", "cid_tounicode_failures", "reversed_or_corrupted_arabic",
            "suspicious_printable_but_meaningless", "inspector_no_ocr_while_poppler_ocr",
        )):
            disagreements.append(row)
        if high_risk or false_skip:
            false_skip_candidates.append(row)

        if (idx + 1) % 50 == 0:
            print(f"evaluated {idx+1}/{len(docs)}", flush=True)

    agree_n = sum(1 for r in per_doc if r.get("ok") and r.get("agreement"))
    ok_n = sum(1 for r in per_doc if r.get("ok"))

    # Arabic / broken-encoding focused slices
    arabic_cats = {"arabic_digital_cv", "scanned_arabic_cv", "bilingual_cv"}
    broken_cats = {"broken_encoding", "cid_tounicode_missing_font", "cid_tounicode"}
    arabic_rows = [r for r in per_doc if r.get("ok") and r.get("category") in arabic_cats]
    broken_rows = [r for r in per_doc if r.get("ok") and r.get("category") in broken_cats]

    summary = {
        "wave": "pdf_inspector_corpus_wave2_shadow_eval",
        "created_at": utc_now(),
        "mode": "offline_shadow",
        "paid_ocr_invoked": False,
        "corpus_valid_pdfs": len(docs),
        "evaluated": len(per_doc),
        "successful_inspector_runs": success,
        "timeouts": timeout_n,
        "errors": error_n,
        "fail_open_count": fail_open_n,
        "agreement_rate_pct": pct(agree_n, ok_n),
        "agreement_count": agree_n,
        "disagreement_count": ok_n - agree_n,
        "inspector_fewer_ocr_docs": sum(1 for r in per_doc if r.get("false_skip_candidates_1idx")),
        "inspector_more_ocr_docs": sum(1 for r in per_doc if r.get("unnecessary_ocr_candidates_1idx")),
        "high_risk_false_skip_docs": sum(1 for r in per_doc if r.get("high_risk_false_skip_candidate")),
        "overhead_ms": {
            "n": len(overheads),
            "p50": percentile(overheads, 50),
            "p95": percentile(overheads, 95),
            "p99": percentile(overheads, 99),
            "max": max(overheads) if overheads else None,
            "mean": round(statistics.fmean(overheads), 3) if overheads else None,
        },
        "detections": dict(detection_counts),
        "poppler_ocr_pages_total": poppler_ocr_pages_total,
        "inspector_ocr_pages_total": inspector_ocr_pages_total,
        "projected_mistral_cost_usd": {
            "assumption_usd_per_page": COST_USD_PER_PAGE,
            "poppler": round(poppler_ocr_pages_total * COST_USD_PER_PAGE, 4),
            "inspector": round(inspector_ocr_pages_total * COST_USD_PER_PAGE, 4),
            "pages_saved_if_inspector_used": poppler_ocr_pages_total - inspector_ocr_pages_total,
            "usd_saved_if_inspector_used": round(
                (poppler_ocr_pages_total - inspector_ocr_pages_total) * COST_USD_PER_PAGE, 4
            ),
        },
        "category_stats": {k: dict(v) for k, v in sorted(category_stats.items())},
        "arabic_rtl_slice": {
            "n": len(arabic_rows),
            "agree": sum(1 for r in arabic_rows if r.get("agreement")),
            "high_risk": sum(1 for r in arabic_rows if r.get("high_risk_false_skip_candidate")),
            "inspector_fewer": sum(1 for r in arabic_rows if r.get("false_skip_candidates_1idx")),
            "reversed_or_corrupted_arabic": sum(
                1 for r in arabic_rows if (r.get("detections") or {}).get("reversed_or_corrupted_arabic")
            ),
        },
        "broken_encoding_slice": {
            "n": len(broken_rows),
            "mojibake": sum(1 for r in broken_rows if (r.get("detections") or {}).get("mojibake")),
            "encoding_flag": sum(1 for r in broken_rows if r.get("has_encoding_issues")),
            "inspector_ocr_any": sum(1 for r in broken_rows if r.get("inspector_ocr_pages")),
            "poppler_ocr_any": sum(1 for r in broken_rows if r.get("poppler_ocr_pages")),
            "high_risk": sum(1 for r in broken_rows if r.get("high_risk_false_skip_candidate")),
        },
    }

    # Disagreement matrix by category
    matrix = []
    for cat, st in sorted(category_stats.items()):
        matrix.append({
            "category": cat,
            "n": st["n"],
            "agree": st["agree"],
            "disagree": st["n"] - st["agree"] - st["errors"] - st["timeouts"],
            "inspector_fewer_docs": st["inspector_fewer"],
            "inspector_more_docs": st["inspector_more"],
            "high_risk_docs": st["high_risk"],
            "poppler_ocr_pages": st["poppler_ocr_pages"],
            "inspector_ocr_pages": st["inspector_ocr_pages"],
            "agreement_pct": pct(st["agree"], max(st["n"] - st["errors"] - st["timeouts"], 1)),
        })
    summary["disagreement_matrix"] = matrix

    (RESULTS / "per_document.json").write_text(json.dumps(per_doc, indent=2, ensure_ascii=False))
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (RESULTS / "disagreements.json").write_text(json.dumps(disagreements, indent=2, ensure_ascii=False))
    (RESULTS / "false_skip_candidates.json").write_text(
        json.dumps(false_skip_candidates, indent=2, ensure_ascii=False)
    )

    # Representative failure artifacts: sample high-risk + broken encoding + arabic disagree
    samples = []
    for pred in (
        lambda r: r.get("high_risk_false_skip_candidate"),
        lambda r: r.get("category") == "broken_encoding",
        lambda r: r.get("category") == "arabic_digital_cv" and not r.get("agreement"),
        lambda r: r.get("category") == "scanned_image_only_cv" and not r.get("agreement"),
        lambda r: (r.get("detections") or {}).get("mojibake"),
    ):
        for r in per_doc:
            if r.get("ok") and pred(r) and r["doc_id"] not in {s["doc_id"] for s in samples}:
                samples.append(r)
                if sum(1 for s in samples if pred(s)) >= 3:
                    break
    (ARTIFACTS / "representative_failures.json").write_text(
        json.dumps(samples[:40], indent=2, ensure_ascii=False)
    )

    # Staging subset: small approved mix, synthetic only, no full corpus intake
    staging_plan = pick_staging_subset(per_doc, docs)
    (STAGING / "staging_subset_manifest.json").write_text(
        json.dumps(staging_plan, indent=2, ensure_ascii=False)
    )
    # Copy only the subset files into staging_subset/pdfs
    pdf_dir = STAGING / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    for item in staging_plan["documents"]:
        src = EVID / item["rel_path"]
        dest = pdf_dir / item["filename"]
        if src.exists() and not dest.exists():
            shutil.copy2(src, dest)

    print(json.dumps({
        "evaluated": summary["evaluated"],
        "agreement_rate_pct": summary["agreement_rate_pct"],
        "high_risk_false_skip_docs": summary["high_risk_false_skip_docs"],
        "overhead_ms": summary["overhead_ms"],
        "projected_pages_saved": summary["projected_mistral_cost_usd"]["pages_saved_if_inspector_used"],
        "staging_subset_n": staging_plan["count"],
    }, indent=2))
    return 0


def pick_staging_subset(per_doc: list[dict[str, Any]], docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Small approved subset for future staging intake testing (owner approval required)."""
    by_id = {d["doc_id"]: d for d in docs}
    wanted = [
        ("english_digital_cv", 4),
        ("arabic_digital_cv", 4),
        ("bilingual_cv", 2),
        ("multicolumn_cv", 2),
        ("design_heavy_cv", 2),
        ("scanned_image_only_cv", 3),
        ("mixed_digital_scanned", 2),
        ("table_heavy_cv", 2),
        ("broken_encoding", 2),
        ("cid_tounicode_missing_font", 1),
        ("rotated_scan_cv", 1),
        ("lowres_compressed_scan_cv", 1),
    ]
    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for cat, n in wanted:
        rows = [r for r in per_doc if r.get("ok") and r.get("category") == cat and r["doc_id"] not in used]
        # Prefer one disagreement if present, else first
        rows_sorted = sorted(rows, key=lambda r: (r.get("agreement", True), not r.get("high_risk_false_skip_candidate", False)))
        for r in rows_sorted[:n]:
            base = by_id[r["doc_id"]]
            selected.append({
                **{k: base[k] for k in (
                    "doc_id", "filename", "rel_path", "sha256", "pages", "category",
                    "source_id", "expected_ocr_policy", "contains_real_pii", "synthetic",
                )},
                "eval_agreement": r.get("agreement"),
                "eval_high_risk": r.get("high_risk_false_skip_candidate"),
                "eval_poppler_ocr": r.get("poppler_ocr_pages"),
                "eval_inspector_ocr": r.get("inspector_ocr_pages"),
            })
            used.add(r["doc_id"])
    return {
        "purpose": "Approved small subset for future staging intake testing only",
        "production_forbidden": True,
        "create_candidate_records": False,
        "owner_approval_required_before_staging_intake": True,
        "count": len(selected),
        "documents": selected,
        "notes": (
            "Do not insert the full Wave 2 corpus into staging/production. "
            "This subset is synthetic-only and sized for smoke/intake harnesses."
        ),
    }


if __name__ == "__main__":
    raise SystemExit(main())
