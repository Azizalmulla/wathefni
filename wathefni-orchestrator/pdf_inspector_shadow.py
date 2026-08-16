"""pdf-inspector Shadow Advisor Wave 1 — CV PDFs only.

Observability only. Never changes Poppler routing, authoritative text, Mistral
calls, or downstream CV results. Fail-open on any inspector error/timeout.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any

logger = logging.getLogger("wathefni.pdf_inspector_shadow")

_ON = frozenset({"1", "true", "on", "yes", "enabled"})
CONTRACT = "pdf_inspector_shadow_advisor_wave1"
DEFAULT_TIMEOUT_MS = 500  # hard fail-open; acceptance p95 overhead is <=150ms
MAX_PAGES_FOR_SHADOW = 10

_MOJIBAKE_RE = re.compile(
    r"(Ã.|Â.|Ù.|Ø.|ð.|�|\ufffd|ÃÑ|Ùn|Â\x9d)",
)
_CID_HINT_RE = re.compile(r"(/CID|/Identity-H|ToUnicode|Identity-V|cid:)", re.I)
# Common visual symptoms of reversed/corrupted Arabic presentation forms without
# expected Arabic letters nearby, or high isolated presentation-form density.
_ARABIC_LETTER_RE = re.compile(r"[\u0600-\u06FF]")
_ARABIC_PRESENTATION_RE = re.compile(r"[\uFB50-\uFDFF\uFE70-\uFEFF]")


def shadow_enabled() -> bool:
    raw = (os.environ.get("WATHEFNI_PDF_INSPECTOR_SHADOW") or "").strip().lower()
    return raw in _ON


def shadow_timeout_ms() -> int:
    raw = (os.environ.get("WATHEFNI_PDF_INSPECTOR_SHADOW_TIMEOUT_MS") or "").strip()
    try:
        value = int(raw) if raw else DEFAULT_TIMEOUT_MS
    except ValueError:
        value = DEFAULT_TIMEOUT_MS
    return max(50, min(value, 5000))


def _normalize_ocr_pages(pages: list[Any], *, page_count: int) -> list[int]:
    vals = sorted({int(p) for p in (pages or []) if str(p).lstrip("-").isdigit()})
    if not vals:
        return []
    if any(v == 0 for v in vals):
        return [v + 1 for v in vals if 0 <= v < max(page_count, 1)]
    # Clamp to page_count when clearly 1-indexed.
    return [v for v in vals if 1 <= v <= max(page_count, 1)]


def _markdown_quality_metrics(markdown: str | None, plain: str | None = None) -> dict[str, Any]:
    text = str(markdown or "")
    plain_text = str(plain or "")
    sample = text or plain_text
    chars = len(sample)
    words = len(re.findall(r"\S+", sample))
    arabic_chars = len(_ARABIC_LETTER_RE.findall(sample))
    printable = sum(1 for ch in sample if ch.isprintable() and not ch.isspace())
    alpha = sum(1 for ch in sample if ch.isalpha())
    replacement = sample.count("\ufffd") + sample.count("�")
    mojibake_hits = len(_MOJIBAKE_RE.findall(sample))
    presentation = len(_ARABIC_PRESENTATION_RE.findall(sample))
    alpha_ratio = round(alpha / max(printable, 1), 4) if printable else 0.0
    suspicious_printable = bool(
        chars >= 40
        and words >= 6
        and alpha_ratio < 0.35
        and arabic_chars == 0
    )
    reversed_or_corrupted_arabic = bool(
        (presentation >= 8 and arabic_chars == 0)
        or (arabic_chars >= 20 and mojibake_hits >= 3)
        or (replacement >= 8 and arabic_chars > 0)
    )
    return {
        "markdown_len": len(text),
        "plain_len": len(plain_text),
        "chars": chars,
        "words": words,
        "arabic_chars": arabic_chars,
        "alpha_ratio": alpha_ratio,
        "replacement_chars": replacement,
        "mojibake_hits": mojibake_hits,
        "arabic_presentation_forms": presentation,
        "markdown_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else None,
        "suspicious_printable_but_meaningless": suspicious_printable,
        "reversed_or_corrupted_arabic": reversed_or_corrupted_arabic,
        "cid_tounicode_hint": bool(_CID_HINT_RE.search(sample)),
    }


def _poppler_pages_needing_ocr(assessments: list[Any]) -> list[int]:
    out: list[int] = []
    for a in assessments or []:
        disposition = str(getattr(a, "disposition", "") or "")
        if disposition == "needs_ocr":
            out.append(int(getattr(a, "page_number")))
    return sorted(set(out))


def _poppler_quality_reasons(assessments: list[Any]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    for a in assessments or []:
        reason = str(getattr(a, "reason", "") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "reason_counts": reasons,
        "quality_gate_failed_pages": [
            int(getattr(a, "page_number"))
            for a in (assessments or [])
            if str(getattr(a, "reason", "") or "") in {
                "quality_gate_failed",
                "corrupt_or_unusable_text",
            }
        ],
    }


def _call_process_pdf(path: str) -> dict[str, Any]:
    import pdf_inspector as pi

    t0 = time.perf_counter()
    processed = pi.process_pdf(path)
    wall_ms = int((time.perf_counter() - t0) * 1000)
    markdown = getattr(processed, "markdown", None)
    plain = None
    try:
        plain = pi.extract_text(path)
    except Exception:
        plain = None
    page_count = int(getattr(processed, "page_count", 0) or 0)
    ocr_pages = _normalize_ocr_pages(
        list(getattr(processed, "pages_needing_ocr", []) or []),
        page_count=page_count,
    )
    quality = _markdown_quality_metrics(markdown, plain)
    return {
        "ok": True,
        "wall_ms": wall_ms,
        "library_processing_time_ms": getattr(processed, "processing_time_ms", None),
        "pdf_type": getattr(processed, "pdf_type", None),
        "confidence": getattr(processed, "confidence", None),
        "has_encoding_issues": getattr(processed, "has_encoding_issues", None),
        "is_complex_layout": getattr(processed, "is_complex_layout", None),
        "pages_with_tables": list(getattr(processed, "pages_with_tables", []) or []),
        "pages_with_columns": list(getattr(processed, "pages_with_columns", []) or []),
        "page_count": page_count,
        "pages_needing_ocr_1idx": ocr_pages,
        "title": getattr(processed, "title", None),
        "markdown_quality": quality,
    }


def compare_shadow_to_poppler(
    *,
    inspector: dict[str, Any],
    assessments: list[Any],
) -> dict[str, Any]:
    poppler_ocr = _poppler_pages_needing_ocr(assessments)
    inspector_ocr = list(inspector.get("pages_needing_ocr_1idx") or [])
    poppler_set = set(poppler_ocr)
    inspector_set = set(inspector_ocr)
    false_skip_candidates = sorted(poppler_set - inspector_set)
    unnecessary_ocr_candidates = sorted(inspector_set - poppler_set)
    quality = inspector.get("markdown_quality") or {}
    detections = {
        "mojibake": bool((quality.get("mojibake_hits") or 0) > 0)
        or bool((quality.get("replacement_chars") or 0) >= 3),
        "cid_tounicode_failures": bool(quality.get("cid_tounicode_hint")),
        "reversed_or_corrupted_arabic": bool(quality.get("reversed_or_corrupted_arabic")),
        "suspicious_printable_but_meaningless": bool(
            quality.get("suspicious_printable_but_meaningless")
        ),
        "inspector_no_ocr_while_poppler_ocr": bool(false_skip_candidates),
        "inspector_encoding_flag": bool(inspector.get("has_encoding_issues")),
    }
    # Elevate false-skip risk when Poppler demanded OCR for quality/encoding reasons
    # and inspector claims clean text_based with no OCR pages.
    poppler_quality = _poppler_quality_reasons(assessments)
    high_risk_false_skip = bool(
        false_skip_candidates
        and not inspector_ocr
        and str(inspector.get("pdf_type") or "") in {"text_based", "mixed"}
        and (
            detections["mojibake"]
            or detections["reversed_or_corrupted_arabic"]
            or detections["suspicious_printable_but_meaningless"]
            or poppler_quality["quality_gate_failed_pages"]
            or inspector.get("has_encoding_issues") is False
        )
    )
    return {
        "poppler_pages_needing_ocr_1idx": poppler_ocr,
        "inspector_pages_needing_ocr_1idx": inspector_ocr,
        "agreement": poppler_set == inspector_set,
        "false_skip_candidates_1idx": false_skip_candidates,
        "unnecessary_ocr_candidates_1idx": unnecessary_ocr_candidates,
        "high_risk_false_skip_candidate": high_risk_false_skip,
        "poppler_quality_gates": poppler_quality,
        "detections": detections,
        "influences_ocr_routing": False,
        "authoritative_router": "poppler_assess_pdf_pages",
    }


def run_pdf_inspector_shadow(
    path: Path | str,
    assessments: list[Any] | None = None,
    *,
    page_count_hint: int | None = None,
) -> dict[str, Any]:
    """Run process_pdf beside Poppler. Always fail-open. Never mutates assessments."""
    enabled = shadow_enabled()
    base: dict[str, Any] = {
        "contract": CONTRACT,
        "enabled": enabled,
        "influences_ocr_routing": False,
        "authoritative_text_source": "poppler_or_existing_pipeline",
        "ok": False,
    }
    if not enabled:
        base["skipped"] = "flag_off"
        return base

    pdf_path = Path(path)
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        base["skipped"] = "not_pdf"
        return base

    assessments = list(assessments or [])
    page_count = page_count_hint or len(assessments) or 0
    if page_count and page_count > MAX_PAGES_FOR_SHADOW:
        # Still allow, but mark oversized for p95 reporting filters.
        base["oversized_for_p95_budget"] = True

    timeout_ms = shadow_timeout_ms()
    base["timeout_ms"] = timeout_ms
    started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_call_process_pdf, str(pdf_path))
            inspector = fut.result(timeout=timeout_ms / 1000.0)
        wall_ms = int((time.perf_counter() - started) * 1000)
        comparison = compare_shadow_to_poppler(
            inspector=inspector,
            assessments=assessments,
        )
        return {
            **base,
            "ok": True,
            "fail_open": False,
            "wall_ms": wall_ms,
            "inspector": {
                "pdf_type": inspector.get("pdf_type"),
                "confidence": inspector.get("confidence"),
                "pages_needing_ocr_1idx": inspector.get("pages_needing_ocr_1idx"),
                "has_encoding_issues": inspector.get("has_encoding_issues"),
                "processing_time_ms": inspector.get("library_processing_time_ms"),
                "wall_ms": inspector.get("wall_ms"),
                "page_count": inspector.get("page_count"),
                "is_complex_layout": inspector.get("is_complex_layout"),
                "pages_with_tables": inspector.get("pages_with_tables"),
                "pages_with_columns": inspector.get("pages_with_columns"),
                "markdown_quality": inspector.get("markdown_quality"),
            },
            "comparison": comparison,
            "metrics": {
                "pdf_inspector_poppler_ocr_page_disagreement": int(
                    not comparison["agreement"]
                ),
                "pdf_inspector_false_skip_candidate": int(
                    bool(comparison["false_skip_candidates_1idx"])
                ),
                "pdf_inspector_high_risk_false_skip_candidate": int(
                    bool(comparison["high_risk_false_skip_candidate"])
                ),
                "pdf_inspector_encoding_issue_rate": int(
                    bool(inspector.get("has_encoding_issues"))
                ),
                "pdf_inspector_mojibake": int(comparison["detections"]["mojibake"]),
                "pdf_inspector_cid_tounicode_failures": int(
                    comparison["detections"]["cid_tounicode_failures"]
                ),
                "pdf_inspector_reversed_or_corrupted_arabic": int(
                    comparison["detections"]["reversed_or_corrupted_arabic"]
                ),
                "pdf_inspector_suspicious_printable_but_meaningless": int(
                    comparison["detections"]["suspicious_printable_but_meaningless"]
                ),
                "pdf_inspector_no_ocr_while_poppler_ocr": int(
                    comparison["detections"]["inspector_no_ocr_while_poppler_ocr"]
                ),
                "pdf_inspector_shadow_wall_ms": wall_ms,
            },
        }
    except FuturesTimeout:
        wall_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "pdf_inspector_shadow_timeout path=%s timeout_ms=%s wall_ms=%s",
            pdf_path.name,
            timeout_ms,
            wall_ms,
        )
        return {
            **base,
            "ok": False,
            "fail_open": True,
            "error": "timeout",
            "wall_ms": wall_ms,
            "comparison": {
                "poppler_pages_needing_ocr_1idx": _poppler_pages_needing_ocr(assessments),
                "influences_ocr_routing": False,
                "authoritative_router": "poppler_assess_pdf_pages",
            },
            "metrics": {
                "pdf_inspector_shadow_timeout": 1,
                "pdf_inspector_shadow_wall_ms": wall_ms,
            },
        }
    except Exception as exc:  # noqa: BLE001 — fail-open is mandatory
        wall_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "pdf_inspector_shadow_fail_open path=%s error=%s",
            pdf_path.name,
            type(exc).__name__,
        )
        return {
            **base,
            "ok": False,
            "fail_open": True,
            "error": f"{type(exc).__name__}:{str(exc)[:180]}",
            "wall_ms": wall_ms,
            "comparison": {
                "poppler_pages_needing_ocr_1idx": _poppler_pages_needing_ocr(assessments),
                "influences_ocr_routing": False,
                "authoritative_router": "poppler_assess_pdf_pages",
            },
            "metrics": {
                "pdf_inspector_shadow_error": 1,
                "pdf_inspector_shadow_wall_ms": wall_ms,
            },
        }


def attach_shadow_metadata(
    metadata: dict[str, Any] | None,
    shadow: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(metadata or {})
    if shadow:
        out["pdf_inspector_shadow"] = shadow
    return out


def record_shadow_run(
    record_fn: Any,
    *,
    company_code: str | None,
    document_id: str | None,
    app_key: str | None,
    content_sha256: str | None,
    shadow: dict[str, Any],
) -> None:
    """Persist a non-authoritative audit row. Never raises into the CV path."""
    if not callable(record_fn):
        return
    try:
        record_fn(
            company_code=company_code,
            document_id=document_id,
            app_key=app_key,
            content_sha256=content_sha256,
            stage="pdf_inspector_shadow",
            tier="shadow_advisor",
            provider="pdf_inspector",
            actual_request_model="process_pdf",
            provider_response_model="pdf-inspector",
            pages_requested=None,
            pages_processed=(shadow.get("inspector") or {}).get("page_count"),
            billable_pages=0,
            estimated_cost_usd=0.0,
            latency_ms=shadow.get("wall_ms"),
            provider_request_id=None,
            quality_ok=None,
            cache_hit=False,
            error=shadow.get("error"),
            metadata={
                "contract": CONTRACT,
                "influences_ocr_routing": False,
                "shadow": shadow,
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("pdf_inspector_shadow_record_failed")
